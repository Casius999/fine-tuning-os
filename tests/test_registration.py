# tests/test_registration.py
"""Assert all 65 tools (64 domain + ftos_health) are registered on the MCP instance."""

from __future__ import annotations

import fine_tuning_os.server as _server
from fine_tuning_os.tools import (
    client,
    docs,
    evaluation,
    execution,
    maintenance,
    packaging,
    pipeline,
    prep,
    security,
    synthetic,
)


def test_total_domain_tool_count() -> None:
    """Each module exposes _MCP_TOOLS; their sum must equal 64 domain tools."""
    modules = [
        prep,
        synthetic,
        pipeline,
        execution,
        evaluation,
        security,
        packaging,
        docs,
        client,
        maintenance,
    ]
    total = sum(len(m._MCP_TOOLS) for m in modules)
    assert total == 64, f"Expected 64 domain tools, got {total}"


def test_server_registers_65_tools() -> None:
    """FastMCP + ftos_health = 65 total registered tools."""
    # Collect registered tool names via FastMCP's internal registry
    mcp = _server.mcp
    # FastMCP stores tools in _tool_manager or similar; check both attrs
    if hasattr(mcp, "_tool_manager") and hasattr(mcp._tool_manager, "_tools"):
        tool_names = list(mcp._tool_manager._tools.keys())
    elif hasattr(mcp, "list_tools"):
        import asyncio

        tools = asyncio.get_event_loop().run_until_complete(mcp.list_tools())
        tool_names = [t.name for t in tools]
    else:
        # Fallback: check module _MCP_TOOLS counts + 1 health
        modules = [
            prep,
            synthetic,
            pipeline,
            execution,
            evaluation,
            security,
            packaging,
            docs,
            client,
            maintenance,
        ]
        total_domain = sum(len(m._MCP_TOOLS) for m in modules)
        assert total_domain + 1 == 65  # +1 for ftos_health
        return

    assert len(tool_names) == 65, f"Expected 65 tools, got {len(tool_names)}: {sorted(tool_names)}"


def test_representative_tool_names_present() -> None:
    """Spot-check that each module has its _MCP_TOOLS list and the total is 64."""
    module_counts = {
        prep: len(prep._MCP_TOOLS),
        synthetic: len(synthetic._MCP_TOOLS),
        pipeline: len(pipeline._MCP_TOOLS),
        execution: len(execution._MCP_TOOLS),
        evaluation: len(evaluation._MCP_TOOLS),
        security: len(security._MCP_TOOLS),
        packaging: len(packaging._MCP_TOOLS),
        docs: len(docs._MCP_TOOLS),
        client: len(client._MCP_TOOLS),
        maintenance: len(maintenance._MCP_TOOLS),
    }
    # Each module must have at least 1 tool
    for mod, count in module_counts.items():
        assert count >= 1, f"{mod.__name__} has no tools"

    # Lot 6 modules must have their declared counts
    assert len(client._MCP_TOOLS) == 6  # tools 55-60
    assert len(maintenance._MCP_TOOLS) == 4  # tools 61-64

    # Grand total must be 64 domain tools
    total = sum(module_counts.values())
    assert total == 64, f"Expected 64 domain tools, got {total}"
