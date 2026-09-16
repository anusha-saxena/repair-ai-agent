"""Manual end-to-end repair test using real Anthropic API credits."""
import os
import subprocess
import sys
import pytest
from execution.run import TestRunner as Runner


@pytest.mark.slow
def test_real_repair_reaches_success(project_root, pollution_copy):
    dotenv = pytest.importorskip("dotenv")
    pytest.importorskip("anthropic")
    dotenv.load_dotenv(project_root / ".env")
    if not os.getenv("ANTHROPIC_API_KEY", "").strip():
        pytest.skip("ANTHROPIC_API_KEY is needed for the real API test.")
    original = pollution_copy.read_bytes()
    target = f"{pollution_copy}::test_b_victim"
    result = subprocess.run(
        [sys.executable, str(project_root / "main.py"), target,
         "--runs", "5", "--max-retries", "3"],
        cwd=project_root, capture_output=True, text=True, timeout=900,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Repair succeeded." in result.stdout
    assert "Repair attempt 4/" not in result.stdout
    assert pollution_copy.with_name(pollution_copy.name + ".bak").read_bytes() == original
    verified = Runner(target).run_perturbations(5)
    assert verified["full_suite_pass_rate"] == 100.0
    assert verified["shuffled_pass_rate"] == 100.0
