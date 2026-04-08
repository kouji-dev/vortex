# Capabilities, Tools & E2E Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the new capabilities/tools registries into the streaming service, remove the deleted `web` and `data_query` capabilities from every layer (backend → frontend), and add E2E tests that verify tool-call UI for `web_search` and `kb_search`.

**Architecture:** Backend files (`capabilities/`, `tools/`) are already created; only `streaming_service.py`, `tool_service.py`, and `router.py` still call the old deleted API. Frontend types and components still reference `web` and `query_structured_data` which must be removed. E2E tests use `page.route()` SSE mocks — no LLM required.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), Playwright (E2E).

---

## File Map

### Backend — modify only

| File | What changes |
|---|---|
| `backend/src/ai_portal/chat/streaming_service.py` | Replace broken `from ai_portal.chat.capabilities import ...` with registry calls; update `_build_system_prompt` signature; pass `max_iter` to `_stream_loop` |
| `backend/src/ai_portal/chat/tool_service.py` | Gut implementation — single delegation to `tool_registry.dispatch()` |
| `backend/src/ai_portal/chat/router.py` | Clean up `get_capability_profile` — return only `reflection` + `research` |

### Frontend — modify only

| File | What changes |
|---|---|
| `frontend/src/lib/chat-types.ts` | Remove `web` from `CapabilityToggles` and `DEFAULT_CAPABILITIES` |
| `frontend/src/hooks/useChatCapabilityProfileQuery.ts` | Remove `web` from `ChatCapabilityProfilePayload` |
| `frontend/src/components/chat/ChatComposerDock.tsx` | Remove `Globe` import, `web` from `CapabilityKey` and `CAPABILITY_MENU`, active caps check, deprecated mode functions |
| `frontend/src/components/chat/ChatComposerDockMobile.tsx` | Remove `Globe` import, `web` from `CAPABILITY_MENU` |
| `frontend/src/components/chat/ConversationThreadPage.tsx` | Remove `web` from `capabilityDescriptions` memo |
| `frontend/src/components/chat/StreamingThinkingBlock.tsx` | Remove `Table2` import and `query_structured_data` switch cases; add `data-testid="chat-tool-card-param"` to param span |

### E2E — create

| File | What it tests |
|---|---|
| `frontend/e2e/chat/chat-tool-web-search.spec.ts` | Test A: web_search tool card UI during stream; Test B: assistant message rendered after stream |
| `frontend/e2e/chat/chat-tool-kb-search.spec.ts` | Test A: kb_search tool card UI during stream; Test B: KB indicator visible on assistant message |

---

## Task 1: Fix streaming_service.py

**Files:**
- Modify: `backend/src/ai_portal/chat/streaming_service.py`

The app is currently broken: `streaming_service.py` imports `build_tool_definitions`, `capability_instructions`, and `kb_tool_system_instruction` from `ai_portal.chat.capabilities`, which was deleted and replaced by the `capabilities/` package. This must be fixed before E2E tests can run.

- [ ] **Step 1: Replace the broken import block (lines 26-30)**

Replace:
```python
from ai_portal.chat.capabilities import (
    build_tool_definitions,
    capability_instructions,
    kb_tool_system_instruction,
)
```
With:
```python
import ai_portal.chat.capabilities.registry as capability_registry
import ai_portal.tools.registry as tool_registry
```

- [ ] **Step 2: Replace the tool definitions + system prompt block (lines 103-116)**

Replace:
```python
    # ── Tool definitions ─────────────────────────────────────────────────────
    kb_ids = repo.get_conversation_kb_ids(db, conv.id)
    cap = conv.settings.capabilities if conv.settings else None
    tools = build_tool_definitions(kb_ids=kb_ids, cap=cap)

    # ── System prompt ────────────────────────────────────────────────────────
    system_content = _build_system_prompt(
        assistant=assistant,
        conv=conv,
        memory_block=memory_block,
        has_kb=bool(kb_ids),
        settings=settings,
    )
    system_content += capability_instructions(conv.settings)
```
With:
```python
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
```

- [ ] **Step 3: Pass max_iter to _stream_loop in the gen() closure (lines 136-151)**

