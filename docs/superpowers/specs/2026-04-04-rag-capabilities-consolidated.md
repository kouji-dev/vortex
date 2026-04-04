# RAG — actionable delivery checklist

**Date:** 2026-04-04  
**Status:** living task list (does not delete source specs; use this for **order**, **backend/UI split**, and **exit checks**)  
**Canonical depth:** [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md), [`2026-03-30-rag-retrieval-quality-improvements.md`](./2026-03-30-rag-retrieval-quality-improvements.md), [`2026-03-31-rag-toolcall-ingest-retrieval-design.md`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md)

**Format:** Same structure as [`2026-04-04-chat-remaining-features-delivery.md`](./2026-04-04-chat-remaining-features-delivery.md): each delivery chunk uses a **Detail** table with **Backend**, **UI**, and **Validation criteria** (functional intent is spelled out so nothing is “obvious from the code” only).

---

## End-to-end testing (Playwright)

Ship user-visible RAG or ingest changes with **Playwright E2E** under `frontend/e2e/`, using the same harness as chat/KB ([`frontend/e2e/README.md`](../../../frontend/e2e/README.md)).

- **Stack:** From the repo root, start the **dedicated E2E environment** with `./scripts/e2e-up.sh` (uses [`docker-compose.e2e.yml`](../../../docker-compose.e2e.yml), Compose project **`local-e2e`**). That brings up an **isolated Postgres** for E2E (**port 5435**, database `ai_portal_e2e`) and the API on **8001**. It does **not** use the everyday **`local-dev`** Compose database on **5434**—Playwright runs must never touch dev data.
- **Run tests:** `cd frontend && pnpm test:e2e` (or `pnpm test:e2e:ui`). Playwright starts Vite on **5174** with `VITE_DEV_API_PROXY_TARGET` → `E2E_API_URL` (default `http://127.0.0.1:8001`).
- **Expectation:** For each delivery step below, add or extend Playwright specs when behavior is **requirement-critical** (upload status, progress, KB attach, RAG tool UI, citations). Prefer stable `data-testid` hooks where selectors would otherwise be brittle.

**Optional API env (document in PR when used):**

| Variable | Effect |
|----------|--------|
| `E2E_ENABLE_RAG_SEED=1` | Enables RAG seed routes for `rag-toolcall.spec.ts` / `chat-rag-indicator.spec.ts` |
| `E2E_CHAT_ENABLED=1` | Run live LLM tests in `chat-send.spec.ts` |
| `E2E_REQUIRE_LIVE_STREAM=1` | Run live streaming tool-indicator test in `rag-toolcall.spec.ts` |
| `E2E_REQUIRE_INGEST_READY=1` | Stricter ingest / file-size tests (needs working embedding key + fixtures) |

---

## Context (already shipped — regression only)

The following are **in the codebase today**; they are **not** the numbered delivery steps below unless you are **fixing regressions** or **closing documented gaps** (e.g. `use_rag` flag). Functionally:

- **Corpus:** User-owned **knowledge bases**; **documents** uploaded into a KB; **conversations** attach one or more KBs so the model may search only that corpus.
- **Ingest (inline):** API triggers **`workers/ingest/worker.py`** on the request path (`asyncio.to_thread`): streaming readers → **Chonkie** chunking → embeddings → **`search_vector`** (BM25) + progress fields **`chunks_done` / `chunks_total`**.
- **Retrieval:** Chat uses **`search_knowledge_base`** tool path — **pgvector** + **BM25** + **RRF** + **Voyage rerank** (cosine fallback) + **similarity threshold**; structured **`used_kbs` / citations** on messages; UI **📚 indicator**, **Sources** chips, **“Searching knowledge bases…”** during tool execution (live stream tests optional).

**Regression:** When you touch these areas, satisfy **§ Global validation (every RAG PR)** at the end of this doc.

---

## Delivery order (strict)

Work in this **sequence** for **new** RAG platform work; do not start a later step until the previous step’s exit criteria are satisfied (or items are explicitly deferred in writing).

| Step | Theme | What (functional) |
|------|--------|-------------------|
| **1** | Queued ingest + worker | User uploads a file and gets a **fast response** while a **separate process** embeds and indexes; failures and retries do not depend on HTTP request lifetime. |
| **2** | Resumable / idempotent ingest | Worker crash or duplicate job does not leave an **ambiguous** mix of old/new chunks; progress and terminal status remain trustworthy. |
| **3** | Spec & registry hygiene | Historical RAG specs and [`README.md`](./README.md) snapshot **say what is actually shipped** so nobody re-builds hybrid search or rerank from scratch. |
| **4** | Ingest & RAG UX polish | **Client-side** max file size (match server), optional **upload progress**, and honest **`use_rag`** behavior (or documented deprecation). |
| **5** | Multi-step (“agentic”) RAG | Optional **`rag_max_tool_iterations` > 1** with stable streaming UX and tests. |
| **6** | Enterprise / science backlog | HyDE, OCR, connectors, shared KB ACL, guardrails on retrieved text — **mini-spec per slice** before coding. |

