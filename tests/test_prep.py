# SPDX-License-Identifier: Apache-2.0
# tests/test_prep.py
"""Tests for prep.py tools (tools 1-5 + tool 8/9/10 from spec)."""

from __future__ import annotations

import json
from pathlib import Path


from fine_tuning_os.store import Store
from fine_tuning_os.tools import prep


# ---------------------------------------------------------------------------
# Tool 1: create_training_config
# ---------------------------------------------------------------------------
class TestCreateTrainingConfig:
    def test_nominal_unsloth(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.create_training_config(
            project_id="p1",
            base_model="mistralai/Mistral-7B-v0.3",
            store=store,
        )
        assert result["success"] is True
        data = result["data"]
        assert "path" in data
        assert "framework" in data
        assert data["framework"] == "unsloth"
        assert "content" in data
        path = Path(data["path"])
        assert path.exists()
        assert "mistralai/Mistral-7B-v0.3" in path.read_text()

    def test_axolotl_framework(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.create_training_config(
            project_id="p1",
            base_model="meta-llama/Llama-3-8B",
            framework="axolotl",
            store=store,
        )
        assert result["success"] is True
        assert result["data"]["framework"] == "axolotl"
        assert "axolotl" in result["data"]["content"].lower()

    def test_custom_framework(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.create_training_config(
            project_id="p1",
            base_model="model/x",
            framework="custom",
            store=store,
        )
        assert result["success"] is True

    def test_lora_rank_in_content(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.create_training_config(
            project_id="p1",
            base_model="x",
            lora_rank=64,
            store=store,
        )
        assert "64" in result["data"]["content"]

    def test_invalid_framework(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.create_training_config(
            project_id="p1",
            base_model="x",
            framework="bad_framework",
            store=store,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 2: cache_base_model (dry_run C2)
# ---------------------------------------------------------------------------
class TestCacheBaseModel:
    def test_returns_command_not_executed(self):
        result = prep.cache_base_model(
            repo_id="mistralai/Mistral-7B-v0.3",
            dest="/tmp/models/mistral",
        )
        assert result["success"] is True
        assert result["meta"]["dry_run"] is True
        assert result["meta"]["executed"] is False
        cmd = result["data"]["command"]
        assert "huggingface-cli" in cmd
        assert "mistralai/Mistral-7B-v0.3" in cmd

    def test_revision_in_command(self):
        result = prep.cache_base_model(
            repo_id="mistralai/Mistral-7B-v0.3",
            dest="/tmp/models/mistral",
            revision="main",
        )
        assert "main" in result["data"]["command"]

    def test_no_network_call(self, monkeypatch):
        """Ensure no socket is opened during dry_run."""
        import socket

        def _no_connect(*args, **kwargs):
            raise AssertionError("Network access forbidden in C2 dry_run")

        monkeypatch.setattr(socket, "create_connection", _no_connect)
        result = prep.cache_base_model(repo_id="x/y", dest="/tmp/x")
        assert result["meta"]["dry_run"] is True


# ---------------------------------------------------------------------------
# Tool 3: generate_requirements
# ---------------------------------------------------------------------------
class TestGenerateRequirements:
    def test_unsloth_has_core_packages(self):
        result = prep.generate_requirements(framework="unsloth")
        assert result["success"] is True
        content = result["data"]["content"]
        for pkg in ("unsloth", "peft", "trl", "transformers", "accelerate", "datasets"):
            assert pkg in content

    def test_axolotl_packages(self):
        result = prep.generate_requirements(framework="axolotl")
        content = result["data"]["content"]
        assert "axolotl" in content

    def test_with_extras(self):
        result = prep.generate_requirements(framework="unsloth", extras=["wandb", "bitsandbytes"])
        content = result["data"]["content"]
        assert "wandb" in content
        assert "bitsandbytes" in content

    def test_writes_to_project(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.generate_requirements(framework="unsloth", project_id="p1", store=store)
        assert result["success"] is True
        assert "path" in result["data"]
        p = Path(result["data"]["path"])
        assert p.exists()
        assert p.name == "requirements.txt"

    def test_no_project_no_file(self, tmp_path):
        result = prep.generate_requirements(framework="unsloth")
        assert "path" not in result["data"]
        assert result["data"]["content"]


# ---------------------------------------------------------------------------
# Tool 4: create_project_structure
# ---------------------------------------------------------------------------
class TestCreateProjectStructure:
    def test_creates_dirs(self, tmp_path):
        store = Store(root=tmp_path)
        result = prep.create_project_structure(
            project_id="myproject",
            client_name="ClientCorp",
            store=store,
        )
        assert result["success"] is True
        data = result["data"]
        assert data["project_id"] == "myproject"
        assert len(data["created_dirs"]) > 0
        pdir = tmp_path / "myproject"
        assert (pdir / "config").is_dir()
        assert (pdir / "data" / "synthetic").is_dir()

    def test_rejects_traversal(self, tmp_path):
        store = Store(root=tmp_path)
        result = prep.create_project_structure(
            project_id="../escape",
            client_name="Evil",
            store=store,
        )
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 5: load_project_template
# ---------------------------------------------------------------------------
class TestLoadProjectTemplate:
    def test_known_template(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.load_project_template(
            template_name="lora-mistral-v3",
            project_id="p1",
            store=store,
        )
        assert result["success"] is True
        data = result["data"]
        assert data["template_name"] == "lora-mistral-v3"
        assert "files" in data
        assert len(data["files"]) >= 1

    def test_unknown_template(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.load_project_template(
            template_name="nonexistent-template",
            project_id="p1",
            store=store,
        )
        assert result["success"] is False
        assert "unknown template" in result["error"].lower()


# ---------------------------------------------------------------------------
# Tool 6: describe_expected_data_format
# ---------------------------------------------------------------------------
class TestDescribeExpectedDataFormat:
    def test_persists_schema(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        columns = [{"name": "text", "dtype": "str"}, {"name": "label", "dtype": "int"}]
        result = prep.describe_expected_data_format(
            project_id="p1",
            columns=columns,
            task_type="classification",
            store=store,
        )
        assert result["success"] is True
        data = result["data"]
        assert data["project_id"] == "p1"
        assert "schema" in data
        # Verify it was persisted
        state = store.read_project("p1")
        assert state["data_schema"] is not None
        assert state["data_schema"]["task_type"] == "classification"

    def test_no_real_data_content(self, tmp_path):
        """The output must not contain any user content — only structural info."""
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.describe_expected_data_format(
            project_id="p1",
            columns=[{"name": "text", "dtype": "str"}],
            task_type="instruct",
            store=store,
        )
        assert result["success"] is True
        # Only column names/types, no sample values
        data_str = json.dumps(result["data"])
        # Should contain column name but not any fabricated text values
        assert "text" in data_str


# ---------------------------------------------------------------------------
# Tool 8: validate_data_schema
# ---------------------------------------------------------------------------
class TestValidateDataSchema:
    def _write_jsonl(self, path: Path, rows: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")

    def test_conforming_file(self, tmp_path):
        f = tmp_path / "data.jsonl"
        self._write_jsonl(f, [{"text": "hello", "label": 1}, {"text": "world", "label": 0}])
        schema = {"columns": [{"name": "text", "dtype": "str"}, {"name": "label", "dtype": "int"}]}
        result = prep.validate_data_schema(file_path=str(f), schema=schema)
        assert result["success"] is True
        assert result["data"]["conforms"] is True
        assert result["data"]["rows_checked"] == 2

    def test_mismatch_detected(self, tmp_path):
        f = tmp_path / "data.jsonl"
        self._write_jsonl(f, [{"text": "hello", "label": "bad_int"}])
        schema = {"columns": [{"name": "text", "dtype": "str"}, {"name": "label", "dtype": "int"}]}
        result = prep.validate_data_schema(file_path=str(f), schema=schema)
        assert result["success"] is True
        assert result["data"]["conforms"] is False
        assert len(result["data"]["mismatches"]) >= 1

    def test_missing_file(self, tmp_path):
        result = prep.validate_data_schema(
            file_path=str(tmp_path / "missing.jsonl"),
            schema={"columns": []},
        )
        assert result["success"] is False

    def test_no_real_values_in_output(self, tmp_path):
        """Values must never appear in the output."""
        f = tmp_path / "data.jsonl"
        secret = "SUPER_SECRET_VALUE_XYZ"
        self._write_jsonl(f, [{"text": secret, "score": 0.99}])
        schema = {
            "columns": [{"name": "text", "dtype": "str"}, {"name": "score", "dtype": "float"}]
        }
        result = prep.validate_data_schema(file_path=str(f), schema=schema)
        assert result["success"] is True
        # The secret value must NOT appear in the returned dict
        result_str = json.dumps(result)
        assert secret not in result_str


# ---------------------------------------------------------------------------
# Tool 9: anonymize_dataset_preview
# ---------------------------------------------------------------------------
class TestAnonymizeDatasetPreview:
    def test_creates_anon_file(self, tmp_path):
        f = tmp_path / "data.jsonl"
        f.write_text(
            json.dumps({"email": "user@example.com", "text": "hello"}) + "\n",
            encoding="utf-8",
        )
        result = prep.anonymize_dataset_preview(file_path=str(f))
        assert result["success"] is True
        data = result["data"]
        assert "anon_path" in data
        assert "masked_count" in data
        assert data["masked_count"] >= 1
        anon = Path(data["anon_path"])
        assert anon.exists()

    def test_no_content_in_output(self, tmp_path):
        """Body of file must not be returned."""
        f = tmp_path / "data.jsonl"
        secret = "BIG_SECRET_EMAIL@corp.internal"
        f.write_text(json.dumps({"email": secret}) + "\n", encoding="utf-8")
        result = prep.anonymize_dataset_preview(file_path=str(f))
        result_str = json.dumps(result)
        assert secret not in result_str

    def test_missing_file(self, tmp_path):
        result = prep.anonymize_dataset_preview(file_path=str(tmp_path / "missing.jsonl"))
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Tool 10: split_dataset_config
# ---------------------------------------------------------------------------
class TestSplitDatasetConfig:
    def test_renders_content(self):
        result = prep.split_dataset_config(ratios={"train": 0.8, "val": 0.1, "test": 0.1})
        assert result["success"] is True
        data = result["data"]
        assert "content" in data
        assert "0.8" in data["content"]
        assert "0.1" in data["content"]

    def test_default_ratios_when_none(self):
        """Passing ratios=None should use default 0.8/0.1/0.1."""
        result = prep.split_dataset_config(ratios=None)
        assert result["success"] is True
        assert result["data"]["ratios"]["train"] == 0.8

    def test_stratify_flag(self):
        result = prep.split_dataset_config(
            ratios={"train": 0.8, "val": 0.1, "test": 0.1}, stratify=True
        )
        assert result["success"] is True
        assert (
            "stratify" in result["data"]["content"].lower() or "label" in result["data"]["content"]
        )

    def test_writes_to_project(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.split_dataset_config(
            ratios={"train": 0.8, "val": 0.1, "test": 0.1},
            project_id="p1",
            store=store,
        )
        assert result["success"] is True
        assert "path" in result["data"]
        p = Path(result["data"]["path"])
        assert p.exists()
        assert p.name == "split.py"

    def test_invalid_ratios(self):
        result = prep.split_dataset_config(ratios={"train": 0.9, "val": 0.1, "test": 0.1})
        assert result["success"] is False


# ---------------------------------------------------------------------------
# Additional coverage: error paths
# ---------------------------------------------------------------------------
class TestErrorPaths:
    def test_requirements_cuda_version_string(self):
        """cuda as a version string triggers the comment line."""
        result = prep.generate_requirements(framework="unsloth", cuda="12.4")
        assert result["success"] is True
        assert "12.4" in result["data"]["content"]

    def test_validate_schema_load_from_project(self, tmp_path):
        """validate_data_schema can load schema from project."""
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        store.update_project(
            "p1",
            data_schema={
                "columns": [{"name": "text", "dtype": "str"}],
                "task_type": "classification",
            },
        )
        f = tmp_path / "data.jsonl"
        f.write_text(json.dumps({"text": "hello"}) + "\n")
        result = prep.validate_data_schema(
            file_path=str(f),
            project_id="p1",
            store=store,
        )
        assert result["success"] is True
        assert result["data"]["conforms"] is True

    def test_validate_schema_invalid_json_line(self, tmp_path):
        """A line with invalid JSON is reported as a mismatch."""
        f = tmp_path / "data.jsonl"
        f.write_text('{"ok": 1}\nnot-json\n{"ok": 3}\n')
        result = prep.validate_data_schema(file_path=str(f), schema={"columns": []})
        assert result["success"] is True
        assert result["data"]["rows_checked"] == 3
        assert any("invalid JSON" in m["issue"] for m in result["data"]["mismatches"])

    def test_validate_schema_empty_line_skipped(self, tmp_path):
        """Empty lines are skipped without increasing rows_checked."""
        f = tmp_path / "data.jsonl"
        f.write_text('{"ok": 1}\n\n{"ok": 2}\n')
        result = prep.validate_data_schema(file_path=str(f), schema={"columns": []})
        assert result["data"]["rows_checked"] == 2

    def test_validate_missing_key_reported(self, tmp_path):
        """A row missing an expected column is reported."""
        f = tmp_path / "data.jsonl"
        f.write_text(json.dumps({"text": "hi"}) + "\n")
        schema = {
            "columns": [{"name": "text", "dtype": "str"}, {"name": "missing_col", "dtype": "int"}]
        }
        result = prep.validate_data_schema(file_path=str(f), schema=schema)
        assert any("missing key" in m["issue"] for m in result["data"]["mismatches"])

    def test_describe_format_invalid_schema(self, tmp_path):
        """Missing required column keys should return fail."""
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        result = prep.describe_expected_data_format(
            project_id="p1",
            columns=[{"name": "only_name"}],  # missing dtype
            task_type="classification",
            store=store,
        )
        assert result["success"] is False

    def test_validate_schema_type_mismatch_no_secret(self, tmp_path):
        """Type-mismatch row: conforms=False AND the wrong-typed secret value is absent."""
        f = tmp_path / "data.jsonl"
        secret = "SUPER_SECRET_VALUE_XYZ"
        # Plant the secret as the value of an int column — wrong type
        f.parent.mkdir(parents=True, exist_ok=True)
        with f.open("w") as fh:
            fh.write(json.dumps({"label": secret}) + "\n")
        schema = {"columns": [{"name": "label", "dtype": "int"}]}
        result = prep.validate_data_schema(file_path=str(f), schema=schema)
        # Should flag the mismatch
        assert result["success"] is True
        assert result["data"]["conforms"] is False
        # The planted secret value must NOT appear in the returned dict
        result_str = json.dumps(result)
        assert secret not in result_str


# ---------------------------------------------------------------------------
# MCP wrappers smoke-test (coverage for lines 507-563)
# ---------------------------------------------------------------------------
class TestMCPWrappers:
    """Test the thin MCP wrappers to ensure they proxy to the real functions."""

    def test_mcp_cache_base_model(self):
        result = prep.cache_base_model(repo_id="x/y", dest="/tmp/x")
        assert result["meta"]["dry_run"] is True

    def test_mcp_generate_requirements_wrapper(self):
        result = prep._mcp_generate_requirements(framework="unsloth")
        assert result["success"] is True

    def test_mcp_create_project_structure_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path))
        result = prep._mcp_create_project_structure(project_id="wraptest", client_name="TestCo")
        assert result["success"] is True

    def test_mcp_validate_data_schema_wrapper(self, tmp_path):
        f = tmp_path / "d.jsonl"
        f.write_text(json.dumps({"x": 1}) + "\n")
        result = prep._mcp_validate_data_schema(file_path=str(f), schema={"columns": []})
        assert result["success"] is True

    def test_mcp_anonymize_wrapper(self, tmp_path):
        f = tmp_path / "d.jsonl"
        f.write_text(json.dumps({"email": "a@b.com"}) + "\n")
        result = prep._mcp_anonymize_dataset_preview(file_path=str(f))
        assert result["success"] is True

    def test_mcp_split_config_wrapper(self):
        result = prep._mcp_split_dataset_config()
        assert result["success"] is True

    def test_mcp_create_training_config_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path))
        # Need a project first
        store = Store(root=tmp_path)
        store.init_project("wtest", "X")
        # workspace must point to tmp_path
        result = prep._mcp_create_training_config(
            project_id="wtest",
            base_model="x/y",
        )
        assert result["success"] is True

    def test_mcp_describe_data_format_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path))
        store = Store(root=tmp_path)
        store.init_project("wtest2", "X")
        result = prep._mcp_describe_expected_data_format(
            project_id="wtest2",
            columns=[{"name": "text", "dtype": "str"}],
            task_type="instruct",
        )
        assert result["success"] is True

    def test_mcp_load_project_template_wrapper(self, tmp_path, monkeypatch):
        monkeypatch.setenv("FTOS_WORKSPACE", str(tmp_path))
        store = Store(root=tmp_path)
        store.init_project("wtest3", "X")
        result = prep._mcp_load_project_template(
            template_name="lora-mistral-v3",
            project_id="wtest3",
        )
        assert result["success"] is True
