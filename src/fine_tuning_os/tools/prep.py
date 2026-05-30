# src/fine_tuning_os/tools/prep.py
"""Lot 2 — Prep & Synthetic tools 1-6, 8, 9, 10 (C1, offline, deterministic).

All tools are pure module-level functions; register(mcp) wraps them for FastMCP.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jinja2
from pydantic import ValidationError

from ..envelope import fail, ok
from ..models import DataSchema, SplitRatios, TrainingParams
from ..render import write_text_atomic
from ..sanitize import sanitize_text
from ..store import Store, workspace_root
from ..templating import render_template

# ---------------------------------------------------------------------------
# Supported frameworks / valid dtype map
# ---------------------------------------------------------------------------
_VALID_FRAMEWORKS = {"unsloth", "axolotl", "custom"}

# Dtype-to-Python-type mapping for schema validation (best-effort)
_DTYPE_MAP: dict[str, type] = {
    "str": str,
    "string": str,
    "int": int,
    "integer": int,
    "float": float,
    "double": float,
    "bool": bool,
    "boolean": bool,
}


# ---------------------------------------------------------------------------
# Template presets (tool 5)
# ---------------------------------------------------------------------------
_TEMPLATE_PRESETS: dict[str, TrainingParams] = {
    "lora-mistral-v3": TrainingParams(
        base_model="mistralai/Mistral-7B-v0.3",
        framework="unsloth",
        lora_rank=32,
        lr=2e-4,
        batch_size=2,
        epochs=3,
        scheduler="cosine",
        max_seq_len=4096,
    ),
    "lora-llama3-8b": TrainingParams(
        base_model="meta-llama/Meta-Llama-3-8B",
        framework="unsloth",
        lora_rank=16,
        lr=2e-4,
        batch_size=2,
        epochs=2,
        scheduler="cosine",
        max_seq_len=4096,
    ),
    "axolotl-llama3": TrainingParams(
        base_model="meta-llama/Meta-Llama-3-8B",
        framework="axolotl",
        lora_rank=16,
        lr=1e-4,
        batch_size=4,
        epochs=2,
        scheduler="cosine",
        max_seq_len=2048,
    ),
    "qlora-mistral-chat": TrainingParams(
        base_model="mistralai/Mistral-7B-Instruct-v0.3",
        framework="unsloth",
        lora_rank=64,
        lr=1e-4,
        batch_size=2,
        epochs=1,
        scheduler="cosine",
        max_seq_len=8192,
    ),
}


# ---------------------------------------------------------------------------
# Helper: resolve store
# ---------------------------------------------------------------------------
def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


# ---------------------------------------------------------------------------
# Tool 1: create_training_config
# ---------------------------------------------------------------------------
def create_training_config(
    project_id: str,
    base_model: str,
    framework: str = "unsloth",
    lora_rank: int = 16,
    lr: float = 2e-4,
    batch_size: int = 2,
    epochs: int = 1,
    scheduler: str = "cosine",
    max_seq_len: int = 2048,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render a training config YAML from template and write to project config/."""
    if framework not in _VALID_FRAMEWORKS:
        return fail(
            f"unknown framework: {framework!r}; valid: {sorted(_VALID_FRAMEWORKS)}"
        ).to_dict()
    try:
        params = TrainingParams(
            base_model=base_model,
            framework=framework,
            lora_rank=lora_rank,
            lr=lr,
            batch_size=batch_size,
            epochs=epochs,
            scheduler=scheduler,
            max_seq_len=max_seq_len,
        )
    except ValidationError as exc:
        return fail(str(exc)).to_dict()

    try:
        content = render_template(
            f"configs/{framework}.yaml.j2",
            base_model=params.base_model,
            framework=params.framework,
            lora_rank=params.lora_rank,
            lr=params.lr,
            batch_size=params.batch_size,
            epochs=params.epochs,
            scheduler=params.scheduler,
            max_seq_len=params.max_seq_len,
        )
    except jinja2.TemplateError as exc:
        return fail(f"template error: {exc}").to_dict()

    s = _get_store(store)
    try:
        dest = s.project_dir(project_id) / "config" / "training.yaml"
        write_text_atomic(dest, content)
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"path": str(dest), "framework": framework, "content": content}).to_dict()