---

## Step 1 — Queued ingest + worker process

| | Detail |
|---|--------|
| **Backend** | **Functional goal:** decouple “accept upload” from “finish embedding.” Implement a **job queue** (Redis + worker library such as Celery/RQ, or equivalent) so `POST …/documents` (or follow-up enqueue call) sets `Document.status` to **`queued`** (or **`pending`** → **`queued`**) and pushes a message `{ document_id }` (and tenant/user metadata if needed). **Remove or shorten** blocking **`asyncio.to_thread(ingest_document_worker, …)`** on the hot path so the HTTP handler returns quickly. Worker process runs the **existing** `ingest_document_worker` (or thin wrapper): same chunking, embeddings, `search_vector`, progress updates, terminal `ready` / `failed`. Add **config** for broker URL (e.g. reuse `REDIS_URL` from settings). Ensure **idempotency rules** are documented for double-enqueue (tie to Step 2 if deferred). Expose **observable status** on document read/list APIs (`queued`, `ingesting`, etc.) consistent with DB. |
| **UI** | **Functional goal:** user sees that indexing is **asynchronous**—not a hung browser. KB document table shows **`queued`** / **`ingesting`** / **`ready`** / **`failed`** with copy that matches reality (“Queued for indexing”, “Indexing…”). If upload HTTP returns before `ready`, UI must **poll** document list or progress endpoint (existing **`chunks_*`** pattern may apply once `ingesting`). Avoid showing `ready` until server says so. |
| **Validation criteria** | (1) **Pytest:** API returns **before** ingest completes (timing or mock queue); worker test or integration test consumes one job and document ends `ready` or `failed`. (2) **Playwright E2E** on **isolated E2E DB** ([§ End-to-end testing](#end-to-end-testing-playwright)): update or add specs so **`ingest-progress.spec.ts`** (and KB detail flows) accept **`queued`** if surfaced; full `pnpm test:e2e` green. (3) **Compose / scripts:** document or add second process in **`e2e-up.sh`** / **`docker-compose.e2e.yml`** (optional profile) so CI can run API + worker. (4) **Smoke:** worker failure leaves document in **`failed`** with **`ingest_error`** user-visible in list. |

---

## Step 2 — Resumable / idempotent ingest

| | Detail |
|---|--------|
| **Backend** | **Functional goal:** after a partial run (crash, OOM, kill), a **retry** completes correctly without duplicate or orphan chunks. **Choose and document** one strategy: e.g. **full replay** (delete existing chunks for `document_id` then re-ingest) or **deterministic tail** (re-chunk, verify prefix matches `chunks_done`, continue embedding from tail). Implement in **`ingest_document_worker`** (or queue handler): transaction boundaries per batch, clear **`failed`** vs **retryable** states, interaction with **`chunks_done` / `chunks_total`**. Align duplicate job delivery with Step 1 (ignore second enqueue while `processing`, or coalesce). |
| **UI** | **Functional goal:** user trusts the progress bar and final status. Progress **`chunks_done` / `chunks_total`** should **monotone** where possible; if retry resets progress, show a **clear state** (e.g. brief “Retrying indexing…”) so it does not look like data loss. No UI change if behavior is identical to today beyond reliability. |
| **Validation criteria** | (1) **Pytest:** simulate failure mid-ingest (inject exception after N chunks), retry job → final **`ready`**, **correct chunk count**, no duplicate **`chunk_index`** rows for same logical content (per chosen strategy). (2) **Pytest:** duplicate enqueue does not corrupt DB. (3) **Playwright (optional):** long-running ingest with `E2E_REQUIRE_INGEST_READY=1` if you add a fixture file large enough to expose progress. (4) **Written:** strategy paragraph in this file or [`2026-03-31-rag-toolcall-ingest-retrieval-design.md`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md). |

---

## Step 3 — Spec & registry hygiene

| | Detail |
|---|--------|
| **Backend** | N/a (docs only), unless OpenAPI/comments reference wrong behavior—then align **status enums** and error messages with docs. |
| **UI** | N/a. |
| **Validation criteria** | (1) Update **status banner** and “partially implemented” lists in **`2026-03-31-rag-toolcall-ingest-retrieval-design.md`** (hybrid, rerank, tool path, chunking: **shipped**; queue, resume: **open**). (2) Patch **`2026-03-25`** / **`2026-03-30`** stale “as implemented” paragraphs or add a pointer: “see **2026-04-04-rag-capabilities-consolidated**.” (3) Sync **[specs `README.md`](./README.md)** implementation snapshot with Steps 1–2 when they ship. (4) No **silent** contradiction between this checklist and the registry. |

---

## Step 4 — Ingest & RAG UX polish

| | Detail |
|---|--------|
| **Backend** | **Functional goal:** server remains the source of truth for limits. Keep **`kb_max_file_size_mb`** enforcement and **clear error payload** on reject; ensure **`use_rag`** on **`StreamMessageBody`** either **gates** offering **`search_knowledge_base`** tools to the model (**false** = no tool / no retrieval) **or** is **removed/deprecated** with OpenAPI + client cleanup—no “dead” field. |
| **UI** | **Functional goal:** user avoids pointless uploads and understands RAG toggle. **`CreateKnowledgeBaseDialog`** / KB upload flows: **client-side** max size check (same numeric cap as server or fetched from config endpoint if you add one), **actionable error** string. Optional: **HTTP upload progress** (XHR) during multipart. Chat composer: if **`use_rag`** is user-visible, it must match server behavior (on/off/disabled with explanation). |
| **Validation criteria** | (1) **Playwright:** reject oversize file **before** or **after** select with expected copy; un-skip or extend **`ingest-progress.spec.ts`** when `E2E_REQUIRE_INGEST_READY=1` + fixture exists. (2) **Pytest:** `use_rag` contract tests if wired. (3) **Playwright / API test:** `use_rag: false` does not produce tool-based retrieval path if gating implemented. |

---

## Step 5 — Multi-step (“agentic”) RAG

| | Detail |
|---|--------|
| **Backend** | **Functional goal:** model may call **`search_knowledge_base`** more than once in one user turn when product enables it. Raise **`rag_max_tool_iterations`** above **1** with **bounded** loop in **`api/conversations.py`**, stable ordering of tool results, and unchanged persistence shape for **`used_kbs` / citations** (merge or last-wins—document choice). |
| **UI** | **Functional goal:** user sees **non-broken** streaming—either multiple **“Searching knowledge bases…”** phases or a single aggregated “Searching…” state that does not flicker confusingly; no stuck spinner if stream ends with error. |
| **Validation criteria** | (1) **Pytest:** stream loop with **2** synthetic tool calls completes and persists assistant message. (2) **Playwright (optional):** with live LLM + fixture KB, assert multiple search phases or acceptable UX. (3) **Load:** document latency impact when iterations > 1. |

---

## Step 6 — Enterprise / science backlog (deferred slices)

| | Detail |
|---|--------|
| **Backend** | **Per slice:** HyDE/query rewrite, OCR (**R-05**), external connectors (**R-06**), shared KB ACL, guardrails on retrieved text, blob storage—each needs a **mini-spec** (data flow, authz, failure modes) before implementation. |
| **UI** | Match each slice: connector admin, quarantine status, citation deep-links, entitlement-gated KB nav, etc. |
| **Validation criteria** | **Mini-spec + pytest + Playwright** on **E2E stack** for any user-visible slice; no “silent” partial stubs without UX honesty (same rule as chat capabilities memo). |

---

## Regression maintenance — shipped areas (when you change this code)

Use these **Detail** tables when a PR touches the subsystem; they restate **function** so reviewers do not lose context.

### R-M1 — Corpus & KB management

| | Detail |
|---|--------|
| **Backend** | **Function:** Users own KBs; only owner can CRUD KB and documents; **document** rows point at **`knowledge_base_id`** and **`storage_path`**; list/detail APIs return **accurate status** for ingest. Primary modules: **`api/knowledge_bases.py`**, **`models/knowledge_base.py`**, **`models/document.py`**. |
| **UI** | **Function:** **`/knowledge-bases`** list/create/delete; **`/knowledge-bases/:id`** detail, upload, document table, edit name/description. User always knows **which KB** they are in and **which files** are indexed or failed. |
| **Validation criteria** | **Pytest:** `test_knowledge_bases_api` (and related). **Playwright:** `kb.spec.ts`, `kb-list.spec.ts`, `kb-detail.spec.ts`. |

### R-M2 — Conversation ↔ KB binding

| | Detail |
|---|--------|
| **Backend** | **Function:** Thread-scoped **attachment** of KBs; retrieval and tools only consider **attached** KB IDs; **`PUT …/conversations/{id}/knowledge-bases`** replaces the set with authz checks. |
| **UI** | **Function:** **`KbChatPicker`** (and related): search, attach, detach, **Active** state, count badge; persistence after reload. |
| **Validation criteria** | **Playwright:** `chat-kb.spec.ts`, `conversation.spec.ts`. |

### R-M3 — Inline ingest pipeline (until Step 1 ships)

| | Detail |
|---|--------|
| **Backend** | **Function:** Turn bytes on disk into **searchable** chunks: **`workers/ingest/readers.py`** (formats), **`chunking.py`** (Chonkie), **`worker.py`** (batch embed, **`search_vector`**, **`chunks_done/total`**), **`services/embedding.py`**. |
| **UI** | **Function:** After upload, user sees **pending → ingesting → ready/failed**; optional **chunk progress** while ingesting. |
| **Validation criteria** | **Pytest:** `test_ingest_worker.py`, `test_ingest_progress.py`. **Playwright:** `ingest-progress.spec.ts`. |

### R-M4 — Retrieval & grounding in chat

| | Detail |
|---|--------|
| **Backend** | **Function:** Model **chooses** to call **`search_knowledge_base`**; server runs **`search_knowledge_base_tool`** (hybrid + rerank + threshold); results formatted with **source lines**; **`message.extra`** stores **`used_kbs`** and **citations** for UI and audit. |
| **UI** | **Function:** User sees when KB search runs (**searching** indicator); after reply, user can open **📚** popover and **Sources** chips (copy reference). |
| **Validation criteria** | **Pytest:** `test_rag_retrieval.py`, conversation tests with mocks as applicable. **Playwright:** `E2E_ENABLE_RAG_SEED=1` → `rag-toolcall.spec.ts`, `chat-rag-indicator.spec.ts`; optional `E2E_REQUIRE_LIVE_STREAM=1` for live tool indicator. |

---

## Global validation (every RAG PR)

| | Detail |
|---|--------|
| **Backend** | Run from `backend/`: `pytest tests/test_rag_retrieval.py tests/test_ingest_worker.py tests/test_ingest_progress.py tests/test_knowledge_bases_api.py tests/test_conversations_api.py -q` (add any new `test_*rag*`, `test_*kb*`, `test_*ingest*` files you introduce). **Ruff** per repo CI. |
| **UI** | N/a (covered by Playwright). |
| **Validation criteria** | - [ ] **T-B-00:** Pytest bundle passes. - [ ] **T-E-00:** With `./scripts/e2e-up.sh`, `cd frontend && pnpm test:e2e` passes. - [ ] **T-E-01:** If RAG seed routes touched: API with `E2E_ENABLE_RAG_SEED=1`, `rag-toolcall.spec.ts` + `chat-rag-indicator.spec.ts` not skipped and green. - [ ] **T-E-02:** If streaming indicator touched: `E2E_REQUIRE_LIVE_STREAM=1` + LLM key when applicable. - [ ] **T-E-03:** If ingest/size touched: `E2E_REQUIRE_INGEST_READY=1` when embeddings + fixtures available. |

**Existing Playwright specs (map):**

| File | Covers |
|------|--------|
| `e2e/kb.spec.ts` | KB list, create/delete |
| `e2e/kb-list.spec.ts` | KB list behavior |
| `e2e/kb-detail.spec.ts` | KB detail, upload, delete |
| `e2e/ingest-progress.spec.ts` | Status transitions during ingest |
| `e2e/chat-kb.spec.ts` | Attach KB, persistence, multi-KB + LLM |
| `e2e/conversation.spec.ts` | Composer, KB picker |
| `e2e/rag-toolcall.spec.ts` | Seeded tool-call + optional live stream |
| `e2e/chat-rag-indicator.spec.ts` | KB indicator (seed) |
| `e2e/chat-send.spec.ts` | Chat (`E2E_CHAT_ENABLED=1`) |

---

## CI recommendation

- **PR gate:** `ruff`, **pytest** (bundle above), **`pnpm test:e2e`** with API on **8001** and **`local-e2e`** Postgres (**5435**).
- **Optional workflows:** `E2E_ENABLE_RAG_SEED=1`, `E2E_REQUIRE_LIVE_STREAM=1`, `E2E_REQUIRE_INGEST_READY=1` with secrets for LLM/embeddings.

---

## References

| Doc | Use |
|-----|-----|
| [2026-03-31-rag-toolcall-ingest-retrieval-design.md](./2026-03-31-rag-toolcall-ingest-retrieval-design.md) | Tool loop, ingest module, hybrid pipeline diagram |
| [2026-03-25-rag-enterprise-design.md](./2026-03-25-rag-enterprise-design.md) | Product vocabulary, R-01–R-08 |
| [specs README](./README.md) | Registry snapshot |
| [frontend/e2e/README.md](../../../frontend/e2e/README.md) | Playwright, `e2e-up.sh`, env vars |

---

## Maintenance

Update this checklist when **delivery order** or **exit criteria** change after another planning pass; when Step **1–2** ship, move their **Validation criteria** into **Regression maintenance** and trim duplicate prose.
