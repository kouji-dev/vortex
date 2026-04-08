# Thread Tool Items — Flat Stream Items Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Thinking" wrapper concept with flat, per-type thread items (memory/web_search/kb_search/tool_call), persisted in `ChatMessage.extra.stream_items` so they survive page refresh and render identically live and on reload — including tool result details (web snippets, KB sources).

**Architecture:** Backend emits specific SSE item kinds (`web_search`, `kb_search`, `memory`, `tool_call`) with no outer `thinking` container. After each tool dispatch, the `item_done` SSE carries result data (web snippet, KB sources). The `_stream_loop` accumulates a `stream_items` list (with result data) and stores it in `extra.stream_items` on save alongside the existing `used_kbs`. Frontend replaces the nested `ThinkingItem` type model with a flat `StreamThreadItem[]`, renders a new `ThreadItemChip` component inline inside each assistant message block — both during streaming (from live SSE state) and on load (from `message.extra.stream_items`). The expanded chip view is identical in both cases because it reads from the same data shape.

**Tech Stack:** Python/FastAPI SSE, SQLAlchemy JSONB, React 18, TypeScript, Tailwind CSS, Playwright E2E

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `backend/src/ai_portal/chat/streaming_service.py` | Emit specific item kinds; accumulate + persist `stream_items` |
| Modify | `frontend/src/lib/chat-types.ts` | Flatten types; remove `ThinkingItem` wrapper |
| Create | `frontend/src/components/chat/ThreadItemChip.tsx` | Per-type chip (spinner→done, expandable) |
| Delete | `frontend/src/components/chat/StreamingThinkingBlock.tsx` | Replaced by `ThreadItemChip` |
| Modify | `frontend/src/components/chat/ConversationThreadPage.tsx` | Update SSE handler; render chips inline |
| Modify | `frontend/e2e/chat/chat-tool-thinking-block.spec.ts` | Rewrite for flat items (no thinking wrapper) |
| Modify | `frontend/e2e/chat/chat-tool-web-search.spec.ts` | Use `kind: 'web_search'` SSE + new selectors |
| Modify | `frontend/e2e/chat/chat-tool-kb-search.spec.ts` | Use `kind: 'kb_search'` SSE + new selectors |

### DB model decision — JSONB vs. separate table

**Option A (chosen): embed `stream_items` in `ChatMessage.extra` JSONB**
- No schema change, no migration, no join
- `extra` already stores `used_kbs` the same way
- Items are always read together with the message — no N+1
- Downside: no indexed query across items; you can't efficiently find "all messages that used web_search"

**Option B: separate `ChatMessageItem` table (one-to-many)**
- Enables per-item querying, proper foreign keys, future analytics
- Requires a migration, an ORM model, a repository method, and a schema type
- Items must be loaded via a join on every message fetch
- More code surface for no current user-facing benefit

**Decision: Option A.** The items are display metadata, not queryable entities. Embedding in JSONB keeps the diff small and the read path unchanged. If analytics become a requirement later, a migration can extract them.

The `ChatMessage` model (`model.py`) is therefore **unchanged** — `extra: Mapped[dict | None]` already exists. No Alembic migration needed.

User messages also get `extra.uid` set before insert (a single UUID4 string, not an array). No schema change needed for that either — `extra` accepts any dict.

---

## Task 1: Backend — Flatten SSE events and persist stream_items

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`

### Design

### Persistence contract

Every assistant message that used tools gets `extra.stream_items` — a complete ordered list of the thread items that preceded the text. This is what gets rendered on page reload instead of the live SSE state.

**Full persistence shape** (all items that appear in the thread, in order):

Every item carries a `uid` (UUID4 string) generated at `item_start` time. The `item_done` event echoes the same `uid` so the frontend can look items up by ID rather than by position. This makes matching O(1) and robust to concurrent items.

```json
{
  "used_kbs": [...],
  "stream_items": [
    {
      "uid": "a1b2c3d4-...",
      "kind": "memory",
      "count": 3
    },
    {
      "uid": "e5f6a7b8-...",
      "kind": "web_search",
      "query": "oil price",
      "result_snippet": "1. [Brent Crude - Live](https://...) $82.40/barrel...\n2. [WTI Oil](https://...) $78.90..."
    },
    {
      "uid": "c9d0e1f2-...",
      "kind": "kb_search",
      "query": "Q1 oil report",
      "sources": [
        {"kb_name": "Oil Market Report Q1 2026.pdf", "chunks_used": 3}
      ]
    },
    {
      "uid": "33445566-...",
      "kind": "tool_call",
      "tool": "some_other_tool"
    }
  ]
}
```

**SSE events — new flat shape** (no `thinking` wrapper):

Every SSE item carries `uid` (UUID4 str, generated in `_stream_loop` at start time):

| Event | Payload |
|---|---|
| `item_start` memory | `{uid, kind:'memory', count:N}` |
| `item_done` memory | `{uid, kind:'memory', count:N, status:'done'}` |
| `item_start` web_search | `{uid, kind:'web_search', query:'...'}` |
| `item_done` web_search | `{uid, kind:'web_search', query:'...', result_snippet:'...', status:'done'}` |
| `item_start` kb_search | `{uid, kind:'kb_search', query:'...'}` |
| `item_done` kb_search | `{uid, kind:'kb_search', query:'...', sources:[...], status:'done'}` |
| `item_start` tool_call | `{uid, kind:'tool_call', tool:'X', params:{...}}` |
| `item_done` tool_call | `{uid, kind:'tool_call', tool:'X', status:'done'}` |

`result_snippet` = first 400 chars of web search content.
`sources` = `[{kb_name, chunks_used}]` from `_used_kbs`.

**Key invariant:** `item_done.item` (minus `status`) is exactly the dict stored in `extra.stream_items`. The backend strips `status` before persisting. The frontend merges `item_done.item` into the matching live item by `uid` (not by position). On reload, `extra.stream_items` items already have `uid` so the same `ThreadItemChip` component renders them with `status: 'done'`.

**User messages** also get a `uid` assigned in `_setup_new_message` before `db.add` and stored in `extra.uid`. This lets the frontend correlate the optimistic user bubble with the persisted row if needed in future, and gives every thread node a stable identity.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/chat/test_streaming_service_sse_shape.py`:

```python
"""Unit tests for _stream_loop SSE event shapes (no DB needed — pure generator)."""
import json
import pytest
from unittest.mock import MagicMock, patch


def _collect_events(gen) -> list[dict]:
    events = []
    for chunk in gen:
        if chunk.startswith("data: "):
            events.append(json.loads(chunk[6:].strip()))
    return events


def _make_db():
    db = MagicMock()
    db.add = MagicMock()
    db.commit = MagicMock()
    return db


def _make_conv(conv_id=1):
    conv = MagicMock()
    conv.id = conv_id
    conv.settings = None
    return conv


def _make_user(user_id=1):
    user = MagicMock()
    user.id = user_id
    return user


def _make_settings():
    s = MagicMock()
    s.rag_max_tool_iterations = 3
    s.conversation_base_window_size = 10
    s.conversation_summary_interval = 5
    return s


@patch("ai_portal.chat.streaming_service.get_chat_provider")
@patch("ai_portal.chat.streaming_service.repo")
@patch("threading.Thread")
def test_no_thinking_events_in_sse(mock_thread, mock_repo, mock_provider):
    """No item_start/item_done with kind='thinking' should be emitted."""
    from ai_portal.chat.streaming_service import _stream_loop

    mock_repo.count_messages_in_conversation.return_value = 1
    mock_repo.get_latest_message.return_value = MagicMock(id=99)

    provider = MagicMock()
    provider.stream_deltas_with_tools.return_value = [
        {"type": "delta", "text": "hello"}
    ]
    mock_provider.return_value = provider

    events = _collect_events(_stream_loop(
        db=_make_db(),
        conv=_make_conv(),
        user=_make_user(),
        user_content="hi",
        llm_messages=[{"role": "user", "content": "hi"}],
        tools=[],
        use_model=None,
        settings=_make_settings(),
        active_memory_count=0,
        kb_ids=[],
        tail_message_id=lambda: 99,
        max_iterations=3,
    ))

    kinds = [e.get("item", {}).get("kind") for e in events if e.get("type") in ("item_start", "item_done")]
    assert "thinking" not in kinds


@patch("ai_portal.chat.streaming_service.get_chat_provider")
@patch("ai_portal.chat.streaming_service.repo")
@patch("threading.Thread")
def test_memory_item_emitted_flat(mock_thread, mock_repo, mock_provider):
    """Memory items are emitted as flat item_start/item_done (not nested in thinking)."""
    from ai_portal.chat.streaming_service import _stream_loop

    mock_repo.count_messages_in_conversation.return_value = 1
    mock_repo.get_latest_message.return_value = MagicMock(id=99)

    provider = MagicMock()
    provider.stream_deltas_with_tools.return_value = [{"type": "delta", "text": "ok"}]
    mock_provider.return_value = provider

    events = _collect_events(_stream_loop(
        db=_make_db(), conv=_make_conv(), user=_make_user(),
        user_content="hi",
        llm_messages=[{"role": "user", "content": "hi"}],
        tools=[], use_model=None, settings=_make_settings(),
        active_memory_count=2, kb_ids=[],
        tail_message_id=lambda: 99, max_iterations=3,
    ))

    starts = [e for e in events if e.get("type") == "item_start" and e.get("item", {}).get("kind") == "memory"]
    dones = [e for e in events if e.get("type") == "item_done" and e.get("item", {}).get("kind") == "memory"]
    assert len(starts) == 1
    assert starts[0]["item"]["count"] == 2
    assert len(dones) == 1


@patch("ai_portal.chat.streaming_service.get_chat_provider")
@patch("ai_portal.chat.streaming_service._dispatch_tool_call")
@patch("ai_portal.chat.streaming_service.repo")
@patch("threading.Thread")
def test_web_search_item_kind(mock_thread, mock_repo, mock_dispatch, mock_provider):
    """web_search tool emits kind='web_search' with query, not kind='tool_call'."""
    from ai_portal.chat.streaming_service import _stream_loop

    mock_repo.count_messages_in_conversation.return_value = 1
    mock_repo.get_latest_message.return_value = MagicMock(id=99)
    mock_dispatch.return_value = {"name": "web_search", "content": "results", "_used_kbs": []}

    call_count = 0
    def side_effect(messages, model, tools):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{"type": "tool_call", "tool_call": {"name": "web_search", "arguments": '{"query": "oil price"}'}}]
        return [{"type": "delta", "text": "done"}]

    provider = MagicMock()
    provider.stream_deltas_with_tools.side_effect = side_effect
    mock_provider.return_value = provider

    events = _collect_events(_stream_loop(
        db=_make_db(), conv=_make_conv(), user=_make_user(),
        user_content="hi",
        llm_messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "web_search"}], use_model=None, settings=_make_settings(),
        active_memory_count=0, kb_ids=[],
        tail_message_id=lambda: 99, max_iterations=3,
    ))

    starts = [e for e in events if e.get("type") == "item_start"]
    ws_start = next((e for e in starts if e.get("item", {}).get("kind") == "web_search"), None)
    assert ws_start is not None, f"Expected web_search item_start, got: {starts}"
    assert ws_start["item"]["query"] == "oil price"

    # No tool_call kind should be present for web_search
    tc_events = [e for e in events if e.get("item", {}).get("kind") == "tool_call"]
    assert len(tc_events) == 0


@patch("ai_portal.chat.streaming_service.get_chat_provider")
@patch("ai_portal.chat.streaming_service._dispatch_tool_call")
@patch("ai_portal.chat.streaming_service.repo")
@patch("threading.Thread")
def test_stream_items_persisted_in_extra(mock_thread, mock_repo, mock_dispatch, mock_provider):
    """stream_items list is saved in ChatMessage.extra.stream_items after stream."""
    from ai_portal.chat.streaming_service import _stream_loop
    from ai_portal.chat.model import ChatMessage

    db = _make_db()
    saved_messages = []
    def capture_add(obj):
        if isinstance(obj, ChatMessage):
            saved_messages.append(obj)
    db.add.side_effect = capture_add

    mock_repo.count_messages_in_conversation.return_value = 1
    mock_repo.get_latest_message.return_value = MagicMock(id=99)
    mock_dispatch.return_value = {"name": "web_search", "content": "results", "_used_kbs": []}

    call_count = 0
    def side_effect(messages, model, tools):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return [{"type": "tool_call", "tool_call": {"name": "web_search", "arguments": '{"query": "test"}'}}]
        return [{"type": "delta", "text": "answer"}]

    provider = MagicMock()
    provider.stream_deltas_with_tools.side_effect = side_effect
    mock_provider.return_value = provider

    list(_stream_loop(
        db=db, conv=_make_conv(), user=_make_user(),
        user_content="hi",
        llm_messages=[{"role": "user", "content": "hi"}],
        tools=[{"name": "web_search"}], use_model=None, settings=_make_settings(),
        active_memory_count=2, kb_ids=[],
        tail_message_id=lambda: 99, max_iterations=3,
    ))

    assert len(saved_messages) == 1
    extra = saved_messages[0].extra
    assert extra is not None
    assert "stream_items" in extra
    items = extra["stream_items"]
    assert any(i["kind"] == "memory" for i in items)
    assert any(i["kind"] == "web_search" for i in items)
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py -v 2>&1 | tail -30
```

