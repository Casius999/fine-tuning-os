# tests/conftest.py
from pathlib import Path

import pytest

from fine_tuning_os.store import Store


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


@pytest.fixture()
def store(workspace: Path) -> Store:
    return Store(root=workspace)


@pytest.fixture()
def project_id(store: Store) -> str:
    store.init_project("demo", "ACME")
    return "demo"
