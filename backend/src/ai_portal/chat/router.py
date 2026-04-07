"""Chat domain — FastAPI router.

Routes only: parse request body, call service functions, return response schemas.
No direct DB queries, no business logic.
"""

from __future__ import annotations

import os
from typing import Annotated, Any

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ai_portal.api.deps import get_current_org_id, get_current_user, get_db
from ai_portal.chat import repository as repo
from ai_portal.chat import service as svc
from ai_portal.chat.schemas import (
    CapabilityProfileEntryRead,
    CapabilityProfileRead,
    ConversationCreate,
    ConversationKnowledgeBasesPut,
    ConversationPatch,
    ConversationRead,
    E2eSeedRagAssistantBody,
    MessagePatch,
    MessageRead,
    StreamMessageBody,
)
from ai_portal.config import get_settings
from ai_portal.models import (
    ChatMessage,
    User,
)

router = APIRouter(prefix="/api/chat", tags=["chat-conversations"])


@router.get("/starters")
def get_starters() -> dict[str, Any]:
    return svc.CHAT_STARTERS


@router.get("/capability-profile", response_model=CapabilityProfileRead)
def get_capability_profile(
    _user: Annotated[User, Depends(get_current_user)],
) -> CapabilityProfileRead:
    """UI copy for chat capability toggles (Add options menu)."""
    return CapabilityProfileRead(
        reflection=CapabilityProfileEntryRead(
            description=(
                "Note key assumptions and uncertainties before answering; adjust if you spot gaps."
            )
        ),
        research=CapabilityProfileEntryRead(
            description=(
                "Separate known facts from what would need verification; suggest concrete checks "
                "or sources the user could use."
            )
        ),
        web=CapabilityProfileEntryRead(
            description=(
                "No live web search is configured. If the answer depends on current events or "
                "post-training facts, say so and suggest how the user can verify."
            )
        ),
        web_search=CapabilityProfileEntryRead(
            description="Search the web in real time to answer questions about current events or recent information."
        ),
        data_query=CapabilityProfileEntryRead(
            description="Analyse CSV, JSON, or table data you share in the conversation."
        ),
    )


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ConversationRead]:
    convs = repo.list_conversations_for_user(db, user.id, org_id)
    return [svc.conversation_read(db, c) for c in convs]


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ConversationRead:
    return svc.create_conversation_svc(
        db=db,
        user=user,
        org_id=org_id,
        title=body.title,
        model=body.model,
        assistant_id=body.assistant_id,
        settings=body.settings,
        knowledge_base_ids=body.knowledge_base_ids,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ConversationRead:
    conv = repo.get_owned_conversation(db, user, conversation_id)
    return svc.conversation_read(db, conv)


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def patch_conversation(
    conversation_id: int,
    body: ConversationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ConversationRead:
    return svc.patch_conversation_svc(
        db=db,
        user=user,
        conversation_id=conversation_id,
        fields_set=body.model_fields_set,
        title=body.title,
        model=body.model,
        assistant_id=body.assistant_id,
        settings=body.settings,
    )


@router.put(
    "/conversations/{conversation_id}/knowledge-bases",
    response_model=ConversationRead,
)
def put_conversation_knowledge_bases(
    conversation_id: int,
    body: ConversationKnowledgeBasesPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ConversationRead:
    conv = repo.get_owned_conversation(db, user, conversation_id)
    conv = repo.sync_conversation_knowledge_links(db, conv, user, body.knowledge_base_ids)
    return svc.conversation_read(db, conv)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    conv = repo.get_owned_conversation(db, user, conversation_id)
    repo.delete_conversation(db, conv)


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageRead])
def list_messages(
    conversation_id: int,
    limit: int = 100,
    offset: int = 0,
    recent: Annotated[
        bool,
        Query(
            description=(
                "If true (default), return the latest `limit` messages in chronological order. "
                "Use `before_id` to load older pages. If false, use `offset` ascending from "
                "the oldest message (legacy)."
            ),
        ),
    ] = True,
    before_id: Annotated[
        int | None,
        Query(
            description=(
                "When `recent` is true, only messages with id strictly less than this value "
                "(older than `before_id`)."
            ),
        ),
    ] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ChatMessage]:
    repo.get_owned_conversation(db, user, conversation_id)
    return repo.list_messages_for_conversation(
        db,
        conversation_id,
        limit=limit,
        offset=offset,
        recent=recent,
        before_id=before_id,
    )


@router.patch(
    "/conversations/{conversation_id}/messages/{message_id}",
    response_model=MessageRead,
)
def patch_message(
    conversation_id: int,
    message_id: int,
    body: MessagePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ChatMessage:
    msg = repo.get_owned_message(db, user, conversation_id, message_id)
    msg = repo.update_message_content(db, msg, body.content)
    return msg


@router.delete(
    "/conversations/{conversation_id}/messages/{message_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_message(
    conversation_id: int,
    message_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> None:
    msg = repo.get_owned_message(db, user, conversation_id, message_id)
    repo.delete_message(db, msg)


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: int,
    body: StreamMessageBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> StreamingResponse:
    return svc.stream_message_svc(db=db, user=user, conversation_id=conversation_id, body=body)


def _e2e_rag_seed_allowed() -> bool:
    """Local Playwright only: ``E2E_ENABLE_RAG_SEED=1`` plus dev auth."""
    settings = get_settings()
    return settings.auth_mode == "dev" and os.environ.get("E2E_ENABLE_RAG_SEED", "").strip() == "1"


@router.post(
    "/conversations/{conversation_id}/e2e/seed-rag-assistant",
    status_code=status.HTTP_201_CREATED,
)
def e2e_seed_rag_assistant(
    conversation_id: int,
    body: E2eSeedRagAssistantBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> dict[str, Any]:
    """Insert user + two assistant rows: one without ``used_kbs``, one with (for KB indicator E2E)."""
    if not _e2e_rag_seed_allowed():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

    conv = repo.get_owned_conversation(db, user, conversation_id)
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    if body.kb_id not in kb_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="kb_id must be attached to this conversation",
        )

    _kb, _msg1, _msg2, msg3 = repo.seed_rag_conversation(
        db,
        conversation_id=conv.id,
        user=user,
        kb_id=body.kb_id,
        kb_name=body.kb_name,
        assistant_content=body.assistant_content,
    )
    return {"ok": True, "assistant_message_id": msg3.id}
