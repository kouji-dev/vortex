# Chat — remaining features (delivery memo)

**Date:** 2026-04-04  
**Status:** Steps 1–4 implemented (2026-04-04): attachments API/UI, capability-profile + honest menu copy, collapsible starters, load-older E2E seed, SSE error banner + retry, stream-failure rollback for retries.  
**Merge:** Landed on **`main`** from **`feat/chat-remaining-features`** (historical worktree: `.worktrees/chat-remaining-features`). Step 1 parity was also tracked on **`feat/chat-spec-parity`** / **`.worktrees/chat-spec-parity`**.  
**Step 1 matrix (checklist):** [2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md)  
**Canonical requirements:** [2026-03-22-chat-conversations-design.md](./2026-03-22-chat-conversations-design.md) (conversations-first chat; note the repo has since shipped assistants, model catalog, and KB/RAG—this memo only covers **what is still open** for chat and the **order** we agreed.)

**Process note (Option B):** For **Step 1**, keep the **checklist matrix** and the **traceability tables** in this file aligned; add a **short spec addendum** only when a row needs an ambiguous product or security decision (e.g. markdown images, stream abort). For **Steps 2–4**, expect a **focused mini-spec** when implementation starts (especially **C-04**).

---

## End-to-end testing (Playwright)

Ship user-visible chat changes with **Playwright E2E** under `frontend/e2e/`, following the existing harness (see [frontend/e2e/README.md](../../../frontend/e2e/README.md) and [2026-03-30-e2e-knowledge-bases-design.md](./2026-03-30-e2e-knowledge-bases-design.md)).

- **Stack:** From the repo root, start the **dedicated E2E environment** with `./scripts/e2e-up.sh` (uses [`docker-compose.e2e.yml`](../../../docker-compose.e2e.yml)). That brings up an **isolated Postgres** for E2E (**port 5435**, database `ai_portal_e2e`) and the API on **8001**. It does **not** use the everyday `local-dev` Compose database on 5434—so Playwright runs never touch dev data.
- **Expectation:** For each delivery step below, add or extend Playwright specs when behavior is **requirement-critical** (streaming, model changes, capabilities, attachments, starters). Prefer stable `data-testid` hooks where selectors would otherwise be brittle.

---

## Context (already shipped, out of scope for this memo)

The following are **not** listed as remaining work here: multi-conversation UX, streaming assistant replies, stop/regenerate, load-older pagination, model catalog + conversation default model, markdown + Shiki + sanitize, copy controls, KB attach in chat, starters API and basic `StartersPanel`, capability **flags** wired to the API (stub behavior). This memo targets **gaps, depth, and polish** relative to the chat spec and the brainstorm above.

---

## Delivery order (strict)

Work in this **sequence**; do not start a later step until the previous step’s exit criteria are satisfied (or items are explicitly deferred in writing).

| Step | Label in discussion | Theme | What |
|------|---------------------|--------|------|
| **1** | “4 — Spec parity” | Close documented gaps vs chat spec | Matrix: spec section → met / partial / gap / deferred; resolve or defer every row; no silent drift |
| **2** | “3 — Capabilities” | Reflection / research / web | Define “done”: real tool or integration vs explicit **disabled** UX and copy; avoid ambiguous half-stubs |
| **3** | “1 — C-04” | Message attachments | User files on **chat messages** (distinct from KB corpus): upload, storage, policy, model context |
| **4** | “2 — Syllabus” | Starters / index | Finalize starter vs doc links, empty vs in-thread placement, insert vs auto-send |

---

## Step 1 — Spec parity sweep

