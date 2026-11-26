from pathlib import Path
import shutil

import pytest


@pytest.fixture(scope="session")
def legacy_workspace(tmp_path_factory):
    """Give legacy integration tests a writable copy of their checked-in example workspace."""
    source = Path(__file__).resolve().parents[1]
    work = tmp_path_factory.mktemp("financial-evidence-workspace")
    shutil.copytree(
        source,
        work,
        ignore=shutil.ignore_patterns("src", "__pycache__", ".pytest_cache", "upstream"),
        dirs_exist_ok=True,
    )
    (work / "src").symlink_to((source / "src").resolve(), target_is_directory=True)
    return work


@pytest.fixture(autouse=True)
def original_project_directory(monkeypatch, legacy_workspace):
    monkeypatch.chdir(legacy_workspace)
