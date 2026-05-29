# Fine-Tuning OS — Lot 1 (Socle) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Construire le socle technique du serveur MCP Fine-Tuning OS (enveloppe de réponse, persistance projet, assainissement Zero-Data, hachage/rendu, chiffrement AES-256-GCM, gating de cibles C2, bootstrap FastMCP) — testé et installable, avant tout outil métier.

**Architecture:** Paquet Python `src/fine_tuning_os/` suivant le pattern de `crypto-mining-mcp` (FastMCP, `pydantic`, hatchling, transport stdio). Le socle expose des modules purs (C1/C3) sans dépendance ML lourde ; un seul outil MCP `ftos_health` est enregistré dans ce lot. Les 64 outils métier et `models.py` arrivent aux lots 2-9.

**Tech Stack:** Python ≥3.10, `mcp` (FastMCP), `pydantic` v2, `cryptography` (AES-256-GCM), `markdown`, `weasyprint` (PDF, extra optionnel), `pytest` + `pytest-cov`, `black`, `ruff`.

**Spec de référence:** `docs/superpowers/specs/2026-05-29-fine-tuning-os-design.md` (§4 arborescence, §5 persistance, §8 sécurité, §9 dépendances, §10 tests). Ce plan couvre **uniquement le lot 1** (§12.1).

**Périmètre du lot 1 — fichiers du socle:**

- Créer `pyproject.toml` — métadonnées, deps, scripts, config pytest/black/ruff.
- Créer `README.md` — minimal (requis par `pyproject`), enrichi au lot 7.
- Créer `src/fine_tuning_os/__init__.py` — `__version__`.
- Créer `src/fine_tuning_os/envelope.py` — `Result` + helpers `ok`/`fail`.
- Créer `src/fine_tuning_os/sanitize.py` — filtres Zero-Data (regex).
- Créer `src/fine_tuning_os/targets.py` — `resolve_target`/`gate` (gating C2 via env).
- Créer `src/fine_tuning_os/store.py` — workspace, état JSON projet, journal d'événements.
- Créer `src/fine_tuning_os/render.py` — SHA256, écriture atomique, Markdown→HTML/PDF.
- Créer `src/fine_tuning_os/crypto.py` — AES-256-GCM (chiffrer/déchiffrer fichier).
- Créer `src/fine_tuning_os/server.py` — bootstrap FastMCP + outil `ftos_health` + `main()`.
- Créer `tests/conftest.py` + un fichier de test par module du socle.

**Hors périmètre (lots ultérieurs):** `models.py` (introduit au lot 2 quand un DTO partagé a un consommateur), les 10 modules `tools/`, les templates Jinja2, `test_zero_data.py` (lot 7), le skill compagnon (lot 8), le bundle démo (lot 9).

---

## Task 0: Scaffolding du projet

**Files:**
- Create: `pyproject.toml`
- Create: `README.md`
- Create: `src/fine_tuning_os/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Créer `pyproject.toml`**

```toml
[project]
name = "fine-tuning-os"
version = "0.1.0"
description = "Zero-Data fine-tuning operations MCP server: 64 tools across the full LLM fine-tuning delivery lifecycle"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "mcp>=1.2.0",
    "pydantic>=2.6.0",
    "httpx>=0.27.0",
    "jinja2>=3.1.0",
    "pyyaml>=6.0",
    "paramiko>=3.0.0",
    "markdown>=3.6",
    "cryptography>=42.0.0",
]

[project.optional-dependencies]
pdf = ["weasyprint>=62"]
dev = ["pytest>=8.0", "pytest-cov>=5.0", "black>=24.0", "ruff>=0.4"]

[project.scripts]
fine-tuning-os = "fine_tuning_os.server:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/fine_tuning_os"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]

[tool.coverage.run]
source = ["src/fine_tuning_os"]

[tool.ruff]
line-length = 100

[tool.black]
line-length = 100
```

> Note Windows : `weasyprint` (PDF) exige des dépendances natives (GTK) souvent pénibles sur Windows. Il est volontairement isolé dans l'extra `pdf` pour que `pip install -e .[dev]` reste vert sans lui. Le rendu PDF (Task 5) est testé en `skip` si `weasyprint` est absent.

- [ ] **Step 2: Créer `README.md` (minimal, enrichi au lot 7)**

```markdown
# Fine-Tuning OS

