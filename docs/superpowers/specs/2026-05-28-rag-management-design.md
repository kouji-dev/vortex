# RAG Management — Design Spec

## Purpose

- [ ] Give enterprises a single place to ingest, govern, and search organizational knowledge with citations
- [ ] Mirror source-system permissions so retrieval never leaks
- [ ] Buyer: Head of Productivity / Head of Knowledge / Head of Customer Success / Head of Legal
- [ ] Comparable to: Kapa.ai, Glean, Sana, Vectara, Inkeep

## Module Boundary

### Owns

- [ ] `knowledge_bases` (KB metadata, settings, embedder, vector backend)
- [ ] `kb_documents`, `kb_chunks`, `kb_document_versions`
- [ ] `kb_acls` (per-doc / per-chunk allow lists, mirrored from source)
- [ ] `kb_connectors` (per-KB connector config)
- [ ] `kb_sync_runs`, `kb_sync_errors`
- [ ] `kb_ingest_jobs`, `kb_ingest_steps`
- [ ] `kb_evals`, `kb_eval_runs`
- [ ] `kb_queries` (analytics)
- [ ] `kb_feedback` (per-citation thumbs / corrections)
- [ ] `search_providers` (external web/internal search configs)

### Consumes from Control Plane

- [ ] auth / RBAC / audit / usage / webhooks / BlobStore / settings

### Consumes from Gateway

- [ ] `embed(...)` for all embedding calls
- [ ] `complete(...)` for answer generation
- [ ] `rerank(...)` for retrieval reranking
- [ ] All LLM calls go through Gateway — never direct to a provider SDK from RAG code

### Exposed to other modules (internal contracts)

- [ ] `retrieve(query, kb_ids, actor, top_k, filters) -> RetrievalResult`
- [ ] `answer(query, kb_ids, actor, options) -> StreamedAnswer`
- [ ] `ingest_text(kb_id, doc_meta, text, actor) -> doc_id`
- [ ] Used by chat tool calls, Memories (as a storage backend option), Task Workers (codebase context)

## Features — In Scope

### Knowledge Bases

- [ ] Create / rename / archive / delete KB
- [ ] KB visibility: private (creator), team, org-public
- [ ] KB-level settings: embedder, vector backend, chunking strategy, default retrieval policy, language — each *selected from* the deployment-declared set (not free-form URLs)
- [ ] KB tags / categories
- [ ] Per-KB API key (read-only, scoped)
- [ ] KB clone / fork

### Document Lifecycle

- [ ] Manual upload (file, paste text, paste URL)
- [ ] Document detail view: status, chunks, last sync, errors
- [ ] Document versions (each ingest creates a version; older retained per policy)
- [ ] Document delete + tombstone (search excludes; vectors purged)
- [ ] Manual re-ingest button
- [ ] Quarantine for documents that failed ingestion (with reason + retry)

### Connectors

Each connector is a configurable provider with auth, scheduling, delta sync, and ACL propagation.

- [ ] Web crawler (sitemap + URL seed; robots.txt respected; per-domain rate)
- [ ] File upload (drag-drop, REST)
- [ ] S3 / Azure Blob / GCS bucket (prefix watch)
- [ ] Google Drive (OAuth, folder + shared drive scope)
- [ ] OneDrive / Sharepoint (OAuth, site + library scope)
- [ ] Confluence (cloud + server)
- [ ] Notion (workspace token)
- [ ] Slack (bot install, channel allow list, threads, files)
- [ ] Github (org or repo scope, code + docs + issues + PRs + wiki)
- [ ] Gitlab (group or project scope)
- [ ] Email / IMAP (shared mailbox, label filter)
- [ ] Salesforce Knowledge (production org)
- [ ] Zendesk / Intercom (articles + tickets opt-in)
- [ ] Jira (project scope, attachments)
- [ ] Generic HTTP API (cursor-paginated, JSONPath extractors)
- [ ] Connector framework: auth (OAuth / token / service principal), scheduler (cron + webhook), delta sync (cursor / etag / change feed), ACL extraction, attachment handling, idempotency key

### Ingestion Pipeline

- [ ] Stage 1 — Fetch: pulled bytes + source metadata
- [ ] Stage 2 — Extract: MIME-dispatch to extractor
  - [ ] PDF (text + tables)
  - [ ] DOCX, XLSX, PPTX
  - [ ] HTML (readability mode)
  - [ ] Markdown / RST / AsciiDoc
  - [ ] Plain text / source code (language-detected)
  - [ ] Email (.eml / .msg)
  - [ ] Image OCR (Tesseract default; cloud OCR optional)
  - [ ] Audio transcription (Whisper; gateway-routed)
