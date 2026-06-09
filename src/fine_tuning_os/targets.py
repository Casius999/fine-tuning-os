# SPDX-License-Identifier: Apache-2.0
# src/fine_tuning_os/targets.py
"""C2 external-target gating from environment variables.

A C2 tool executes live only when its target is fully configured via env
vars; otherwise it returns dry_run + the exact command. Secrets are never
written to disk or logs — only their presence is ever surfaced.
"""

from __future__ import annotations

import os
from typing import Any

# kind -> env var names that must ALL be present (non-empty) to go live.
_REQUIRED: dict[str, tuple[str, ...]] = {
    "ssh": ("FTOS_SSH_HOST", "FTOS_SSH_KEY"),
    "registry": ("FTOS_REGISTRY", "FTOS_REGISTRY_TOKEN"),
    "sftp": ("FTOS_SFTP_HOST", "FTOS_SFTP_USER", "FTOS_SFTP_KEY"),
    "smtp": ("FTOS_SMTP_HOST", "FTOS_SMTP_USER", "FTOS_SMTP_PASSWORD"),
    "slack": ("FTOS_SLACK_WEBHOOK",),
    "calendly": ("FTOS_CALENDLY_TOKEN",),
    "hf": ("HF_TOKEN",),
    "git_remote": ("FTOS_GIT_REMOTE",),
    "local_python": ("FTOS_LOCAL_PYTHON",),
}


def resolve_target(kind: str) -> bool:
    """Return True iff every env var for `kind` is present (non-empty).

    Only presence is surfaced — secret values never leave this module via
    this function, so it is safe to expose to Claude and to log.
    """
    names = _REQUIRED.get(kind)
    if names is None:
        raise ValueError(f"unknown target kind: {kind}")
    return all(os.environ.get(name) for name in names)


def _get_target_config(kind: str) -> dict[str, str] | None:
    """Return the env config dict for `kind`, or None if not fully configured.

    Internal use only: C2 tools that must open a live connection read the
    secret values here. Callers MUST NOT log, persist, or return these
    values to Claude (Zero-Data, cf. spec §5/§6).
    """
    names = _REQUIRED.get(kind)
    if names is None:
        raise ValueError(f"unknown target kind: {kind}")
    values: dict[str, str] = {}
    for name in names:
        val = os.environ.get(name)
        if not val:
            return None
        values[name] = val
    return values


def gate(kind: str) -> tuple[bool, dict[str, Any]]:
    """Return (configured, meta) where meta carries executed/dry_run flags."""
    if not resolve_target(kind):
        return False, {"executed": False, "dry_run": True}
    return True, {"executed": True, "dry_run": False}