Serveur MCP « Zero-Data » d'opérations de fine-tuning LLM (64 outils, cycle de vie complet).
Voir `docs/superpowers/specs/2026-05-29-fine-tuning-os-design.md`.

## Installation (dev)

    python -m venv .venv
    .venv\Scripts\activate
    pip install -e .[dev]

## Tests

    pytest --cov=src --cov-report=term-missing
```

- [ ] **Step 3: Créer les paquets**

```python
# src/fine_tuning_os/__init__.py
"""Fine-Tuning OS — Zero-Data fine-tuning operations MCP server."""

__version__ = "0.1.0"
```

```python
# tests/__init__.py
```

(Le fichier `tests/__init__.py` est vide.)

- [ ] **Step 4: Installer et vérifier l'import**

Run:
```bash
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -e .[dev]
.venv\Scripts\python -c "import fine_tuning_os; print(fine_tuning_os.__version__)"
```
Expected: dernière ligne affiche `0.1.0`.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml README.md src/fine_tuning_os/__init__.py tests/__init__.py
git commit -m "chore: scaffold fine-tuning-os package (pyproject, deps, version)"
```

---

## Task 1: `envelope.py` — Result + helpers

**Files:**
- Create: `src/fine_tuning_os/envelope.py`
- Test: `tests/test_envelope.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_envelope.py
import dataclasses

import pytest

from fine_tuning_os.envelope import Result, fail, ok


def test_ok_builds_success_result():
    r = ok({"x": 1}, executed=True)
    assert r.success is True
    assert r.data == {"x": 1}
    assert r.error is None
    assert r.meta == {"executed": True}


def test_fail_builds_error_result():
    r = fail("boom", dry_run=True)
    assert r.success is False
    assert r.data is None
    assert r.error == "boom"
    assert r.meta == {"dry_run": True}


def test_to_dict_roundtrips_all_fields():
    r = ok({"a": 2}, command="docker build .")
    assert r.to_dict() == {
        "success": True,
        "data": {"a": 2},
        "error": None,
        "meta": {"command": "docker build ."},
    }


def test_result_is_frozen():
    r = ok()
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.success = False  # type: ignore[misc]
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_envelope.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.envelope'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/envelope.py
"""Response envelope shared by every Fine-Tuning OS tool."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Result:
    """Uniform tool response. C2 tools surface gating via meta keys
    (executed / dry_run / command)."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ok(data: dict[str, Any] | None = None, **meta: Any) -> Result:
    return Result(success=True, data=data, meta=dict(meta))


def fail(error: str, **meta: Any) -> Result:
    return Result(success=False, error=error, meta=dict(meta))
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_envelope.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/envelope.py tests/test_envelope.py
git commit -m "feat: add Result response envelope with ok/fail helpers"
```

---

## Task 2: `sanitize.py` — filtres Zero-Data

**Files:**
- Create: `src/fine_tuning_os/sanitize.py`
- Test: `tests/test_sanitize.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_sanitize.py
from fine_tuning_os.sanitize import sanitize_text


def test_masks_email():
    out, n = sanitize_text("contact jean.dupont@acme.fr now")
    assert "jean.dupont@acme.fr" not in out
    assert "[REDACTED:EMAIL]" in out
    assert n == 1


def test_masks_ipv4():
    out, n = sanitize_text("host 192.168.1.42 down")
    assert "192.168.1.42" not in out
    assert "[REDACTED:IP]" in out
    assert n == 1


def test_masks_url_with_credentials():
    out, n = sanitize_text("clone https://user:secret@git.acme.fr/repo.git")
    assert "secret" not in out
    assert "[REDACTED:URL_CRED]" in out
    assert n == 1


def test_masks_long_base64_blob():
    blob = "QUJD" * 20  # 80 base64 chars
    out, n = sanitize_text(f"weights={blob}")
    assert blob not in out
    assert "[REDACTED:BLOB]" in out
    assert n == 1


def test_clean_text_is_unchanged_and_counts_zero():
    text = "loss=0.42 step=10 vram=11GB"
    out, n = sanitize_text(text)
    assert out == text
    assert n == 0


def test_counts_multiple_masks():
    out, n = sanitize_text("a@b.cd and e@f.gh")
    assert n == 2
    assert out.count("[REDACTED:EMAIL]") == 2
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_sanitize.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.sanitize'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/sanitize.py
"""Zero-Data text/log sanitization filters.

Every external string (remote logs, debug samples) MUST pass through
sanitize_text before being returned to Claude. Order matters: credential
URLs are masked whole before their host/email parts can match.
"""

from __future__ import annotations

import re

_URL_CRED_RE = re.compile(r"\b\w+://[^\s:/@]+:[^\s:/@]+@\S+")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_BASE64_RE = re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}\b")

_MASKS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_URL_CRED_RE, "[REDACTED:URL_CRED]"),
    (_EMAIL_RE, "[REDACTED:EMAIL]"),
    (_IPV4_RE, "[REDACTED:IP]"),
    (_BASE64_RE, "[REDACTED:BLOB]"),
)


def sanitize_text(text: str) -> tuple[str, int]:
    """Return (masked_text, number_of_substitutions)."""
    out = text
    count = 0
    for pattern, mask in _MASKS:
        out, n = pattern.subn(mask, out)
        count += n
    return out, count
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_sanitize.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/sanitize.py tests/test_sanitize.py
git commit -m "feat: add Zero-Data text sanitizer (email/ip/url-cred/blob masking)"
```

