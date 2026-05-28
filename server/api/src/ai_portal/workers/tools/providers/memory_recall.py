"""Memory recall tool — surface worker-scoped memories to the agent.

Worker memories are scoped by ``repo_id`` (the closest analogue in the
existing memory module is ``ScopeKind.assistant`` with ``assistant_id``
= repo_id). The worker orchestrator passes ``memory_session`` (an
``AsyncSession``) and ``repo_id`` via ``pool_settings``.
"""

from __future__ import annotations

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _build_memory_service(session):
    """Indirection seam — overridden in tests."""
    from ai_portal.memory.service import MemoryService  # noqa: PLC0415

    return MemoryService(session)


def _build_scope(org_id: str, actor_user_id: str, repo_id: str | None):
    from ai_portal.memory.recallers.protocol import RecallScope  # noqa: PLC0415

    return RecallScope(
        org_id=str(org_id),
        actor_user_id=str(actor_user_id),
        team_ids=[],
        assistant_id=repo_id,
        conversation_id=None,
    )


def _build_opts(top_k: int | None):
    from ai_portal.memory.recallers.protocol import RecallOpts  # noqa: PLC0415

    if top_k is None:
        return RecallOpts()
    return RecallOpts(top_k=int(top_k))


class MemoryRecallTool:
    """Search worker-scoped memories for facts/preferences."""

    name = "memory_recall"
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        query = args["query"]
        top_k = args.get("top_k")

        await ctx.emit_event(
            EventKind.tool_call, {"tool": "memory_recall", "query": query}
        )

        settings = ctx.pool_settings or {}
        session = settings.get("memory_session")
        if session is None:
            return ToolResult(
                ok=False, error="memory_session not bound on worker context"
            )

        repo_id = settings.get("repo_id")
        svc = _build_memory_service(session)
        scope = _build_scope(ctx.org_id, ctx.actor_id, repo_id)
        opts = _build_opts(top_k)

        try:
            results = await svc.recall(query, scope, opts)
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"recall failed: {e}")

        rows = [
            {
                "id": r.memory_id,
                "text": r.text,
                "score": round(float(r.score), 4),
            }
            for r in results
        ]

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.memory_recall",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {"query": query, "result_count": len(rows)},
                }
            )

        return ToolResult(ok=True, output={"results": rows})


_: Tool = MemoryRecallTool()