Expected: ImportError or failures because `_stream_loop` still emits `thinking` kinds and doesn't persist `stream_items`.

- [ ] **Step 3: Rewrite `_stream_loop` in `streaming_service.py`**

Replace the entire `_stream_loop` function with:

```python
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
    stream_items: list[dict] = []   # accumulated for persistence
    messages = list(llm_messages)
    iterations = 0

    logger.info("stream_loop: start conv=%d model=%r tools=%d max_iter=%d", conv.id, use_model, len(tools), max_iterations)

    # ── Memory pill ──────────────────────────────────────────────────────────
    if active_memory_count > 0:
        import uuid as _uuid_mod
        memory_uid = str(_uuid_mod.uuid4())
        logger.debug("stream_loop: emitting memory item count=%d uid=%s", active_memory_count, memory_uid)
        yield _sse({"type": "item_start", "item": {"uid": memory_uid, "kind": "memory", "count": active_memory_count}})
        yield _sse({"type": "item_done", "item": {"uid": memory_uid, "kind": "memory", "count": active_memory_count, "status": "done"}})
        stream_items.append({"uid": memory_uid, "kind": "memory", "count": active_memory_count})

    # ── Tool-call loop ───────────────────────────────────────────────────────
    while iterations <= max_iterations:
        full: list[str] = []
        tool_call_buffer: dict | None = None

        logger.info("stream_loop: LLM call iteration=%d messages=%d", iterations, len(messages))
        try:
            provider = get_chat_provider(settings)
            for piece in provider.stream_deltas_with_tools(
                messages, model=use_model, tools=tools if tools else None
            ):
                if isinstance(piece, dict) and piece.get("type") == "tool_call":
                    tool_call_buffer = piece.get("tool_call")
                    _tool_name = tool_call_buffer.get("name", "")
                    try:
                        _tool_params = json.loads(tool_call_buffer.get("arguments", "{}"))
                    except Exception:
                        _tool_params = {}
                    import uuid as _uuid_mod
                    _tool_uid = str(_uuid_mod.uuid4())
                    tool_call_buffer["_uid"] = _tool_uid  # stash for item_done
                    logger.info("stream_loop: tool_call name=%r uid=%s", _tool_name, _tool_uid)
                    yield _sse(_make_tool_item_start(_tool_name, _tool_params, _tool_uid))
                elif isinstance(piece, dict) and piece.get("type") == "delta":
                    text = piece.get("text", "")
                    full.append(text)
                    yield _sse({"type": "delta", "text": text})
                else:
                    full.append(str(piece))
                    yield _sse({"type": "delta", "text": str(piece)})

        except (ValueError, Exception) as exc:
            logger.error("stream_loop: error at iteration=%d exc=%s", iterations, exc, exc_info=True)
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
            logger.info("stream_loop: dispatching tool=%r uid=%s", _tool_name, _tool_uid)
            tool_result = _dispatch_tool_call(db, tool_call_buffer, kb_ids=kb_ids)
            used_kbs_meta.extend(tool_result.get("_used_kbs", []))

            done_item = _make_tool_item_done(_tool_name, tool_call_buffer, tool_result, _tool_uid)
            yield _sse(done_item)
            stream_items.append(_tool_item_for_persistence(_tool_name, tool_call_buffer, tool_result, _tool_uid))

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
            iterations += 1
            continue

        # Iteration cap — close open item if any
        if tool_call_buffer:
            _tool_name = tool_call_buffer.get("name", "")
            _tool_uid = tool_call_buffer.pop("_uid", str(_uuid_mod.uuid4()))
            logger.warning("stream_loop: max_iterations reached, closing tool=%r", _tool_name)
            yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer, {}, _tool_uid))
            stream_items.append(_tool_item_for_persistence(_tool_name, tool_call_buffer, {}, _tool_uid))

        # ── Persist final reply ──────────────────────────────────────────────
        reply = "".join(full)
        logger.info("stream_loop: persisting reply conv=%d reply_len=%d", conv.id, len(reply))
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

        msg_id = tail_message_id()
        logger.info("stream_loop: done conv=%d message_id=%d", conv.id, msg_id)
        yield _sse({"type": "done", "message_id": msg_id})
        return
```

Also add these three helpers just above `_stream_loop`:

