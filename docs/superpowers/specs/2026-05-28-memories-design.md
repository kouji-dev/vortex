# Memories — Design Spec

## Purpose

- [ ] Persist user / team / org context across conversations so assistants and workers improve over time without re-explaining
- [ ] Give end users + admins explicit control over what is stored, when it's recalled, when it's forgotten
- [ ] Compliance-first: GDPR delete, PII gating, audit trail per memory use
- [ ] Buyer: Productivity Lead (feature value) + CISO (governance value)

## Module Boundary

### Owns

- [ ] `memories` (the records themselves)
- [ ] `memory_scopes` (user/conversation/team/org/assistant bindings)
- [ ] `memory_extraction_policies` (per-org / per-scope)
- [ ] `memory_recall_policies`
- [ ] `memory_jobs` (background extraction queue)
- [ ] `memory_uses` (audit trail: which memory used in which response)

### Consumes from Control Plane

- [ ] auth / RBAC / audit / usage / webhooks / settings

### Consumes from Gateway

- [ ] `complete(...)` for extraction LLM calls
- [ ] `embed(...)` for recall vector search

### Optionally consumes from RAG

- [ ] As a backing store option (memories-as-KB) — alternative to a dedicated `memories_vectors` table when org wants unified retrieval

### Exposed to other modules (internal contracts)

- [ ] `extract(turns, actor, scope) -> ExtractedMemories` (background or sync)
- [ ] `recall(query, actor, scope_filter, top_k) -> Memories`
- [ ] `delete_for_actor(actor)` (GDPR cascade)

## Features — In Scope

### Memory Scopes

- [ ] `user` (personal, only the owner)
- [ ] `conversation` (only that thread)
- [ ] `assistant` (tied to a specific assistant/agent)
- [ ] `team` (visible to a team, with consent)
- [ ] `org` (visible across org, with admin policy)
- [ ] Memories are tagged with one or more scopes; recall filters by actor's effective scopes

### Memory Types

- [ ] `fact` (atomic statement: "user prefers TypeScript")
- [ ] `preference` (UI/UX / formatting / tone preferences)
- [ ] `entity` (named entity with attributes — person, project, repo, customer)
- [ ] `relation` (link between entities — minimal v1)
- [ ] `episode` (summary of an interaction with timestamp)
- [ ] `procedure` (how-the-user-does-X learned from interactions)

### Extraction

- [ ] Extraction triggers:
  - [ ] After every conversation turn (default off; org policy opt-in)
  - [ ] On explicit user "remember this" (always on)
  - [ ] On conversation close (batched summarization)
  - [ ] Scheduled background job (every N hours, processes recent turns)
- [ ] LLM-based extractor (calls Gateway with caveman-style system prompt)
- [ ] Rule-based extractor (regex / classifier; used as fast pre-filter)
- [ ] Dedupe against existing memories (semantic similarity + literal match)
- [ ] Update existing memory (newer info supersedes) vs add new
- [ ] Conflict policy: `newer_wins`, `keep_both`, `prompt_user`
- [ ] Confidence score per memory; low-confidence = candidate, requires user confirmation

### Recall

- [ ] Vector search over scoped memories
- [ ] Hybrid: vector + recency + importance score
- [ ] Recall budget: max memories to inject per turn (configurable)
- [ ] Recall filters: type, scope, tag, time range, source assistant
- [ ] "Why was this recalled?" — explanation log per memory injection

### Decay & Lifecycle

- [ ] TTL per memory type (preference = ∞, episode = 90d, etc; org-tunable)
- [ ] Importance decay (unused memories lose importance, eventually pruned)
- [ ] Pin / star a memory to exempt from decay
- [ ] Soft delete with 30-day undo
- [ ] Compaction: merge near-duplicate memories on a schedule

### User Controls

- [ ] List my memories (filter, search, sort)
- [ ] Edit memory text
- [ ] Delete memory
- [ ] Bulk delete (by type, scope, time range)
- [ ] Pause memory creation globally / per-assistant
- [ ] Export memories (JSON)
- [ ] Inline "this is from a memory" indicator in chat with link to the memory

### Org / Admin Controls

- [ ] Org-wide memory enabled / disabled
- [ ] Per-scope policy (e.g., team memories require admin approval)
- [ ] Sensitive-category exclusion list (health, financial, sexual orientation, religion, etc.) — extractor must skip
- [ ] PII gate on extraction (uses shared Guardrail providers from Gateway)
- [ ] Allow / deny extractor models (only sanctioned models)
- [ ] Retention policy override per org
- [ ] Audit: see which memories influenced which conversation responses

### Provenance

- [ ] Every memory records: source conversation id, turn ids, timestamp, extractor model, confidence
- [ ] Every memory use logs: query, recall score, response message id, user
- [ ] Right to explanation: user can ask "why do you know X about me?" → trace back to original turn

### Compliance / GDPR

- [ ] Deleting a user cascades: all `memories` where actor=user are purged
- [ ] Per-tenant key envelope for memory text (optional)
- [ ] Export-on-request includes memories
- [ ] Sensitive category opt-out enforced at extractor time
- [ ] Retention enforced by background sweeper

### Integration Points

