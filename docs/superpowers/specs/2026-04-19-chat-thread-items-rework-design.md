# Chat Thread Items Rework — Design Spec

**Date:** 2026-04-19
**Status:** Draft (awaiting user review)
**Owner:** NAJIH Driss

## 1. Problem

Today's chat stack has three intertwined issues:

1. **Token tracking is aggregated per message.** One `message_usage` row per assistant message rolls up all iterations and tool calls. Impossible to answer "how much did iteration 3 cost?" or "which tool calls are burning money?".
2. **Event typing is weak.** SSE events, LLM provider events, and tool results are all untyped `dict`s; the type system can't catch protocol drift between backend and frontend.
3. **No per-step audit surface.** The existing `UsagePanel` shows a 30-day summary; there's no way to see what happened step-by-step inside a conversation, or to attribute cost to specific tool providers (Firecrawl, Jina, Tavily, etc.).

Additional constraint: `streaming_service.py` has grown to 1066 lines and does 14 distinct jobs in one file. Hard to change, hard to test.

## 2. Goal

Rework the chat stack around a single idea: **every event in the SSE stream has a matching typed row in a new `thread_items` table.** Stream shape = storage shape. Cost is attributed at the step level, flows through a single isolated calculator, and is surfaced in a dedicated admin Consumption page.

Scope is a full rewrite of chat streaming + DB model + admin consumption UI, with a destructive one-shot migration. Pre-scale stage; risk is acceptable.

## 3. Non-Goals (v1)

- Per-provider metered cost parsers beyond signals already exposed today (hook exists; add parsers incrementally later).
- WebSocket dashboards; the admin page polls (30s).
- CSV export of consumption data (audit-events export already exists; consumption export is a follow-up).
- Self-service quota management UI for end users (stays admin-only).
- Zero-downtime deploy; maintenance window is acceptable.

## 4. Architecture

### 4.1 Data model

**`threads`** (rename of `chat_conversations`). Same columns: `id`, `org_id`, `user_id`, `assistant_id`, `title`, `model`, `settings`, `summary`, `last_message_at`, `created_at`.

**`thread_items`** (new, replaces `chat_messages` + `message_usage` + `extra.stream_items` JSONB blob).

Shared columns on every row:

| column            | type                | notes                                                |
|-------------------|---------------------|------------------------------------------------------|
| `id`              | BIGSERIAL           | PK                                                   |
| `thread_id`       | BIGINT FK           | → `threads.id`, indexed                              |
| `turn_id`         | UUID                | shared by all items in a turn; matches the UUID on the `user_message` item |
| `kind`            | enum                | discriminator (see 4.2)                              |
| `role`            | enum                | `user \| assistant \| system` or NULL for markers    |
| `status`          | enum                | `streaming \| done \| error \| cancelled`            |
| `provider`        | TEXT                | NULL for text/marker kinds                           |
| `model`           | TEXT                | NULL for non-LLM kinds                               |
| `cost_usd`        | NUMERIC(12,6)       | NULL for non-billable kinds                          |
| `cost_estimated`  | BOOLEAN             | default FALSE                                        |
| `latency_ms`      | INT                 | NULL for instantaneous kinds                         |
| `data`            | JSONB               | kind-specific payload; Pydantic-typed                |
| `parent_item_id`  | BIGINT FK           | e.g. Citation → ToolCall that produced it            |
| `started_at`      | TIMESTAMPTZ         | NULL until status leaves `streaming`                 |
| `finished_at`     | TIMESTAMPTZ         | NULL until terminal                                  |
| `created_at`      | TIMESTAMPTZ         | `DEFAULT clock_timestamp()` for µs-distinct inserts  |

**Ordering** is by `created_at`; `clock_timestamp()` gives microsecond resolution within a single transaction. No `seq` column.

**Indexes:**
- `(thread_id, created_at)` — primary conversation read
- `(thread_id, turn_id)` — turn queries (regenerate, timeline)
- `(org_id, created_at)` — consumption aggregation
- partial on `cost_usd WHERE cost_usd IS NOT NULL` — aggregation scan width

**Constraints:** `CHECK` enforcing the discriminated union (e.g. `kind='llm_call'` requires non-null model + tokens in `data`). RLS mirrors existing `chat_conversations` patterns.

