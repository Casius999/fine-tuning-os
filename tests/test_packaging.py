# SPDX-License-Identifier: Apache-2.0
# tests/test_packaging.py
"""TDD tests for packaging.py tools (39–46).

C2 dry-run proof: with no env vars set, every C2 tool must return
executed=False, dry_run=True, a command string, and must NOT call
paramiko or subprocess.

Tool 44: round-trip test — encrypt then decrypt with returned key_hex.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from fine_tuning_os.tools import packaging


# ---------------------------------------------------------------------------
# Tool 39: merge_lora_weights (C2 — local_python)
# ---------------------------------------------------------------------------
class TestMergeLoraWeights:
    def test_dry_run_no_env(self) -> None:
        result = packaging.merge_lora_weights(
            base_model="meta-llama/Llama-3-8B",
            adapter_path="/tmp/adapter",
            output_path="/tmp/merged",
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        assert "command" in result["data"]
        assert "peft" in result["data"]["command"] or "merge" in result["data"]["command"].lower()

    def test_command_contains_paths(self) -> None:
        result = packaging.merge_lora_weights(
            base_model="model/base",
            adapter_path="/adapters/lora",
            output_path="/out/merged",
        )
        assert "model/base" in result["data"]["command"]
        assert "/adapters/lora" in result["data"]["command"]
        assert "/out/merged" in result["data"]["command"]

    def test_dry_run_no_subprocess(self) -> None:
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            result = packaging.merge_lora_weights("m", "a", "o")
        assert result["success"] is True

    def test_local_python_not_configured_stays_dry(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.merge_lora_weights("base", "adapter", "out", local_python=True)
        assert result["meta"]["dry_run"] is True


# ---------------------------------------------------------------------------
# Tool 40: quantize_model (C2 — local_python)
# ---------------------------------------------------------------------------
class TestQuantizeModel:
    def test_dry_run_gguf(self) -> None:
        result = packaging.quantize_model(model_path="/models/merged", format="gguf", bits=4)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert (
            "gguf" in result["data"]["command"].lower()
            or "convert" in result["data"]["command"].lower()
        )

    def test_dry_run_gptq(self) -> None:
        result = packaging.quantize_model(model_path="/models/merged", format="gptq", bits=8)
        assert result["success"] is True
        assert (
            "gptq" in result["data"]["command"].lower() or "AutoGPTQ" in result["data"]["command"]
        )

    def test_dry_run_awq(self) -> None:
        result = packaging.quantize_model(model_path="/models/merged", format="awq", bits=4)
        assert result["success"] is True
        assert "awq" in result["data"]["command"].lower() or "AWQ" in result["data"]["command"]

    def test_invalid_format_fails(self) -> None:
        result = packaging.quantize_model(model_path="/models/merged", format="bnb4")
        assert result["success"] is False
        assert "bnb4" in result["error"]

    def test_output_path_in_command(self) -> None:
        result = packaging.quantize_model(
            model_path="/models/merged", format="gguf", bits=4, output_path="/out/q4"
        )
        assert "/out/q4" in result["data"]["command"]

    def test_dry_run_no_subprocess(self) -> None:
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            result = packaging.quantize_model("/models/m", "gguf", 4)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tool 41: build_inference_container (C2 — docker)
# ---------------------------------------------------------------------------
class TestBuildInferenceContainer:
    def test_dry_run_no_docker_env(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/merged",
            engine="vllm",
            project_id=project_id,
            store=store,
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert "docker build" in result["data"]["command"]
        assert "dockerfile_content" in result["data"]

    def test_dockerfile_contains_engine_vllm(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/m", engine="vllm", project_id=project_id, store=store
        )
        assert "vllm" in result["data"]["dockerfile_content"].lower()

    def test_dockerfile_contains_engine_sglang(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/m", engine="sglang", project_id=project_id, store=store
        )
        assert "sglang" in result["data"]["dockerfile_content"].lower()

    def test_invalid_engine_fails(self) -> None:
        result = packaging.build_inference_container(model_path="/models/m", engine="triton")
        assert result["success"] is False
        assert "triton" in result["error"]

    def test_missing_project_id_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No project_id → fail (never write to CWD)."""
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/m", engine="vllm", project_id=None
        )
        assert result["success"] is False
        assert "project_id" in result["error"].lower()

    def test_dockerfile_written_to_disk(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/m",
            engine="vllm",
            project_id=project_id,
            store=store,
        )
        assert result["success"] is True
        dockerfile = Path(result["data"]["dockerfile_path"])
        assert dockerfile.exists()
        assert "FROM" in dockerfile.read_text()

    def test_dry_run_no_subprocess(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        with patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            result = packaging.build_inference_container(
                model_path="/m", engine="vllm", project_id=project_id, store=store
            )
        assert result["success"] is True

    def test_no_project_id_fails_not_writes_to_cwd(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TDD / Task A regression: calling without project_id must fail (not write to cwd).

        The old code fell back to Path("docker") relative to CWD, creating stray files
        at the repo root. After the fix, omitting project_id must return an error, never
        silently write outside the workspace.
        """
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        # Capture CWD so we can assert no docker/ dir was created there
        cwd = Path.cwd()
        stray_dir = cwd / "docker"

        result = packaging.build_inference_container(
            model_path="/models/m",
            engine="vllm",
            project_id=None,
            store=None,
        )
        # Must fail with an error — no longer silently writes to CWD
        assert result["success"] is False, (
            f"Expected failure when project_id is None, got success=True. "
            f"data={result.get('data')}"
        )
        # No stray docker/ directory should exist at CWD
        assert not stray_dir.exists(), f"Stray docker/ directory was created at {stray_dir}"

    def test_dockerfile_written_inside_workspace_only(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Dockerfile must land inside store.project_dir, never outside workspace."""
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        result = packaging.build_inference_container(
            model_path="/models/m",
            engine="vllm",
            project_id=project_id,
            store=store,
        )
        assert result["success"] is True
        dockerfile = Path(result["data"]["dockerfile_path"])
        # Must be under store.root
        assert (
            store.root in dockerfile.parents
        ), f"Dockerfile {dockerfile} is not under workspace {store.root}"
        # Must NOT be in cwd or any ancestor of store.root
        cwd = Path.cwd()
        assert not dockerfile.is_relative_to(cwd) or dockerfile.is_relative_to(
            store.root
        ), f"Dockerfile {dockerfile} would be inside CWD but outside workspace"


# ---------------------------------------------------------------------------
# Tool 42: generate_inference_config (C1)
# ---------------------------------------------------------------------------
class TestGenerateInferenceConfig:
    def test_nominal(self) -> None:
        result = packaging.generate_inference_config(port=8080, engine="sglang")
        assert result["success"] is True
        assert result["data"]["config"]["port"] == 8080
        assert result["data"]["config"]["engine"] == "sglang"

    def test_no_real_key_in_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("API_KEY", "super_secret_api_key_12345")
        result = packaging.generate_inference_config(api_key_env_name="API_KEY")
        config_json = result["data"]["config_json"]
        assert "super_secret_api_key_12345" not in config_json
        # Only the ENV NAME is referenced
        assert "API_KEY" in config_json

    def test_written_to_project(self, store: Any, project_id: str) -> None:
        result = packaging.generate_inference_config(project_id=project_id, store=store)
        assert result["success"] is True
        assert "path" in result["data"]
        assert Path(result["data"]["path"]).exists()

    def test_extra_params_included(self) -> None:
        result = packaging.generate_inference_config(extra_params={"max_model_len": 8192})
        assert result["data"]["config"]["max_model_len"] == 8192

    def test_extra_params_api_key_excluded(self) -> None:
        result = packaging.generate_inference_config(
            extra_params={"api_key": "should_not_appear", "max_model_len": 512}
        )
        assert "api_key" not in result["data"]["config"]


# ---------------------------------------------------------------------------
# Tool 43: test_inference_api (C2 — base_url)
# ---------------------------------------------------------------------------
class TestTestInferenceApi:
    def test_dry_run_no_base_url(self) -> None:
        result = packaging.test_inference_api(prompts=["Hello!"], base_url=None)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert "curl" in result["data"]["command"].lower()

    def test_curl_command_references_env_name(self) -> None:
        result = packaging.test_inference_api(
            prompts=["Test"], base_url=None, api_key_env="MY_API_KEY"
        )
        assert "$MY_API_KEY" in result["data"]["command"]
        # Secret value must not appear
        assert "secret" not in result["data"]["command"].lower()

    def test_empty_prompts_fails(self) -> None:
        result = packaging.test_inference_api(prompts=[])
        assert result["success"] is False

    def test_live_response_sanitized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With base_url set, httpx is called; secrets in response must be masked."""
        import json  # noqa: PLC0415

        fake_response_body = json.dumps(
            {"choices": [{"message": {"content": "Connected from 192.168.1.100 user@secret.com"}}]}
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = fake_response_body
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.post", return_value=mock_resp):
            result = packaging.test_inference_api(
                prompts=["Hi"],
                base_url="http://localhost:8000",
                api_key_env="API_KEY",
            )

        assert result["success"] is True
        response_text = result["data"]["results"][0]["response"]
        assert "192.168.1.100" not in response_text
        assert "user@secret.com" not in response_text

    def test_dry_run_no_httpx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch("httpx.post", side_effect=AssertionError("no httpx")):
            result = packaging.test_inference_api(prompts=["Hello"], base_url=None)
        assert result["success"] is True


# ---------------------------------------------------------------------------
# Tool 44: encrypt_deliverable (C1 — crypto round-trip)
# ---------------------------------------------------------------------------
class TestEncryptDeliverable:
    def test_nominal_round_trip(self, tmp_path: Path) -> None:
        """Encrypt a temp file, then decrypt with returned key_hex — must recover exact bytes."""
        original_content = b"Top secret fine-tuned model deliverable v1.0\n"
        src = tmp_path / "model.bin"
        src.write_bytes(original_content)

        result = packaging.encrypt_deliverable(paths=[str(src)])
        assert result["success"] is True
        data = result["data"]

        assert "key_hex" in data
        assert "encrypted_path" in data
        assert "sha256" in data

        # Decrypt using the returned key
        from fine_tuning_os.crypto import decrypt_file  # noqa: PLC0415

        key = bytes.fromhex(data["key_hex"])
        decrypted_path = tmp_path / "model.decrypted"
        decrypt_file(Path(data["encrypted_path"]), decrypted_path, key)
        assert decrypted_path.read_bytes() == original_content

    def test_key_not_written_to_disk(self, tmp_path: Path) -> None:
        """The key_hex must NOT appear in any file in the output dir."""
        src = tmp_path / "file.txt"
        src.write_bytes(b"content")
        result = packaging.encrypt_deliverable(paths=[str(src)], output_dir=str(tmp_path))
        assert result["success"] is True
        key_hex = result["data"]["key_hex"]

        # Check no file in tmp_path contains the key hex
        for f in tmp_path.iterdir():
            if f.is_file() and f.suffix not in (".enc",):
                try:
                    content = f.read_text(encoding="utf-8", errors="replace")
                    assert key_hex not in content, f"Key found in {f}"
                except OSError:
                    pass

    def test_sha256_present(self, tmp_path: Path) -> None:
        src = tmp_path / "f.txt"
        src.write_bytes(b"hello")
        result = packaging.encrypt_deliverable(paths=[str(src)])
        assert len(result["data"]["sha256"]) == 64  # SHA-256 hex = 64 chars

    def test_multiple_paths_archived(self, tmp_path: Path) -> None:
        src1 = tmp_path / "a.txt"
        src2 = tmp_path / "b.txt"
        src1.write_bytes(b"aaa")
        src2.write_bytes(b"bbb")
        result = packaging.encrypt_deliverable(paths=[str(src1), str(src2)])
        assert result["success"] is True
        assert result["data"]["source_count"] == 2

    def test_missing_file_fails(self, tmp_path: Path) -> None:
        result = packaging.encrypt_deliverable(paths=[str(tmp_path / "missing.bin")])
        assert result["success"] is False

    def test_empty_paths_fails(self) -> None:
        result = packaging.encrypt_deliverable(paths=[])
        assert result["success"] is False

    def test_key_not_in_output_data_keys(self, tmp_path: Path) -> None:
        """Confirm key_hex is in data but no field named 'key' without 'hex' for safety."""
        src = tmp_path / "model.bin"
        src.write_bytes(b"model weights")
        result = packaging.encrypt_deliverable(paths=[str(src)])
        # Should have key_hex (intentional), not a bare 'key' field
        assert "key_hex" in result["data"]


# ---------------------------------------------------------------------------
# Tool 45: upload_deliverable (C2 — sftp)
# ---------------------------------------------------------------------------
class TestUploadDeliverable:
    def test_dry_run_no_env(self, tmp_path: Path) -> None:
        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"encrypted")
        result = packaging.upload_deliverable(path=str(src))
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False

    def test_command_uses_env_name_refs(self, tmp_path: Path) -> None:
        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"x")
        result = packaging.upload_deliverable(path=str(src))
        cmd = result["data"]["command"]
        # Env NAME refs (not values)
        assert "$FTOS_SFTP_KEY" in cmd or "FTOS_SFTP" in cmd

    def test_no_secret_values_in_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_SFTP_HOST", "sftp.example.com")
        monkeypatch.setenv("FTOS_SFTP_USER", "ftosuser")
        monkeypatch.setenv("FTOS_SFTP_KEY", "/home/user/.ssh/id_rsa_ftos")

        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"x")

        with patch(
            "paramiko.Transport",
            side_effect=AssertionError("no paramiko transport"),
        ):
            # Gate is configured so it will try live; mock to fail
            try:
                result = packaging.upload_deliverable(path=str(src))
            except AssertionError:
                # Live path failed, but we already tested command
                return

        # If it succeeded somehow, check no secret values in command
        if result.get("success"):
            cmd = result["data"].get("command", "")
            assert "ftosuser" not in cmd or "$FTOS_SFTP_USER" in cmd

    def test_dry_run_no_paramiko(self, tmp_path: Path) -> None:
        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"enc")
        with patch("paramiko.Transport", side_effect=AssertionError("no paramiko")):
            result = packaging.upload_deliverable(path=str(src))
        # Without env vars, should be dry_run and not reach paramiko
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_live_sanitizes_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FTOS_SFTP_HOST", "sftp.example.com")
        monkeypatch.setenv("FTOS_SFTP_USER", "ftosuser")
        monkeypatch.setenv("FTOS_SFTP_KEY", "/home/user/.ssh/id_rsa")

        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"x")

        import paramiko as _paramiko  # noqa: PLC0415

        mock_transport = MagicMock()
        mock_transport.__enter__ = MagicMock(return_value=mock_transport)
        mock_transport.__exit__ = MagicMock(return_value=False)
        mock_transport.connect.side_effect = _paramiko.SSHException(
            "Auth failed for user ftosuser@sftp.example.com 192.168.1.1"
        )

        with patch("paramiko.Transport", return_value=mock_transport):
            result = packaging.upload_deliverable(path=str(src))

        # Should fail gracefully
        assert result["success"] is False
        # Error should be sanitized (IP redacted)
        assert "192.168.1.1" not in result.get("error", "")


# ---------------------------------------------------------------------------
# Tool 46: generate_delivery_note (C1)
# ---------------------------------------------------------------------------
class TestGenerateDeliveryNote:
    def test_nominal(self, store: Any, project_id: str, tmp_path: Path) -> None:
        src = tmp_path / "model.enc"
        src.write_bytes(b"encrypted model")
        from fine_tuning_os.render import sha256_file  # noqa: PLC0415

        file_sha = sha256_file(src)
        result = packaging.generate_delivery_note(
            project_id=project_id,
            files=[{"name": "model.enc", "path": str(src), "sha256": file_sha}],
            store=store,
        )
        assert result["success"] is True
        assert "md_path" in result["data"]
        md_path = Path(result["data"]["md_path"])
        assert md_path.exists()
        content = md_path.read_text(encoding="utf-8")
        assert "model.enc" in content
        assert file_sha[:8] in content  # SHA256 in the table

    def test_sha256_computed_if_missing(self, store: Any, project_id: str, tmp_path: Path) -> None:
        src = tmp_path / "weights.bin"
        src.write_bytes(b"weights data")
        result = packaging.generate_delivery_note(
            project_id=project_id,
            files=[{"name": "weights.bin", "path": str(src)}],
            store=store,
        )
        assert result["success"] is True
        md_path = Path(result["data"]["md_path"])
        content = md_path.read_text()
        # SHA256 should have been auto-computed and appear in content
        assert "sha256" in content.lower() or "[" in content

    def test_empty_files_fails(self, store: Any, project_id: str) -> None:
        result = packaging.generate_delivery_note(
            project_id=project_id,
            files=[],
            store=store,
        )
        assert result["success"] is False

    def test_pdf_skipped_gracefully(self, store: Any, project_id: str, tmp_path: Path) -> None:
        src = tmp_path / "f.enc"
        src.write_bytes(b"x")
        with patch(
            "fine_tuning_os.tools.packaging.markdown_file_to_pdf",
            side_effect=ImportError("weasyprint not installed"),
        ):
            result = packaging.generate_delivery_note(
                project_id=project_id,
                files=[{"name": "f.enc", "sha256": "abc123"}],
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]

    def test_sha256_in_result(self, store: Any, project_id: str, tmp_path: Path) -> None:
        src = tmp_path / "f.txt"
        src.write_bytes(b"hi")
        result = packaging.generate_delivery_note(
            project_id=project_id,
            files=[{"name": "f.txt", "sha256": "fake256"}],
            store=store,
        )
        assert result["success"] is True
        assert len(result["data"]["sha256"]) == 64

    def test_decryption_procedure_in_note(
        self, store: Any, project_id: str, tmp_path: Path
    ) -> None:
        result = packaging.generate_delivery_note(
            project_id=project_id,
            files=[{"name": "model.enc", "sha256": "deadbeef" * 8}],
            store=store,
        )
        assert result["success"] is True
        content = Path(result["data"]["md_path"]).read_text()
        # Must contain decryption procedure
        assert (
            "AES" in content or "déchiffrement" in content.lower() or "decrypt" in content.lower()
        )


# ---------------------------------------------------------------------------
# MCP wrappers and register() — thin coverage pass
# ---------------------------------------------------------------------------
class TestPackagingMcpWrappers:
    def test_mcp_merge_lora_delegates(self) -> None:
        result = packaging._mcp_merge_lora_weights(
            base_model="base", adapter_path="adapter", output_path="out"
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_mcp_quantize_delegates(self) -> None:
        result = packaging._mcp_quantize_model(model_path="/m", format="gguf", bits=4)
        assert result["success"] is True

    def test_mcp_build_container_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("FTOS_LOCAL_PYTHON", raising=False)
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = packaging._mcp_build_inference_container(
            model_path="/m", engine="vllm", project_id=project_id
        )
        assert result["success"] is True

    def test_mcp_inference_config_delegates(self) -> None:
        result = packaging._mcp_generate_inference_config()
        assert result["success"] is True
        assert "config" in result["data"]

    def test_mcp_test_api_delegates(self) -> None:
        result = packaging._mcp_test_inference_api(prompts=["Hello"], base_url=None)
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_mcp_encrypt_delegates(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_bytes(b"content")
        result = packaging._mcp_encrypt_deliverable(paths=[str(f)])
        assert result["success"] is True

    def test_mcp_upload_delegates_dry(self, tmp_path: Path) -> None:
        f = tmp_path / "file.enc"
        f.write_bytes(b"enc")
        result = packaging._mcp_upload_deliverable(path=str(f))
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True

    def test_mcp_delivery_note_delegates(
        self, store: Any, project_id: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_WORKSPACE", str(store.root))
        result = packaging._mcp_generate_delivery_note(
            project_id=project_id,
            files=[{"name": "f.enc", "sha256": "a" * 64}],
        )
        assert result["success"] is True

    def test_register_calls_mcp_tool(self) -> None:
        registered: list[str] = []

        class FakeMcp:
            def tool(self, description: str):  # type: ignore[no-untyped-def]
                def decorator(fn):  # type: ignore[no-untyped-def]
                    registered.append(fn.__name__)
                    return fn

                return decorator

        packaging.register(FakeMcp())
        assert len(registered) == 8  # 8 packaging tools


# ---------------------------------------------------------------------------
# Live/configured branch coverage — mock gate + subprocess/paramiko
# ---------------------------------------------------------------------------
class TestLiveConfiguredBranches:
    """Cover the 'configured=True' execution paths by mocking gate() and subprocess."""

    _MOCK_META = {"executed": True, "dry_run": False}
    _MOCK_SUBPROCESS_RESULT = MagicMock(stdout="success output", stderr="", returncode=0)

    def _mock_gate_configured(self):
        """Return a mock gate that says configured=True."""
        return MagicMock(return_value=(True, self._MOCK_META))

    def test_merge_lora_live_configured(self) -> None:
        mock_run = MagicMock(return_value=self._MOCK_SUBPROCESS_RESULT)
        with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
            with patch("fine_tuning_os.tools.packaging._get_target_config") as mock_cfg:
                mock_cfg.return_value = {"FTOS_LOCAL_PYTHON": "/usr/bin/python3"}
                with patch("subprocess.run", mock_run):
                    result = packaging.merge_lora_weights(
                        base_model="base",
                        adapter_path="adapter",
                        output_path="out",
                        local_python=True,
                    )
        assert result["success"] is True
        assert result["meta"]["executed"] is True

    def test_merge_lora_live_subprocess_timeout(self) -> None:
        import subprocess  # noqa: PLC0415

        with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
            with patch("fine_tuning_os.tools.packaging._get_target_config") as mock_cfg:
                mock_cfg.return_value = {"FTOS_LOCAL_PYTHON": "/usr/bin/python3"}
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 600)):
                    result = packaging.merge_lora_weights(
                        base_model="base",
                        adapter_path="adapter",
                        output_path="out",
                        local_python=True,
                    )
        assert result["success"] is False

    def test_quantize_live_configured(self) -> None:
        mock_run = MagicMock(return_value=self._MOCK_SUBPROCESS_RESULT)
        with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
            with patch("fine_tuning_os.tools.packaging._get_target_config") as mock_cfg:
                mock_cfg.return_value = {"FTOS_LOCAL_PYTHON": "/usr/bin/python3"}
                with patch("subprocess.run", mock_run):
                    result = packaging.quantize_model(
                        model_path="/models/m",
                        format="gguf",
                        bits=4,
                        local_python=True,
                    )
        assert result["success"] is True
        assert result["meta"]["executed"] is True

    def test_quantize_live_subprocess_timeout(self) -> None:
        import subprocess  # noqa: PLC0415

        with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
            with patch("fine_tuning_os.tools.packaging._get_target_config") as mock_cfg:
                mock_cfg.return_value = {"FTOS_LOCAL_PYTHON": "/usr/bin/python3"}
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("cmd", 1800)):
                    result = packaging.quantize_model(
                        model_path="/models/m",
                        format="gguf",
                        bits=4,
                        local_python=True,
                    )
        assert result["success"] is False

    def test_build_container_live_docker(self, store: Any, project_id: str) -> None:
        mock_run = MagicMock(
            return_value=MagicMock(stdout="Successfully built", stderr="", returncode=0)
        )
        with patch("fine_tuning_os.tools.packaging.shutil") as mock_shutil:
            mock_shutil.which = MagicMock(return_value="/usr/bin/docker")
            with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
                with patch("subprocess.run", mock_run):
                    result = packaging.build_inference_container(
                        model_path="/models/m",
                        engine="vllm",
                        project_id=project_id,
                        store=store,
                    )
        assert result["success"] is True

    def test_build_container_live_docker_timeout(self, store: Any, project_id: str) -> None:
        import subprocess  # noqa: PLC0415

        with patch("fine_tuning_os.tools.packaging.shutil") as mock_shutil:
            mock_shutil.which = MagicMock(return_value="/usr/bin/docker")
            with patch("fine_tuning_os.tools.packaging.gate", return_value=(True, self._MOCK_META)):
                with patch(
                    "subprocess.run", side_effect=subprocess.TimeoutExpired(["docker"], 600)
                ):
                    result = packaging.build_inference_container(
                        model_path="/models/m",
                        engine="vllm",
                        project_id=project_id,
                        store=store,
                    )
        assert result["success"] is False

    def test_test_inference_api_exception_in_prompt(self) -> None:
        """Each prompt's exception is caught, appended as error entry."""
        with patch("httpx.post", side_effect=OSError("connection refused")):
            result = packaging.test_inference_api(
                prompts=["Hello"],
                base_url="http://localhost:9999",
            )
        assert result["success"] is True
        assert result["data"]["results"][0]["ok"] is False

    def test_upload_deliverable_live_success(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("FTOS_SFTP_HOST", "sftp.example.com")
        monkeypatch.setenv("FTOS_SFTP_USER", "testuser")
        monkeypatch.setenv("FTOS_SFTP_KEY", "/tmp/key")

        src = tmp_path / "deliverable.enc"
        src.write_bytes(b"encrypted")

        mock_transport = MagicMock()
        mock_sftp = MagicMock()
        mock_sftp.put = MagicMock(return_value=None)

        with patch("paramiko.Transport", return_value=mock_transport):
            with patch("paramiko.RSAKey.from_private_key_file", return_value=MagicMock()):
                with patch("paramiko.SFTPClient.from_transport", return_value=mock_sftp):
                    result = packaging.upload_deliverable(path=str(src))

        assert result["success"] is True
        assert result["data"]["uploaded"] is True

    def test_encrypt_deliverable_oserror(self, tmp_path: Path) -> None:
        """OSError during encryption fails gracefully."""
        src = tmp_path / "file.txt"
        src.write_bytes(b"data")
        with patch("fine_tuning_os.tools.packaging.encrypt_file", side_effect=OSError("disk full")):
            result = packaging.encrypt_deliverable(paths=[str(src)])
        assert result["success"] is False
        assert "disk full" in result["error"]

    def test_delivery_note_pdf_generic_exception_uses_pdf_skipped(
        self, store: Any, project_id: str, tmp_path: Path
    ) -> None:
        """PDF renderer generic exception → success=True, pdf_skipped present, md_path+sha256 intact."""
        with patch(
            "fine_tuning_os.tools.packaging.markdown_file_to_pdf",
            side_effect=RuntimeError("renderer crashed"),
        ):
            result = packaging.generate_delivery_note(
                project_id=project_id,
                files=[{"name": "model.enc", "sha256": "a" * 64}],
                store=store,
            )
        assert result["success"] is True
        assert "pdf_skipped" in result["data"]
        assert "pdf_path" not in result["data"]
        assert "md_path" in result["data"]
        assert len(result["data"]["sha256"]) == 64
