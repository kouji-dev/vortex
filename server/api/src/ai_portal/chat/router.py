"""Chat domain — FastAPI router.

Routes only: parse request body, call service functions, return response schemas.
No direct DB queries, no business logic.
"""

from __future__ import annotations

from typing import Annotated

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_org_id, get_current_user, get_db
from ai_portal.chat import repository as repo
from ai_portal.chat import service as svc
from ai_portal.chat.streaming.orchestrator import stream_turn
from ai_portal.core.db.session import get_async_db
from ai_portal.chat.schemas import (
    CapabilityProfileEntryRead,
    CapabilityProfileRead,
    ChatUploadRead,
    ConversationCreate,
    ConversationKnowledgeBasesPut,
    ConversationPatch,
    ConversationRead,
    StreamMessageBody,
    ThreadItemRead,
)
from ai_portal.core.config import get_settings
from ai_portal.auth.model import User
from ai_portal.chat.model import ThreadItem
from ai_portal.chat import upload_service as upload_svc

router = APIRouter(prefix="/api/chat", tags=["chat-conversations"])


@router.get("/capability-profile", response_model=CapabilityProfileRead)
def get_capability_profile(
    _user: Annotated[User, Depends(get_current_user)],
) -> CapabilityProfileRead:
    """UI copy for chat capability toggles (Add options menu)."""
    return CapabilityProfileRead(
        reflection=CapabilityProfileEntryRead(
            description=(
                "Deep thinking mode. The model challenges assumptions, gathers data via web search, "
                "and synthesises a well-reasoned conclusion."
            )
        ),
        research=CapabilityProfileEntryRead(
            description=(
                "Deep web research mode. Breaks the question into sub-questions, searches "
                "systematically, and returns a comprehensive, well-cited synthesis."
            )
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


@router.get("/conversations/{conversation_id}/messages", response_model=list[ThreadItemRead])
def list_messages(
    conversation_id: int,
    since_id: Annotated[
        int | None,
        Query(
            description="Return only items with id strictly greater than this value.",
        ),
    ] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> list[ThreadItem]:
    repo.get_owned_conversation(db, user, conversation_id)
    return repo.list_thread_items(
        db,
        thread_id=conversation_id,
        org_id=org_id,
        since_id=since_id,
    )


@router.post(
    "/conversations/{conversation_id}/uploads",
    response_model=ChatUploadRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    conversation_id: int,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> ChatUploadRead:
    """Upload a file attachment to a conversation. Returns a record the client can reference by id."""
    settings = get_settings()
    repo.get_owned_conversation(db, user, conversation_id)
    return await upload_svc.create_upload(
        db=db,
        user=user,
        org_id=org_id,
        thread_id=conversation_id,
        file=file,
        upload_dir=settings.upload_dir,
    )


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: int,
    body: StreamMessageBody,
    async_db: AsyncSession = Depends(get_async_db),
    user: User = Depends(get_current_user),
    org_id: _uuid.UUID = Depends(get_current_org_id),
) -> StreamingResponse:
    return await stream_turn(
        session=async_db,
        user=user,
        thread_id=conversation_id,
        body={
            "text": body.content,
            "attachments": [{"id": aid} for aid in (body.attachment_ids or [])],
            "model": body.model,
            "regenerate_from_turn_id": body.regenerate_after_message_id,
            "use_rag": body.use_rag,
            "capabilities": body.capabilities,
            "tools": body.tools,
        },
    )


