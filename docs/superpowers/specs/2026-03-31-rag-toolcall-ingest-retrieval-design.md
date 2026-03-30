# RAG Tool-Call, Ingest Worker & Retrieval Optimizations

**Status:** approved
**Date:** 2026-03-31
**Context:** Current RAG pre-injects retrieved chunks into the system prompt before the model sees them. This spec replaces that with tool-call-based retrieval, upgrades the retrieval pipeline quality, decouples the ingest pipeline into a scalable worker module, and introduces hybrid search and semantic chunking.
**Related specs:** [`2026-03-30-rag-retrieval-quality-improvements.md`](./2026-03-30-rag-retrieval-quality-improvements.md), [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md)

---

## 1. RAG Tool-Call (replacing system prompt injection)

### Current behavior

```
embed query → retrieve top-5 chunks → inject into system prompt → stream tokens
```

Context is pre-fetched whether relevant or not. The model receives it passively and cannot request more or refine the query.

### New behavior

```
stream starts
  → model emits tool_call { name: "search_knowledge_base", query, kb_ids, top_k? }
  → server: pgvector (max_top_k) → Voyage Rerank → top min_top_k chunks
  → chunks returned as tool result
  → model continues generation with grounded context
```

The model decides **when** to search and **what** to search for. If the question needs no KB context, no retrieval happens. If the answer requires specific terms, the model formulates a precise query.

### Agent loop design

`api/conversations.py` stream loop becomes a single-iteration agent loop:

```
max_tool_iterations = 1  (config, bump to 3+ later for multi-step agentic RAG)

loop:
  stream LLM response
  if tool_call emitted:
    execute search_knowledge_base(query, kb_ids, top_k)
    feed tool result back to model
    continue streaming (counts as 1 iteration)
  else:
    pass tokens to client, done
```

`max_tool_iterations=1` is the current default. The architecture supports increasing this to N without structural changes.

### Tool definition

```json
{
  "name": "search_knowledge_base",
  "description": "Search the attached knowledge bases for relevant context. Call this when you need information from the user's documents to answer accurately.",
  "parameters": {
    "query": "string — the search query, formulated to maximize retrieval precision",
    "kb_ids": "list[int] — knowledge base IDs to search (subset of attached KBs)",
    "top_k": "int? — optional override for number of results, defaults to rag_min_top_k"
  }
}
```

### Retrieval pipeline (inside tool execution)

```
1. Embed query (query input_type)
2. pgvector cosine search → rag_max_top_k candidates
3. Voyage Rerank (client.rerank(query, documents)) → scored candidates
4. Filter: drop chunks below rag_similarity_threshold
5. Take top rag_min_top_k remaining chunks
6. If zero chunks remain: return "No relevant context found in the knowledge bases."
7. Format chunks with source attribution (see §3)
8. Return as tool result
```

### New config settings (`config.py`)

| Setting | Default | Description |
|---|---|---|
| `rag_max_top_k` | 30 | Max candidates fetched from pgvector (wide net) |
| `rag_min_top_k` | 8 | Min chunks kept after reranking (precision pass) |
| `rag_similarity_threshold` | 0.3 | Drop threshold — chunks below this score are excluded |
| `rag_max_tool_iterations` | 1 | Max tool call iterations per turn (future: 3+ for agentic) |

### Source attribution format

Each chunk returned to the model is formatted as:

```
[Source: {filename}, section: "{section}"]
{chunk text}
```

The model is instructed to cite sources in `[brackets]` when using context. Citations are parsed from the response and stored in `message.extra.used_kbs[].citations` for frontend rendering.

### Files touched

- `backend/src/ai_portal/api/conversations.py` — agent loop, tool dispatch
- `backend/src/ai_portal/services/rag.py` — retrieval pipeline, reranking, source formatting
- `backend/src/ai_portal/config.py` — new settings

---

## 2. Ingest Worker Module (decoupled, scalable)

### Design principles

- Self-contained under `backend/src/ai_portal/workers/ingest/`
- No imports from `api/` layer — communicates via DB and task queue only
- Deployable as a separate container/worker cluster; scales independently from the API server
- API server enqueues jobs and polls `Document.status` — never calls ingest code directly

### Architecture

```
API server              Task Queue           Ingest Worker(s)
    |                       |                      |
    | -- enqueue job -----> |                      |
    |                       | -- dispatch task --> |
    |                       |                      | -- stream read file (pages/sections)
    |                       |                      | -- semantic chunk (structure-aware)
    |                       |                      | -- embed batch (capped batch size)
    |                       |                      | -- commit chunks (every 100)
    |                       |                      | -- update Document.progress
    | <-- poll status ------|----------------------|
```