# ---------------------------------------------------------------------------
# Tool 2: cache_base_model (C2 dry_run — never executes)
# ---------------------------------------------------------------------------
def cache_base_model(
    repo_id: str,
    dest: str,
    revision: str = "main",
) -> dict[str, Any]:
    """Emit the huggingface-cli download command (dry_run only, no network)."""
    cmd = f"huggingface-cli download {repo_id} --revision {revision} --local-dir {dest}"
    return ok(
        {
            "command": cmd,
            "repo_id": repo_id,
            "revision": revision,
            "dest": dest,
            "verify": "compare sha256 after download",
        },
        executed=False,
        dry_run=True,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 3: generate_requirements
# ---------------------------------------------------------------------------
_BASE_REQUIREMENTS: dict[str, list[str]] = {
    "unsloth": [
        "unsloth>=2024.11",
        "peft>=0.13.0",
        "trl>=0.13.0",
        "transformers>=4.46.0",
        "accelerate>=1.1.0",
        "datasets>=3.1.0",
        "bitsandbytes>=0.44.0",
        "torch>=2.4.0",
    ],
    "axolotl": [
        "axolotl>=0.7.0",
        "peft>=0.13.0",
        "trl>=0.13.0",
        "transformers>=4.46.0",
        "accelerate>=1.1.0",
        "datasets>=3.1.0",
        "bitsandbytes>=0.44.0",
        "torch>=2.4.0",
    ],
    "custom": [
        "peft>=0.13.0",
        "trl>=0.13.0",
        "transformers>=4.46.0",
        "accelerate>=1.1.0",
        "datasets>=3.1.0",
        "bitsandbytes>=0.44.0",
        "torch>=2.4.0",
    ],
}


def generate_requirements(
    framework: str = "unsloth",
    cuda: bool | str = True,
    extras: list[str] | None = None,
    project_id: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Generate a versioned requirements.txt for the given framework."""
    base = list(_BASE_REQUIREMENTS.get(framework, _BASE_REQUIREMENTS["custom"]))
    if extras:
        for pkg in extras:
            if pkg not in base and not any(pkg in line for line in base):
                base.append(pkg)
    if cuda and cuda is not True:
        base.append(f"# CUDA {cuda} — ensure matching torch build")
    content = "\n".join(base) + "\n"

    result_data: dict[str, Any] = {"content": content}
    if project_id is not None:
        s = _get_store(store)
        try:
            dest = s.project_dir(project_id) / "requirements.txt"
            write_text_atomic(dest, content)
            result_data["path"] = str(dest)
        except ValueError as exc:
            return fail(str(exc)).to_dict()

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# Tool 4: create_project_structure
# ---------------------------------------------------------------------------
def create_project_structure(
    project_id: str,
    client_name: str,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Initialise project directory tree via Store.init_project."""
    s = _get_store(store)
    try:
        state = s.init_project(project_id, client_name)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    pdir = s.project_dir(project_id)
    created_dirs = [
        str(pdir / sub)
        for sub in (
            "config",
            "data/synthetic",
            "src",
            "docker",
            "outputs",
            "reports",
            "deliverables",
            "docs",
        )
    ]
    return ok({"project_id": state["project_id"], "created_dirs": created_dirs}).to_dict()


# ---------------------------------------------------------------------------
# Tool 5: load_project_template
# ---------------------------------------------------------------------------
def load_project_template(
    template_name: str,
    project_id: str,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Instantiate a preset template: render config + requirements for the project."""
    params = _TEMPLATE_PRESETS.get(template_name)
    if params is None:
        return fail(
            f"unknown template: {template_name!r}; available: {sorted(_TEMPLATE_PRESETS)}"
        ).to_dict()

    files: list[str] = []
    s = _get_store(store)

    cfg_result = create_training_config(
        project_id=project_id,
        base_model=params.base_model,
        framework=params.framework,
        lora_rank=params.lora_rank,
        lr=params.lr,
        batch_size=params.batch_size,
        epochs=params.epochs,
        scheduler=params.scheduler,
        max_seq_len=params.max_seq_len,
        store=s,
    )
    if not cfg_result["success"]:
        return cfg_result

    files.append(cfg_result["data"]["path"])

    req_result = generate_requirements(
        framework=params.framework,
        project_id=project_id,
        store=s,
    )
    if not req_result["success"]:
        return req_result

    if "path" in req_result["data"]:
        files.append(req_result["data"]["path"])

    return ok({"template_name": template_name, "files": files}).to_dict()


# ---------------------------------------------------------------------------
# Tool 6: describe_expected_data_format
# ---------------------------------------------------------------------------
def describe_expected_data_format(
    project_id: str,
    columns: list[dict[str, str]],
    task_type: str,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Validate and persist the abstract data schema. No real content."""
    try:
        schema = DataSchema(
            columns=[{"name": c["name"], "dtype": c["dtype"]} for c in columns],
            task_type=task_type,
        )
    except (ValidationError, KeyError) as exc:
        return fail(f"invalid schema: {exc}").to_dict()

    schema_dict = schema.model_dump()
    s = _get_store(store)
    try:
        s.update_project(project_id, data_schema=schema_dict)
    except (ValueError, FileNotFoundError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"project_id": project_id, "schema": schema_dict}).to_dict()


# ---------------------------------------------------------------------------
# Tool 8: validate_data_schema
# ---------------------------------------------------------------------------
def validate_data_schema(
    file_path: str,
    schema: dict[str, Any] | None = None,
    project_id: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Check JSONL file against schema. Returns keys/types/lengths ONLY — no values."""
    fp = Path(file_path)
    if not fp.exists():
        return fail(f"file not found: {file_path}").to_dict()

    # Resolve schema
    resolved_schema = schema
    if resolved_schema is None and project_id is not None:
        try:
            s = _get_store(store)
            state = s.read_project(project_id)
            resolved_schema = state.get("data_schema")
        except (ValueError, FileNotFoundError) as exc:
            return fail(str(exc)).to_dict()

    columns: list[dict[str, str]] = []
    if resolved_schema and "columns" in resolved_schema:
        columns = resolved_schema["columns"]

    col_types = {c["name"]: _DTYPE_MAP.get(c["dtype"], str) for c in columns}

    mismatches: list[dict[str, Any]] = []
    rows_checked = 0

    with fp.open(encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                mismatches.append({"line": lineno, "issue": f"invalid JSON: {exc}"})
                rows_checked += 1
                continue

            rows_checked += 1
            for col_name, expected_type in col_types.items():
                if col_name not in row:
                    mismatches.append({"line": lineno, "issue": f"missing key: {col_name!r}"})
                else:
                    val = row[col_name]
                    if not isinstance(val, expected_type):
                        # Report type mismatch WITHOUT the value
                        actual_type = type(val).__name__
                        mismatches.append(
                            {
                                "line": lineno,
                                "issue": f"key {col_name!r}: expected {expected_type.__name__}, got {actual_type}",
                            }
                        )

    conforms = len(mismatches) == 0
    return ok(
        {
            "conforms": conforms,
            "rows_checked": rows_checked,
            "mismatches": mismatches,
            "columns_checked": len(col_types),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 9: anonymize_dataset_preview
# ---------------------------------------------------------------------------
def anonymize_dataset_preview(file_path: str) -> dict[str, Any]:
    """Sanitize a dataset file via sanitize_text and write .anon copy.

    Returns only masked_count and anon_path — never the file body.
    """
    fp = Path(file_path)
    if not fp.exists():
        return fail(f"file not found: {file_path}").to_dict()

    try:
        raw = fp.read_text(encoding="utf-8")
        masked_text, masked_count = sanitize_text(raw)
        anon_path = fp.with_suffix(fp.suffix + ".anon")
        write_text_atomic(anon_path, masked_text)
    except (OSError, UnicodeDecodeError) as exc:
        return fail(str(exc)).to_dict()

    return ok({"anon_path": str(anon_path), "masked_count": masked_count}).to_dict()


# ---------------------------------------------------------------------------
# Tool 10: split_dataset_config
# ---------------------------------------------------------------------------
def split_dataset_config(
    ratios: dict[str, float] | None = None,
    seed: int = 42,
    stratify: bool = False,
    project_id: str | None = None,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render a seeded train/val/test split Python script via template."""
    if ratios is None:
        ratios = {"train": 0.8, "val": 0.1, "test": 0.1}

    try:
        split = SplitRatios(
            train=ratios.get("train", 0.8),
            val=ratios.get("val", 0.1),
            test=ratios.get("test", 0.1),
        )
    except ValidationError as exc:
        return fail(f"invalid ratios: {exc}").to_dict()

    try:
        content = render_template(
            "train/split.py.j2",
            train=split.train,
            val=split.val,
            test=split.test,
            seed=seed,
            stratify=stratify,
        )
    except jinja2.TemplateError as exc:
        return fail(f"template error: {exc}").to_dict()

    result_data: dict[str, Any] = {
        "content": content,
        "ratios": {"train": split.train, "val": split.val, "test": split.test},
    }

    if project_id is not None:
        s = _get_store(store)
        try:
            dest = s.project_dir(project_id) / "src" / "split.py"
            write_text_atomic(dest, content)
            result_data["path"] = str(dest)
        except ValueError as exc:
            return fail(str(exc)).to_dict()

    return ok(result_data).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------
# FastMCP uses Pydantic to build JSON schemas for parameters.
# Store is not JSON-serialisable, so it must be excluded from tool signatures.
# These wrappers call the underlying functions with store=None (default workspace).


# MCP wrapper — keep signature in sync with create_training_config
def _mcp_create_training_config(
    project_id: str,
    base_model: str,
    framework: str = "unsloth",
    lora_rank: int = 16,
    lr: float = 2e-4,
    batch_size: int = 2,
    epochs: int = 1,
    scheduler: str = "cosine",
    max_seq_len: int = 2048,
) -> dict[str, Any]:
    return create_training_config(
        project_id=project_id,
        base_model=base_model,
        framework=framework,
        lora_rank=lora_rank,
        lr=lr,
        batch_size=batch_size,
        epochs=epochs,
        scheduler=scheduler,
        max_seq_len=max_seq_len,
    )


# MCP wrapper — keep signature in sync with generate_requirements
def _mcp_generate_requirements(
    framework: str = "unsloth",
    cuda: bool | str = True,
    extras: list[str] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    return generate_requirements(
        framework=framework, cuda=cuda, extras=extras, project_id=project_id
    )


# MCP wrapper — keep signature in sync with create_project_structure
def _mcp_create_project_structure(project_id: str, client_name: str) -> dict[str, Any]:
    return create_project_structure(project_id=project_id, client_name=client_name)


# MCP wrapper — keep signature in sync with load_project_template
def _mcp_load_project_template(template_name: str, project_id: str) -> dict[str, Any]:
    return load_project_template(template_name=template_name, project_id=project_id)


# MCP wrapper — keep signature in sync with describe_expected_data_format
def _mcp_describe_expected_data_format(
    project_id: str,
    columns: list[dict[str, str]],
    task_type: str,
) -> dict[str, Any]:
    return describe_expected_data_format(
        project_id=project_id, columns=columns, task_type=task_type
    )


# MCP wrapper — keep signature in sync with validate_data_schema
def _mcp_validate_data_schema(
    file_path: str,
    schema: dict[str, Any] | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    return validate_data_schema(file_path=file_path, schema=schema, project_id=project_id)


# MCP wrapper — keep signature in sync with anonymize_dataset_preview
def _mcp_anonymize_dataset_preview(file_path: str) -> dict[str, Any]:
    return anonymize_dataset_preview(file_path=file_path)


# MCP wrapper — keep signature in sync with split_dataset_config
def _mcp_split_dataset_config(
    ratios: dict[str, float] | None = None,
    seed: int = 42,
    stratify: bool = False,
    project_id: str | None = None,
) -> dict[str, Any]:
    return split_dataset_config(ratios=ratios, seed=seed, stratify=stratify, project_id=project_id)


_MCP_TOOLS = [
    (
        _mcp_create_training_config,
        "Render a LoRA training config YAML and write it to the project config/ directory.",
    ),
    (
        cache_base_model,
        "Emit the huggingface-cli download command for a base model (dry_run — no network).",
    ),
    (
        _mcp_generate_requirements,
        "Generate a pinned requirements.txt for the given fine-tuning framework.",
    ),
    (
        _mcp_create_project_structure,
        "Initialise the project directory tree and project.json in the workspace.",
    ),
    (
        _mcp_load_project_template,
        "Apply a named template preset (config + requirements) to a project.",
    ),
    (
        _mcp_describe_expected_data_format,
        "Validate and persist an abstract data schema (no real content).",
    ),
    (
        _mcp_validate_data_schema,
        "Check a JSONL file against a schema — returns keys/types/lengths only, never values.",
    ),
    (
        _mcp_anonymize_dataset_preview,
        "Sanitize a dataset file via pattern-based masking and write an .anon copy.",
    ),
    (
        _mcp_split_dataset_config,
        "Render a seeded train/val/test split Python script from template.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all prep tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