- [ ] Stage 3 — Normalize: encoding, language detect, dedupe hash
- [ ] Stage 4 — Redact: PII removal per ingest policy (shared guardrail with Gateway)
- [ ] Stage 5 — Chunk: configurable strategy (fixed, semantic, structural, code-aware)
- [ ] Stage 6 — Metadata enrich: title, author, date, tags, language, source URL
- [ ] Stage 7 — Embed: batch through Gateway
- [ ] Stage 8 — Index: write to vector backend + BM25 store + ACL store
- [ ] Each stage emits progress + errors visible per-document
- [ ] Retry policy per stage; failure-isolated to one document

### Ingestion Execution & Scaling

> **DEFERRED / optional — do later.** In-process execution is sufficient for now. The work below is to build a proper per-part `JobExecutor` abstraction (ingest, connector sync, pipeline, re-embed) so each can run remotely. Not required for v1.

Heavy work (extract / chunk / embed / index + connector sync) runs through a configurable **Job Execution Backend** so it can run in-process for dev or on separate machines (another VPS / AWS) for scale. Remote workers need only DB + queue access — no coupling to the API server.

- [ ] Executor declared in deployment config: `inprocess` (dev), `rq` (Redis queue → remote workers), future `celery` / `sqs` / `aws_batch` / `k8s_job`
- [ ] PARTIAL TODAY: document ingest already dispatches in-process (FastAPI `BackgroundTasks`) when no Redis, else enqueues to RQ for a remote worker (`run_ingest_job`); toggle is implicit on `redis_url`
- [ ] GAP: make the executor an explicit named config choice (not implicit on `redis_url`), routed through the shared abstraction below
- [ ] GAP: connector sync currently runs in-process only (`BackgroundTasks`) — route it through the executor so syncs run remotely
- [ ] GAP: pipeline runner (`rag/pipeline/runner.py`) dispatches per-stage through the executor

### ACL Mirroring

- [ ] On ingest, capture source ACLs (group/user IDs + read/write)
- [ ] Resolve source IDs to org users/groups via IdP mapping (best-effort)
- [ ] Store per-doc + per-chunk allow set
- [ ] Retrieval filters by `actor ∈ allow_set` server-side (never client)
- [ ] Re-sync ACLs on source-side ACL change events (where connector supports)
- [ ] "Permission test" UI: pick a user, see which docs they could retrieve

### Vector Backends

- [ ] pgvector (default, no extra infra)
- [ ] Qdrant (self-hosted recommended for large corpora)
- [ ] Pinecone (managed)
- [ ] Weaviate (optional)
- [ ] Backend abstraction with required ops: `upsert`, `delete`, `query`, `query_with_filter`, `count`

### Search

- [ ] Hybrid search: BM25 + dense + metadata filters merged via Reciprocal Rank Fusion
- [ ] Reranking via Gateway `rerank` (default: voyage-rerank)
- [ ] Filters: source, language, date range, tag, author
- [ ] Boosts: freshness, source priority, popularity
- [ ] Multi-KB federated search (single query → many KBs → merged)

### Search Providers (external, for "AI search" UX)

- [ ] Tavily
- [ ] Exa
- [ ] Brave Search
- [ ] Bing Search
- [ ] Google CSE
- [ ] Internal (this RAG store) as a "search provider" too
- [ ] Search provider abstraction (`search/protocol.py`)
- [ ] Use case: chat tools, agentic web research, KB fallback when no internal hit

### Answer Generation

- [ ] Streaming answer with progressive citation markers `[1]`, `[2]`
- [ ] Citations resolve to source doc + chunk + permalink
- [ ] Citation hover-card UX in frontend
- [ ] Multi-turn conversational RAG (rewrite question + summarize prior turns)
- [ ] Configurable answer length, tone, language
- [ ] Refusal when no high-confidence source ("I don't know" gate)

### Retrieval Policies

- [ ] Per-KB defaults: top_k, min_score, freshness window, max_tokens_to_llm
- [ ] Per-query overrides via API
- [ ] Source priority weights

### Eval Framework

- [ ] Test set: list of `{question, expected_sources, expected_answer (optional)}`
- [ ] Metrics: recall@k, MRR, nDCG (retrieval); answer correctness + faithfulness (generation)
- [ ] LLM-as-judge with disclosed judge model + temp
- [ ] Run on KB snapshot; results compared across runs
- [ ] Regression alert on metric drop > threshold

### KB Chat Playground

- [ ] Pick KB(s) + retrieval policy + model
- [ ] Stream answer + citations
- [ ] Inspect retrieved chunks per turn
- [ ] Save as eval test case

### KB Analytics

- [ ] Top queries
- [ ] Zero-result queries (gap report)
- [ ] Citation hit-rate per doc
- [ ] User feedback (thumbs up/down + reason)
- [ ] Token + storage + query cost dashboard

### Consumer Surfaces

