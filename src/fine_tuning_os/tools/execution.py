# src/fine_tuning_os/tools/execution.py
"""Lot 3 — Execution tools 18-25.

C2 contract (all tools marked C2):
  configured, meta = gate(kind)
  command = <exact runnable command string>   # ALWAYS computed
  if not configured: return ok({command:..., ...}, **meta).to_dict()
  # configured → real action; sanitize ALL external text before returning
  sanitized, n = sanitize_text(raw_output)
  return ok({command:..., output:sanitized, ...}, **meta).to_dict()

SSH actions (20, 21, 22, 24): use paramiko with key auth.
Registry push (18): use subprocess docker push.
Never raise to caller — wrap I/O in try/except and return fail(str(exc)).
"""

from __future__ import annotations

import math
import re
import subprocess
from typing import Any

import jinja2
import paramiko

from ..envelope import fail, ok
from ..sanitize import sanitize_text
from ..targets import _get_target_config, gate
from ..templating import render_template

# ---------------------------------------------------------------------------
# SSH helper
# ---------------------------------------------------------------------------


def _ssh_exec(host: str, key_path: str, command: str) -> tuple[str, str]:
    """Connect via paramiko key auth, run command, return (stdout, stderr).

    AutoAddPolicy is used here to accept unknown host keys for the
    operator-controlled bastion host.  Operators who prefer strict host-key
    checking can supply a known_hosts file via paramiko's load_host_keys().

    Caller is responsible for sanitizing the output before returning it.
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        # Fix #4: add connect timeout to prevent hanging indefinitely
        client.connect(hostname=host, key_filename=key_path, timeout=30)
        _, stdout, stderr = client.exec_command(command)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        return out, err
    finally:
        client.close()


# ---------------------------------------------------------------------------
# SSH gate helper (DRY — tools 20, 21, 22, 24)
# ---------------------------------------------------------------------------


def _ssh_gate(
    fallback_host: str,
) -> tuple[bool, dict[str, Any], str, dict[str, Any] | None]:
    """Run the SSH C2 gate and return (configured, meta, host, cfg).

    The dry_run command must reference the $FTOS_SSH_KEY NAME placeholder
    (never the secret value) — callers use this helper to get host/cfg then
    build their own dry_cmd string with $FTOS_SSH_KEY.
    """
    configured, meta = gate("ssh")
    cfg = _get_target_config("ssh") if configured else None
    host = cfg["FTOS_SSH_HOST"] if cfg else fallback_host
    return configured, meta, host, cfg


# ---------------------------------------------------------------------------
# Tool 18: push_docker_to_registry (C2 — registry)
# ---------------------------------------------------------------------------


def push_docker_to_registry(tag: str) -> dict[str, Any]:
    """Push a Docker image to the configured registry.

    Gate: FTOS_REGISTRY + FTOS_REGISTRY_TOKEN must be set.
    The command is always computed; live push uses subprocess docker push.
    """
    configured, meta = gate("registry")
    cfg = _get_target_config("registry") if configured else None
    registry = cfg["FTOS_REGISTRY"] if cfg else "<FTOS_REGISTRY>"
    full_tag = f"{registry}/{tag}"
    command = f"docker push {full_tag}"

    if not configured:
        return ok({"command": command, "full_tag": full_tag}, **meta).to_dict()

    # Fix #2: convert to list form — no shell=True (prevents command injection)
    try:
        proc = subprocess.run(
            ["docker", "push", full_tag],
            shell=False,
            capture_output=True,
            text=True,
            timeout=300,
        )
        raw = proc.stdout + proc.stderr
        sanitized, n = sanitize_text(raw)
        # Extract digest if present
        digest_match = re.search(r"digest:\s*(sha256:[a-f0-9]+)", sanitized)
        digest = digest_match.group(1) if digest_match else None
        return ok(
            {
                "command": command,
                "full_tag": full_tag,
                "output": sanitized,
                "masked_count": n,
                "digest": digest,
                "returncode": proc.returncode,
            },
            **meta,
        ).to_dict()
    except (
        subprocess.TimeoutExpired,
        subprocess.CalledProcessError,
        FileNotFoundError,
        OSError,
    ) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 19: generate_deployment_command (C1)
# ---------------------------------------------------------------------------


def generate_deployment_command(
    image: str,
    mounts: list[dict[str, str]],
    env_names: list[str],
    gpus: list[str],
) -> dict[str, Any]:
    """Produce docker run / docker compose command and compose YAML.

    Env var NAMES are embedded as references (${VAR}); secret VALUES are
    never read or returned. No env vars needed to run this tool.
    """
    # Fix #3: use truthiness check so empty list [] produces no --gpus flag
    gpu_flag = ""
    if gpus:
        gpu_ids = ",".join(gpus)
        gpu_flag = f" --gpus '\"device={gpu_ids}\"'"
    # (no else branch — empty list or no GPUs → no flag)

    env_flags = " ".join(f"-e {n}=${{{n}}}" for n in env_names)
    mount_flags = " ".join(
        f"-v {m['host']}:{m['container']}" + (":ro" if m.get("readonly") else "") for m in mounts
    )
    parts = ["docker run", "--rm"]
    if gpu_flag:
        parts.append(gpu_flag.strip())
    if mount_flags:
        parts.append(mount_flags)
    if env_flags:
        parts.append(env_flags)
    parts.append(image)
    command = " ".join(parts)

    # Fix #6: narrow bare except → jinja2.TemplateError only
    try:
        compose_content = render_template(
            "docker/compose.yaml.j2",
            image=image,
            mounts=[{"host": m["host"], "container": m["container"], **m} for m in mounts],
            env_names=env_names,
            gpus=gpus,
        )
    except jinja2.TemplateError as exc:
        return fail(f"compose render failed: {exc}").to_dict()

    return ok({"command": command, "compose_content": compose_content}).to_dict()


# ---------------------------------------------------------------------------
# Tool 20: trigger_remote_training (C2 — ssh)
# ---------------------------------------------------------------------------


def trigger_remote_training(target: str, command: str) -> dict[str, Any]:
    """Launch remote training over SSH.

    Dry-run command uses $FTOS_SSH_KEY placeholder (never the secret value).
    """
    configured, meta, host, cfg = _ssh_gate(fallback_host=target)
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{command}'"

    if not configured:
        return ok({"command": dry_cmd}, **meta).to_dict()

    # Live branch
    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], command)  # type: ignore[index]
        raw = out + err
        sanitized, n = sanitize_text(raw)
        return ok(
            {"command": dry_cmd, "output": sanitized, "masked_count": n},
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 21: stream_remote_logs (C2 — ssh)
# ---------------------------------------------------------------------------


def stream_remote_logs(job_id: str, target: str, n_lines: int = 100) -> dict[str, Any]:
    """Fetch last n_lines of remote job logs over SSH; sanitize every line."""
    configured, meta, host, cfg = _ssh_gate(fallback_host=target)
    remote_cmd = f"tail -{n_lines} ~/training_logs/{job_id}.log 2>/dev/null || echo 'no log'"
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{remote_cmd}'"

    if not configured:
        return ok({"command": dry_cmd}, **meta).to_dict()

    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], remote_cmd)  # type: ignore[index]
        raw_lines = (out + err).splitlines()
        sanitized_lines: list[str] = []
        total_masked = 0
        for line in raw_lines:
            clean, n = sanitize_text(line)
            sanitized_lines.append(clean)
            total_masked += n
        return ok(
            {
                "command": dry_cmd,
                "logs": sanitized_lines,
                "masked_count": total_masked,
            },
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 22: monitor_training_metrics (C2 — ssh)
# ---------------------------------------------------------------------------

_METRIC_RE = re.compile(r"step=(\d+).*?loss=([\d.]+)(?:.*?lr=([\d.e+-]+))?(?:.*?gpu_util=(\d+))?")


def monitor_training_metrics(job_id: str, source: str) -> dict[str, Any]:
    """Aggregate loss/lr/gpu series from sanitized remote logs."""
    configured, meta, host, cfg = _ssh_gate(fallback_host=source)
    remote_cmd = f"cat ~/training_logs/{job_id}.log 2>/dev/null || echo 'no log'"
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{remote_cmd}'"

    if not configured:
        return ok({"command": dry_cmd}, **meta).to_dict()

    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], remote_cmd)  # type: ignore[index]
        sanitized, _ = sanitize_text(out + err)

        loss_series: list[dict[str, Any]] = []
        lr_series: list[dict[str, Any]] = []
        gpu_series: list[dict[str, Any]] = []

        for line in sanitized.splitlines():
            m = _METRIC_RE.search(line)
            if m:
                step = int(m.group(1))
                loss = float(m.group(2))
                loss_series.append({"step": step, "loss": loss})
                if m.group(3):
                    lr_series.append({"step": step, "lr": float(m.group(3))})
                if m.group(4):
                    gpu_series.append({"step": step, "gpu_util": int(m.group(4))})

        return ok(
            {
                "command": dry_cmd,
                "loss_series": loss_series,
                "lr_series": lr_series,
                "gpu_series": gpu_series,
            },
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 23: detect_anomalies (C1)
# ---------------------------------------------------------------------------

_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _check_log_anomalies(logs: list[str]) -> list[dict[str, Any]]:
    """Scan log lines for NaN/Inf and PII patterns; return alerts."""
    alerts: list[dict[str, Any]] = []
    for i, line in enumerate(logs):
        if re.search(r"\bnan\b", line, re.IGNORECASE) or re.search(r"\binf\b", line, re.IGNORECASE):
            alerts.append(
                {
                    "type": "nan_loss",
                    "severity": "critical",
                    "detail": f"NaN/Inf detected in log line {i + 1}: {line[:120]}",
                }
            )
        if _EMAIL_PATTERN.search(line):
            alerts.append(
                {
                    "type": "pii_data_leak",
                    "severity": "high",
                    "detail": f"Possible PII in log line {i + 1} (email-like pattern)",
                }
            )
    return alerts


def _check_metric_anomalies(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    """Check step_history for NaN losses and plateau; return alerts."""
    alerts: list[dict[str, Any]] = []
    history: list[dict[str, Any]] = metrics.get("step_history", [])
    losses = [s.get("loss") for s in history if "loss" in s]

    # NaN in metrics
    for step_data in history:
        loss = step_data.get("loss")
        if loss is not None and (math.isnan(float(loss)) or math.isinf(float(loss))):
            alerts.append(
                {
                    "type": "nan_loss",
                    "severity": "critical",
                    "detail": f"NaN/Inf loss at step {step_data.get('step')}",
                }
            )
            break

    # Plateau: last 10 steps variance
    recent = [float(v) for v in losses[-10:] if v is not None]
    if len(recent) >= 10:
        loss_range = max(recent) - min(recent)
        if loss_range < 0.005:
            alerts.append(
                {
                    "type": "plateau",
                    "severity": "medium",
                    "detail": f"Loss plateau over {len(recent)} steps (range={loss_range:.5f})",
                }
            )
    return alerts


def detect_anomalies(
    logs: list[str],
    metrics: dict[str, Any],
) -> dict[str, Any]:
    """Analyze sanitized logs/metrics for anomalies.

    Returns list of alerts with keys: type, severity, detail.
    Inputs MUST already be sanitized (external text goes through sanitize_text
    before reaching this tool via stream_remote_logs / monitor_training_metrics).
    """
    alerts = _check_log_anomalies(logs) + _check_metric_anomalies(metrics)
    return ok({"alerts": alerts}).to_dict()


# ---------------------------------------------------------------------------
# Tool 24: pause_resume_training (C2 — ssh)
# ---------------------------------------------------------------------------

_VALID_ACTIONS = {"pause", "resume"}


def pause_resume_training(job_id: str, action: str) -> dict[str, Any]:
    """Pause or resume a remote training job via SSH."""
    if action not in _VALID_ACTIONS:
        return fail(f"invalid action {action!r}; must be 'pause' or 'resume'").to_dict()

    configured, meta, host, cfg = _ssh_gate(fallback_host="<FTOS_SSH_HOST>")
    remote_cmd = (
        f"kill -SIGSTOP $(cat ~/jobs/{job_id}.pid)"
        if action == "pause"
        else f"kill -SIGCONT $(cat ~/jobs/{job_id}.pid)"
    )
    dry_cmd = f"ssh -i $FTOS_SSH_KEY {host} '{remote_cmd}'"

    if not configured:
        return ok({"command": dry_cmd, "action": action, "job_id": job_id}, **meta).to_dict()

    try:
        out, err = _ssh_exec(host, cfg["FTOS_SSH_KEY"], remote_cmd)  # type: ignore[index]
        sanitized, n = sanitize_text(out + err)
        return ok(
            {
                "command": dry_cmd,
                "action": action,
                "job_id": job_id,
                "status": sanitized.strip() or f"job {job_id} {action}d",
                "masked_count": n,
            },
            **meta,
        ).to_dict()
    except (paramiko.SSHException, OSError) as exc:
        return fail(str(exc)).to_dict()


# ---------------------------------------------------------------------------
# Tool 25: early_stopping_check (C1)
# ---------------------------------------------------------------------------


def early_stopping_check(
    metrics: dict[str, Any],
    patience: int = 5,
    min_delta: float = 0.001,
) -> dict[str, Any]:
    """Evaluate whether training should stop early.

    Decision logic:
    - If fewer steps than patience → continue (insufficient history).
    - If len(losses) == patience → continue (no 'before' window to compare).
    - If the best loss hasn't improved by min_delta for `patience` consecutive
      steps → stop.
    - Otherwise → continue.
    """
    history: list[dict[str, Any]] = metrics.get("step_history", [])
    if not history:
        return fail("step_history is empty; cannot evaluate early stopping").to_dict()

    losses = [float(s["loss"]) for s in history if "loss" in s]
    # Fix #1: guard against empty losses[:-patience] when len == patience
    if len(losses) <= patience:
        return ok(
            {
                "decision": "continue",
                "reason": f"only {len(losses)} steps recorded; need at least {patience} to evaluate",
            }
        ).to_dict()

    # Sliding window: check if no improvement >= min_delta for last `patience` steps
    best_before = min(losses[:-patience])
    recent_best = min(losses[-patience:])
    improved = best_before - recent_best >= min_delta

    if not improved:
        return ok(
            {
                "decision": "stop",
                "reason": (
                    f"No improvement >= {min_delta} over last {patience} steps "
                    f"(best_recent={recent_best:.5f}, best_earlier={best_before:.5f})"
                ),
            }
        ).to_dict()

    return ok(
        {
            "decision": "continue",
            "reason": (
                f"Loss improved by {best_before - recent_best:.5f} "
                f"(min_delta={min_delta}) — training should continue"
            ),
        }
    ).to_dict()


# ---------------------------------------------------------------------------
# FastMCP registration — thin wrappers without non-serialisable kwargs
# ---------------------------------------------------------------------------


_MCP_TOOLS = [
    (
        push_docker_to_registry,
        "Push a Docker image to the configured registry (dry-run unless FTOS_REGISTRY configured).",
    ),
    (
        generate_deployment_command,
        "Produce docker run / compose command using env NAME references only — never secret values.",
    ),
    (
        trigger_remote_training,
        "Launch remote training via SSH (dry-run unless FTOS_SSH_* configured).",
    ),
    (
        stream_remote_logs,
        "Fetch and sanitize remote training logs via SSH (dry-run unless FTOS_SSH_* configured).",
    ),
    (
        monitor_training_metrics,
        "Aggregate loss/lr/gpu time-series from sanitized remote logs via SSH.",
    ),
    (
        detect_anomalies,
        "Detect divergence, NaN, plateau, and data-leak signs from sanitized logs/metrics.",
    ),
    (
        pause_resume_training,
        "Pause or resume a remote training job via SSH (dry-run unless FTOS_SSH_* configured).",
    ),
    (
        early_stopping_check,
        "Evaluate early-stop (patience + min_delta) over a loss history.",
    ),
]


def register(mcp: object) -> None:  # type: ignore[type-arg]
    """Register all execution tools with the FastMCP instance."""
    for fn, desc in _MCP_TOOLS:
        mcp.tool(description=desc)(fn)  # type: ignore[union-attr]
