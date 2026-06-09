# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/store.py
"""Project workspace + JSON state persistence.

State is written atomically (tmp file + os.replace). Updates are immutable:
read -> build a new dict -> write; the caller's dict is never mutated.
Secrets are never persisted here (cf. spec §5/§8).
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SUBDIRS: tuple[str, ...] = (
    "config",
    "data/synthetic",
    "src",
    "docker",
    "outputs",
    "reports",
    "deliverables",
    "docs",
)


def workspace_root() -> Path:
    return Path(os.environ.get("FTOS_WORKSPACE", "./ftos-workspace")).resolve()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else workspace_root()

    def project_dir(self, project_id: str) -> Path:
        root = self.root.resolve()
        pdir = (root / project_id).resolve()
        if not pdir.is_relative_to(root):
            raise ValueError(f"project_id escapes workspace: {project_id!r}")
        return pdir

    def init_project(self, project_id: str, client: str) -> dict[str, Any]:
        pdir = self.project_dir(project_id)
        for sub in _SUBDIRS:
            (pdir / sub).mkdir(parents=True, exist_ok=True)
        state: dict[str, Any] = {
            "project_id": project_id,
            "client": client,
            "status": "onboarded",
            "created_at": _now(),
            "schema": None,
            "checkpoints": [],
            "milestones": [],
        }
        self.write_project(project_id, state)
        (pdir / "events.jsonl").touch(exist_ok=True)
        return state

    def read_project(self, project_id: str) -> dict[str, Any]:
        path = self.project_dir(project_id) / "project.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def write_project(self, project_id: str, state: dict[str, Any]) -> None:
        pdir = self.project_dir(project_id)
        pdir.mkdir(parents=True, exist_ok=True)
        path = pdir / "project.json"
        tmp = path.with_name("project.json.tmp")
        try:
            tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any]:
        state = self.read_project(project_id)
        new_state = {**state, **changes}
        self.write_project(project_id, new_state)
        return new_state

    def append_event(self, project_id: str, event_type: str, payload: dict[str, Any]) -> str:
        event_id = uuid.uuid4().hex
        record = {"id": event_id, "ts": _now(), "type": event_type, "payload": payload}
        path = self.project_dir(project_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return event_id