---

## Task 3: `targets.py` — gating C2 via variables d'environnement

**Files:**
- Create: `src/fine_tuning_os/targets.py`
- Test: `tests/test_targets.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_targets.py
import pytest

from fine_tuning_os.targets import gate, resolve_target


def test_resolve_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
    assert resolve_target("slack") is None


def test_resolve_returns_config_when_set(monkeypatch):
    monkeypatch.setenv("FTOS_SLACK_WEBHOOK", "https://hooks.example/abc")
    assert resolve_target("slack") == {"FTOS_SLACK_WEBHOOK": "https://hooks.example/abc"}


def test_resolve_requires_all_vars(monkeypatch):
    monkeypatch.setenv("FTOS_SSH_HOST", "bastion.acme.fr")
    monkeypatch.delenv("FTOS_SSH_KEY", raising=False)
    assert resolve_target("ssh") is None


def test_resolve_empty_string_counts_as_missing(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    assert resolve_target("hf") is None


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        resolve_target("nope")


def test_gate_dry_run_when_unconfigured(monkeypatch):
    monkeypatch.delenv("FTOS_REGISTRY", raising=False)
    monkeypatch.delenv("FTOS_REGISTRY_TOKEN", raising=False)
    configured, meta = gate("registry")
    assert configured is False
    assert meta == {"executed": False, "dry_run": True}


def test_gate_live_when_configured(monkeypatch):
    monkeypatch.setenv("FTOS_REGISTRY", "reg.acme.fr")
    monkeypatch.setenv("FTOS_REGISTRY_TOKEN", "tok")
    configured, meta = gate("registry")
    assert configured is True
    assert meta == {"executed": True, "dry_run": False}
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_targets.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.targets'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/targets.py
"""C2 external-target gating from environment variables.

A C2 tool executes live only when its target is fully configured via env
vars; otherwise it returns dry_run + the exact command. Secrets are never
written to disk or logs — only their presence is ever surfaced.
"""

from __future__ import annotations

import os
from typing import Any

# kind -> env var names that must ALL be present (non-empty) to go live.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "ssh": ("FTOS_SSH_HOST", "FTOS_SSH_KEY"),
    "registry": ("FTOS_REGISTRY", "FTOS_REGISTRY_TOKEN"),
    "sftp": ("FTOS_SFTP_HOST", "FTOS_SFTP_USER", "FTOS_SFTP_KEY"),
    "smtp": ("FTOS_SMTP_HOST", "FTOS_SMTP_USER", "FTOS_SMTP_PASSWORD"),
    "slack": ("FTOS_SLACK_WEBHOOK",),
    "calendly": ("FTOS_CALENDLY_TOKEN",),
    "hf": ("HF_TOKEN",),
    "git_remote": ("FTOS_GIT_REMOTE",),
    "local_python": ("FTOS_LOCAL_PYTHON",),
}


def resolve_target(kind: str) -> dict[str, str] | None:
    """Return the env config for `kind`, or None if not fully configured."""
    names = _REQUIRED.get(kind)
    if names is None:
        raise ValueError(f"unknown target kind: {kind}")
    values: dict[str, str] = {}
    for name in names:
        val = os.environ.get(name)
        if not val:
            return None
        values[name] = val
    return values


def gate(kind: str) -> tuple[bool, dict[str, Any]]:
    """Return (configured, meta) where meta carries executed/dry_run flags."""
    if resolve_target(kind) is None:
        return False, {"executed": False, "dry_run": True}
    return True, {"executed": True, "dry_run": False}
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_targets.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/targets.py tests/test_targets.py
git commit -m "feat: add C2 target gating (resolve_target/gate) from env vars"
```

