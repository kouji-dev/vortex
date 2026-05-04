# Assistants & Multi-Agent Orchestration — Design Spec

**Date:** 2026-05-04
**Status:** Draft, pending review
**Owner:** Kouji

## Problem

The current `assistants` module is inert: assistants are stored (with `name`, `description`, `system_prompt`, `visibility`) and conversations carry an `assistant_id`, but the chat orchestrator never loads the assistant's `system_prompt` (`server/api/src/ai_portal/chat/streaming/orchestrator.py:104` passes `assistant_prompt=None`). There is no frontend management UI, no composer attachment, and no way to bind tools or knowledge bases to an assistant.

The product goal is bigger than fixing the bug: an **assistant** should be a domain expert with bound knowledge and bound tools, attachable to a conversation. Multiple assistants can be attached, and a built-in orchestrator dispatches user messages to the right expert(s), supporting sequencing, parallelism, and recursion within static budgets.

## Non-goals

- Code-defined agent graphs (LangGraph-style fixed topologies) — orchestration is LLM-decided.
- Per-message or per-conversation runtime overrides of orchestration limits — limits are static backend constants for v1.
- Peer-to-peer assistant delegation — only the orchestrator can dispatch (star topology).
- LangGraph or any external graph framework — own implementation, ~200 LOC of glue on top of a refactored iteration engine.
- Cross-organization assistant sharing.

## Architecture

### Concepts

- **Assistant** — domain expert: `name`, `description` (skill-style trigger), `system_prompt`, bound `tool_names`, bound `kb_ids`, optional `default_model`, `visibility` (`private` | `org`), per-user ACL. Stateless leaf worker.
- **Orchestrator** — built-in skill auto-loaded when ≥1 assistant is attached to a conversation. LLM-driven dispatcher with a single tool: `call_assistant(name, query)`.
- **Run** — one user-turn execution unit. Bound by `RunLimits`: `max_iter`, `max_wall_time_s`, `max_assistant_calls`, `max_recursion_depth`.
- **Node** — one step in the run's tree (`orchestrator_iteration`, `assistant_call`, `assistant_iteration`, `tool_call`). Persisted with retry/timeout state and final result.

### Topology

Star: orchestrator is the sole decision-maker. Assistants are pure leaves — they run their own bounded sub-loop using only their bound tools and bound KBs. They cannot call other assistants. Sequencing/parallelism/recursion all happen at the orchestrator level via native LLM tool-calling (multiple `tool_use` blocks in one response = parallel; multiple iteration rounds = sequence; same assistant called again later = loop).

### Engine refactor

The current `chat/streaming/iteration_loop.py` cannot be reused as-is because:

1. It accumulates a single `tool_request` per iteration; if a provider emits multiple `tool_use` blocks, only the last is kept. This breaks orchestrator parallelism.
2. Tool dispatch is hardcoded to the global `dispatch_tool` and global registry — no scoping for "this loop's allowed tools".
3. `ItemWriter` writes only to `thread_items` — no abstraction for nested orchestration nodes.
4. Cost, citations, cancellation, server tools mixed inline; hard to compose.

**New module `server/api/src/ai_portal/core/llm_loop/`:**

```
engine.py       LLMIterationEngine — generic, ~150 LOC
protocols.py    ToolDispatcher, EventSink (typing.Protocol)
parallel.py     Multi-tool-use-per-iteration via asyncio.gather
limits.py       RunLimits dataclass, BudgetTracker, TimeoutGuard
errors.py       IterationLimitExceeded, RecursionDepthExceeded, NodeTimeoutError
```

**Engine contract:**

```python
class LLMIterationEngine:
    async def run(
        *,
        provider: Provider,
        model: str,
        system_prompt: str,
        messages: list[dict],
        tool_schemas: list[dict],
        tool_dispatcher: ToolDispatcher,   # plug
        event_sink: EventSink,             # plug
        limits: RunLimits,
        budget: BudgetTracker,             # tracks across nested loops
        cancel_token: CancelToken | None = None,
    ) -> AsyncIterator[EngineEvent]: ...
```

The engine parses **all** `tool_use` blocks in a provider response, dispatches them concurrently via `asyncio.gather`, and appends every `tool_result` before the next iteration.

The existing chat path becomes a thin wrapper: build chat-tool dispatcher + `ThreadItemEventSink`, call the engine. ~50 LOC.

### Orchestration layer

**New module `server/api/src/ai_portal/orchestration/`:**

