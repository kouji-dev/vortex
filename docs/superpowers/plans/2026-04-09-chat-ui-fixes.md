# Chat UI Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix five chat UI/UX bugs: tool-call chips stuck as spinners / wrong icon / disappear after stream, unnecessary messages API refetch after stream, attachment button position on desktop, `extra` field always null, and user message not shown optimistically while streaming.

**Architecture:** Backend changes to `_stream_loop` in `streaming_service.py` (uid emission, kind mapping, stream_items accumulation/persistence, remove thinking wrapper). Frontend changes to `ConversationThreadPage.tsx` (optimistic user message display, streaming surface visibility, message_id capture, optimistic cache for both user+assistant) and `ChatComposerDock.tsx` (paperclip move).

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), React/TypeScript/TanStack Query (frontend)

---

## File Map

| File | What changes |
|---|---|
| `backend/src/ai_portal/chat/streaming_service.py` | Remove thinking wrapper; add uuid4 import; emit uid in item_start/item_done; map tool name → kind; accumulate and persist stream_items; pass uid/kind to error handler |
| `frontend/src/components/chat/ConversationThreadPage.tsx` | Optimistic user message display; streaming surface render condition; streamEndedRef handoff; message_id capture in done event; optimistic cache update (user + assistant) in finally |
| `frontend/src/components/chat/ChatComposerDock.tsx` | Move hidden file input + paperclip button to bottom bar; update chips section condition |
| `frontend/e2e/chat/chat-attachments.spec.ts` | Update file input selector now that it lives outside `chat-composer-attachments` |
| `frontend/e2e/chat/chat-tool-web-search.spec.ts` | Already written; run to confirm passes after backend fix |

---

## Task 1 — Backend: remove thinking wrapper, fix memory uid emission

Tests already written in `backend/tests/chat/test_streaming_service_sse_shape.py` — tests 1 (`test_no_thinking_events_in_sse`) and 2 (`test_memory_item_emitted_flat`).

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`
- Test: `backend/tests/chat/test_streaming_service_sse_shape.py`

- [ ] **Step 1: Run existing tests to confirm they fail**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py::test_no_thinking_events_in_sse tests/chat/test_streaming_service_sse_shape.py::test_memory_item_emitted_flat -v
```
Expected: both FAIL (thinking events emitted, no uid on memory items).

- [ ] **Step 2: Add uuid4 import at the top of streaming_service.py**

Current imports (around line 8) — add after `import threading`:
```python
from uuid import uuid4
```

- [ ] **Step 3: Remove thinking_started flag and all thinking wrapper events from _stream_loop**

In `_stream_loop` (starts at line 310):

Remove the `thinking_started = False` declaration (line 328).

Replace the memory block (lines 333–339):
```python
# ── Memory pill ──────────────────────────────────────────────────────────────
if active_memory_count > 0:
    _memory_uid = str(uuid4())
    stream_items.append({"uid": _memory_uid, "kind": "memory", "count": active_memory_count})
    yield _sse({"type": "item_start", "item": {"uid": _memory_uid, "kind": "memory", "count": active_memory_count}})
    yield _sse({"type": "item_done", "item": {"uid": _memory_uid, "kind": "memory", "count": active_memory_count, "status": "done"}})
```

Note: `stream_items` will be declared in Task 3 — for now add `stream_items: list[dict] = []` at the start of `_stream_loop` alongside `used_kbs_meta`.

Replace the lazy thinking open on first tool call (lines 361–363):
```python
# (remove the thinking open entirely — no thinking wrapper)
```

Replace the `if thinking_started:` block at the end of `_stream_loop` (lines 447–448) — remove it entirely.

- [ ] **Step 4: Update _handle_stream_error to remove thinking events**

In `_handle_stream_error` (lines 488–519), the function receives `thinking_started`. Since we no longer use that flag, change its signature and body.

