"""Chat domain — streaming message orchestration.

Coordinates the full streaming flow: message setup, context assembly,
LLM invocation, tool loop, persistence, and background tasks.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

import ai_portal.chat.capabilities.registry as capability_registry
import ai_portal.tools.registry as tool_registry
from ai_portal.assistant.model import Assistant  # kept for type annotation
from ai_portal.assistant.router import _can_access_assistant
from ai_portal.auth.model import User
from ai_portal.catalog.providers import LlmProviderFactory
from ai_portal.catalog.service import resolve_stored_model_to_chat_model
from ai_portal.chat import repository as repo
from ai_portal.chat import upload_service as upload_svc
from ai_portal.chat.context_window import should_summarize, slice_window_messages
from ai_portal.chat.memory_context import build_memory_block
from ai_portal.chat.model import ChatConversation, ChatMessage
from ai_portal.chat.schemas import StreamMessageBody
from ai_portal.chat.tool_service import _dispatch_tool_call
from ai_portal.core.config import get_settings
from ai_portal.memory.workers.extractor import extract_user_memories
from ai_portal.memory.workers.summarizer import summarize_conversation
from ai_portal.tools.gemini_quirks import tool_choice_for_iteration

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
    logger.info("stream_message_svc: start conv=%d user=%d", conversation_id, user.id)
    conv = repo.get_owned_conversation(db, user, conversation_id)
    settings = get_settings()

    # ── Quota check ──────────────────────────────────────────────────────────
    if user.org_id is not None:
        try:
            from ai_portal.usage.service import check_quota  # noqa: PLC0415
            from fastapi import status as _status  # noqa: PLC0415
            from fastapi.responses import JSONResponse  # noqa: PLC0415
            stored_model_for_quota = (body.model or conv.model or settings.chat_default_api_model or "").strip()
            decision = check_quota(db, org_id=user.org_id, user_id=user.id, api_model_id=stored_model_for_quota)
            if decision.is_blocked:
                logger.warning("quota_blocked user=%d reason=%s", user.id, decision.reason)
                headers = {}
                if decision.retry_after_seconds:
                    headers["Retry-After"] = str(decision.retry_after_seconds)
                raise HTTPException(
                    status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=decision.reason or "Quota exceeded",
                    headers=headers,
                )
        except ImportError:
            pass  # usage domain not yet deployed

    # ── Resolve assistant ────────────────────────────────────────────────────
    assistant: Assistant | None = None
    if conv.assistant_id is not None:
        assistant = _can_access_assistant(conv.assistant_id, user, conv.org_id, db)
        logger.debug("stream: resolved assistant=%d", conv.assistant_id)

    # ── Resolve user message + prior history ────────────────────────────────
    user_content, anchor_id, prior_rows = _setup_user_message(db, conv, body, user)
    logger.info(
        "stream: user_message anchor=%d content_len=%d prior_msgs=%d",
        anchor_id,
        len(user_content),
        len(prior_rows),
    )

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
    logger.debug(
        "stream: context_window sliced to %d messages (base_window=%d)",
        len(prior),
        settings.conversation_base_window_size,
    )

    # ── Memories ─────────────────────────────────────────────────────────────
    system_profile, manual_memories = repo.get_user_memories(db, user.id)
    memory_block = build_memory_block(
        system_profile=system_profile,
        manual_memories=manual_memories,
    )
    logger.debug(
        "stream: memory_block len=%d active_memories=%d",
        len(memory_block),
        len(manual_memories),
    )

    # ── RBAC model gate ─────────────────────────────────────────────────────
    stored_model_rbac = (body.model or conv.model or settings.chat_default_api_model or "").strip()
    if user.org_id is not None and stored_model_rbac:
        try:
            from ai_portal.rbac.evaluator import evaluate as rbac_eval  # noqa: PLC0415
            model_decision = rbac_eval(
                db, user=user, org_id=user.org_id, resource_type="model", resource_key=stored_model_rbac
            )
            if not model_decision:
                logger.warning("rbac: model blocked user=%d model=%s reason=%s", user.id, stored_model_rbac, model_decision.reason)
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    detail=f"Access to model {stored_model_rbac!r} is not allowed for your role.",
                )
        except ImportError:
            pass

    # ── Tool definitions ─────────────────────────────────────────────────────
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    _stored_model_for_tools = (
        body.model or conv.model or settings.chat_default_api_model or ""
    ).strip()
    _capabilities = conv.settings.capabilities if conv.settings else None
    tools = tool_registry.get_tool_definitions(
        kb_ids,
        model_id=_stored_model_for_tools or None,
        capabilities=_capabilities,
    )

    # Filter tools by RBAC policy.
    if user.org_id is not None:
        try:
            from ai_portal.rbac.evaluator import evaluate as rbac_eval  # noqa: PLC0415
            tools = [
                t for t in tools
                if rbac_eval(
                    db, user=user, org_id=user.org_id,
                    resource_type="tool",
                    resource_key=(t.get("function") or {}).get("name", t.get("type", "")),
                )
            ]
        except ImportError:
            pass

    max_iter = capability_registry.get_max_iterations(
        conv.settings, base=settings.rag_max_tool_iterations
    )
    logger.info(
        "stream: kb_ids=%s tools=%d max_iterations=%d", kb_ids, len(tools), max_iter
    )

    # ── System prompt ────────────────────────────────────────────────────────
    # Filter capabilities by RBAC policy before building prompts.
    if user.org_id is not None and _capabilities:
        try:
            from ai_portal.rbac.evaluator import evaluate as rbac_eval  # noqa: PLC0415
            from ai_portal.chat.schemas import CapabilityToggles  # noqa: PLC0415
            cap_dict = _capabilities.model_dump() if hasattr(_capabilities, "model_dump") else {}
            filtered = {
                k: v for k, v in cap_dict.items()
                if not v or rbac_eval(db, user=user, org_id=user.org_id, resource_type="capability", resource_key=k)
            }
            _capabilities = type(_capabilities)(**filtered) if filtered else _capabilities
        except (ImportError, Exception):
            pass

    extra_prompts = tool_registry.get_system_prompts(
        kb_ids, capabilities=_capabilities
    ) + capability_registry.get_system_prompts(conv.settings)
    system_content = _build_system_prompt(
        assistant=assistant,
        conv=conv,
        memory_block=memory_block,
        extra_prompts=extra_prompts,
        settings=settings,
    )
    logger.debug(
        "stream: system_prompt len=%d extra_prompts=%d",
        len(system_content),
        len(extra_prompts),
    )

    # ── LLM messages ────────────────────────────────────────────────────────
    llm_messages: list[dict[str, Any]] = [{"role": "system", "content": system_content}]
    llm_messages.extend(prior)
    llm_messages.append({"role": "user", "content": user_content})

    # ── Model resolution ─────────────────────────────────────────────────────
    stored_model = (
        body.model or conv.model or settings.chat_default_api_model or ""
    ).strip()
    use_model = (
        resolve_stored_model_to_chat_model(db, stored_model) if stored_model else None
    )
    logger.info("stream: stored_model=%r resolved=%r", stored_model, use_model)

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
    msg_extra: dict | None = None

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
            user_content = (
                f"{user_content}\n\n{file_block}" if user_content else file_block
            )
        msg_extra = {
            "attachments": [
                {"id": up.id, "filename": up.original_filename} for up in uploads
            ]
        }

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
        assistant.system_prompt.strip()
        if assistant
        else settings.default_system_prompt.strip()
    )
    if conv.summary:
        parts.append(f"Earlier in this conversation:\n{conv.summary}")
    if memory_block:
        parts.append(memory_block)
    parts.extend(extra_prompts)
    return "\n\n".join(p for p in parts if p)


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
    # Accumulated across all iterations — written to message_usage once at persist.
    accumulated_usage: dict[str, Any] = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_input_tokens": 0,
        "cache_creation_input_tokens": 0,
        "reasoning_tokens": None,
    }
    thinking_blocks: list[str] = []
    citations: list[dict] = []

    logger.info(
        "stream_loop: start conv=%d model=%r tools=%d max_iter=%d",
        conv.id,
        use_model,
        len(tools),
        max_iterations,
    )

    # ── Memory pill ──────────────────────────────────────────────────────────────
    if active_memory_count > 0:
        _memory_uid = str(uuid4())
        stream_items.append(
            {"uid": _memory_uid, "kind": "memory", "count": active_memory_count}
        )
        logger.debug(
            "stream_loop: emitting memory item uid=%s count=%d",
            _memory_uid,
            active_memory_count,
        )
        yield _sse(
            {
                "type": "item_start",
                "item": {
                    "uid": _memory_uid,
                    "kind": "memory",
                    "count": active_memory_count,
                },
            }
        )
        yield _sse(
            {
                "type": "item_done",
                "item": {
                    "uid": _memory_uid,
                    "kind": "memory",
                    "count": active_memory_count,
                    "status": "done",
                },
            }
        )

    # ── Tool-call loop ───────────────────────────────────────────────────────
    while iterations <= max_iterations:
        full: list[str] = []
        tool_call_buffer: dict | None = None
        _tool_item_uid: str | None = None
        _tool_item_kind: str | None = None
        _tool_name: str = ""

        logger.info(
            "stream_loop: LLM call iteration=%d messages=%d", iterations, len(messages)
        )
        _tool_choice = tool_choice_for_iteration(
            str(use_model), iterations, bool(tools)
        )
        if _tool_choice:
            logger.info(
                "stream_loop: forcing tool_choice=%r for model=%r",
                _tool_choice,
                use_model,
            )
        try:
            provider = LlmProviderFactory.create(settings, use_model)
            logger.debug("stream_loop: provider=%s", type(provider).__name__)
            for piece in provider.stream_deltas_with_tools(
                messages,
                model=use_model,
                tools=tools if tools else None,
                tool_choice=_tool_choice,
            ):
                if not isinstance(piece, dict):
                    full.append(str(piece))
                    yield _sse({"type": "delta", "text": str(piece)})
                    continue

                ptype = piece.get("type")

                if ptype == "usage":
                    accumulated_usage["input_tokens"] += piece.get("input_tokens", 0) or 0
                    accumulated_usage["output_tokens"] += piece.get("output_tokens", 0) or 0
                    accumulated_usage["cached_input_tokens"] += piece.get("cached_input_tokens", 0) or 0
                    accumulated_usage["cache_creation_input_tokens"] += piece.get("cache_creation_input_tokens", 0) or 0
                    rt = piece.get("reasoning_tokens")
                    if rt:
                        accumulated_usage["reasoning_tokens"] = (accumulated_usage["reasoning_tokens"] or 0) + rt
                    continue

                if ptype == "thinking":
                    thinking_blocks.append(piece.get("text", ""))
                    continue

                if ptype == "citation":
                    citations.append({
                        "url": piece.get("url", ""),
                        "title": piece.get("title"),
                        "snippet": piece.get("snippet"),
                    })
                    continue

                if ptype == "tool_call":
                    tool_call_buffer = piece.get("tool_call")
                    _tool_name = tool_call_buffer.get("name", "")
                    try:
                        _tool_params = json.loads(
                            tool_call_buffer.get("arguments", "{}")
                        )
                    except Exception:
                        _tool_params = {}
                    # Map tool name to SSE kind
                    if _tool_name == "web_search":
                        _tool_item_kind = "web_search"
                    elif _tool_name == "fetch_webpage":
                        _tool_item_kind = "fetch_webpage"
                    elif _tool_name == "kb_search":
                        _tool_item_kind = "kb_search"
                    else:
                        _tool_item_kind = "tool_call"
                    _tool_item_uid = str(uuid4())
                    logger.info(
                        "stream_loop: tool_call name=%r kind=%r params=%r",
                        _tool_name,
                        _tool_item_kind,
                        _tool_params,
                    )
                    _query = _tool_params.get("query", "")
                    _url = _tool_params.get("url", "")
                    item_start_payload: dict = {
                        "uid": _tool_item_uid,
                        "kind": _tool_item_kind,
                        "tool": _tool_name,
                        "params": _tool_params,
                    }
                    if _query:
                        item_start_payload["query"] = _query
                    if _url:
                        item_start_payload["url"] = _url
                    yield _sse({"type": "item_start", "item": item_start_payload})
                    # Accumulate for persistence (no status field)
                    stream_item_entry: dict = {
                        "uid": _tool_item_uid,
                        "kind": _tool_item_kind,
                    }
                    if _query:
                        stream_item_entry["query"] = _query
                    if _url:
                        stream_item_entry["url"] = _url
                    stream_items.append(stream_item_entry)
                elif ptype == "server_tool_use":
                    # Native provider tool (Anthropic web_search_20260209, Gemini grounding).
                    # The provider executes this — we just surface a chip for the UI.
                    _srv_name = piece.get("name", "web_search")
                    _srv_input = piece.get("input", {})
                    _srv_uid = str(uuid4())
                    _srv_query = _srv_input.get("query", "")
                    _srv_url = _srv_input.get("url", "")
                    _srv_kind = (
                        "web_search" if _srv_name == "web_search"
                        else "fetch_webpage" if _srv_name == "web_fetch"
                        else "tool_call"
                    )
                    logger.info(
                        "stream_loop: server_tool_use name=%r query=%r",
                        _srv_name,
                        _srv_query,
                    )
                    srv_start: dict = {
                        "uid": _srv_uid,
                        "kind": _srv_kind,
                        "tool": _srv_name,
                        "params": _srv_input,
                    }
                    if _srv_query:
                        srv_start["query"] = _srv_query
                    if _srv_url:
                        srv_start["url"] = _srv_url
                    yield _sse({"type": "item_start", "item": srv_start})
                    srv_done: dict = {
                        "uid": _srv_uid,
                        "kind": _srv_kind,
                        "tool": _srv_name,
                        "status": "done",
                    }
                    if _srv_query:
                        srv_done["query"] = _srv_query
                    srv_item: dict = {"uid": _srv_uid, "kind": _srv_kind}
                    if _srv_query:
                        srv_item["query"] = _srv_query
                    stream_items.append(srv_item)
                    yield _sse({"type": "item_done", "item": srv_done})
                    # Do NOT set tool_call_buffer — server tools are not dispatched by us
                elif ptype == "delta":
                    text = piece.get("text", "")
                    full.append(text)
                    yield _sse({"type": "delta", "text": text})
                # Unknown event types are intentionally ignored (forward compatibility).

        except (ValueError, Exception) as exc:
            logger.error(
                "stream_loop: error at iteration=%d exc_type=%s exc=%s",
                iterations,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            yield from _handle_stream_error(
                db=db,
                conv=conv,
                exc=exc,
                tool_call_buffer=tool_call_buffer,
                tool_item_uid=_tool_item_uid if tool_call_buffer else None,
                tool_item_kind=_tool_item_kind if tool_call_buffer else None,
                tail_message_id=tail_message_id,
            )
            return

        logger.debug(
            "stream_loop: iteration=%d delta_chars=%d tool_call=%r",
            iterations,
            sum(len(t) for t in full),
            tool_call_buffer.get("name") if tool_call_buffer else None,
        )

        # ── Tool execution ───────────────────────────────────────────────────
        if tool_call_buffer and iterations < max_iterations:
            logger.info(
                "stream_loop: dispatching tool=%r", tool_call_buffer.get("name")
            )
            tool_result = _dispatch_tool_call(db, tool_call_buffer, kb_ids=kb_ids)
            used_kbs_meta.extend(tool_result.get("_used_kbs", []))
            logger.info(
                "stream_loop: tool result name=%r content_len=%d used_kbs=%d",
                tool_result.get("name"),
                len(tool_result.get("content", "")),
                len(tool_result.get("_used_kbs", [])),
            )
            _tc_id = f"tc_{iterations}"
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {"id": _tc_id, "type": "function", "function": tool_call_buffer}
                    ],
                }
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": _tc_id,
                    "name": tool_result["name"],
                    "content": tool_result["content"],
                }
            )
            _result_snippet = (tool_result.get("content") or "")[:500]
            _tool_provider = tool_result.get("_provider") or ""
            # Update stream_items entry with result fields (no status field in persisted copy)
            for _si in stream_items:
                if _si.get("uid") == _tool_item_uid:
                    if _result_snippet:
                        _si["result_snippet"] = _result_snippet
                    if _tool_provider:
                        _si["provider"] = _tool_provider
                    break
            item_done_payload: dict = {
                "uid": _tool_item_uid,
                "kind": _tool_item_kind,
                "tool": _tool_name,
                "status": "done",
            }
            if _url:
                item_done_payload["url"] = _url
            if _result_snippet:
                item_done_payload["result_snippet"] = _result_snippet
            if _tool_provider:
                item_done_payload["provider"] = _tool_provider
            yield _sse({"type": "item_done", "item": item_done_payload})
            iterations += 1

            # ── Auto-fetch: if web_search returned thin/no results, fetch top URL ──
            if (
                _tool_name == "web_search"
                and tool_result.get("_thin")
                and tool_result.get("_top_urls")
                and iterations < max_iterations
            ):
                fetch_url = tool_result["_top_urls"][0]
                logger.info(
                    "stream_loop: auto_fetch url=%r (thin web_search results)",
                    fetch_url,
                )
                _fetch_uid = str(uuid4())
                yield _sse(
                    {
                        "type": "item_start",
                        "item": {
                            "uid": _fetch_uid,
                            "kind": "fetch_webpage",
                            "tool": "fetch_webpage",
                            "url": fetch_url,
                            "params": {"url": fetch_url},
                        },
                    }
                )
                stream_items.append(
                    {"uid": _fetch_uid, "kind": "fetch_webpage", "url": fetch_url}
                )
                from ai_portal.tools import fetch_webpage as fetch_webpage_tool

                fetch_result = fetch_webpage_tool.execute(fetch_url)
                fetch_snippet = (fetch_result.get("content") or "")[:500]
                _fetch_provider = fetch_result.get("_provider") or ""
                for _si in stream_items:
                    if _si.get("uid") == _fetch_uid:
                        if fetch_snippet:
                            _si["result_snippet"] = fetch_snippet
                        if _fetch_provider:
                            _si["provider"] = _fetch_provider
                        break
                _af_tc_id = f"tc_{iterations}_af"
                messages.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": _af_tc_id,
                                "type": "function",
                                "function": {
                                    "name": "fetch_webpage",
                                    "arguments": f'{{"url": "{fetch_url}"}}',
                                },
                            }
                        ],
                    }
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": _af_tc_id,
                        "name": "fetch_webpage",
                        "content": fetch_result["content"],
                    }
                )
                fetch_done_payload: dict = {
                    "uid": _fetch_uid,
                    "kind": "fetch_webpage",
                    "tool": "fetch_webpage",
                    "url": fetch_url,
                    "status": "done",
                }
                if fetch_snippet:
                    fetch_done_payload["result_snippet"] = fetch_snippet
                if _fetch_provider:
                    fetch_done_payload["provider"] = _fetch_provider
                yield _sse({"type": "item_done", "item": fetch_done_payload})
                # Note: auto-fetch does NOT increment iterations — it's backend-enforced,
                # not an LLM tool decision. The next LLM call stays within the budget.

            continue

        # Iteration cap reached — close open tool item if any
        if tool_call_buffer:
            logger.warning(
                "stream_loop: max_iterations=%d reached, closing tool=%r",
                max_iterations,
                _tool_name,
            )
            yield _sse(
                {
                    "type": "item_done",
                    "item": {
                        "uid": _tool_item_uid,
                        "kind": _tool_item_kind,
                        "tool": _tool_name,
                        "status": "done",
                    },
                }
            )

        # ── Force response if LLM went silent after tool calls ──────────────
        reply = "".join(full)
        if not reply and stream_items:
            logger.warning(
                "stream_loop: empty reply after tool calls — forcing final response"
            )
            messages.append(
                {
                    "role": "user",
                    "content": "Based on the information gathered above, provide a complete answer to the original question.",
                }
            )
            try:
                provider = LlmProviderFactory.create(settings, use_model)
                for piece in provider.stream_deltas_with_tools(
                    messages, model=use_model, tools=None
                ):
                    text = (
                        piece.get("text", "") if isinstance(piece, dict) else str(piece)
                    )
                    if text:
                        reply += text
                        yield _sse({"type": "delta", "text": text})
            except Exception as exc:
                logger.error("stream_loop: forced final response failed: %s", exc)
                friendly = _friendly_api_error(exc)
                yield _sse({"type": "error", "message": friendly})

        # ── Persist final reply ──────────────────────────────────────────────
        logger.info(
            "stream_loop: persisting reply conv=%d reply_len=%d used_kbs=%d",
            conv.id,
            len(reply),
            len(used_kbs_meta),
        )
        extra: dict = {}
        if used_kbs_meta:
            extra["used_kbs"] = used_kbs_meta
        if stream_items:
            extra["stream_items"] = stream_items
        if thinking_blocks:
            extra["thinking"] = "".join(thinking_blocks)
        if citations:
            extra["citations"] = citations
        if any(accumulated_usage.values()):
            extra["usage"] = accumulated_usage

        assistant_msg = ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=reply,
            model_id=str(use_model) if use_model else None,
            extra=extra or None,
        )
        db.add(assistant_msg)
        db.commit()
        db.refresh(assistant_msg)

        # Asynchronously persist usage metrics (non-blocking; fails silently).
        if any(v for v in accumulated_usage.values() if v):
            _record_usage_async(
                db=db,
                user=user,
                conv=conv,
                message_id=assistant_msg.id,
                use_model=use_model,
                usage=accumulated_usage,
            )

        # ── Background tasks ─────────────────────────────────────────────────
        total_msgs = repo.count_messages_in_conversation(db, conv.id)
        if should_summarize(
            message_count=total_msgs,
            base_window=settings.conversation_base_window_size,
            summary_interval=settings.conversation_summary_interval,
        ):
            logger.info(
                "stream_loop: spawning summarizer for conv=%d (total_msgs=%d)",
                conv.id,
                total_msgs,
            )
            threading.Thread(
                target=summarize_conversation, args=(conv.id,), daemon=True
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

        msg_id = tail_message_id()
        logger.info("stream_loop: done conv=%d message_id=%d", conv.id, msg_id)

        # Fire-and-forget audit event.
        if user.org_id is not None:
            try:
                from ai_portal.audit.service import log_event  # noqa: PLC0415
                log_event(
                    org_id=user.org_id,
                    actor_user_id=user.id,
                    event_type="chat.stream.completed",
                    resource_type="message",
                    resource_id=str(msg_id),
                    action="stream",
                    metadata={
                        "conversation_id": conv.id,
                        "model": str(use_model),
                        "input_tokens": accumulated_usage.get("input_tokens"),
                        "output_tokens": accumulated_usage.get("output_tokens"),
                    },
                )
            except ImportError:
                pass

        yield _sse({"type": "done", "message_id": msg_id})
        return


def _record_usage_async(
    *,
    db: Session,
    user: User,
    conv: ChatConversation,
    message_id: int,
    use_model: Any,
    usage: dict[str, Any],
) -> None:
    """Fire-and-forget usage recording — fully wired in M3 (usage domain).

    Uses a daemon thread so it never blocks the streaming response. Silently
    swallows any error so a metering failure can't break a chat reply.
    """
    def _do() -> None:
        try:
            from ai_portal.usage.service import record_usage  # noqa: PLC0415
            from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
            with SessionLocal() as _db:
                record_usage(
                    _db,
                    org_id=conv.org_id,
                    user_id=user.id,
                    conversation_id=conv.id,
                    message_id=message_id,
                    api_model_id=str(use_model or ""),
                    usage=usage,
                )
        except ImportError:
            pass  # M3 not yet deployed
        except Exception as exc:  # noqa: BLE001
            logger.warning("usage_record_failed: %s", exc)

    threading.Thread(target=_do, daemon=True).start()


def _friendly_api_error(exc: Exception) -> str:
    """Convert provider API exceptions into human-readable messages."""
    msg = str(exc)
    exc_type = type(exc).__name__

    # Rate limit / quota exhausted
    if "429" in msg or "RESOURCE_EXHAUSTED" in msg or "quota" in msg.lower():
        import re

        retry_match = re.search(r"retry.*?(\d+(?:\.\d+)?s)", msg, re.IGNORECASE)
        retry_hint = f" Retry in {retry_match.group(1)}." if retry_match else ""
        return f"Rate limit exceeded for this model.{retry_hint} Try a different model or wait before retrying."

    # Auth / API key errors
    if (
        "401" in msg
        or "403" in msg
        or "UNAUTHENTICATED" in msg
        or "API_KEY" in msg.upper()
    ):
        return "Invalid or missing API key. Check your API key configuration."

    # Model not found
    if (
        "404" in msg
        or "NOT_FOUND" in msg
        or "model" in msg.lower()
        and "not found" in msg.lower()
    ):
        return f"Model not found or unavailable. ({exc_type})"

    # Network / timeout
    if any(k in exc_type.lower() for k in ("timeout", "connection", "network")):
        return f"Could not reach the AI provider (network error). Please try again."

    # Context / token limit
    if "context" in msg.lower() or "token" in msg.lower() and "limit" in msg.lower():
        return "Message is too long for this model. Try shortening your message."

    # Generic fallback — include type and shortened message for debugging
    short = msg[:200] if len(msg) > 200 else msg
    return f"Model error ({exc_type}): {short}"


def _handle_stream_error(
    *,
    db: Session,
    conv: ChatConversation,
    exc: Exception,
    tool_call_buffer: dict | None,
    tool_item_uid: str | None,
    tool_item_kind: str | None,
    tail_message_id: Any,
) -> Any:
    if isinstance(exc, ValueError):
        detail = str(exc)
    else:
        logger.exception("chat_stream_failed exc_type=%s", type(exc).__name__)
        detail = _friendly_api_error(exc)

    db.add(
        ChatMessage(
            conversation_id=conv.id,
            role="assistant",
            content=f"**Error:** {detail}",
        )
    )
    db.commit()

    if tool_call_buffer and tool_item_uid and tool_item_kind:
        yield _sse(
            {
                "type": "item_done",
                "item": {
                    "uid": tool_item_uid,
                    "kind": tool_item_kind,
                    "tool": tool_call_buffer.get("name", ""),
                    "status": "done",
                },
            }
        )

    yield _sse({"type": "error", "detail": detail})
    yield _sse({"type": "done", "message_id": tail_message_id()})
