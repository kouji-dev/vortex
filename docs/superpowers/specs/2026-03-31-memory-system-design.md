# Memory System Design

**Status:** approved
**Date:** 2026-03-31
**Context:** The portal currently has no persistent memory beyond raw conversation history. This spec introduces two memory layers: user profile memories (persistent facts about the user) and conversation context compression (sliding window + summarization). Users can manage their memories manually.

---

## 1. Overview

Two distinct memory types with different lifecycles:

| Type | Scope | Persistence | Purpose |
|---|---|---|---|
| **User profile memory** | Per user, cross-conversation | Permanent until deleted | Facts about the user — preferences, context, role |
| **Conversation memory** | Per conversation | Lives with the conversation | Compressed history of what was discussed |

---

## 2. User Profile Memory

### Data model

New table: `user_memories`

```python
class UserMemory(Base):
    __tablename__ = "user_memories"

    id: int                    # PK
    user_id: int               # FK → users.id (CASCADE DELETE)
    content: str               # The memory text, e.g. "prefers Python over JS"
    source: str                # "auto" (model-extracted) | "manual" (user-created)
    is_active: bool            # True = injected into prompts; False = detached
    created_at: datetime
    updated_at: datetime
```

### Injection into system prompt

When a conversation turn begins, active profile memories are injected as a block:

```
What you know about this user:
- Prefers concise answers
- Works with Python and React
- Is building an enterprise AI portal
```

Injected only when `user_memories` exist and `is_active=True`. The full system prompt order is:

```
[assistant base prompt]
[user profile memories block]
[conversation summary — if exists]
[RAG tool instructions — if KB attached]
```

### Auto-extraction

After every assistant response, a background job runs a cheap extraction call (Haiku or equivalent fast model):

```
Prompt: "Extract any persistent facts about the user from this exchange.
         Return a JSON array of strings, or an empty array if nothing notable.
         Only include facts that would be useful across future conversations.
         Examples: preferences, role, tools they use, constraints they mentioned."

Input: last user message + assistant response
```

If the returned array is non-empty, each fact is saved as a `UserMemory` with `source="auto"` and `is_active=True`. Duplicate detection: skip if a semantically similar memory already exists (simple string similarity check, not embedding-based, for now).

### Manual memory management

Users can:
- **View** all memories (active and inactive) in a memory panel
- **Create** memories manually (free-text input)
- **Edit** any memory
- **Toggle** active/inactive (attach/detach from prompts)
- **Delete** any memory

API endpoints:
```
GET    /users/me/memories
POST   /users/me/memories          { content: string }
PATCH  /users/me/memories/{id}     { content?, is_active? }
DELETE /users/me/memories/{id}
```

---

## 3. Conversation Memory (Sliding Window + Summarization)

### Sliding window

Every conversation turn, only the last `conversation_window_size` messages (default 30) are passed as full messages to the model. Messages outside the window are replaced by a cumulative summary.

```
System prompt:
  [user profile memories]
  [assistant base prompt]
  [conversation summary — if exists]

Messages:
  [last N full messages]
  [current user message]
```

### Summarization triggers

Two triggers (both run as background jobs, never blocking the response):

**Trigger 1 — Window boundary:**
```python
if message_count % conversation_window_size == 0:
    summarize_conversation(conversation_id)
```
Fires at message 30, 60, 90, etc. Summarizes all messages outside the current window into a cumulative summary.

**Trigger 2 — Inactivity gap:**
```python
if last_message_at < now - timedelta(hours=conversation_inactivity_summary_hours):
    summarize_conversation(conversation_id)
```
When the user returns after an inactivity gap, the previous session is summarized regardless of message count.

### Summarization strategy

The summary is **cumulative** — not a chain of summaries. Each time it fires:

1. Fetch existing `summary` (if any) + all messages outside the current window
2. Send to fast model (Haiku or equivalent):
   ```
   Prompt: "Summarize the conversation so far, incorporating any previous summary.
            Be concise. Preserve: key decisions, facts established, user goals,
            unresolved questions. Discard: pleasantries, repetition."
   ```
3. Replace `ChatConversation.summary` with the new summary

This ensures one summary field, not a growing chain.

### Schema changes

`ChatConversation` gains:

```python
summary: str | None           # cumulative conversation summary
last_message_at: datetime     # updated on every message, used for inactivity trigger
```

### New config settings

| Setting | Default | Description |
|---|---|---|
| `conversation_window_size` | 30 | Number of full messages to keep in context |
| `conversation_inactivity_summary_hours` | 1 | Hours of inactivity before session summary |

---

## 4. Background Job Architecture

Both memory operations run as background tasks (same task queue as ingest):

