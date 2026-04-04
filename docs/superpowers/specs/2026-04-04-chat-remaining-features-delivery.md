# Chat — remaining features (delivery memo)

**Date:** 2026-04-04  
**Status:** delivery outline from product discussion (does not replace the source spec)  
**Branch / worktree:** Implement Step 1 on **`feat/chat-spec-parity`** (repo-local **`.worktrees/chat-spec-parity`**) so parity + E2E hooks stay isolated from `main` until merge.  
**Step 1 matrix:** [2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md)  
**Canonical requirements:** [2026-03-22-chat-conversations-design.md](./2026-03-22-chat-conversations-design.md) (conversations-first chat; note the repo has since shipped assistants, model catalog, and KB/RAG—this memo only covers **what is still open** for chat and the **order** we agreed.)

**Process note (Option B):** For **Step 1**, drive a **checklist** against the chat spec first; add a **short written spec or spec addendum** only when you hit an ambiguous product or security decision (e.g. markdown images, behavior on stream abort). For **Steps 2–4**, expect a **focused mini-spec** when implementation starts (especially **C-04**).

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
| **UI** | `ConversationThreadPage`, `ChatComposerDock`, `MarkdownMessage`, sidebar/shell: align streaming presentation, errors/retry, accessibility (focus, semantics, mobile), and **clarity** of model selection (default vs one-shot send) with whatever you lock in the matrix. |
| **Validation criteria** | (1) **Traceability matrix** maintained in [../checklists/2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md) — each row **met / partial / gap / deferred** with owner; no silent **gap**. (2) **Playwright E2E** on the **isolated E2E DB** (see [§ End-to-end testing](#end-to-end-testing-playwright)): at minimum `chat-parity.spec.ts` (no LLM) green; extend with `E2E_CHAT_ENABLED=1` for flows marked **met** that need a real stream. (3) **Explicit decisions** where spec and code disagree (incremental markdown vs plain-then-parse; **markdown images**; per-send model vs persist). (4) **Task board:** ticket or deferral text for every non-**met** row (sync via task-manager MCP in `/loop`). |

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
| [2026-04-04-chat-spec-parity-matrix.md](../checklists/2026-04-04-chat-spec-parity-matrix.md) | Step 1 traceability + exit criteria |

---

## Maintenance

Update this memo when **delivery order** or **exit criteria** change after another planning pass.
