"""Observe, diagnose, repair, and verify a flaky pytest test."""

import argparse
import difflib
import json
import shutil
import sys
import tokenize
from pathlib import Path

from agent.repair import AIRepairAgent
from analysis.ast_inspector import ASTInspector
from analysis.classifier import FlakinessClassifier
from execution.run import TestRunner


def repair_test(target, runs=10, max_retries=3):
    """Try up to max_retries patches, restoring the original on failure."""
    if runs < 1 or max_retries < 1:
        raise ValueError("Runs and maximum attempts must be positive.")
    file_path = Path(target.split("::", 1)[0])
    if not file_path.is_file():
        raise FileNotFoundError(f"Test file does not exist: {file_path}")
    with tokenize.open(file_path) as source_file:
        original = source_file.read()
        encoding = source_file.encoding

    runner = TestRunner(target)
    evidence = runner.run_perturbations(runs)
    diagnosis = FlakinessClassifier(evidence).classify()
    suspicious_vars = ASTInspector(file_path).detect_shared_state()
    print(json.dumps(diagnosis, indent=2))
    if diagnosis["diagnosis_category"] == "Deterministic Pass":
        print("Test passes under all conditions. Nothing to repair.")
        return 0

    agent = AIRepairAgent()
    backup = file_path.with_name(file_path.name + ".bak")
    # Do not overwrite a backup from an earlier repair session.
    with backup.open("xb") as backup_file:
        backup_file.write(file_path.read_bytes())
    trail = [{"stage": "observe", "evidence": evidence}]
    feedback = None
    success = False
    try:
        for attempt in range(1, max_retries + 1):
            print(f"Repair attempt {attempt}/{max_retries}")
            result = {"attempt": attempt}
            try:
                patch = agent.generate_fix(original, diagnosis, suspicious_vars, feedback)
                result["patched_source"] = patch
                file_path.write_text(patch, encoding=encoding)
                new_evidence = runner.run_perturbations(runs)
                result["evidence"] = new_evidence
                if (new_evidence["full_suite_pass_rate"] == 100.0
                        and new_evidence["shuffled_pass_rate"] == 100.0):
                    success = True
                    trail.append(result)
                    print("Repair succeeded.")
                    print("".join(difflib.unified_diff(
                        original.splitlines(keepends=True), patch.splitlines(keepends=True),
                        fromfile=str(backup), tofile=str(file_path),
                    )), end="")
                    return 0
            except Exception as exc:
                # API errors, bad patches, and subprocess failures count as attempts.
                result["error"] = f"{type(exc).__name__}: {exc}"
            trail.append(result)
            feedback = result
        print("Repair failed after all attempts. Evidence trail:")
        print(json.dumps(trail, indent=2))
        return 1
    finally:
        if not success:
            shutil.copyfile(backup, file_path)
            print(f"Original file restored from {backup}.")


def positive_int(value):
    """Validate a positive integer command-line option."""
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None):
    """Parse CLI arguments and report errors without a long traceback."""
    parser = argparse.ArgumentParser(description="Diagnose and repair flaky pytest tests.")
    parser.add_argument("target", help="test_file::test_name (pytest node ID)")
    parser.add_argument("--runs", type=positive_int, default=10)
    parser.add_argument("--max-retries", type=positive_int, default=3,
                        help="maximum total repair attempts (default: 3)")
    args = parser.parse_args(argv)
    try:
        return repair_test(args.target, args.runs, args.max_retries)
    except KeyboardInterrupt:
        print("Repair interrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