```python
_WEB_SNIPPET_MAX = 400  # chars to store from web search result


def _make_tool_item_start(tool_name: str, params: dict, uid: str) -> dict:
    """Build the item_start SSE payload for a tool call (no result data yet).
    uid is generated by the caller and will be echoed in item_done."""
    if tool_name == "web_search":
        return {"type": "item_start", "item": {"uid": uid, "kind": "web_search", "query": params.get("query", "")}}
    if tool_name == "search_knowledge_base":
        query = params.get("query") or params.get("question") or ""
        return {"type": "item_start", "item": {"uid": uid, "kind": "kb_search", "query": query}}
    return {"type": "item_start", "item": {"uid": uid, "kind": "tool_call", "tool": tool_name, "params": params}}


def _make_tool_item_done(tool_name: str, tool_call_buffer: dict, tool_result: dict, uid: str) -> dict:
    """Build the item_done SSE payload — carries result data so the live chip can expand.

    The item dict is the exact same shape as what gets stored in extra.stream_items,
    so the frontend can store it directly in state without transformation.
    """
    try:
        params = json.loads(tool_call_buffer.get("arguments", "{}"))
    except Exception:
        params = {}

    if tool_name == "web_search":
        content = tool_result.get("content", "")
        snippet = content[:_WEB_SNIPPET_MAX] if content else ""
        return {"type": "item_done", "item": {
            "uid": uid,
            "kind": "web_search",
            "query": params.get("query", ""),
            "result_snippet": snippet,
            "status": "done",
        }}

    if tool_name == "search_knowledge_base":
        query = params.get("query") or params.get("question") or ""
        sources = [
            {"kb_name": kb.get("kb_name", ""), "chunks_used": kb.get("chunks_used", 0)}
            for kb in tool_result.get("_used_kbs", [])
        ]
        return {"type": "item_done", "item": {
            "uid": uid,
            "kind": "kb_search",
            "query": query,
            "sources": sources,
            "status": "done",
        }}

    return {"type": "item_done", "item": {"uid": uid, "kind": "tool_call", "tool": tool_name, "status": "done"}}


def _tool_item_for_persistence(tool_name: str, tool_call_buffer: dict, tool_result: dict, uid: str) -> dict:
    """Build the dict stored in extra.stream_items.

    Identical to item_done.item (minus 'status'). Frontend stores item_done.item
    directly in live state; backend stores this on save. Same shape = same render
    path for live and reload.
    """
    try:
        params = json.loads(tool_call_buffer.get("arguments", "{}"))
    except Exception:
        params = {}

    if tool_name == "web_search":
        content = tool_result.get("content", "")
        return {
            "uid": uid,
            "kind": "web_search",
            "query": params.get("query", ""),
            "result_snippet": content[:_WEB_SNIPPET_MAX] if content else "",
        }

    if tool_name == "search_knowledge_base":
        sources = [
            {"kb_name": kb.get("kb_name", ""), "chunks_used": kb.get("chunks_used", 0)}
            for kb in tool_result.get("_used_kbs", [])
        ]
        return {
            "uid": uid,
            "kind": "kb_search",
            "query": params.get("query") or params.get("question") or "",
            "sources": sources,
        }

    return {"uid": uid, "kind": "tool_call", "tool": tool_name}
```

The `_stream_loop` code block above already shows the updated call sites with `uid` threading.

