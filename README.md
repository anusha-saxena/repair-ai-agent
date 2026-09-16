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
python execution/run.py test_fixtures/order_dependency/test_pollution.py::test_b_victim 5
python execution/run.py test_fixtures/stable/test_clean.py::test_addition 5
python execution/run.py test_fixtures/broken/test_real_bug.py::test_wrong_addition 5
python execution/run.py test_fixtures/standalone_flaky/test_random.py::test_random_threshold 5
```

The random example has a 50% failure probability per draw, so a short sample
can still pass or fail every time. Parser unit tests enforce the current strict
format: one Python code block, with prose outside the block rejected.