### Streaming read (memory-efficient)

Files are never loaded fully into memory. Processing is page/section-based:

- **PDF**: read page by page via `pypdf` or `pdfminer`
- **DOCX/HTML**: section by section
- **Plain text / Markdown / code**: line-buffer streaming
- **Max file size**: enforced at upload time — `kb_max_file_size_mb` (default 500MB)

### Progress tracking

`Document` model gains two fields:

```python
chunks_total: int | None  # set once file is scanned
chunks_done: int          # incremented every commit batch
```

API exposes `GET /knowledge-bases/{kb_id}/documents/{doc_id}/progress` for the frontend progress bar.

### Batched commits

Chunks are written to DB in batches of 100 (configurable: `ingest_commit_batch_size`). If the worker crashes at chunk 800 of 2000, the document is resumable from the last committed batch.

### Embedding batching

Voyage SDK already batches internally; worker caps batch at `ingest_embed_batch_size` (default 128) to avoid API timeouts on large files.

### Module structure

```
backend/src/ai_portal/workers/
└── ingest/
    ├── __init__.py
    ├── worker.py          # task entry point (replaces tasks/ingest.py logic)
    ├── readers.py         # file-type streaming readers
    ├── chunking.py        # semantic chunker (all file types)
    └── progress.py        # progress update helpers
```

`tasks/ingest.py` becomes a thin shim that calls `workers/ingest/worker.py` — backward compatible.

### New config settings

| Setting | Default | Description |
|---|---|---|
| `kb_max_file_size_mb` | 500 | Max upload size, enforced at API layer |
| `ingest_commit_batch_size` | 100 | Chunks per DB commit |
| `ingest_embed_batch_size` | 128 | Texts per embedding API call |

### Files touched

- `backend/src/ai_portal/workers/ingest/` — new module
- `backend/src/ai_portal/tasks/ingest.py` — thin shim
- `backend/src/ai_portal/models/document.py` — `chunks_total`, `chunks_done` fields
- `backend/src/ai_portal/api/knowledge_bases.py` — progress endpoint, file size validation
- `backend/src/ai_portal/config.py` — new settings
- New Alembic migration for `chunks_total`, `chunks_done` columns

---

## 3. Semantic Chunking

### Strategy per file type

| File type | Split strategy | Overlap |
|---|---|---|
| Plain text / prose | Paragraph → sentence boundaries | 10–15% (last N sentences) |
| Markdown | Heading structure (h1/h2/h3 sections) | First sentence of previous section |
| HTML | Block elements (p, section, article) | 10% |
| Code (.py, .ts, .js, etc.) | AST function/class boundaries | Docstring of previous unit |
| PDF | Page → paragraph | 10–15% |

Target: ~500 tokens per chunk (not characters). Overlap prevents context loss at boundaries.

### Richer metadata

Each chunk stores:

```python
meta = {
    "source": filename,
    "section": "heading text or function name",
    "page": N,           # for PDFs
    "char_start": N,
    "char_end": N,
    "file_type": "markdown" | "code" | "prose" | "pdf",
}
```

### Files touched

- `backend/src/ai_portal/workers/ingest/chunking.py` — new semantic chunker
- `backend/src/ai_portal/workers/ingest/worker.py` — uses chunker

---

## 4. Hybrid Search (BM25 + Vector)

### Problem

Pure vector search misses exact keyword matches: error codes, config keys, function names, identifiers. BM25 (Postgres full-text search) catches these; vector search catches semantic meaning. Combined they cover both.

### Implementation

**At ingest time:**
- Add `tsvector` column to `document_chunks`, populated from `content` during ingest
- GIN index on the column for fast full-text search

**At query time:**
```
1. Vector search: pgvector cosine → top rag_max_top_k candidates (with rank positions)
2. BM25 search:   tsvector/tsquery → top rag_max_top_k candidates (with rank positions)
3. RRF merge:     score = 1/(k+rank_vector) + 1/(k+rank_bm25), k=60
4. Take top rag_max_top_k from merged list
5. Voyage Rerank → rag_min_top_k final chunks
```

Both searches run in parallel (two DB queries, merged in Python).

### Files touched

- New Alembic migration — `tsvector` column + GIN index on `document_chunks`
- `backend/src/ai_portal/workers/ingest/worker.py` — populate `tsvector` at ingest
- `backend/src/ai_portal/services/rag.py` — hybrid search + RRF merge

