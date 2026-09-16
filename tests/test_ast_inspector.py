"""Check shared-state detection on the example files."""
from analysis.ast_inspector import ASTInspector


def test_pollution_shared_state(fixture_root):
    path = fixture_root / "order_dependency" / "test_pollution.py"
    assert set(ASTInspector(path).detect_shared_state()) == {"SHARED_STATE"}


def test_clean_has_no_shared_state(fixture_root):
    path = fixture_root / "stable" / "test_clean.py"
    assert ASTInspector(path).detect_shared_state() == []


def test_globals_found_and_locals_ignored(tmp_path):
    path = tmp_path / "test_globals.py"
    path.write_text("GLOBAL_DICT = {}\nGLOBAL_INT = 42\n"
                    "def test_example():\n"
                    "    global INJECTED_GLOBAL\n"
                    "    INJECTED_GLOBAL = True\n"
                    "    local_var = 1\n", encoding="utf-8")
    assert set(ASTInspector(path).detect_shared_state()) == {
        "GLOBAL_DICT", "GLOBAL_INT", "INJECTED_GLOBAL"
    }