| | Detail |
|---|--------|
| **Backend** | Adjust only where the spec demands server truth: e.g. stream lifecycle / persistence on abort, error payloads, pagination contract edge cases, any `message.extra` conventions you decide when closing gaps. Much of the chat API may already satisfy the spec. |
| **UI** | `ConversationThreadPage`, `ChatComposerDock`, `MarkdownMessage`, sidebar/shell: align streaming presentation, errors/retry, accessibility (focus, semantics, mobile), and **clarity** of model selection (default vs one-shot send) with whatever you lock in the tables below. |
| **Validation criteria** | (1) **Checklist matrix** in [../checklists/2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md) **and** the **traceability tables** below: each row **met / partial / gap / deferred** with owner. (2) **Playwright E2E** on the **isolated E2E DB** (see [§ End-to-end testing](#end-to-end-testing-playwright)) for user-critical flows you mark **met** (stream, send, load older, model change). (3) **Explicit decisions** where spec and code disagree (e.g. incremental markdown while streaming vs “plain until `done`”; markdown **images**; per-send **model** vs persist-on-change). (4) No silent **gap** — ticket or deferral note in-table. |

### Step 1 — traceability tables (living)

**Statuses:** **met** = implemented and validated · **partial** · **gap** · **deferred**  
**Validation:** **E2E** = Playwright on E2E Postgres (`./scripts/e2e-up.sh`) · **E2E chat streams** = `chat-send.spec.ts` / attachment LLM tests use live **Claude Haiku 4.5** (**ANTHROPIC_API_KEY** on API) · **manual** · **TBD** = see [chat spec open decisions](./2026-03-22-chat-conversations-design.md#open-decisions)

### Step 1 — product decisions (locked for this iteration)

| Topic | Decision |
|-------|-----------|
| **Streaming markdown** | **Incremental** GFM in `MarkdownMessage` while tokens arrive (plus sanitize). The 2026-03-22 spec’s “plain text until `done`” is **not** how the app behaves; refresh that spec in a doc PR or treat as superseded here. |
| **Markdown images** | **`![]()` not rendered** — explicit `img → null` in `MarkdownMessage` (defense in depth with `rehype-sanitize`). Enabling images needs a new spec (proxy / allowlist / attachment flow). |
| **Per-send vs default model** | API accepts optional `model` on stream body; UI **persists** catalog selection via PATCH when the user changes the thread model. A dedicated “one-shot model” UX is **deferred** unless requested. |

Playwright’s `webServer` must pass **`VITE_AUTH_MODE=dev`** and **`VITE_DEV_BEARER_TOKEN`** (default `devtoken`) matching the API’s `DEV_BEARER_TOKEN` so E2E auth works (see `playwright.config.ts`).

#### Routing & IA

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| Base path `/chat` | met | UI | E2E → `/chat/conversations` |
| Conversation list + New conversation | met | UI | `shell/conversations-sidebar.spec.ts` / nav tests |
| Deep link `/chat/conversations/:id` | met | UI+API | `chat/conversation.spec.ts` + reload |
| Empty state + starters + CTA | met | UI | E2E `shell/chat-parity.spec.ts`; collapsible in-thread starters (`data-testid="chat-starters-collapsed"`) when thread has messages |

#### Main chat surface

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| Message list roles distinct | met | UI | `chat/chat-send.spec.ts` (E2E+LLM) |
| Streaming state + finalize | met | UI | `chat/chat-send.spec.ts` Stop / send |
| SSE incremental text | met | BE+UI | stream + E2E+LLM |
| Markdown while streaming (plain vs incremental) | met | UI | **Shipped:** incremental `MarkdownMessage` + sanitize. **Spec drift:** update 2026-03-22 doc — see § Step 1 product decisions |
| Composer multiline + Send | met | UI | placeholder + send tests |
| Send disabled during stream unless stop | met | UI | `chat/chat-send.spec.ts` |
| Load older / pagination | met | UI+API | `data-testid="chat-load-older"`; E2E seeds via `POST …/e2e/seed-messages` when `E2E_ENABLE_CHAT_MESSAGES_SEED=1` (`e2e-up.sh`) |

#### Markdown, code, copy

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| GFM assistant markdown | met | UI | manual / visual |
| Sanitize + safe links | met | UI | `rehype-sanitize` |
| Fenced code + Shiki | met | UI | manual |
| Copy code block | met | UI | component; E2E optional |
| Copy message | met | UI | `chat/chat-send.spec.ts` (E2E+LLM) |
| Images in markdown | met | UI | **Not rendered** (`img` omitted); E2E+LLM still validates assistant text paths — see § product decisions |

#### Controls

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| Model per conversation + PATCH | met | UI+API | `chat/chat-send.spec.ts` |
| Per-send model override | met | UI+API | API `model` on send + persisted default via selector; **deferred:** dedicated one-shot-only UX — see § product decisions |
| Capabilities reflection / research / web | partial | BE+UI | `GET /api/chat/capability-profile` + per-toggle descriptions in Add options menu; behavior remains prompt-level (+ honest **web** copy unless `TAVILY_API_KEY`) |
| Attachments | met | BE+UI | `POST …/uploads` (.txt/.md), `attachment_ids` on stream, `message.extra.attachments`; composer + thread UI; pytest + `alembic` `020_chat_uploads` |

#### Syllabus

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| `GET /api/chat/starters` | met | BE | API |
| Starters fill composer (not auto-send) | met | UI | `EmptyConversationState` copy |
| Doc links | met | UI | `StartersPanel` + sample link in `CHAT_STARTERS` |
| In-thread collapsible starters | met | UI | `chat-starters-collapsed` + `shell/chat-parity.spec.ts` |

#### Shell, a11y, engineering

| Requirement | Status | Owner | Validation |
|-------------|--------|-------|------------|
| Responsive sidebar | partial | UI | manual breakpoints |
| Loading / errors / draft retained | partial | UI | SSE `error` → alert + `data-testid="chat-stream-retry"`; failed **new** turns rolled back server-side so same payload (incl. `attachment_ids`) can retry |
| TanStack Router / Query | met | UI | architecture |
| a11y | partial | UI | `aria-live` on streaming bubble; message list `role="log"`; further pass deferred |
| Terminology “Conversation” | met | UI | copy |

#### Spec drift (read-only)

The 2026-03-22 chat spec still mentions **assistants deferred** and naming that predates shipped **assistants**, **KB/RAG**, and **`/api/chat/conversations`**. Treat those passages as **historical** unless the spec is refreshed.

#### Step 1 — next actions

1. **Remaining gaps:** stream **abort** persistence policy, full a11y audit, optional attachment DELETE for unstaged server rows, live Tavily wiring when product wants true **web**.  
2. Refresh **2026-03-22-chat-conversations-design.md** to match streaming + image decisions (or link this memo).

#### Step 1 — verification log (local)

| Check | Command / note |
|-------|------------------|
| Frontend build | `cd frontend && pnpm run build` |
| E2E (no LLM) | `./scripts/e2e-up.sh` (sets `E2E_ENABLE_CHAT_MESSAGES_SEED=1`), then `pnpm exec playwright test e2e/shell/chat-parity.spec.ts` |
| E2E chat (Haiku) | `pnpm exec playwright test e2e/chat/chat-send.spec.ts` (requires **ANTHROPIC_API_KEY** on API; model slug `anthropic-claude-haiku-4-5`) |

---

## Step 2 — Capability depth (reflection, research, web)

| | Detail |
|---|--------|
| **Backend** | `api/conversations.py` (and related services): implement or hard-disable each capability with clear server-side behavior; prompts, tool allowlists, and “not configured” responses should match the UI. |
| **UI** | Composer toggles: show **on / off / unavailable** honestly; help text or disabled state when the backend cannot perform the action. |
| **Validation criteria** | Per capability: **manual** scenario checklist and **Playwright E2E** (isolated E2E DB) when behavior is stable and visible. Contract or API tests for flags → prompt/tool path. **Definition of done** written in one place (this memo or a one-page addendum) so “stub” is not confused with “shipped.” |

---

## Step 3 — C-04: attachments in chat

| | Detail |
|---|--------|
| **Backend** | Upload endpoint(s), storage (local/blob), virus-scan **hooks** if required, size/MIME enforcement, attachment metadata on messages (`extra` or dedicated fields), and rules for **what reaches the model** vs metadata-only. |
| **UI** | File picker, pending upload list, errors, post-send affordance on user messages (icon/link/preview per policy). |
| **Validation criteria** | **Mini-spec before coding** (policy table: types, max size, retention). **Pytest** for API and authz; **Playwright E2E** on the **E2E Postgres** for pick → send → visible attachment → model receives expected context (or expected refusal). Align with future **GR-05** when that exists. |

---

## Step 4 — Syllabus / starters

| | Detail |
|---|--------|
| **Backend** | Adjust `GET …/starters` payload/shape only if product choices require it; otherwise static JSON may be enough. |
| **UI** | `StartersPanel` and empty state: finalize **starter prompts vs external doc links**, **click = fill composer vs auto-send**, and whether a **collapsible starters panel** exists when the thread already has messages (per chat spec § syllabus). |
| **Validation criteria** | Short **UX acceptance** list; **Playwright E2E** on the **E2E stack** if click behavior or routing changes. Content updates (copy/links) tracked separately from code when possible. |

---

## References

| Doc | Use |
|-----|-----|
| [2026-03-22-chat-conversations-design.md](./2026-03-22-chat-conversations-design.md) | Full chat requirements and open decisions |
| [specs README](./README.md) | Registry; **C-04** capability ID |
| [frontend/e2e/README.md](../../../frontend/e2e/README.md) | Playwright + isolated DB ports, `e2e-up.sh`, env vars |
| [2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md) | Step 1 checklist + exit criteria |

---

## Maintenance

Update this memo when **delivery order** or **exit criteria** change after another planning pass.
