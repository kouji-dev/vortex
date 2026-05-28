"""RAG-style ``memory.search`` tool exposed to the LLM.

The tool wraps :meth:`MemoryService.recall` so a tool-using model can
proactively retrieve memories without a chat-side hook. Registration
hooks into the RAG tool registry when available; otherwise the tool
definition + executor are still importable.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


TOOL_DEFINITION: dict[str, Any] = {
    "name": "memory.search",
    "description": "Search the caller's memories. Returns top matches with scores.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Free-text query."},
            "top_k": {"type": "integer", "default": 8, "minimum": 1, "maximum": 50},
        },
        "required": ["query"],
    },
}


async def execute(
    session,
    *,
    org_id: str,
    actor_user_id: str,
    query: str,
    top_k: int = 8,
    team_ids: list[str] | None = None,
    assistant_id: str | None = None,
    conversation_id: str | None = None,
) -> list[dict[str, Any]]:
    from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope
    from ai_portal.memory.service import MemoryService

    scope = RecallScope(
        org_id=str(org_id),
        actor_user_id=str(actor_user_id),
        team_ids=list(team_ids or []),
        assistant_id=assistant_id,
        conversation_id=conversation_id,
    )
    svc = MemoryService(session)
    results = await svc.recall(query, scope, RecallOpts(top_k=top_k))
    return [
        {"id": r.memory_id, "text": r.text, "score": round(float(r.score), 4)}
        for r in results
    ]


def register_with_rag() -> bool:
    """Best-effort registration in the RAG tool registry."""
    try:
        from ai_portal.rag.tools.registry import register as rag_register

        rag_register(TOOL_DEFINITION["name"], TOOL_DEFINITION, execute)
        return True
    except Exception:
        logger.debug("memory.rag_tool registration deferred")
        return False
