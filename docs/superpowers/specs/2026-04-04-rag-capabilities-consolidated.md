# RAG — actionable delivery checklist

**Status:** living task list (replaces narrative-only planning for RAG)  
**Date:** 2026-04-04  
**Legacy detail:** [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md), [`2026-03-30-rag-retrieval-quality-improvements.md`](./2026-03-30-rag-retrieval-quality-improvements.md), [`2026-03-31-rag-toolcall-ingest-retrieval-design.md`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md)

This document is the **checklist engineers run against**: implementation boxes, validation boxes (pytest + **Playwright E2E** on the **isolated E2E stack** — not `local-dev`).

---

## 1. E2E environment: `local-e2e` (not `local-dev`)

Playwright tests **must** target the dedicated E2E backend and database. Do **not** point E2E at the default dev API/DB.

| Stack | Compose project | Postgres | API default | Purpose |
|--------|-----------------|----------|-------------|---------|
| **Day-to-day dev** | `local-dev` (`docker-compose.yml`) | `127.0.0.1:5434` | varies | Human development |
| **Playwright E2E** | **`local-e2e`** (`docker-compose.e2e.yml`) | **`127.0.0.1:5435`** / DB `ai_portal_e2e` | **`127.0.0.1:8001`** | Automated UI tests only |

**Start the E2E API (from repo root):**

```bash
./scripts/e2e-up.sh
```

**Run Playwright (separate terminal):**

```bash
cd frontend
pnpm test:e2e          # headless
pnpm test:e2e:ui       # UI mode
```

Playwright (`playwright.config.ts`) starts Vite on **5174** with `VITE_DEV_API_PROXY_TARGET` → **`E2E_API_URL`** (default `http://127.0.0.1:8001`). `global-setup` fails fast if `/health` on that URL is down.

**Reference:** [`frontend/e2e/README.md`](../../../frontend/e2e/README.md)

### E2E env vars (copy-paste awareness)

| Variable | When needed |
|----------|-------------|
| `E2E_API_URL` | Default `http://127.0.0.1:8001` — must match `e2e-up.sh` API |
| `E2E_BASE_URL` | Set only if Vite already running (skip Playwright `webServer`) |
| `E2E_ENABLE_RAG_SEED=1` | On API: enables RAG seed routes for `rag-toolcall.spec.ts` / `chat-rag-indicator.spec.ts` |
| `E2E_CHAT_ENABLED=1` | Run live LLM tests in `chat-send.spec.ts` |
| `E2E_REQUIRE_LIVE_STREAM=1` | Run live streaming tool indicator test in `rag-toolcall.spec.ts` |
| `E2E_REQUIRE_INGEST_READY=1` | Stricter ingest / file-size tests (embedding key + fixtures) |

---

## 2. Backend pytest bundle (all RAG-related PRs)

Run from `backend/` with your normal `DATABASE_URL` for **unit** work, or against E2E DB when debugging ingest:

```bash
cd backend
pytest tests/test_rag_retrieval.py tests/test_ingest_worker.py tests/test_ingest_progress.py tests/test_knowledge_bases_api.py tests/test_conversations_api.py -q
```

- [ ] **T-B-00** — Above command passes locally before merge (expand with any new `test_*rag*` / `test_*kb*` / `test_*ingest*` files you add).

---

## 3. Playwright regression bundle (all RAG-related PRs)

With **`./scripts/e2e-up.sh`** running (API on **8001**, DB **5435**):

```bash
cd frontend
pnpm test:e2e
```

- [ ] **T-E-00** — Full default suite green (includes KB + conversation specs; excludes optional skips).
- [ ] **T-E-01** — If you changed RAG seed / tool UI: start API with `E2E_ENABLE_RAG_SEED=1` and confirm `e2e/rag-toolcall.spec.ts` and `e2e/chat-rag-indicator.spec.ts` are not skipped and pass.
- [ ] **T-E-02** — If you changed live streaming RAG: run with `E2E_REQUIRE_LIVE_STREAM=1` + working LLM key and confirm `rag-toolcall` live test passes.
- [ ] **T-E-03** — If you changed ingest / file limits: run with `E2E_REQUIRE_INGEST_READY=1` when you have embeddings configured and confirm ingest + size tests pass.

**Spec file map (existing):**