Replace:
```python
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
            manual_memories=manual_memories,
            system_profile=system_profile,
            active_memory_count=active_memory_count,
            kb_ids=kb_ids,
            tail_message_id=_tail_message_id,
        )
```
With:
```python
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
            manual_memories=manual_memories,
            system_profile=system_profile,
            active_memory_count=active_memory_count,
            kb_ids=kb_ids,
            tail_message_id=_tail_message_id,
            max_iter=max_iter,
        )
```

- [ ] **Step 4: Update _build_system_prompt signature (lines 265-284)**

Replace the entire function:
```python
def _build_system_prompt(
    *,
    assistant: Assistant | None,
    conv: ChatConversation,
    memory_block: str,
    has_kb: bool,
    settings: Any,
) -> str:
    """Assemble the system prompt from all static parts (excluding capability instructions)."""
    parts: list[str] = []
    parts.append(
        assistant.system_prompt.strip() if assistant else settings.default_system_prompt.strip()
    )
    if conv.summary:
        parts.append(f"Earlier in this conversation:\n{conv.summary}")
    if memory_block:
        parts.append(memory_block)
    if has_kb:
        parts.append(kb_tool_system_instruction())
    return "\n\n".join(p for p in parts if p)
```
With:
```python
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
```

- [ ] **Step 5: Update _stream_loop to accept max_iter (lines 302-320)**

Replace the function signature and first lines:
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
    manual_memories: list,
    system_profile: Any,
    active_memory_count: int,
    kb_ids: list[int],
    tail_message_id: Any,
) -> Any:
    used_kbs_meta: list[dict] = []
    messages = list(llm_messages)
    max_iterations = settings.rag_max_tool_iterations
```
With:
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
    manual_memories: list,
    system_profile: Any,
    active_memory_count: int,
    kb_ids: list[int],
    tail_message_id: Any,
    max_iter: int,
) -> Any:
    used_kbs_meta: list[dict] = []
    messages = list(llm_messages)
    max_iterations = max_iter
```

- [ ] **Step 6: Verify Python can import the module**

```bash
cd backend
python -c "from ai_portal.chat.streaming_service import stream_message_svc; print('OK')"
```

Expected: `OK` (no ImportError)

- [ ] **Step 7: Commit**

```bash
git add backend/src/ai_portal/chat/streaming_service.py
git commit -m "fix(streaming): wire capability + tool registries, replace broken capabilities import"
```

---

## Task 2: Rewrite tool_service.py

**Files:**
- Modify: `backend/src/ai_portal/chat/tool_service.py`

The current `tool_service.py` still uses the deleted `ToolRegistry` class and duplicates dispatch logic that now lives in `tools/registry.py`.

- [ ] **Step 1: Replace the entire file content**

```python
"""Chat domain — tool dispatch layer.

Handles execution of tool calls emitted by the LLM during streaming.
"""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

import ai_portal.tools.registry as tool_registry


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
    return tool_registry.dispatch(name, args, db=db, kb_ids=kb_ids)
```

- [ ] **Step 2: Verify the module imports cleanly**

```bash
cd backend
python -c "from ai_portal.chat.tool_service import _dispatch_tool_call; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/src/ai_portal/chat/tool_service.py
git commit -m "refactor(tool_service): delegate dispatch entirely to tools/registry"
```

---

## Task 3: Clean up router.py capability-profile endpoint

**Files:**
- Modify: `backend/src/ai_portal/chat/router.py`

The `get_capability_profile` endpoint still constructs `CapabilityProfileRead` with `web`, `web_search`, and `data_query` kwargs (which are no longer fields on the schema).

- [ ] **Step 1: Replace the capability-profile endpoint body**

The current endpoint (lines ~46-73 in router.py):
```python
@router.get("/capability-profile", response_model=CapabilityProfileRead)
def get_capability_profile(
    _user: Annotated[User, Depends(get_current_user)],
) -> CapabilityProfileRead:
    """UI copy for chat capability toggles (Add options menu)."""
    return CapabilityProfileRead(
        reflection=CapabilityProfileEntryRead(
            description=(
                "Note key assumptions and uncertainties before answering; adjust if you spot gaps."
            )
        ),
        research=CapabilityProfileEntryRead(
            description=(
                "Separate known facts from what would need verification; suggest concrete checks "
                "or sources the user could use."
            )
        ),
        web=CapabilityProfileEntryRead(
            description=(
                "No live web search is configured. If the answer depends on current events or "
                "post-training facts, say so and suggest how the user can verify."
            )
        ),
        web_search=CapabilityProfileEntryRead(
            description="Search the web in real time to answer questions about current events or recent information."
        ),
        data_query=CapabilityProfileEntryRead(
            description="Analyse CSV, JSON, or table data you share in the conversation."
        ),
    )
```

