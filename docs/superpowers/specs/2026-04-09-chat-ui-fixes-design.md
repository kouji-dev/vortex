# Chat UI Fixes Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four related chat UI/UX bugs: tool-call chip display after stream ends, unnecessary messages API refetch on stream completion, attachment button location on desktop, and `extra` field always null.

**Architecture:** Changes span `ChatComposerDock.tsx` (attachment button move), `ConversationThreadPage.tsx` (stream completion, refetch suppression), and `streaming_service.py` (uid emission, extra persistence). No new components, no new endpoints.

**Related spec:** `2026-04-09-stream-item-persistence-design.md` — this spec supersedes and absorbs that one. Implement this spec only.

---

## Bug 1 — Tool-call chips stuck as spinners; disappear after stream

**Root cause A — uid never correlated:** Backend emits `item_start` with no `uid`. Frontend assigns `crypto.randomUUID()` at `item_start` time. `item_done` also has no `uid`, so `prev.findIndex(it => it.uid === item.uid)` always returns -1. Items stay as `status: "running"` forever.

**Root cause B — chips inside `{streaming && ...}`:** All chips are rendered inside the streaming surface block gated on `streaming`. When `setStreaming(false)` fires in `finally`, the block unmounts — chips vanish even though `streamThreadItems` state still holds them.

**Root cause C — wrong icon for web_search:** Backend emits `kind: "tool_call"`, `tool: "web_search"`. Frontend maps that to `GenericToolThreadItem` → `<Wrench>` icon. The `<Globe>` icon path fires only for `kind: "web_search"`, which the backend never produces.

### Fix — Backend (`streaming_service.py`, `_stream_loop`)

1. Import `uuid` at the top of the file (already present or add `import uuid`).
2. For each tool call detected in the streaming loop, generate `_tool_item_uid = str(uuid.uuid4())` and include `"uid": _tool_item_uid` in the `item_start` payload. Store the uid in a local variable `_tool_item_uid` alongside `tool_call_buffer`.
3. When emitting `item_done` after tool execution (and at the iteration-cap path), include the same `"uid": _tool_item_uid`.
4. For the memory item: generate a uid once before the memory `item_start` and include it in both the `item_start` and `item_done` for memory.

### Fix — Frontend (`ConversationThreadPage.tsx`)

5. In the `item_start` handler, add two branches **before** the generic `tool_call` branch:
   ```typescript
   if (item.kind === 'tool_call' && item.tool === 'web_search') {
     return [...prev, { uid, kind: 'web_search', query: item.params?.query ?? '', status: 'running' }]
   }
   if (item.kind === 'tool_call' && item.tool === 'kb_search') {
     return [...prev, { uid, kind: 'kb_search', query: item.params?.query ?? '', status: 'running' }]
   }
   ```
6. Change the streaming surface render condition from `{streaming && (...)}` to `{(streaming || streamThreadItems.length > 0) && (...)}`.
7. Inside the block, gate the "streaming…" header / stop button on `{streaming && (...)}`. Gate "Waiting for tokens…" on `{streaming && streamThreadItems.length === 0 && !streamingText}`. Chips and `streamingText` render unconditionally within the block.
8. Add `const streamEndedRef = React.useRef(false)`. Set `streamEndedRef.current = true` in the `finally` block. Add a `useEffect` watching `tailQ.data`:
   ```typescript
   React.useEffect(() => {
     if (streamEndedRef.current && tailQ.data) {
       streamEndedRef.current = false
       setStreamThreadItems([])
     }
   }, [tailQ.data])
   ```
   This hands off from the live stream chips to `PersistedStreamItems` without a flicker.

---

## Bug 2 — Unnecessary messages API refetch after every stream

**Root cause:** The `finally` block calls `qc.invalidateQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })`, which triggers a full messages refetch. The new message is already known from the stream (content in `streamingText`, id in the `done` SSE event).

### Fix — Frontend (`ConversationThreadPage.tsx`)

1. Capture `message_id` from the `done` SSE event:
   ```typescript
   if (e.type === 'done') {
     streamReachedTerminal = true
     doneMessageId = typeof e.message_id === 'number' ? e.message_id : null
   }
   ```
   Declare `let doneMessageId: number | null = null` alongside `let assembled = ''`.

