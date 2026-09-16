"""Shared paths and opt-in settings."""
import shutil
from pathlib import Path
import pytest


def pytest_ignore_collect(collection_path, config):
    """Exclude old deliberately failing demos unless explicitly requested."""
    if collection_path.name not in ("test_sample.py", "test_phase2_demo.py"):
        return None
    explicit = any(Path(arg.split("::", 1)[0]).resolve() == collection_path
                   for arg in config.args)
    return not explicit


def pytest_addoption(parser):
    parser.addoption("--run-slow", action="store_true", default=False,
                     help="Run slow tests, including paid Anthropic API calls.")


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--run-slow"):
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="Opt in with --run-slow (uses API credits)."))


@pytest.fixture
def project_root():
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_root(project_root):
    return project_root / "test_fixtures"


@pytest.fixture
def pollution_copy(tmp_path, fixture_root):
    """Repairs and backups belong in a temporary directory."""
    path = tmp_path / "test_pollution.py"
    shutil.copyfile(fixture_root / "order_dependency" / "test_pollution.py", path)
    return path
