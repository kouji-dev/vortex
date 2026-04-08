# Capabilities, Tools & E2E — Design Spec

**Date:** 2026-04-08
**Status:** Approved

---

## 1. Overview

This spec covers three tightly coupled changes:

1. **Capability model redefinition** — two user-facing capabilities (`reflection`, `research`), each owning its own system prompt and tool-iteration multiplier.
2. **Tool architecture** — each tool (`web_search`, `kb_search`) owns its schema, execution, and system prompt. A registry per domain keeps `streaming_service.py` ignorant of individual tools/capabilities.
3. **E2E test coverage** — one spec file per tool, two test cases each (streaming UI + full round-trip).

---

## 2. Capabilities

### 2.1 Removed capabilities

| Capability | Action |
|---|---|
| `web` | Removed — was only a disclaimer with no tool backing |
| `data_query` | Removed entirely — schema, backend, UI |

### 2.2 Retained capabilities (UI-exposed)

Only `reflection` and `research` are shown in the capability toggle UI.

---

### 2.3 `reflection`

**What it is:** Deep thinking mode. The LLM takes a structured position on the question — criticising assumptions, gathering data via `web_search`, and synthesising a conclusion. Inspired by Claude's extended thinking and OpenAI's reasoning mode framing.

**System prompt injected when active:**

> You are in **Reflection mode**. Before answering:
> 1. Identify the key assumptions in the question and challenge them.
> 2. Use `web_search` to gather relevant data, KPIs, and indicators that bear on the question.
> 3. Steelman the strongest opposing view.
> 4. Synthesise the evidence into a clear, well-reasoned conclusion.
> Take a position — do not hedge without basis.

**Iteration multiplier:** `5×` — `max_tool_iterations = base × 5` when reflection is active. Allows the LLM to run multiple search passes before concluding.

---

### 2.4 `research`

**What it is:** Deep web research mode. The LLM acts as a rigorous researcher — decomposing the question into sub-questions, searching systematically, cross-referencing sources, and returning a well-cited synthesis. Inspired by Perplexity's research mode and Claude's research framing.

**System prompt injected when active:**

> You are in **Research mode**. Approach this like a rigorous researcher:
> 1. Break the question into focused sub-questions.
> 2. Use `web_search` actively and repeatedly to gather sources for each sub-question.
> 3. Cross-reference findings — note where sources agree or conflict.
> 4. Return a comprehensive, well-sourced synthesis. Cite sources inline where possible.
> Prioritise accuracy and coverage over brevity.

**Iteration multiplier:** `5×` — same as reflection.

---

### 2.5 Capability registry — `chat/capabilities/registry.py`

```python
get_system_prompts(settings: ConversationSettings | None) -> list[str]
get_max_iterations(settings: ConversationSettings | None, base: int) -> int
```

- `get_system_prompts` returns the prompt strings for all enabled capabilities (empty list if none).
- `get_max_iterations` returns `base * max(multiplier for each active capability)`, or `base` if none active.
- The streaming service calls only these two functions — no imports of individual capability modules.

---

## 3. Tools

### 3.1 `web_search` — always on, hidden from user

**File:** `tools/web_search.py`

| Exported | Description |
|---|---|
| `system_prompt() → str` | Always injected into every conversation's system prompt. Instructs the LLM to use `web_search` for recent events, live data, or facts unreliable from training. Discourages use for general knowledge the model knows well. |
| `schema() → dict` | OpenAI function schema with `query` (required) and `num_results` (optional, default 5, max 10) |
| `execute(query, num_results) → ToolResult` | Wraps `DuckDuckGoProvider` |

**System prompt text:**

> You have access to the `web_search` tool. Use it when the question involves: recent events, current data, live prices or statistics, or facts you cannot reliably answer from training data alone. Do not use it for general knowledge you are confident about.

---

### 3.2 `kb_search` — on when KB IDs present

**File:** `tools/kb_search.py`

| Exported | Description |
|---|---|
| `system_prompt() → str` | Injected only when `kb_ids` is non-empty. Instructs LLM to cite sources as `[Source: filename, section]`. |
| `schema(kb_ids) → dict` | OpenAI function schema with `query`, `kb_ids`, and optional `top_k` |
| `execute(query, kb_ids, top_k, db) → ToolResult` | Wraps the RAG service |

---

### 3.3 Tool registry — `tools/registry.py`

```python
get_system_prompts(kb_ids: list[int]) -> list[str]
get_tool_definitions(kb_ids: list[int]) -> list[dict]
dispatch(tool_name: str, args: dict, db: Session, kb_ids: list[int]) -> ToolResult
```

