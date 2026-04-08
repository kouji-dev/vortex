"""Chat domain — streaming message orchestration.

Coordinates the full streaming flow: message setup, context assembly,
LLM invocation, tool loop, persistence, and background tasks.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid as _uuid_mod
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ai_portal.assistant.router import _can_access_assistant
from ai_portal.assistant.model import Assistant  # kept for type annotation
from ai_portal.auth.model import User
from ai_portal.catalog.providers import get_chat_provider
from ai_portal.catalog.service import resolve_stored_model_to_chat_model
from ai_portal.chat import repository as repo
from ai_portal.chat import upload_service as upload_svc
import ai_portal.chat.capabilities.registry as capability_registry
import ai_portal.tools.registry as tool_registry
from ai_portal.chat.context_window import should_summarize, slice_window_messages
from ai_portal.chat.memory_context import build_memory_block
from ai_portal.chat.model import ChatConversation, ChatMessage
from ai_portal.chat.schemas import StreamMessageBody
from ai_portal.chat.tool_service import _dispatch_tool_call
from ai_portal.memory.workers.extractor import extract_user_memories
from ai_portal.memory.workers.summarizer import summarize_conversation
from ai_portal.core.config import get_settings

logger = logging.getLogger(__name__)

_FIRST_PROMPT_TITLE_MAX_LEN = 128
_TITLE_ELLIPSIS = "..."


# ---------------------------------------------------------------------------
# SSE helpers
# ---------------------------------------------------------------------------

def _sse(obj: dict[str, Any]) -> str:
    return f"data: {json.dumps(obj)}\n\n"


def _title_from_first_user_prompt(content: str) -> str:
    text = content.strip()
    if not text:
        return ""
    if len(text) <= _FIRST_PROMPT_TITLE_MAX_LEN:
        return text
    keep = _FIRST_PROMPT_TITLE_MAX_LEN - len(_TITLE_ELLIPSIS)
    return text[:keep] + _TITLE_ELLIPSIS


# ---------------------------------------------------------------------------
# Main streaming entry point
# ---------------------------------------------------------------------------

def stream_message_svc(
    db: Session,
    user: User,
    conversation_id: int,
    body: StreamMessageBody,
) -> StreamingResponse:
    conv = repo.get_owned_conversation(db, user, conversation_id)
    settings = get_settings()

    # ── Resolve assistant ────────────────────────────────────────────────────
    assistant: Assistant | None = None
    if conv.assistant_id is not None:
        assistant = _can_access_assistant(conv.assistant_id, user, conv.org_id, db)

    # ── Resolve user message + prior history ────────────────────────────────
    user_content, anchor_id, prior_rows = _setup_user_message(db, conv, body, user)

    # ── Context window ───────────────────────────────────────────────────────
    prior: list[dict[str, str]] = [
        {"role": m.role, "content": m.content} for m in prior_rows
    ]
    prior = slice_window_messages(
        prior,
        base_window=settings.conversation_base_window_size,
        summary_interval=settings.conversation_summary_interval,
        has_summary=bool(conv.summary),
    )

    # ── Memories ─────────────────────────────────────────────────────────────
    system_profile, manual_memories = repo.get_user_memories(db, user.id)
    memory_block = build_memory_block(
        system_profile=system_profile,
        manual_memories=manual_memories,
    )

    # ── Tool definitions ─────────────────────────────────────────────────────
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    tools = tool_registry.get_tool_definitions(kb_ids)
    max_iter = capability_registry.get_max_iterations(
        conv.settings, base=settings.rag_max_tool_iterations
    )

    # ── System prompt ────────────────────────────────────────────────────────
    extra_prompts = (
        tool_registry.get_system_prompts(kb_ids)
        + capability_registry.get_system_prompts(conv.settings)
    )
    system_content = _build_system_prompt(
        assistant=assistant,
        conv=conv,
        memory_block=memory_block,
        extra_prompts=extra_prompts,
        settings=settings,
    )

    # ── LLM messages ────────────────────────────────────────────────────────
    llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    llm_messages.extend(prior)
    llm_messages.append({"role": "user", "content": user_content})

    # ── Model resolution ─────────────────────────────────────────────────────
    stored_model = (
        body.model or conv.model or settings.chat_default_api_model or ""
    ).strip()
    use_model = resolve_stored_model_to_chat_model(db, stored_model) if stored_model else None

    # ── Streaming generator ──────────────────────────────────────────────────
    active_memory_count = _count_active_memories(system_profile, manual_memories)

    def _tail_message_id() -> int:
        last = repo.get_latest_message(db, conv.id)
        return last.id if last else 0

    def gen() -> Any:
        yield from _stream_loop(
            db=db,
            conv=conv,
            user=user,
            user_content=user_content,
            llm_messages=llm_messages,
            tools=tools,
            use_model=use_model,
            settings=settings,
            active_memory_count=active_memory_count,
            kb_ids=kb_ids,
            tail_message_id=_tail_message_id,
            max_iterations=max_iter,
        )

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _setup_user_message(
    db: Session,
    conv: ChatConversation,
    body: StreamMessageBody,
    user: User,
) -> tuple[str, int, list]:
    """Resolve the user message content, anchor message id, and prior history rows.

    Handles both new messages (with optional file attachments) and regeneration
    of the latest assistant reply.
    """
    if body.regenerate_after_message_id is not None:
        return _setup_regenerate(db, conv, body.regenerate_after_message_id)
    return _setup_new_message(db, conv, body, user)


def _setup_regenerate(
    db: Session,
    conv: ChatConversation,
    regenerate_after_message_id: int,
) -> tuple[str, int, list]:
    asst_msg = db.get(ChatMessage, regenerate_after_message_id)
    if (
        asst_msg is None
        or asst_msg.conversation_id != conv.id
        or asst_msg.role != "assistant"
    ):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid regenerate target message",
        )
    latest = repo.get_latest_message(db, conv.id)
    if latest is None or latest.id != asst_msg.id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Can only regenerate the latest assistant message",
        )
    user_row = repo.get_latest_message_with_role_before(
        db, conv.id, asst_msg.id, "user"
    )
    if user_row is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="No user message found before this assistant reply",
        )
    user_content = user_row.content.strip()
    anchor_id = user_row.id
    db.delete(asst_msg)
    db.commit()
    prior_rows = repo.get_messages_before(db, conv.id, anchor_id)
    return user_content, anchor_id, prior_rows


def _setup_new_message(
    db: Session,
    conv: ChatConversation,
    body: StreamMessageBody,
    user: User,
) -> tuple[str, int, list]:
    user_content = body.content.strip()
    msg_extra: dict = {"uid": str(_uuid_mod.uuid4())}

    if body.attachment_ids:
        uploads = upload_svc.get_uploads_by_ids(db, body.attachment_ids, user.id)
        attachment_parts: list[str] = []
        for up in uploads:
            text = upload_svc.load_upload_text(up)
            if text is not None:
                attachment_parts.append(
                    f"[Attached file: {up.original_filename}]\n{text}"
                )
        if attachment_parts:
            file_block = "\n\n".join(attachment_parts)
            user_content = f"{user_content}\n\n{file_block}" if user_content else file_block
        msg_extra["attachments"] = [
            {"id": up.id, "filename": up.original_filename} for up in uploads
        ]

    user_msg = ChatMessage(
        conversation_id=conv.id,
        role="user",
        content=user_content,
        extra=msg_extra,
    )
    db.add(user_msg)
    conv.last_message_at = datetime.now(tz=UTC)
    if not conv.title:
        conv.title = _title_from_first_user_prompt(user_content) or None
    db.commit()
    db.refresh(user_msg)

    prior_rows = repo.get_messages_before(db, conv.id, user_msg.id)
    return user_content, user_msg.id, prior_rows


def _build_system_prompt(
    *,
    assistant: Assistant | None,
    conv: ChatConversation,
    memory_block: str,
    extra_prompts: list[str],
    settings: Any,
) -> str:
    """Assemble the system prompt from base + memory + tool/capability instructions."""
    parts: list[str] = []
    parts.append(
        assistant.system_prompt.strip() if assistant else settings.default_system_prompt.strip()
    )
    if conv.summary:
        parts.append(f"Earlier in this conversation:\n{conv.summary}")
    if memory_block:
        parts.append(memory_block)
    parts.extend(extra_prompts)
    return "\n\n".join(p for p in parts if p)


_WEB_SNIPPET_MAX = 400


def _make_tool_item_start(tool_name: str, params: dict, uid: str) -> dict:
    if tool_name == "web_search":
        return {"type": "item_start", "item": {"uid": uid, "kind": "web_search", "query": params.get("query", "")}}
    if tool_name == "search_knowledge_base":
        query = params.get("query") or params.get("question") or ""
        return {"type": "item_start", "item": {"uid": uid, "kind": "kb_search", "query": query}}
    return {"type": "item_start", "item": {"uid": uid, "kind": "tool_call", "tool": tool_name, "params": params}}


def _make_tool_item_done(tool_name: str, tool_call_buffer: dict, tool_result: dict, uid: str) -> dict:
    try:
        params = json.loads(tool_call_buffer.get("arguments", "{}"))
    except Exception:
        params = {}
    if tool_name == "web_search":
        content = tool_result.get("content", "")
        return {"type": "item_done", "item": {
            "uid": uid, "kind": "web_search",
            "query": params.get("query", ""),
            "result_snippet": content[:_WEB_SNIPPET_MAX] if content else "",
            "status": "done",
        }}
    if tool_name == "search_knowledge_base":
        query = params.get("query") or params.get("question") or ""
        sources = [{"kb_name": kb.get("kb_name", ""), "chunks_used": kb.get("chunks_used", 0)}
                   for kb in tool_result.get("_used_kbs", [])]
        return {"type": "item_done", "item": {
            "uid": uid, "kind": "kb_search", "query": query, "sources": sources, "status": "done",
        }}
    return {"type": "item_done", "item": {"uid": uid, "kind": "tool_call", "tool": tool_name, "status": "done"}}


def _tool_item_for_persistence(tool_name: str, tool_call_buffer: dict, tool_result: dict, uid: str) -> dict:
    """Same shape as item_done.item, minus 'status'."""
    try:
        params = json.loads(tool_call_buffer.get("arguments", "{}"))
    except Exception:
        params = {}
    if tool_name == "web_search":
        content = tool_result.get("content", "")
        return {"uid": uid, "kind": "web_search", "query": params.get("query", ""),
                "result_snippet": content[:_WEB_SNIPPET_MAX] if content else ""}
    if tool_name == "search_knowledge_base":
        sources = [{"kb_name": kb.get("kb_name", ""), "chunks_used": kb.get("chunks_used", 0)}
                   for kb in tool_result.get("_used_kbs", [])]
        return {"uid": uid, "kind": "kb_search",
                "query": params.get("query") or params.get("question") or "", "sources": sources}
    return {"uid": uid, "kind": "tool_call", "tool": tool_name}


def _count_active_memories(system_profile: Any, manual_memories: list) -> int:
    count = sum(
        1
        for m in manual_memories
        if m.is_active and not m.is_system and (m.content or "").strip()
    )
    if (
        system_profile is not None
        and (system_profile.content or "").strip()
        and system_profile.is_active
    ):
        count += 1
    return count


def _stream_loop(
    *,
    db: Session,
    conv: ChatConversation,
    user: User,
    user_content: str,
    llm_messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    use_model: Any,
    settings: Any,
    active_memory_count: int,
    kb_ids: list[int],
    tail_message_id: Any,
    max_iterations: int,
) -> Any:
    used_kbs_meta: list[dict] = []
    stream_items: list[dict] = []
    messages = list(llm_messages)
    iterations = 0

    # ── Memory pill (flat item, no thinking wrapper) ─────────────────────────
    if active_memory_count > 0:
        memory_uid = str(_uuid_mod.uuid4())
        yield _sse({"type": "item_start", "item": {"uid": memory_uid, "kind": "memory", "count": active_memory_count}})
        yield _sse({"type": "item_done", "item": {"uid": memory_uid, "kind": "memory", "count": active_memory_count, "status": "done"}})
        stream_items.append({"uid": memory_uid, "kind": "memory", "count": active_memory_count})

    # ── Tool-call loop ───────────────────────────────────────────────────────
    while iterations <= max_iterations:
        full: list[str] = []
        tool_call_buffer: dict | None = None

        try:
            for piece in get_chat_provider(settings).stream_deltas_with_tools(
                messages, model=use_model, tools=tools if tools else None
            ):
                if isinstance(piece, dict) and piece.get("type") == "tool_call":
                    tool_call_buffer = piece.get("tool_call")
                    _tool_name = tool_call_buffer.get("name", "")
                    try:
                        _tool_params = json.loads(tool_call_buffer.get("arguments", "{}"))
                    except Exception:
                        _tool_params = {}
                    _tool_uid = str(_uuid_mod.uuid4())
                    tool_call_buffer["_uid"] = _tool_uid
                    yield _sse(_make_tool_item_start(_tool_name, _tool_params, _tool_uid))
                elif isinstance(piece, dict) and piece.get("type") == "delta":
                    text = piece.get("text", "")
                    full.append(text)
                    yield _sse({"type": "delta", "text": text})
                else:
                    full.append(str(piece))
                    yield _sse({"type": "delta", "text": str(piece)})

        except (ValueError, Exception) as exc:
            yield from _handle_stream_error(
                db=db, conv=conv, exc=exc,
                tool_call_buffer=tool_call_buffer,
                tail_message_id=tail_message_id,
            )
            return

        # ── Tool execution ───────────────────────────────────────────────────
        if tool_call_buffer and iterations < max_iterations:
            _tool_name = tool_call_buffer.get("name", "")
            _tool_uid = tool_call_buffer.pop("_uid", str(_uuid_mod.uuid4()))
            tool_result = _dispatch_tool_call(db, tool_call_buffer, kb_ids=kb_ids)
            used_kbs_meta.extend(tool_result.get("_used_kbs", []))
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": [{"id": "tc_0", "type": "function", "function": tool_call_buffer}],
            })
            messages.append({
                "role": "tool",
                "tool_call_id": "tc_0",
                "name": tool_result["name"],
                "content": tool_result["content"],
            })
            yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer, tool_result, _tool_uid))
            stream_items.append(_tool_item_for_persistence(_tool_name, tool_call_buffer, tool_result, _tool_uid))
            iterations += 1
            continue

        # Iteration cap reached — close open tool item if any
        if tool_call_buffer:
            _tool_name = tool_call_buffer.get("name", "")
            _tool_uid = tool_call_buffer.pop("_uid", str(_uuid_mod.uuid4()))
            yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer, {}, _tool_uid))
            stream_items.append(_tool_item_for_persistence(_tool_name, tool_call_buffer, {}, _tool_uid))

        # ── Persist final reply ──────────────────────────────────────────────
        reply = "".join(full)
        extra: dict = {}
        if used_kbs_meta:
            extra["used_kbs"] = used_kbs_meta
        if stream_items:
            extra["stream_items"] = stream_items
        db.add(ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=reply,
            extra=extra or None,
        ))
        db.commit()

        # ── Background tasks ─────────────────────────────────────────────────
        total_msgs = repo.count_messages_in_conversation(db, conv.id)
        if should_summarize(
            message_count=total_msgs,
            base_window=settings.conversation_base_window_size,
            summary_interval=settings.conversation_summary_interval,
        ):
            threading.Thread(target=summarize_conversation, args=(conv.id,), daemon=True).start()

        threading.Thread(
            target=extract_user_memories,
            kwargs={"user_id": user.id, "user_message": user_content, "assistant_message": reply},
            daemon=True,
        ).start()

        yield _sse({"type": "done", "message_id": tail_message_id()})
        return


def _handle_stream_error(
    *,
    db: Session,
    conv: ChatConversation,
    exc: Exception,
    tool_call_buffer: dict | None,
    tail_message_id: Any,
) -> Any:
    if isinstance(exc, ValueError):
        detail = str(exc)
    else:
        logger.exception("chat_stream_failed")
        detail = "Upstream model error"

    db.add(ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content=f"**Error:** {detail}",
    ))
    db.commit()

    if tool_call_buffer:
        _tool_name = tool_call_buffer.get("name", "")
        _tool_uid = tool_call_buffer.pop("_uid", str(_uuid_mod.uuid4()))
        yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer, {}, _tool_uid))

    yield _sse({"type": "error", "detail": detail})
    yield _sse({"type": "done", "message_id": tail_message_id()})
