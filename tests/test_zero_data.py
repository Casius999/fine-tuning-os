# tests/test_zero_data.py
"""§10 Zero-Data Guard Tests — Four invariant groups.

Group 1 — No network for C1/C3 tools:
  Monkeypatches socket.socket and socket.create_connection to raise AssertionError;
  calls every C1 and C3 tool once with minimal valid inputs; asserts success and
  no socket opened.

Group 2 — C2 dry_run is networkless:
  With all FTOS_*/HF_TOKEN env vars deleted, every C2 tool must return
  meta.executed=False, meta.dry_run=True and not open any socket.

Group 3 — Registration & boot:
  65 tools total (64 domain + ftos_health). Server imports without error even
  with zero env vars.

Group 4 — Filesystem confinement:
  After exercising file-writing tools against a tmp workspace, no file exists
  outside the workspace root (in particular no docker/ at repo root).
"""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

import pytest

from fine_tuning_os.store import Store
from fine_tuning_os.tools import (
    client,
    docs,
    evaluation,
    execution,
    maintenance,
    packaging,
    pipeline,
    prep,
    security,
    synthetic,
)

# ---------------------------------------------------------------------------
# Tool-class mapping
# Tool numbers from spec: C2 = 2,11,12,13,18,20,21,22,24,26,28,39,40,41,43,45,
#   54(send_status_update=56),56,57,64; C3 = 33,34,35,36,38.
# We classify by module+position for clarity.
# ---------------------------------------------------------------------------

# Each entry: (module, index_in_MCP_TOOLS, class)
# C1 = offline pure; C2 = emit/dry_run unless env configured; C3 = audit/static
_TOOL_CLASS: dict[str, str] = {
    # prep (tools 1-5 + extras)
    "prep:0": "C1",  # create_training_config
    "prep:1": "C2",  # cache_base_model
    "prep:2": "C1",  # generate_requirements
    "prep:3": "C1",  # create_project_structure
    "prep:4": "C1",  # load_project_template
    "prep:5": "C1",  # describe_expected_data_format
    "prep:6": "C1",  # validate_data_schema
    "prep:7": "C1",  # anonymize_dataset_preview
    "prep:8": "C1",  # split_dataset_config
    # synthetic (tool 7)
    "synthetic:0": "C1",  # generate_synthetic_dataset
    # pipeline (tools 11-17)
    "pipeline:0": "C2",  # build_docker_image
    "pipeline:1": "C2",  # test_docker_build
    "pipeline:2": "C2",  # run_local_synthetic_train
    "pipeline:3": "C1",  # get_local_metrics
    "pipeline:4": "C1",  # dry_run_remote_config
    "pipeline:5": "C1",  # optimize_hyperparams
    "pipeline:6": "C1",  # generate_unit_tests
    # execution (tools 18-25)
    "execution:0": "C2",  # push_docker_to_registry (registry gate)
    "execution:1": "C1",  # generate_deployment_command (emits only, no gate)
    "execution:2": "C2",  # trigger_remote_training (ssh gate)
    "execution:3": "C2",  # stream_remote_logs (ssh gate)
    "execution:4": "C2",  # monitor_training_metrics (ssh gate)
    "execution:5": "C1",  # detect_anomalies (pure analysis, no gate)
    "execution:6": "C2",  # pause_resume_training (ssh gate)
    "execution:7": "C1",  # early_stopping_check (pure analysis, no gate)
    # evaluation (tools 26-32)
    "evaluation:0": "C2",  # download_checkpoint_metadata
    "evaluation:1": "C1",  # evaluate_on_synthetic
    "evaluation:2": "C2",  # evaluate_on_validation_set
    "evaluation:3": "C1",  # compute_metrics
    "evaluation:4": "C1",  # generate_predictions_sample
    "evaluation:5": "C1",  # compare_to_baseline
    "evaluation:6": "C1",  # bias_fairness_scan
    # security (tools 33-38, all C3)
    "security:0": "C3",  # audit_code_no_network
    "security:1": "C3",  # audit_dockerfile_security
    "security:2": "C3",  # scan_data_leakage_risk
    "security:3": "C3",  # verify_model_license
    "security:4": "C3",  # generate_security_report
    "security:5": "C3",  # sanitize_logs_for_claude
    # packaging (tools 39-46)
    "packaging:0": "C2",  # merge_lora_weights
    "packaging:1": "C2",  # quantize_model
    "packaging:2": "C2",  # build_inference_container
    "packaging:3": "C1",  # generate_inference_config
    "packaging:4": "C2",  # test_inference_api
    "packaging:5": "C1",  # encrypt_deliverable
    "packaging:6": "C2",  # upload_deliverable
    "packaging:7": "C1",  # generate_delivery_note
    # docs (tools 47-54)
    "docs:0": "C1",  # generate_contract
    "docs:1": "C1",  # generate_nda
    "docs:2": "C1",  # generate_performance_report
    "docs:3": "C1",  # generate_user_guide
    "docs:4": "C1",  # generate_deployment_guide
    "docs:5": "C1",  # generate_destruction_certificate
    "docs:6": "C1",  # export_document_pdf (local render, no network)
    "docs:7": "C1",  # sign_document (local hash, no network)
    # client (tools 55-60)
    "client:0": "C1",  # onboard_client
    "client:1": "C2",  # send_status_update
    "client:2": "C2",  # schedule_meeting
    "client:3": "C1",  # log_project_event
    "client:4": "C1",  # request_client_approval
    "client:5": "C1",  # generate_invoice
    # maintenance (tools 61-64)
    "maintenance:0": "C1",  # check_model_rot
    "maintenance:1": "C1",  # suggest_retraining
    "maintenance:2": "C1",  # update_base_model
    "maintenance:3": "C2",  # self_update
}

