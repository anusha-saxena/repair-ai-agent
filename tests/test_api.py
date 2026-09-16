"""Exercise the allowlist, privacy, rate limit, and lifecycle without paid API calls."""
import asyncio
import json
import os
import time
from uuid import uuid4
from unittest.mock import Mock

from fastapi.testclient import TestClient
import pytest

from api.main import create_app, expiry_loop
from api.runner import public_result
from api.store import JobStore


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.sqlite3", tmp_path / "work")


@pytest.fixture
def client(tmp_path, project_root):
    executor = Mock(return_value={"success": True, "attempts": 1})
    app = create_app(tmp_path / "api.sqlite3", tmp_path / "work",
                     project_root / "demos", executor=executor, rate_limit=5)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, app, executor


def test_catalog_contains_only_curated_demos(client):
    browser, _, _ = client
    response = browser.get("/demos")
    assert response.status_code == 200
    assert {demo["id"] for demo in response.json()} == {
        "order_dependency", "mutable_default_arg", "shared_counter"
    }
    assert "/Users/" not in response.text
    assert "source" not in response.json()[0]
    assert "def test_" in response.json()[0]["original_source"]


def test_unknown_demo_and_code_inputs_are_rejected(client):
    browser, _, executor = client
    assert browser.post("/run/unknown").status_code == 404
    assert browser.post("/run/%2e%2e%2fsecret").status_code == 404
    for body in ({"url": "https://example.com/repo"}, {"path": "/tmp/test.py"}, {"code": "print(1)"}):
        assert browser.post("/run/order_dependency", json=body).status_code == 400
    executor.assert_not_called()


def test_job_runs_against_copy_and_returns_result(client, project_root):
    browser, app, executor = client
    original = project_root / "demos/order_dependency/test_pollution.py"
    before = original.read_bytes()
    response = browser.post("/run/order_dependency")
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = browser.get(f"/status/{job_id}").json()
    assert job["status"] == "complete"
    assert job["result"]["success"] is True
    copied = app.state.store.work_root / job_id / "test_pollution.py"
    assert copied.read_bytes() == before
    assert original.read_bytes() == before
    executor.assert_called_once()


def test_rate_limit_is_five_submissions_per_hour(client):
    browser, _, executor = client
    for _ in range(5):
        assert browser.post("/run/shared_counter").status_code == 202
    response = browser.post("/run/shared_counter")
    assert response.status_code == 429
    assert "rate-limited" in response.json()["detail"]
    assert executor.call_count == 5


def test_execution_errors_are_generic(client):
    browser, _, executor = client
    executor.side_effect = RuntimeError("secret-key /private/path Traceback")
    job_id = browser.post("/run/order_dependency").json()["job_id"]
    response = browser.get(f"/status/{job_id}")
    assert response.json()["status"] == "error"
    assert "secret-key" not in response.text
    assert "/private/path" not in response.text
    assert "Traceback" not in response.text


def test_cors_allows_only_configured_origin(client, monkeypatch):
    browser, _, _ = client
    # Fixture constructs the app before this test; default development origin is explicit.
    origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173")
    assert browser.get("/demos", headers={"Origin": origin}).headers["access-control-allow-origin"] == origin
    assert "access-control-allow-origin" not in browser.get("/demos", headers={"Origin": "https://other.invalid"}).headers


def test_created_at_expiry_deletes_rows_and_temp_files(store):
    now = time.time()
    old_id, fresh_id, boundary_id = uuid4().hex, uuid4().hex, uuid4().hex
    for job_id, created in [(old_id, now - 86401), (fresh_id, now), (boundary_id, now - 86400)]:
        assert store.reserve(job_id, "order_dependency", job_id, 5, now=created)
        directory = store.work_root / job_id
        directory.mkdir()
        (directory / "test.py").write_text("STATE = {}")
        # Fresh mtime must not rescue a job with an old created_at.
        os.utime(directory, (now, now))
    assert store.get(old_id, now=now) is None
    assert store.cleanup_expired(now=now) == 1
    with store.connect() as db:
        assert db.execute("SELECT id FROM jobs WHERE id = ?", (old_id,)).fetchone() is None
    assert not (store.work_root / old_id).exists()
    assert (store.work_root / fresh_id).exists()
    assert (store.work_root / boundary_id).exists()
    assert store.cleanup_expired(now=now) == 0


def test_cleanup_does_not_follow_symlink_outside_work_root(store, tmp_path):
    now = time.time()
    job_id = uuid4().hex
    store.reserve(job_id, "order_dependency", "ip", 5, now=now - 90000)
    outside = tmp_path / "keep"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep")
    (store.work_root / job_id).symlink_to(outside, target_is_directory=True)
    store.cleanup_expired(now)
    assert (outside / "keep.txt").read_text() == "keep"
    assert not (store.work_root / job_id).is_symlink()