---

## Task 4: `store.py` — persistance projet (écritures immuables)

**Files:**
- Create: `src/fine_tuning_os/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
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
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_store.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.store'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
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
        return self.root / project_id

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
        tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)

    def update_project(self, project_id: str, **changes: Any) -> dict[str, Any]:
        state = self.read_project(project_id)
        new_state = {**state, **changes}
        self.write_project(project_id, new_state)
        return new_state

    def append_event(
        self, project_id: str, event_type: str, payload: dict[str, Any]
    ) -> str:
        event_id = uuid.uuid4().hex
        record = {"id": event_id, "ts": _now(), "type": event_type, "payload": payload}
        path = self.project_dir(project_id) / "events.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        return event_id
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_store.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/store.py tests/test_store.py
git commit -m "feat: add project Store (workspace, atomic JSON state, event log)"
```

---

## Task 5: `render.py` — hachage, écriture atomique, Markdown→HTML/PDF

**Files:**
- Create: `src/fine_tuning_os/render.py`
- Test: `tests/test_render.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_render.py
import importlib.util
from pathlib import Path

import pytest

from fine_tuning_os.render import (
    markdown_file_to_pdf,
    markdown_to_html,
    sha256_bytes,
    sha256_file,
    write_text_atomic,
)

_HAS_WEASYPRINT = importlib.util.find_spec("weasyprint") is not None


def test_sha256_bytes_known_vector():
    assert sha256_bytes(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )


def test_sha256_file_matches_bytes(tmp_path):
    p = tmp_path / "f.txt"
    p.write_bytes(b"hello")
    assert sha256_file(p) == sha256_bytes(b"hello")


def test_write_text_atomic_creates_parents_and_no_tmp(tmp_path):
    target = tmp_path / "a" / "b" / "note.md"
    write_text_atomic(target, "content")
    assert target.read_text(encoding="utf-8") == "content"
    assert list((tmp_path / "a" / "b").glob("*.tmp")) == []


def test_markdown_to_html_renders_table_and_heading():
    html = markdown_to_html("# Title\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "<h1>" in html
    assert "<table>" in html


@pytest.mark.skipif(not _HAS_WEASYPRINT, reason="weasyprint extra not installed")
def test_markdown_file_to_pdf_writes_pdf(tmp_path):
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n\nbody\n", encoding="utf-8")
    pdf = tmp_path / "out" / "doc.pdf"
    markdown_file_to_pdf(md, pdf)
    assert pdf.is_file()
    assert pdf.read_bytes().startswith(b"%PDF")
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_render.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.render'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/render.py
"""Deterministic file utilities: hashing, atomic writes, Markdown rendering."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import markdown as _markdown


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def write_text_atomic(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def markdown_to_html(md_text: str) -> str:
    return _markdown.markdown(md_text, extensions=["tables", "fenced_code"])


def markdown_file_to_pdf(md_path: Path, pdf_path: Path) -> Path:
    """Render a Markdown file to PDF via WeasyPrint.

    Requires the optional `pdf` extra (`pip install -e .[pdf]`). Imported
    lazily so the core install stays light on Windows.
    """
    from weasyprint import HTML  # noqa: PLC0415 (lazy heavy native dep)

    html = markdown_to_html(Path(md_path).read_text(encoding="utf-8"))
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html).write_pdf(str(pdf_path))
    return pdf_path
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_render.py -v`
Expected: PASS (4 tests passent ; le test PDF est `PASSED` si l'extra `pdf` est installé, sinon `SKIPPED`).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/render.py tests/test_render.py
git commit -m "feat: add render utils (sha256, atomic write, markdown to html/pdf)"
```

---

## Task 6: `crypto.py` — AES-256-GCM

**Files:**
- Create: `src/fine_tuning_os/crypto.py`
- Test: `tests/test_crypto.py`

- [ ] **Step 1: Écrire le test qui échoue**

```python
# tests/test_crypto.py
import pytest
from cryptography.exceptions import InvalidTag

from fine_tuning_os.crypto import decrypt_file, encrypt_file, generate_key


def test_generate_key_is_32_bytes():
    assert len(generate_key()) == 32


def test_encrypt_decrypt_roundtrip(tmp_path):
    src = tmp_path / "model.bin"
    src.write_bytes(b"secret weights \x00\x01\x02")
    key = generate_key()
    enc = encrypt_file(src, tmp_path / "model.enc", key)
    assert enc.read_bytes() != src.read_bytes()
    out = decrypt_file(enc, tmp_path / "model.dec", key)
    assert out.read_bytes() == b"secret weights \x00\x01\x02"


def test_wrong_key_fails(tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(b"data")
    enc = encrypt_file(src, tmp_path / "f.enc", generate_key())
    with pytest.raises(InvalidTag):
        decrypt_file(enc, tmp_path / "f.dec", generate_key())


def test_bad_key_length_rejected(tmp_path):
    src = tmp_path / "f.bin"
    src.write_bytes(b"data")
    with pytest.raises(ValueError):
        encrypt_file(src, tmp_path / "f.enc", b"tooshort")
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_crypto.py -v`
Expected: FAIL avec `ModuleNotFoundError: No module named 'fine_tuning_os.crypto'`.

- [ ] **Step 3: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/crypto.py
"""AES-256-GCM encryption for deliverables.

Output layout: nonce (12 bytes) || ciphertext+tag. The key is generated
fresh per deliverable and surfaced to the operator exactly once; it is never
persisted to disk by this module.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32


def generate_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


def encrypt_file(src: Path, dst: Path, key: bytes) -> Path:
    if len(key) != _KEY_BYTES:
        raise ValueError("key must be 32 bytes for AES-256-GCM")
    plaintext = Path(src).read_bytes()
    nonce = os.urandom(_NONCE_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(nonce + ciphertext)
    return dst


def decrypt_file(src: Path, dst: Path, key: bytes) -> Path:
    blob = Path(src).read_bytes()
    nonce, ciphertext = blob[:_NONCE_BYTES], blob[_NONCE_BYTES:]
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_bytes(plaintext)
    return dst
```

- [ ] **Step 4: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_crypto.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/fine_tuning_os/crypto.py tests/test_crypto.py
git commit -m "feat: add AES-256-GCM encrypt/decrypt for deliverables"
```

---

## Task 7: `server.py` — bootstrap FastMCP + `ftos_health` + conftest

**Files:**
- Create: `src/fine_tuning_os/server.py`
- Create: `tests/conftest.py`
- Test: `tests/test_server.py`

- [ ] **Step 1: Écrire `tests/conftest.py` (fixtures partagées)**

```python
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
```

- [ ] **Step 2: Écrire le test qui échoue**

```python
# tests/test_server.py
from fine_tuning_os import server


def test_health_reports_name_and_version(monkeypatch, tmp_path):
    monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path / "ws"))
    out = server.ftos_health()
    assert out["success"] is True
    assert out["data"]["name"] == "fine-tuning-os"
    assert out["data"]["version"] == server.__version__
    assert out["data"]["workspace"].endswith("ws")