Replace with:
```python
@router.get("/capability-profile", response_model=CapabilityProfileRead)
def get_capability_profile(
    _user: Annotated[User, Depends(get_current_user)],
) -> CapabilityProfileRead:
    """UI copy for chat capability toggles (Add options menu)."""
    return CapabilityProfileRead(
        reflection=CapabilityProfileEntryRead(
            description=(
                "Deep thinking mode. The model challenges assumptions, gathers data via web search, "
                "and synthesises a well-reasoned conclusion."
            )
        ),
        research=CapabilityProfileEntryRead(
            description=(
                "Deep web research mode. Breaks the question into sub-questions, searches "
                "systematically, and returns a comprehensive, well-cited synthesis."
            )
        ),
    )
```

- [ ] **Step 2: Verify the endpoint returns correct JSON**

Start the E2E backend first:
```bash
./scripts/e2e-up.sh
```

Then in a separate terminal:
```bash
curl -s http://127.0.0.1:8011/api/chat/capability-profile \
  -H "Authorization: Bearer $(curl -s -X POST http://127.0.0.1:8011/api/auth/dev-token | jq -r .access_token)" \
  | jq .
```

Expected output (keys only `reflection` and `research`):
```json
{
  "reflection": { "description": "Deep thinking mode. ..." },
  "research": { "description": "Deep web research mode. ..." }
}
```

- [ ] **Step 3: Commit**

```bash
git add backend/src/ai_portal/chat/router.py
git commit -m "fix(router): capability-profile returns only reflection + research"
```

---

## Task 4: Update frontend type definitions

**Files:**
- Modify: `frontend/src/lib/chat-types.ts`
- Modify: `frontend/src/hooks/useChatCapabilityProfileQuery.ts`

- [ ] **Step 1: Remove `web` from CapabilityToggles and DEFAULT_CAPABILITIES in chat-types.ts**

In `frontend/src/lib/chat-types.ts`, replace:
```typescript
export type CapabilityToggles = {
  reflection: boolean
  research: boolean
  web: boolean
}
```
With:
```typescript
export type CapabilityToggles = {
  reflection: boolean
  research: boolean
}
```

And replace:
```typescript
export const DEFAULT_CAPABILITIES: CapabilityToggles = {
  reflection: false,
  research: false,
  web: false,
}
```
With:
```typescript
export const DEFAULT_CAPABILITIES: CapabilityToggles = {
  reflection: false,
  research: false,
}
```

- [ ] **Step 2: Remove `web` from ChatCapabilityProfilePayload in useChatCapabilityProfileQuery.ts**

In `frontend/src/hooks/useChatCapabilityProfileQuery.ts`, replace:
```typescript
export type ChatCapabilityProfilePayload = {
  reflection: CapabilityProfileEntry
  research: CapabilityProfileEntry
  web: CapabilityProfileEntry
}
```
With:
```typescript
export type ChatCapabilityProfilePayload = {
  reflection: CapabilityProfileEntry
  research: CapabilityProfileEntry
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend
pnpm tsc --noEmit 2>&1 | head -20
```