def test_expired_orphan_directory_is_removed(store):
    now = time.time()
    orphan = store.work_root / uuid4().hex
    orphan.mkdir()
    os.utime(orphan, (now - 90000, now - 90000))
    store.cleanup_expired(now)
    assert not orphan.exists()


def test_failed_cleanup_keeps_row_for_next_sweep(store, monkeypatch):
    now = time.time()
    job_id = uuid4().hex
    store.reserve(job_id, "order_dependency", "ip", 5, now=now - 90000)
    (store.work_root / job_id).mkdir()
    remove = store.remove_directory
    monkeypatch.setattr(store, "remove_directory", Mock(side_effect=OSError("disk unavailable")))
    assert store.cleanup_expired(now) == 0
    with store.connect() as db:
        assert db.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone() is not None
    monkeypatch.setattr(store, "remove_directory", remove)
    assert store.cleanup_expired(now) == 1


def test_rate_limit_resets_after_hour(store):
    now = time.time()
    for _ in range(5):
        assert store.reserve(uuid4().hex, "order_dependency", "ip", 5, now=now)
    assert not store.reserve(uuid4().hex, "order_dependency", "ip", 5, now=now)
    assert store.reserve(uuid4().hex, "order_dependency", "ip", 5, now=now + 3600)


def test_startup_sweeps_and_marks_interrupted_jobs(tmp_path, project_root):
    database, work = tmp_path / "jobs.sqlite3", tmp_path / "work"
    store = JobStore(database, work)
    old_id, fresh_id = uuid4().hex, uuid4().hex
    store.reserve(old_id, "order_dependency", "ip", 5, now=time.time() - 90000)
    store.reserve(fresh_id, "order_dependency", "ip", 5)
    (work / old_id).mkdir()
    app = create_app(database, work, project_root / "demos", executor=Mock())
    with TestClient(app) as browser:
        assert not (work / old_id).exists()
        assert browser.get(f"/status/{old_id}").status_code == 404
        assert browser.get(f"/status/{fresh_id}").json()["status"] == "error"


def test_hourly_task_repeats_and_can_be_cancelled(monkeypatch):
    store = Mock()
    sleeps = []
    async def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 3:
            raise asyncio.CancelledError
    monkeypatch.setattr("api.main.asyncio.sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(expiry_loop(store))
    assert sleeps == [3600, 3600, 3600]
    assert store.cleanup_expired.call_count == 2


def test_public_results_strip_traces_and_reject_secrets(tmp_path):
    rates = {key: 100.0 for key in ("baseline_pass_rate", "isolated_pass_rate", "shuffled_pass_rate", "full_suite_pass_rate")}
    report = {"diagnosis": {"diagnosis_category": "Order Dependency", "diagnosis_description": "Dirty state", "evidence": {"test_id": "/private/file"}},
              "before": {**rates, "mode_results": {"failure_traces": ["secret"]}}, "after": rates,
              "original_source": "STATE = {}", "patched_source": "STATE = {}", "suspicious_vars": ["STATE"],
              "attempts": 1, "success": True}
    assert "failure_traces" not in json.dumps(public_result(report, "key-value", tmp_path))
    report["patched_source"] = "KEY = 'key-value'"
    with pytest.raises(ValueError, match="private"):
        public_result(report, "key-value", tmp_path)


def test_status_exposes_recorded_activity_only(client):
    browser, app, _ = client
    job_id = browser.post("/run/order_dependency").json()["job_id"]
    path = app.state.store.work_root / job_id / "progress.json"
    path.write_text(json.dumps([
        {"kind": "observed", "elapsed_seconds": 3.0,
         "rates": {"baseline_pass_rate": 100.0, "shuffled_pass_rate": 40.0, "full_suite_pass_rate": 0.0},
         "failure_trace": "/private/path secret"},
        {"kind": "repairing", "elapsed_seconds": 4.0, "attempt": 1},
    ]))
    response = browser.get(f"/status/{job_id}")
    events = response.json()["activity"]
    assert "isolated 100.0%, shuffled 40.0%, suite 0.0%" in events[0]["message"]
    assert events[1]["phase"] == "repairing"
    assert "secret" not in response.text
    assert "/private/path" not in response.text


def test_activity_reader_rejects_malformed_and_symlink_files(tmp_path):
    from api.activity import read_activity
    directory = tmp_path / "job"
    directory.mkdir()
    path = directory / "progress.json"
    path.write_text("not json")
    assert read_activity(directory) == []
    path.write_text(json.dumps([{"kind": "unknown", "elapsed_seconds": 0}]))
    assert read_activity(directory) == []
    path.unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(json.dumps([{"kind": "observing", "elapsed_seconds": 0}]))
    path.symlink_to(outside)
    assert read_activity(directory) == []