def test_health_targets_are_booleans_no_secrets(monkeypatch):
    monkeypatch.delenv("FTOS_SLACK_WEBHOOK", raising=False)
    monkeypatch.setenv("HF_TOKEN", "hf_secret_value")
    out = server.ftos_health()
    targets = out["data"]["targets_configured"]
    assert targets["slack"] is False
    assert targets["hf"] is True
    # the secret value must never appear anywhere in the response
    assert "hf_secret_value" not in repr(out)


def test_mcp_instance_named():
    assert server.mcp.name == "fine-tuning-os"
```

- [ ] **Step 3: Lancer le test pour vérifier l'échec**

Run: `.venv\Scripts\pytest tests/test_server.py -v`
Expected: FAIL avec `AttributeError: module 'fine_tuning_os.server' has no attribute 'ftos_health'` (ou ImportError).

- [ ] **Step 4: Écrire l'implémentation minimale**

```python
# src/fine_tuning_os/server.py
"""Fine-Tuning OS — MCP server bootstrap.

Zero-Data fine-tuning operations toolkit. Lot 1 registers only the socle
health tool; the 64 domain tools are added across lots 2-9. Transport: stdio.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import __version__
from .envelope import ok
from .store import workspace_root
from .targets import resolve_target

mcp = FastMCP("fine-tuning-os")

_TARGET_KINDS: tuple[str, ...] = (
    "ssh",
    "registry",
    "sftp",
    "smtp",
    "slack",
    "calendly",
    "hf",
    "git_remote",
    "local_python",
)


@mcp.tool(
    description=(
        "Report Fine-Tuning OS server health: version, workspace path, and "
        "which external targets are configured (booleans only — never secrets)."
    )
)
def ftos_health() -> dict:
    targets = {kind: resolve_target(kind) is not None for kind in _TARGET_KINDS}
    return ok(
        {
            "name": "fine-tuning-os",
            "version": __version__,
            "workspace": str(workspace_root()),
            "targets_configured": targets,
        }
    ).to_dict()


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Lancer le test pour vérifier le succès**

Run: `.venv\Scripts\pytest tests/test_server.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Vérifier le démarrage stdio sans aucune variable d'env (critère d'acceptation §11.3)**

Run:
```bash
.venv\Scripts\python -c "from fine_tuning_os import server; print(server.ftos_health()['data']['targets_configured'])"
```
Expected: un dict de 9 clés toutes à `False` (aucun env configuré → tous les C2 basculeraient en dry_run).

- [ ] **Step 7: Commit**

```bash
git add src/fine_tuning_os/server.py tests/conftest.py tests/test_server.py
git commit -m "feat: add FastMCP bootstrap with ftos_health tool (stdio)"
```

---

## Task 8: Portail qualité du socle (couverture, format, lint)

**Files:** aucun fichier source nouveau ; vérification + corrections éventuelles.

- [ ] **Step 1: Couverture ≥80% sur le socle**

Run: `.venv\Scripts\pytest --cov=src --cov-report=term-missing`
Expected: tous les tests PASS ; ligne `TOTAL` ≥ 80%. Si un module est sous le seuil, ajouter le test du chemin manquant (chaque branche d'erreur ci-dessus est déjà testée → attendu ≥ 95%).

- [ ] **Step 2: Format black**

Run: `.venv\Scripts\black --check src tests`
Expected: `All done!`. Si échec : `.venv\Scripts\black src tests` puis re-vérifier.

- [ ] **Step 3: Lint ruff**

Run: `.venv\Scripts\ruff check src tests`
Expected: `All checks passed!`. Corriger tout finding (imports inutilisés, etc.) puis re-lancer.

- [ ] **Step 4: Vérification d'enregistrement de l'outil MCP**

Run:
```bash
.venv\Scripts\python -c "import asyncio; from fine_tuning_os.server import mcp; print(sorted(t.name for t in asyncio.run(mcp.list_tools())))"
```
Expected: `['ftos_health']`.

- [ ] **Step 5: Commit final du lot (si des corrections format/lint ont été faites)**

```bash
git add -A
git commit -m "chore: socle quality gate (coverage >=80%, black, ruff clean)"
```

---

## Self-Review (effectuée à l'écriture)

**1. Couverture spec (lot 1 = §12.1 socle):** `envelope`✓ `sanitize`✓ `render`✓ `crypto`✓ `targets`✓ `store`✓ `server`✓ `conftest`✓ `pyproject`✓. `models.py` explicitement reporté au lot 2 (aucun consommateur en lot 1 — YAGNI, documenté en tête de plan). `test_zero_data.py` reporté au lot 7 (frontière de lot respectée, spec §12.7). Critère d'acceptation §11.3 (démarrage sans env → C2 en dry_run) vérifié en Task 7 Step 6. Critère §11.5 (black/ruff/annotations) vérifié en Task 8.

**2. Scan placeholders:** aucun « TBD/TODO/à compléter ». Chaque step de code montre le code complet ; chaque commande montre la sortie attendue.

**3. Cohérence des types/signatures:** `Result.to_dict()` utilisé par `server.ftos_health` (Task 7) défini en Task 1. `ok()` importé par `server` depuis `envelope` (Task 1). `resolve_target`/`gate` (Task 3) consommés par `server` (Task 7). `Store(root=...)`/`workspace_root()` (Task 4) utilisés par `conftest` + `server` (Task 7). `sha256_file`/`write_text_atomic` (Task 5) prêts pour les lots packaging/docs. Noms identiques d'un task à l'autre — aucune divergence.

**4. Risque plateforme:** `weasyprint` isolé en extra `pdf` ; test PDF en `skipif` → le socle reste vert sur Windows sans GTK. Chemins de venv en `.venv\Scripts\` (Windows). À adapter en `.venv/bin/` sur Unix.