**Removed tables** after migration: `chat_messages`, `message_usage`. Kept and repurposed: `usage_rollup` (now aggregates over `thread_items`), `usage_quota` (reads `SUM(cost_usd) FROM thread_items`), `audit_events` (unchanged; different domain).

### 4.2 Item kinds (discriminated union)

| kind              | role                  | cost?  | data payload                                                                 |
|-------------------|-----------------------|--------|------------------------------------------------------------------------------|
| `user_message`    | user                  | no     | `{ text, attachments[] }`                                                    |
| `turn_end`        | system                | no     | `{ reason: "done" \| "error" \| "cancelled" }`                               |
| `assistant_text`  | assistant             | no     | `{ text }` (one per text block; an assistant turn often has multiple)        |
| `llm_call`        | assistant             | yes    | `{ input_tokens, output_tokens, cached_input_tokens, cache_creation_input_tokens, reasoning_tokens, iteration_index }` |
| `tool_call`       | assistant             | yes    | `{ tool_name, params, result_snippet, error? }`                              |
| `server_tool_use` | assistant             | yes    | `{ tool_name, input }` (Anthropic web_search / Gemini grounding)             |
| `thinking`        | assistant             | no\*   | `{ text }` (\*reasoning tokens billed on the parent `llm_call`)              |
| `citation`        | system                | no     | `{ url, title, snippet }` (parent_item_id → source `tool_call`)              |
| `memory_pill`     | system                | no     | `{ count }`                                                                  |
| `error`           | system                | no     | `{ code, message }`                                                          |

### 4.3 Turn lifecycle

1. User submits → backend generates `turn_id` (UUID) → inserts `user_message` item with that `turn_id`.
2. Streaming begins. For each LLM iteration: insert `llm_call` (streaming), stream `assistant_text` items (streaming), on each `tool_call` event insert `tool_call` (streaming) → dispatch → update (done, cost attached).
3. On `usage` event from provider: update the `llm_call` with tokens + cost, mark `done`.
4. Loop continues until LLM produces text with no tool call, or `max_iterations` reached.
5. Backend writes `turn_end` item (status `done`, `reason: "done"`), fires background tasks (summarizer, memory extractor, audit log), closes SSE.

**Retry = delete every item in the turn except the `user_message`, re-run the loop.**

**Cancel = user POSTs cancel → provider SDK cancellation token tripped → all streaming items flipped to `cancelled` → `turn_end` written with `reason: "cancelled"` → cost preserved via estimation from observed deltas (see 4.5).**

### 4.4 State machine per item

```
Terminal-on-create:     user_message, turn_end, citation, memory_pill, error
                        → always inserted with status = done

Active-then-terminal:   llm_call, assistant_text, thinking, tool_call, server_tool_use
                        → streaming ──► done
                                    ──► error
                                    ──► cancelled
```

Transitions enforced in `item_writer.py` (see 5). Unrecoverable backend crash → stale `streaming` items older than N seconds flipped to `error` with `data.error = "interrupted"` on next thread read (lazy sweep).

### 4.5 Cost attribution

**Isolated module** `chat/cost_calculator.py` is the only public cost API. Stable signature:

```python
def compute_llm_cost(model, input_tokens, output_tokens, cached, cache_creation, reasoning) -> CostResult
def compute_tool_cost(outcome: ToolCallOutcome) -> CostResult
def compute_server_tool_cost(tool_name, provider, usage_metadata) -> CostResult

class CostResult(BaseModel):
    cost_usd: Decimal
    estimated: bool
    source: Literal["flat_rate", "provider_metered", "unknown_model", "free"]
```

**Sources fed to the calculator:**
- `llm_pricing.py` — flat rates per model (moved from `usage/pricing.py`); deterministic, `estimated=False` for known models.
- `tool_pricing.py` — flat fallback rates per tool provider.
- Each tool provider adapter returns `ToolCallOutcome` with an optional `cost_usd: Decimal | None`. If present → use it (`source="provider_metered"`, `estimated=False`); else fallback to flat rate (`source="flat_rate"`, `estimated=True`).

