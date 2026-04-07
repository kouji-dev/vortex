"""Chat domain — business logic layer.

Streaming logic, history building, tool orchestration, memory operations.
Calls ``chat.repository`` for DB operations and ``services.*`` for cross-domain deps.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.api.assistants import _can_access_assistant
from ai_portal.chat import repository as repo
from ai_portal.chat.schemas import (
    ConversationRead,
    ConversationSettings,
    StreamMessageBody,
)
from ai_portal.workers.memory.extractor import extract_user_memories
from ai_portal.workers.memory.summarizer import summarize_conversation
from ai_portal.config import get_settings
from ai_portal.models import (
    Assistant,
    ChatConversation,
    ChatMessage,
    User,
)
from ai_portal.models.memory import UserMemory as UserMemoryModel
from ai_portal.services import llm as llm_svc
from ai_portal.services import rag as rag_svc
from ai_portal.services.conversation_model_resolve import (
    resolve_stored_model_to_chat_model,
)
from ai_portal.services.default_conversation_model import (
    default_conversation_settings,
    resolve_default_conversation_stored_model,
)
from ai_portal.tools.registry import ToolRegistry

_tool_registry = ToolRegistry()

logger = logging.getLogger(__name__)

# Stored in ``chat_conversations.title`` (column max 255); first prompt seeds title when unset.
_FIRST_PROMPT_TITLE_MAX_LEN = 128
_TITLE_ELLIPSIS = "..."

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


def _title_from_first_user_prompt(content: str) -> str:
    text = content.strip()
    if not text:
        return ""
    if len(text) <= _FIRST_PROMPT_TITLE_MAX_LEN:
        return text
    keep = _FIRST_PROMPT_TITLE_MAX_LEN - len(_TITLE_ELLIPSIS)
    return text[:keep] + _TITLE_ELLIPSIS


def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


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
    if cap.web_search:
        parts.append(
            "Web search: you have access to the web_search tool. "
            "Use it to find current information when needed."
        )
    if cap.data_query:
        parts.append(
            "Data analysis: you have access to the query_structured_data tool. "
            "Use it when the user shares CSV, JSON, or table data and asks questions about it."
        )
    if not parts:
        return ""
    return "\n\n[Conversation capabilities]\n" + "\n".join(f"- {p}" for p in parts)


def _build_memory_block(
    *,
    system_profile: UserMemoryModel | None,
    manual_memories: list[UserMemoryModel],
) -> str:
    """``system_profile`` is the optional single ``is_system`` row; manuals exclude it."""
    parts: list[str] = []
    if (
        system_profile is not None
        and getattr(system_profile, "content", "").strip()
        and system_profile.is_active
    ):
        parts.append(
            "User profile (auto-updated from your conversations):\n"
            + system_profile.content.strip()
        )
    manuals = [
        m
        for m in manual_memories
        if m.is_active and not m.is_system and (m.content or "").strip()
    ]
    if manuals:
        lines = "\n".join(f"- {m.content.strip()}" for m in manuals)
        parts.append(f"Memories the user saved manually:\n{lines}")
    if not parts:
        return ""
    return "What you know about this user:\n\n" + "\n\n".join(parts)


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
    if name in ("web_search", "query_structured_data"):
        return _tool_registry.dispatch(name, args)
    return {"role": "tool", "name": name, "content": f"Error: unknown tool '{name}'"}


def _should_summarize(
    *, message_count: int, base_window: int, summary_interval: int
) -> bool:
    if message_count <= base_window:
        return False
    excess = message_count - base_window
    return excess == 1 or excess % summary_interval == 0


def _slice_window_messages(
    messages: list[dict],
    *,
    base_window: int,
    summary_interval: int,
    has_summary: bool,
) -> list[dict]:
    n = len(messages)
    if n <= base_window:
        return messages
    if not has_summary:
        return messages[-base_window:]
    return messages[-summary_interval:]


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


def stream_message_svc(
    db: Session,
    user: User,
    conversation_id: int,
    body: StreamMessageBody,
) -> StreamingResponse:
    conv = repo.get_owned_conversation(db, user, conversation_id)
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
        conv.last_message_at = datetime.now(tz=UTC)
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

    prior = _slice_window_messages(
        prior,
        base_window=settings.conversation_base_window_size,
        summary_interval=settings.conversation_summary_interval,
        has_summary=bool(conv.summary),
    )

    kb_ids = repo.get_conversation_kb_ids(db, conv.id)

    system_parts: list[str] = []
    if assistant is not None:
        system_parts.append(assistant.system_prompt.strip())
    else:
        system_parts.append(settings.default_system_prompt.strip())

    if conv.summary:
        system_parts.append(f"Earlier in this conversation:\n{conv.summary}")

    system_profile, manual_memories = repo.get_user_memories(db, user.id)
    memory_block = _build_memory_block(
        system_profile=system_profile, manual_memories=manual_memories
    )
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

    cap = conv.settings.capabilities if conv.settings else None
    if cap and cap.web_search:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "web_search",
                    "description": (
                        "Search the web for current information. Use when the user asks about "
                        "recent events, facts you are unsure about, or anything requiring "
                        "up-to-date data."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "The search query"},
                            "num_results": {
                                "type": "integer",
                                "description": "Number of results to return. Default 5, max 10.",
                            },
                        },
                        "required": ["query"],
                    },
                },
            }
        )
    if cap and cap.data_query:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": "query_structured_data",
                    "description": (
                        "Answer questions about structured data (CSV, JSON, or table) "
                        "the user has provided in the conversation. Use for aggregations, "
                        "filtering, lookups, or comparisons."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "data": {
                                "type": "string",
                                "description": "The raw CSV, JSON, or table content to analyze",
                            },
                            "question": {
                                "type": "string",
                                "description": "The question to answer about the data",
                            },
                        },
                        "required": ["data", "question"],
                    },
                },
            }
        )

    cap_instr = _capability_instructions(conv.settings)
    if cap_instr:
        system_parts.append(cap_instr)

    system_content = "\n\n".join(p for p in system_parts if p)

    llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    llm_messages.extend(prior)
    llm_messages.append({"role": "user", "content": user_content})

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
        messages = list(llm_messages)
        max_iterations = settings.rag_max_tool_iterations
        iterations = 0
        thinking_started = False

        _active_memory_count = sum(
            1 for m in manual_memories if m.is_active and not m.is_system and (m.content or "").strip()
        ) + (1 if system_profile is not None and getattr(system_profile, "content", "").strip() and system_profile.is_active else 0)
        _has_tools = bool(tools)
        if _active_memory_count > 0 or _has_tools:
            yield _sse({"type": "item_start", "item": {"kind": "thinking"}})
            thinking_started = True
            if _active_memory_count > 0:
                yield _sse({"type": "item_start", "item": {"kind": "memory", "count": _active_memory_count}})
                yield _sse({"type": "item_done", "item": {"kind": "memory", "status": "done"}})

        while iterations <= max_iterations:
            full: list[str] = []
            tool_call_buffer: dict | None = None

            try:
                for piece in llm_svc.chat_completions_stream_with_tools(
                    messages, model=use_model, tools=tools if tools else None
                ):
                    if isinstance(piece, dict) and piece.get("type") == "tool_call":
                        tool_call_buffer = piece.get("tool_call")
                        _tool_name = tool_call_buffer.get("name", "")
                        try:
                            _tool_params = json.loads(tool_call_buffer.get("arguments", "{}"))
                        except Exception:
                            _tool_params = {}
                        yield _sse({
                            "type": "item_start",
                            "item": {"kind": "tool_call", "tool": _tool_name, "params": _tool_params},
                        })
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
                if thinking_started:
                    if tool_call_buffer:
                        yield _sse({
                            "type": "item_done",
                            "item": {"kind": "tool_call", "tool": tool_call_buffer.get("name", ""), "status": "done"},
                        })
                    yield _sse({"type": "item_done", "item": {"kind": "thinking"}})
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
                if thinking_started:
                    if tool_call_buffer:
                        yield _sse({
                            "type": "item_done",
                            "item": {"kind": "tool_call", "tool": tool_call_buffer.get("name", ""), "status": "done"},
                        })
                    yield _sse({"type": "item_done", "item": {"kind": "thinking"}})
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
                yield _sse({
                    "type": "item_done",
                    "item": {"kind": "tool_call", "tool": tool_call_buffer.get("name", ""), "status": "done"},
                })
                iterations += 1
                continue
            else:
                # Iteration cap reached — close the open tool item
                if tool_call_buffer:
                    yield _sse({
                        "type": "item_done",
                        "item": {"kind": "tool_call", "tool": tool_call_buffer.get("name", ""), "status": "done"},
                    })

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

            total_msgs = repo.count_messages_in_conversation(db, conv.id)
            if _should_summarize(
                message_count=total_msgs,
                base_window=settings.conversation_base_window_size,
                summary_interval=settings.conversation_summary_interval,
            ):
                threading.Thread(
                    target=summarize_conversation,
                    args=(conv.id,),
                    daemon=True,
                ).start()

            threading.Thread(
                target=extract_user_memories,
                kwargs={
                    "user_id": user.id,
                    "user_message": user_content,
                    "assistant_message": reply,
                },
                daemon=True,
            ).start()

            if thinking_started:
                yield _sse({"type": "item_done", "item": {"kind": "thinking"}})
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