- [ ] REST API: `/v1/kbs/{id}/search`, `/v1/kbs/{id}/answer`
- [ ] Per-KB scoped API key
- [ ] Webhook on KB events (sync_complete, sync_failed, answer_generated)
- [ ] Chat module integration: KB attachment as conversation context

### Sync Operations

- [ ] Sync schedule per connector (cron or interval)
- [ ] Manual sync trigger
- [ ] Delta sync via connector-native change cursor when available; else full re-walk with content-hash dedupe
- [ ] Sync run record (started, ended, docs added/updated/deleted, errors)
- [ ] Backoff on source rate-limit; respect 429/Retry-After

## Features — Out of Scope (for now)

- [ ] Layout-aware document parsing beyond what Unstructured/PyMuPDF give (no LayoutLM-style models in pipeline)
- [ ] Multi-modal (image-as-query) retrieval — text queries only for v1
- [ ] Knowledge graph derived from docs (entity extraction → graph store)
- [ ] Web SDK / embeddable widget for public sites
- [ ] No-code KB sharing externally (public KBs)
- [ ] Fine-tuning embedders on org data
- [ ] On-device retrieval
- [ ] Real-time low-latency KB streaming (collaborative ingest)
- [ ] Versioned dataset releases for downstream training
- [ ] Cross-tenant KB sharing
- [ ] Custom embedding model upload UI (config only via env / settings)
- [ ] Pluggable distributed Job Execution Backend (per-part executor: ingest / connector sync / pipeline / re-embed) — deferred/optional; in-process + existing RQ path is enough for now

## Configurable Abstractions

> **Real implementations required.** Every layer below ships a working implementation against the providers listed — not a stub. The gateway `FakeProvider` is a dev-only shortcut for LLM/embed calls; it is never a substitute for the embedder, vector-store, reranker, search-provider, or connector implementations here.
>
> **Deploy-vs-runtime split** (see suite-overview): for each layer, the *available set* + endpoints + credentials are declared in deployment config (YAML/env) — the UI cannot add a backend or change an endpoint. The UI only enables/disables and sets the KB-level default among the declared set.

| Layer | Declared in YAML/env | Managed in UI |
|---|---|---|
| Embedders | available set, endpoints, keys | enable/disable, per-KB default |
| Vector stores | available backends, connection URLs, keys | enable/disable, per-KB default |
| Rerankers | available set, endpoints, keys | enable/disable, per-KB default |
| Search providers | available set, API keys | enable/disable, default-for-web |
| Connectors | available connector TYPES, OAuth app creds | per-KB connector instance + schedule |

### Connector (`rag/connectors/`)

- [ ] Interface: `Connector` with `setup(config) -> Connector`, `discover() -> Iterator[SourceDoc]`, `fetch(source_doc) -> Bytes+Meta`, `acls(source_doc) -> AclSet`, `delta_cursor()` / `apply_delta_cursor(cursor)`
- [ ] Bundled implementations listed above
- [ ] Connector manifest declares: auth kinds, schedulable, supports_delta, supports_acl, supports_webhook

### Extractor

- [ ] Interface: `Extractor` with `supports(mime)`, `extract(bytes, meta) -> Document`
- [ ] Bundled: `pdf`, `docx`, `xlsx`, `pptx`, `html`, `markdown`, `email`, `image_ocr`, `audio_transcribe`, `code` (language-tagged)

### Chunker

- [ ] Interface: `Chunker` with `chunk(document, opts) -> Iterator[Chunk]`
- [ ] Bundled: `fixed_token`, `sentence`, `semantic` (embedding-based break), `structural` (headings), `code_aware` (AST split)

### Embedder

- [ ] Shared with Gateway

### Vector Store

- [ ] Interface above
- [ ] Bundled: `pgvector`, `qdrant`, `pinecone`, `weaviate`

### Reranker

- [ ] Shared with Gateway

### Search Provider

- [ ] Interface: `SearchProvider` with `search(query, opts) -> Results`
- [ ] Bundled: `tavily`, `exa`, `brave`, `bing`, `google_cse`, `internal_kbs`

### ACL Provider

- [ ] Interface: per-connector ACL mapper
- [ ] Bundled with each connector that supports ACL

### Job Execution Backend (shared — suite-wide) — DEFERRED / optional

- [ ] Interface: `JobExecutor` with `submit(job_name, *args, **opts)`, `health()`
- [ ] Bundled: `inprocess` (dev, FastAPI BackgroundTasks), `rq` (Redis → remote workers); future `celery`, `sqs` / `aws_batch`, `k8s_job`
- [ ] Backend declared in deployment config (deploy-vs-runtime split) — not an implicit toggle
- [ ] Consumers: RAG ingest + connector sync + re-embed jobs (first); intended to converge the suite's other ad-hoc job paths later

## Data Model (sketch)