Add `tool_item_uid: str | None = None, tool_item_kind: str | None = None` parameters and remove `thinking_started`:
```python
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

    db.add(ChatMessage(
        conversation_id=conv.id,
        role="assistant",
        content=f"**Error:** {detail}",
    ))
    db.commit()

    if tool_call_buffer and tool_item_uid and tool_item_kind:
        yield _sse({
            "type": "item_done",
            "item": {"uid": tool_item_uid, "kind": tool_item_kind, "tool": tool_call_buffer.get("name", ""), "status": "done"},
        })

    yield _sse({"type": "error", "detail": detail})
    yield _sse({"type": "done", "message_id": tail_message_id()})
```

Update the `_handle_stream_error` call site in `_stream_loop` (lines 378–383):
```python
yield from _handle_stream_error(
    db=db, conv=conv, exc=exc,
    tool_call_buffer=tool_call_buffer,
    tool_item_uid=_tool_item_uid if 'tool_call_buffer' in dir() and tool_call_buffer else None,
    tool_item_kind=_tool_item_kind if 'tool_call_buffer' in dir() and tool_call_buffer else None,
    tail_message_id=tail_message_id,
)
```

Note: `_tool_item_uid` and `_tool_item_kind` will be declared in Task 2. For now, pass `None`:
```python
yield from _handle_stream_error(
    db=db, conv=conv, exc=exc,
    tool_call_buffer=tool_call_buffer,
    tool_item_uid=None,
    tool_item_kind=None,
    tail_message_id=tail_message_id,
)
```

- [ ] **Step 5: Run tests to confirm they pass**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py::test_no_thinking_events_in_sse tests/chat/test_streaming_service_sse_shape.py::test_memory_item_emitted_flat -v
```
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "fix(stream): remove thinking wrapper; emit memory item with uid"
```

---

## Task 2 — Backend: uid + kind mapping for tool calls + result_snippet in item_done

Test already written: `test_web_search_item_kind` in `test_streaming_service_sse_shape.py`.

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`
- Test: `backend/tests/chat/test_streaming_service_sse_shape.py`

- [ ] **Step 1: Run test to confirm it fails**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py::test_web_search_item_kind -v
```
Expected: FAIL (kind is 'tool_call', no uid, no result_snippet).

- [ ] **Step 2: Replace tool-call item_start emission in _stream_loop**

In the `for piece in provider.stream_deltas_with_tools(...)` loop, find the tool_call detection block (currently emits `{"kind": "tool_call", "tool": ..., "params": ...}`).

Replace lines 352–367 with:
```python
if isinstance(piece, dict) and piece.get("type") == "tool_call":
    tool_call_buffer = piece.get("tool_call")
    _tool_name = tool_call_buffer.get("name", "")
    try:
        _tool_params = json.loads(tool_call_buffer.get("arguments", "{}"))
    except Exception:
        _tool_params = {}
    # Map tool name to SSE kind
    if _tool_name == "web_search":
        _tool_item_kind = "web_search"
    elif _tool_name == "kb_search":
        _tool_item_kind = "kb_search"
    else:
        _tool_item_kind = "tool_call"
    _tool_item_uid = str(uuid4())
    logger.info("stream_loop: tool_call name=%r kind=%r params=%r", _tool_name, _tool_item_kind, _tool_params)
    _query = _tool_params.get("query", "")
    item_start_payload: dict = {"uid": _tool_item_uid, "kind": _tool_item_kind, "tool": _tool_name, "params": _tool_params}
    if _query:
        item_start_payload["query"] = _query
    yield _sse({"type": "item_start", "item": item_start_payload})
```

- [ ] **Step 3: Replace item_done emission after tool execution**

After `tool_result = _dispatch_tool_call(...)` (lines 389–409), replace the `yield _sse({"type": "item_done", ...})` with:
```python
_result_snippet = (tool_result.get("content") or "")[:500]
item_done_payload: dict = {
    "uid": _tool_item_uid,
    "kind": _tool_item_kind,
    "tool": _tool_name,
    "status": "done",
}
if _result_snippet:
    item_done_payload["result_snippet"] = _result_snippet
yield _sse({"type": "item_done", "item": item_done_payload})
```

