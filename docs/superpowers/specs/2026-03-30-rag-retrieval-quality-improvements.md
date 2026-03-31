# RAG retrieval quality — from naive to production

**Status:** brainstorming  
**Date:** 2026-03-30  
**Context:** Current RAG works end-to-end (KB → ingest → embed → retrieve → inject → stream) but uses a naive approach that won't scale beyond small KBs. This document captures concrete improvements ordered by impact and effort.  
**Parent spec:** [`2026-03-25-rag-enterprise-design.md`](./2026-03-25-rag-enterprise-design.md) §4–§5.

---

## Current state (what we have)

| Layer | Implementation | Limitation |
|---|---|---|
| **Chunking** | Fixed 800-char splits, no overlap (`tasks/ingest.py`) | Breaks mid-sentence, mid-function; loses document structure |
| **Retrieval** | pgvector cosine distance, `top_k=5` (`services/rag.py`) | Too few chunks; no reranking; noisy results |
| **Injection** | Concatenate top chunks into system prompt | Wastes context window on low-relevance text; no compression |
| **Query** | Single embedding of the user's message | One vector can't capture multi-faceted questions |
| **Metadata** | `{"source": filename}` only | No page numbers, section titles, or structural context |

For a handful of short documents this works. For a 1 GB file, a full GitHub repo, or a large doc corpus it will fail — too many irrelevant chunks, missed relevant content, and context window exhaustion.

---

## Tier 1 — high impact, low effort

### 1.1 Semantic chunking with overlap

**Problem:** Fixed 800-char windows split mid-sentence and lose context at boundaries.

**Approach:**
- Replace `_chunk_text` in `tasks/ingest.py` with a recursive splitter that respects paragraph → sentence → word boundaries.
- Target ~500 tokens per chunk (not characters) with 10–15% overlap.
- For code files (.py, .ts, .js, etc.): use AST or tree-sitter to split on function/class boundaries so each chunk is a complete logical unit.
- For Markdown/HTML: split on heading structure (h1/h2/h3 sections).
- Store richer metadata: `{"source": filename, "page": N, "section": "heading text", "char_start": N, "char_end": N}`.

**Effort:** Small. Swap the chunker; re-ingest existing documents. No schema changes beyond richer `meta` JSON.

**Files touched:** `tasks/ingest.py`, possibly a new `services/chunking.py`.

### 1.2 Increase top_k and add reranking

**Problem:** 5 chunks by embedding distance alone is noisy. Embedding similarity is a coarse filter — it catches topical relevance but not query-specific precision.

**Approach:**
- Retrieve **top 20–30** chunks from pgvector (cheap; already indexed).
- Re-rank with a cross-encoder: **Voyage Rerank** (same SDK we already use for embeddings, `voyageai.Client.rerank()`), or Cohere Rerank, or a local `bge-reranker-v2`.
- Pass only the **top 5–8 after reranking** into the prompt.
- Config: `rag_initial_top_k` (pgvector stage), `rag_final_top_k` (after rerank), `rag_max_chars` (char budget for injected context).

**Effort:** Small–medium. Add a rerank call between retrieval and injection. Voyage Rerank is a single API call. Config goes in `Settings`.

**Files touched:** `services/rag.py`, `config.py`, `api/conversations.py` (pass settings).

### 1.3 Minimum similarity threshold

**Problem:** When no chunks are relevant, the model still gets injected with noise and hallucinates grounded-sounding answers.

**Approach:**
- After reranking (or after pgvector if no reranker), drop chunks below a configurable similarity threshold.
- If zero chunks remain: omit the RAG block entirely. Optionally inject a system line: "No matching internal context was found. Answer from general knowledge or ask the user to clarify."
- Setting: `rag_min_similarity` (default 0.3 or tuned per embedding model).

**Effort:** Minimal. A few lines in `retrieve_context_with_meta`.

**Files touched:** `services/rag.py`, `config.py`.

---

## Tier 2 — medium impact, medium effort

### 2.1 Structured context blocks with source attribution

**Problem:** Chunks are concatenated as plain text. The model can't cite sources, and the user can't verify claims.

**Approach:**
- Format each injected chunk as:
  ```
  [Source: {filename}, page {page}, section "{section}"]
  {chunk text}
  ```
- Instruct the model: "When using context, cite the source in [brackets]."
- Parse citations from the assistant's response and return them in `extra.used_kbs[].citations` for the UI to render as clickable references.

**Effort:** Medium. Formatting is simple; citation parsing and UI rendering are the real work.

**Files touched:** `services/rag.py` (formatting), `api/conversations.py` (parsing), frontend citation UI component.

### 2.2 HyDE (Hypothetical Document Embeddings)

**Problem:** Short user questions ("how does auth work?") produce poor embeddings for retrieval. The embedding of the question is far in vector space from the embedding of the answer text.

**Approach:**
- Before embedding the query, ask the LLM to generate a brief hypothetical answer (1–2 sentences).
- Embed that hypothetical answer instead of (or in addition to) the raw query.
- The hypothetical answer's embedding is closer in vector space to actual relevant chunks.
- Use a fast/cheap model for the hypothesis (e.g., Haiku) to keep latency low.

**Effort:** Medium. One additional LLM call per retrieval (adds ~200–500ms latency). Can be optional/configurable.