```
models.py              SQLAlchemy: OrchestrationRun, OrchestrationNode
schemas.py             Pydantic in/out
service.py             OrchestrationService — entry point from chat router
orchestrator_loop.py   Engine config: only call_assistant tool
assistant_loop.py      Engine config: assistant's bound tools/KBs
call_assistant_tool.py The orchestrator's only tool
prompts.py             Orchestrator system prompt (caveman style)
limits.py              Static defaults (CHAT_LIMITS, ORCH_LIMITS, ASSIST_LIMITS)
retry.py               Per-node retry policy
```

**Static defaults:**

```python
ORCH_LIMITS    = RunLimits(max_iter=6, max_wall_time_s=120, max_assistant_calls=8, max_recursion_depth=2)
ASSIST_LIMITS  = RunLimits(max_iter=5, max_wall_time_s=60)
NODE_RETRY     = RetryPolicy(max_attempts=2, backoff_s=[1, 3])  # transient errors only
NODE_TIMEOUT_S = 60
```

**Turn flow with attached assistants:**

```
chat router
  └─ if conversation_assistants exists for this conv:
       └─ OrchestrationService.run_turn(...)
            ├─ creates OrchestrationRun row
            ├─ orchestrator_loop.run() (engine + call_assistant tool)
            │    ↳ engine emits tool_use("call_assistant", name=X, query=...)
            │       └─ dispatcher creates OrchestrationNode (kind=assistant_call, status=pending)
            │       └─ assistant_loop.run() with X's prompt + bound tools + bound KBs
            │            ↳ on success → node.status=ok, node.result=text
            │            ↳ on transient fail → retry per NODE_RETRY
            │            ↳ on timeout/max-fail → node.status=failed, return error string
            │       └─ orchestrator integrates result; may call again
            └─ final assistant_text → flushed to chat ThreadItems
       └─ else: existing chat loop (no orchestration overhead)
```

**Orchestrator system prompt (caveman style):**

```
You orchestrate domain experts. Tools: call_assistant(name, query).
- Read user message + assistant descriptions.
- Call experts whose description matches. Multiple in one round = parallel.
- Same expert again later = follow-up. Different experts in sequence = pipeline.
- Read each result. Decide: more calls, or final answer.
- Stop when answered. No expert needed for trivial → answer directly.
```