Expected: no errors referencing `web` in these types. (There will be errors from the components we haven't fixed yet — that's OK at this stage.)

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/chat-types.ts frontend/src/hooks/useChatCapabilityProfileQuery.ts
git commit -m "fix(types): remove web capability from CapabilityToggles and profile payload"
```

---

## Task 5: Update ChatComposerDock.tsx

**Files:**
- Modify: `frontend/src/components/chat/ChatComposerDock.tsx`

- [ ] **Step 1: Remove Globe from imports (line 1)**

Replace:
```typescript
import { BookOpen, Brain, Globe, Lock, Paperclip, Plus, Send, Settings2, Square, X, type LucideIcon } from 'lucide-react'
```
With:
```typescript
import { BookOpen, Brain, Lock, Paperclip, Plus, Send, Settings2, Square, X, type LucideIcon } from 'lucide-react'
```

- [ ] **Step 2: Update CapabilityKey type (line 27)**

Replace:
```typescript
export type CapabilityKey = 'reflection' | 'research' | 'web'
```
With:
```typescript
export type CapabilityKey = 'reflection' | 'research'
```

- [ ] **Step 3: Remove web entry from CAPABILITY_MENU (lines 29-33)**

Replace:
```typescript
const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
  { key: 'web', label: 'Web stance', Icon: Globe },
]
```
With:
```typescript
const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
]
```

- [ ] **Step 4: Update active caps check (lines 498-512)**

Replace:
```typescript
            {(capabilities.reflection ||
              capabilities.research ||
              capabilities.web) && (
```
With:
```typescript
            {(capabilities.reflection ||
              capabilities.research) && (
```

- [ ] **Step 5: Remove deprecated CapabilityMode type and functions (lines 555-571)**

Remove the entire block at the bottom of the file:
```typescript
/** @deprecated Use individual capability toggles; kept for any external use. */
export type CapabilityMode = 'none' | 'reflection' | 'research' | 'web'

export function capabilityModeFromToggles(c: CapabilityToggles): CapabilityMode {
  if (c.reflection) return 'reflection'
  if (c.research) return 'research'
  if (c.web) return 'web'
  return 'none'
}

export function togglesFromCapabilityMode(m: CapabilityMode): CapabilityToggles {
  return {
    reflection: m === 'reflection',
    research: m === 'research',
    web: m === 'web',
  }
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/chat/ChatComposerDock.tsx
git commit -m "fix(composer): remove web capability from desktop composer dock"
```

---

## Task 6: Update ChatComposerDockMobile.tsx

**Files:**
- Modify: `frontend/src/components/chat/ChatComposerDockMobile.tsx`

- [ ] **Step 1: Remove Globe from imports (line 2)**

Replace:
```typescript
import { ArrowUp, BookOpen, Brain, Check, Globe, Lock, Paperclip, Settings2, SlidersHorizontal, Square, X, type LucideIcon } from 'lucide-react'
```
With:
```typescript
import { ArrowUp, BookOpen, Brain, Check, Lock, Paperclip, Settings2, SlidersHorizontal, Square, X, type LucideIcon } from 'lucide-react'
```

- [ ] **Step 2: Remove web entry from CAPABILITY_MENU (lines 21-25)**

Replace:
```typescript
const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
  { key: 'web', label: 'Web stance', Icon: Globe },
]
```
With:
```typescript
const CAPABILITY_MENU: { key: CapabilityKey; label: string; Icon: LucideIcon }[] = [
  { key: 'reflection', label: 'Reflection', Icon: Brain },
  { key: 'research', label: 'Research', Icon: BookOpen },
]
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatComposerDockMobile.tsx
git commit -m "fix(composer): remove web capability from mobile composer dock"
```

---

## Task 7: Update ConversationThreadPage.tsx and StreamingThinkingBlock.tsx

**Files:**
- Modify: `frontend/src/components/chat/ConversationThreadPage.tsx`
- Modify: `frontend/src/components/chat/StreamingThinkingBlock.tsx`

- [ ] **Step 1: Remove `web` from capabilityDescriptions memo in ConversationThreadPage.tsx**

Find the block around line 128:
```typescript
  const capabilityDescriptions = React.useMemo(
      capProfileQ.data
            reflection: capProfileQ.data.reflection.description,
            research: capProfileQ.data.research.description,
            web: capProfileQ.data.web.description,
```

Replace that useMemo with:
```typescript
  const capabilityDescriptions = React.useMemo(
    () =>
      capProfileQ.data
        ? {
            reflection: capProfileQ.data.reflection.description,
            research: capProfileQ.data.research.description,
          }
        : undefined,
    [capProfileQ.data],
  )
```

- [ ] **Step 2: Remove Table2 import and query_structured_data cases from StreamingThinkingBlock.tsx**

In `frontend/src/components/chat/StreamingThinkingBlock.tsx`, remove `Table2` from the lucide-react import line. The current import line looks like:
```typescript
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Globe,
  Library,
  Loader2,
  Table2,
  Wrench,
} from 'lucide-react'
```

Replace with:
```typescript
import {
  Brain,
  Check,
  ChevronDown,
  ChevronRight,
  Globe,
  Library,
  Loader2,
  Wrench,
} from 'lucide-react'
```

- [ ] **Step 3: Remove query_structured_data case from getToolIcon**

Replace:
```typescript
function getToolIcon(tool: string, isMemory: boolean) {
  if (isMemory) return <Brain className="size-3.5 shrink-0" strokeWidth={2} />
  switch (tool) {
    case 'web_search':
      return <Globe className="size-3.5 shrink-0" strokeWidth={2} />
    case 'search_knowledge_base':
      return <Library className="size-3.5 shrink-0" strokeWidth={2} />
    case 'query_structured_data':
      return <Table2 className="size-3.5 shrink-0" strokeWidth={2} />
    default:
      return <Wrench className="size-3.5 shrink-0" strokeWidth={2} />
  }
}
```
With:
```typescript
function getToolIcon(tool: string, isMemory: boolean) {
  if (isMemory) return <Brain className="size-3.5 shrink-0" strokeWidth={2} />
  switch (tool) {
    case 'web_search':
      return <Globe className="size-3.5 shrink-0" strokeWidth={2} />
    case 'search_knowledge_base':
      return <Library className="size-3.5 shrink-0" strokeWidth={2} />
    default:
      return <Wrench className="size-3.5 shrink-0" strokeWidth={2} />
  }
}
```

- [ ] **Step 4: Remove query_structured_data case from getToolLabel**

Replace:
```typescript
function getToolLabel(tool: string, isMemory: boolean): string {
  if (isMemory) return 'Memory'
  switch (tool) {
    case 'web_search':
      return 'Web Search'
    case 'search_knowledge_base':
      return 'Knowledge Base'
    case 'query_structured_data':
      return 'Data Analysis'
    default:
      return tool
  }
}
```
With:
```typescript
function getToolLabel(tool: string, isMemory: boolean): string {
  if (isMemory) return 'Memory'
  switch (tool) {
    case 'web_search':
      return 'Web Search'
    case 'search_knowledge_base':
      return 'Knowledge Base'
    default:
      return tool
  }
}
```

- [ ] **Step 5: Add data-testid to tool param span**

Find the param span inside the `ToolCard` function (currently has no testid):
```typescript
        {param ? (
          <span className="text-[11px] text-neutral-400 dark:text-neutral-500 truncate">
            {param}
          </span>
        ) : null}
```
Replace with:
```typescript
        {param ? (
          <span
            data-testid="chat-tool-card-param"
            className="text-[11px] text-neutral-400 dark:text-neutral-500 truncate"
          >
            {param}
          </span>
        ) : null}
```

- [ ] **Step 6: Verify TypeScript compiles cleanly**

```bash
cd frontend
pnpm tsc --noEmit 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/chat/ConversationThreadPage.tsx \
        frontend/src/components/chat/StreamingThinkingBlock.tsx
git commit -m "fix(chat-ui): remove web capability refs, drop query_structured_data icon, add param testid"
```

---

## Task 8: E2E tests — web_search tool

**Files:**
- Create: `frontend/e2e/chat/chat-tool-web-search.spec.ts`

These tests mock the SSE stream to emit a `web_search` tool call, then assert the tool card renders correctly.

- [ ] **Step 1: Write the test file**

```typescript
import { test, expect } from '@playwright/test'
import { createOrFindConversation } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const CONV_NAME = 'E2E Web Search Tool'

function buildWebSearchSse(messageId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'thinking' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'web_search', params: { query: 'current oil price' } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'web_search', status: 'done' } }) +
    e({ type: 'item_done', item: { kind: 'thinking' } }) +
    e({ type: 'delta', text: 'Based on web search, oil is $80/barrel.' }) +
    e({ type: 'done', message_id: messageId })
  )
}