**Adapter responsibility:** Firecrawl reads `credits_used` and converts to USD; DuckDuckGo returns `Decimal("0")` (explicit free); adapters that can't parse cost return `None`. No parsing logic lives in `cost_calculator.py`.

**v1 concrete tool rates** (constants in `tool_pricing.py`):

```python
_FLAT_RATES: dict[str, Decimal] = {
    "duckduckgo": Decimal("0"),
    "serper":     Decimal("0.0003"),
    "tavily":     Decimal("0.008"),
    "firecrawl":  Decimal("0.002"),
    "jina":       Decimal("0.001"),
    "crawl4ai":   Decimal("0"),
}
```

**Reasoning tokens** (Anthropic extended thinking) are billed at the output-token rate on the parent `llm_call`. The `thinking` items themselves carry no cost — cost is aggregated onto the `llm_call`.

**Upgrade path:** a future `register_tool_cost_estimator(provider, strategy)` hook adds metered parsers without changing the public API. Out of scope for v1.

### 4.6 Typed contracts

**Source of truth: hand-written Pydantic on the backend.** Hand-written TypeScript mirrors on the frontend. Discriminated unions on both sides.

Backend files:
- `server/api/src/ai_portal/chat/items.py` — `ThreadItem` union + one class per kind.
- `server/api/src/ai_portal/chat/sse.py` — `SseEvent` envelope: `{ event_type: "item" | "error" | "done", item, error, done }`.
- `server/api/src/ai_portal/catalog/providers/events.py` — `ProviderStreamEvent` typed discriminated union (replaces the current `dict` event shape).
- Tool provider return type: `ToolCallOutcome` pydantic model.

Frontend file:
- `apps/frontend/src/lib/chat-types.ts` — mirror TypeScript types.

**CLAUDE.md enforcement rule** (added to project CLAUDE.md):

> **Chat types stay in sync.** When you change any Pydantic model in `server/api/src/ai_portal/chat/items.py`, `chat/sse.py`, or `catalog/providers/events.py` (add/rename/remove a field or a kind), you MUST also update the corresponding TypeScript type in `apps/frontend/src/lib/chat-types.ts` in the same commit. A CI check reads `ItemKind` literals from Python and from the TS union and fails the build on mismatch. No dual-tree drift.

## 5. Streaming service decomposition

Today's `streaming_service.py` (1066 LOC) is replaced by a package `chat/streaming/` with one responsibility per file.

```
chat/
  router.py                          # HTTP surface (existing, trimmed)
  schemas.py                         # request/response
  model.py                           # ThreadItem SQLAlchemy model
  items.py                           # Pydantic discriminated union (4.6)
  sse.py                             # SseEvent envelope
  repository.py                      # CRUD for threads + thread_items
  cost_calculator.py                 # isolated cost module (4.5)
  llm_pricing.py
  tool_pricing.py
  tool_service.py                    # wraps tool dispatch, returns ToolCallOutcome

  streaming/
    orchestrator.py      ~150 LOC   # public entry; the only function router calls
    turn_gate.py         ~80 LOC    # quota + RBAC (model, tool, capability) pre-flight
    turn_setup.py        ~100 LOC   # user_message item + attachments + regenerate path
    context_assembler.py ~120 LOC   # reads thread_items → provider message list
    system_prompt.py     ~60 LOC    # composes system prompt
    iteration_loop.py    ~220 LOC   # LLM call → tool dispatch → repeat; yields SseEvents
    item_writer.py       ~150 LOC   # state-machine transitions (the only writer)
    sse_emitter.py       ~40 LOC    # typed SseEvent → SSE line encoder
    error_handler.py     ~80 LOC    # provider-exception → ErrorItem → friendly text
    cancellation.py      ~60 LOC    # cancel token wiring; batch-flip to cancelled
```

### 5.1 Module contracts

