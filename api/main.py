"""Demo-only API with automatic 24-hour job expiry."""
import asyncio
from contextlib import asynccontextmanager, suppress
import json
import logging
import os
from pathlib import Path
import shutil
import time
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.catalog import load_demos
from api.runner import clean_directory, execute_job
from api.store import JobStore

logger = logging.getLogger(__name__)


async def expiry_loop(store):
    """Startup performs the first sweep; this task repeats it every hour."""
    while True:
        await asyncio.sleep(3600)
        try:
            await asyncio.to_thread(store.cleanup_expired)
        except Exception:
            logger.exception("Hourly job expiry failed; will retry next hour")


def create_app(database=None, work_root=None, demo_root=None, executor=None, rate_limit=None):
    """Construct isolated app state; injected settings are for server-side tests only."""
    project = Path(__file__).resolve().parents[1]
    database = database or os.getenv("JOB_DATABASE", "/data/jobs.sqlite3")
    work_root = work_root or os.getenv("JOB_WORK_ROOT", "/work/jobs")
    demo_root = demo_root or project / "demos"
    limit = rate_limit if rate_limit is not None else int(os.getenv("RATE_LIMIT_PER_HOUR", "5"))
    if limit < 1:
        raise ValueError("Rate limit must be positive")
    executor = executor or execute_job

    @asynccontextmanager
    async def lifespan(app):
        app.state.demos = load_demos(demo_root)
        app.state.store = JobStore(database, work_root, cleanup_fallback=clean_directory if executor is execute_job else None)
        await asyncio.to_thread(app.state.store.cleanup_expired)
        await asyncio.to_thread(app.state.store.mark_interrupted)
        app.state.semaphore = asyncio.Semaphore(1)
        task = asyncio.create_task(expiry_loop(app.state.store))
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(title="FlakeDetective", lifespan=lifespan)
    origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    parsed_origin = urlparse(origin)
    if (parsed_origin.scheme not in ("http", "https") or not parsed_origin.netloc
            or parsed_origin.path or parsed_origin.query or parsed_origin.fragment or parsed_origin.username):
        raise ValueError("FRONTEND_ORIGIN must be one specific origin")
    app.add_middleware(CORSMiddleware, allow_origins=[origin], allow_methods=["GET", "POST"], allow_headers=["Content-Type"])

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error("API request failed", exc_info=(type(exc), exc, exc.__traceback__))
        return JSONResponse(status_code=500, content={"detail": "Something went wrong. Please try again."})

    async def run_job(job_id):
        store = app.state.store
        async with app.state.semaphore:
            if not store.get(job_id):
                return
            store.update(job_id, "running")
            try:
                result = await asyncio.to_thread(executor, job_id, store)
                store.update(job_id, "complete", result)
            except Exception:
                logger.exception("Job %s failed", job_id)
                store.update(job_id, "error", {"message": "The demo could not finish. Please try again."})

    @app.get("/demos")
    async def demos():
        return [demo["manifest"] for demo in app.state.demos.values()]

    @app.post("/run/{demo_id}", status_code=202)
    async def submit(demo_id: str, request: Request, background_tasks: BackgroundTasks):
        demo = app.state.demos.get(demo_id)
        if demo is None:
            raise HTTPException(404, "Demo not found.")
        # No request body is accepted, including URLs, paths, or source strings.
        if await request.body():
            raise HTTPException(400, "This endpoint accepts a demo ID only, with no request body.")
        store = app.state.store
        job_id = uuid4().hex
        ip = request.client.host if request.client else "unknown"
        if not store.reserve(job_id, demo_id, ip, limit):
            raise HTTPException(429, "Demo is rate-limited. Try again in a bit.", headers={"Retry-After": "3600"})
        directory = store.work_root / job_id
        try:
            directory.mkdir(mode=0o770)
            shutil.copyfile(demo["source"], directory / demo["source"].name)
            # This metadata is created by the allowlist lookup, never from a body.
            (directory / "job.json").write_text(json.dumps({"target": demo["manifest"]["target_test"]}))
        except Exception:
            store.update(job_id, "error", {"message": "The demo could not start. Please try again."})
            raise
        background_tasks.add_task(run_job, job_id)
        return {"job_id": job_id}

    @app.get("/status/{job_id}")
    async def status(job_id: str):
        row = app.state.store.get(job_id)
        if row is None:
            raise HTTPException(404, "Job not found or expired.")
        response = {"job_id": row["id"], "demo_id": row["demo_id"], "status": row["status"],
                    "created_at": row["created_at"], "elapsed_seconds": max(0, time.time() - row["created_at"])}
        if row["result_json"] is not None:
            response["result"] = json.loads(row["result_json"])
        return response

    return app


app = create_app()
