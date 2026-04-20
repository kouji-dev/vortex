"""Chat domain — database query layer.

All functions here take a ``db: Session`` as first argument and return ORM
objects or plain Python values.  No business logic, no HTTP concerns.
"""

from __future__ import annotations

import uuid as _uuid
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ai_portal.assistant.model import Assistant
from ai_portal.auth.model import User
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.chat.schemas import ConversationSettings
from ai_portal.knowledge_base.model import ConversationKnowledgeBase, KnowledgeBase


# ---------------------------------------------------------------------------
# Thread CRUD
# ---------------------------------------------------------------------------


def list_threads(
    db: Session,
    *,
    org_id: UUID,
    user_id: int,
    limit: int = 50,
    offset: int = 0,
) -> list[Thread]:
    stmt = (
        select(Thread)
        .where(Thread.org_id == org_id, Thread.user_id == user_id)
        .order_by(Thread.last_message_at.desc().nulls_last(), Thread.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt).all())


def get_thread(
    db: Session, *, thread_id: int, org_id: UUID
) -> Thread | None:
    stmt = select(Thread).where(Thread.id == thread_id, Thread.org_id == org_id)
    return db.scalars(stmt).first()


def create_thread(
    db: Session,
    *,
    org_id: UUID,
    user_id: int,
    title: str | None = None,
    model: str | None = None,
    assistant_id: int | None = None,
    settings: ConversationSettings | None = None,
) -> Thread:
    thread = Thread(
        org_id=org_id,
        user_id=user_id,
        title=title,
        model=model,
        assistant_id=assistant_id,
        settings=settings,
    )
    db.add(thread)
    db.flush()
    return thread


def update_thread(
    db: Session,
    *,
    thread_id: int,
    org_id: UUID,
    **fields,
) -> Thread:
    stmt = (
        update(Thread)
        .where(Thread.id == thread_id, Thread.org_id == org_id)
        .values(**fields)
        .returning(Thread)
    )
    result = db.execute(stmt)
    thread = result.scalar_one_or_none()
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread


def delete_thread(
    db: Session, *, thread_id: int, org_id: UUID
) -> None:
    stmt = delete(Thread).where(Thread.id == thread_id, Thread.org_id == org_id)
    db.execute(stmt)


# ---------------------------------------------------------------------------
# ThreadItem reads
# ---------------------------------------------------------------------------


def list_thread_items(
    db: Session,
    *,
    thread_id: int,
    org_id: UUID,
    since_id: int | None = None,
) -> list[ThreadItem]:
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_id,
        ThreadItem.org_id == org_id,
    )
    if since_id is not None:
        stmt = stmt.where(ThreadItem.id > since_id)
    stmt = stmt.order_by(ThreadItem.created_at, ThreadItem.id)
    return list(db.scalars(stmt).all())


def get_thread_item(
    db: Session, *, item_id: int, org_id: UUID
) -> ThreadItem | None:
    stmt = select(ThreadItem).where(
        ThreadItem.id == item_id, ThreadItem.org_id == org_id
    )
    return db.scalars(stmt).first()


def count_thread_items(
    db: Session, *, thread_id: int, org_id: UUID
) -> int:
    stmt = select(func.count()).select_from(ThreadItem).where(
        ThreadItem.thread_id == thread_id, ThreadItem.org_id == org_id
    )
    return db.scalar(stmt) or 0


# ---------------------------------------------------------------------------
# Legacy conversation helpers (still used by router / service)
# ---------------------------------------------------------------------------


def get_owned_conversation(
    db: Session, user: User, conversation_id: int
) -> Thread:
    conv = db.get(Thread, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def list_conversations_for_user(
    db: Session, user_id: int, org_id: _uuid.UUID
) -> list[Thread]:
    return list(
        db.scalars(
            select(Thread)
            .where(Thread.user_id == user_id)
            .where(Thread.org_id == org_id)
            .order_by(Thread.id.desc())
        ).all()
    )


def get_conversation_kb_ids(db: Session, conversation_id: int) -> list[int]:
    return list(
        db.scalars(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conversation_id
            )
        ).all()
    )


def sync_conversation_knowledge_links(
    db: Session,
    conv: Thread,
    user: User,
    knowledge_base_ids: list[int],
) -> Thread:
    seen: set[int] = set()
    unique_ids: list[int] = []
    for kb_id in knowledge_base_ids:
        if kb_id in seen:
            continue
        seen.add(kb_id)
        unique_ids.append(kb_id)
    for kb_id in unique_ids:
        kb = db.get(KnowledgeBase, kb_id)
        if kb is None or kb.owner_user_id != user.id:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                detail="Knowledge base not found",
            )
    db.execute(
        delete(ConversationKnowledgeBase).where(
            ConversationKnowledgeBase.conversation_id == conv.id
        )
    )
    for kb_id in unique_ids:
        db.add(
            ConversationKnowledgeBase(
                conversation_id=conv.id,
                knowledge_base_id=kb_id,
            )
        )
    db.commit()
    db.refresh(conv)
    return conv


def delete_conversation(db: Session, conv: Thread) -> None:
    db.delete(conv)
    db.commit()


def get_assistant_for_user(
    db: Session, user: User, assistant_id: int
) -> Assistant | None:
    return db.get(Assistant, assistant_id)


# ---------------------------------------------------------------------------
# Legacy message helpers (still used by streaming_service — remove in Phase 6)
# ---------------------------------------------------------------------------


def get_messages_before(
    db: Session,
    conversation_id: int,
    before_id: int,
    *,
    role: str | None = None,
) -> list[ThreadItem]:
    stmt = (
        select(ThreadItem)
        .where(ThreadItem.thread_id == conversation_id)
        .where(ThreadItem.id < before_id)
    )
    if role is not None:
        stmt = stmt.where(ThreadItem.role == role)
    stmt = stmt.order_by(ThreadItem.id)
    return list(db.scalars(stmt).all())


def get_latest_message_with_role_before(
    db: Session,
    conversation_id: int,
    before_id: int,
    role: str,
) -> ThreadItem | None:
    return db.scalars(
        select(ThreadItem)
        .where(ThreadItem.thread_id == conversation_id)
        .where(ThreadItem.id < before_id)
        .where(ThreadItem.role == role)
        .order_by(ThreadItem.id.desc())
        .limit(1)
    ).first()


def count_messages_in_conversation(db: Session, conversation_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(ThreadItem)
        .where(ThreadItem.thread_id == conversation_id)
    ) or 0


def get_latest_message(db: Session, conversation_id: int) -> ThreadItem | None:
    return db.scalars(
        select(ThreadItem)
        .where(ThreadItem.thread_id == conversation_id)
        .order_by(ThreadItem.id.desc())
        .limit(1)
    ).first()


def get_user_memories(
    db: Session, user_id: int
) -> tuple:
    """Return (system_profile, manual_memories) for a user."""
    from sqlalchemy import select as _select
    from ai_portal.memory.model import UserMemory as UserMemoryModel

    system_profile = db.scalars(
        _select(UserMemoryModel)
        .where(
            UserMemoryModel.user_id == user_id,
            UserMemoryModel.is_system == True,  # noqa: E712
            UserMemoryModel.is_active == True,  # noqa: E712
        )
        .limit(1)
    ).first()
    manual_memories = list(
        db.scalars(
            _select(UserMemoryModel)
            .where(
                UserMemoryModel.user_id == user_id,
                UserMemoryModel.is_system == False,  # noqa: E712
                UserMemoryModel.is_active == True,  # noqa: E712
            )
            .order_by(UserMemoryModel.created_at)
        ).all()
    )
    return system_profile, manual_memories
