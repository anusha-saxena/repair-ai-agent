# repair-ai-agent
a developer tool that automatically detects flaky tests in a Python test suite, gathers structured evidence about why they're flaky through controlled perturbation experiments, classifies the likely root cause, and uses an AI agent to propose and validate a targeted fix.

Install dependencies and run from this directory:

```sh
python -m pip install -r requirements.txt
python main.py tests/test_phase2_demo.py::test_b_victim --runs 10 --max-retries 3
```

Set `ANTHROPIC_API_KEY` in your environment or this directory's `.env` file.
The model is configured in `agent/repair.py`. `--max-retries` is the total attempt limit.
Failed attempts are sent back to Claude with the patched source and failure
evidence. After all attempts fail, the original file is restored and the evidence
trail is printed. Successful repairs print a unified diff.

The original `.bak` file is kept after either outcome. Move it before starting
another repair of the same file; existing backups are never overwritten.
The current runner's suite mode runs the target test file, so the reported suite
pass rate covers that file rather than every test in the repository.

The repair loop can be tested without an API key:

```sh
python -m unittest discover -s tests -p test_repair.py
```

## Terminal folder fix

If Python reports `can't open file .../repair-ai-agent/execution/run.py`,
your terminal is in the outer workspace folder. The Python project is inside
the nested `repair-ai-agent/` folder. From the outer folder, run:

```sh
cd repair-ai-agent
ls execution
python execution/run.py tests/test_phase2_demo.py::test_b_victim 10
```

`ls execution` should list `process.py` and `run.py`. If your shell only has
`python3`, use that command or activate the outer virtual environment with
`source ../.venv/bin/activate`.

## Testing FlakeDetective

From the nested project folder, run the normal suite:

```sh
python -m pytest -q
```

The suite includes a subprocess integration test with five runs per mode.
The intentionally failing examples in `test_fixtures/` are excluded from default
collection by `testpaths = tests`. The older `tests/test_sample.py` and
`tests/test_phase2_demo.py` demos are also excluded unless explicitly targeted.
Temporary copies keep repairs and `.bak` files away from the checked-in examples.

Run the paid end-to-end test manually with an API key and the SDK installed:

```sh
python -m pytest tests/test_main_e2e.py --run-slow -v
```

The `slow` marker is registered and skipped by default, including in CI.
This manual test makes real API calls and requires a successful repair within
three attempts. Model availability, API access, and the generated patch can
affect its result.

Example diagnosis targets:

```sh
python execution/run.py demos/order_dependency/test_pollution.py::test_b_victim 5
python execution/run.py test_fixtures/stable/test_clean.py::test_addition 5
python execution/run.py test_fixtures/broken/test_real_bug.py::test_wrong_addition 5
python execution/run.py test_fixtures/standalone_flaky/test_random.py::test_random_threshold 5
```

The random example has a 50% failure probability per draw, so a short sample
can still pass or fail every time. Parser unit tests enforce the current strict
format: one Python code block, with prose outside the block rejected.

## Deployable demo

The `demos/` catalog contains shared-dictionary, mutable-default, and shared-counter
cases. Each submission repairs a temporary copy. No request can upload code or
provide an execution path or URL.

From the nested Python project directory, set `ANTHROPIC_API_KEY` in your shell
or `.env`, and review the placeholder settings in `.env.example`:

```sh
docker compose up --build -d
```

The API is bound to localhost port 8000. Place a TLS reverse proxy in front of
it for a public deployment. Set `FRONTEND_ORIGIN` to the exact frontend origin
and tune the resource and submission limits. See [SECURITY.md](SECURITY.md) for
Linux capability requirements, network restrictions, and the demo's limits.
Use the supplied Compose deployment; `docker run` alone does not enforce egress.

For Render, read the [deployment assessment](deploy/RENDER.md) first. Building
the Dockerfile alone does not supply the sandbox's Compose runtime settings.
The API accepts a `PORT` environment variable, but Render sandbox compatibility
still needs confirmation or a separate worker implementation.

## Static portfolio frontend

The frontend displays recordings captured from real local repairs. It does not
submit jobs, poll FastAPI, or call Anthropic. "Replay demo" reveals recorded
activity every half second before showing the saved diagnosis, pass rates,
repair attempts, and patch. Visitors can skip directly to results. The animation
is explicitly labelled as a recorded replay, and event times refer to the original
run. The live backend and CLI are still available separately.

Start the frontend:

```sh
cd frontend
cp .env.example .env
npm ci
npm run dev
```

Build the portfolio for production:

```sh
npm run build
```

Deploy on Vercel with Root Directory `frontend`, framework Vite, build command
`npm run build`, and output directory `dist`. No environment variables or backend
hosting are needed. Remove the old `VITE_API_URL` from Vercel; it is no longer used.
Never put an Anthropic key in frontend settings.

The three recordings live in `frontend/public/recordings/demos.json`. To refresh
them from the Python project directory, with your local Anthropic key configured:

```sh
python demos/record.py --runs 5 --max-retries 3
```

**Recording uses real Anthropic credits and executes generated patches locally.**
Use it only with the trusted curated demos, as with the local CLI. The script
works on temporary copies and keeps the existing catalog unless every repair
verifies. It publishes sanitized results without raw traces, credentials, or
internal paths. Commit refreshed recordings and redeploy to update the website.
The recorded patches are Claude-generated; timestamps and pass rates describe
those particular sampled runs, rather than a guarantee of future behavior.

API routes: `GET /demos`, `POST /run/{demo_id}` (no body), and
`GET /status/{job_id}`. Job status is `queued`, `running`, `complete`, or `error`.
A complete result has diagnosis, before/after rates, suspicious variables,
original and patched source, repair attempts, and a success flag. An unsuccessful
repair is a complete result with `success: false`; execution errors are `error`.
The UI shows recorded Observe/Diagnose/Repair/Verify events, pass-rate summaries,
and retry outcomes. Original demo source can be viewed before submitting a job.
The run log describes tool actions; it does not expose model internal reasoning,
raw tracebacks, or subprocess output.

Jobs become inaccessible after 24 hours. An asyncio sweep runs on startup and
every hour, deleting expired SQLite rows and their working directories. It also
removes old orphan directories. SQLite lives in the `jobs` named volume and
working files in the `work` volume; restarting the API does not reset the rate
limiter. The deployment intentionally runs one Uvicorn worker.

API and retention tests run without credits as part of `python -m pytest -q`.
The slow real repair test remains opt-in with `--run-slow`.

Container checks can be repeated with placeholder credentials and default limits:

```sh
docker compose --env-file .env.example -p flakedetective-check up --build -d
docker compose --env-file .env.example -p flakedetective-check exec -T api python - < deploy/check_sandbox.py
docker compose --env-file .env.example -p flakedetective-check down --volumes
```

These probes make no Messages API calls. They check file permissions, resource
limits, proxy allow/deny rules, expiry cleanup, and a short wall timeout.
Use this isolated test project name when removing its disposable volumes.
