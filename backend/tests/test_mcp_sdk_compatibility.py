from __future__ import annotations

import asyncio
import importlib


def test_mcp_v2_server_registers_public_tools() -> None:
    module = importlib.import_module("podcast_intelligence.mcp_server")

    tools = asyncio.run(module.mcp.list_tools())

    assert {tool.name for tool in tools} == {
        "ask_episode",
        "create_summary",
        "fetch",
        "list_episodes",
        "search",
    }
