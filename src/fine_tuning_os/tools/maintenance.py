# src/fine_tuning_os/tools/maintenance.py
"""Lot 6 — Model maintenance tools 61-64.

C1 tools (61, 62, 63): pure, deterministic, no network.
C2 tool (64 mcp_self_update — git_remote): subprocess git pull.

C2 contract:
  configured, meta = gate("git_remote")
  command = <exact git command list>   # ALWAYS computed
  not configured → ok({command:..., ...}, **meta)  # dry_run, no subprocess
  configured → subprocess.run(list, shell=False, timeout), sanitize output,
               never put secret VALUES in output (only env NAME refs).

Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import subprocess
from typing import Any

from ..envelope import fail, ok
from ..sanitize import sanitize_text
from ..store import Store, workspace_root
from ..targets import _get_target_config, gate

# Metrics where a *higher* value indicates degradation (lower-is-better)
_LOWER_IS_BETTER_METRICS = frozenset({"perplexity", "loss", "wer", "cer"})

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_store(store: Store | None) -> Store:
    return store if store is not None else Store(root=workspace_root())


# ---------------------------------------------------------------------------
# Tool 61: check_model_rot (C1)
# ---------------------------------------------------------------------------


def check_model_rot(
    metric_history: list[dict[str, Any]],
    metric_key: str,
    threshold: float = 0.05,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    """Detect performance drift in a time-ordered metric history.

    Computes relative degradation between the first and last valid entries.
    drift_detected is True when degradation > threshold (as a fraction of
    the initial value).

    lower_is_better: set True for perplexity / loss — auto-detected for
    known metric names if omitted.
    """
    if not metric_history:
        return fail("metric_history must not be empty").to_dict()

    # Auto-detect direction for known metrics
    if metric_key in _LOWER_IS_BETTER_METRICS:
        lower_is_better = True

    # Extract values for the requested key
    values: list[tuple[str, float]] = []
    for entry in metric_history:
        val = entry.get("metrics", {}).get(metric_key)
        if val is not None:
            try:
                values.append((entry.get("date", ""), float(val)))
            except (TypeError, ValueError):
                pass

    if not values:
        return fail(f"metric_key {metric_key!r} not found in any history entry").to_dict()

    if len(values) < 2:
        return ok(
            {
                "drift_detected": False,
                "magnitude": 0.0,
                "detail": "Insufficient history (< 2 data points) — no drift detectable",
            }
        ).to_dict()

    first_val = values[0][1]
    last_val = values[-1][1]

    if first_val == 0.0:
        magnitude = abs(last_val - first_val)
        drift_detected = magnitude > threshold
    else:
        if lower_is_better:
            # degradation: value increased
            relative_change = (last_val - first_val) / abs(first_val)
        else:
            # degradation: value decreased
            relative_change = (first_val - last_val) / abs(first_val)
        magnitude = round(max(relative_change, 0.0), 6)
        drift_detected = relative_change > threshold

    detail = (
        f"{metric_key}: {first_val:.4f} → {last_val:.4f} "
        f"({'degraded' if drift_detected else 'stable'}, "
        f"relative change {magnitude:.4f}, threshold {threshold})"
    )

    return ok(
        {
            "drift_detected": drift_detected,
            "magnitude": magnitude,
            "detail": detail,
            "metric_key": metric_key,
            "first_value": first_val,
            "last_value": last_val,
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 62: suggest_retraining (C1)
# ---------------------------------------------------------------------------

_DRIFT_THRESHOLD = 0.08  # relative drift fraction → recommend
_NEW_DATA_THRESHOLD = 500  # rows of new data → recommend
_DAYS_STALE_THRESHOLD = 45  # days since last train → recommend


def suggest_retraining(
    drift_magnitude: float,
    new_data_size: int,
    days_since_last_train: int,
) -> dict[str, Any]:
    """Recommend retraining based on production signals (heuristics, pure).

    Returns {recommend: bool, reasons: list[str]}.
    Fails if any argument is negative.
    """
    if drift_magnitude < 0 or new_data_size < 0 or days_since_last_train < 0:
        return fail("all signal values must be non-negative").to_dict()

    reasons: list[str] = []

    if drift_magnitude >= _DRIFT_THRESHOLD:
        reasons.append(
            f"Significant performance drift detected (magnitude={drift_magnitude:.3f} "
            f">= threshold={_DRIFT_THRESHOLD})"
        )

    if new_data_size >= _NEW_DATA_THRESHOLD:
        reasons.append(
            f"Large volume of new data available ({new_data_size} samples "
            f">= threshold={_NEW_DATA_THRESHOLD})"
        )

    if days_since_last_train >= _DAYS_STALE_THRESHOLD:
        reasons.append(
            f"Model is stale ({days_since_last_train} days since last training "
            f">= threshold={_DAYS_STALE_THRESHOLD} days)"
        )

    recommend = len(reasons) > 0

    return ok(
        {
            "recommend": recommend,
            "reasons": reasons,
            "signals": {
                "drift_magnitude": drift_magnitude,
                "new_data_size": new_data_size,
                "days_since_last_train": days_since_last_train,
            },
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 63: update_base_model (C1)
# ---------------------------------------------------------------------------


def update_base_model(
    project_id: str,
    new_repo: str,
    new_revision: str,
    *,
    store: Store | None = None,
) -> dict[str, Any]:
    """Update the pipeline to a newer base model (pure, no network).

    Produces a config diff (old vs new repo/revision) and updates the
    persisted project config. Returns {diff, updated_config_path?}.
    """
    if not new_repo or not new_repo.strip():
        return fail("new_repo must not be empty").to_dict()

    s = _get_store(store)
    try:
        state = s.read_project(project_id)
    except (ValueError, OSError, FileNotFoundError) as exc:
        return fail(str(exc)).to_dict()

    old_repo = state.get("base_model", "[none]")
    old_revision = state.get("base_revision", "[none]")

    diff_lines = [
        "--- config/model (old)",
        "+++ config/model (new)",
        f"-  base_model:    {old_repo}",
        f"+  base_model:    {new_repo}",
        f"-  base_revision: {old_revision}",
        f"+  base_revision: {new_revision}",
    ]
    diff = "\n".join(diff_lines)

    try:
        s.update_project(
            project_id,
            base_model=new_repo,
            base_revision=new_revision,
        )
    except (ValueError, OSError) as exc:
        return fail(str(exc)).to_dict()

    return ok(
        {
            "diff": diff,
            "old_repo": old_repo,
            "new_repo": new_repo,
            "old_revision": old_revision,
            "new_revision": new_revision,
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# Tool 64: mcp_self_update (C2 — git_remote)
# ---------------------------------------------------------------------------


def mcp_self_update(ref: str = "main") -> dict[str, Any]:
    """Update the MCP server from the configured Git remote.

    dry_run (no FTOS_GIT_REMOTE): return the exact git command.
    configured: run subprocess git pull <remote> <ref> (list form, shell=False).
    Sanitizes all git output. Never puts credential values in the command.
    """
    # The command uses the remote NAME from env, not the URL inline
    dry_command = f"git pull $FTOS_GIT_REMOTE {ref}"

    configured, meta = gate("git_remote")
    if not configured:
        return ok({"command": dry_command, "ref": ref}, **meta).to_dict()

    cfg = _get_target_config("git_remote")
    assert cfg is not None
    remote = cfg["FTOS_GIT_REMOTE"]

    # Build the command as a list (shell=False — never inline credentials)
    cmd = ["git", "pull", remote, ref]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return fail(f"git error: {exc}").to_dict()

    stdout_san, _ = sanitize_text(proc.stdout)
    stderr_san, _ = sanitize_text(proc.stderr)

    if proc.returncode != 0:
        return fail(f"git pull failed (rc={proc.returncode}): {stderr_san.strip()}").to_dict()

    return ok(
        {
            "command": dry_command,
            "ref": ref,
            "stdout": stdout_san.strip(),
            "stderr": stderr_san.strip(),
        },
        **meta,
    ).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers
# ---------------------------------------------------------------------------


# MCP wrapper — keep signature in sync with check_model_rot
def _mcp_check_model_rot(
    metric_history: list[dict[str, Any]],
    metric_key: str,
    threshold: float = 0.05,
    lower_is_better: bool = False,
) -> dict[str, Any]:
    return check_model_rot(
        metric_history=metric_history,
        metric_key=metric_key,
        threshold=threshold,
        lower_is_better=lower_is_better,
    )


# MCP wrapper — keep signature in sync with suggest_retraining
def _mcp_suggest_retraining(
    drift_magnitude: float,
    new_data_size: int,
    days_since_last_train: int,
) -> dict[str, Any]:
    return suggest_retraining(
        drift_magnitude=drift_magnitude,
        new_data_size=new_data_size,
        days_since_last_train=days_since_last_train,
    )


# MCP wrapper — keep signature in sync with update_base_model
def _mcp_update_base_model(
    project_id: str,
    new_repo: str,
    new_revision: str,
) -> dict[str, Any]:
    return update_base_model(
        project_id=project_id,
        new_repo=new_repo,
        new_revision=new_revision,
    )


# MCP wrapper — keep signature in sync with mcp_self_update
def _mcp_self_update(ref: str = "main") -> dict[str, Any]:
    return mcp_self_update(ref=ref)


_MCP_TOOLS = [
    (
        _mcp_check_model_rot,
        "Detect performance drift in a time-ordered metric history — pure, deterministic.",
    ),
    (
        _mcp_suggest_retraining,
        "Recommend retraining from production signals (drift, new data volume, staleness) — pure.",
    ),
    (
        _mcp_update_base_model,
        "Update the base model repo/revision in the project config and produce a diff — pure, no network.",
    ),
    (
        _mcp_self_update,
        "Update the MCP server from a secure Git remote via git pull (dry-run if FTOS_GIT_REMOTE not set).",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all maintenance tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