- **`orchestrator.stream_turn(db, user, thread_id, body) -> StreamingResponse`** — public entry. Calls `turn_gate.evaluate`, `turn_setup.start_or_regenerate`, returns `StreamingResponse(iteration_loop.run(...))`. Fits on one screen.
- **`turn_gate.evaluate(...) -> GateResult`** — runs quota + RBAC checks. Throws `HTTPException` on block. Returns `(allowed_tools, allowed_capabilities, effective_model)`. Pure pre-flight.
- **`turn_setup.start_or_regenerate(...) -> Turn`** — creates or regenerates. Returns `Turn(turn_id, user_message_item, effective_model)`. Handles attachment text expansion.
- **`context_assembler.build_provider_messages(...) -> list[ProviderMessage]`** — reads prior `thread_items`, reconstructs `[{role, content, tool_calls}]` the provider expects. Applies window slicing + system prompt + memory block.
- **`system_prompt.compose(...) -> str`** — pure function.
- **`iteration_loop.run(...) -> Iterator[SseEvent]`** — the loop. Writes items via `item_writer`, dispatches tools via `tool_service`, yields typed `SseEvent`s. Terminates on no-tool-call or `max_iterations`. Writes `TurnEndItem` and fires background jobs at the end.
- **`item_writer`** — the ONLY module that writes to `thread_items`. State-machine methods raise `IllegalTransition` on invalid moves:
  - `start_llm_call`, `finish_llm_call`, `fail_llm_call`
  - `append_text_delta`, `finalize_text`
  - `start_tool_call`, `finish_tool_call`
  - `cancel_turn_items`, `sweep_stale`
- **`sse_emitter.encode(event) -> str`** — trivial; `SseEvent.model_dump_json()` wrapped in `data: …\n\n`.
- **`error_handler.handle_stream_error(...)`** — maps provider exceptions, writes `ErrorItem` + `TurnEndItem` via writer, yields trailing SSE.
- **`cancellation.cancel_turn(turn_id)`** — public cancel endpoint handler; trips provider token, calls `item_writer.cancel_turn_items`.

### 5.2 Testability

Pure functions (`turn_gate`, `turn_setup`, `context_assembler`, `system_prompt`, `cost_calculator`, `sse_emitter`) unit-tested with fixtures. `item_writer` tested with a real test DB asserting transitions. `iteration_loop` tested with a fake `ChatProvider` yielding scripted `ProviderStreamEvent`s; asserts `SseEvent` sequence and `thread_items` rows. `orchestrator` gets one happy-path integration test. Existing E2E tests continue to run against `stream_turn` via the router.

## 6. Consumption page

### 6.1 Admin Consumption (`apps/frontend/src/routes/org/consumption.tsx`)

Vortex design-system layout. Polls every 30s.

- **KPI strip (4 cards):** month spend · messages streamed · tool calls · top model by spend.
- **Trend charts (last 90d):** spend-over-time (area, stacked by `kind`); token-volume-over-time.
- **Grouped tables (tabbed):** Model · User · Provider · Capability · Tool. Columns: messages, tokens, cost, % estimated. Sortable, paginated, period filter.
- **Per-conversation drilldown:** thread list filtered by period → click thread → timeline view rendering ordered `thread_items` as vertically-stacked step cards (kind icon, provider chip, cost chip, latency, tokens, params preview).

Backend endpoints under `/api/admin/consumption/*`:

| endpoint                                      | response                                                |
|-----------------------------------------------|---------------------------------------------------------|
| `GET /summary?start=&end=`                    | KPIs + grouped rows                                     |
| `GET /trend?start=&end=&grain=day\|hour&by=kind\|provider` | time series                              |
| `GET /threads?start=&end=&user_id=&model=`    | paginated threads with per-thread cost total            |
| `GET /threads/:id/timeline`                   | full ordered `thread_items` for one thread              |

Existing `/api/admin/usage/*` endpoints kept during transition, marked deprecated.

### 6.2 "My usage" page (`apps/frontend/src/routes/settings/usage.tsx`)

Minimal: two KPI cards (cost this month, messages this month) + quota progress bar. Reads existing `/api/admin/usage/my`.

## 7. Migration

One Alembic migration `20XX_thread_items_rework.py`. Destructive; maintenance-window cutover.

### 7.1 Up

