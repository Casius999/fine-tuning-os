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