**Per-assistant invocation isolation:** each `call_assistant` opens a fresh `assistant_loop.run()` with depth+1, inherited wall-time, scoped `tool_dispatcher` (only the assistant's bound tools), and a `NodeEventSink` writing to `orchestration_nodes`. The user-visible `thread_items` stream gets one `assistant_call` item per top-level invocation; the rest is in the orchestration tables.

### Data model

**Migration 1 — orchestration tables:**

```
orchestration_runs
  id: UUID PK
  conversation_id: UUID FK → conversations.id
  turn_id: UUID FK
  org_id: UUID FK → orgs.id (RLS)
  status: ENUM("running","completed","failed","cancelled","timed_out")
  limits_json: JSONB                  -- snapshot of RunLimits used
  total_assistant_calls: int
  total_iterations: int
  total_cost_usd: NUMERIC(12,6)
  started_at, finished_at: timestamptz
  error: TEXT NULL

orchestration_nodes
  id: UUID PK
  run_id: UUID FK → orchestration_runs.id (CASCADE)
  parent_node_id: UUID FK NULL → orchestration_nodes.id
  kind: ENUM("orchestrator_iteration","assistant_call","assistant_iteration","tool_call")
  assistant_id: int FK NULL → assistants.id
  depth: int
  sequence_index: int
  status: ENUM("pending","running","ok","failed","timed_out","cancelled","retrying")
  attempt: int
  input_json: JSONB
  output_json: JSONB
  error: TEXT NULL
  input_tokens, output_tokens: int
  cost_usd: NUMERIC(12,6)
  latency_ms: int
  started_at, finished_at: timestamptz
  INDEX (run_id, parent_node_id), INDEX (assistant_id)
```

RLS on both tables uses the same pattern as `thread_items` — gated by `org_id` from session.

**Migration 2 — assistants upgrades + many-to-many:**

```
ALTER TABLE assistants ADD COLUMN
  tool_names    JSONB DEFAULT '[]',     -- subset of tool registry
  kb_ids        JSONB DEFAULT '[]',     -- subset of org KBs
  default_model VARCHAR(255) NULL,
  icon          VARCHAR(64) DEFAULT '';

CREATE TABLE conversation_assistants (
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  assistant_id    INT  NOT NULL REFERENCES assistants(id)    ON DELETE CASCADE,
  position        INT  NOT NULL DEFAULT 0,
  PRIMARY KEY (conversation_id, assistant_id)
);

-- Backfill from the deprecated single column
INSERT INTO conversation_assistants (conversation_id, assistant_id, position)
SELECT id, assistant_id, 0 FROM conversations WHERE assistant_id IS NOT NULL;

ALTER TABLE conversations DROP COLUMN assistant_id;
```

**Migration 3 — link thread items to runs:**

```
ALTER TABLE thread_items ADD COLUMN
  orchestration_run_id UUID NULL REFERENCES orchestration_runs(id);
```

For `assistant_call` thread items, `data.orchestration_node_id` references the specific node so the frontend can lazy-load the subtree.

### Backend API

**Existing assistants CRUD stays; add the missing DELETE.**

```
GET    /api/assistants                                          (existing)
POST   /api/assistants                                          (existing — add tool_names/kb_ids/default_model/icon to body)
GET    /api/assistants/{id}                                     (existing)
PATCH  /api/assistants/{id}                                     (existing — same body extension)
DELETE /api/assistants/{id}                                     NEW

POST   /api/conversations/{id}/assistants                       NEW — body: {assistant_ids: int[]}
DELETE /api/conversations/{id}/assistants/{assistant_id}        NEW
PATCH  /api/conversations/{id}/assistants/reorder               NEW — body: {ordered_ids: int[]}

GET    /api/orchestration/runs/{run_id}                         NEW
GET    /api/orchestration/nodes/{node_id}                       NEW

GET    /api/tools/registry                                      NEW — for AssistantToolPicker
```

### Frontend

**Routes (`apps/frontend/src/routes/`):**

```
assistants/
  route.tsx     (list)
  $id.tsx       (edit)
  new.tsx       (create)
```

**Components (`apps/frontend/src/components/`):**

```
assistants/
  AssistantsListPage.tsx
  AssistantEditor.tsx          name, description, system_prompt, icon, default_model
  AssistantToolPicker.tsx      multiselect from /api/tools/registry
  AssistantKbPicker.tsx        multiselect from org KBs
  AssistantVisibilityToggle.tsx
  AssistantCard.tsx            reusable in lists, composer chips, header
chat/
  composer/
    AssistantAttachmentPicker.tsx
  items/
    AssistantCallItem.tsx      collapsible card
  ConversationAssistantsBar.tsx
hooks/
  useAssistants.ts
  useConversationAssistants.ts
  useOrchestrationNode.ts
```

**SSE / item kinds — CLAUDE.md non-negotiable: Python and TS updated in the same commit:**

New kind `assistant_call`. Payload:

```ts
{
  kind: "assistant_call";
  data: {
    assistant_id: number;
    assistant_name: string;
    orchestration_node_id: string;
    query: string;
    result_snippet: string;        // first 200 chars
    status: "running" | "ok" | "failed" | "timed_out";
    iterations: number;
    cost_usd: string;
    latency_ms: number;
  };
}
```

The card is collapsible. Click → `useOrchestrationNode` lazy-loads the subtree and renders the assistant's internal tool calls and intermediate text.

**Composer behavior:** new "Assistants" button next to the model picker opens `AssistantAttachmentPicker`. Attached assistants render as removable chips above the textarea. Reflection/Research toggles remain available — when assistants are attached they pass into the orchestrator's prompt as hints, not into assistants (assistants own their tools).

**Thread view:** `ConversationAssistantsBar` chips at the top of the thread (read-only, click → opens picker). For each turn that triggered orchestration, `AssistantCallItem` cards render inline before the final `assistant_text`.

**Design v2 alignment:** Tailwind utilities + existing system classes (`.panel`, `.pill`, `.btn`); no hardcoded colors; light/dark via `data-theme`. Per CLAUDE.md.

### Limits, retry, timeout

- Limits are static constants in `orchestration/limits.py` for v1. Snapshotted into `orchestration_runs.limits_json` at run start so a future move to dynamic config is non-breaking for stored data.
- `BudgetTracker` is shared across the run tree. Each nested loop deducts from the same wall-clock budget; recursion depth is enforced inline.
- `RetryPolicy.max_attempts=2` with backoff `[1s, 3s]`, applied only to transient errors (provider 5xx, network). Non-transient errors (validation, auth, missing tool) fail the node immediately.
- Per-node timeout `NODE_TIMEOUT_S=60`. Exceeding → node `status=timed_out`, error logged, control returns to orchestrator which may try a different assistant or finalize.

## Failure modes

| Failure | Behavior |
|---|---|
| Orchestrator hits `max_iter` | Run `status=failed`, error="iteration limit"; flush whatever assistant_text was last produced or a generic "couldn't complete" message |
| Run hits `max_wall_time_s` | Same as above with `status=timed_out` |
| Single node timeout | Node `status=timed_out`; orchestrator sees error string, can route around |
| Transient provider error | Retry per `NODE_RETRY` |
| Non-transient error in assistant sub-loop | Node `status=failed`; orchestrator sees error string |
| Cancellation token tripped | All in-flight nodes set to `cancelled`; run `status=cancelled` |
| `max_recursion_depth` hit | Engine raises `RecursionDepthExceeded`; node fails; orchestrator continues |
| `max_assistant_calls` hit | Further `call_assistant` invocations rejected at dispatcher; orchestrator must finalize |

## Testing

**Backend (`server/api/tests/`):**

```
unit/
  core/llm_loop/
    test_engine.py
    test_parallel.py
    test_limits.py
  orchestration/
    test_orchestrator_loop.py
    test_assistant_loop.py
    test_call_assistant_tool.py
    test_retry.py
    test_persistence.py
integration/
  test_chat_with_assistants.py
  test_orchestration_api.py
  test_assistant_crud.py
  test_concurrent_assistant_calls.py
```

**Frontend Playwright (`apps/frontend/e2e/specs/`):**

```
assistants-crud.spec.ts
conversation-assistants.spec.ts
orchestration-single.spec.ts
orchestration-parallel.spec.ts
orchestration-sequence.spec.ts
orchestration-failure.spec.ts
orchestration-timeout.spec.ts
orchestration-card-expand.spec.ts
```

E2E pattern per CLAUDE.md: all interactions through browser UI; mock SSE via `page.route()` for deterministic orchestration tests; use `createOrFindConversation` helpers; run against E2E DB on port 8001/5435 via `./scripts/e2e-up.sh`.

## Migrations execution

```
1. alembic -c server/api/alembic.ini revision --autogenerate -m "orchestration_runs_nodes"
2. alembic -c server/api/alembic.ini revision --autogenerate -m "assistants_tools_kbs_join"
3. alembic -c server/api/alembic.ini revision --autogenerate -m "thread_items_orchestration_link"
4. Hand-edit autogen output for the conversation_assistants backfill SQL.
5. Local: alembic upgrade head
6. E2E:   ./scripts/e2e-up.sh   (resets E2E DB + reruns migrations)
```

## Rollout phases

| Phase | Scope | Ships green when |
|---|---|---|
| 1 | Engine refactor + multi-tool-use-per-iteration fix + apply assistant `system_prompt` to chat | unit tests + existing chat E2Es green |
| 2 | Assistant model upgrades (`tool_names`, `kb_ids`, `default_model`, `icon`) + `DELETE /api/assistants/{id}` + frontend `/assistants` CRUD page | `assistants-crud.spec` green |
| 3 | Many-to-many migration + attach/detach API + composer attachment picker | `conversation-assistants.spec` green |
| 4 | Orchestration tables + service + orchestrator/assistant loops + chat router integration | `orchestration-single` + `orchestration-parallel` + `orchestration-sequence` green |
| 5 | Retry/timeout/failure handling + node inspector card expansion | `orchestration-failure` + `orchestration-timeout` + `orchestration-card-expand` green |

Each phase is a separate PR. The Phase 1 engine refactor is invisible to users but immediately fixes the existing single-assistant `system_prompt` bug as a side effect.

## Risks

- **Cost runaway** — bounded by `max_assistant_calls`, `max_iter`, `max_wall_time`, `max_recursion`. Every node logs cost; run rejects further invocations once budget exhausted.
- **Provider variance in `tool_use` block parsing** — engine uses provider-agnostic `tool_use[]` extraction; per-provider integration tests in Phase 1.
- **Long SSE streams** — per-node timeout + run-level wall-time cap force clean failure rendering rather than indefinite hangs.
- **Migration backfill** — `conversations.assistant_id` → join table is single-statement; safe even with concurrent writes since the column drop runs in the same transaction.
- **Recursion depth confusion** — depth is enforced on the orchestration tree, not on LLM call counts; documented in `engine.py` to avoid future ambiguity.
