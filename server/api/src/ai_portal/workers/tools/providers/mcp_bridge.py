"""MCP bridge tool — surface allow-listed MCP servers as worker tools.

The bridge exposes a single ``mcp_bridge`` tool that dispatches on
``server`` + ``tool`` arguments. The orchestrator additionally calls
:func:`build_mcp_tools` to enumerate remote tool schemas so they can be
shown to the planning LLM (one MCP tool per remote tool, namespaced by
server URL).

Pool settings:
    ``mcp_servers``: list of allow-listed MCP server URLs.
    ``mcp_clients``: ``dict[url, client]`` — duck-typed MCP client with
        ``async list_tools() -> list[dict]`` and
        ``async call_tool(name, args) -> dict``.

Clients are injected by the orchestrator; tests pass stubs.
"""

from __future__ import annotations

from typing import Any

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _allow_listed(server: str, allow_list: list[str]) -> bool:
    return server in allow_list


class McpBridgeTool:
    """Dispatch a tool call to an allow-listed MCP server."""

    name = "mcp_bridge"
    schema = {
        "type": "object",
        "properties": {
            "server": {"type": "string"},
            "tool": {"type": "string"},
            "args": {"type": "object"},
        },
        "required": ["server", "tool"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        server = args["server"]
        tool_name = args["tool"]
        tool_args = dict(args.get("args") or {})

        await ctx.emit_event(
            EventKind.tool_call,
            {"tool": "mcp_bridge", "server": server, "remote_tool": tool_name},
        )

        settings = ctx.pool_settings or {}
        allow_list = list(settings.get("mcp_servers") or [])
        if not _allow_listed(server, allow_list):
            return ToolResult(
                ok=False, error=f"mcp server not on allow-list: {server}"
            )

        clients: dict[str, Any] = settings.get("mcp_clients") or {}
        client = clients.get(server)
        if client is None:
            return ToolResult(
                ok=False, error=f"no mcp client bound for server: {server}"
            )

        try:
            result = await client.call_tool(tool_name, tool_args)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"mcp call failed: {e}")

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.mcp_call",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "server": server,
                        "tool": tool_name,
                        "arg_count": len(tool_args),
                    },
                }
            )

        return ToolResult(ok=True, output=dict(result))


async def build_mcp_tools(
    *,
    servers: list[str],
    clients: dict[str, Any],
) -> list[dict]:
    """List remote tools across allow-listed servers.

    Returns a flat list of ``{name, description, server, schema}`` entries
    keyed by ``mcp.<server>.<tool>`` so the orchestrator can register them
    in the worker tool registry without name collisions.
    """
    out: list[dict] = []
    for server in servers:
        client = clients.get(server)
        if client is None:
            continue
        try:
            remote = await client.list_tools()
        except Exception:  # noqa: BLE001
            continue
        for entry in remote:
            rname = entry.get("name")
            if not rname:
                continue
            out.append(
                {
                    "name": f"mcp.{server}.{rname}",
                    "description": entry.get("description", ""),
                    "server": server,
                    "remote_name": rname,
                    "schema": entry.get("input_schema") or entry.get("schema") or {},
                }
            )
    return out


_: Tool = McpBridgeTool()