test.describe('web_search tool', () => {
  test('Test A — tool card renders during stream', async ({ page }) => {
    const convId = await createOrFindConversation(page, CONV_NAME)
    const messageId = convId * 1000 + 1
    const sseBody = buildWebSearchSse(messageId)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Thinking pill becomes visible once stream ends
    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })

    // Expand the thinking block to see tool cards
    await pill.click()
    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    // Tool card for web_search is present with correct label
    const toolCard = block.getByTestId('chat-tool-card').first()
    await expect(toolCard).toBeVisible()
    await expect(toolCard.getByTestId('chat-tool-card-name')).toHaveText('Web Search')

    // Param span shows the query
    await expect(toolCard.getByTestId('chat-tool-card-param')).toHaveText('current oil price')

    // Status is done (not running)
    await expect(toolCard.getByTestId('chat-tool-card-status')).toHaveText('done')

    // Textarea re-enables after stream completes
    await expect(textarea).toBeEnabled({ timeout: 15_000 })
  })

  test('Test B — assistant message rendered after stream', async ({ page }) => {
    const convId = await createOrFindConversation(page, CONV_NAME)
    const messageId = convId * 1000 + 2
    const sseBody = buildWebSearchSse(messageId)
    let streamCompleted = false

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
      streamCompleted = true
    })

    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET' && streamCompleted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on web search, oil is $80/barrel.',
              created_at: new Date().toISOString(),
              extra: null,
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await page.getByRole('textbox', { name: /message/i }).fill('What is the current oil price?')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to finish
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    // Assistant message with the synthesised content is in the thread
    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on web search, oil is $80/barrel.')
  })
})
```

- [ ] **Step 2: Run Test A only to verify it passes**

```bash
cd frontend
pnpm test:e2e:filter "web_search tool"
```

Expected: 2 tests pass. If either fails, diagnose from the Playwright error message — common causes: wrong `data-testid`, timing issue (increase timeout), or stream not fulfilling correctly.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/chat/chat-tool-web-search.spec.ts
git commit -m "test(e2e): web_search tool card — streaming UI + assistant message"
```

