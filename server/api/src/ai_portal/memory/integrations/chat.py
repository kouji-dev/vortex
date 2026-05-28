"""Chat-side memory integration.

Two hooks:
- ``recall_for_turn``: before LLM call, fetch memories + render system block.
- ``extract_async``:    after assistant message persisted, enqueue extract job.

Both are pure functions that take an AsyncSession so chat code can call
them inside its own UoW. The chat module is the *caller* — this module
does not import chat models.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory import jobs as _jobs
from ai_portal.memory.extractors.protocol import ExtractScope, Turn
from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope, Recalled
from ai_portal.memory.service import MemoryService

logger = logging.getLogger(__name__)


@dataclass
class InjectedMemories:
    items: list[Recalled] = field(default_factory=list)
    system_block: str = ""

    def has_any(self) -> bool:
        return bool(self.items)


def render_system_block(items: list[Recalled]) -> str:
    """Render recalled memories as a system prompt block (caveman)."""
    if not items:
        return ""
    lines = ["Memories:"]
    for r in items:
        lines.append(f"- {r.text}")
    return "\n".join(lines)


async def recall_for_turn(
    session: AsyncSession,
    *,
    org_id: str,
    actor_user_id: str,
    query: str,
    team_ids: list[str] | None = None,
    assistant_id: str | None = None,
    conversation_id: str | None = None,
    top_k: int = 8,
) -> InjectedMemories:
    scope = RecallScope(
        org_id=str(org_id),
        actor_user_id=str(actor_user_id),
        team_ids=list(team_ids or []),
        assistant_id=assistant_id,
        conversation_id=conversation_id,
    )
    svc = MemoryService(session)
    items = await svc.recall(query, scope, RecallOpts(top_k=top_k))
    return InjectedMemories(items=items, system_block=render_system_block(items))


async def attach_uses_for_response(
    session: AsyncSession,
    injected: InjectedMemories,
    *,
    response_message_id: str,
    query: str = "",
) -> None:
    if not injected.has_any():
        return
    svc = MemoryService(session)
    await svc.attach_uses(
        injected.items, response_message_id=response_message_id, query=query
    )


async def extract_async(
    session: AsyncSession,
    *,
    org_id,
    actor_user_id: str,
    conversation_id: int | str,
    turns: list[dict[str, Any]],
    assistant_id: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> None:
    """Enqueue an extract job for the just-completed turn."""
    import uuid as _uuid

    org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
    payload = {
        "actor_user_id": str(actor_user_id),
        "conversation_id": conversation_id,
        "assistant_id": assistant_id,
        "scope_id": str(actor_user_id),
        "model": model,
        "turns": turns,
        "last_turn_id": turns[-1].get("turn_id") if turns else None,
    }
    await _jobs.enqueue(
        session,
        org_id=org_uuid,
        kind="extract",
        scope_kind="user",
        payload=payload,
    )


async def extract_on_close(
    session: AsyncSession,
    *,
    org_id,
    actor_user_id: str,
    conversation_id: int | str,
    transcript: list[dict[str, Any]],
    assistant_id: str | None = None,
) -> None:
    """On conversation close, enqueue a batched extract job over the full transcript."""
    import uuid as _uuid

    org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
    payload = {
        "actor_user_id": str(actor_user_id),
        "conversation_id": conversation_id,
        "assistant_id": assistant_id,
        "scope_id": str(actor_user_id),
        "model": "claude-sonnet-4-6",
        "turns": transcript,
        "batched": True,
    }
    await _jobs.enqueue(
        session,
        org_id=org_uuid,
        kind="extract",
        scope_kind="conversation",
        payload=payload,
    )


async def on_conversation_close(
    session: AsyncSession,
    *,
    org_id,
    actor_user_id: str,
    conversation_id: int | str,
    transcript: list[dict[str, Any]],
    assistant_id: str | None = None,
    model: str = "claude-sonnet-4-6",
) -> None:
    """Public close hook — enqueues a batched summarization MemoryJob.

    Worker ``memory/workers/conversation_close.py`` drains the queue and calls
    the extractor with the full conversation history.
    """
    import uuid as _uuid

    org_uuid = org_id if isinstance(org_id, _uuid.UUID) else _uuid.UUID(str(org_id))
    payload = {
        "actor_user_id": str(actor_user_id),
        "conversation_id": conversation_id,
        "assistant_id": assistant_id,
        "scope_id": str(actor_user_id),
        "model": model,
        "turns": transcript,
        "batched": True,
        "trigger": "conversation_close",
    }
    await _jobs.enqueue(
        session,
        org_id=org_uuid,
        kind="conversation_close",
        scope_kind="conversation",
        payload=payload,
    )