Also replace the iteration-cap `item_done` (lines 414–418):
```python
if tool_call_buffer:
    logger.warning("stream_loop: max_iterations=%d reached, closing tool=%r", max_iterations, _tool_name)
    yield _sse({
        "type": "item_done",
        "item": {"uid": _tool_item_uid, "kind": _tool_item_kind, "tool": _tool_name, "status": "done"},
    })
```

- [ ] **Step 4: Update _handle_stream_error call site to pass uid and kind**

Update the call to `_handle_stream_error` in the except block:
```python
yield from _handle_stream_error(
    db=db, conv=conv, exc=exc,
    tool_call_buffer=tool_call_buffer,
    tool_item_uid=_tool_item_uid if tool_call_buffer else None,
    tool_item_kind=_tool_item_kind if tool_call_buffer else None,
    tail_message_id=tail_message_id,
)
```

Note: `_tool_item_uid` and `_tool_item_kind` are only defined once a tool call has been detected in the current iteration. Use a try/except or pre-initialize them to `None` at the top of each iteration:
```python
while iterations <= max_iterations:
    full: list[str] = []
    tool_call_buffer: dict | None = None
    _tool_item_uid: str | None = None
    _tool_item_kind: str | None = None
    _tool_name: str = ""
    ...
```

- [ ] **Step 5: Run test to confirm it passes**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py::test_web_search_item_kind -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "fix(stream): emit uid + correct kind for tool-call items; add result_snippet to item_done"
```

---

## Task 3 — Backend: stream_items accumulation and persistence

Test already written: `test_stream_items_persisted_in_extra` in `test_streaming_service_sse_shape.py`.

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`
- Test: `backend/tests/chat/test_streaming_service_sse_shape.py`

- [ ] **Step 1: Run test to confirm it fails**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py::test_stream_items_persisted_in_extra -v
```
Expected: FAIL (`extra` is None, no `stream_items`).

- [ ] **Step 2: Add stream_items accumulator at the top of _stream_loop**

Right after `used_kbs_meta: list[dict] = []` (line 325), add:
```python
stream_items: list[dict] = []
```

- [ ] **Step 3: Append to stream_items in memory item_start**

In the memory block (already updated in Task 1), ensure `stream_items.append(...)` is called. The Task 1 code already includes this line — verify it's there:
```python
stream_items.append({"uid": _memory_uid, "kind": "memory", "count": active_memory_count})
```

- [ ] **Step 4: Append to stream_items in tool item_start**

Right after `yield _sse({"type": "item_start", "item": item_start_payload})` in Task 2:
```python
# Accumulate for persistence (no status field)
stream_item_entry: dict = {"uid": _tool_item_uid, "kind": _tool_item_kind}
if _query:
    stream_item_entry["query"] = _query
stream_items.append(stream_item_entry)
```

- [ ] **Step 5: Update stream_items entry in item_done**

After computing `_result_snippet` and before yielding `item_done`, find the matching entry and update it:
```python
# Update stream_items entry with result fields (no status field in persisted copy)
for _si in stream_items:
    if _si.get("uid") == _tool_item_uid:
        if _result_snippet:
            _si["result_snippet"] = _result_snippet
        break
```

- [ ] **Step 6: Persist stream_items in extra**

Replace the `db.add(ChatMessage(...))` block (currently lines 423–428):
```python
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
```

- [ ] **Step 7: Run all four backend SSE shape tests**

```bash
cd backend && python -m pytest tests/chat/test_streaming_service_sse_shape.py -v
```
Expected: all 4 PASS.

- [ ] **Step 8: Run full backend test suite**

```bash
cd backend && python -m pytest -v
```
Expected: all pass (or at most pre-existing failures unrelated to this change).

- [ ] **Step 9: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "fix(stream): accumulate and persist stream_items in message extra"
```

---

## Task 4 — Frontend: optimistic user message via cache (no separate state)

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

The user message is injected directly into `tailQ.data` at the start of the stream using `setQueryData`. It appears in the same `visibleMessages` list as all other messages — no separate render path, no extra state.