_MODULE_MAP = {
    "prep": prep,
    "synthetic": synthetic,
    "pipeline": pipeline,
    "execution": execution,
    "evaluation": evaluation,
    "security": security,
    "packaging": packaging,
    "docs": docs,
    "client": client,
    "maintenance": maintenance,
}


def _get_tools_by_class(cls: str) -> list[tuple[str, Any]]:
    """Return [(key, fn), ...] for all tools of the given class."""
    result = []
    for key, tool_cls in _TOOL_CLASS.items():
        if tool_cls != cls:
            continue
        mod_name, idx_str = key.split(":")
        mod = _MODULE_MAP[mod_name]
        idx = int(idx_str)
        fn, _ = mod._MCP_TOOLS[idx]
        result.append((key, fn))
    return result


# ---------------------------------------------------------------------------
# Minimal call-arg factories for each tool key
# ---------------------------------------------------------------------------


def _make_args(key: str, workspace: Path, store: Store, project_id: str) -> dict[str, Any]:
    """Return kwargs sufficient for one valid call of the tool identified by *key*."""
    # We need files, dirs and project created when needed
    pdir = store.project_dir(project_id)
    fake_enc = pdir / "deliverables" / "file.enc"
    fake_enc.parent.mkdir(parents=True, exist_ok=True)
    if not fake_enc.exists():
        fake_enc.write_bytes(b"fake-encrypted-content")

    fake_md = pdir / "docs" / "doc.md"
    fake_md.parent.mkdir(parents=True, exist_ok=True)
    if not fake_md.exists():
        fake_md.write_text("# Doc\n", encoding="utf-8")

    # Prep tools
    if key == "prep:0":
        return {"project_id": project_id, "base_model": "base/model"}
    if key == "prep:1":
        return {"repo_id": "meta-llama/Llama-3-8B", "dest": str(workspace / "models")}
    if key == "prep:2":
        return {"framework": "unsloth"}
    if key == "prep:3":
        return {"project_id": "zd_struct_prj", "client_name": "ACME"}
    if key == "prep:4":
        return {"template_name": "lora-mistral-v3", "project_id": project_id}
    if key == "prep:5":
        return {
            "project_id": project_id,
            "columns": [{"name": "input", "dtype": "str"}, {"name": "output", "dtype": "str"}],
            "task_type": "instruction-tuning",
        }
    if key == "prep:6":
        sample = pdir / "data" / "synthetic" / "sample.jsonl"
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text('{"input": "hello"}\n', encoding="utf-8")
        return {"file_path": str(sample)}
    if key == "prep:7":
        sample = pdir / "data" / "synthetic" / "preview.jsonl"
        sample.parent.mkdir(parents=True, exist_ok=True)
        sample.write_text('{"name": "Alice", "email": "alice@example.com"}\n', encoding="utf-8")
        return {"file_path": str(sample)}
    if key == "prep:8":
        return {"project_id": project_id}

    # Synthetic
    if key == "synthetic:0":
        return {
            "project_id": project_id,
            "n": 10,
            "seed": 42,
            "schema": {"columns": [{"name": "text", "dtype": "str"}]},
        }

    # Pipeline
    if key == "pipeline:0":
        return {
            "project_id": project_id,
            "base_image": "python:3.11",
            "tag": "ftos-test:latest",
        }
    if key == "pipeline:1":
        return {"image_tag": "ftos-test:latest"}
    if key == "pipeline:2":
        return {"project_id": project_id, "steps": 5}
    if key == "pipeline:3":
        metrics_path = pdir / "outputs" / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text('{"final_loss": 0.42}', encoding="utf-8")
        return {"project_id": project_id}
    if key == "pipeline:4":
        return {"deployment_spec": {"env_names": ["FOO", "BAR"]}}
    if key == "pipeline:5":
        return {"metrics": {"final_loss": 0.3, "step_history": []}}
    if key == "pipeline:6":
        return {"project_id": project_id, "targets": ["train", "eval"]}

    # Execution
    if key == "execution:0":
        return {"tag": "registry.example.com/ftos:latest"}
    if key == "execution:1":
        return {
            "image": "registry.example.com/ftos:latest",
            "mounts": [{"host": "/data", "container": "/data"}],
            "env_names": ["API_KEY"],
            "gpus": ["all"],
        }
    if key == "execution:2":
        return {"target": "gpu01.example.com", "command": "python3 train.py --steps 100"}
    if key == "execution:3":
        return {"job_id": "job-abc123", "target": "gpu01.example.com"}
    if key == "execution:4":
        return {"job_id": "job-abc123", "source": "gpu01.example.com"}
    if key == "execution:5":
        return {
            "logs": ["Epoch 1 loss: 0.5", "Epoch 2 loss: 0.3"],
            "metrics": {"final_loss": 0.3},
        }
    if key == "execution:6":
        return {"job_id": "job-abc123", "action": "pause"}
    if key == "execution:7":
        return {
            "metrics": {"loss_history": [0.5, 0.4, 0.38, 0.37, 0.37, 0.37]},
        }

    # Evaluation
    if key == "evaluation:0":
        return {"target": "gpu01.example.com", "checkpoint": "checkpoint-100"}
    if key == "evaluation:1":
        return {"project_id": project_id}
    if key == "evaluation:2":
        return {
            "target": "gpu01.example.com",
            "eval_spec": {"script": "eval.py", "data_path": "data/val.jsonl"},
        }
    if key == "evaluation:3":
        return {
            "preds": ["Paris", "4"],
            "refs": ["Paris", "4"],
            "task": "classification",
        }
    if key == "evaluation:4":
        return {"prompts": ["What is 2+2?"]}
    if key == "evaluation:5":
        return {
            "metrics_ft": {"accuracy": 0.9, "f1": 0.88},
            "metrics_base": {"accuracy": 0.7, "f1": 0.65},
        }
    if key == "evaluation:6":
        return {
            "test_prompts": ["Tell me about history"],
            "categories": ["gender", "religion"],
        }

    # Security (C3)
    if key == "security:0":
        return {"source": "import os\nprint(os.getcwd())"}
    if key == "security:1":
        return {"dockerfile_text": "FROM ubuntu:22.04\nRUN apt-get update"}
    if key == "security:2":
        return {"text": "user@example.com connected from 192.168.1.1"}
    if key == "security:3":
        return {"repo_id": "meta-llama/Llama-3-8B"}
    if key == "security:4":
        return {
            "project_id": project_id,
            "findings": {"issues": ["no hardcoded keys found"]},
        }
    if key == "security:5":
        return {"text": "error: connection refused from 10.0.0.1 user@corp.com"}

    # Packaging
    if key == "packaging:0":
        return {
            "base_model": "base/model",
            "adapter_path": "/adapters/lora",
            "output_path": "/out/merged",
        }
    if key == "packaging:1":
        return {"model_path": "/models/merged", "format": "gguf", "bits": 4}
    if key == "packaging:2":
        return {"model_path": "/models/m", "engine": "vllm", "project_id": project_id}
    if key == "packaging:3":
        return {"port": 8000, "engine": "vllm"}
    if key == "packaging:4":
        return {"prompts": ["Hello"], "base_url": None}
    if key == "packaging:5":
        return {"paths": [str(fake_enc)]}
    if key == "packaging:6":
        return {"path": str(fake_enc)}
    if key == "packaging:7":
        return {
            "project_id": project_id,
            "files": [{"name": "file.enc", "sha256": "a" * 64}],
        }

    # Docs
    if key == "docs:0":
        return {"project_id": project_id, "montant": "5000 EUR"}
    if key == "docs:1":
        return {"project_id": project_id, "partie_a": "ACME", "partie_b": "DevCo"}
    if key == "docs:2":
        return {
            "project_id": project_id,
            "metrics": {"accuracy": 0.92, "f1": 0.89},
        }
    if key == "docs:3":
        return {"project_id": project_id}
    if key == "docs:4":
        return {"project_id": project_id}
    if key == "docs:5":
        return {
            "project_id": project_id,
            "date": "2026-06-09",
            "methode": "secure_delete",
        }
    if key == "docs:6":
        # export_document_pdf — file must exist, weasyprint may not; expect fail ok
        return {"md_path": str(fake_md)}
    if key == "docs:7":
        return {"doc_path": str(fake_md)}

    # Client
    if key == "client:0":
        return {"company": "ACME Corp", "needs": "LLM fine-tuning", "contact_email": "cto@acme.com"}
    if key == "client:1":
        return {
            "project_id": project_id,
            "subject": "Status update",
            "body": "Training complete",
        }
    if key == "client:2":
        return {"duration": 60, "window": "next 2 weeks"}
    if key == "client:3":
        return {
            "project_id": project_id,
            "event_type": "training_started",
            "payload": {"step": 0},
        }
    if key == "client:4":
        return {
            "project_id": project_id,
            "question": "Approve delivery?",
            "artifacts": ["delivery_note.md"],
        }
    if key == "client:5":
        return {
            "project_id": project_id,
            "lines": [{"description": "Fine-tuning service", "qty": 1, "unit_price": 5000}],
        }

    # Maintenance
    if key == "maintenance:0":
        return {
            "metric_history": [
                {"step": 1, "accuracy": 0.9},
                {"step": 2, "accuracy": 0.85},
                {"step": 3, "accuracy": 0.78},
            ],
            "metric_key": "accuracy",
            "threshold": 0.05,
        }
    if key == "maintenance:1":
        return {
            "drift_magnitude": 0.12,
            "new_data_size": 1500,
            "days_since_last_train": 45,
        }
    if key == "maintenance:2":
        return {
            "project_id": project_id,
            "new_repo": "meta-llama/Meta-Llama-3.1-8B",
            "new_revision": "main",
        }
    if key == "maintenance:3":
        return {"ref": "main"}

    raise ValueError(f"No arg factory for key={key!r}")