- `get_system_prompts`: always includes `web_search` prompt; includes `kb_search` prompt only if `kb_ids` non-empty.
- `get_tool_definitions`: same conditional logic for schemas.
- `dispatch`: routes to the correct `execute()` by tool name.

---

### 3.4 Streaming service — final shape

The streaming service assembles context with four registry calls and is otherwise tool/capability-agnostic:

```python
tool_prompts = tool_registry.get_system_prompts(kb_ids)
tools        = tool_registry.get_tool_definitions(kb_ids)
cap_prompts  = capability_registry.get_system_prompts(conv.settings)
max_iter     = capability_registry.get_max_iterations(conv.settings, base=settings.rag_max_tool_iterations)
```

No tool names, no capability names in `streaming_service.py`.

---

## 4. Schema changes

### `CapabilityToggles` (backend schema + frontend types)

**Remove:** `web`, `data_query`
**Keep:** `reflection`, `research`

All references in router, streaming service, frontend hooks, and UI components updated accordingly.

---

## 5. Frontend

### 5.1 Capability toggle UI

Only `reflection` and `research` shown. Both desktop (`ChatComposerDock`) and mobile (`ChatComposerDockMobile`) updated.

`useChatCapabilityProfileQuery` type updated to match.

### 5.2 Tool display (no change)

`StreamingThinkingBlock` already handles `web_search` and `search_knowledge_base` tool cards correctly. The `query_structured_data` entry is removed from the icon/label map.

---

## 6. E2E Tests

### 6.1 `chat-tool-web-search.spec.ts`

**Test A — Streaming UI**
- Create/find a conversation
- Mock `POST .../messages/stream` to emit: `item_start thinking` → `item_start tool_call(web_search, {query})` → `item_done tool_call` → `delta(text)` → `item_done thinking` → `done`
- Assert: thinking pill visible, tool card shows "Web Search" label and query param, card status transitions to done, textarea re-enables

**Test B — Full round-trip**
- Same SSE mock
- Mock `GET .../messages` to return the persisted assistant message after `streamCompleted = true`
- Assert: assistant message rendered in thread with synthesised content

---

### 6.2 `chat-tool-kb-search.spec.ts`

**Test A — Streaming UI**
- Create/find a KB (via `createOrFindKb`), attach it to conversation via UI
- Mock `POST .../messages/stream` to emit: `item_start thinking` → `item_start tool_call(search_knowledge_base, {query, kb_ids})` → `item_done tool_call` → `delta(text)` → `item_done thinking` → `done`
- Assert: tool card shows "Knowledge Base" label and query param, transitions to done

**Test B — Full round-trip**
- Same SSE mock
- Mock `GET .../messages` to return message with `extra.used_kbs` set
- Assert: assistant message rendered, RAG indicator (KB usage pill) visible on the message

---

### 6.3 Existing tests — unchanged

`chat-tool-thinking-block.spec.ts` covers generic thinking block rendering (pill/block toggle, memory pill). Kept as-is — the new specs cover tool-specific flows, not the shell.

---

## 7. File map

### New / replaced files

| File | Action |
|---|---|
| `backend/src/ai_portal/chat/capabilities/reflection.py` | New — prompt + multiplier |
| `backend/src/ai_portal/chat/capabilities/research.py` | New — prompt + multiplier |
| `backend/src/ai_portal/chat/capabilities/registry.py` | New — `get_system_prompts`, `get_max_iterations` |
| `backend/src/ai_portal/tools/web_search.py` | New — schema + execute + prompt |
| `backend/src/ai_portal/tools/kb_search.py` | New — schema + execute + prompt |
| `backend/src/ai_portal/tools/registry.py` | Replace — expose three registry functions |
| `backend/src/ai_portal/chat/capabilities.py` | Delete — replaced by `capabilities/` package |
| `frontend/e2e/chat/chat-tool-web-search.spec.ts` | New |
| `frontend/e2e/chat/chat-tool-kb-search.spec.ts` | New |

### Modified files

| File | Change |
|---|---|
| `backend/src/ai_portal/chat/schemas.py` | Remove `web`, `data_query` from `CapabilityToggles` |
| `backend/src/ai_portal/chat/streaming_service.py` | Use registries; remove direct capability/tool logic |
| `backend/src/ai_portal/chat/tool_service.py` | Delegate dispatch to `tools/registry.py`; remove `data_query` |
| `frontend/src/components/chat/ChatComposerDock.tsx` | Remove `web`, `data_query` from `CAPABILITY_MENU` |
| `frontend/src/components/chat/ChatComposerDockMobile.tsx` | Same |
| `frontend/src/hooks/useChatCapabilityProfileQuery.ts` | Remove `web`, `data_query` from type |
| `frontend/src/components/chat/StreamingThinkingBlock.tsx` | Remove `query_structured_data` icon/label entry |