A sentinel ID of `-1` marks it as optimistic. The `finally` block filters it out and replaces it with the real messages (Task 6). On error/abort, the `invalidateQueries` fallback replaces the whole cache with real server data, naturally removing the sentinel.

- [ ] **Step 1: Inject optimistic user message into the cache at the start of runStream**

In `runStream`, right after `setStreamThreadItems([])` (before the `let streamReachedTerminal` declaration), add:
```typescript
const _optUserContent = (body.content as string | undefined)?.trim() ?? ''
if (_optUserContent && body.regenerate_after_message_id == null && conversationId != null) {
  qc.setQueryData(
    queryKeys.conversationMessagesTail(conversationId),
    (old: ChatMessage[] | undefined): ChatMessage[] => [
      ...(old ?? []),
      {
        id: -1,
        conversation_id: conversationId,
        role: 'user',
        content: _optUserContent,
        created_at: new Date().toISOString(),
        extra: null,
      },
    ],
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "feat(chat): optimistically inject user message into messages cache at stream start"
```

---

## Task 5 — Frontend: streaming surface post-stream chip visibility + handoff

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 1: Add streamEndedRef near other refs**

After the existing `streamHadSseErrorRef` ref declaration, add:
```typescript
const streamEndedRef = React.useRef(false)
```

- [ ] **Step 2: Set streamEndedRef.current in the finally block**

In the `finally` block (around line 476), right after `setStreaming(false)`:
```typescript
setStreaming(false)
streamEndedRef.current = true
```

- [ ] **Step 3: Add useEffect for handoff from live chips to persisted chips**

After the existing `useEffect` that watches `tailQ.data` (the one at lines ~194–199), add a new `useEffect`:
```typescript
React.useEffect(() => {
  if (streamEndedRef.current && tailQ.data) {
    streamEndedRef.current = false
    setStreamThreadItems([])
    // Optimistic user message (id: -1) was already replaced in tailQ.data
    // by the setQueryData in finally (Task 6) — no extra cleanup needed here.
  }
}, [tailQ.data])
```

- [ ] **Step 4: Change streaming surface render condition**

Find line 917:
```typescript
{streaming && (
```
Change to:
```typescript
{(streaming || streamThreadItems.length > 0) && (
```

- [ ] **Step 5: Gate the header row on streaming inside the block**

Find the header `<div className="mb-1.5 flex items-center justify-between gap-2">` (lines 925–938) that contains the "streaming…" label and Stop button. Wrap it so it only shows during streaming:
```typescript
{streaming && (
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
)}
```

- [ ] **Step 6: Gate "Waiting for tokens…" on streaming**

Find the `streamingText ? ... : streamThreadItems.length === 0 ? <p>Waiting for tokens…</p> : null` ternary (lines 947–958). Change the fallback condition to also require `streaming`:
```typescript
{streamingText ? (
  <MarkdownMessage
    content={streamingText}
    streaming
    className="text-neutral-900 dark:text-neutral-100"
  />
) : streaming && streamThreadItems.length === 0 ? (
  <p className="flex items-center gap-2 text-sm text-neutral-400">
    <span className="inline-block h-3.5 w-0.5 animate-pulse rounded-full bg-neutral-400 dark:bg-neutral-500" />
    Waiting for tokens…
  </p>
) : null}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "fix(chat): keep tool chips visible after stream ends; hand off to PersistedStreamItems"
```

---

## Task 6 — Frontend: capture message_id from done event + optimistic cache update (user + assistant)

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 1: Add doneMessageId variable alongside assembled**

In `runStream`, find `let assembled = ''` (line 364). Add below it:
```typescript
let doneMessageId: number | null = null
```

- [ ] **Step 2: Add message_id to the event type annotation**

In the `applyEvents` function, find the `const e = ev as { ... }` type cast. Add `message_id?: number` to it:
```typescript
const e = ev as {
  type?: string
  text?: string
  detail?: string
  message_id?: number
  item?: {
    uid?: string
    kind?: string
    query?: string
    count?: number
    tool?: string
    params?: Record<string, string>
    result_snippet?: string
    sources?: { kb_name: string; chunks_used: number }[]
    status?: string
  }
}
```