```
workers/
└── memory/
    ├── __init__.py
    ├── extractor.py       # profile memory extraction from exchanges
    └── summarizer.py      # conversation summarization
```

Jobs are fire-and-forget from the API layer:
- After assistant response saved → enqueue `extract_user_memories(user_id, exchange)`
- After message saved → check triggers → enqueue `summarize_conversation(conversation_id)` if triggered

Both workers are lightweight (single LLM call each) and can run on the same worker cluster as ingest.

---

## 5. Frontend Integration

### 5.1 Memory panel (sidebar)

Add a **Memories** entry to `AppSidebar.tsx` (between Chat and Knowledge Bases):

```tsx
<Link to="/memories">
  <BrainIcon />
  {!compact && "Memories"}
</Link>
```

New route: `routes/memories/index.tsx` → `MemoriesPage` component.

**`MemoriesPage` layout:**
```
┌─────────────────────────────────────────┐
│  Memories                    [+ Add]    │
│                                         │
│  ● User prefers Python over JS  [auto] ✕│  ← active (toggle on)
│  ○ Works at Acme Corp          [auto] ✕│  ← inactive (toggle off, dimmed)
│  ● Wants concise answers      [manual] ✕│
│                                         │
│  [conversation window: 30 ──────── ]    │
│  [ ] Disable auto-extraction            │
└─────────────────────────────────────────┘
```

- Each memory row: toggle switch (active/inactive), content text, source badge (`auto` / `manual`), delete button
- Inline edit: click content text to edit in place, press Enter or blur to save (`PATCH`)
- "Add memory" opens a small inline form (text input + confirm)
- Settings at bottom of page: window size slider (10–100), auto-extraction toggle

**React Query hooks:**
```typescript
// lib/queryKeys.ts
memories: () => ['memories']

// hooks/useMemoriesQuery.ts
useMemoriesQuery()           // GET /users/me/memories
useCreateMemoryMutation()    // POST /users/me/memories
useUpdateMemoryMutation()    // PATCH /users/me/memories/{id}
useDeleteMemoryMutation()    // DELETE /users/me/memories/{id}
```

All mutations invalidate `memories` query key on success.

### 5.2 Conversation view — memories indicator

**`ConversationThreadPage.tsx`** — add a small indicator in the chat header when profile memories are active:

```tsx
{activeMemoryCount > 0 && (
  <span title={`${activeMemoryCount} memories active`}>
    <BrainIcon size={14} />
    {activeMemoryCount}
  </span>
)}
```

Clicking the indicator navigates to `/memories` — no inline panel needed (keeps the chat UI clean).

### 5.3 Conversation summarization — transparent to user

No UI change needed for the sliding window / summarization. It's invisible by default. The only visible effect is that very long conversations stay fast and coherent — which is the feature.

Optional future enhancement: a "conversation summary" collapse at the top of the message list showing what was summarized (Phase 3+).

### 5.4 HomePage additions

Add a **Memories** feature card to `HomePage.tsx` alongside Chat and Knowledge Bases:

```tsx
<FeatureCard to="/memories" title="Memories" icon={BrainIcon}
  description="Facts the assistant knows about you, across all conversations." />
```

### Frontend files touched

- `frontend/src/components/layout/AppSidebar.tsx` — Memories nav link
- `frontend/src/routes/memories/index.tsx` — new route + MemoriesPage
- `frontend/src/components/memories/MemoriesPage.tsx` — new component
- `frontend/src/components/chat/ConversationThreadPage.tsx` — memories active indicator
- `frontend/src/components/home/HomePage.tsx` — Memories feature card
- `frontend/src/lib/queryKeys.ts` — memories query key
- `frontend/src/hooks/useMemoriesQuery.ts` — new hook

---

## 6. Implementation order (updated)

```
Phase 1 — Conversation sliding window (backend + transparent):
  - Add summary + last_message_at to ChatConversation (migration)
  - Implement window slicing in conversations.py
  - Background summarizer worker
  - Inactivity + window-boundary triggers

Phase 2 — User profile memories (backend):
  - user_memories table + migration
  - Auto-extraction worker
  - Profile memory injection in system prompt
  - CRUD API endpoints

Phase 3 — Frontend:
  - MemoriesPage + route
  - AppSidebar Memories nav link
  - Memories active indicator in ConversationThreadPage
  - HomePage Memories feature card
  - React Query hooks for memories
  - Settings controls (window size, auto-extraction toggle)
```

---

## 7. Success metrics

| Metric | Target |
|---|---|
| Long conversation token cost | 40–60% reduction vs current (full history) after window kicks in |
| Profile memory recall | User-reported: "it remembered X" — qualitative initially |
| Auto-extraction precision | < 5% false positives (noise memories) — manual review sample |
| Extraction latency impact | < 100ms added to response save path (job is async) |