- [ ] Chat module: on turn complete, fire async extraction job; before turn LLM call, fire recall
- [ ] Assistants: assistant-scoped memories injected into system prompt
- [ ] Task Workers: worker-scoped memories per (repo, user) — workers remember "this repo's lint command is X"
- [ ] RAG: memories surface as a tool the LLM can call (`memory.search`)

### Analytics

- [ ] Memory count over time
- [ ] Top recalled memories
- [ ] Recall hit-rate (how often recalled memories actually used in answer)
- [ ] Extraction success / dedupe / rejection rates

## Features — Out of Scope (for now)

- [ ] Full graph store (entities + relations as a queryable graph) — relations exist but not graph-traversable
- [ ] Cross-org memories
- [ ] Federated memory sync between deployments
- [ ] User-trainable memory extractors (no fine-tune UI)
- [ ] Long-horizon "memory autopilot" (auto-summarize and act without explicit recall)
- [ ] Memory-as-context-window-replacement (no long-context emulation tricks)
- [ ] Voice-only / dictation memory capture
- [ ] Multi-modal memories (image / video memories) — text only for v1

## Configurable Abstractions

### Extractor (`memory/extractors/`)

- [ ] Interface: `Extractor` with `extract(turns, scope, opts) -> List[Memory]`
- [ ] Bundled: `llm_default` (caveman prompt → JSON memories), `llm_typed` (per-type prompt), `rule_based` (regex), `no_op` (always empty)

### Recaller (`memory/recallers/`)

- [ ] Interface: `Recaller` with `recall(query, scope, opts) -> List[Memory]`
- [ ] Bundled: `vector_pgvector`, `vector_qdrant`, `hybrid` (vector + BM25 + recency)

### Store (`memory/stores/`)

- [ ] Interface: `MemoryStore` with `upsert`, `delete`, `list_for_actor`, `search`
- [ ] Bundled: `postgres_default` (pgvector), `rag_backed` (delegate to a hidden KB in RAG module)

### Policy Provider

- [ ] Interface: `MemoryPolicy` with `should_extract(turn, scope) -> bool`, `should_recall(query, scope) -> bool`, `sensitive_category_match(text) -> bool`
- [ ] Bundled: `default`, `strict_eu` (preset that blocks special-category data per GDPR Art. 9)

## Data Model (sketch)

- [ ] `memories(id, org_id, actor_owner_json, scope_kind, scope_ids_json, type, text, embedding_ref, importance, confidence, source_conversation_id NULLABLE, source_turn_ids_json, extractor_model, created_at, last_used_at, expires_at NULLABLE, pinned, deleted_at NULLABLE)`
- [ ] `memory_extraction_policies(id, org_id, scope_kind, triggers_json, sensitive_block_json, model_allow_json)`
- [ ] `memory_recall_policies(id, org_id, scope_kind, top_k, recency_weight, importance_weight, filters_json)`
- [ ] `memory_jobs(id, org_id, kind, scope_kind, payload_json, status, started_at, ended_at, error)`
- [ ] `memory_uses(id, memory_id, query_text_hash, response_message_id, score, ts)`

## Public API (sketch)

- [ ] `GET /v1/memories?...` (filter by scope, type, search)
- [ ] `POST /v1/memories` (manual add — "remember this")
- [ ] `PATCH /v1/memories/{id}` (edit text, pin, importance)
- [ ] `DELETE /v1/memories/{id}` (soft)
- [ ] `POST /v1/memories/bulk-delete`
- [ ] `POST /v1/memories/extract` (manual trigger on conversation)
- [ ] `POST /v1/memories/recall` (debug / playground)
- [ ] `GET /v1/memories/{id}/uses` (provenance)
- [ ] `GET/POST /v1/memories/policies`
- [ ] `POST /v1/memories/pause` / `POST /v1/memories/resume`

## UI Surface

- [ ] Memories → My Memories (list, filter, edit, delete)
- [ ] Memories → Shared (team / org / assistant — read-only or admin-edit)
- [ ] Memories → Settings (pause, scope toggles, export)
- [ ] Chat sidebar → "Memories used in this turn" panel
- [ ] Admin → Memory Policies
- [ ] Admin → Memory Analytics

## Dependencies on Other Modules

- [ ] Control Plane (hard)
- [ ] Gateway (hard — for extraction + embedding)
- [ ] RAG (soft — only if `rag_backed` store chosen)

## Acceptance Criteria

- [ ] After 5 conversation turns with extraction on, relevant memories exist; user can view, edit, delete
- [ ] On a new conversation, recall surfaces matching memories in <100ms p95
- [ ] User clicks "pause memory" → no new extractions until resumed; existing memories untouched
- [ ] Org admin enables `strict_eu` policy → extractor refuses sensitive-category data; audit captures refusal
- [ ] Memory used in an answer is visible in the response sidebar with link to memory + source turn
- [ ] User deletion cascades: all their memories purged within job SLA

## Testing

- [ ] Unit tests per file in `server/api/src/ai_portal/memory/`, plus new `memory/extractors/`, `memory/recallers/`, `memory/stores/`, `memory/policies/`
- [ ] Mock LLM responses for extraction tests
- [ ] Run only touched-file tests during implementation
- [ ] Defer E2E to the final verification step
- [ ] E2E targets (added at the end): turn → extract → recall in next turn, pause stops extraction, sensitive-category gating, GDPR delete cascade, provenance sidebar shows source turn
