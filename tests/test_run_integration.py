from execution.run import TestRunner as Runner
import json
import subprocess
import sys


def test_order_dependency_pass_rates(pollution_copy):
    evidence = Runner(f"{pollution_copy}::test_b_victim").run_perturbations(5)
    # These modes disable random ordering, giving exact expectations.
    assert evidence["isolated_pass_rate"] == 100.0
    assert evidence["full_suite_pass_rate"] == 0.0
    suite = evidence["mode_results"]["suite"]
    assert suite["failures"] == 5
    assert any("Another test left shared state" in trace for trace in suite["failure_traces"])
    # Five shuffled samples do not give a reliable statistical threshold.
    assert 0.0 <= evidence["shuffled_pass_rate"] <= 100.0


def test_cli_writes_structured_stable_result(project_root, fixture_root, tmp_path, monkeypatch):
    """The API's report format also works on the no-repair path without a key."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = fixture_root / "stable" / "test_clean.py"
    report_path = tmp_path / "report.json"
    progress_path = tmp_path / "progress.json"
    result = subprocess.run(
        [sys.executable, str(project_root / "main.py"), f"{path}::test_addition",
         "--runs", "1", "--json-report", str(report_path), "--progress-json", str(progress_path)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text())
    assert report["success"] is True
    assert report["attempts"] == 0
    assert report["diagnosis"]["diagnosis_category"] == "Deterministic Pass"
    assert report["original_source"] == report["patched_source"] == path.read_text()
    assert report["before"]["full_suite_pass_rate"] == report["after"]["full_suite_pass_rate"] == 100.0
    activity = json.loads(progress_path.read_text())
    assert activity == report["activity"]
    assert [event["kind"] for event in activity] == ["observing", "observed", "diagnosed", "completed"]
