# Tool Use Thinking Block — Design Spec

**Date:** 2026-04-06
**Status:** Approved

---

## Overview

Replace the current hardcoded "Searching knowledge bases…" indicator with a unified, collapsible **Thinking block** that renders all context items — tool calls (web search, KB search, data query) and memory injection — as a live thread during streaming. When the stream ends the block auto-collapses into a pill; the user can re-expand it to inspect what was used.

---

## Goals

- Consistent UI for every tool and context source — no hardcoded strings in the frontend
- Live feedback: user sees each item appear as it happens, with running → done status
- Memory visibility: user can see that their saved memories were injected into the conversation
- Clean final state: thinking details are hidden by default after streaming, response is the focus
- Respect existing design system (Tailwind classes, colors, animations, component patterns)

---

## SSE Protocol Changes

Two new event types are added. All existing events (`delta`, `done`, `error`) are **unchanged**.

### New events

```jsonc
// Thinking container opens (emitted at the very start of every stream turn that has any context)
{ "type": "item_start", "item": { "kind": "thinking" } }

// Memory injection — emitted once per turn when memories are injected into the system prompt
{ "type": "item_start", "item": { "kind": "memory", "count": 3 } }
{ "type": "item_done",  "item": { "kind": "memory", "status": "done" } }

// Tool call starts
{ "type": "item_start", "item": { "kind": "tool_call", "tool": "web_search",            "params": { "query": "..." } } }
{ "type": "item_start", "item": { "kind": "tool_call", "tool": "search_knowledge_base", "params": { "query": "..." } } }
{ "type": "item_start", "item": { "kind": "tool_call", "tool": "query_structured_data", "params": { "question": "..." } } }

// Tool call finishes
{ "type": "item_done", "item": { "kind": "tool_call", "tool": "web_search", "status": "done" } }

// Thinking container closes (emitted after last tool result, before first delta)
{ "type": "item_done", "item": { "kind": "thinking" } }
```

### Backward compatibility

- The old bare `{ "type": "tool_call", "name": "..." }` event is **replaced** by `item_start {kind: "tool_call"}`.
- Frontends that don't know `item_start` / `item_done` will simply ignore them — graceful degradation.
- The existing `isSearchingKb` state variable is removed; all tool feedback flows through `streamItems`.

### Full example stream

```
item_start  { kind: "thinking" }
item_start  { kind: "memory", count: 2 }
item_done   { kind: "memory", status: "done" }
item_start  { kind: "tool_call", tool: "search_knowledge_base", params: { query: "average revenue per region" } }
item_done   { kind: "tool_call", tool: "search_knowledge_base", status: "done" }
item_start  { kind: "tool_call", tool: "web_search", params: { query: "North America revenue news 2025" } }
delta       { text: "Based on your data…" }
item_done   { kind: "tool_call", tool: "web_search", status: "done" }
delta       { text: " the top region is North America…" }
item_done   { kind: "thinking" }
done
```

### When to emit the thinking block

The `item_start {kind: "thinking"}` is emitted at the start of a turn **only if** at least one of the following is true:
- Memories (system profile or manual) are active and injected
- At least one tool is enabled (web_search, data_query, KB attached)

If none of these apply (plain text conversation with no tools and no memories), no thinking block is emitted and the stream is just `delta` + `done` as today.

Note: `delta` events can interleave with `item_done` — the frontend handles both independently.

---

## Frontend State Model

### New types (`frontend/src/lib/chat-types.ts`)

```ts
export type ToolCallItem = {
  kind: 'tool_call'
  tool: string
  params: Record<string, string>
  status: 'running' | 'done'
}

export type MemoryItem = {
  kind: 'memory'
  count: number
  status: 'running' | 'done'
}

export type ThinkingChildItem = ToolCallItem | MemoryItem

export type ThinkingItem = {
  kind: 'thinking'
  status: 'running' | 'done'
  children: ThinkingChildItem[]
}

export type StreamItem = ThinkingItem | ThinkingChildItem
```

### State changes in `ConversationThreadPage`

| Old state | New state | Notes |
|---|---|---|
| `isSearchingKb: boolean` | removed | replaced by `streamItems` |
| — | `streamItems: StreamItem[]` | ordered list built from SSE |
| — | `thinkingExpanded: boolean` | user toggle; true while streaming, false after `item_done {thinking}` |

### `applyEvents` changes

