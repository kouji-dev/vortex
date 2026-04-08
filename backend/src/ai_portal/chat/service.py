"""Chat domain — business logic layer.

Conversation CRUD operations. Streaming logic lives in ``streaming_service``.
"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.api.assistants import _can_access_assistant
from ai_portal.assistant.model import Assistant
from ai_portal.auth.model import User
from ai_portal.catalog.service import (
    default_conversation_settings,
    resolve_default_conversation_stored_model,
)
from ai_portal.chat import repository as repo
from ai_portal.chat.model import ChatConversation
from ai_portal.chat.schemas import (
    ConversationRead,
    ConversationSettings,
)

CHAT_STARTERS: dict[str, Any] = {
    "sections": [
        {
            "title": "Starters",
            "prompts": [
                "Summarize the key risks in this design in 5 bullets.",
                "Draft a concise PR description from these changes.",
                "Explain this error and suggest the next debugging step.",
            ],
            "links": [],
        },
    ],
}


def conversation_read(db: Session, conv: ChatConversation) -> ConversationRead:
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    return ConversationRead(
        id=conv.id,
        user_id=conv.user_id,
        assistant_id=conv.assistant_id,
        title=conv.title,
        model=conv.model,
        settings=conv.settings,
        created_at=conv.created_at,
        knowledge_base_ids=kb_ids,
    )


def create_conversation_svc(
    db: Session,
    user: User,
    org_id: Any,
    title: str | None,
    model: str | None,
    assistant_id: int | None,
    settings: ConversationSettings | None,
    knowledge_base_ids: list[int],
) -> ConversationRead:
    if assistant_id is not None:
        a = db.get(Assistant, assistant_id)
        if a is None or not _can_access_assistant(db, user, a):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    model_raw = (model or "").strip() or None
    model_val = model_raw or resolve_default_conversation_stored_model(db)
    settings_val = (
        settings
        if settings is not None
        else default_conversation_settings()
    )
    conv = ChatConversation(
        user_id=user.id,
        org_id=org_id,
        assistant_id=assistant_id,
        title=title,
        model=model_val,
        settings=settings_val,
    )
    db.add(conv)
    db.flush()
    if knowledge_base_ids:
        repo.sync_conversation_knowledge_links(db, conv, user, knowledge_base_ids)
    db.commit()
    db.refresh(conv)
    return conversation_read(db, conv)


def patch_conversation_svc(
    db: Session,
    user: User,
    conversation_id: int,
    fields_set: set[str],
    title: str | None,
    model: str | None,
    assistant_id: int | None,
    settings: ConversationSettings | None,
) -> ConversationRead:
    conv = repo.get_owned_conversation(db, user, conversation_id)
    if "title" in fields_set:
        conv.title = title
    if "model" in fields_set:
        conv.model = model
    if "assistant_id" in fields_set:
        if assistant_id is not None:
            a = db.get(Assistant, assistant_id)
            if a is None or not _can_access_assistant(db, user, a):
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Assistant not found"
                )
        conv.assistant_id = assistant_id
    if "settings" in fields_set:
        conv.settings = settings
    db.commit()
    db.refresh(conv)
    return conversation_read(db, conv)


# Re-export so existing callers (router + tests) don't need changes.
from ai_portal.chat.streaming_service import stream_message_svc  # noqa: F401
from ai_portal.chat.streaming_service import (  # noqa: F401
    _build_memory_block,
    _should_summarize,
    _slice_window_messages,
    _title_from_first_user_prompt,
    _capability_instructions,
    _sse,
)
from ai_portal.chat.tool_service import _dispatch_tool_call  # noqa: F401