Also update `_handle_stream_error` signature and body — it needs `uid` too (retrieve from the buffer's `_uid` key):

```python
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
        logger.exception("chat_stream_failed exc_type=%s", type(exc).__name__)
        detail = _friendly_api_error(exc)

    db.add(ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content=f"**Error:** {detail}",
    ))
    db.commit()

    if tool_call_buffer:
        import uuid as _uuid_mod
        _tool_name = tool_call_buffer.get("name", "")
        _tool_uid = tool_call_buffer.pop("_uid", str(_uuid_mod.uuid4()))
        yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer, {}, _tool_uid))

    yield _sse({"type": "error", "detail": detail})
    yield _sse({"type": "done", "message_id": tail_message_id()})
```

Also add `import uuid` at the top of `streaming_service.py` (module-level, not inline):

```python
import uuid as _uuid_mod
```

Also update `_setup_new_message` to assign `uid` to the user message `extra` before insert:

```python
def _setup_new_message(
    db: Session,
    conv: ChatConversation,
    body: StreamMessageBody,
    user: User,
) -> tuple[str, int, list]:
    user_content = body.content.strip()
    msg_extra: dict = {"uid": str(_uuid_mod.uuid4())}  # stable identity for every user message

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
    # ... rest unchanged
```

Also update `_handle_stream_error` — remove the `thinking_started` param (no longer needed):

```python
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
        logger.exception("chat_stream_failed exc_type=%s", type(exc).__name__)
        detail = _friendly_api_error(exc)

    db.add(ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content=f"**Error:** {detail}",
    ))
    db.commit()

    if tool_call_buffer:
        _tool_name = tool_call_buffer.get("name", "")
        yield _sse(_make_tool_item_done(_tool_name, tool_call_buffer))

    yield _sse({"type": "error", "detail": detail})
    yield _sse({"type": "done", "message_id": tail_message_id()})
```

Update the call site in `_stream_loop` error handler (already shown above — no `thinking_started` arg).

- [ ] **Step 4: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py -v 2>&1 | tail -20
```

Expected: all 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd backend && git add src/ai_portal/chat/streaming_service.py tests/chat/test_streaming_service_sse_shape.py
git commit -m "feat(streaming): flat SSE item kinds + persist stream_items in extra"
```

---

## Task 2: Frontend types — flatten StreamThreadItem

**Files:**
- Modify: `frontend/src/lib/chat-types.ts`

- [ ] **Step 1: Update `chat-types.ts`**

Replace the `ToolCallItem`, `MemoryItem`, `ThinkingChildItem`, `ThinkingItem`, `StreamItem` section at the bottom of the file with:

```typescript
export type MemoryThreadItem = {
  uid: string
  kind: 'memory'
  count: number
  status: 'running' | 'done'
}

export type WebSearchThreadItem = {
  uid: string
  kind: 'web_search'
  query: string
  result_snippet?: string   // populated on item_done and from extra.stream_items
  status: 'running' | 'done'
}

export type KBSearchThreadItem = {
  uid: string
  kind: 'kb_search'
  query: string
  sources?: { kb_name: string; chunks_used: number }[]  // populated on item_done
  status: 'running' | 'done'
}

export type GenericToolThreadItem = {
  uid: string
  kind: 'tool_call'
  tool: string
  params: Record<string, string>
  status: 'running' | 'done'
}

/** Union of all thread-level stream item types. */
export type StreamThreadItem =
  | MemoryThreadItem
  | WebSearchThreadItem
  | KBSearchThreadItem
  | GenericToolThreadItem
```

Remove the old types entirely:
- `ToolCallItem`
- `MemoryItem`
- `ThinkingChildItem`
- `ThinkingItem`
- `StreamItem`

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: errors in `StreamingThinkingBlock.tsx` and `ConversationThreadPage.tsx` because they still use old types. This is expected — we fix them in subsequent tasks.

- [ ] **Step 3: Commit**

```bash
cd frontend && git add src/lib/chat-types.ts
git commit -m "refactor(types): flatten StreamThreadItem — remove ThinkingItem wrapper"
```

---

## Task 3: Create `ThreadItemChip.tsx`

**Files:**
- Create: `frontend/src/components/chat/ThreadItemChip.tsx`
- Delete: `frontend/src/components/chat/StreamingThinkingBlock.tsx`

Visual contract from design:
- **Memory** (blue) — `🧠 Loading memories…` + spinner → `🧠 N memories loaded ✓` (non-expandable)
- **Web Search** (neutral/stone) — `🌐 Searching for "query"…` + spinner → `🌐 Web Searched "query" ▶` (expandable: query + snippet placeholder)
- **KB Search** (purple) — `📚 Searching knowledge base for "query"…` + spinner → `📚 KB Searched "query" ▶` (expandable: query)
- **Generic tool** (gray) — `🔧 Running tool_name…` + spinner → `🔧 tool_name ▶` (expandable: params)

- [ ] **Step 1: Create the component**

```tsx
// frontend/src/components/chat/ThreadItemChip.tsx
import { Check, Globe, Library, Brain, Wrench, ChevronRight, ChevronDown, Loader2 } from 'lucide-react'
import * as React from 'react'
import type { StreamThreadItem } from '~/lib/chat-types'

interface Props {
  item: StreamThreadItem
}

type Theme = {
  border: string
  bg: string
  text: string
  iconColor: string
  chevronColor: string
  labelColor: string
}

function getTheme(kind: StreamThreadItem['kind']): Theme {
  switch (kind) {
    case 'memory':
      return {
        border: 'border-blue-900/60 dark:border-blue-900/40',
        bg: 'bg-blue-950/40 dark:bg-blue-950/30',
        text: 'text-blue-300 dark:text-blue-300',
        iconColor: 'text-blue-400',
        chevronColor: 'text-blue-800',
        labelColor: 'text-blue-700 dark:text-blue-600',
      }
    case 'web_search':
      return {
        border: 'border-neutral-700/60',
        bg: 'bg-neutral-900/50',
        text: 'text-neutral-300',
        iconColor: 'text-neutral-400',
        chevronColor: 'text-neutral-600',
        labelColor: 'text-neutral-600',
      }
    case 'kb_search':
      return {
        border: 'border-purple-900/60',
        bg: 'bg-purple-950/30',
        text: 'text-purple-300',
        iconColor: 'text-purple-400',
        chevronColor: 'text-purple-800',
        labelColor: 'text-purple-700',
      }
    default:
      return {
        border: 'border-neutral-700/60',
        bg: 'bg-neutral-900/50',
        text: 'text-neutral-400',
        iconColor: 'text-neutral-500',
        chevronColor: 'text-neutral-600',
        labelColor: 'text-neutral-600',
      }
  }
}

function getIcon(kind: StreamThreadItem['kind']) {
  switch (kind) {
    case 'memory': return <Brain className="size-3.5 shrink-0" strokeWidth={2} />
    case 'web_search': return <Globe className="size-3.5 shrink-0" strokeWidth={2} />
    case 'kb_search': return <Library className="size-3.5 shrink-0" strokeWidth={2} />
    default: return <Wrench className="size-3.5 shrink-0" strokeWidth={2} />
  }
}

function getRunningLabel(item: StreamThreadItem): string {
  switch (item.kind) {
    case 'memory': return 'Loading memories\u2026'
    case 'web_search': return `Searching for \u201c${item.query}\u201d\u2026`
    case 'kb_search': return `Searching knowledge base for \u201c${item.query}\u201d\u2026`
    case 'tool_call': return `Running ${item.tool}\u2026`
  }
}

function getDoneLabel(item: StreamThreadItem): React.ReactNode {
  switch (item.kind) {
    case 'memory': return <>{item.count} {item.count === 1 ? 'memory' : 'memories'} loaded</>
    case 'web_search': return <>Web Searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'kb_search': return <>KB Searched <em className="not-italic opacity-70">&ldquo;{item.query}&rdquo;</em></>
    case 'tool_call': return <>{item.tool}</>
  }
}

function ExpandedDetails({ item }: { item: StreamThreadItem }) {
  switch (item.kind) {
    case 'web_search':
      return (
        <div className="flex flex-col gap-2 text-[11px]">
          <div>
            <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Query</div>
            <div className="text-neutral-300">{item.query}</div>
          </div>
          {item.result_snippet && (
            <div>
              <div className="text-neutral-600 dark:text-neutral-500 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Results</div>
              <div className="text-neutral-400 whitespace-pre-wrap leading-relaxed">{item.result_snippet}</div>
            </div>
          )}
        </div>
      )
    case 'kb_search':
      return (
        <div className="flex flex-col gap-2 text-[11px]">
          <div>
            <div className="text-purple-700 dark:text-purple-600 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Query</div>
            <div className="text-purple-300">{item.query}</div>
          </div>
          {item.sources && item.sources.length > 0 && (
            <div>
              <div className="text-purple-700 dark:text-purple-600 font-semibold uppercase tracking-wide text-[10px] mb-0.5">Sources</div>
              <div className="flex flex-col gap-0.5">
                {item.sources.map((s, i) => (
                  <div key={i} className="text-purple-300">
                    {s.kb_name}
                    {s.chunks_used > 0 && (
                      <span className="text-purple-600 ml-1">· {s.chunks_used} chunks</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    case 'tool_call':
      return (
        <div className="flex flex-col gap-1 text-[11px]">
          <div className="text-neutral-600 font-semibold uppercase tracking-wide text-[10px]">Tool</div>
          <div className="text-neutral-300">{item.tool}</div>
        </div>
      )
    default:
      return null
  }
}

export function ThreadItemChip({ item }: Props) {
  const [expanded, setExpanded] = React.useState(false)
  const theme = getTheme(item.kind)
  const isRunning = item.status === 'running'
  const isMemory = item.kind === 'memory'
  const canExpand = !isMemory && !isRunning

  const chipClass = `inline-flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[12px] ${theme.border} ${theme.bg} ${theme.text}`

  if (isRunning) {
    return (
      <div data-testid="thread-item-chip" data-kind={item.kind} data-status="running">
        <div className={chipClass}>
          <span className={theme.iconColor}>{getIcon(item.kind)}</span>
          <span>{getRunningLabel(item)}</span>
          <Loader2 className="size-3 animate-spin shrink-0 text-current opacity-60" strokeWidth={2} />
        </div>
      </div>
    )
  }

  // Memory — non-expandable done chip
  if (isMemory) {
    return (
      <div data-testid="thread-item-chip" data-kind="memory" data-status="done">
        <div className={chipClass}>
          <span className={theme.iconColor}>{getIcon(item.kind)}</span>
          <span>{getDoneLabel(item)}</span>
          <Check className="size-3 shrink-0 text-blue-500" strokeWidth={2.5} />
        </div>
      </div>
    )
  }

  // Expandable done chip
  return (
    <div data-testid="thread-item-chip" data-kind={item.kind} data-status="done">
      <button
        data-testid="thread-item-chip-toggle"
        onClick={() => setExpanded(e => !e)}
        className={`${chipClass} cursor-pointer hover:opacity-90 transition-opacity`}
      >
        <span className={theme.iconColor}>{getIcon(item.kind)}</span>
        <span>{getDoneLabel(item)}</span>
        <Check className="size-3 shrink-0 text-green-500" strokeWidth={2.5} />
        <span className={theme.chevronColor}>
          {expanded
            ? <ChevronDown className="size-3" strokeWidth={2} />
            : <ChevronRight className="size-3" strokeWidth={2} />}
        </span>
      </button>
      {expanded && (
        <div
          data-testid="thread-item-details"
          className={`mt-1.5 px-3 py-2 rounded-lg border ${theme.border} ${theme.bg} max-w-sm`}
        >
          <ExpandedDetails item={item} />
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Delete `StreamingThinkingBlock.tsx`**

```bash
rm frontend/src/components/chat/StreamingThinkingBlock.tsx
```

- [ ] **Step 3: Verify TypeScript on the new file**

```bash
cd frontend && npx tsc --noEmit 2>&1 | grep ThreadItemChip
```

Expected: no errors for the new file (errors in ConversationThreadPage are still expected).

- [ ] **Step 4: Commit**

```bash
cd frontend && git add src/components/chat/ThreadItemChip.tsx
git rm src/components/chat/StreamingThinkingBlock.tsx
git commit -m "feat(ui): ThreadItemChip — per-type spinner→chip with expand (replaces ThinkingBlock)"
```

---

## Task 4: Update `ConversationThreadPage.tsx` — SSE handler + inline rendering

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

This is the largest change. Four sub-tasks:
1. Update imports and state
2. Update SSE `applyEvents` handler
3. Render `ThreadItemChip` inline in the streaming block
4. Render persisted `stream_items` in each assistant message

- [ ] **Step 1: Update imports and state**

Replace the import of `StreamingThinkingBlock` and old types with:

```tsx
import { ThreadItemChip } from '~/components/chat/ThreadItemChip'
import {
  DEFAULT_CAPABILITIES,
  type CapabilityToggles,
  type ChatMessage,
  type Conversation,
  type ConversationSettings,
  type UsedKbEntry,
  type StreamThreadItem,
  type GenericToolThreadItem,
} from '~/lib/chat-types'
```

Replace state declarations:

```tsx
// OLD:
const [streamItems, setStreamItems] = React.useState<StreamItem[]>([])
const [thinkingExpanded, setThinkingExpanded] = React.useState(false)

// NEW:
const [streamThreadItems, setStreamThreadItems] = React.useState<StreamThreadItem[]>([])
```

In the `useEffect` that resets on `conversationId` change, replace:
```tsx
setStreamItems([])
setThinkingExpanded(false)
// with:
setStreamThreadItems([])
```

In `runStream` at the top of the function, replace:
```tsx
setStreamItems([])
setThinkingExpanded(false)
// with:
setStreamThreadItems([])
```

In the `catch` block inside `runStream`, replace:
```tsx
setStreamItems([])
setThinkingExpanded(false)
// with:
setStreamThreadItems([])
```

- [ ] **Step 2: Replace `applyEvents` SSE handler**

Replace the entire `applyEvents` function body with:

```tsx
const applyEvents = (events: unknown[]) => {
  for (const ev of events) {
    const e = ev as {
      type?: string
      text?: string
      detail?: string
      item?: {
        kind?: string
        query?: string
        count?: number
        tool?: string
        params?: Record<string, string>
        status?: string
      }
    }

    if (e.type === 'item_start') {
      const item = e.item ?? {}
      const uid = (item.uid as string) ?? crypto.randomUUID()  // fallback for older SSE shape
      setStreamThreadItems(prev => {
        if (item.kind === 'memory') {
          return [...prev, { uid, kind: 'memory', count: item.count ?? 0, status: 'running' }]
        }
        if (item.kind === 'web_search') {
          return [...prev, { uid, kind: 'web_search', query: item.query ?? '', status: 'running' }]
        }
        if (item.kind === 'kb_search') {
          return [...prev, { uid, kind: 'kb_search', query: item.query ?? '', status: 'running' }]
        }
        if (item.kind === 'tool_call') {
          return [...prev, { uid, kind: 'tool_call', tool: item.tool ?? '', params: item.params ?? {}, status: 'running' }]
        }
        return prev
      })
    }

    if (e.type === 'item_done') {
      const item = e.item ?? {}
      setStreamThreadItems(prev => {
        // Match by uid — O(1), no positional ambiguity
        const idx = prev.findIndex(it => it.uid === item.uid)
        if (idx === -1) return prev
        return prev.map((it, i) => {
          if (i !== idx) return it
          // Merge all result fields from item_done (result_snippet, sources, etc.)
          // Backend sends exact same shape as persistence format, just with status added
          const { status: _s, ...resultFields } = item as Record<string, unknown>
          return { ...it, ...resultFields, status: 'done' as const }
        })
      })
    }

    if (e.type === 'delta' && e.text) {
      assembled += e.text
      setStreamingText(assembled)
    }
    if (e.type === 'error') {
      streamHadSseErrorRef.current = true
      setSendError(
        typeof e.detail === 'string' && e.detail.trim()
          ? e.detail
          : 'The assistant returned an error.',
      )
    }
    if (e.type === 'done') {
      streamReachedTerminal = true
    }
  }
}
```

- [ ] **Step 3: Update the streaming render block**

Find the streaming block (around line 994–1036):

```tsx
{streaming && (
  <div className="mt-1 w-full">
    <div
      className="stream-surface-breathe w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75"
      aria-live="polite"
      aria-busy="true"
      aria-label="Assistant is responding"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          assistant
        </span>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-neutral-400">streaming…</span>
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
            onClick={stopStream}
          >
            Stop
          </button>
        </div>
      </div>
      <StreamingThinkingBlock
        items={streamItems}
        expanded={thinkingExpanded}
        onToggle={() => setThinkingExpanded(e => !e)}
      />
      {streamingText ? (
        <MarkdownMessage
          content={streamingText}
          streaming
          className="text-neutral-900 dark:text-neutral-100"
        />
      ) : streamItems.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-neutral-400">
          <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
          Waiting for tokens…
        </p>
      ) : null}
    </div>
  </div>
)}
```

Replace with:

```tsx
{streaming && (
  <div className="mt-1 w-full">
    <div
      className="stream-surface-breathe w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75"
      aria-live="polite"
      aria-busy="true"
      aria-label="Assistant is responding"
    >
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          assistant
        </span>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-neutral-400">streaming…</span>
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-[10px] font-medium text-red-600 underline decoration-dotted dark:text-red-400"
            onClick={stopStream}
          >
            Stop
          </button>
        </div>
      </div>
      {streamThreadItems.length > 0 && (
        <div className="mb-2 flex flex-col gap-1.5">
          {streamThreadItems.map((item, i) => (
            <ThreadItemChip key={i} item={item} />
          ))}
        </div>
      )}
      {streamingText ? (
        <MarkdownMessage
          content={streamingText}
          streaming
          className="text-neutral-900 dark:text-neutral-100"
        />
      ) : streamThreadItems.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-neutral-400">
          <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
          Waiting for tokens…
        </p>
      ) : null}
    </div>
  </div>
)}
```

- [ ] **Step 4: Remove the stale post-stream thinking block**

Remove the block that renders `StreamingThinkingBlock` after streaming ends (lines ~982–993):

```tsx
// DELETE this entire block:
{!streaming &&
  streamItems.some((i) => i.kind === 'thinking') && (
    <div className="mt-1 w-full">
      <div className="w-full max-w-none rounded-2xl bg-white/90 px-4 py-3 dark:bg-neutral-900/75">
        <StreamingThinkingBlock
          items={streamItems}
          expanded={thinkingExpanded}
          onToggle={() => setThinkingExpanded((e) => !e)}
        />
      </div>
    </div>
  )}
