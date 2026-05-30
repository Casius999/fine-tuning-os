# src/fine_tuning_os/tools/pipeline.py
"""Lot 3 — Pipeline tools 11-17.

Gating policy for local execution (tools 11, 12, 13):
- Docker tools (11, 12) require BOTH `local_python` env (`FTOS_LOCAL_PYTHON`)
  AND `shutil.which("docker")` to be present. This two-gate design ensures:
  (a) the operator has explicitly opted in via FTOS_LOCAL_PYTHON, and
  (b) docker is actually installed before attempting a build/test.
  Without both conditions, the tool returns a dry-run with the exact command.
- Local train (13) requires only `local_python` opt-in (no docker needed).
  The generated `train.py` is run via the configured python path from
  `_get_target_config("local_python")`, with a capped subprocess timeout.

All text returned from external processes MUST pass through `sanitize_text`.
No exceptions are propagated to the caller — I/O errors return fail(...).
"""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import jinja2

from ..envelope import fail, ok
from ..render import write_text_atomic
from ..sanitize import sanitize_text
from ..store import Store, workspace_root
from ..targets import _get_target_config, gate
from ..templating import render_template

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


def _is_docker_locally_allowed() -> bool:
    """Return True iff local_python is opted in AND docker binary exists."""
    configured, _ = gate("local_python")
    return configured and shutil.which("docker") is not None


def _render_and_write(template_rel: str, dest_path: Path, **ctx: Any) -> str | None:
    """Render *template_rel* with **ctx and write atomically to *dest_path*.

    Returns an error string on failure, or None on success.
    """
    try:
        content = render_template(template_rel, **ctx)
    except jinja2.TemplateError as exc:
        return f"template error: {exc}"
    try:
        write_text_atomic(dest_path, content)
    except OSError as exc:
        return str(exc)
    return None


def _run_subprocess_live(
    cmd: list[str],
    timeout: int,
) -> tuple[str | None, dict[str, Any]]:
    """Run *cmd* (list form) and return (error_str, result_data).

    On success error_str is None; on failure result_data is {}.
    """
    try:
        proc = subprocess.run(
            cmd,
            shell=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        raw = proc.stdout + proc.stderr
        sanitized, n = sanitize_text(raw)
        return None, {"output": sanitized, "masked_count": n, "returncode": proc.returncode}
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        FileNotFoundError,
        OSError,
    ) as exc:
        return str(exc), {}


# ---------------------------------------------------------------------------
# Tool 11: build_docker_image (C2 — local_python + docker)
# ---------------------------------------------------------------------------


