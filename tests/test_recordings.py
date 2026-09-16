"""Check that portfolio recording never patches the curated source in place."""
import json
from pathlib import Path

import pytest

from demos import record


@pytest.fixture
def recorder(monkeypatch, tmp_path):
    """Use a temporary catalog and replace repair execution, with no API calls."""
    source = tmp_path / "test_example.py"
    source.write_text("def test_example():\n    assert True\n")
    manifest = {"id": "example", "original_source": source.read_text()}
    monkeypatch.setattr(record, "ROOT", tmp_path)
    monkeypatch.setattr(record, "load_demos", lambda root: {
        "example": {"manifest": manifest, "source": source, "test_name": "test_example"}
    })
    monkeypatch.setattr(record, "public_result", lambda report, secret, directory: report)
    monkeypatch.setattr("sys.argv", ["record.py"])
    return source, tmp_path / "frontend/public/recordings/demos.json"


def test_recording_uses_temporary_copy(monkeypatch, recorder):
    source, destination = recorder
    original = source.read_text()
    paths = []

    def repair(target, runs, retries, on_result):
        copy = Path(target.split("::")[0])
        assert copy != source
        copy.write_text("# repaired\n")
        paths.append(copy)
        on_result({"success": True, "attempts": 1})

    monkeypatch.setattr(record, "repair_test", repair)
    record.main()
    assert source.read_text() == original
    assert not paths[0].exists()
    saved = json.loads(destination.read_text())
    assert saved[0]["result"]["success"] is True
    assert saved[0]["recorded_at"]


def test_failed_capture_keeps_existing_catalog(monkeypatch, recorder):
    source, destination = recorder
    original = source.read_text()
    destination.parent.mkdir(parents=True)
    destination.write_text("existing recording")

    def repair(target, runs, retries, on_result):
        Path(target.split("::")[0]).write_text("# unsuccessful patch\n")
        on_result({"success": False, "attempts": 3})

    monkeypatch.setattr(record, "repair_test", repair)
    with pytest.raises(RuntimeError, match="did not verify"):
        record.main()
    assert destination.read_text() == "existing recording"
    assert source.read_text() == original