```

- [ ] **Step 5: Render persisted stream_items in each assistant message**

Inside the `visibleMessages.map` render, find where `<MarkdownMessage content={m.content} .../>` is rendered for assistant messages. Add stream items before it:

```tsx
// Before <MarkdownMessage content={m.content} .../> inside the message body div,
// add for assistant messages:
{m.role === 'assistant' && (() => {
  const persistedItems = m.extra?.stream_items as StreamThreadItem[] | undefined
  if (!persistedItems?.length) return null
  return (
    <div className="mb-2 flex flex-col gap-1.5">
      {persistedItems.map((item, i) => (
        <ThreadItemChip key={i} item={item} />
      ))}
    </div>
  )
})()}
<MarkdownMessage
  content={m.content}
  ...
/>
```

The exact insertion point is inside the content area `<div>` (after the user attachments list), before the `<MarkdownMessage>` call. Using an IIFE keeps the JSX clean. Alternatively, extract to a small helper:

```tsx
function PersistedStreamItems({ message }: { message: ChatMessage }) {
  const items = message.extra?.stream_items as StreamThreadItem[] | undefined
  if (!items?.length) return null
  return (
    <div className="mb-2 flex flex-col gap-1.5">
      {items.map((item, i) => (
        <ThreadItemChip key={i} item={item} />
      ))}
    </div>
  )
}
```

Use it as `<PersistedStreamItems message={m} />` before `<MarkdownMessage>` for assistant messages.

- [ ] **Step 6: Verify TypeScript compiles clean**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -30
```

Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
cd frontend && git add src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(chat): render ThreadItemChip inline — live streaming + persisted on reload"
```

---

## Task 5: Update E2E tests

**Files:**
- Modify: `frontend/e2e/chat/chat-tool-thinking-block.spec.ts`
- Modify: `frontend/e2e/chat/chat-tool-web-search.spec.ts`
- Modify: `frontend/e2e/chat/chat-tool-kb-search.spec.ts`

### New SSE shape

The new SSE sequences use flat kinds — no `thinking` wrapper:

```typescript
// web_search
e({ type: 'item_start', item: { kind: 'web_search', query: 'oil price' } }) +
e({ type: 'item_done', item: { kind: 'web_search', query: 'oil price', status: 'done' } }) +

