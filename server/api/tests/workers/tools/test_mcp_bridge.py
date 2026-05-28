"""Tests for the MCP bridge — exposes allow-listed MCP servers as worker tools."""

from __future__ import annotations

import pytest

from ai_portal.workers.tools.providers.mcp_bridge import (
    McpBridgeTool,
    build_mcp_tools,
)


class _FakeMcpClient:
    """Stub MCP client; satisfies the duck-typed interface."""

    def __init__(self, server_url: str, tools: list[dict], responses: dict):
        self.server_url = server_url
        self._tools = tools
        self._responses = responses
        self.calls: list[tuple[str, dict]] = []

    async def list_tools(self) -> list[dict]:
        return list(self._tools)

    async def call_tool(self, name: str, args: dict) -> dict:
        self.calls.append((name, dict(args)))
        if name not in self._responses:
            raise RuntimeError(f"no scripted response for {name}")
        return self._responses[name]


@pytest.mark.asyncio
async def test_mcp_bridge_invokes_tool_via_client(harness) -> None:
    client = _FakeMcpClient(
        "https://mcp.example/",
        tools=[{"name": "echo", "input_schema": {"type": "object"}}],
        responses={"echo": {"content": "hi"}},
    )
    _sb, _h, ctx, rec = await harness(
        pool_settings={
            "mcp_servers": ["https://mcp.example/"],
            "mcp_clients": {"https://mcp.example/": client},
        }
    )
    bridge = McpBridgeTool()
    r = await bridge.invoke(
        {
            "server": "https://mcp.example/",
            "tool": "echo",
            "args": {"text": "hi"},
        },
        ctx,
    )
    assert r.ok is True
    assert r.output["content"] == "hi"
    assert client.calls == [("echo", {"text": "hi"})]
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_mcp_bridge_rejects_non_allow_listed_server(harness) -> None:
    client = _FakeMcpClient(
        "https://mcp.example/",
        tools=[{"name": "echo"}],
        responses={"echo": {"content": "x"}},
    )
    _sb, _h, ctx, _rec = await harness(
        pool_settings={
            "mcp_servers": ["https://mcp.example/"],
            "mcp_clients": {"https://mcp.example/": client},
        }
    )
    r = await McpBridgeTool().invoke(
        {
            "server": "https://evil.example/",
            "tool": "echo",
            "args": {},
        },
        ctx,
    )
    assert r.ok is False
    assert "not on allow-list" in (r.error or "") or "allow" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_mcp_bridge_no_client_bound_returns_error(harness) -> None:
    _sb, _h, ctx, _rec = await harness(
        pool_settings={"mcp_servers": ["https://mcp.example/"]}
    )
    r = await McpBridgeTool().invoke(
        {"server": "https://mcp.example/", "tool": "echo", "args": {}},
        ctx,
    )
    assert r.ok is False
    assert "client" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_mcp_bridge_audits_tool_call(harness) -> None:
    client = _FakeMcpClient(
        "https://mcp.example/",
        tools=[{"name": "echo"}],
        responses={"echo": {"content": "x"}},
    )
    _sb, _h, ctx, rec = await harness(
        pool_settings={
            "mcp_servers": ["https://mcp.example/"],
            "mcp_clients": {"https://mcp.example/": client},
        }
    )
    await McpBridgeTool().invoke(
        {"server": "https://mcp.example/", "tool": "echo", "args": {}}, ctx
    )
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.mcp_call"
    assert audit["payload"]["server"] == "https://mcp.example/"
    assert audit["payload"]["tool"] == "echo"


@pytest.mark.asyncio
async def test_build_mcp_tools_lists_remote_tools(harness) -> None:
    """Listing helper used by the orchestrator to expose remote tools via the
    worker registry surface."""
    client = _FakeMcpClient(
        "https://mcp.example/",
        tools=[
            {"name": "echo", "description": "echo back"},
            {"name": "sum", "description": "add nums"},
        ],
        responses={},
    )
    tools = await build_mcp_tools(
        servers=["https://mcp.example/"],
        clients={"https://mcp.example/": client},
    )
    names = [t["name"] for t in tools]
    assert "mcp.https://mcp.example/.echo" in names
    assert "mcp.https://mcp.example/.sum" in names
