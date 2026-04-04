# RAG capabilities — consolidated specification

**Status:** living document (reconciles older RAG specs with the repo)  
**Date:** 2026-04-04  
**Audience:** engineers and PM; use this file when planning RAG work.  
**Supersedes as “index of truth”:** nothing — older specs remain historical detail. **This doc wins** when it disagrees with prose in older files.

---

## 1. Why this document exists

The RAG story was captured across several specs written at different times. Some sections describe **pre-shipping** behavior (fixed-size chunking, `top_k=5` only, no citations). The codebase has **moved on**. Reading only [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md) or [`2026-03-30-rag-retrieval-quality-improvements.md`](./2026-03-30-rag-retrieval-quality-improvements.md) without cross-checking code is misleading.

This document:

- **Resumes** the intent of the legacy specs in one place.
- States **recommended delivery order** for remaining work.
- Gives **backend vs UI** ownership per capability.
- Gives **validation criteria** you can turn into tests or checklists.

### Source specs (read for depth, not for “current” flags)

| Document | Role |
|----------|------|
| [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md) | Product/engineering breadth (R-01–R-08), UX expectations, enterprise backlog. Many “as implemented” paragraphs are **stale**. |
| [`2026-03-30-rag-retrieval-quality-improvements.md`](./2026-03-30-rag-retrieval-quality-improvements.md) | Ordered quality ideas (chunking, rerank, hybrid, HyDE). **Tier 1 narrative is stale** (chunking and retrieval evolved). Still useful for **backlog tiers** (HyDE, compression). |
| [`2026-03-31-rag-toolcall-ingest-retrieval-design.md`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md) | Tool-call RAG, ingest worker layout, hybrid + rerank, frontend behaviors. **Status line is stale** (several items are implemented). Phased plan at doc end is still a good **skeleton**. |
| [`README.md`](./README.md) (implementation snapshot) | High-level shipped vs backlog; keep in sync when RAG milestones move. |

### Suggested reading order (onboarding)

