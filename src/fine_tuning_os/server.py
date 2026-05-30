# src/fine_tuning_os/server.py
"""Fine-Tuning OS — MCP server bootstrap.

Zero-Data fine-tuning operations toolkit. Lot 1 registers only the socle
health tool; the 64 domain tools are added across lots 2-9. Transport: stdio.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from . import __version__
from .envelope import ok
from .store import workspace_root
from .targets import resolve_target

mcp = FastMCP("fine-tuning-os")

from .tools import execution, pipeline, prep, synthetic  # noqa: E402

prep.register(mcp)
synthetic.register(mcp)
pipeline.register(mcp)
execution.register(mcp)

_TARGET_KINDS: tuple[str, ...] = (
    "ssh",
    "registry",
    "sftp",
    "smtp",
    "slack",
    "calendly",
    "hf",
    "git_remote",
    "local_python",
)


@mcp.tool(
    description=(
        "Report Fine-Tuning OS server health: version, workspace path, and "
        "which external targets are configured (booleans only — never secrets)."
    )
)
def ftos_health() -> dict[str, Any]:
    targets = {kind: resolve_target(kind) for kind in _TARGET_KINDS}
    return ok(
        {
            "name": "fine-tuning-os",
            "version": __version__,
            "workspace": str(workspace_root()),
            "targets_configured": targets,
        }
    ).to_dict()


def main() -> None:
    """Run the MCP server over stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