// kb_search
e({ type: 'item_start', item: { kind: 'kb_search', query: 'Q1 report' } }) +
e({ type: 'item_done', item: { kind: 'kb_search', query: 'Q1 report', status: 'done' } }) +

// memory
e({ type: 'item_start', item: { kind: 'memory', count: 2 } }) +
e({ type: 'item_done', item: { kind: 'memory', count: 2, status: 'done' } }) +
```

### New selectors

| Old selector | New selector |
|---|---|
| `[data-testid="chat-thinking-pill"]` | N/A — removed |
| `[data-testid="chat-thinking-block"]` | N/A — removed |
| `[data-testid="chat-tool-card"]` | `[data-testid="thread-item-chip"]` |
| `[data-testid="chat-tool-card-name"]` | check `data-kind` attribute |
| `[data-testid="chat-tool-card-param"]` | chip text content |
| `[data-testid="chat-tool-card-status"]` | `data-status` attribute |

- [ ] **Step 1: Rewrite `chat-tool-thinking-block.spec.ts`**

```typescript
import { test, expect } from '@playwright/test'
import { createEmptyConversation } from '../support/create-conversation'

test.describe.configure({ mode: 'serial' })

function buildToolStreamSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'memory', count: 1 } }) +
    e({ type: 'item_done', item: { kind: 'memory', count: 1, status: 'done' } }) +
    e({ type: 'item_start', item: { kind: 'web_search', query: 'latest news' } }) +
    e({ type: 'item_done', item: { kind: 'web_search', query: 'latest news', status: 'done' } }) +
    e({ type: 'item_start', item: { kind: 'kb_search', query: 'news' } }) +
    e({ type: 'item_done', item: { kind: 'kb_search', query: 'news', status: 'done' } }) +
    e({ type: 'delta', text: 'Here is the latest news based on my web search.' }) +
    e({ type: 'done', message_id: messageId })
  )
}

async function setupSseReplay(
  page: import('@playwright/test').Page,
  convId: number,
  sseText: string,
) {
  await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: sseText,
    })
  })
}

