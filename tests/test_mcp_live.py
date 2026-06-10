# SPDX-License-Identifier: Apache-2.0
# tests/test_mcp_live.py
"""Live MCP stdio smoke test.

Launches the Fine-Tuning OS server as a real subprocess over stdio using the
mcp client SDK.  Proves that the server is a genuine MCP server, not just a
FastMCP object under test.

Assertions:
  - at least 64 tools are exposed (all domain tools registered)
  - ftos_health is present in the tool list
  - ftos_health returns a real result with success=True, version, workspace
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile


import pytest
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Subprocess-based live test — runs in the dedicated `integration` job, not the unit matrix.
pytestmark = pytest.mark.integration

_TIMEOUT = 30  # seconds — generous for cold-start import on CI


async def _run_smoke_test(workspace: str) -> None:
    """Async body; launched via asyncio.run() so we stay sync-test-compatible."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "fine_tuning_os"],
        env={
            **os.environ,
            "FTOS_WORKSPACE": workspace,
            # Ensure no C2 targets are live — we only test the server bootstrap.
            "FTOS_SSH_HOST": "",
            "FTOS_SSH_KEY": "",
            "FTOS_SLACK_WEBHOOK": "",
            "FTOS_SMTP_HOST": "",
        },
    )

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # --- list_tools: expect >=64 tools ---
            result = await session.list_tools()
            tool_names = [t.name for t in result.tools]
            assert (
                len(tool_names) >= 64
            ), f"Expected >=64 tools, got {len(tool_names)}: {tool_names[:10]}..."
            assert "ftos_health" in tool_names, f"ftos_health not in tools: {tool_names}"

            # --- call_tool ftos_health: real round-trip ---
            health = await session.call_tool("ftos_health", {})
            assert health is not None, "ftos_health returned None"
            # CallToolResult.content is a list of content items
            assert health.content, "ftos_health returned empty content"
            # Extract first text content
            text_items = [c for c in health.content if hasattr(c, "text")]
            assert text_items, f"No text content in ftos_health result: {health.content}"
            import json

            data = json.loads(text_items[0].text)
            assert data.get("success") is True, f"ftos_health success!=True: {data}"
            assert "version" in data.get("data", {}), f"version missing: {data}"
            assert "workspace" in data.get("data", {}), f"workspace missing: {data}"


def test_mcp_stdio_smoke() -> None:
    """Launch the MCP server over stdio; assert >=64 tools + ftos_health works."""
    with tempfile.TemporaryDirectory() as workspace:
        asyncio.run(
            asyncio.wait_for(
                _run_smoke_test(workspace),
                timeout=_TIMEOUT,
            )
        )