| File | Covers (high level) |
|------|---------------------|
| `e2e/kb.spec.ts` | KB list, create/delete |
| `e2e/kb-list.spec.ts` | KB list behavior |
| `e2e/kb-detail.spec.ts` | KB detail, upload, delete |
| `e2e/ingest-progress.spec.ts` | Status transitions during ingest |
| `e2e/chat-kb.spec.ts` | Attach KB, persistence, multi-KB retrieval (LLM) |
| `e2e/conversation.spec.ts` | Composer, KB picker, indicator |
| `e2e/rag-toolcall.spec.ts` | Seeded tool-call + optional live stream indicator |
| `e2e/chat-rag-indicator.spec.ts` | KB indicator on messages (seed) |
| `e2e/chat-send.spec.ts` | Chat flow (`E2E_CHAT_ENABLED=1`) |

---

## 4. Track A — Shipped capabilities (maintenance only)

Complete **§2** and **§3** before merging. Below: per-area acceptance checks when you touch that code.

### A-1 Corpus & KB UI

| Task | Backend / UI | Validation checklist |
|------|----------------|----------------------|
| **A-1.1** KB CRUD & ownership | `api/knowledge_bases.py`, `/knowledge-bases` | - [ ] pytest: `test_knowledge_bases_api` relevant cases<br>- [ ] Playwright: `kb.spec.ts`, `kb-list.spec.ts` |
| **A-1.2** Document upload & list | KB detail route, upload API | - [ ] Playwright: `kb-detail.spec.ts`<br>- [ ] Row reaches `ready` or `failed` (fixture + optional `E2E_REQUIRE_INGEST_READY`) |
| **A-1.3** Attach KB to conversation | `PUT …/knowledge-bases`, picker | - [ ] Playwright: `chat-kb.spec.ts`, `conversation.spec.ts` |

### A-2 Ingest pipeline (current: inline worker)

| Task | Backend / UI | Validation checklist |
|------|----------------|----------------------|
| **A-2.1** Chunking + embeddings + `search_vector` | `workers/ingest/*`, migration `017_*` | - [ ] pytest: `test_ingest_worker.py`, `test_rag_retrieval.py` (BM25 path if covered) |
| **A-2.2** Progress API + UI | progress endpoint, KB detail rows | - [ ] Playwright: `ingest-progress.spec.ts`<br>- [ ] Manual: `chunks_done` / `chunks_total` while `ingesting` |
| **A-2.3** File size limit | `kb_max_file_size_mb` API | - [ ] pytest: API rejects oversize<br>- [ ] Playwright: extend `ingest-progress.spec.ts` or un-skip size test when `E2E_REQUIRE_INGEST_READY=1` + fixture exists |
| **A-2.4** Unsupported file types | `readers.py` | - [ ] pytest or Playwright: upload → `failed` with clear outcome |

### A-3 Retrieval & chat (tool-call RAG)

| Task | Backend / UI | Validation checklist |
|------|----------------|----------------------|
| **A-3.1** `search_knowledge_base` tool + stream | `conversations.py`, `rag.py` | - [ ] pytest: conversation/kb tests that mock RAG where applicable<br>- [ ] Playwright: `E2E_ENABLE_RAG_SEED=1` → `rag-toolcall.spec.ts` |
| **A-3.2** Hybrid + RRF + rerank + threshold | `rag.py` | - [ ] pytest: `test_rag_retrieval.py` (vector, threshold, etc.) |
| **A-3.3** Citations + `MessageKbIndicator` | `rag.py`, indicator component | - [ ] Playwright: `rag-toolcall.spec.ts` popover; `chat-rag-indicator.spec.ts` if enabled<br>- [ ] Sources chips visible when `citations` present |
| **A-3.4** “Searching knowledge bases…” | `ConversationThreadPage` | - [ ] Playwright: `E2E_REQUIRE_LIVE_STREAM=1` path in `rag-toolcall.spec.ts` OR manual stream observation |

### A-4 Known gaps (document or fix)

| Task | Work | Validation checklist |
|------|------|----------------------|
| **A-4.1** `use_rag` on `StreamMessageBody` | Wire to tool gating **or** document unused | - [ ] pytest: contract test for flag behavior<br>- [ ] OpenAPI / client types updated |
| **A-4.2** Client-side max file size | `CreateKnowledgeBaseDialog` (per 03-31 spec) | - [ ] Playwright: reject before upload<br>- [ ] Copy matches server limit |