2. In the `finally` block, **replace** `qc.invalidateQueries(conversationMessagesTail)` with an optimistic cache update:
   ```typescript
   if (doneMessageId != null && conversationId != null && assembled) {
     const newMsg: ChatMessage = {
       id: doneMessageId,
       conversation_id: conversationId,
       role: 'assistant',
       content: assembled,
       created_at: new Date().toISOString(),
       extra: null,
     }
     qc.setQueryData(
       queryKeys.conversationMessagesTail(conversationId),
       (old: ChatMessage[] | undefined) => [...(old ?? []), newMsg],
     )
   } else if (conversationId != null) {
     // Fallback: only invalidate if we couldn't build the message optimistically
     void qc.invalidateQueries({ queryKey: queryKeys.conversationMessagesTail(conversationId) })
   }
   ```

3. Keep the `conversations()` and `conversation(conversationId)` invalidations — they update the sidebar title/timestamp and are lightweight.

4. **Note on extra:** The optimistic message has `extra: null`. When the backend later persists `stream_items` (Bug 4 fix), a background refetch will eventually bring the real extra. This is acceptable — the chips are shown from `streamThreadItems` during transition, then from `extra.stream_items` once the query eventually refreshes (e.g. on next page load or focus refetch).

---

## Bug 3 — Attachment button above textarea on desktop; should be in bottom bar

**Current:** The paperclip button and pending attachment chips live in the `p-2 pb-1.5` input container div, above the `<textarea>`. The button is shown whenever `onLocalFilesChosen != null`.

**Target:** Move the paperclip button (the `<input type="file" .../>` + `<button>` pair) into the bottom bar's left flex group, immediately after the `+` (capabilities) button. Pending attachment chips stay in the input area above the textarea (they need the space; the bottom bar is too narrow for chips).

### Fix — `ChatComposerDock.tsx`

1. In the `p-2 pb-1.5` input container, keep the pending-chips section (the `div[data-testid="chat-composer-attachments"]`) but remove the paperclip button + hidden file input from it.
2. Move the hidden `<input type="file" .../>` and paperclip `<button>` to the bottom bar, right after the `+` capabilities button (before the model `<Select>`).
3. The `attachInputRef` ref and its click handler move with the button — no logic changes.
4. The chips section condition becomes: show only when `pendingServerAttachments?.length > 0 || pendingLocalFileNames?.length > 0` (drop the `onLocalFilesChosen != null` condition from the chips wrapper, since that was there to always show the button).

---

## Bug 4 — `extra` always null (no stream_items or used_kbs persisted)

**Root cause:** `streaming_service.py` only writes `extra = {"used_kbs": used_kbs_meta} if used_kbs_meta else None`. Stream items are never accumulated or saved.

### Fix — Backend (`streaming_service.py`, `_stream_loop`)

1. Add `stream_items: list[dict] = []` accumulator at the top of `_stream_loop`.
2. When emitting each `item_start` (memory, tool_call), also append the item dict to `stream_items` with `status: "running"`.
3. When emitting each `item_done`, find the matching entry in `stream_items` by uid and update its status to `"done"`, merging any result fields.
4. Skip `kind: "thinking"` — it is a container wrapper, not a card.
5. When persisting the reply:
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

---

## What is NOT changed

- `ThreadItemChip.tsx` — already correct; Globe for `web_search`, Library for `kb_search`, Wrench for generic tool_call
- `PersistedStreamItems` — already correct; reads `extra.stream_items`
- `StreamThreadItem` types in `chat-types.ts` — already correct
- `ChatComposerDockMobile.tsx` — no change; attachment button stays where it is on mobile
- No DB migration — `extra` is an existing `jsonb` nullable column
- No new API endpoints

---

## Testing notes

- After fix, send a message with web_search: chips show Globe icon + spinner → flip to Globe + green check → remain visible after stream → survive page refresh
- After fix, stream completion should NOT fire a GET `/messages` request in devtools network tab (only `conversations` list/detail refresh)
- Attachment button appears in bottom bar next to `+` on desktop; chips still appear above textarea when files are selected