---

## 5. Frontend Integration

### 5.1 Ingest progress tracking

**KB detail page (`routes/knowledge-bases/$id.tsx`):**
- Each document row shows a real-time progress bar when `status === "ingesting"`
- Progress bar reads from `GET /knowledge-bases/{kb_id}/documents/{doc_id}/progress` → `{ chunks_done, chunks_total }`
- Poll every 1.5s while any document is ingesting (same pattern as `KnowledgeBaseConnectorsSection` auto-refetch)
- When `chunks_total` is known: show `chunks_done / chunks_total chunks` with a percentage bar
- When `chunks_total` is null (file scan not yet complete): show an indeterminate spinner
- On completion (`status === "ready"`): invalidate document list query, stop polling

**Upload flow (`CreateKnowledgeBaseDialog.tsx`):**
- Add file size validation client-side before upload — reject files above `kb_max_file_size_mb` with a clear error message (avoid a silent server rejection)
- Show per-file upload progress via `XMLHttpRequest` or `fetch` with `ReadableStream` — progress bar during the HTTP upload itself, then transition to the ingest progress bar

### 5.2 Tool-call RAG — streaming UI changes

**`ConversationThreadPage.tsx`:**
- When the model emits a tool call during streaming, the stream momentarily pauses
- Show an inline **"Searching knowledge bases..."** indicator in the streaming bubble (not a full spinner — a subtle animated text or pulsing icon)
- When tool result is returned and streaming resumes, the indicator disappears and tokens flow normally
- The existing `MessageKbIndicator` (📚 popover) still works — KB metadata is returned in `message.extra.used_kbs` as before

**KB picker — no change needed:** the model receives `kb_ids` from the conversation settings; it decides which to search. The picker remains the user's way of attaching/detaching KBs.

### 5.3 Source citations UI

**`MessageKbIndicator` (existing component — extend):**
- Currently shows: KB name, chunks used, top score, sections
- Add: `citations` list — each citation links to the source file/section
- Render citations as clickable chips: `[filename, section]`
- For now, clicking a citation copies the source reference to clipboard (deep-linking to documents is a future feature)

### 5.4 New query keys / hooks

```typescript
// lib/queryKeys.ts additions
documentProgress: (kbId: number, docId: number) => ['kb', kbId, 'doc', docId, 'progress']

// New hook
useDocumentProgressQuery(kbId, docId, { enabled: status === 'ingesting' })
  // polls every 1500ms, stops when status !== 'ingesting'
```

### Frontend files touched

- `frontend/src/routes/knowledge-bases/$id.tsx` — document progress bars, polling
- `frontend/src/components/knowledge-bases/CreateKnowledgeBaseDialog.tsx` — file size validation, upload progress
- `frontend/src/components/chat/ConversationThreadPage.tsx` — tool-call streaming indicator
- `frontend/src/components/knowledge-bases/MessageKbIndicator.tsx` — citations display (extend existing)
- `frontend/src/lib/queryKeys.ts` — new progress query key
- New hook: `frontend/src/hooks/useDocumentProgressQuery.ts`

---

## 6. Implementation order (phased)

```
Phase 1 — Ingest worker (foundation, unblocks everything):
  - Decouple ingest into workers/ingest/ module
  - Semantic chunking
  - Progress tracking + streaming reads
  - File size limits

Phase 2 — Retrieval quality:
  - Hybrid search (BM25 + vector)
  - Voyage Rerank integration
  - rag_max_top_k / rag_min_top_k / rag_similarity_threshold config

Phase 3 — RAG tool-call:
  - Agent loop in conversations.py
  - search_knowledge_base tool definition
  - Source attribution + citation parsing
  - Remove system prompt injection
```

Phase 1 is a prerequisite for Phase 2 (new chunker produces richer metadata used in retrieval). Phase 2 and 3 can overlap once Phase 1 is stable.

---

## 7. Success metrics

| Metric | Current | Target (Phase 2) | Target (Phase 3) |
|---|---|---|---|
| Chunk relevance (% of injected chunks actually useful) | ~40–60% | 75–85% | 85–90% |
| Large file ingest (max practical size) | ~10MB before issues | 500MB | 500MB |
| Retrieval latency p95 | ~200ms | ~500ms (rerank added) | ~400ms (tool-call, on demand) |
| Answer groundedness | Unmeasured | Measurable via citations | Measurable + verifiable |