- [ ] `knowledge_bases(id, org_id, name, slug, visibility, embedder_id, vector_backend, chunker_id, settings_json, status, created_at)`
- [ ] `kb_connectors(id, kb_id, kind, config_encrypted, schedule_cron, last_sync_at, enabled)`
- [ ] `kb_documents(id, kb_id, source_uri, title, mime, content_hash, language, source_acl_json, status, latest_version_id, created_at, updated_at)`
- [ ] `kb_document_versions(id, document_id, version_no, content_hash, extracted_text_ref, meta_json, created_at)`
- [ ] `kb_chunks(id, document_id, version_id, chunk_index, text, embedding_ref, acl_json, meta_json)`
- [ ] `kb_sync_runs(id, connector_id, started_at, ended_at, docs_added, docs_updated, docs_deleted, errors_count, status)`
- [ ] `kb_sync_errors(id, run_id, source_uri, error)`
- [ ] `kb_ingest_jobs(id, document_id, status, started_at, ended_at)`
- [ ] `kb_ingest_steps(id, job_id, stage, status, started_at, ended_at, error)`
- [ ] `kb_queries(id, org_id, actor_json, kb_ids, query_text, top_k, latency_ms, retrieved_doc_ids, ts)`
- [ ] `kb_feedback(id, query_id, citation_index, rating, comment, actor_json, ts)`
- [ ] `kb_evals(id, kb_id, name, test_set_json)`
- [ ] `kb_eval_runs(id, eval_id, snapshot_id, metrics_json, ran_at)`
- [ ] `search_providers(id, org_id, kind, config_encrypted, enabled, default_for_web)`

## Public API (sketch)

- [ ] `POST /v1/kbs` / `GET /v1/kbs` / `PATCH /v1/kbs/{id}` / `DELETE /v1/kbs/{id}`
- [ ] `POST /v1/kbs/{id}/documents` (upload + URL + text)
- [ ] `GET /v1/kbs/{id}/documents?...`
- [ ] `DELETE /v1/kbs/{id}/documents/{doc_id}`
- [ ] `POST /v1/kbs/{id}/connectors` / `GET /v1/kbs/{id}/connectors`
- [ ] `POST /v1/kbs/{id}/connectors/{cid}/sync`
- [ ] `POST /v1/kbs/{id}/search`
- [ ] `POST /v1/kbs/{id}/answer` (streaming SSE)
- [ ] `POST /v1/kbs/federated/answer` (multi-KB)
- [ ] `POST /v1/search` (web/internal search providers)
- [ ] `GET /v1/kbs/{id}/queries` (analytics)
- [ ] `POST /v1/kbs/{id}/feedback`
- [ ] `GET/POST /v1/kbs/{id}/evals`
- [ ] `POST /v1/kbs/{id}/evals/{eid}/run`
- [ ] `POST /v1/kbs/{id}/permission-test`

## UI Surface

- [ ] RAG → KBs list
- [ ] KB detail → Overview (status, stats)
- [ ] KB detail → Documents (table, filter, drill-in)
- [ ] KB detail → Connectors (configure, schedule, history)
- [ ] KB detail → Settings (embedder, chunker, retrieval policy)
- [ ] KB detail → Permissions (ACL test, allow list browser)
- [ ] KB detail → Chat / Playground
- [ ] KB detail → Analytics
- [ ] KB detail → Evals
- [ ] Global → Search Providers config
- [ ] Global → Connector marketplace (preset templates)

## Dependencies on Other Modules

- [ ] Control Plane (hard)
- [ ] Gateway (hard — for all LLM/embed/rerank)

## Acceptance Criteria

- [ ] Org admin can create a KB, attach a Sharepoint connector, schedule daily sync, see documents flow in
- [ ] A document's source ACLs are mirrored: a user without source access cannot retrieve that doc via the API
- [ ] An end user chats against the KB, gets a streaming answer with clickable citations
- [ ] Switching embedder triggers re-embed of all chunks (job visible)
- [ ] A failing document is quarantined; admin sees error reason, can retry
- [ ] Eval run produces recall@k + faithfulness metrics; comparison vs previous run
- [ ] Federated query across 3 KBs returns merged, reranked results within p95 < 2s for top_k=10

## Testing

- [ ] Unit tests per file in `server/api/src/ai_portal/rag/`, `knowledge_base/`, plus new `rag/connectors/`, `rag/extractors/`, `rag/chunkers/`, `rag/search/`
- [ ] Use fixture HTML/PDF/DOCX samples committed under `tests/fixtures/`
- [ ] Mock external connector APIs with `respx`
- [ ] Run only touched-file tests during implementation
- [ ] Defer E2E to the final verification step
- [ ] E2E targets (added at the end): create KB, upload doc, ask question, see citation; web-crawler connector ingests sample site; ACL filter blocks unauthorized user; eval run pass/fail