- [ ] **Step 3: Capture message_id in the done event handler**

Find:
```typescript
if (e.type === 'done') {
  streamReachedTerminal = true
}
```
Replace with:
```typescript
if (e.type === 'done') {
  streamReachedTerminal = true
  doneMessageId = typeof e.message_id === 'number' ? e.message_id : null
}
```

- [ ] **Step 4: Replace invalidateQueries for messages tail with optimistic setQueryData (user + assistant)**

In the `finally` block, find:
```typescript
void qc.invalidateQueries({
  queryKey: queryKeys.conversationMessagesTail(conversationId),
})
```
Replace with:
```typescript
if (doneMessageId != null && conversationId != null && assembled) {
  const updates: ChatMessage[] = []
  const userContent = (body.content as string | undefined)?.trim() ?? ''
  if (userContent && body.regenerate_after_message_id == null) {
    // Optimistically add the user message so the cache is complete when
    // streamEndedRef clears optimisticUserMessage.
    updates.push({
      id: doneMessageId - 1,  // user message precedes assistant; exact id replaced on next real fetch
      conversation_id: conversationId,
      role: 'user',
      content: userContent,
      created_at: new Date(Date.now() - 1000).toISOString(),
      extra: null,
    })
  }
  updates.push({
    id: doneMessageId,
    conversation_id: conversationId,
    role: 'assistant',
    content: assembled,
    created_at: new Date().toISOString(),
    extra: null,
  })
  qc.setQueryData(
    queryKeys.conversationMessagesTail(conversationId),
    (old: ChatMessage[] | undefined): ChatMessage[] => [
      // Remove the sentinel optimistic entry (id: -1) added at stream start
      ...(old ?? []).filter(m => m.id !== -1),
      ...updates,
    ],
  )
} else if (conversationId != null) {
  // Fallback: couldn't build optimistic state — real fetch replaces sentinel too
  void qc.invalidateQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
}
```

**Important:** The user message gets a synthetic `id` of `doneMessageId - 1` which is a best-effort approximation (postgres auto-increments, so the real user message was created immediately before the assistant message). This temporary entry is replaced the next time the query does a real server fetch (e.g., on page focus or next conversation load).

- [ ] **Step 5: Verify conversations() and conversation(conversationId) invalidations are still present**

