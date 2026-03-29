# RAG KB Discovery & Chat UX Design

**Date:** 2026-03-29
**Status:** Approved
**Scope:** KB attachment UX in chat conversations — discoverability, picker, and AI response grounding indicators

---

## Problem

Knowledge bases can be attached to conversations but the current UI lacks:
1. **Discoverability** — users don't know KBs can be activated in a chat
2. **Selection UX** — no clean way to browse, search, and toggle KBs
3. **Grounding transparency** — AI responses don't indicate whether or which KBs were actually used

---

## Design

### 1. Input bar — `📚 KBs` toolbar button

A `📚 KBs` button sits in the chat input toolbar (right of the text area, left of send).

**States:**
- **No KBs attached:** button label `📚 KBs` in neutral style
- **KBs attached:** button becomes a badge `📚 N KBs active` with a blue tint border

**Hover on the badge** → popover appears (top-right anchored) showing:
- Each active KB: icon, name, doc count, last sync time, green status dot
- Footer hint: "Hover the 📚 icon on AI responses to see which KB was used"

**Click the button** → opens KB picker (see §2)

---

### 2. KB Picker — command palette

Opens as a centered overlay on click of the KBs button.

**Behavior:**
- Search input auto-focused on open
- Type to fuzzy-filter KBs by name
- Arrow keys `↑↓` to navigate list
- `Enter` to toggle attach/detach immediately (no Apply button)
- `Esc` or click outside to close
- Active KBs shown at top with a `● active` indicator and appear first in the list
- Each row: KB icon, name, doc count

**No confirmation step** — toggling is immediate and reflected in the badge count.

---

### 3. AI message — KB usage indicator

A small green `📚` icon appears **inline with** "Claude · HH:MM" (bottom-left of the AI message bubble), **only when retrieval actually ran and contributed chunks** to that response.

- **Icon absent** = pure LLM response (KBs were attached but relevance scores were below threshold or no retrieval ran)
- **Icon present** = at least one KB contributed retrieved chunks to this response

**Hover on the icon** → popover listing every KB used in that response:
- KB icon + name
- Chunks retrieved count
- Top similarity score
- Section names / document references pulled

Popovers are hover-only (no click needed), dismiss on mouse leave.

---

## Backend changes required

### Chat endpoint response
The `/api/chat` response (and streamed message object) must include a `used_kbs` field per assistant message:

```json
{
  "role": "assistant",
  "content": "...",
  "used_kbs": [
    {
      "kb_id": "uuid",
      "kb_name": "HR Policies",
      "chunks_used": 3,
      "top_score": 0.91,
      "sections": ["Remote Work Policy p.14", "Contractor Addendum p.22"]
    }
  ]
}
```

`used_kbs` is an empty array `[]` when no retrieval contributed (pure LLM answer).

### RAG retrieval service
`services/rag.py` already scopes retrieval to conversation-attached KBs. It needs to also return retrieval metadata (chunk count, top score, source section/page) alongside the injected context, so the chat endpoint can include it in the response.

### Message model
`chat_messages` table needs a `used_kbs` JSONB column to persist retrieval metadata per message.

---

## Frontend changes required

### Components to create
- `KbsToolbarButton` — input bar button + active badge
- `KbsActivePopover` — hover popover on the badge (active KBs summary)
- `KbPickerDialog` — command palette overlay (search + toggle)
- `MessageKbIndicator` — green 📚 icon + hover popover on AI messages

### Components to modify
- `ConversationThreadPage` — add `KbsToolbarButton` to input bar
- `ChatMessage` (AI variant) — add `MessageKbIndicator` next to timestamp
- `ConversationKnowledgeBasesPanel` — may be superseded or kept as admin-only view

### State
- Active KBs per conversation already stored via `conversation_knowledge_bases` API
- `used_kbs` returned per message from the API, stored in React Query message cache

---

## Out of scope (this spec)
- Per-KB relevance threshold controls exposed to users
- KB content preview / browsing inside the picker
- Suggesting KBs based on conversation topic
- KB sync status management
