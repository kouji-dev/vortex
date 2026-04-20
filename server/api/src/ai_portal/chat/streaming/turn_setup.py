"""turn_setup — create or restore the turn context before streaming begins.

Returns a TurnContext with:
- turn_id: UUID for this turn's thread_items
- user_text: the user's message text
- attachments: list of attachment dicts
- writer: an ItemWriter pre-initialised for this thread
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.model import Thread
from ai_portal.chat.streaming.item_writer import ItemWriter


@dataclass
class TurnContext:
    turn_id: uuid.UUID
    user_text: str
    attachments: list[dict[str, Any]]
    writer: ItemWriter


async def new_turn(
    *,
    session: AsyncSession,
    thread: Thread,
    user_text: str,
    attachments: list[dict[str, Any]],
    org_id: uuid.UUID,
) -> TurnContext:
    """Create a fresh turn: new UUID + insert user_message item."""
    turn_id = uuid.uuid4()
    writer = ItemWriter(session=session, thread_id=thread.id, org_id=org_id)
    await writer.insert_user_message(turn_id=turn_id, text=user_text, attachments=attachments)
    return TurnContext(
        turn_id=turn_id,
        user_text=user_text,
        attachments=attachments,
        writer=writer,
    )


async def regenerate_turn(
    *,
    session: AsyncSession,
    thread: Thread,
    turn_id: uuid.UUID,
    user_text: str,
    org_id: uuid.UUID,
) -> TurnContext:
    """Restore a previous turn context for regeneration (re-use existing turn_id).

    Does NOT insert a new user_message — it already exists in the thread.
    The caller is responsible for cancelling/deleting the old streaming items.
    """
    writer = ItemWriter(session=session, thread_id=thread.id, org_id=org_id)
    return TurnContext(
        turn_id=turn_id,
        user_text=user_text,
        attachments=[],
        writer=writer,
    )


async def start_or_regenerate(
    *,
    session: AsyncSession,
    thread: Thread,
    user_text: str,
    attachments: list[dict[str, Any]],
    org_id: uuid.UUID,
    regenerate_from_turn_id: uuid.UUID | None,
) -> TurnContext:
    """Unified entry point: create a new turn or restore one for regeneration.

    If *regenerate_from_turn_id* is provided, delegates to ``regenerate_turn``;
    otherwise delegates to ``new_turn``.
    """
    if regenerate_from_turn_id is not None:
        return await regenerate_turn(
            session=session,
            thread=thread,
            turn_id=regenerate_from_turn_id,
            user_text=user_text,
            org_id=org_id,
        )
    return await new_turn(
        session=session,
        thread=thread,
        user_text=user_text,
        attachments=attachments,
        org_id=org_id,
    )
