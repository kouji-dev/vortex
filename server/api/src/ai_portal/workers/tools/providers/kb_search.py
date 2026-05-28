"""KB search tool — query org knowledge bases through RAG.

ACL: the pool config carries an ``kb_ids`` allow-list. If the agent
requests an explicit ``kb_ids`` arg, it is intersected with the pool
allow-list before the RAG call — never widened.

The RAG call requires a SQLAlchemy session; the worker orchestrator
threads one in via ``ctx.pool_settings["rag_session"]``. If absent the
tool returns an empty result instead of failing the run.
"""

from __future__ import annotations

from typing import Any

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _search_knowledge_base(db, *, query: str, kb_ids: list[int], top_k=None) -> dict:
    """Indirection seam — overridden in tests.

    Defers the heavy import until call time so workers tests don't pull in
    the full RAG pipeline (voyageai, pgvector, etc.) just to construct a tool.
    """
    from ai_portal.rag.service import search_knowledge_base_tool  # noqa: PLC0415

    return search_knowledge_base_tool(db, query=query, kb_ids=kb_ids, top_k=top_k)


class KbSearchTool:
    """Retrieve passages from org KBs via the RAG service."""

    name = "kb_search"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "kb_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Optional subset of pool-allowed KB ids.",
            },
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args["query"]
        top_k = args.get("top_k")

        settings: dict[str, Any] = ctx.pool_settings or {}
        allowed = [int(k) for k in (settings.get("kb_ids") or [])]
        requested_raw = args.get("kb_ids")
        if requested_raw is not None:
            requested = [int(k) for k in requested_raw]
            kb_ids = [k for k in requested if k in allowed]
        else:
            kb_ids = list(allowed)

        await ctx.emit_event(
            EventKind.tool_call,
            {"tool": "kb_search", "query": query, "kb_ids": kb_ids},
        )

        if not kb_ids:
            if ctx.audit is not None:
                await ctx.audit(
                    {
                        "action": "worker.kb_search",
                        "resource_type": "worker_run",
                        "resource_id": ctx.run_id,
                        "payload": {
                            "query": query,
                            "kb_ids": [],
                            "citation_count": 0,
                        },
                    }
                )
            return ToolResult(
                ok=True,
                output={"context": "", "used_kbs": [], "citations": []},
            )

        db = settings.get("rag_session")
        if db is None:
            return ToolResult(
                ok=False, error="no rag_session bound to worker context"
            )

        try:
            res = _search_knowledge_base(db, query=query, kb_ids=kb_ids, top_k=top_k)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"kb search failed: {e}")

        citations = list(res.get("citations") or [])
        used_kbs = list(res.get("used_kbs") or [])

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.kb_search",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "query": query,
                        "kb_ids": kb_ids,
                        "citation_count": len(citations),
                    },
                }
            )

        return ToolResult(
            ok=True,
            output={
                "context": res.get("context", ""),
                "used_kbs": used_kbs,
                "citations": citations,
            },
        )


_: Tool = KbSearchTool()