```ts
case 'item_start':
  if (e.item.kind === 'thinking') {
    setStreamItems(prev => [...prev, { kind: 'thinking', status: 'running', children: [] }])
    setThinkingExpanded(true)
  } else if (e.item.kind === 'tool_call') {
    setStreamItems(prev => {
      const next = [...prev]
      const thinking = next.findLast(i => i.kind === 'thinking' && i.status === 'running') as ThinkingItem | undefined
      const toolItem: ToolCallItem = { kind: 'tool_call', tool: e.item.tool, params: e.item.params ?? {}, status: 'running' }
      if (thinking) thinking.children.push(toolItem)
      else next.push(toolItem)
      return next
    })
  }
  break

case 'item_done':
  if (e.item.kind === 'thinking') {
    setStreamItems(prev => prev.map(i => i.kind === 'thinking' && i.status === 'running' ? { ...i, status: 'done' } : i))
    setThinkingExpanded(false)   // auto-collapse when thinking ends
  } else if (e.item.kind === 'tool_call') {
    setStreamItems(prev => {
      // mark the most-recent running tool_call for this tool as done
      const next = [...prev]
      for (const item of next) {
        if (item.kind === 'thinking') {
          const tc = [...item.children].reverse().find(c => c.tool === e.item.tool && c.status === 'running')
          if (tc) { tc.status = 'done'; return next }
        }
      }
      return next
    })
  }
  break
```

---

## New Component: `StreamingThinkingBlock`

**File:** `frontend/src/components/chat/StreamingThinkingBlock.tsx`

**Props:**
```ts
interface Props {
  items: StreamItem[]
  expanded: boolean
  onToggle: () => void
}
```

**Behavior:**

- If `items` is empty or has no `thinking` item → renders nothing
- **While `thinking.status === 'running'`** (streaming):
  - Shows open block with `animate-pulse` dot + "Thinking…" header
  - Children: tool cards with running/done status
  - Below the block: response text streams as usual
- **After `thinking.status === 'done'`** (stream ended):
  - `expanded === false` → collapsed pill: `▶ Thinking · N tools used`
  - `expanded === true` → expanded list indented under left border
  - Clicking pill toggles `onToggle()`

**Tool icons by name (Lucide React):**

All icons use `className="size-3.5 shrink-0"` and `strokeWidth={2}`.

| tool / kind | Lucide component | icon color (running) | icon color (done) |
|---|---|---|---|
| `web_search` | `Globe` | `text-blue-500 dark:text-blue-400` | `text-neutral-400 dark:text-neutral-500` |
| `search_knowledge_base` | `Library` | `text-blue-500 dark:text-blue-400` | `text-neutral-400 dark:text-neutral-500` |
| `query_structured_data` | `Table2` | `text-blue-500 dark:text-blue-400` | `text-neutral-400 dark:text-neutral-500` |
| `memory` | `Brain` | `text-blue-500 dark:text-blue-400` | `text-neutral-400 dark:text-neutral-500` |
| unknown | `Wrench` | `text-blue-500 dark:text-blue-400` | `text-neutral-400 dark:text-neutral-500` |

Status indicators inside each tool card:

- **Running:** `<Loader2 className="size-3 animate-spin text-blue-500 dark:text-blue-400" strokeWidth={2} />` + label `"running"` in `text-[11px] text-blue-500 dark:text-blue-400`
- **Done:** `<Check className="size-3 text-green-500" strokeWidth={2.5} />` + label `"done"` in `text-[11px] text-green-500`

Thinking block header chevron (expand/collapse toggle):

- **Open:** `<ChevronDown className="size-3 text-neutral-400 dark:text-neutral-500" strokeWidth={2} />`
- **Closed (pill):** `<ChevronRight className="size-3 text-neutral-400 dark:text-neutral-500" strokeWidth={2} />`

**Design system alignment:**

- Thinking block border: `border border-neutral-200/60 dark:border-neutral-700/50 rounded-xl`
- Thinking block header: `flex items-center gap-1.5 px-3 py-2 text-[11px] font-medium text-neutral-500 dark:text-neutral-400`
- Running header pulse dot: `size-1.5 rounded-full bg-blue-500 dark:bg-blue-400 animate-pulse`
- Tool card layout: `flex items-center gap-2 rounded-lg px-2.5 py-2`
- Tool card (running): `bg-blue-500/5 dark:bg-blue-500/[0.07] border border-blue-500/20`
- Tool card (done): `bg-neutral-100/50 dark:bg-white/[0.03] border border-neutral-200/50 dark:border-white/[0.06]`
- Tool name: `text-[11px] font-medium text-neutral-700 dark:text-neutral-300`
- Tool param (query preview): `text-[11px] text-neutral-400 dark:text-neutral-500 truncate`
- Collapsed pill: `inline-flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400 rounded-full border border-neutral-200 dark:border-neutral-700/60 px-2.5 py-1 cursor-pointer hover:bg-neutral-100 dark:hover:bg-neutral-800/50 transition-colors`
- Expanded post-stream children indent: `border-l border-neutral-200/60 dark:border-neutral-700/50 ml-1.5 pl-3 flex flex-col gap-1.5 mt-1.5`
- All font sizes: `text-xs` / `text-[11px]` consistent with existing message header elements

