"""Launch the fixed sandbox helper and publish only safe result fields."""
import json
import logging
import math
import os
import subprocess
from pathlib import Path
from api.activity import public_activity

logger = logging.getLogger(__name__)


def clean_directory(job_id):
    """Privileged cleanup accepts only a UUID under the helper's fixed work root."""
    try:
        subprocess.run(["sudo", "-n", "/usr/local/bin/flake-sandbox", "--clean", job_id],
                       check=True, timeout=15, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.SubprocessError as exc:
        raise OSError("Sandbox directory cleanup failed") from exc


def public_result(report, secret, work_root):
    """Never publish subprocess output, traces, or internal evidence paths."""
    rates = ("baseline_pass_rate", "shuffled_pass_rate", "isolated_pass_rate", "full_suite_pass_rate")
    result = {
        "diagnosis": {key: report["diagnosis"][key] for key in ("diagnosis_category", "diagnosis_description")},
        "before": {key: report["before"][key] for key in rates},
        "after": {key: report["after"][key] for key in rates},
        "suspicious_vars": report["suspicious_vars"],
        "original_source": report["original_source"], "patched_source": report["patched_source"],
        "attempts": report["attempts"], "success": report["success"],
        "activity": public_activity(report.get("activity", [])),
    }
    for group in (result["before"], result["after"]):
        if not all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 100
                   for value in group.values()):
            raise ValueError("Invalid pass rates in worker report")
    if type(result["success"]) is not bool or type(result["attempts"]) is not int or not 0 <= result["attempts"] <= 3:
        raise ValueError("Invalid repair outcome in worker report")
    if not isinstance(result["suspicious_vars"], list) or not all(isinstance(name, str) and name.isidentifier() for name in result["suspicious_vars"]):
        raise ValueError("Invalid shared-variable names in worker report")
    if not all(isinstance(result[key], str) and len(result[key]) <= 65536 for key in ("original_source", "patched_source")):
        raise ValueError("Invalid source in worker report")
    encoded = json.dumps(result)
    # Do not deliver a generated file that accidentally repeats execution context or credentials.
    forbidden = [str(work_root), "/app/", "/job", "/data/", "/work/", "Traceback (most recent call last)", "sk-ant-"]
    if secret:
        forbidden.append(secret)
    if any(value in encoded for value in forbidden):
        raise ValueError("Result contains private execution details")
    return result


def execute_job(job_id, store):
    """The root-owned helper performs a resource-limited subprocess.run."""
    secret = os.getenv("ANTHROPIC_API_KEY", "")
    if not secret:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")
    proc = subprocess.run(
        ["sudo", "-n", "/usr/local/bin/flake-sandbox", job_id],
        input=json.dumps({"api_key": secret}), capture_output=True, text=True,
        timeout=int(os.getenv("SANDBOX_WALL_SECONDS", "90")) + 10, check=False,
    )
    if proc.stderr:
        logger.warning("Worker diagnostics: %s", proc.stderr)
    if proc.returncode not in (0, 1):
        logger.error("Sandbox failed: %s %s", proc.stdout, proc.stderr)
        raise RuntimeError("Sandbox execution failed")
    report_file = store.work_root / job_id / "result.json"
    if report_file.is_symlink() or report_file.stat().st_size > 1_000_000:
        raise ValueError("Invalid sandbox report")
    report = json.loads(report_file.read_text(encoding="utf-8"))
    return public_result(report, secret, store.work_root)
