# Stream Item Persistence & Display Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four related bugs so tool-call chips (web_search, kb_search, memory) show the correct icon, persist as done after the stream ends, and survive page refresh.

**Architecture:** Four targeted fixes across backend SSE emission, backend persistence, and frontend rendering — no new components needed.

**Tech Stack:** Python (streaming_service.py), TypeScript/React (ConversationThreadPage.tsx), existing `ThreadItemChip` and `PersistedStreamItems` components.

---

## Bug Inventory

### Bug 1 — Missing `uid` correlation (root cause of visual bugs)

Backend emits `item_start` with no `uid`. Frontend assigns a random UUID at `item_start` time. `item_done` also has no `uid`. Frontend matches by `item.uid`, finds nothing (`idx === -1`), and returns state unchanged. Chips are permanently stuck as `running` spinners and never flip to `done`.

### Bug 2 — Chips vanish when stream ends

Chips are rendered inside `{streaming && (...)}`. When `setStreaming(false)` fires in the `finally` block, the block unmounts. `streamThreadItems` state still holds the items but nothing renders them.

### Bug 3 — Wrong icon for `web_search`

Backend emits `kind: "tool_call"`, `tool: "web_search"`. Frontend maps that to `GenericToolThreadItem` (kind `"tool_call"`) which renders a `<Wrench>` icon. The `<Globe>` icon path only activates for `kind: "web_search"`, which is never produced by the backend.

### Bug 4 — No persistence after refresh

Backend saves only `used_kbs` to `extra`. Stream items are never written. `PersistedStreamItems` (already in the codebase) reads `extra.stream_items` but finds nothing — all chips are gone on page refresh.

---

## Fix Design

### Backend: `streaming_service.py` — `_stream_loop`

**1. Add uid to each tool-call item_start / item_done pair**

At the point where a tool call is detected in the streaming loop, generate `_tool_item_uid = str(uuid4())`. Include `"uid": _tool_item_uid` in the `item_start` payload and store the uid in a separate variable (not inside `tool_call_buffer` which is passed to the LLM). When emitting `item_done` after tool execution, include the same `"uid": _tool_item_uid`.

For the memory item (emitted before the tool loop), assign a uid the same way.

**2. Accumulate stream_items**

Add `stream_items: list[dict] = []` at the top of `_stream_loop`. On each `item_start` for non-thinking items (tool_call, memory), append the full item dict (uid, kind, tool, params, query, count) with `status: "running"`. On each `item_done`, find the matching entry by uid and update its status to `"done"` and merge any result fields (query updates, result_snippet, sources, etc.).

Skip `kind: "thinking"` — it is a container wrapper, not a card.

**3. Persist to extra**

When calling `db.add(ChatMessage(...))`, build `extra` as:
```python
extra: dict = {}
if used_kbs_meta:
    extra["used_kbs"] = used_kbs_meta
if stream_items:
    extra["stream_items"] = stream_items
db.add(ChatMessage(..., extra=extra or None))
```

### Frontend: `ConversationThreadPage.tsx`

**4. Map specific tool names to specific kinds in item_start handler**

In the `if (e.type === 'item_start')` block, before the generic `kind === 'tool_call'` branch, add:

```typescript
if (item.kind === 'tool_call' && item.tool === 'web_search') {
  return [...prev, { uid, kind: 'web_search', query: item.params?.query ?? '', status: 'running' }]
}
if (item.kind === 'tool_call' && item.tool === 'kb_search') {
  return [...prev, { uid, kind: 'kb_search', query: item.params?.query ?? '', status: 'running' }]
}
```

**5. Keep chips visible after streaming ends**

Change the render condition from `{streaming && (...)}` to `{(streaming || streamThreadItems.length > 0) && (...)}`.

Inside the block, gate the "streaming…" header and stop button on `{streaming && (...)}`. Gate "Waiting for tokens…" on `{streaming && streamThreadItems.length === 0 && !streamingText}`. This way chips remain visible after `streaming` goes false, without the streaming header.

**6. Hand off to PersistedStreamItems, then clear**

Add `const streamEndedRef = React.useRef(false)`. In the `finally` block (after `setStreaming(false)`), set `streamEndedRef.current = true`.

Add a `useEffect` watching `tailQ.data`:
```typescript
React.useEffect(() => {
  if (streamEndedRef.current && tailQ.data) {
    streamEndedRef.current = false
    setStreamThreadItems([])
  }
}, [tailQ.data])
```

When the query refetches after the stream, this clears the live chips. `PersistedStreamItems` on the newly-loaded message takes over (reading from `extra.stream_items`). Seamless handoff with no flicker.

---

## Data Flow (after fixes)

```
Stream starts
  → setStreamThreadItems([])
  → item_start (uid="abc", kind="tool_call", tool="web_search", params={query:"..."})
  → frontend creates WebSearchThreadItem {uid:"abc", kind:"web_search", query:"...", status:"running"}
  → Globe icon + Loader2 spinner shown inside streaming surface

  → item_done (uid="abc", status="done")
  → frontend finds idx by uid="abc", updates status → "done"
  → Globe icon + green Check shown

Stream ends (finally)
  → setStreaming(false)  → streaming surface hides header/stop button but chips remain
  → streamEndedRef.current = true
  → qc.invalidateQueries(...)

Query refetch completes
  → tailQ.data updates with new message (extra.stream_items = [{uid,kind,query,...,status:"done"}])
  → useEffect fires → setStreamThreadItems([]) → live chips cleared
  → PersistedStreamItems renders chips from extra.stream_items ✓

Page refresh
  → tailQ.data loads message with extra.stream_items
  → PersistedStreamItems renders chips identically ✓
```

---

## What is NOT changed

- `ThreadItemChip.tsx` — already correct; Globe icon is already mapped for `kind: "web_search"`, Library for `kb_search`
- `PersistedStreamItems` component — already correct; reads `extra.stream_items`
- `StreamThreadItem` types in `chat-types.ts` — already correct
- No new DB migration needed — `extra` is an existing `jsonb` column