test.describe('Thread item chips UI', () => {
  test('item chips are visible after stream ends', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await setupSseReplay(page, convId, buildToolStreamSse(convId * 100))
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('What is the latest news?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to complete
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    // All three item chips rendered (memory + web_search + kb_search)
    const chips = page.getByTestId('thread-item-chip')
    await expect(chips).toHaveCount(3)
  })

  test('memory chip shows count and is not expandable', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await setupSseReplay(page, convId, buildToolStreamSse(convId * 100))
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('test')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const memoryChip = page.getByTestId('thread-item-chip').filter({ hasText: 'memory' }).first()
    // Memory chip has kind=memory and status=done
    await expect(page.locator('[data-testid="thread-item-chip"][data-kind="memory"]')).toBeVisible()
    await expect(page.locator('[data-testid="thread-item-chip"][data-kind="memory"]')).toHaveAttribute('data-status', 'done')
    // Memory chip has no toggle button
    await expect(page.locator('[data-testid="thread-item-chip"][data-kind="memory"] [data-testid="thread-item-chip-toggle"]')).toBeHidden()
  })

  test('web_search chip is expandable', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)
    await setupSseReplay(page, convId, buildToolStreamSse(convId * 100))
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })

    await page.getByRole('textbox', { name: /message/i }).fill('test')
    await page.getByRole('button', { name: /send message/i }).click()
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    const wsChip = page.locator('[data-testid="thread-item-chip"][data-kind="web_search"]')
    await expect(wsChip).toBeVisible()
    await expect(wsChip).toHaveAttribute('data-status', 'done')

    // Click toggle to expand
    await wsChip.getByTestId('thread-item-chip-toggle').click()
    await expect(wsChip.locator('[data-testid="thread-item-details"]')).toBeVisible()
    await expect(wsChip.locator('[data-testid="thread-item-details"]')).toContainText('latest news')
  })

  test('no item chips for plain text reply', async ({ page, request }) => {
    const base = process.env.E2E_API_URL ?? 'http://127.0.0.1:8001'
    const convId = await createEmptyConversation(request, base)

    const plainSse =
      'data: {"type":"delta","text":"Hello!"}\n\n' +
      'data: {"type":"done","message_id":999}\n\n'

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        headers: { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache' },
        body: plainSse,
      })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('Say hello')
    await page.getByRole('button', { name: /send message/i }).click()

    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })
    await expect(page.getByTestId('thread-item-chip')).toHaveCount(0)
  })
})
```

- [ ] **Step 2: Update `chat-tool-web-search.spec.ts`**

Replace `buildWebSearchSse` with:

```typescript
function buildWebSearchSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'web_search', query: 'current oil price' } }) +
    e({ type: 'item_done', item: { kind: 'web_search', query: 'current oil price', status: 'done' } }) +
    e({ type: 'delta', text: 'Based on web search, oil is $80/barrel.' }) +
    e({ type: 'done', message_id: messageId })
  )
}
```

In `Test A`, replace all references to old selectors:

```typescript
// Replace the pill/block/card assertions with:
await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

const wsChip = page.locator('[data-testid="thread-item-chip"][data-kind="web_search"]')
await expect(wsChip).toBeVisible()
await expect(wsChip).toHaveAttribute('data-status', 'done')

// Click to expand and check query
await wsChip.getByTestId('thread-item-chip-toggle').click()
await expect(wsChip.locator('[data-testid="thread-item-details"]')).toContainText('current oil price')
```

- [ ] **Step 3: Update `chat-tool-kb-search.spec.ts`**

Replace `buildKbSearchSse` with:

```typescript
function buildKbSearchSse(messageId: number, kbId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'kb_search', query: 'project summary' } }) +
    e({ type: 'item_done', item: { kind: 'kb_search', query: 'project summary', status: 'done' } }) +
    e({ type: 'delta', text: 'Based on your documents, the project summary is...' }) +
    e({ type: 'done', message_id: messageId })
  )
}
```

In `Test A`, replace all old selectors:

```typescript
// Replace pill/block/card assertions with:
await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

const kbChip = page.locator('[data-testid="thread-item-chip"][data-kind="kb_search"]')
await expect(kbChip).toBeVisible()
await expect(kbChip).toHaveAttribute('data-status', 'done')

await kbChip.getByTestId('thread-item-chip-toggle').click()
await expect(kbChip.locator('[data-testid="thread-item-details"]')).toContainText('project summary')
```

- [ ] **Step 4: Run the updated E2E tests**

First start the E2E backend:
```bash
./scripts/e2e-up.sh
```

Then run:
```bash
cd frontend && pnpm test:e2e:filter "chat-tool" 2>&1 | tail -40
```

Expected: all tests in the three files pass.

- [ ] **Step 5: Run full E2E suite**

```bash
cd frontend && pnpm test:e2e 2>&1 | tail -20
```

Expected: all tests pass (including memories-chat, chat-kb, etc.).

- [ ] **Step 6: Commit**

```bash
cd frontend && git add e2e/chat/chat-tool-thinking-block.spec.ts e2e/chat/chat-tool-web-search.spec.ts e2e/chat/chat-tool-kb-search.spec.ts
git commit -m "test(e2e): update tool chip tests for flat StreamThreadItem (no thinking wrapper)"
```

---

## Self-Review

**Spec coverage:**
- ✅ Flat per-type items (memory/web_search/kb_search/tool_call) — Tasks 1–3
- ✅ Same visual live and on reload — Task 4 (rendering from both `streamThreadItems` and `extra.stream_items`)
- ✅ Position stability (chips inline in message, not outside `<ul>`) — Task 4 Step 3–4
- ✅ Memory non-expandable — ThreadItemChip
- ✅ Web/KB/Tool expandable — ThreadItemChip
- ✅ Persist `stream_items` in DB — Task 1 Step 3
- ✅ No DB migration needed — JSONB column already exists

**Placeholder scan:** None found.

**Type consistency:**
- `StreamThreadItem` defined in Task 2, used in Tasks 3 and 4 — consistent
- `item.kind` values: `'memory' | 'web_search' | 'kb_search' | 'tool_call'` — consistent across backend SSE, frontend handler, and component
- `data-testid="thread-item-chip"` used in component (Task 3) and E2E tests (Task 5) — consistent
- `data-testid="thread-item-chip-toggle"` used in component and tests — consistent
- `data-testid="thread-item-details"` used in component and tests — consistent
