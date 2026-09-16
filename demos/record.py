"""Capture real local repairs for the static portfolio (uses Anthropic credits)."""
import argparse
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.catalog import load_demos
from api.runner import public_result
from main import repair_test


def main():
    """Repair temporary copies and publish sanitized recordings, never raw logs."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--max-retries", type=int, default=3)
    args = parser.parse_args()
    if args.runs < 1 or not 1 <= args.max_retries <= 3:
        parser.error("runs must be positive and max-retries must be between 1 and 3")
    output = ROOT / "frontend" / "public" / "recordings"
    output.mkdir(parents=True, exist_ok=True)
    recordings = []
    for demo in load_demos(ROOT / "demos").values():
        manifest = demo["manifest"]
        print(f"Recording {manifest['id']} (real API calls)…", flush=True)
        with tempfile.TemporaryDirectory(prefix="flakedetective-record-") as directory:
            source = Path(directory) / demo["source"].name
            shutil.copyfile(demo["source"], source)
            reports = []
            # The orchestrator prints internal evidence; it is never published.
            with contextlib.redirect_stdout(io.StringIO()):
                repair_test(f"{source}::{demo['test_name']}", args.runs,
                            args.max_retries, on_result=reports.append)
            result = public_result(reports[0], os.getenv("ANTHROPIC_API_KEY", ""), directory)
        if not result["success"]:
            raise RuntimeError(f"{manifest['id']} did not verify; existing recordings were kept")
        recordings.append({**manifest, "recorded_at": datetime.now(timezone.utc).isoformat(),
                           "runs": args.runs, "result": result})
        print(f"Verified {manifest['id']} in {result['attempts']} attempt(s)", flush=True)
    destination = output / "demos.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(recordings, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    print(f"Saved {len(recordings)} real recordings.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # API exceptions may contain private request details; keep the message generic.
        print(f"Recording failed ({type(exc).__name__}). No catalog was replaced.", file=sys.stderr)
        sys.exit(1)
