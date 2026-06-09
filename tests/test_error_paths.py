# SPDX-License-Identifier: Apache-2.0
"""Targeted error-path tests to push coverage from 93% → ≥95%.

Each test triggers a specific error branch (OSError, TemplateError,
missing project, bad crypto key, short ciphertext) via monkeypatching
or crafted inputs, then asserts the returned failure envelope is correct.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import jinja2
import pytest

from fine_tuning_os.crypto import decrypt_file, generate_key
from fine_tuning_os.store import Store
from fine_tuning_os.tools.client import generate_invoice, log_project_event, onboard_client
from fine_tuning_os.tools.docs import (
    export_document_pdf,
    generate_contract,
    generate_deployment_guide,
    generate_destruction_certificate,
    generate_nda,
    generate_performance_report,
    generate_user_guide,
)
from fine_tuning_os.tools.maintenance import mcp_self_update, update_base_model
from fine_tuning_os.tools.packaging import (
    build_inference_container,
    encrypt_deliverable,
)
from fine_tuning_os.tools.pipeline import (
    _render_and_write,
    _run_subprocess_live,
    build_docker_image,
    get_local_metrics,
    run_local_synthetic_train,
)
from fine_tuning_os.tools.prep import (
    anonymize_dataset_preview,
    create_training_config,
    describe_expected_data_format,
    generate_requirements,
    split_dataset_config,
)
from fine_tuning_os.tools.security import (
    generate_security_report,
)
from fine_tuning_os.tools.synthetic import generate_synthetic_dataset

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_project(tmp_path: Path, pid: str = "test_proj") -> Store:
    """Create a minimal project workspace and return the Store."""
    s = Store(root=tmp_path)
    s.init_project(pid, "TestClient")
    return s


# ---------------------------------------------------------------------------
# crypto.py — missing lines 40 (bad key) and 43 (short ciphertext)
# ---------------------------------------------------------------------------


class TestCryptoErrorPaths:
    def test_decrypt_wrong_key_length_raises(self, tmp_path: Path) -> None:
        src = tmp_path / "src.bin"
        src.write_bytes(b"x" * 64)
        with pytest.raises(ValueError, match="32 bytes"):
            decrypt_file(src, tmp_path / "out.bin", b"short")

    def test_decrypt_too_short_ciphertext(self, tmp_path: Path) -> None:
        src = tmp_path / "tiny.bin"
        # 12-byte nonce + 16-byte GCM tag = 28 minimum — write fewer
        src.write_bytes(b"\x00" * 10)
        key = generate_key()
        with pytest.raises(ValueError, match="too short"):
            decrypt_file(src, tmp_path / "out.bin", key)


# ---------------------------------------------------------------------------
# render.py — lines 50-54 (weasyprint not installed, covered indirectly via
# markdown_file_to_pdf ImportError path in docs/client tools)
# We trigger the ImportError branch explicitly.
# ---------------------------------------------------------------------------


class TestRenderPdfBranch:
    def test_markdown_file_to_pdf_import_error(self, tmp_path: Path) -> None:
        """render.markdown_file_to_pdf raises ImportError when weasyprint absent."""
        from fine_tuning_os.render import markdown_file_to_pdf

        md = tmp_path / "doc.md"
        md.write_text("# Hello", encoding="utf-8")
        # Weasyprint is not installed in the test env → ImportError
        with pytest.raises(ImportError):
            markdown_file_to_pdf(md, tmp_path / "doc.pdf")


# ---------------------------------------------------------------------------
# server.py — lines 79, 83 (main() and __main__ guard)
# These are execution-entry branches; we can cover them by importing and
# calling main() with the mcp.run patched to a no-op.
# ---------------------------------------------------------------------------


class TestServerMain:
    def test_main_calls_mcp_run(self) -> None:
        import fine_tuning_os.server as server_mod

        with patch.object(server_mod.mcp, "run") as mock_run:
            server_mod.main()
        mock_run.assert_called_once_with(transport="stdio")


# ---------------------------------------------------------------------------
# tools/synthetic.py — lines 59-60 (project read fails) and 80-87 (write fails)
# ---------------------------------------------------------------------------


class TestSyntheticErrorPaths:
    def test_missing_project_returns_fail(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        # No project initialised → FileNotFoundError in read_project
        result = generate_synthetic_dataset("no_project", 10, 42, store=s)
        assert result["success"] is False

    def test_write_atomic_oserror_returns_fail(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "synth_proj")
        schema = {"columns": [{"name": "x", "dtype": "int"}]}
        with patch(
            "fine_tuning_os.tools.synthetic.write_text_atomic", side_effect=OSError("disk full")
        ):
            result = generate_synthetic_dataset("synth_proj", 10, 1, schema=schema, store=s)
        assert result["success"] is False
        assert "disk full" in result["error"]


# ---------------------------------------------------------------------------
# tools/docs.py — template error branches (lines 42, 81-82, 89, 130-131, …)
# Each doc tool has a "template error" early-return; we patch render_template
# to raise jinja2.TemplateError for one tool at a time.
# ---------------------------------------------------------------------------

_TEMPLATE_PATCH = "fine_tuning_os.tools.docs.render_template"


class TestDocsTemplateErrors:
    def _bad_template(self, *_a: Any, **_kw: Any) -> str:
        raise jinja2.TemplateError("boom")

    def test_generate_contract_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_contract")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_contract("proj_contract", "1000€", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_nda_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_nda")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_nda("proj_nda", "A", "B", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_performance_report_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_perf")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_performance_report("proj_perf", {"bleu": 0.5}, store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_user_guide_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_ug")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_user_guide("proj_ug", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_deployment_guide_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_dg")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_deployment_guide("proj_dg", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_destruction_cert_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_dc")
        with patch(_TEMPLATE_PATCH, side_effect=self._bad_template):
            r = generate_destruction_certificate("proj_dc", "2025-01-01", "shred", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_contract_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_cw")
        with patch("fine_tuning_os.tools.docs.write_text_atomic", side_effect=OSError("no space")):
            r = generate_contract("proj_cw", "1000€", store=s)
        assert r["success"] is False

    def test_generate_user_guide_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_ugw")
        with patch("fine_tuning_os.tools.docs.write_text_atomic", side_effect=OSError("no space")):
            r = generate_user_guide("proj_ugw", store=s)
        assert r["success"] is False

    def test_generate_deployment_guide_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "proj_dgw")
        with patch("fine_tuning_os.tools.docs.write_text_atomic", side_effect=OSError("no space")):
            r = generate_deployment_guide("proj_dgw", store=s)
        assert r["success"] is False

    def test_export_document_pdf_missing_file(self, tmp_path: Path) -> None:
        r = export_document_pdf(str(tmp_path / "nonexistent.md"))
        assert r["success"] is False
        assert "not found" in r["error"]


# ---------------------------------------------------------------------------
# tools/prep.py — missing lines (OSError on write, template error, validation)
# ---------------------------------------------------------------------------

_PREP_TEMPLATE_PATCH = "fine_tuning_os.tools.prep.render_template"


class TestPrepErrorPaths:
    def test_create_training_config_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "prep_tmpl")
        with patch(_PREP_TEMPLATE_PATCH, side_effect=jinja2.TemplateError("oops")):
            r = create_training_config(
                "prep_tmpl",
                base_model="m",
                framework="unsloth",
                store=s,
            )
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_create_training_config_write_oserror(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "prep_write")
        with patch("fine_tuning_os.tools.prep.write_text_atomic", side_effect=OSError("disk")):
            r = create_training_config(
                "prep_write",
                base_model="m",
                framework="unsloth",
                store=s,
            )
        assert r["success"] is False

    def test_anonymize_dataset_read_oserror(self, tmp_path: Path) -> None:
        fp = tmp_path / "data.jsonl"
        fp.write_bytes(b"\xff\xfe")  # invalid UTF-8 → UnicodeDecodeError path
        r = anonymize_dataset_preview(str(fp))
        assert r["success"] is False

    def test_describe_expected_data_format_missing_project(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = describe_expected_data_format(
            "no_project",
            columns=[{"name": "x", "dtype": "int"}],
            task_type="generation",
            store=s,
        )
        assert r["success"] is False

    def test_split_dataset_config_template_error(self, tmp_path: Path) -> None:
        with patch(_PREP_TEMPLATE_PATCH, side_effect=jinja2.TemplateError("bad")):
            r = split_dataset_config(ratios={"train": 0.8, "val": 0.1, "test": 0.1})
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_generate_requirements_write_error_invalid_pid(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        # Path traversal → ValueError from project_dir
        r = generate_requirements(project_id="../escape", store=s)
        assert r["success"] is False


# ---------------------------------------------------------------------------
# tools/pipeline.py — render_and_write + run_subprocess_live error paths
# Lines 88-94, 144-149, 211-212, 240, 267-268, 398-399
# ---------------------------------------------------------------------------


class TestPipelineErrorPaths:
    def test_render_and_write_template_error(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with patch(
            "fine_tuning_os.tools.pipeline.render_template", side_effect=jinja2.TemplateError("t")
        ):
            err = _render_and_write("fake.j2", dest, key="val")
        assert err is not None
        assert "template error" in err

    def test_render_and_write_oserror(self, tmp_path: Path) -> None:
        dest = tmp_path / "out.txt"
        with patch("fine_tuning_os.tools.pipeline.write_text_atomic", side_effect=OSError("io")):
            err = _render_and_write("train/train.py.j2", dest, project_id="x", steps=5)
        assert err is not None

    def test_run_subprocess_live_oserror(self) -> None:

        with patch("subprocess.run", side_effect=OSError("no exec")):
            err, data = _run_subprocess_live(["nonexistent_cmd_xyz"], timeout=5)
        assert err is not None

    def test_run_local_synthetic_train_render_fail(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "pipe_train")
        with patch(
            "fine_tuning_os.tools.pipeline.render_template",
            side_effect=jinja2.TemplateError("bad"),
        ):
            r = run_local_synthetic_train("pipe_train", store=s)
        assert r["success"] is False

    def test_build_docker_image_render_fail(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "pipe_docker")
        with patch(
            "fine_tuning_os.tools.pipeline.render_template",
            side_effect=jinja2.TemplateError("bad"),
        ):
            r = build_docker_image("pipe_docker", "python:3.12", "mytag", store=s)
        assert r["success"] is False

    def test_get_local_metrics_oserror(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "pipe_metrics")
        metrics_path = tmp_path / "pipe_metrics" / "outputs" / "metrics.json"
        metrics_path.parent.mkdir(parents=True, exist_ok=True)
        metrics_path.write_text('{"loss": 0.1}', encoding="utf-8")
        with patch("pathlib.Path.read_text", side_effect=OSError("read fail")):
            r = get_local_metrics("pipe_metrics", store=s)
        assert r["success"] is False


# ---------------------------------------------------------------------------
# tools/execution.py — lines 125-131, 211-212, 246-247, 294-295, 412-413
# Cover the OSError exception handler in push_to_registry (C2 live path)
# and the ssh gate fallback config-unavailable path.
# ---------------------------------------------------------------------------


class TestExecutionErrorPaths:
    def test_push_docker_to_registry_dry_run(self) -> None:
        """push_docker_to_registry without FTOS_REGISTRY → dry_run envelope."""
        from fine_tuning_os.tools.execution import push_docker_to_registry

        import os

        os.environ.pop("FTOS_REGISTRY", None)
        r = push_docker_to_registry("myimage:latest")
        assert r["success"] is True
        assert r["meta"].get("dry_run") is True

    def test_push_docker_to_registry_oserror(self) -> None:
        """push_docker_to_registry live path OSError → fail envelope."""
        from fine_tuning_os.tools.execution import push_docker_to_registry

        import os

        os.environ["FTOS_REGISTRY"] = "registry.example.io"
        os.environ["FTOS_REGISTRY_TOKEN"] = "tok"
        try:
            with patch("subprocess.run", side_effect=OSError("connection refused")):
                r = push_docker_to_registry("myimage:latest")
            assert r["success"] is False
        finally:
            os.environ.pop("FTOS_REGISTRY", None)
            os.environ.pop("FTOS_REGISTRY_TOKEN", None)

    def test_monitor_training_metrics_ssh_not_configured(self) -> None:
        from fine_tuning_os.tools.execution import monitor_training_metrics

        r = monitor_training_metrics("job123", "remote-host")
        # Without SSH creds configured → dry_run
        assert r["success"] is True
        assert r["meta"].get("dry_run") is True or "command" in (r.get("data") or {})

    def test_pause_resume_training_dry_run(self) -> None:
        from fine_tuning_os.tools.execution import pause_resume_training

        r = pause_resume_training("job42", "pause")
        assert r["success"] is True


# ---------------------------------------------------------------------------
# tools/packaging.py — lines 108, 124, 267-268, 279-280, 286-287, 407-408 …
# ---------------------------------------------------------------------------

_PKG_TEMPLATE_PATCH = "fine_tuning_os.tools.packaging.render_template"


class TestPackagingErrorPaths:
    def test_build_inference_container_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "pkg_tmpl")
        with patch(_PKG_TEMPLATE_PATCH, side_effect=jinja2.TemplateError("bad")):
            r = build_inference_container("model/path", project_id="pkg_tmpl", store=s)
        assert r["success"] is False
        assert "template error" in r["error"]

    def test_build_inference_container_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "pkg_write")
        with patch("fine_tuning_os.tools.packaging.write_text_atomic", side_effect=OSError("disk")):
            r = build_inference_container("model/path", project_id="pkg_write", store=s)
        assert r["success"] is False

    def test_build_inference_container_missing_project_id(self) -> None:
        r = build_inference_container("model/path")
        assert r["success"] is False
        assert "project_id is required" in r["error"]

    def test_encrypt_deliverable_oserror(self, tmp_path: Path) -> None:
        src = tmp_path / "file.txt"
        src.write_text("hello", encoding="utf-8")
        with patch("fine_tuning_os.tools.packaging.encrypt_file", side_effect=OSError("enc fail")):
            r = encrypt_deliverable([str(src)], output_dir=str(tmp_path))
        assert r["success"] is False

    def test_encrypt_deliverable_inference_config_write_error(self, tmp_path: Path) -> None:
        from fine_tuning_os.tools.packaging import generate_inference_config

        s = _make_project(tmp_path, "pkg_inf")
        with patch("fine_tuning_os.tools.packaging.write_text_atomic", side_effect=OSError("io")):
            r = generate_inference_config(project_id="pkg_inf", store=s)
        assert r["success"] is False


# ---------------------------------------------------------------------------
# tools/maintenance.py — lines 82-83, 100, 254-255, 267-268, 302, 316-317
# ---------------------------------------------------------------------------


class TestMaintenanceErrorPaths:
    def test_update_base_model_missing_project(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = update_base_model("no_project", "org/model-v2", "main", store=s)
        assert r["success"] is False

    def test_mcp_self_update_dry_run_no_env(self) -> None:
        import os

        os.environ.pop("FTOS_GIT_REMOTE", None)
        r = mcp_self_update()
        assert r["success"] is True
        assert r["meta"].get("dry_run") is True


# ---------------------------------------------------------------------------
# tools/security.py — lines 83-84, 101, 528-534, 570-571, 589-590
# ---------------------------------------------------------------------------


class TestSecurityErrorPaths:
    def test_generate_security_report_invalid_project(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = generate_security_report("../escape", store=s)
        assert r["success"] is False

    def test_generate_security_report_empty_project_id(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = generate_security_report("", store=s)
        assert r["success"] is False
        assert "project_id must not be empty" in r["error"]

    def test_generate_security_report_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "sec_write")
        with patch("fine_tuning_os.tools.security.write_text_atomic", side_effect=OSError("disk")):
            r = generate_security_report("sec_write", store=s)
        assert r["success"] is False

    def test_audit_code_no_network_parse_error(self) -> None:
        from fine_tuning_os.tools.security import audit_code_no_network

        r = audit_code_no_network(source="def foo(: pass")
        assert r["success"] is False

    def test_audit_dockerfile_missing_file(self, tmp_path: Path) -> None:
        from fine_tuning_os.tools.security import audit_dockerfile_security

        r = audit_dockerfile_security(dockerfile_path=str(tmp_path / "no.dockerfile"))
        assert r["success"] is False
        assert "not found" in r["error"]

    def test_audit_dockerfile_read_oserror(self, tmp_path: Path) -> None:
        from fine_tuning_os.tools.security import audit_dockerfile_security

        df = tmp_path / "Dockerfile"
        df.write_text("FROM python:3.12\n", encoding="utf-8")
        with patch("pathlib.Path.read_text", side_effect=OSError("permission denied")):
            r = audit_dockerfile_security(dockerfile_path=str(df))
        assert r["success"] is False


# ---------------------------------------------------------------------------
# tools/client.py — lines 202-203, 225-226, 338, 346, 456-457, 490, 510, 517
# ---------------------------------------------------------------------------


class TestClientErrorPaths:
    def test_log_project_event_missing_project(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = log_project_event("no_project", "test_event", {"k": "v"}, store=s)
        assert r["success"] is False

    def test_generate_invoice_template_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "inv_tmpl")
        lines = [{"desc": "work", "qty": 1, "pu": 100.0, "montant": 100.0}]
        with patch(
            "fine_tuning_os.tools.client.render_template", side_effect=Exception("bad tmpl")
        ):
            r = generate_invoice("inv_tmpl", lines, store=s)
        assert r["success"] is False

    def test_generate_invoice_write_error(self, tmp_path: Path) -> None:
        s = _make_project(tmp_path, "inv_write")
        lines = [{"desc": "x", "qty": 1, "pu": 50.0, "montant": 50.0}]
        with patch("fine_tuning_os.tools.client.write_text_atomic", side_effect=OSError("io")):
            r = generate_invoice("inv_write", lines, store=s)
        assert r["success"] is False

    def test_onboard_client_creates_project(self, tmp_path: Path) -> None:
        s = Store(root=tmp_path)
        r = onboard_client("AcmeCorp", "LLM fine-tuning", store=s)
        assert r["success"] is True
        assert "project_id" in r["data"]
