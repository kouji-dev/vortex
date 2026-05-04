"""turn_setup — create or restore the turn context before streaming begins."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from ai_portal.chat.model import Thread
from ai_portal.chat.streaming.item_writer import ItemWriter


@dataclass
class TurnContext:
    turn_id: uuid.UUID
    user_text: str
    attachments: list[dict[str, Any]]
    writer: ItemWriter


def new_turn(
    *,
    session: Session,
    thread: Thread,
    user_text: str,
    attachments: list[dict[str, Any]],
    org_id: uuid.UUID,
) -> TurnContext:
    turn_id = uuid.uuid4()
    writer = ItemWriter(session=session, thread_id=thread.id, org_id=org_id)
    writer.insert_user_message(turn_id=turn_id, text=user_text, attachments=attachments)
    return TurnContext(
        turn_id=turn_id,
        user_text=user_text,
        attachments=attachments,
        writer=writer,
    )


def regenerate_turn(
    *,
    session: Session,
    thread: Thread,
    turn_id: uuid.UUID,
    user_text: str,
    org_id: uuid.UUID,
) -> TurnContext:
    writer = ItemWriter(session=session, thread_id=thread.id, org_id=org_id)
    return TurnContext(
        turn_id=turn_id,
        user_text=user_text,
        attachments=[],
        writer=writer,
    )


def start_or_regenerate(
    *,
    session: Session,
    thread: Thread,
    user_text: str,
    attachments: list[dict[str, Any]],
    org_id: uuid.UUID,
    regenerate_from_turn_id: uuid.UUID | None,
) -> TurnContext:
    if regenerate_from_turn_id is not None:
        return regenerate_turn(
            session=session,
            thread=thread,
            turn_id=regenerate_from_turn_id,
            user_text=user_text,
            org_id=org_id,
        )
    return new_turn(
        session=session,
        thread=thread,
        user_text=user_text,
        attachments=attachments,
        org_id=org_id,
    )
