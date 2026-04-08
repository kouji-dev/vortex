"""Chat domain — database query layer.

All functions here take a ``db: Session`` as first argument and return ORM objects
or plain Python values.  No business logic, no HTTP concerns.
"""

from __future__ import annotations

import uuid as _uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from ai_portal.assistant.model import Assistant
from ai_portal.auth.model import User
from ai_portal.chat.model import ChatConversation, ChatMessage
from ai_portal.memory.model import UserMemory as UserMemoryModel
from ai_portal.knowledge_base.model import ConversationKnowledgeBase, KnowledgeBase


# ---------------------------------------------------------------------------
# Conversation helpers
# ---------------------------------------------------------------------------

def get_owned_conversation(
    db: Session, user: User, conversation_id: int
) -> ChatConversation:
    conv = db.get(ChatConversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def get_owned_message(
    db: Session, user: User, conversation_id: int, message_id: int
) -> ChatMessage:
    get_owned_conversation(db, user, conversation_id)
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.conversation_id != conversation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found")
    return msg


def list_conversations_for_user(
    db: Session, user_id: int, org_id: _uuid.UUID
) -> list[ChatConversation]:
    return list(
        db.scalars(
            select(ChatConversation)
            .where(ChatConversation.user_id == user_id)
            .where(ChatConversation.org_id == org_id)
            .order_by(ChatConversation.id.desc())
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
    conv: ChatConversation,
    user: User,
    knowledge_base_ids: list[int],
) -> ChatConversation:
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


def delete_conversation(db: Session, conv: ChatConversation) -> None:
    db.delete(conv)
    db.commit()


def update_message_content(db: Session, msg: ChatMessage, content: str) -> ChatMessage:
    msg.content = content.strip()
    db.commit()
    db.refresh(msg)
    return msg


def delete_message(db: Session, msg: ChatMessage) -> None:
    db.delete(msg)
    db.commit()


def seed_rag_conversation(
    db: Session,
    *,
    conversation_id: int,
    user: User,
    kb_id: int,
    kb_name: str,
    assistant_content: str,
) -> tuple[KnowledgeBase, ChatMessage, ChatMessage, ChatMessage]:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None or kb.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    used_kbs_meta: list[dict] = [
        {
            "kb_id": kb_id,
            "kb_name": kb_name,
            "chunks_used": 2,
            "top_score": 0.88,
            "sections": ["E2E section"],
        }
    ]

    msg1 = ChatMessage(
        conversation_id=conversation_id,
        role="user",
        content="E2E: what does the knowledge base say?",
    )
    msg2 = ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content="A short reply without retrieval metadata.",
        extra=None,
    )
    msg3 = ChatMessage(
        conversation_id=conversation_id,
        role="assistant",
        content=assistant_content,
        extra={"used_kbs": used_kbs_meta},
    )
    db.add(msg1)
    db.add(msg2)
    db.add(msg3)
    db.commit()
    db.refresh(msg1)
    db.refresh(msg2)
    db.refresh(msg3)
    return kb, msg1, msg2, msg3


def get_messages_before(
    db: Session,
    conversation_id: int,
    before_id: int,
    *,
    role: str | None = None,
) -> list[ChatMessage]:
    stmt = (
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .where(ChatMessage.id < before_id)
    )
    if role is not None:
        stmt = stmt.where(ChatMessage.role == role)
    stmt = stmt.order_by(ChatMessage.id)
    return list(db.scalars(stmt).all())


def get_latest_message_with_role_before(
    db: Session,
    conversation_id: int,
    before_id: int,
    role: str,
) -> ChatMessage | None:
    return db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .where(ChatMessage.id < before_id)
        .where(ChatMessage.role == role)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    ).first()


def get_assistant_for_user(
    db: Session, user: User, assistant_id: int
) -> Assistant | None:
    return db.get(Assistant, assistant_id)


def list_messages_for_conversation(
    db: Session,
    conversation_id: int,
    *,
    limit: int,
    offset: int,
    recent: bool,
    before_id: int | None,
) -> list[ChatMessage]:
    lim = min(max(limit, 1), 500)
    off = max(offset, 0)
    base = select(ChatMessage).where(ChatMessage.conversation_id == conversation_id)
    if recent:
        stmt = base
        if before_id is not None:
            stmt = stmt.where(ChatMessage.id < before_id)
        stmt = stmt.order_by(ChatMessage.id.desc()).limit(lim)
        rows = list(db.scalars(stmt).all())
        rows.reverse()
        return rows
    return list(
        db.scalars(
            base.order_by(ChatMessage.id).offset(off).limit(lim)
        ).all()
    )


def count_messages_in_conversation(db: Session, conversation_id: int) -> int:
    return db.scalar(
        select(sa_func.count())
        .select_from(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
    )


def get_latest_message(db: Session, conversation_id: int) -> ChatMessage | None:
    return db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conversation_id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    ).first()


def get_user_memories(
    db: Session, user_id: int
) -> tuple[UserMemoryModel | None, list[UserMemoryModel]]:
    """Return (system_profile, manual_memories) for a user."""
    system_profile = db.scalars(
        select(UserMemoryModel)
        .where(
            UserMemoryModel.user_id == user_id,
            UserMemoryModel.is_system == True,  # noqa: E712
            UserMemoryModel.is_active == True,  # noqa: E712
        )
        .limit(1)
    ).first()
    manual_memories = list(
        db.scalars(
            select(UserMemoryModel)
            .where(
                UserMemoryModel.user_id == user_id,
                UserMemoryModel.is_system == False,  # noqa: E712
                UserMemoryModel.is_active == True,  # noqa: E712
            )
            .order_by(UserMemoryModel.created_at)
        ).all()
    )
    return system_profile, manual_memories