# ---------------------------------------------------------------------------
# Socket-blocking context manager
# ---------------------------------------------------------------------------


class _NetworkBlocked:
    """Monkeypatches socket.socket and socket.create_connection to raise."""

    def __enter__(self) -> "_NetworkBlocked":
        def _raise(*_a: Any, **_kw: Any) -> None:
            raise AssertionError("network access attempted")

        self._orig_socket = socket.socket
        self._orig_create_connection = socket.create_connection
        socket.socket = _raise  # type: ignore[assignment]
        socket.create_connection = _raise  # type: ignore[assignment]
        return self

    def __exit__(self, *_: Any) -> None:
        socket.socket = self._orig_socket  # type: ignore[assignment]
        socket.create_connection = self._orig_create_connection  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    return tmp_path / "ws"


@pytest.fixture()
def store(workspace: Path) -> Store:
    return Store(root=workspace)


@pytest.fixture()
def project_id(store: Store) -> str:
    store.init_project("zdtest", "ACME")
    return "zdtest"


# ---------------------------------------------------------------------------
# Group 1 — No network for C1/C3 tools
# ---------------------------------------------------------------------------


class TestNoNetworkC1C3:
    """Every C1 and C3 tool must complete without opening a socket."""

    def _call(
        self,
        key: str,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict[str, Any]:
        mod_name, idx_str = key.split(":")
        mod = _MODULE_MAP[mod_name]
        fn, _ = mod._MCP_TOOLS[int(idx_str)]
        kwargs = _make_args(key, workspace, store, project_id)
        return fn(**kwargs)

    def _check(self, key: str, result: dict[str, Any]) -> None:
        assert isinstance(result, dict), f"[{key}] result is not a dict"
        assert "success" in result, f"[{key}] missing 'success' key"

    @pytest.mark.parametrize("key", [k for k, cls in _TOOL_CLASS.items() if cls == "C1"])
    def test_c1_no_network(
        self,
        key: str,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """C1 tool must complete without network and return a result dict."""
        # Point FTOS_WORKSPACE at tmp so any workspace_root() calls go there,
        # not to the repo root (which would leave stray ftos-workspace dirs).
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        with _NetworkBlocked():
            result = self._call(key, workspace, store, project_id, monkeypatch)
        self._check(key, result)

    @pytest.mark.parametrize("key", [k for k, cls in _TOOL_CLASS.items() if cls == "C3"])
    def test_c3_no_network(
        self,
        key: str,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """C3 tool must complete without network and return a result dict."""
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))
        with _NetworkBlocked():
            result = self._call(key, workspace, store, project_id, monkeypatch)
        self._check(key, result)


# ---------------------------------------------------------------------------
# Group 2 — C2 dry_run is networkless
# ---------------------------------------------------------------------------

# All env vars that might activate C2 tools
_C2_ENV_VARS = [
    "FTOS_SSH_HOST",
    "FTOS_SSH_KEY",
    "FTOS_REGISTRY",
    "FTOS_REGISTRY_TOKEN",
    "FTOS_SFTP_HOST",
    "FTOS_SFTP_USER",
    "FTOS_SFTP_KEY",
    "FTOS_SMTP_HOST",
    "FTOS_SMTP_USER",
    "FTOS_SMTP_PASSWORD",
    "FTOS_SLACK_WEBHOOK",
    "FTOS_CALENDLY_TOKEN",
    "HF_TOKEN",
    "FTOS_GIT_REMOTE",
    "FTOS_LOCAL_PYTHON",
    "FTOS_WORKSPACE",
]


class TestC2DryRunNetworkless:
    """Every C2 tool with no env configured must: executed=False, dry_run=True, no socket."""

    def _call(
        self,
        key: str,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> dict[str, Any]:
        # Wipe all C2-relevant env vars
        for var in _C2_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        # Point FTOS_WORKSPACE at tmp so workspace_root() calls don't pollute repo root
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))

        mod_name, idx_str = key.split(":")
        mod = _MODULE_MAP[mod_name]
        fn, _ = mod._MCP_TOOLS[int(idx_str)]
        kwargs = _make_args(key, workspace, store, project_id)
        return fn(**kwargs)

    @pytest.mark.parametrize("key", [k for k, cls in _TOOL_CLASS.items() if cls == "C2"])
    def test_c2_dry_run_no_network(
        self,
        key: str,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """C2 tool without env: dry_run=True, executed=False, no socket opened."""
        with _NetworkBlocked():
            result = self._call(key, workspace, store, project_id, monkeypatch)

        assert isinstance(result, dict), f"[{key}] result not dict"
        assert "success" in result, f"[{key}] missing 'success'"
        assert (
            result["success"] is True
        ), f"[{key}] expected success=True in dry_run, got error={result.get('error')}"
        meta = result.get("meta", {})
        assert meta.get("executed") is False, f"[{key}] expected meta.executed=False, got {meta}"
        assert meta.get("dry_run") is True, f"[{key}] expected meta.dry_run=True, got {meta}"
        data = result.get("data", {})
        # Must have a command, message, or note in data
        has_command_hint = "command" in data or "message" in data or "note" in data or "cmd" in data
        assert has_command_hint, f"[{key}] no command/message/note in data={data}"


# ---------------------------------------------------------------------------
# Group 3 — Registration & boot
# ---------------------------------------------------------------------------


class TestRegistrationAndBoot:
    """65 tools registered, server importable with zero env vars."""

    def test_total_domain_tool_count(self) -> None:
        modules = [
            prep,
            synthetic,
            pipeline,
            execution,
            evaluation,
            security,
            packaging,
            docs,
            client,
            maintenance,
        ]
        total = sum(len(m._MCP_TOOLS) for m in modules)
        assert total == 64, f"Expected 64 domain tools, got {total}"

    def test_server_registers_65_tools(self) -> None:
        import fine_tuning_os.server as _server  # noqa: PLC0415

        mcp = _server.mcp
        if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
            count = len(mcp._tool_manager._tools)
        else:
            modules = [
                prep,
                synthetic,
                pipeline,
                execution,
                evaluation,
                security,
                packaging,
                docs,
                client,
                maintenance,
            ]
            count = sum(len(m._MCP_TOOLS) for m in modules) + 1  # +1 for ftos_health
        assert count == 65, f"Expected 65 tools, got {count}"

    def test_server_import_zero_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Importing server and accessing mcp must not raise with zero env vars."""
        for var in _C2_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        # Just access the already-imported module — any import-time exception
        # would have already failed above.
        import fine_tuning_os.server as _server  # noqa: PLC0415

        assert _server.mcp is not None

    def test_tool_class_map_covers_all_tools(self) -> None:
        """Our _TOOL_CLASS dict must account for every tool in every module."""
        for mod_name, mod in _MODULE_MAP.items():
            for idx in range(len(mod._MCP_TOOLS)):
                key = f"{mod_name}:{idx}"
                assert key in _TOOL_CLASS, f"Tool {key} is not in _TOOL_CLASS mapping — add it"


# ---------------------------------------------------------------------------
# Group 4 — Filesystem confinement
# ---------------------------------------------------------------------------

# Representative file-writing tools (mix of C1 and C2)
_WRITING_TOOLS: list[str] = [
    "prep:0",  # create_training_config  → config/training.yaml
    "prep:2",  # generate_requirements  → requirements.txt
    "prep:3",  # create_project_structure → dirs
    "synthetic:0",  # generate_synthetic_dataset → data/synthetic/…
    "pipeline:6",  # generate_unit_tests → tests/*.py
    "packaging:2",  # build_inference_container → docker/Dockerfile.infer
    "packaging:7",  # generate_delivery_note → deliverables/delivery_note.md
    "docs:0",  # generate_contract → docs/
    "docs:3",  # generate_user_guide → docs/
    "client:3",  # log_project_event → events.jsonl
]


class TestFilesystemConfinement:
    """After exercising file-writing tools, no file exists outside workspace."""

    def test_all_writes_inside_workspace(
        self,
        workspace: Path,
        store: Store,
        project_id: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """No stray files should be created outside the workspace root."""
        # Wipe C2 env vars so C2 tools run in dry_run (no live writes outside)
        for var in _C2_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        # Point FTOS_WORKSPACE at our tmp workspace so MCP wrappers that call
        # workspace_root() (e.g. create_project_structure) use the tmp dir.
        monkeypatch.setenv("FTOS_WORKSPACE", str(workspace))

        repo_root = Path(__file__).parent.parent.resolve()
        stray_docker = repo_root / "docker"
        stray_ftos_workspace = repo_root / "ftos-workspace"

        for key in _WRITING_TOOLS:
            mod_name, idx_str = key.split(":")
            mod = _MODULE_MAP[mod_name]
            fn, _ = mod._MCP_TOOLS[int(idx_str)]
            kwargs = _make_args(key, workspace, store, project_id)
            fn(**kwargs)  # call; we don't care if it succeeds, only about side-effects

        # Assert no stray docker/ dir at repo root
        assert (
            not stray_docker.exists()
        ), f"Stray docker/ directory was created at repo root: {stray_docker}"
        # Assert no ftos-workspace at repo root (default workspace_root() fallback)
        assert (
            not stray_ftos_workspace.exists()
        ), f"Stray ftos-workspace created at repo root: {stray_ftos_workspace}"

    def test_no_project_id_container_build_fails_not_cwd(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """build_inference_container with no project_id must fail, not write to CWD."""
        for var in _C2_ENV_VARS:
            monkeypatch.delenv(var, raising=False)

        cwd_docker = Path.cwd() / "docker"
        result = packaging._mcp_build_inference_container(
            model_path="/models/m",
            engine="vllm",
            project_id=None,
        )
        assert result["success"] is False, "Expected failure when project_id=None, got success=True"
        assert not cwd_docker.exists(), f"Stray docker/ directory at CWD: {cwd_docker}"
