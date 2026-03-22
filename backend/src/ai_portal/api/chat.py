from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.assistants import _can_access_assistant
from ai_portal.api.deps import get_current_user, get_db
from ai_portal.models import Assistant, ChatMessage, ChatSession, User
from ai_portal.services import embedding as embedding_svc
from ai_portal.services import llm as llm_svc
from ai_portal.services import rag as rag_svc

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatMessageIn(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    assistant_id: int
    messages: list[ChatMessageIn]
    session_id: int | None = None
    use_rag: bool = True


class ChatResponse(BaseModel):
    session_id: int
    reply: str


@router.post("", response_model=ChatResponse)
def post_chat(
    body: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ChatResponse:
    assistant = db.get(Assistant, body.assistant_id)
    if assistant is None or not _can_access_assistant(db, user, assistant):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")

    if body.session_id is not None:
        session = db.get(ChatSession, body.session_id)
        if (
            session is None
            or session.user_id != user.id
            or session.assistant_id != assistant.id
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="Invalid session")
    else:
        session = ChatSession(user_id=user.id, assistant_id=assistant.id)
        db.add(session)
        db.commit()
        db.refresh(session)

    prior_rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.session_id == session.id)
        .order_by(ChatMessage.id)
    ).all()
    prior: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in prior_rows
    ]

    for m in body.messages:
        db.add(ChatMessage(session_id=session.id, role=m.role, content=m.content))
    db.commit()

    rag_block = ""
    if body.use_rag:
        last_user = next(
            (m.content for m in reversed(body.messages) if m.role == "user"),
            "",
        )
        if last_user.strip():
            try:
                q_emb = embedding_svc.embed_texts([last_user])[0]
                rag_block = rag_svc.retrieve_context(
                    db, assistant_id=assistant.id, query_embedding=q_emb
                )
            except ValueError:
                logger.warning("rag_skipped_no_embedding_key")

    system_parts = [assistant.system_prompt.strip()]
    if rag_block:
        system_parts.append(
            "Use the following context when answering. If it is insufficient, say so.\n\n"
            + rag_block
        )
    system_content = "\n\n".join(p for p in system_parts if p)

    openai_messages: list[dict[str, str]] = [{"role": "system", "content": system_content}]
    openai_messages.extend(prior)
    openai_messages.extend({"role": m.role, "content": m.content} for m in body.messages)

    try:
        raw = llm_svc.chat_completions(openai_messages)
    except ValueError as e:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.exception("chat_completion_failed")
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Upstream model error",
        ) from e

    try:
        reply = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as e:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail="Unexpected model response",
        ) from e

    db.add(ChatMessage(session_id=session.id, role="assistant", content=reply))
    db.commit()

    return ChatResponse(session_id=session.id, reply=reply)
