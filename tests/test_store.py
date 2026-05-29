# tests/test_store.py
import json
from pathlib import Path

from fine_tuning_os.store import Store, workspace_root


def test_workspace_root_uses_env(monkeypatch, tmp_path):
    monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path / "ws"))
    assert workspace_root() == (tmp_path / "ws").resolve()


def test_init_project_creates_dirs_and_state(tmp_path):
    store = Store(root=tmp_path)
    state = store.init_project("p1", "ACME")
    pdir = tmp_path / "p1"
    assert (pdir / "config").is_dir()
    assert (pdir / "data" / "synthetic").is_dir()
    assert (pdir / "deliverables").is_dir()
    assert (pdir / "events.jsonl").is_file()
    assert state["project_id"] == "p1"
    assert state["client"] == "ACME"
    assert state["status"] == "onboarded"


def test_read_project_roundtrips(tmp_path):
    store = Store(root=tmp_path)
    store.init_project("p1", "ACME")
    assert store.read_project("p1")["client"] == "ACME"


def test_update_project_is_immutable(tmp_path):
    store = Store(root=tmp_path)
    original = store.init_project("p1", "ACME")
    updated = store.update_project("p1", status="training")
    assert updated["status"] == "training"
    assert original["status"] == "onboarded"  # original dict not mutated
    assert store.read_project("p1")["status"] == "training"


def test_append_event_writes_line_and_returns_id(tmp_path):
    store = Store(root=tmp_path)
    store.init_project("p1", "ACME")
    eid = store.append_event("p1", "milestone", {"name": "kickoff"})
    assert isinstance(eid, str) and len(eid) == 32
    lines = (tmp_path / "p1" / "events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["id"] == eid
    assert rec["type"] == "milestone"
    assert rec["payload"] == {"name": "kickoff"}
    assert "ts" in rec


def test_write_project_is_atomic_no_tmp_left(tmp_path):
    store = Store(root=tmp_path)
    store.init_project("p1", "ACME")
    leftovers = list((tmp_path / "p1").glob("*.tmp"))
    assert leftovers == []