The `finally` block should still contain (after our change):
```typescript
void qc.invalidateQueries({ queryKey: queryKeys.conversations() })
void qc.invalidateQueries({ queryKey: queryKeys.conversation(conversationId) })
```
These are lightweight and should stay.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx
git commit -m "fix(chat): capture message_id; optimistic cache update for user + assistant after stream"
```

---

## Task 7 — Frontend: move paperclip button to bottom bar

**Files:**
- Modify: `frontend/src/components/chat/ChatComposerDock.tsx`

- [ ] **Step 1: Update the chips section condition to not require onLocalFilesChosen**

Find the chips wrapper condition (lines 238–241):
```typescript
{(onLocalFilesChosen != null ||
  (pendingServerAttachments != null && pendingServerAttachments.length > 0) ||
  (pendingLocalFileNames != null && pendingLocalFileNames.length > 0)) && (
```
Change to show only when there are actual chips:
```typescript
{((pendingServerAttachments != null && pendingServerAttachments.length > 0) ||
  (pendingLocalFileNames != null && pendingLocalFileNames.length > 0)) && (
```

- [ ] **Step 2: Remove the paperclip button + hidden file input from the chips section**

Inside the `data-testid="chat-composer-attachments"` div, find the block starting with `{onLocalFilesChosen != null && (` (lines 283–308) and remove it entirely. The `attachInputRef` ref and `onLocalFilesChosen` prop remain — we're just moving the JSX.

- [ ] **Step 3: Add a data-testid to the hidden file input for test targeting**

The file input will need a `data-testid` for the attachment E2E test. When moving the file input to the bottom bar, add `data-testid="chat-attach-file-input"` to it.

- [ ] **Step 4: Move hidden file input + paperclip button to the bottom bar**

In the bottom bar's left flex group, find the `</div>` that closes the `relative shrink-0` div wrapping the `+` button and its dropdown (after line 403). Immediately after that closing tag, before the model `<Select>` wrapper `<div className="min-w-0">`, insert:
```typescript
{onLocalFilesChosen != null && (
  <>
    <input
      ref={attachInputRef}
      data-testid="chat-attach-file-input"
      type="file"
      multiple
      className="sr-only"
      accept=".txt,.md,text/plain,text/markdown"
      disabled={Boolean(attachDisabled) || streaming}
      onChange={(e) => {
        const files = Array.from(e.target.files ?? [])
        e.target.value = ''
        if (files.length) onLocalFilesChosen(files)
      }}
    />
    <button
      type="button"
      className="inline-flex size-8 items-center justify-center rounded-lg border border-neutral-200 text-neutral-600 hover:bg-neutral-50 disabled:opacity-40 dark:border-neutral-700 dark:text-neutral-300 dark:hover:bg-neutral-900"
      aria-label="Attach files"
      disabled={Boolean(attachDisabled) || streaming}
      onClick={() => attachInputRef.current?.click()}
    >
      <Paperclip className="size-3.5" strokeWidth={2} />
    </button>
  </>
)}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/chat/ChatComposerDock.tsx
git commit -m "fix(chat): move attachment button from input area to bottom bar on desktop"
```

---

## Task 8 — Update E2E test for attachment button location + run all E2E tests

**Files:**
- Modify: `frontend/e2e/chat/chat-attachments.spec.ts`
- Run: `frontend/e2e/chat/chat-tool-web-search.spec.ts`

- [ ] **Step 1: Update chat-attachments.spec.ts file input selector**

The test currently uses `page.getByTestId('chat-composer-attachments').locator('input[type="file"]')`. After moving the file input to the bottom bar, this selector no longer works.

Update lines 53–54:
```typescript
// Before:
const attachRoot = page.getByTestId('chat-composer-attachments')
await attachRoot.locator('input[type="file"]').setInputFiles({ ... })

// After:
await page.getByTestId('chat-attach-file-input').setInputFiles({ ... })
```

Apply the same selector change to all three tests in the file that use `attachRoot.locator('input[type="file"]')`:
- Test `'after attach, first messages/stream POST includes attachment_ids'` (line 53–54)
- Test `'assistant answer reflects unique text inside the attached file'` (line 136)

For the `await expect(attachRoot).toContainText(...)` assertions, the chips are still shown inside `data-testid="chat-composer-attachments"`, so those selectors remain valid.

Updated pattern for each test:
```typescript
await page.getByTestId('chat-attach-file-input').setInputFiles({
  name: 'stream-payload.txt',
  mimeType: 'text/plain',
  buffer: Buffer.from('Stream payload check: file is attached to this turn.'),
})
const attachRoot = page.getByTestId('chat-composer-attachments')
await expect(attachRoot).toContainText('stream-payload.txt', { timeout: 20_000 })
```

- [ ] **Step 2: Start the E2E backend**

```bash
./scripts/e2e-up.sh
```
Verify: `curl http://localhost:8001/health` returns OK.

- [ ] **Step 3: Run chat-tool-web-search E2E spec**

```bash
cd frontend && pnpm test:e2e:filter chat-tool-web-search
```
Expected: both tests PASS (chips show Globe icon, persist after stream, assistant message renders).

- [ ] **Step 4: Run chat-attachments E2E spec**

```bash
cd frontend && pnpm test:e2e:filter chat-attachments
```
Expected: all tests PASS (file input now accessible via `chat-attach-file-input` testid, chips still show in `chat-composer-attachments`).

- [ ] **Step 5: Run full E2E suite**

```bash
cd frontend && pnpm test:e2e
```
Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/e2e/chat/chat-attachments.spec.ts
git commit -m "test(e2e): update attachment file input selector after button move to bottom bar"
```
