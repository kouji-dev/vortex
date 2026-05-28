"""Web search tool — proxies to RAG search providers, gated by egress.

The pool's ``settings`` dict resolves which provider to use:

- ``search_provider_instance``: a ready-built provider object (test path)
- ``search_provider``: a provider name (e.g. ``tavily``); built via the
  RAG search_providers registry

After the provider returns rows, each row's host is checked against the
pool egress policy — non-allow-listed hosts are dropped (provider call
itself happens out-of-process so we cannot block the provider's own
HTTP, but we audit + filter the results we surface to the agent).
"""

from __future__ import annotations

from urllib.parse import urlsplit

from ai_portal.workers.egress.policy import EgressPolicy, check_host
from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _resolve_provider(settings: dict):
    inst = settings.get("search_provider_instance")
    if inst is not None:
        return inst
    name = settings.get("search_provider")
    if not name:
        return None
    try:
        from ai_portal.rag.search_providers import get_provider  # noqa: PLC0415

        return get_provider(name)
    except Exception:
        return None


class WebSearchTool:
    """Run a search query through the pool's configured provider."""

    name = "web_search"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 25},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args["query"]
        num = int(args.get("num_results") or 5)

        await ctx.emit_event(
            EventKind.tool_call, {"tool": "web_search", "query": query, "n": num}
        )

        provider = _resolve_provider(ctx.pool_settings or {})
        if provider is None:
            return ToolResult(ok=False, error="no search provider configured for pool")

        try:
            raw = provider.search(query, num_results=num)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"search failed: {e}")

        policy = ctx.egress if isinstance(ctx.egress, EgressPolicy) else None

        kept: list[dict] = []
        dropped_hosts: list[str] = []
        for row in raw:
            host = urlsplit(row.url).hostname or ""
            if policy is not None and host:
                decision = check_host(policy, host)
                if not decision.allowed:
                    dropped_hosts.append(host)
                    continue
            kept.append(
                {
                    "title": row.title,
                    "url": row.url,
                    "snippet": row.snippet,
                    "score": float(row.score),
                    "source": row.source,
                }
            )

        if dropped_hosts:
            await ctx.emit_event(
                EventKind.egress_blocked,
                {"tool": "web_search", "dropped_hosts": dropped_hosts},
            )

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.web_search",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "query": query,
                        "result_count": len(kept),
                        "dropped_egress": len(dropped_hosts),
                    },
                }
            )

        return ToolResult(ok=True, output={"query": query, "results": kept})


_: Tool = WebSearchTool()