---

## Task 9: E2E tests — kb_search tool

**Files:**
- Create: `frontend/e2e/chat/chat-tool-kb-search.spec.ts`

These tests attach a KB to the conversation via UI, mock the SSE stream to emit a `search_knowledge_base` tool call, then assert the KB tool card and KB indicator render correctly.

- [ ] **Step 1: Write the test file**

```typescript
import { test, expect } from '@playwright/test'
import { createOrFindConversation, createOrFindKb, attachKbToConversationViaUi } from '../support/ui-helpers'

test.describe.configure({ mode: 'serial' })

const CONV_NAME = 'E2E KB Search Tool'
const KB_NAME = 'E2E KB Search Fixture'

function buildKbSearchSse(messageId: number, kbId: number): string {
  const e = (payload: object) => `data: ${JSON.stringify(payload)}\n\n`
  return (
    e({ type: 'item_start', item: { kind: 'thinking' } }) +
    e({ type: 'item_start', item: { kind: 'tool_call', tool: 'search_knowledge_base', params: { query: 'project summary', kb_ids: [kbId] } } }) +
    e({ type: 'item_done', item: { kind: 'tool_call', tool: 'search_knowledge_base', status: 'done' } }) +
    e({ type: 'item_done', item: { kind: 'thinking' } }) +
    e({ type: 'delta', text: 'Based on your documents, the project summary is...' }) +
    e({ type: 'done', message_id: messageId })
  )
}

test.describe('kb_search tool', () => {
  test('Test A — KB tool card renders during stream', async ({ page }) => {
    const kbId = await createOrFindKb(page, KB_NAME)
    const convId = await createOrFindConversation(page, CONV_NAME)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, KB_NAME)

    const messageId = convId * 1000 + 10
    const sseBody = buildKbSearchSse(messageId, kbId)

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
    })

    const textarea = page.getByRole('textbox', { name: /message/i })
    await textarea.fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    // Thinking pill becomes visible once stream ends
    const pill = page.getByTestId('chat-thinking-pill')
    await expect(pill).toBeVisible({ timeout: 15_000 })

    // Expand to see tool cards
    await pill.click()
    const block = page.getByTestId('chat-thinking-block')
    await expect(block).toBeVisible()

    // Tool card for search_knowledge_base
    const toolCard = block.getByTestId('chat-tool-card').first()
    await expect(toolCard).toBeVisible()
    await expect(toolCard.getByTestId('chat-tool-card-name')).toHaveText('Knowledge Base')

    // Param shows query
    await expect(toolCard.getByTestId('chat-tool-card-param')).toHaveText('project summary')

    // Status is done
    await expect(toolCard.getByTestId('chat-tool-card-status')).toHaveText('done')

    // Textarea re-enables
    await expect(textarea).toBeEnabled({ timeout: 15_000 })
  })

  test('Test B — KB indicator on assistant message', async ({ page }) => {
    const kbId = await createOrFindKb(page, KB_NAME)
    const convId = await createOrFindConversation(page, CONV_NAME)
    await page.goto(`/chat/conversations/${convId}`, { waitUntil: 'networkidle' })
    await attachKbToConversationViaUi(page, KB_NAME)

    const messageId = convId * 1000 + 11
    const sseBody = buildKbSearchSse(messageId, kbId)
    let streamCompleted = false

    await page.route(`**/api/chat/conversations/${convId}/messages/stream`, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'text/event-stream',
        body: sseBody,
      })
      streamCompleted = true
    })

    await page.route(`**/api/chat/conversations/${convId}/messages*`, async (route) => {
      if (route.request().method() === 'GET' && streamCompleted) {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify([
            {
              id: messageId,
              conversation_id: convId,
              role: 'assistant',
              content: 'Based on your documents, the project summary is...',
              created_at: new Date().toISOString(),
              extra: {
                used_kbs: [
                  {
                    kb_id: kbId,
                    kb_name: KB_NAME,
                    chunks_used: 2,
                    top_score: 0.85,
                    sections: ['Introduction'],
                  },
                ],
              },
            },
          ]),
        })
      } else {
        await route.continue()
      }
    })

    await page.getByRole('textbox', { name: /message/i }).fill('Summarise the project')
    await page.getByRole('button', { name: /send message/i }).click()

    // Wait for stream to finish
    await expect(page.getByRole('textbox', { name: /message/i })).toBeEnabled({ timeout: 15_000 })

    // Assistant message is present
    const assistantMsg = page.getByTestId('chat-message-assistant').last()
    await expect(assistantMsg).toContainText('Based on your documents')

    // KB indicator trigger is visible on the assistant message
    await expect(assistantMsg.getByTestId('message-kb-indicator-trigger')).toBeVisible()
  })
})
```