**Files touched:** `services/rag.py` or a new `services/rag_query.py`, `api/conversations.py`.

### 2.3 Hybrid search (BM25 + vector)

**Problem:** Pure vector search misses exact keyword matches (error codes, function names, config keys).

**Approach:**
- Add a `tsvector` column to `document_chunks` (Postgres full-text search).
- At query time, run both BM25 (keyword) and pgvector (semantic) searches.
- Merge results with Reciprocal Rank Fusion (RRF): `score = 1/(k + rank_vector) + 1/(k + rank_bm25)`.
- Feed merged top-N into the reranker.

**Effort:** Medium. Requires an Alembic migration for the tsvector column + GIN index, a trigger or ingest-time update, and a merge step in retrieval.

**Files touched:** New migration, `tasks/ingest.py`, `services/rag.py`.

---

## Tier 3 — high impact, high effort (architectural)

### 3.1 Agentic RAG (tool-based retrieval)

**Problem:** One-shot "retrieve then answer" doesn't handle complex questions that need multiple searches, follow-up queries, or "I need more context" loops.

**Approach:**
- Expose retrieval as a **tool call** the LLM can invoke during generation:
  ```json
  {
    "name": "search_knowledge_base",
    "parameters": {
      "query": "authentication middleware configuration",
      "kb_ids": [1, 3],
      "top_k": 10
    }
  }
  ```
- The model decides **when** to search (maybe zero times for simple questions), **what** to search for (reformulating the query), and **whether** results are sufficient.
- Supports multi-turn retrieval: the model can search, read results, search again with a refined query.
- This is the pattern used by Cursor, Perplexity, and OpenAI's retrieval-augmented tools.

**Implementation sketch:**
- LangChain tool or native Anthropic tool_use / OpenAI function_calling.
- The stream handler invokes retrieval when the model emits a tool call, feeds results back, and continues generation.
- Requires switching from simple `stream_deltas` to an agent loop.

**Effort:** High. Changes the streaming architecture from "pipe tokens" to "agent loop with tool calls." But this is where the industry is heading and it's the right long-term architecture.

**Files touched:** `services/rag.py` (expose as callable), new `services/rag_agent.py` or similar, `api/conversations.py` (agent loop), `services/llm_providers/langchain_chat.py` (tool support).

### 3.2 Hierarchical / multi-level retrieval

**Problem:** Flat chunk search doesn't scale to large corpora. Searching 1M chunks is slow and returns scattered, decontextualized results.

**Approach:**
- **Document-level summaries:** On ingest, generate a summary of each document (LLM call). Store as a separate embedding.
- **Two-stage retrieval:**
  1. Find the **top N documents** by summary embedding similarity.
  2. Search chunks **only within those documents**.
- For code repos: index at **file level** (file path + summary), then drill into **function/class level** chunks.
- Optional: add **section-level** summaries for long documents (one summary per heading group).

**Effort:** High. Requires summary generation at ingest time (LLM cost), new DB rows/tables for summaries, and a two-pass retrieval pipeline.

**Files touched:** `tasks/ingest.py`, new `services/summarize.py`, `services/rag.py`, possibly new migration for summary table.

### 3.3 Graph RAG / structural retrieval

**Problem:** Code repositories and structured documentation have relationships (imports, inheritance, cross-references) that flat vector search ignores.

**Approach:**
- Build a **knowledge graph** at ingest time: entities (files, functions, classes, config keys) and relationships (imports, calls, references).
- At query time: find relevant entities by embedding, then traverse the graph to include related context (e.g., "show me the auth middleware" also pulls in the config it reads and the routes it protects).
- Can use Neo4j, or keep it simple with a Postgres adjacency table.

**Effort:** Very high. Graph extraction, storage, and traversal are each substantial. Best suited for code-specific use cases where structure matters most.

**Files touched:** New extraction pipeline, new graph model/table, new graph traversal in retrieval.

---

## Recommended implementation order

```
Phase 1 (next sprint, immediate quality win):
  1.1 Semantic chunking with overlap
  1.2 Increase top_k + Voyage Rerank
  1.3 Minimum similarity threshold

Phase 2 (following sprint, measurable improvement):
  2.1 Structured context blocks + citations
  2.3 Hybrid search (BM25 + vector)

Phase 3 (when scaling demands it):
  3.1 Agentic RAG (tool-based retrieval)
  3.2 Hierarchical retrieval

Phase 4 (specialized, if code-repo KBs become a product focus):
  2.2 HyDE
  3.3 Graph RAG
```

Phase 1 items are independent of each other and can be implemented in parallel. Phase 3 is the biggest architectural shift but delivers the most transformative improvement — the model becomes an active retriever rather than a passive consumer of pre-fetched context.

---

## Success metrics

| Metric | Current | Target (Phase 1) | Target (Phase 3) |
|---|---|---|---|
| **Chunk relevance** (manual eval, % of injected chunks actually useful) | ~40–60% | 70–80% | 85%+ |
| **Answer groundedness** (claims supported by retrieved context) | Unmeasured | Measurable via citations | Measurable + verifiable |
| **Max corpus size** (practical, acceptable latency) | ~50 docs | ~500 docs | 10K+ docs / full repos |
| **Retrieval latency** (p95) | ~200ms | ~400ms (rerank added) | ~800ms (agent may multi-search) |