1. **This file** — scope, order, validation.
2. **[`2026-03-31-rag-toolcall-ingest-retrieval-design.md`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md)** — tool loop, ingest module layout, retrieval pipeline diagram.
3. **[`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md)** — product vocabulary and enterprise phases ( skim “as implemented”; trust §1 table below instead).

---

## 2. Implementation snapshot (vs legacy prose)

Use this table when updating older specs or the README snapshot.

| Area | Legacy docs often say | Repo today (high level) |
|------|------------------------|-------------------------|
| Chunking | Fixed 800-char splits | **`workers/ingest/chunking.py`** — Chonkie (semantic / code / fallback), ~512-token target, rich `meta`. |
| Ingest execution | Inline only | **Still inline** from API (`asyncio.to_thread` → `ingest_document_worker`). Worker code is **modular**; **queue + separate process** is not done. |
| Retrieval | Cosine `top_k=5`, inject into system | **Tool path:** `search_knowledge_base_tool` in **`services/rag.py`** — vector + **BM25** + **RRF** + **Voyage rerank** (cosine fallback) + **threshold**; used from **`api/conversations.py`** agent loop. **`retrieve_context_with_meta`** remains for simpler/tests; not the primary chat path. |
| Chat UX | No citations | **`MessageKbIndicator`** shows KB usage + **source chips** (copy to clipboard). Stream shows **“Searching knowledge bases…”** during tool execution. |
| Ingest UX | Async progress TBD | **KB detail** polls **`GET …/documents/{id}/progress`** for `chunks_done` / `chunks_total` while `ingesting`. |
| DB | No tsvector | Migration **`017_ingest_progress_and_tsvector.py`** — `search_vector` on chunks, `chunks_total` / `chunks_done` on documents. |
| `use_rag` request flag | Gates RAG | Field exists on **`StreamMessageBody`**; **not wired** to tool gating in the stream handler — tools are offered when **conversation has attached KBs**. (Follow-up: wire flag or document as reserved.) |

---

## 3. Recommended delivery order (remaining RAG work)

This order matches **finish what we already agreed** (queue + reliability) before adding **new** retrieval science.

| Phase | Theme | Rationale |
|-------|--------|-----------|
| **P0** | **Queued ingest + worker process** | Matches [`2026-03-31`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md) §2 and enterprise §3: API should not block on large files; Redis already exists in Compose. |
| **P1** | **Resumable / idempotent ingest** | Same specs: crash mid-batch should not always mean “start from zero” or undefined partial state; pairs with job retries from P0. |
| **P2** | **Spec & registry hygiene** | Update status lines in 03-25 / 03-30 / 03-31 and the README snapshot so engineers do not re-implement hybrid search. |
| **P3** | **Ingest UX polish** | Client-side **max file size** before upload; optional **HTTP upload progress** ([`2026-03-31`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md) §5.1). |
| **P4** | **`use_rag` semantics** | Either enforce “no tools when false” or remove/rename the field; align frontend. |
| **P5** | **Agentic RAG** | Raise **`rag_max_tool_iterations`** above 1 when product wants multi-step search; add tests and UI affordances for multiple tool rounds. |
| **P6+** | **Enterprise / quality backlog** | HyDE, OCR (**R-05**), connectors (**R-06**), shared KB ACL, guardrails on RAG text, FinOps — from enterprise + 03-30 Tier 2–3. |

Phases **P0–P1** are the critical path for “RAG pipeline is production-shaped.” **P2** prevents organizational thrash.

---

## 4. Capability catalog — RAG features

Each row: **what** the capability is, **backend** and **UI** surfaces, **status**, and **validation criteria** (objective checks).

**Status legend:** `shipped` | `partial` | `planned` | `backlog`

### 4.1 Corpus, access, and chat binding

| ID | Capability | Backend | UI | Status | Validation criteria |
|----|------------|---------|----|--------|---------------------|
| **R-C01** | Knowledge bases (CRUD, owner-scoped) | `api/knowledge_bases.py`, `models/knowledge_base.py` | `/knowledge-bases`, create/edit flows | shipped | User can create KB, rename, see in list; API returns 403 for other user’s KB. |
| **R-C02** | Documents under KB (upload, list, delete) | `POST/GET/DELETE …/knowledge-bases/{id}/documents` | KB detail route | shipped | Upload creates `pending` → terminal `ready` or `failed`; list shows status. |
| **R-C03** | Attach KBs to conversation | `PUT …/conversations/{id}/knowledge-bases`, join table | `KbChatPicker` / conversation KB UI | shipped | Thread uses only attached KB IDs; API rejects unattached KBs. |
| **R-C04** | Shared / tenant KB ACL | Not implemented | N/a | backlog | `can_access_knowledge_base` beyond owner; tests for cross-user attach and retrieval denial. |

### 4.2 Ingest pipeline

| ID | Capability | Backend | UI | Status | Validation criteria |
|----|------------|---------|----|--------|---------------------|
| **R-I01** | Text extraction (pdf, md, txt, …) | `workers/ingest/readers.py` | Error surfaced on doc row | partial | Unsupported ext → `failed` with clear reason; golden file tests per type. |
| **R-I02** | Semantic / code chunking | `workers/ingest/chunking.py` | N/a | shipped | Chunks have stable `meta` (source, section, page where applicable); no empty-only success. |
| **R-I03** | Embeddings + persist chunks | `services/embedding.py`, `worker.py` | N/a | shipped | `document_chunks` rows with embedding; `documents.status=ready`. |
| **R-I04** | Full-text `search_vector` on chunks | Ingest updates `tsvector`; migration `017_*` | N/a | shipped | BM25 leg of retrieval returns hits for keyword-only queries in tests. |
| **R-I05** | Progress fields | `chunks_total`, `chunks_done`, progress API | Progress sub-row on KB detail while ingesting | shipped | During ingest, `chunks_done` increases; completes at `chunks_total`; stops polling when `ready`. |
| **R-I06** | File size limit | Config `kb_max_file_size_mb`, API enforcement | Spec: client pre-check | partial | Reject oversize at API with clear error; optional: UI rejects before upload ([`2026-03-31`](./2026-03-31-rag-toolcall-ingest-retrieval-design.md) §5.1). |
| **R-I07** | **Async queue + worker deployment** | Enqueue from API; consumer in separate process/container; Redis (or chosen broker) | Fast return on upload; job status visible | planned | Upload HTTP returns without waiting for embed completion; worker drains queue; integration test with real Redis. |
| **R-I08** | **Resumable ingest** | Worker restarts from last safe batch OR defined full-replay rule | Same progress UI; no duplicate chunks | planned | Kill worker mid-ingest → retry completes to `ready` without corruption; DB chunk count matches expected. |

### 4.3 Retrieval and grounding (chat)

| ID | Capability | Backend | UI | Status | Validation criteria |
|----|------------|---------|----|--------|---------------------|
| **R-R01** | Tool `search_knowledge_base` in stream | `api/conversations.py` loop, `rag.search_knowledge_base_tool` | “Searching knowledge bases…” state | shipped | With KB attached, model can invoke tool; stream receives tool events; answer follows. |
| **R-R02** | pgvector candidate retrieval | `services/rag.py` | N/a | shipped | Only `ready` docs in attached KBs; respects `rag_max_top_k`. |
| **R-R03** | BM25 + RRF merge | `services/rag.py` | N/a | shipped | For query matching rare token in corpus, chunk appears in merged set (regression test). |
| **R-R04** | Rerank (Voyage) + cosine fallback | `services/rag.py` | N/a | shipped | With `VOYAGE_API_KEY`, rerank path invoked; without key, cosine ordering still returns results. |
| **R-R05** | Similarity threshold | `rag_similarity_threshold` | N/a | shipped | When all scores below threshold, tool returns empty context path; no bogus “sources”. |
| **R-R06** | Source attribution + structured citations | Formatting in `rag.py`; parsing into `message.extra` | `MessageKbIndicator` Sources chips | shipped | Assistant message `extra` contains `used_kbs` with citations; UI lists chips; click copies ref. |
| **R-R07** | `use_rag` request flag | Field on `StreamMessageBody` | Frontend may send flag | partial | **Either** flag disables tools when false **or** API docs state flag unused — covered by contract test. |
| **R-R08** | Multi-iteration tool loop | `rag_max_tool_iterations` | Loading states for multiple searches | partial | Default 1; increasing N allows multiple tool rounds without stream corruption; e2e optional. |
| **R-R09** | HyDE / query rewriting | N/a | N/a | backlog | Measurable recall improvement on short-query fixture set; latency budget documented. |
| **R-R10** | `retrieve_context_with_meta` (legacy/simple) | `services/rag.py` | N/a | shipped | Unit tests; used where chat tool path is not invoked. |

### 4.4 Enterprise / platform (explicit backlog)

| ID | Capability | Backend | UI | Status | Validation criteria |
|----|------------|---------|----|--------|---------------------|
| **R-E01** | OCR / scanned PDF (**R-05**) | Extractor routing | Upload hints | backlog | Golden PDF images → text; failed docs marked clearly. |
| **R-E02** | External connectors (**R-06**) | Sync jobs, cursors | Connector admin UI | backlog | Incremental sync; conflict rules documented. |
| **R-E03** | Virus scan / content policy | Pre-ingest hook | Quarantine status | backlog | Infected file never reaches `ready`. |
| **R-E04** | Guardrails on retrieved text (**GR-**) | Same pipeline as user input | Policy messaging | backlog | Block/redact logged; user sees safe outcome. |
| **R-E05** | Blob storage + hashing | `storage_path` abstraction | N/a | backlog | Worker streams from blob URL; integrity check. |

---

## 5. Cross-cutting validation (CI-friendly)

- **Backend:** `pytest` for `services/rag.py` (hybrid, rerank fallback, threshold), ingest worker tests, knowledge base API tests.
- **Frontend:** e2e or component tests for KB progress, `MessageKbIndicator`, stream tool states (`frontend/e2e/` patterns).
- **Contract:** OpenAPI / typed client stays aligned with `progress` and stream SSE event shapes when queue work lands.

---

## 6. Maintaining this document

When you ship **R-I07**, **R-I08**, or move a row from `partial` → `shipped`:

1. Update **§2** snapshot and the row in **§4**.
2. Adjust **§3** phases (completed phases sink to “done” bullets or remove).
3. Patch **[`README.md`](./README.md)** implementation snapshot so the registry matches.

Do not delete older specs; add a one-line banner at the top of heavily stale files pointing here if confusion persists.
