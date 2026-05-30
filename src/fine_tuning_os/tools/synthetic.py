# src/fine_tuning_os/tools/synthetic.py
"""Lot 2 — Tool 7: generate_synthetic_dataset (C1, offline, deterministic)."""

from __future__ import annotations

import json
import random
from typing import Any

from ..envelope import fail, ok
from ..render import write_text_atomic
from ..store import Store, workspace_root

# ---------------------------------------------------------------------------
# Value generators by dtype
# ---------------------------------------------------------------------------


def _make_value(col_name: str, dtype: str, rng: random.Random, idx: int) -> Any:
    """Generate a deterministic placeholder value for a column."""
    norm = dtype.lower().strip()
    if norm in ("int", "integer"):
        return rng.randint(0, 999)
    if norm in ("float", "double"):
        return round(rng.uniform(0.0, 1.0), 6)
    if norm in ("bool", "boolean"):
        return rng.choice([True, False])
    # str / string / anything else
    return f"synthetic_{col_name}_{idx:04d}"


# ---------------------------------------------------------------------------
# Tool 7: generate_synthetic_dataset
# ---------------------------------------------------------------------------
def generate_synthetic_dataset(
    project_id: str,
    n: int,
    seed: int,
    schema: dict[str, Any] | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Generate n deterministic synthetic rows matching the data schema.

    n must be in [10, 50]. Uses a seeded RNG so same seed => identical file.
    """
    if not (10 <= n <= 50):
        return fail(f"n must be between 10 and 50 inclusive, got {n}").to_dict()

    s = store if store is not None else Store(root=workspace_root())

    # Resolve schema: inline takes precedence over persisted
    resolved_schema = schema
    if resolved_schema is None:
        try:
            state = s.read_project(project_id)
            resolved_schema = state.get("data_schema")
        except (ValueError, FileNotFoundError) as exc:
            return fail(str(exc)).to_dict()

    if resolved_schema is None:
        return fail(
            "no data_schema found; call describe_expected_data_format first or pass schema inline"
        ).to_dict()

    columns: list[dict[str, str]] = resolved_schema.get("columns", [])

    rng = random.Random(seed)
    rows: list[dict[str, Any]] = []
    for i in range(n):
        row: dict[str, Any] = {}
        for col in columns:
            row[col["name"]] = _make_value(col["name"], col["dtype"], rng, i)
        rows.append(row)

    # Write JSONL
    try:
        dest = s.project_dir(project_id) / "data" / "synthetic" / "dataset.jsonl"
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
    try:
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"path": str(dest), "n": n, "seed": seed}).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrapper without `store` kwarg
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with generate_synthetic_dataset
def _mcp_generate_synthetic_dataset(
    project_id: str,
    n: int,
    seed: int,
    schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return generate_synthetic_dataset(project_id=project_id, n=n, seed=seed, schema=schema)


_MCP_TOOLS = [
    (
        _mcp_generate_synthetic_dataset,
        "Generate n deterministic synthetic rows (10-50) matching the project data schema and write as JSONL.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all synthetic tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