**data-testid attributes:**

| Element | testid |
|---|---|
| Thinking block container | `chat-thinking-block` |
| Collapsed pill button | `chat-thinking-pill` |
| Individual tool card | `chat-tool-card` |
| Tool name text | `chat-tool-card-name` |
| Tool status text | `chat-tool-card-status` |

---

## Backend Changes

### `backend/src/ai_portal/api/conversations.py`

**`stream_message` — emit `item_start {thinking}` before first tool call:**

In the `gen()` generator, before appending tool schemas to `tools[]`, check if any tool is enabled. If yes, emit `item_start {kind: "thinking"}` at the start of the first iteration that produces a tool call.

Specifically, after `tool_call_buffer` is captured:
1. On the **first** tool call in the loop, yield `_sse({"type": "item_start", "item": {"kind": "thinking"}})` (only once, tracked by a `thinking_started` flag)
2. Yield `_sse({"type": "item_start", "item": {"kind": "tool_call", "tool": name, "params": params}})`
3. After tool dispatch, yield `_sse({"type": "item_done", "item": {"kind": "tool_call", "tool": name, "status": "done"}})`
4. When the loop ends with no more tool calls (final reply), yield `_sse({"type": "item_done", "item": {"kind": "thinking"}})` (only if `thinking_started`)

**Remove:** The old `yield _sse({"type": "tool_call", "name": ...})` line is replaced by the above.

---

## Streaming Message Rendering

The streaming message container in `ConversationThreadPage` renders in this order:

1. `<StreamingThinkingBlock items={streamItems} expanded={thinkingExpanded} onToggle={...} />`
2. Streaming text (unchanged — `streamingText` via `<MarkdownMessage>`)
3. Cursor animation (unchanged)
4. "Waiting for tokens…" fallback if no text yet and no thinking block

The old `{isSearchingKb && <p>Searching knowledge bases…</p>}` block is removed.

---

## E2E Tests

**New file:** `frontend/e2e/chat/chat-tool-thinking-block.spec.ts`

Uses a new backend seed endpoint `POST /e2e/seed-tool-stream` (similar to existing `seed-rag-assistant`) that returns a pre-built SSE response with `item_start`/`item_done` events — no real LLM or DuckDuckGo call needed.

| Test | data-testid / assertion |
|---|---|
| `thinking block appears during streaming` | `chat-thinking-block` visible while stream in progress |
| `thinking block collapses after stream ends` | `chat-thinking-pill` visible, block children hidden after done |
| `user can expand thinking block` | click `chat-thinking-pill` → tool cards visible |
| `user can collapse thinking block` | click again → tool cards hidden |
| `tool card shows tool name` | `chat-tool-card-name` contains "web_search" |
| `tool card shows running then done status` | status transitions during stream |
| `KB tool renders in thinking block` | `chat-tool-card-name` contains "search_knowledge_base" |
| `no thinking block when no tools used` | `chat-thinking-block` absent for plain text reply |

---

## Changed Files Summary

| File | Change |
|---|---|
| `backend/src/ai_portal/api/conversations.py` | Replace `tool_call` SSE event with `item_start`/`item_done` pair; add `thinking` wrapper |
| `frontend/src/lib/chat-types.ts` | Add `ToolCallItem`, `ThinkingItem`, `StreamItem` types |
| `frontend/src/components/chat/ConversationThreadPage.tsx` | Add `streamItems` + `thinkingExpanded` state; update `applyEvents`; remove `isSearchingKb`; render `StreamingThinkingBlock` |
| `frontend/src/components/chat/StreamingThinkingBlock.tsx` | New component |
| `backend/tests/test_builtin_tools_e2e.py` | Update `tool_call` event assertions to expect `item_start` shape |
| `frontend/e2e/chat/chat-tool-thinking-block.spec.ts` | New Playwright E2E tests |
| `backend/src/ai_portal/api/e2e.py` (or equivalent) | New seed endpoint `POST /e2e/seed-tool-stream` |

---

## What Does NOT Change

- `delta`, `done`, `error` SSE events — identical
- Message persistence, DB schema, memory, RAG
- The KB indicator (`MessageKbIndicator`) in persisted messages — unchanged
- Composer, model selector, all other chat UI