- [ ] **Step 2: Run both KB tests**

```bash
cd frontend
pnpm test:e2e:filter "kb_search tool"
```

Expected: 2 tests pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/chat/chat-tool-kb-search.spec.ts
git commit -m "test(e2e): kb_search tool card — streaming UI + KB indicator on message"
```

---

## Task 10: Run full E2E suite

- [ ] **Step 1: Ensure E2E backend is running**

```bash
./scripts/e2e-up.sh
```

- [ ] **Step 2: Run all E2E tests**

```bash
cd frontend
pnpm test:e2e
```

Expected: all tests pass (8 workers, 0 retries as per project config). If any test fails:
- Check the Playwright HTML report: `pnpm test:e2e:ui` to replay
- The new web_search / kb_search tests should pass
- Existing thinking-block tests should still pass
- If `chat-tool-thinking-block.spec.ts` fails, investigate whether the `web` capability removal broke any shared state

- [ ] **Step 3: Final commit if any last fixes were needed**

```bash
git add -p
git commit -m "fix(e2e): address test suite failures after capabilities cleanup"
```

---

## Self-Review

**Spec coverage:**
- ✅ §2.1 — `web`, `data_query` removed from `CapabilityToggles` (Task 4)
- ✅ §2.2 — only `reflection` + `research` in UI (Tasks 5, 6)
- ✅ §2.3/2.4 — capability prompts + multipliers already in `capabilities/` package (pre-done)
- ✅ §2.5 — capability registry already in `capabilities/registry.py` (pre-done); streaming service wired in Task 1
- ✅ §3.1/3.2 — tool modules already in `tools/` package (pre-done)
- ✅ §3.3 — tool registry already done (pre-done)
- ✅ §3.4 — streaming service uses four registry calls after Task 1
- ✅ §4 — schema + all frontend type references updated (Tasks 4–7)
- ✅ §5.1 — capability toggle UI updated (Tasks 5, 6)
- ✅ §5.2 — `query_structured_data` removed from StreamingThinkingBlock (Task 7)
- ✅ §6.1 — web_search E2E (Task 8)
- ✅ §6.2 — kb_search E2E (Task 9)
- ✅ §6.3 — existing thinking-block tests untouched

**Type consistency check:**
- `CapabilityKey` in `ChatComposerDock.tsx` → `'reflection' | 'research'` ✓
- `CapabilityToggles` in `chat-types.ts` → `{ reflection, research }` ✓ (no `web`)
- `ChatCapabilityProfilePayload` → `{ reflection, research }` ✓
- `_dispatch_tool_call` return shape → `{ name, content, _used_kbs }` — matches what `tool_registry.dispatch` returns ✓
- `_build_system_prompt` called with `extra_prompts: list[str]` in Task 1 and defined with that signature ✓
- `_stream_loop` called with `max_iter: int` in Task 1 and defined with that param ✓