1. Rename `chat_conversations` → `threads`.
2. Create `thread_items` with all columns, indexes, CHECK constraints, RLS policies.
3. **Backfill** (Python function called from the migration):
   - For each `chat_messages` row in order:
     - **User row** → one `user_message` ThreadItem. Generate `turn_id = uuid4()`. Record the mapping `{msg_id → turn_id}` for the next assistant row.
     - **Assistant row** → use the preceding turn_id. Derive multiple items from `content` + `extra`:
       - `extra.stream_items[kind='memory']` → `MemoryPillItem` (done).
       - `extra.stream_items[kind in {'web_search','fetch_webpage','kb_search','tool_call'}]` → `ToolCallItem` (done, cost from flat fallback table, `cost_estimated=True`, provider from `stream_item.provider` if present).
       - `extra.thinking` (if present) → `ThinkingItem` (done).
       - `content` (non-empty text) → `AssistantTextItem` (done).
       - `extra.citations` → `CitationItem`(s) with `parent_item_id` pointing to the derived `tool_call` when matchable, else NULL.
       - Joined `message_usage` row → `LlmCallItem` (done) with tokens + original `cost_usd`; `iteration_index=0` (historical per-iteration data is lost).
       - Terminal `TurnEndItem` (done, `reason="done"`).
   - Timestamp spacing: base on `chat_messages.created_at`; bump by +1µs per item in the derived order to preserve sequence.
4. Drop `chat_messages`, `message_usage`.

### 7.2 Down

Not reversible. Take `pg_dump` before applying in prod.

### 7.3 Frontend

Chat renderer rewritten in the same PR. Reads `thread_items` directly; groups by `turn_id`; renders one component per `kind`. Old `ChatMessage`-based components deleted. `ConversationInspectorPanel`, `MessageUsageBadge`, `QuotaBanner` adapted to the new shape.

E2E tests: selectors updated where DOM changed. Helper signatures (`createOrFindConversation`, `createOrFindKb`) unchanged. Test DB isolation rules unchanged.

## 8. Risks

- **Migration backfill bugs** silently corrupt historical conversations. Mitigated by: dry-run on a worktree DB first; checksum comparison (sum of `input_tokens` across old `message_usage` vs new `llm_call` items must match); full pg_dump before cutover.
- **Frontend rewrite scope** larger than usual; a single PR touches the renderer, inspector, badges, and composer. Mitigated by: build the backend + types + migration first and verify with E2E; then tackle the UI on top of a stable API.
- **Hand-written TS drift** without a codegen pipeline. Mitigated by the CLAUDE.md rule + a CI alignment check that reads kinds from both sides and diffs.
- **Per-provider cost signals** may be absent or inconsistent — v1 accepts this and flags everything from the flat table as `estimated=True`.

## 9. Success criteria

- Every SSE event the client receives has a matching `thread_items` row with the same `id`.
- `SELECT SUM(cost_usd) FROM thread_items WHERE org_id=?` returns total spend to 6-decimal precision; matches Stripe/provider invoices within 1% when sampled.
- Existing E2E test suite passes.
- Admin Consumption page renders a 90-day trend + per-conversation timeline in under 2s (p95) for an org with 10k threads.
- `streaming_service.py` is deleted; its successors each sit under 250 LOC.

## 10. Verification

Rules for the implementation pass:

- **E2E tests run only at the very end.** No per-step E2E runs during implementation. The final step of the plan is one consolidated E2E pass that covers the full reworked flow (chat streaming, thread persistence, consumption page, migration smoke).
- **Correct failing E2E tests in that final pass** — update selectors/assertions to match the new DOM + API shapes. Helper signatures (`createOrFindConversation`, `createOrFindKb`) stay stable.
- **Backend must start cleanly** after every implementation step: `uvicorn` boots without import errors, no missing-model migration warnings.
- **Alembic migrations must be in sync** with SQLAlchemy models at every commit: `alembic check` (or equivalent `--autogenerate` dry-run) reports no diff. The thread_items migration is the only structural change; any subsequent model tweak requires a follow-up migration in the same commit.
- **Unit tests** for pure modules (`cost_calculator`, `system_prompt`, `context_assembler`, `sse_emitter`) run throughout as they're the fast feedback loop.
- **Pre-merge gate:** backend unit tests + frontend type-check + full E2E suite green.

## 11. Open questions

_(None at spec close; all clarifiers resolved during brainstorming.)_
