"""Run inside the test API container; no valid key or paid API requests."""
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4
from api.catalog import load_demos

print("API user:", os.getuid(), flush=True)
assert os.getuid() == 10001
print("Demo catalog count:", len(load_demos("/app/demos")), flush=True)
job_id = uuid4().hex
folder = Path("/work/jobs") / job_id
folder.mkdir(mode=0o770)
(folder / "job.json").write_text(json.dumps({"target": "test_probe.py::test_probe"}))
(folder / "test_probe.py").write_text("""import os
import resource
import socket
from urllib.parse import urlparse
from pathlib import Path
import pytest


def test_probe():
    assert os.getuid() == 10002
    assert resource.getrlimit(resource.RLIMIT_CPU)[0] == 60
    assert resource.getrlimit(resource.RLIMIT_AS)[0] == 512 * 1024 * 1024
    assert resource.getrlimit(resource.RLIMIT_NPROC)[0] == 32
    assert not Path('/data').exists()
    assert not Path('/work').exists()
    with pytest.raises(OSError):
        Path('/app/write_probe').write_text('denied')
    with pytest.raises(OSError):
        Path('/outside_probe').write_text('denied')
    Path('/tmp/write_probe').write_text('allowed')
    source = Path(__file__)
    source.write_text(source.read_text())
    Path('locked').mkdir(exist_ok=True)
    Path('locked').chmod(0)
    proxy = urlparse(os.environ['HTTPS_PROXY'])
    for host, expected in [('api.anthropic.com', b'200'), ('example.com', b'403')]:
        with socket.create_connection((proxy.hostname, proxy.port), timeout=5) as connection:
            connection.sendall(f'CONNECT {host}:443 HTTP/1.1\\r\\nHost: {host}:443\\r\\n\\r\\n'.encode())
            assert connection.recv(1024).split()[1] == expected
    for address in [('1.1.1.1', 443), ('127.0.0.1', 8000)]:
        with pytest.raises(OSError):
            socket.create_connection(address, timeout=0.2)
""")
result = subprocess.run(["sudo", "-n", "/usr/local/bin/flake-sandbox", job_id],
                        input=json.dumps({"api_key": "unused-placeholder"}) + "\n",
                        capture_output=True, text=True, timeout=100)
print("Sandbox return code:", result.returncode, flush=True)
if result.returncode:
    print(result.stderr, flush=True)
if (folder / "result.json").exists():
    report = json.loads((folder / "result.json").read_text())
    print("Probe classification:", report["diagnosis"]["diagnosis_category"], flush=True)
    print("Probe rates:", {key: value for key, value in report["before"].items() if key.endswith("pass_rate")}, flush=True)
assert result.returncode == 0
print("Filesystem, non-root user, and resource probes passed.", flush=True)

# Created-at cleanup must remove the complete sandbox-owned working directory.
from api.runner import clean_directory
from api.store import JobStore
store = JobStore("/data/probe.sqlite3", "/work/jobs", cleanup_fallback=clean_directory)
store.reserve(job_id, "order_dependency", "probe", 5, now=time.time() - 90000)
assert store.cleanup_expired() >= 1
assert not folder.exists()
print("Network allow/deny and created-at cleanup probes passed.", flush=True)

# A deliberately stuck subprocess must stop at the outer wall-clock deadline.
timeout_id = uuid4().hex
timeout_folder = Path("/work/jobs") / timeout_id
timeout_folder.mkdir(mode=0o770)
(timeout_folder / "job.json").write_text(json.dumps({"target": "test_timeout.py::test_timeout"}))
(timeout_folder / "test_timeout.py").write_text("def test_timeout():\n    while True:\n        pass\n")
environment = dict(os.environ, SANDBOX_WALL_SECONDS="1")
started = time.monotonic()
stuck = subprocess.run(["sudo", "-n", "/usr/local/bin/flake-sandbox", timeout_id],
                       input=json.dumps({"api_key": "unused-placeholder"}) + "\n",
                       capture_output=True, text=True, timeout=10, env=environment)
assert stuck.returncode == 2
assert time.monotonic() - started < 5
assert "wall-clock limit" in stuck.stderr
clean_directory(timeout_id)
print("Hard wall-clock timeout probe passed.", flush=True)