def build_docker_image(
    project_id: str,
    base_image: str,
    tag: str,
    cache_models: bool = False,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render Dockerfile.train and emit/execute docker build command.

    Gate: local_python opt-in AND docker binary present.
    """
    s = _get_store(store)
    try:
        pdir = s.project_dir(project_id)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    dockerfile_path = pdir / "docker" / "Dockerfile.train"
    err = _render_and_write(
        "docker/Dockerfile.train.j2",
        dockerfile_path,
        project_id=project_id,
        base_image=base_image,
        cache_models=cache_models,
    )
    if err:
        return fail(err).to_dict()

    context = str(pdir)
    # Display command (readable, never executed via shell)
    command = f"docker build -t {tag} -f {dockerfile_path} {context}"

    allowed = _is_docker_locally_allowed()
    if not allowed:
        return ok(
            {"dockerfile_path": str(dockerfile_path), "command": command},
            executed=False,
            dry_run=True,
        ).to_dict()

    # Fix #2: list form — no shell=True, prevents command injection
    live_cmd = ["docker", "build", "-t", tag, "-f", str(dockerfile_path), context]
    error, result_data = _run_subprocess_live(live_cmd, timeout=300)
    if error:
        return fail(error).to_dict()

    return ok(
        {
            "dockerfile_path": str(dockerfile_path),
            "command": command,
            **result_data,
        },
        executed=True,
        dry_run=False,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 12: test_docker_build (C2 — local_python + docker)
# ---------------------------------------------------------------------------


def test_docker_build(image_tag: str) -> dict[str, Any]:
    """Run docker build + internal pytest for the image.

    Gate: local_python opt-in AND docker binary present.
    """
    command = f"docker run --rm {image_tag} pytest"

    allowed = _is_docker_locally_allowed()
    if not allowed:
        return ok({"command": command}, executed=False, dry_run=True).to_dict()

    # Fix #2: list form — no shell=True, prevents command injection
    live_cmd = ["docker", "run", "--rm", image_tag, "pytest"]
    error, result_data = _run_subprocess_live(live_cmd, timeout=120)
    if error:
        return fail(error).to_dict()

    return ok(
        {
            "command": command,
            **result_data,
            "passed": result_data.get("returncode") == 0,
        },
        executed=True,
        dry_run=False,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 13: run_local_synthetic_train (C2 — local_python)
# ---------------------------------------------------------------------------


def run_local_synthetic_train(
    project_id: str,
    steps: int = 10,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Render train.py and optionally execute it under the configured python.

    Gate: FTOS_LOCAL_PYTHON must be set (no docker needed).
    """
    s = _get_store(store)
    try:
        pdir = s.project_dir(project_id)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    train_path = pdir / "src" / "train.py"
    err = _render_and_write(
        "train/train.py.j2",
        train_path,
        project_id=project_id,
        steps=steps,
    )
    if err:
        return fail(err).to_dict()

    configured, meta = gate("local_python")
    cfg = _get_target_config("local_python") if configured else None
    python_bin = cfg["FTOS_LOCAL_PYTHON"] if cfg else "python3"
    command = f"{python_bin} {train_path} --steps {steps} --project-root {pdir}"

    if not configured:
        return ok(
            {"command": command, "train_path": str(train_path)},
            executed=False,
            dry_run=True,
        ).to_dict()

    # Live branch — already uses list form (was correct before)
    live_cmd = [python_bin, str(train_path), "--steps", str(steps), "--project-root", str(pdir)]
    error, result_data = _run_subprocess_live(live_cmd, timeout=120)
    if error:
        return fail(error).to_dict()

    return ok(
        {
            "command": command,
            "train_path": str(train_path),
            **result_data,
        },
        executed=True,
        dry_run=False,
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 14: get_local_metrics (C1)
# ---------------------------------------------------------------------------


def get_local_metrics(
    project_id: str,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Parse metrics from the last synthetic run (outputs/metrics.json)."""
    s = _get_store(store)
    try:
        pdir = s.project_dir(project_id)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    metrics_path = pdir / "outputs" / "metrics.json"
    if not metrics_path.exists():
        return fail(f"metrics file not found: {metrics_path}").to_dict()

    try:
        data = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return fail(f"failed to read metrics: {exc}").to_dict()

    return ok(data).to_dict()


# ---------------------------------------------------------------------------
# Tool 15: dry_run_remote_config (C1)
# ---------------------------------------------------------------------------


def dry_run_remote_config(deployment_spec: dict[str, Any]) -> dict[str, Any]:
    """Check presence (not values) of env var names in a deployment spec.

    Only names are checked — secret values are NEVER read into output.
    """
    env_names: list[str] = deployment_spec.get("env_names", [])
    present = [name for name in env_names if os.environ.get(name)]
    missing = [name for name in env_names if not os.environ.get(name)]
    return ok({"ok": present, "missing": missing}).to_dict()


# ---------------------------------------------------------------------------
# Tool 16: optimize_hyperparams (C1)
# ---------------------------------------------------------------------------

_PLATEAU_THRESHOLD = 0.005  # max delta below which we consider a plateau
_PLATEAU_WINDOW = 10  # steps to look back


def optimize_hyperparams(metrics: dict[str, Any]) -> dict[str, Any]:
    """Suggest hyperparameter adjustments from local metrics.

    Heuristics:
    - NaN loss → flag divergence, suggest lr reduction + grad clipping
    - Plateau (loss std < threshold over last N steps) → suggest lr/rank changes
    - Fast convergence → suggest increasing rank or grad_accum
    """
    history: list[dict[str, Any]] = metrics.get("step_history", [])
    final_loss: float = metrics.get("final_loss", float("nan"))

    proposed: dict[str, Any] = {}
    justifications: list[str] = []

    # NaN / Inf check
    if math.isnan(final_loss) or math.isinf(final_loss):
        justifications.append("NaN/Inf loss detected — likely divergence or data issue")
        proposed["lr"] = 1e-5
        proposed["gradient_clipping"] = 1.0
        return ok({"proposed_config": proposed, "justifications": justifications}).to_dict()

    # Plateau check on last PLATEAU_WINDOW steps
    losses = [s.get("loss", float("nan")) for s in history[-_PLATEAU_WINDOW:] if "loss" in s]
    if len(losses) >= _PLATEAU_WINDOW:
        valid = [v for v in losses if not math.isnan(v)]
        if valid:
            loss_range = max(valid) - min(valid)
            if loss_range < _PLATEAU_THRESHOLD:
                justifications.append(
                    f"Loss plateau detected (range={loss_range:.5f} over {len(valid)} steps);"
                    " try reducing lr or increasing lora_rank/grad_accum"
                )
                proposed["lr"] = 5e-5
                proposed["lora_rank"] = 32
                proposed["gradient_accumulation_steps"] = 8

    # Rapid convergence — room to increase capacity
    if len(history) >= 2 and not math.isnan(final_loss) and final_loss < 0.3:
        justifications.append(
            f"Low final loss ({final_loss:.4f}); consider increasing lora_rank for more capacity"
        )
        proposed.setdefault("lora_rank", 64)

    if not justifications:
        justifications.append("Metrics look healthy; no critical adjustments needed")

    return ok({"proposed_config": proposed, "justifications": justifications}).to_dict()


# ---------------------------------------------------------------------------
# Tool 17: generate_unit_tests (C1)
# ---------------------------------------------------------------------------

_TEST_TEMPLATE = """\
# tests/test_{target}.py
# Auto-generated by Fine-Tuning OS — edit to fit your training script.
\"\"\"Unit tests for {target} functions.\"\"\"
from __future__ import annotations
import pytest


class Test{Title}:
    def test_nominal_{target}(self) -> None:
        \"\"\"Nominal path: {target} runs without error.\"\"\"
        # TODO: import and call {target}()
        pass

    def test_{target}_handles_empty_input(self) -> None:
        \"\"\"Edge case: empty/missing input raises or returns gracefully.\"\"\"
        # TODO: assert appropriate error handling
        pass

    def test_{target}_output_structure(self) -> None:
        \"\"\"Output must include expected keys/types.\"\"\"
        # TODO: assert output schema
        pass
"""


def generate_unit_tests(
    project_id: str,
    targets: list[str],
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Produce pytest unit-test stubs for critical training-script functions."""
    if not targets:
        return fail("targets list must not be empty").to_dict()

    s = _get_store(store)
    try:
        pdir = s.project_dir(project_id)
    except ValueError as exc:
        return fail(str(exc)).to_dict()

    tests_dir = pdir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)

    file_paths: list[str] = []
    for target in targets:
        safe = target.replace(" ", "_").lower()
        content = _TEST_TEMPLATE.format(target=safe, Title=safe.title().replace("_", ""))
        dest = tests_dir / f"test_{safe}.py"
        try:
            write_text_atomic(dest, content)
        except OSError as exc:
            return fail(str(exc)).to_dict()
        file_paths.append(str(dest))

    return ok({"file_paths": file_paths}).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without `store` kwarg
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with build_docker_image
def _mcp_build_docker_image(
    project_id: str,
    base_image: str,
    tag: str,
    cache_models: bool = False,
) -> dict[str, Any]:
    return build_docker_image(
        project_id=project_id, base_image=base_image, tag=tag, cache_models=cache_models
    )


# MCP wrapper — keep signature in sync with run_local_synthetic_train
def _mcp_run_local_synthetic_train(
    project_id: str,
    steps: int = 10,
) -> dict[str, Any]:
    return run_local_synthetic_train(project_id=project_id, steps=steps)


# MCP wrapper — keep signature in sync with get_local_metrics
def _mcp_get_local_metrics(project_id: str) -> dict[str, Any]:
    return get_local_metrics(project_id=project_id)


# MCP wrapper — keep signature in sync with generate_unit_tests
def _mcp_generate_unit_tests(
    project_id: str,
    targets: list[str],
) -> dict[str, Any]:
    return generate_unit_tests(project_id=project_id, targets=targets)


_MCP_TOOLS = [
    (
        _mcp_build_docker_image,
        "Render Dockerfile.train and emit/execute docker build command (dry-run unless local_python+docker configured).",
    ),
    (
        test_docker_build,
        "Run docker build + internal pytest tests for an image (dry-run unless local_python+docker configured).",
    ),
    (
        _mcp_run_local_synthetic_train,
        "Render train.py and optionally run a micro-train loop (dry-run unless FTOS_LOCAL_PYTHON set).",
    ),
    (
        _mcp_get_local_metrics,
        "Parse metrics from the last synthetic run (outputs/metrics.json).",
    ),
    (
        dry_run_remote_config,
        "Check which deployment env vars are present/missing (names only — never secret values).",
    ),
    (
        optimize_hyperparams,
        "Suggest hyperparameter adjustments from local training metrics.",
    ),
    (
        _mcp_generate_unit_tests,
        "Generate pytest unit-test stubs for critical training-script functions.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all pipeline tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
