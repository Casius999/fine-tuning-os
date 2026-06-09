# SPDX-License-Identifier: Apache-2.0
# tests/test_synthetic.py
"""Tests for synthetic.py tools (tool 7: generate_synthetic_dataset)."""

from __future__ import annotations

import json
from pathlib import Path


from fine_tuning_os.store import Store
from fine_tuning_os.tools import synthetic


# ---------------------------------------------------------------------------
# Tool 7: generate_synthetic_dataset
# ---------------------------------------------------------------------------
class TestGenerateSyntheticDataset:
    def _setup_project(self, tmp_path: Path, columns=None) -> tuple[Store, str]:
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        if columns is None:
            columns = [
                {"name": "text", "dtype": "str"},
                {"name": "label", "dtype": "int"},
                {"name": "score", "dtype": "float"},
            ]
        store.update_project(
            "p1",
            data_schema={
                "columns": columns,
                "task_type": "classification",
            },
        )
        return store, "p1"

    def test_generates_n_rows(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        result = synthetic.generate_synthetic_dataset(project_id=pid, n=10, seed=42, store=store)
        assert result["success"] is True
        data = result["data"]
        assert data["n"] == 10
        p = Path(data["path"])
        assert p.exists()
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        assert len(rows) == 10

    def test_deterministic_same_seed(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        r1 = synthetic.generate_synthetic_dataset(project_id=pid, n=15, seed=99, store=store)
        r2 = synthetic.generate_synthetic_dataset(project_id=pid, n=15, seed=99, store=store)
        p1 = Path(r1["data"]["path"])
        p2 = Path(r2["data"]["path"])
        assert p1.read_text() == p2.read_text()

    def test_different_seeds_differ(self, tmp_path):
        # Use two separate projects so different seeds write to separate files
        store = Store(root=tmp_path)
        store.init_project("proj_a", "X")
        store.init_project("proj_b", "X")
        cols = [{"name": "text", "dtype": "str"}, {"name": "label", "dtype": "int"}]
        schema = {"columns": cols, "task_type": "cls"}
        store.update_project("proj_a", data_schema=schema)
        store.update_project("proj_b", data_schema=schema)

        r1 = synthetic.generate_synthetic_dataset(project_id="proj_a", n=20, seed=1, store=store)
        r2 = synthetic.generate_synthetic_dataset(project_id="proj_b", n=20, seed=2, store=store)
        p1 = Path(r1["data"]["path"])
        p2 = Path(r2["data"]["path"])
        assert p1.read_text() != p2.read_text()

    def test_n_too_small(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        result = synthetic.generate_synthetic_dataset(project_id=pid, n=5, seed=42, store=store)
        assert result["success"] is False

    def test_n_too_large(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        result = synthetic.generate_synthetic_dataset(project_id=pid, n=51, seed=42, store=store)
        assert result["success"] is False

    def test_row_has_expected_keys(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        result = synthetic.generate_synthetic_dataset(project_id=pid, n=10, seed=42, store=store)
        p = Path(result["data"]["path"])
        row = json.loads(p.read_text().splitlines()[0])
        assert "text" in row
        assert "label" in row
        assert "score" in row

    def test_inline_schema(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        # No persisted schema — pass inline
        inline_schema = {
            "columns": [{"name": "prompt", "dtype": "str"}, {"name": "response", "dtype": "str"}],
            "task_type": "chat",
        }
        result = synthetic.generate_synthetic_dataset(
            project_id="p1",
            n=10,
            seed=7,
            schema=inline_schema,
            store=store,
        )
        assert result["success"] is True
        p = Path(result["data"]["path"])
        row = json.loads(p.read_text().splitlines()[0])
        assert "prompt" in row
        assert "response" in row

    def test_no_project_no_schema_fails(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        # No persisted schema, no inline schema
        result = synthetic.generate_synthetic_dataset(project_id="p1", n=10, seed=1, store=store)
        assert result["success"] is False

    def test_output_path_is_in_project(self, tmp_path):
        store, pid = self._setup_project(tmp_path)
        result = synthetic.generate_synthetic_dataset(project_id=pid, n=10, seed=42, store=store)
        p = Path(result["data"]["path"])
        # Must be under the project's data/synthetic dir
        assert "synthetic" in str(p)

    def test_dtype_int_generates_int(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        store.update_project(
            "p1",
            data_schema={
                "columns": [{"name": "count", "dtype": "int"}],
                "task_type": "regression",
            },
        )
        result = synthetic.generate_synthetic_dataset(project_id="p1", n=10, seed=1, store=store)
        p = Path(result["data"]["path"])
        row = json.loads(p.read_text().splitlines()[0])
        assert isinstance(row["count"], int)

    def test_dtype_float_generates_float(self, tmp_path):
        store = Store(root=tmp_path)
        store.init_project("p1", "ACME")
        store.update_project(
            "p1",
            data_schema={
                "columns": [{"name": "score", "dtype": "float"}],
                "task_type": "regression",
            },
        )
        result = synthetic.generate_synthetic_dataset(project_id="p1", n=10, seed=1, store=store)
        p = Path(result["data"]["path"])
        row = json.loads(p.read_text().splitlines()[0])
        assert isinstance(row["score"], float)


# ---------------------------------------------------------------------------
# MCP wrapper tests (Fix 7)
# ---------------------------------------------------------------------------
class TestMCPWrapper:
    def test_mcp_wrapper_nominal(self, tmp_path):
        """_mcp_generate_synthetic_dataset nominal path via inline schema."""
        store = Store(root=tmp_path)
        store.init_project("mcp1", "ACME")
        inline_schema = {
            "columns": [{"name": "text", "dtype": "str"}, {"name": "score", "dtype": "float"}],
            "task_type": "regression",
        }
        # We can't pass store through the MCP wrapper, so set up the project with a schema
        # and use monkeypatch approach — instead, test via generate_synthetic_dataset directly
        # but call the wrapper with inline schema (which bypasses the store lookup).
        # The wrapper signature matches the underlying function except `store`.
        # Use monkeypatch to point workspace to tmp_path.
        import os

        old_env = os.environ.get("FTOS_WORKSPACE")
        os.environ["FTOS_WORKSPACE"] = str(tmp_path)
        try:
            store.init_project("mcp1", "ACME")  # already inited, will be a no-op or update
            result = synthetic._mcp_generate_synthetic_dataset(
                project_id="mcp1",
                n=10,
                seed=42,
                schema=inline_schema,
            )
        finally:
            if old_env is None:
                os.environ.pop("FTOS_WORKSPACE", None)
            else:
                os.environ["FTOS_WORKSPACE"] = old_env

        assert result["success"] is True
        assert result["data"]["n"] == 10

    def test_mcp_wrapper_no_schema_error(self, tmp_path):
        """project_id with no persisted schema and no inline schema returns success=False."""
        import os

        old_env = os.environ.get("FTOS_WORKSPACE")
        os.environ["FTOS_WORKSPACE"] = str(tmp_path)
        try:
            store = Store(root=tmp_path)
            store.init_project("mcp_noschema", "ACME")
            # No schema persisted, no inline schema passed
            result = synthetic._mcp_generate_synthetic_dataset(
                project_id="mcp_noschema",
                n=10,
                seed=1,
                schema=None,
            )
        finally:
            if old_env is None:
                os.environ.pop("FTOS_WORKSPACE", None)
            else:
                os.environ["FTOS_WORKSPACE"] = old_env

        assert result["success"] is False
        assert (
            "data_schema" in result["error"].lower() or "no data_schema" in result["error"].lower()
        )
