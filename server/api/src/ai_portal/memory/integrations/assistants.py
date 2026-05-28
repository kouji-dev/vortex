"""Assistant-scoped memory integration.

Compose a recall scope keyed to a specific assistant so its system prompt
can include curated memories that follow the assistant across conversations.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope
from ai_portal.memory.service import MemoryService


async def recall_for_assistant(
    session: AsyncSession,
    *,
    org_id: str,
    actor_user_id: str,
    assistant_id: str,
    query: str,
    top_k: int = 6,
):
    scope = RecallScope(
        org_id=str(org_id),
        actor_user_id=str(actor_user_id),
        team_ids=[],
        assistant_id=str(assistant_id),
    )
    svc = MemoryService(session)
    return await svc.recall(query, scope, RecallOpts(top_k=top_k))


def render_assistant_block(items) -> str:
    if not items:
        return ""
    lines = ["Assistant memory:"]
    for r in items:
        lines.append(f"- {r.text}")
    return "\n".join(lines)
