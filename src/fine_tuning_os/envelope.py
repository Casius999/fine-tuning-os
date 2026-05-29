# src/fine_tuning_os/envelope.py
"""Response envelope shared by every Fine-Tuning OS tool."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Result:
    """Uniform tool response. C2 tools surface gating via meta keys
    (executed / dry_run / command)."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ok(data: dict[str, Any] | None = None, **meta: Any) -> Result:
    return Result(success=True, data=data, meta=dict(meta))


def fail(error: str, **meta: Any) -> Result:
    return Result(success=False, error=error, meta=dict(meta))