---

## 5. Track B — Queued ingest + worker process (P0)

**Goal:** HTTP upload returns quickly; a **separate process** drains jobs (Redis or chosen broker); same DB as today.

| Task | Backend | UI | Validation checklist |
|------|---------|-----|----------------------|
| **B-1** Job enqueue from API | Replace blocking `asyncio.to_thread(ingest…)` with enqueue + `queued` status | Show `queued` / `ingesting` in doc list | - [ ] pytest: API returns before ingest completes<br>- [ ] Integration: worker consumes job<br>- [ ] Playwright: `ingest-progress.spec.ts` updated for `queued` state if shown<br>- [ ] **E2E:** `pnpm test:e2e` on `local-e2e` stack still green |
| **B-2** Worker container / script | Dockerfile or `python -m` entrypoint documented | N/a | - [ ] `docker-compose.e2e.yml` or `e2e-up.sh` can start worker (optional profile) OR documented second process<br>- [ ] CI doc updated |
| **B-3** Redis (or broker) wiring | Config `REDIS_URL`, connection health | N/a | - [ ] pytest or smoke: enqueue + dequeue in test env<br>- [ ] No regression: existing `local-dev` redis unused by mistake for E2E DB |

---

## 6. Track C — Resumable / idempotent ingest (P1)

**Goal:** Retry after crash does not corrupt chunk sets; behavior matches chosen strategy (full replay vs tail resume).

| Task | Backend | UI | Validation checklist |
|------|---------|-----|----------------------|
| **C-1** Define strategy | Document: wipe+replay **or** deterministic tail from `chunks_done` | N/a | - [ ] Spec paragraph in this file or 03-31 updated |
| **C-2** Implement resume | Worker + job retry safe | Progress bar consistent | - [ ] pytest: simulate mid-batch failure + retry → `ready`, chunk count correct<br>- [ ] Playwright: optional long-file test with `E2E_REQUIRE_INGEST_READY=1` |
| **C-3** Duplicate job idempotency | Same `document_id` enqueued twice | No double chunks | - [ ] pytest: concurrent / duplicate enqueue |

---

## 7. Track D — Docs & registry hygiene (P2)

| Task | Validation checklist |
|------|----------------------|
| **D-1** Update status banners in `2026-03-31-rag-toolcall-ingest-retrieval-design.md` | - [ ] “Hybrid/rerank shipped” reflected<br>- [ ] Open items = queue + resume + UX gaps |
| **D-2** Update `2026-03-25` / `2026-03-30` stale “as implemented” paragraphs | - [ ] Or pointer: “see consolidated checklist” |
| **D-3** Sync [`README.md`](./README.md) implementation snapshot | - [ ] Matches Tracks A–C |

---

## 8. Track E — Product follow-ups (P3–P5)

| Task | Validation checklist |
|------|----------------------|
| **E-1** Client upload progress (XHR) | - [ ] Playwright: assert progress UI during upload |
| **E-2** `use_rag` semantics (see A-4.1) | - [ ] E2E: send with `use_rag: false` → no tool call path |
| **E-3** `rag_max_tool_iterations` > 1 | - [ ] pytest: multi-tool round trip<br>- [ ] Playwright: multiple “Searching…” or stable loading state |
| **E-4** HyDE / OCR / connectors / ACL | - [ ] Each gets its own spec + pytest + Playwright when scoped |

---

## 9. CI recommendation

- **PR gate:** `ruff`, `pytest` (backend subset in §2), **`pnpm test:e2e`** against API on **8001** (job starts `e2e-up` or compose `local-e2e` + migrations + uvicorn).
- **Optional jobs:** `E2E_ENABLE_RAG_SEED=1`, `E2E_REQUIRE_LIVE_STREAM=1`, `E2E_REQUIRE_INGEST_READY=1` as separate workflows with secrets.

---

## 10. Maintaining this checklist

When a Track B/C task ships:

1. Move its validation rows into **§3** / **§4** as regression items.
2. Add or rename Playwright specs in the tables above.
3. Bump **§1** if ports, compose project name, or env vars change.

Do not delete older RAG specs; link here from their header when they drift.
