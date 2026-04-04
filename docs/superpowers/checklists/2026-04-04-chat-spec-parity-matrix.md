# Chat spec parity matrix (Step 1)

**Date:** 2026-04-04  
**Worktree / branch:** `feat/chat-spec-parity` — develop in **`.worktrees/chat-spec-parity`** until merge to `main`.  
**Source spec:** [2026-03-22-chat-conversations-design.md](../specs/2026-03-22-chat-conversations-design.md)  
**Delivery memo:** [2026-04-04-chat-remaining-features-delivery.md](../specs/2026-04-04-chat-remaining-features-delivery.md)  
**Rule:** Each row is **met** (implemented + validated), **partial**, **gap**, or **deferred** with an owner. **Exit:** no silent **gap** — ticket on task board or explicit deferral note in this file.

**Validation legend**

- **E2E (harness):** Playwright under `frontend/e2e/` against **isolated E2E Postgres** (`./scripts/e2e-up.sh`, Compose project **`local-e2e`**, see [frontend/e2e/README.md](../../../frontend/e2e/README.md)).
- **E2E (LLM):** same harness but `E2E_CHAT_ENABLED=1` (real model calls).
- **Manual:** ad hoc checklist.
- **TBD:** product/security decision still open — see [Open decisions](../specs/2026-03-22-chat-conversations-design.md#open-decisions).

---

## Routing & IA

| Requirement                          | Status  | Owner  | Validation                                                                                                                                                       |
| ------------------------------------ | ------- | ------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Base path `/chat`                    | met     | UI     | E2E navigates `/chat/conversations`                                                                                                                              |
| Conversation list + New conversation | met     | UI     | `conversations-sidebar.spec.ts` / navigation tests                                                                                                               |
| Deep link `/chat/conversations/:id`  | met     | UI+API | conversation tests + reload                                                                                                                                      |
| Empty state + starters + CTA         | partial | UI     | **E2E:** `chat-parity.spec.ts` (starters block when API returns sections). **Gap:** collapsible starters when thread has messages (spec optional) — **deferred** |

---

## Main chat surface

| Requirement                                    | Status      | Owner  | Validation                                                                                                                                                                                              |
| ---------------------------------------------- | ----------- | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Message list roles distinct                    | met         | UI     | `chat-send.spec.ts` (E2E_CHAT_ENABLED)                                                                                                                                                                  |
| Streaming state + finalize                     | met         | UI     | `chat-send.spec.ts` Stop / send                                                                                                                                                                         |
| SSE incremental text                           | met         | BE+UI  | stream implementation; E2E with LLM                                                                                                                                                                     |
| Markdown while streaming: plain vs incremental | **partial** | UI     | **Shipped:** incremental `MarkdownMessage` during stream. **TBD:** align spec to implementation *or* switch to plain-then-parse — [Open decisions §5](../specs/2026-03-22-chat-conversations-design.md) |
| Composer multiline + Send                      | met         | UI     | placeholder + send tests                                                                                                                                                                                |
| Send disabled during stream unless stop        | met         | UI     | Stop visible; `chat-send.spec.ts`                                                                                                                                                                       |
| Load older / pagination                        | **partial** | UI+API | **UI:** `data-testid="chat-load-older"` when `canLoadOlder`. **Validation:** **deferred** full E2E (needs ≥100 messages or test-only limit) — manual / future seed helper                               |

---

## Markdown, code, copy

| Requirement            | Status    | Owner | Validation                                                                                                                                 |
| ---------------------- | --------- | ----- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| GFM markdown assistant | met       | UI    | manual / visual                                                                                                                              |
| Sanitize + safe links  | met       | UI    | `rehype-sanitize` in `MarkdownMessage`                                                                                                       |
| Fenced code + Shiki    | met       | UI    | manual                                                                                                                                       |
| Copy code block        | met       | UI    | component-level; E2E optional                                                                                                                |
| Copy message           | met       | UI    | `chat-send.spec.ts` (E2E_CHAT_ENABLED)                                                                                                      |
| Images in markdown     | **deferred** | Doc+UI | **No silent gap:** product choice tracked under [Open decisions](../specs/2026-03-22-chat-conversations-design.md). **Current behavior:** images stripped / not rendered via sanitize pipeline — document in spec addendum when decided (allow remote vs proxy vs strip). |

---

## Controls

| Requirement                          | Status      | Owner  | Validation                                                    |
| ------------------------------------ | ----------- | ------ | ------------------------------------------------------------- |
| Model per conversation + PATCH       | met         | UI+API | `chat-send.spec.ts` selector + persist                        |
| Per-send model override              | **partial** | UI+API | Body supports `model`; **TBD** UX clarity vs “always persist” |
| Capabilities reflection/research/web | **partial** | BE+UI  | Toggles + PATCH; **Step 2** defines real vs stub **done**     |
| Attachments                          | **deferred** | —      | **Step 3** (C-04) — ticket on board when scoped; not a silent gap |

---

## Syllabus

| Requirement                            | Status       | Owner | Validation                       |
| -------------------------------------- | ------------ | ----- | -------------------------------- |
| `GET /api/chat/starters`               | met          | BE    | API exists                       |
| Starters fill composer (not auto-send) | met          | UI    | copy in `EmptyConversationState` |
| Doc links                              | met          | UI    | `StartersPanel` links            |
| In-thread collapsible starters         | **deferred** | UI    | **Step 4**                       |

---

## Shell, a11y, engineering

| Requirement                       | Status  | Owner | Validation                                             |
| --------------------------------- | ------- | ----- | ------------------------------------------------------ |
| Responsive sidebar                | partial | UI    | manual breakpoints                                     |
| Loading / errors / draft retained | partial | UI    | inline errors exist; **gap:** full retry matrix — **deferred** dedicated pass |
| TanStack Router/Query             | met     | UI    | architecture                                           |
| a11y (focus, semantics, contrast) | partial | UI    | **deferred** dedicated audit checklist                 |
| Terminology “Conversation”        | met     | UI    | copy review                                            |

---

## Spec drift (document only)

The chat spec still says **assistants deferred** and `/api/chat` naming; the repo ships **assistants**, **KB/RAG**, and uses `**/api/chat/conversations`**. Treat those sections of the 2026-03-22 doc as **historical** unless refreshed in a spec edit.

---

## Next actions (ordered)

1. ~~Close silent **gaps** in this matrix~~ — markdown images and C-04 attachments reframed as **deferred** with owner/path (above).
2. Add long-thread E2E **or** lower `MESSAGES_LIMIT` in E2E-only build — only if product agrees.
3. Decide markdown images + streaming markdown policy → one-line spec addendum in `2026-03-22-chat-conversations-design.md`.
4. **Task board:** create/link tickets for **Step 2–4** when task-manager MCP is available (`list_tickets` / `create_ticket`).
5. Proceed to **Step 2** on [delivery memo](../specs/2026-04-04-chat-remaining-features-delivery.md).

---

## Ralph /loop note

Sync tickets via **task-manager** MCP (`list_scopes` → `list_epics` → `list_tickets`); if MCP is down, start `.cursor/skills/task-manager/scripts/epic-ticket-server` (`npm start`) per [ralph-delivery-loop](../../../.cursor/rules/ralph-delivery-loop.mdc). This branch should use **one worktree** (`.worktrees/chat-spec-parity`) until Step 1 exit criteria are met, then merge.
