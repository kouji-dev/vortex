"""
Chat conversations API.

Browser ↔ API uses **SSE** (``StreamingResponse`` + ``text/event-stream``) for token streaming.

**Azure / scale:** API replicas stay stateless (each stream is one HTTP request). Raise **idle
timeouts** on Front Door, App Gateway, or Container Apps ingress above your P95 stream length.
Throughput to the model is bounded by **Azure OpenAI PTU/TPM** per deployment/region—add
deployments, regions, or a gateway queue for heavy load—not by replacing SSE with WebSockets.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated, Any, Self

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ai_portal.api.assistants import _can_access_assistant
from ai_portal.api.deps import get_current_user, get_db
from ai_portal.config import get_settings
from ai_portal.models import (
    Assistant,
    ChatConversation,
    ChatMessage,
    ConversationKnowledgeBase,
    KnowledgeBase,
    User,
)
from ai_portal.models.memory import UserMemory as UserMemoryModel
from ai_portal.schemas.conversation_settings import ConversationSettings
from ai_portal.services import llm as llm_svc
from ai_portal.services import rag as rag_svc
from ai_portal.services.conversation_model_resolve import (
    resolve_stored_model_to_chat_model,
)
from ai_portal.services.default_conversation_model import (
    default_conversation_settings,
    resolve_default_conversation_stored_model,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat-conversations"])

# Stored in ``chat_conversations.title`` (column max 255); first prompt seeds title when unset.
_FIRST_PROMPT_TITLE_MAX_LEN = 128
_TITLE_ELLIPSIS = "..."


def _title_from_first_user_prompt(content: str) -> str:
    text = content.strip()
    if not text:
        return ""
    if len(text) <= _FIRST_PROMPT_TITLE_MAX_LEN:
        return text
    keep = _FIRST_PROMPT_TITLE_MAX_LEN - len(_TITLE_ELLIPSIS)
    return text[:keep] + _TITLE_ELLIPSIS


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


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _get_owned_conversation(
    db: Session, user: User, conversation_id: int
) -> ChatConversation:
    conv = db.get(ChatConversation, conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conv


def _get_owned_message(
    db: Session, user: User, conversation_id: int, message_id: int
) -> ChatMessage:
    _get_owned_conversation(db, user, conversation_id)
    msg = db.get(ChatMessage, message_id)
    if msg is None or msg.conversation_id != conversation_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Message not found")
    return msg


def _sync_conversation_knowledge_links(
    db: Session,
    conv: ChatConversation,
    user: User,
    knowledge_base_ids: list[int],
) -> None:
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


def _capability_instructions(st: ConversationSettings | None) -> str:
    if st is None or st.capabilities is None:
        return ""
    cap = st.capabilities
    parts: list[str] = []
    if cap.reflection:
        parts.append(
            "Reflection: note key assumptions and uncertainties before answering; adjust if "
            "you spot gaps."
        )
    if cap.research:
        parts.append(
            "Research mindset: separate known facts from what would need verification; suggest "
            "concrete checks or sources the user could use."
        )
    if cap.web:
        parts.append(
            "Recency: you have no live web access. If the answer depends on current events or "
            "post-training facts, say so and suggest how the user can verify."
        )
    if not parts:
        return ""
    return "\n\n[Conversation capabilities]\n" + "\n".join(f"- {p}" for p in parts)


def _build_memory_block(memories: list) -> str:
    active = [m for m in memories if m.is_active]
    if not active:
        return ""
    lines = "\n".join(f"- {m.content}" for m in active)
    return f"What you know about this user:\n{lines}"


def _dispatch_tool_call(
    db: Session,
    tool_call: dict,
    *,
    kb_ids: list[int],
) -> dict:
    """Execute a tool call emitted by the LLM. Returns tool result dict."""
    name = tool_call.get("name", "")
    try:
        args = json.loads(tool_call.get("arguments", "{}"))
    except Exception:
        args = {}

    if name == "search_knowledge_base":
        query = args.get("query", "")
        requested_kb_ids = args.get("kb_ids") or kb_ids
        result = rag_svc.search_knowledge_base_tool(
            db=db, query=query, kb_ids=requested_kb_ids, top_k=args.get("top_k"),
        )
        return {
            "role": "tool",
            "name": name,
            "content": result["context"],
            "_used_kbs": result.get("used_kbs", []),
            "_citations": result.get("citations", []),
        }
    return {"role": "tool", "name": name, "content": f"Error: unknown tool '{name}'"}


def _should_summarize(*, message_count: int, window_size: int) -> bool:
    return message_count > 0 and message_count % window_size == 0


def _slice_window_messages(messages: list[dict], *, window_size: int) -> list[dict]:
    return messages[-window_size:] if len(messages) > window_size else messages


class ConversationCreate(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    assistant_id: int | None = None
    settings: ConversationSettings | None = None
    knowledge_base_ids: list[int] = Field(default_factory=list)


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, max_length=255)
    model: str | None = Field(default=None, max_length=128)
    assistant_id: int | None = None
    settings: ConversationSettings | None = None


class ConversationRead(BaseModel):
    id: int
    user_id: int
    assistant_id: int | None
    title: str | None
    model: str | None
    settings: ConversationSettings | None
    created_at: Any
    knowledge_base_ids: list[int] = Field(default_factory=list)


def _conversation_read(db: Session, conv: ChatConversation) -> ConversationRead:
    kb_ids = list(
        db.scalars(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conv.id
            )
        ).all()
    )
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


class MessageRead(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    created_at: Any
    extra: dict | None

    model_config = {"from_attributes": True}


class MessagePatch(BaseModel):
    content: str = Field(min_length=1, max_length=500_000)


class ConversationKnowledgeBasesPut(BaseModel):
    knowledge_base_ids: list[int] = Field(default_factory=list)


class StreamMessageBody(BaseModel):
    content: str = Field(default="", max_length=500_000)
    regenerate_after_message_id: int | None = None
    model: str | None = Field(default=None, max_length=128)
    use_rag: bool = False

    @model_validator(mode="after")
    def content_or_regenerate(self) -> Self:
        if self.regenerate_after_message_id is None and not self.content.strip():
            raise ValueError("content is required unless regenerating a reply")
        return self


@router.get("/starters")
def get_starters() -> dict[str, Any]:
    return CHAT_STARTERS


@router.get("/conversations", response_model=list[ConversationRead])
def list_conversations(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ConversationRead]:
    convs = list(
        db.scalars(
            select(ChatConversation)
            .where(ChatConversation.user_id == user.id)
            .order_by(ChatConversation.id.desc())
        ).all()
    )
    return [_conversation_read(db, c) for c in convs]


@router.post("/conversations", response_model=ConversationRead, status_code=status.HTTP_201_CREATED)
def create_conversation(
    body: ConversationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationRead:
    if body.assistant_id is not None:
        a = db.get(Assistant, body.assistant_id)
        if a is None or not _can_access_assistant(db, user, a):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")
    model_raw = (body.model or "").strip() or None
    model_val = model_raw or resolve_default_conversation_stored_model(db)
    settings_val = (
        body.settings
        if body.settings is not None
        else default_conversation_settings()
    )
    conv = ChatConversation(
        user_id=user.id,
        assistant_id=body.assistant_id,
        title=body.title,
        model=model_val,
        settings=settings_val,
    )
    db.add(conv)
    db.flush()
    if body.knowledge_base_ids:
        _sync_conversation_knowledge_links(db, conv, user, body.knowledge_base_ids)
    db.commit()
    db.refresh(conv)
    return _conversation_read(db, conv)


@router.get("/conversations/{conversation_id}", response_model=ConversationRead)
def get_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationRead:
    conv = _get_owned_conversation(db, user, conversation_id)
    return _conversation_read(db, conv)


@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)
def patch_conversation(
    conversation_id: int,
    body: ConversationPatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationRead:
    conv = _get_owned_conversation(db, user, conversation_id)
    if "title" in body.model_fields_set:
        conv.title = body.title
    if "model" in body.model_fields_set:
        conv.model = body.model
    if "assistant_id" in body.model_fields_set:
        if body.assistant_id is not None:
            a = db.get(Assistant, body.assistant_id)
            if a is None or not _can_access_assistant(db, user, a):
                raise HTTPException(
                    status.HTTP_404_NOT_FOUND, detail="Assistant not found"
                )
        conv.assistant_id = body.assistant_id
    if "settings" in body.model_fields_set:
        conv.settings = body.settings
    db.commit()
    db.refresh(conv)
    return _conversation_read(db, conv)


@router.put(
    "/conversations/{conversation_id}/knowledge-bases",
    response_model=ConversationRead,
)
def put_conversation_knowledge_bases(
    conversation_id: int,
    body: ConversationKnowledgeBasesPut,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ConversationRead:
    conv = _get_owned_conversation(db, user, conversation_id)
    _sync_conversation_knowledge_links(db, conv, user, body.knowledge_base_ids)
    db.commit()
    db.refresh(conv)
    return _conversation_read(db, conv)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    conv = _get_owned_conversation(db, user, conversation_id)
    db.delete(conv)
    db.commit()


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
) -> list[ChatMessage]:
    _get_owned_conversation(db, user, conversation_id)
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
) -> ChatMessage:
    msg = _get_owned_message(db, user, conversation_id, message_id)
    msg.content = body.content.strip()
    db.commit()
    db.refresh(msg)
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
) -> None:
    msg = _get_owned_message(db, user, conversation_id, message_id)
    db.delete(msg)
    db.commit()


@router.post("/conversations/{conversation_id}/messages/stream")
def stream_message(
    conversation_id: int,
    body: StreamMessageBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    conv = _get_owned_conversation(db, user, conversation_id)
    settings = get_settings()

    assistant: Assistant | None = None
    if conv.assistant_id is not None:
        assistant = db.get(Assistant, conv.assistant_id)
        if assistant is None or not _can_access_assistant(db, user, assistant):
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assistant not found")

    if body.regenerate_after_message_id is not None:
        asst_msg = db.get(ChatMessage, body.regenerate_after_message_id)
        if (
            asst_msg is None
            or asst_msg.conversation_id != conv.id
            or asst_msg.role != "assistant"
        ):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Invalid regenerate target message",
            )
        latest = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv.id)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).first()
        if latest is None or latest.id != asst_msg.id:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="Can only regenerate the latest assistant message",
            )
        user_row = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv.id)
            .where(ChatMessage.id < asst_msg.id)
            .where(ChatMessage.role == "user")
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).first()
        if user_row is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                detail="No user message found before this assistant reply",
            )
        user_content = user_row.content.strip()
        anchor_id = user_row.id
        db.delete(asst_msg)
        db.commit()
        prior_rows = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv.id)
            .where(ChatMessage.id < anchor_id)
            .order_by(ChatMessage.id)
        ).all()
    else:
        user_content = body.content.strip()
        user_msg = ChatMessage(
            conversation_id=conv.id, role="user", content=user_content
        )
        db.add(user_msg)
        from datetime import datetime

        conv.last_message_at = datetime.now(tz=datetime.UTC)
        if not conv.title:
            conv.title = _title_from_first_user_prompt(user_content) or None
        db.commit()
        db.refresh(user_msg)
        anchor_id = user_msg.id
        prior_rows = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv.id)
            .where(ChatMessage.id < anchor_id)
            .order_by(ChatMessage.id)
        ).all()

    prior: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in prior_rows
    ]

    prior = _slice_window_messages(prior, window_size=settings.conversation_window_size)

    kb_ids = list(
        db.scalars(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conv.id
            )
        ).all()
    )

    system_parts: list[str] = []
    if assistant is not None:
        system_parts.append(assistant.system_prompt.strip())
    else:
        system_parts.append(settings.default_system_prompt.strip())

    if conv.summary:
        system_parts.append(f"Earlier in this conversation:\n{conv.summary}")

    active_memories = list(
        db.scalars(
            select(UserMemoryModel)
            .where(UserMemoryModel.user_id == user.id, UserMemoryModel.is_active == True)  # noqa: E712
            .order_by(UserMemoryModel.created_at)
        ).all()
    )
    memory_block = _build_memory_block(active_memories)
    if memory_block:
        system_parts.append(memory_block)

    tools: list[dict[str, Any]] = []
    if kb_ids:
        system_parts.append(
            "You have access to the search_knowledge_base tool. "
            "Use it when you need information from the user's documents to answer accurately. "
            "When using retrieved context, cite sources as [Source: filename, section]."
        )
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_knowledge_base",
                    "description": (
                        "Search attached knowledge bases for relevant context. "
                        "Call when you need document information."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query",
                            },
                            "kb_ids": {
                                "type": "array",
                                "items": {"type": "integer"},
                                "description": "KB IDs to search",
                            },
                            "top_k": {
                                "type": "integer",
                                "description": "Optional: number of results",
                            },
                        },
                        "required": ["query", "kb_ids"],
                    },
                },
            }
        ]

    cap_instr = _capability_instructions(conv.settings)
    if cap_instr:
        system_parts.append(cap_instr)

    system_content = "\n\n".join(p for p in system_parts if p)

    openai_messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    openai_messages.extend(prior)
    openai_messages.append({"role": "user", "content": user_content})

    stored_model = (
        body.model or conv.model or settings.chat_default_api_model or ""
    ).strip()
    if not stored_model:
        use_model = None
    else:
        use_model = resolve_stored_model_to_chat_model(db, stored_model)

    def _tail_message_id() -> int:
        last = db.scalars(
            select(ChatMessage)
            .where(ChatMessage.conversation_id == conv.id)
            .order_by(ChatMessage.id.desc())
            .limit(1)
        ).first()
        return last.id if last else 0

    def gen() -> Any:
        used_kbs_meta: list[dict] = []
        messages = list(openai_messages)
        max_iterations = settings.rag_max_tool_iterations
        iterations = 0

        while iterations <= max_iterations:
            full: list[str] = []
            tool_call_buffer: dict | None = None

            try:
                for piece in llm_svc.chat_completions_stream_with_tools(
                    messages, model=use_model, tools=tools if tools else None
                ):
                    if isinstance(piece, dict) and piece.get("type") == "tool_call":
                        tool_call_buffer = piece.get("tool_call")
                        yield _sse(
                            {"type": "tool_call", "name": tool_call_buffer.get("name", "")}
                        )
                    elif isinstance(piece, dict) and piece.get("type") == "delta":
                        text = piece.get("text", "")
                        full.append(text)
                        yield _sse({"type": "delta", "text": text})
                    else:
                        full.append(str(piece))
                        yield _sse({"type": "delta", "text": str(piece)})
            except ValueError as e:
                detail = str(e)
                db.add(
                    ChatMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=f"**Error:** {detail}",
                    )
                )
                db.commit()
                yield _sse({"type": "error", "detail": detail})
                yield _sse({"type": "done", "message_id": _tail_message_id()})
                return
            except Exception:
                logger.exception("chat_stream_failed")
                detail = "Upstream model error"
                db.add(
                    ChatMessage(
                        conversation_id=conv.id,
                        role="assistant",
                        content=f"**Error:** {detail}",
                    )
                )
                db.commit()
                yield _sse({"type": "error", "detail": detail})
                yield _sse({"type": "done", "message_id": _tail_message_id()})
                return

            if tool_call_buffer and iterations < max_iterations:
                tool_result = _dispatch_tool_call(db, tool_call_buffer, kb_ids=kb_ids)
                used_kbs_meta.extend(tool_result.get("_used_kbs", []))
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "tc_0",
                                "type": "function",
                                "function": tool_call_buffer,
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": "tc_0",
                        "name": tool_result["name"],
                        "content": tool_result["content"],
                    }
                )
                iterations += 1
                continue

            reply = "".join(full)
            db.add(
                ChatMessage(
                    conversation_id=conv.id,
                    role="assistant",
                    content=reply,
                    extra={"used_kbs": used_kbs_meta} if used_kbs_meta else None,
                )
            )
            db.commit()

            from sqlalchemy import func as sa_func

            total_msgs = db.scalar(
                select(sa_func.count())
                .select_from(ChatMessage)
                .where(ChatMessage.conversation_id == conv.id)
            )
            if _should_summarize(
                message_count=total_msgs,
                window_size=settings.conversation_window_size,
            ):
                import threading

                from ai_portal.workers.memory.summarizer import (
                    summarize_conversation,
                )

                threading.Thread(
                    target=summarize_conversation,
                    args=(conv.id,),
                    daemon=True,
                ).start()

            import threading as _thr

            from ai_portal.workers.memory.extractor import extract_user_memories

            _thr.Thread(
                target=extract_user_memories,
                kwargs={
                    "user_id": user.id,
                    "user_message": user_content,
                    "assistant_message": reply,
                },
                daemon=True,
            ).start()

            yield _sse({"type": "done", "message_id": _tail_message_id()})
            return

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _e2e_rag_seed_allowed() -> bool:
    """Local Playwright only: ``E2E_ENABLE_RAG_SEED=1`` plus dev auth."""
    settings = get_settings()
    return settings.auth_mode == "dev" and os.environ.get("E2E_ENABLE_RAG_SEED", "").strip() == "1"


class E2eSeedRagAssistantBody(BaseModel):
    kb_id: int
    kb_name: str = "Knowledge base"
    assistant_content: str = Field(
        default="This reply is grounded in your attached knowledge base (E2E seed).",
        max_length=500_000,
    )


@router.post(
    "/conversations/{conversation_id}/e2e/seed-rag-assistant",
    status_code=status.HTTP_201_CREATED,
)
def e2e_seed_rag_assistant(
    conversation_id: int,
    body: E2eSeedRagAssistantBody,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Insert user + two assistant rows: one without ``used_kbs``, one with (for KB indicator E2E)."""
    if not _e2e_rag_seed_allowed():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Not found")

    conv = _get_owned_conversation(db, user, conversation_id)
    kb_ids = list(
        db.scalars(
            select(ConversationKnowledgeBase.knowledge_base_id).where(
                ConversationKnowledgeBase.conversation_id == conv.id
            )
        ).all()
    )
    if body.kb_id not in kb_ids:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="kb_id must be attached to this conversation",
        )

    kb = db.get(KnowledgeBase, body.kb_id)
    if kb is None or kb.owner_user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Knowledge base not found")

    used_kbs_meta: list[dict[str, Any]] = [
        {
            "kb_id": body.kb_id,
            "kb_name": body.kb_name,
            "chunks_used": 2,
            "top_score": 0.88,
            "sections": ["E2E section"],
        }
    ]

    db.add(
        ChatMessage(
            conversation_id=conv.id,
            role="user",
            content="E2E: what does the knowledge base say?",
        )
    )
    db.add(
        ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content="A short reply without retrieval metadata.",
            extra=None,
        )
    )
    db.add(
        ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=body.assistant_content,
            extra={"used_kbs": used_kbs_meta},
        )
    )
    db.commit()

    last = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == conv.id)
        .order_by(ChatMessage.id.desc())
        .limit(1)
    ).first()
    return {"ok": True, "assistant_message_id": last.id if last else None}
