# Chat — conversations-first requirements & design notes

**Status:** spec-draft  
**Date:** 2026-03-22  
**Scope:** Chat vertical (**backend API + frontend UX**). **Assistants are explicitly out of scope for this iteration** (revisit later for system prompt source, RAG binding, catalog, ACL). **Identity / login** is a prerequisite — see [Auth — Microsoft Entra](./2026-03-22-auth-entra-design.md) and [Frontend requirements](#frontend-requirements).

---

## Product intent

Deliver an **OpenAI-style chat** experience:

- **Many conversations** per user (not a single thread).
- **Streaming** assistant responses (token/stream events to the client).
- **Toggleable capabilities** on sends (or equivalent UX): **reflection**, **research**, **web** — backend interprets these as routing / allowed tools / prompt modes (exact implementation can evolve; stubs acceptable until integrations exist).
- **Attachments** on messages (upload, persist, pass into the model path per policy — v1 may limit file types and processing depth).
- **Configurable model** — user chooses which model to use (**per conversation default**, optional **per-send override**).
- **Syllabus / index** — curated **starter questions** and/or **links to docs** so users can jump to useful prompts or resources (exact mix **TBD**: starter prompts only, doc links only, or both).
- **Rich replies** — **Markdown** rendering for assistant messages, with **syntax-highlighted fenced code blocks** for **any common language** the highlighter supports (from ` ```lang ` info string); **copy-friendly** UX (per-block and whole-message copy).
- **Terminology:** use **conversation** everywhere (UI, API, docs). Do **not** use “session” for this concept.

---

## Domain model (target)

| Concept | Notes |
|--------|--------|
| **Conversation** | User-owned chat container: title, timestamps, optional settings (defaults for model, capability toggles). |
| **Message** | Belongs to a conversation; `role` + text `content`; **`extra` (JSON)** for attachment refs, per-message overrides, future tool traces. |
| **Assistant** | **Deferred.** Schema may keep `assistant_id` **nullable** on conversations later so assistants plug in without renaming again. |

### Database naming (migration from current state)

Today (Alembic `003_chat`): `chat_sessions` + `chat_messages.session_id`.

**Target naming:**

- Table **`chat_conversations`** (replaces `chat_sessions`).
- **`ChatConversation`** model.
- Messages reference **`conversation_id`** (rename from `session_id` for clarity).

Ship via **new Alembic revision** (rename table/columns/FKs/indexes). Do **not** rewrite applied migrations in place if environments already ran `003`.

---

## API shape (illustrative)

Prefix: **`/api/chat`** (router stays chat-scoped; resources are **conversations**).

- `GET /api/chat/conversations` — list current user’s conversations.
- `POST /api/chat/conversations` — create (optional initial title/model).
- `GET/PATCH/DELETE /api/chat/conversations/{id}` — detail, rename, delete.
- `GET /api/chat/conversations/{id}/messages` — paginated history.
- `POST /api/chat/conversations/{id}/messages/stream` — append user message, stream assistant output (**SSE** recommended: events such as `delta`, `done`, `error`), persist assistant message on completion.

**Starters / syllabus (read-only):**

- e.g. `GET /api/chat/starters` — static JSON in repo for v1, or DB-backed later.

---

## Frontend requirements

**Prerequisite:** Chat UI lives behind **authenticated access** ([Entra auth spec](./2026-03-22-auth-entra-design.md), **MVP-1**). The app must have **protected routes**, an **API client** that sends **`Authorization: Bearer <access_token>`** (Entra API scope) or the **dev** token in local `auth_mode=dev`, and **401/403 handling** (redirect to sign-in or inline error). Do not implement chat as a public/anonymous surface.

### Routing & information architecture

| Area | Requirement |
|------|-------------|
| **Base path** | Authenticated app area, e.g. `/app/chat` or `/chat` (project convention TBD), not mixed with marketing routes. |
| **Conversation list** | **Sidebar or drawer** listing the user’s conversations (title + updated time); **New conversation** action; select loads that thread in the main pane. |
| **Deep link** | **Optional v1:** `/chat/{conversationId}` (or equivalent) so a conversation is bookmarkable and refresh-safe; must validate ownership (404 if not yours). |
| **Empty state** | When there are no conversations (or none selected), show **syllabus / starters** and a clear **“New conversation”** CTA. |

### Main chat surface

| Area | Requirement |
|------|-------------|
| **Message list** | Scrollable thread: **user** vs **assistant** (and **system** if ever shown) visually distinct; assistant bubbles render via **[Markdown, code & copy](#markdown-code--copy)**. |
| **Streaming** | Consume **SSE** (or agreed stream protocol): append **incremental assistant text** as events arrive; show a **distinct “streaming” state** (cursor/spinner); on **`done`**, finalize the bubble and clear streaming state; on **`error`**, show a **recoverable error** (retry send or reload thread). **Markdown:** while streaming, either render as **plain text** until `done` then run full markdown+highlight pass (**recommended v1**), or use a **debounced** incremental parse (optional if UX requires live formatting). |
| **Composer** | Multiline input; **Send** (keyboard shortcut e.g. Enter vs Shift+Enter documented in UI or help). Disable send while a stream is in progress unless **stop** is implemented (stop is **optional v1**). |
| **History load** | **Pagination or “load older”** for long threads (aligned with `GET .../messages` contract); initial load shows the most recent messages. |

### Markdown, code & copy

| Area | Requirement |
|------|-------------|
| **Markdown** | Render **GitHub-flavored** (or strict commonmark + GFM tables) for assistant messages: **headings, lists, blockquotes, tables, links, inline code**, horizontal rules as appropriate. **Images:** policy **TBD** (allow remote URLs vs block vs proxy). |
| **Security** | **Sanitize** output: **no raw HTML** from model unless passed through a strict allowlist; **safe link** handling (`rel="noopener noreferrer"` for external URLs; optional warn on `javascript:`). Prefer a pipeline (**markdown → AST → sanitize → render**) used consistently in the app. |
| **Code fences** | Support **fenced code blocks** with an optional **language tag** (e.g. ` ```ts ` …); **syntax highlight** via a maintained highlighter (**Shiki** or **Prism** recommended) with **light/dark**-aware theme. **Unknown or missing language:** monospace block, highlight as plain `text`. |
| **Copy — code block** | Each fence has an explicit **“Copy”** control (button) that copies **only that block’s raw text**; **keyboard-accessible** and screen-reader labeled (e.g. “Copy code”). |
| **Copy — message** | **Optional v1 / recommended:** **“Copy message”** (or copy assistant reply) copies **markdown source** as stored/displayed so users can paste into an editor. |
| **Copy — user clipboard** | **Composer** supports **paste** of plain text and multi-line code (no rich paste required v1). |
| **Layout** | Long lines: **horizontal scroll** inside code blocks (default) or **wrap** toggle (optional); preserve **indentation** and avoid breaking strings awkwardly. |
| **Line numbers** | **Optional** (nice for long snippets); not required v1. |

### Controls (product parity with backend)

| Control | Requirement |
|---------|-------------|
| **Model** | **Selector** for default model **per conversation** (persisted via PATCH or create); **optional** override in the composer **per send** if the API supports it — show current model clearly. |
| **Capabilities** | **Toggles or chips** for **reflection**, **research**, **web** (labels match backend flags). State sent **with each message** (or last-known toggles visible). Disabled/stub state if backend returns “not configured.” |
| **Attachments** | **File picker**; show **pending uploads** (name, size) and **errors** (type/size); after send, show **attachment affordance** on the user message (icon/link). Exact preview (image thumb vs generic file) **v1 TBD** per attachment policy. |

### Syllabus / index (UX)

| Area | Requirement |
|------|-------------|
| **Data** | Load from **`GET /api/chat/starters`** (or static fallback bundled for offline dev). |
| **Starter prompts** | Clicking a starter **fills or sends** the composer (product choice: insert text vs auto-send — pick one and document). |
| **Doc links** | If spec includes URLs, render as **external links** (target=`_blank`, `rel` appropriate). |
| **Placement** | **Empty state** + **optional collapsible panel** when the thread has messages so users can still browse suggestions. |

### Shell, quality, and engineering

| Topic | Requirement |
|-------|-------------|
| **Layout** | **Responsive:** sidebar collapses to overlay on small viewports; composer remains usable on mobile. |
| **Loading / errors** | Skeletons or spinners for list and messages; **inline errors** for failed sends or stream failures; do not lose the user’s draft on transient failure. |
| **Stack alignment** | Use existing app patterns: **TanStack Router** for routes, **TanStack Query** for server state (conversations list, messages, starters), shared **API base URL** and auth headers from auth slice. |
| **Accessibility** | Focus management when opening/closing sidebar; **semantic** lists for messages; sufficient **contrast** for bubbles; keyboard path to send (where reasonable). |
| **Terminology (UI copy)** | User-facing strings use **“Conversation”** / **“New conversation”**, not “session.” |

### Out of scope (frontend) for this spec iteration

- **Assistant catalog** UI and **picker** inside chat (deferred with assistants).
- **Voice input**, **plugins marketplace**, and **custom themes** (unless explicitly added later).

---

## Architecture preference

- **Server-authoritative** threads and message history (multi-device, auditable).
- **Streaming:** **SSE** for model token stream first; WebSockets only if/when true duplex tooling requires it.
- **Capabilities** (reflection / research / web): treat as **request-time flags** the orchestration layer respects (prompt routing + tool allowlist); may be **stubbed** until each capability has a real backend.

---

## Explicitly deferred

- **Assistant** catalog, CRUD, entitlements, versioning, and **RAG binding to assistant** — separate brainstorm/spec after Chat v1 shape is stable.
- Full **RAG** retrieval design — separate pass (after or parallel to chat contract, but not blocking conversation CRUD + streaming shell).

---

## Open decisions

1. **Syllabus:** starter prompts only vs doc links vs **both** (user preference not finalized).
2. **Attachments v1:** allowed MIME types, max size, image-only vs PDF text extract, storage backend (local vs blob).
3. **Default behavior** when `assistant_id` is null: global configurable **system prompt** and **no RAG** until assistant phase.
4. **Markdown images** in assistant replies: allow `![]()` remote URLs, strip, or proxy (security + privacy).
5. **Streaming vs markdown:** confirm **plain text until `done`** vs debounced incremental render (see [Main chat surface](#main-chat-surface)).

---

## Related codebase (current, to replace/evolve)

- Models: `backend/src/ai_portal/models/chat.py` — `ChatSession` / `ChatMessage`.
- API: `backend/src/ai_portal/api/chat.py` — non-streaming `POST /api/chat` with required `assistant_id` and RAG tied to assistant.
- Migration: `backend/alembic/versions/003_chat_tables.py`.

---

## Next step (process)

User approval of this doc → **`writing-plans`** implementation plan for Chat v1 → **vertical slice: backend API + frontend per [Frontend requirements](#frontend-requirements)** after [auth Entra vertical](./2026-03-22-auth-entra-design.md) (or compatible `auth_mode=dev` for early UI work), without expanding assistant scope.
