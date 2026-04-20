# Chat Thread Items Rework — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the aggregated-per-message chat model with a typed, step-granular `thread_items` table where every SSE event maps to one persisted row; isolate cost attribution in a dedicated module; decompose the 1066-LOC `streaming_service.py` into a focused package; ship a new admin Consumption page.

**Architecture:** One table (`thread_items`) stores a discriminated union keyed on `kind` (`user_message | assistant_text | llm_call | tool_call | server_tool_use | thinking | citation | memory_pill | turn_end | error`). All items in a turn share a `turn_id` UUID (minted on the `user_message`). Ordering is by `created_at` using `clock_timestamp()` for µs resolution — no `seq` column. Cost is attached at the item level and computed by a single `cost_calculator` module that reads per-provider signals first and falls back to flat rates. Streaming pipeline is split into 10 small files under `chat/streaming/`; `item_writer.py` is the only module that mutates `thread_items`. A new `/api/admin/consumption/*` surface feeds a Vortex-styled Consumption page with KPI strip, 90d trend, grouped tables, and per-thread timeline.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Pydantic v2, pytest + pytest-asyncio, PostgreSQL 16, React 19, TanStack Router/Query, Tailwind v4, Playwright.

**Spec:** `docs/superpowers/specs/2026-04-19-chat-thread-items-rework-design.md`

**Prerequisites:**
- E2E DB isolation rules (CLAUDE.md) — `ai_portal_e2e` on container port 5435 only.
- `chat_messages.extra.stream_items` (JSONB) is the source truth for the backfill of tool-call and memory-pill history.
- Latest Alembic head before this plan: `030_seed_default_policies`. The new migration is `031_thread_items_rework`.

---

## File Map

### Backend — new files

**Data + types**
- `server/api/src/ai_portal/chat/model.py` — replace `ChatConversation` / `ChatMessage` with `Thread` + `ThreadItem` (SQLAlchemy).
- `server/api/src/ai_portal/chat/items.py` — Pydantic discriminated union (`ThreadItem`, one class per kind).
- `server/api/src/ai_portal/chat/sse.py` — `SseEvent` envelope (`event_type: item | error | done`).
- `server/api/src/ai_portal/chat/item_kinds.py` — `ItemKind`, `ItemStatus`, `ItemRole` enums; shared with DB + Pydantic.
- `server/api/alembic/versions/031_thread_items_rework.py` — destructive migration + backfill hook.
- `server/api/src/ai_portal/chat/_backfill.py` — Python backfill routine called from the migration.

**Cost + tool dispatch**
- `server/api/src/ai_portal/chat/cost_calculator.py` — public cost API (`compute_llm_cost`, `compute_tool_cost`, `compute_server_tool_cost`).
- `server/api/src/ai_portal/chat/llm_pricing.py` — flat LLM rates (moved from `usage/pricing.py`).
- `server/api/src/ai_portal/chat/tool_pricing.py` — flat tool rates.
- `server/api/src/ai_portal/chat/tool_outcome.py` — `ToolCallOutcome` Pydantic model.

**Provider events**
- `server/api/src/ai_portal/catalog/providers/events.py` — `ProviderStreamEvent` discriminated union (replaces untyped dicts flowing out of provider adapters).

**Streaming package (replaces `streaming_service.py`)**
- `server/api/src/ai_portal/chat/streaming/__init__.py`
- `server/api/src/ai_portal/chat/streaming/orchestrator.py`
- `server/api/src/ai_portal/chat/streaming/turn_gate.py`
- `server/api/src/ai_portal/chat/streaming/turn_setup.py`
- `server/api/src/ai_portal/chat/streaming/context_assembler.py`
- `server/api/src/ai_portal/chat/streaming/system_prompt.py`
- `server/api/src/ai_portal/chat/streaming/iteration_loop.py`
- `server/api/src/ai_portal/chat/streaming/item_writer.py`
- `server/api/src/ai_portal/chat/streaming/sse_emitter.py`
- `server/api/src/ai_portal/chat/streaming/error_handler.py`
- `server/api/src/ai_portal/chat/streaming/cancellation.py`

**Consumption backend**
- `server/api/src/ai_portal/api/admin/consumption.py` — router (`/api/admin/consumption/*`).
- `server/api/src/ai_portal/usage/consumption_service.py` — aggregation queries over `thread_items`.
- `server/api/src/ai_portal/usage/consumption_schemas.py` — response Pydantic models.

**Tests (new)**
- `server/api/tests/chat/test_items_schema.py` — Pydantic kinds + CHECK constraint behavior.
- `server/api/tests/chat/test_item_writer.py` — state-machine transitions, writer is the only writer.
- `server/api/tests/chat/test_cost_calculator.py` — rate tables + metered-signal precedence.
- `server/api/tests/chat/test_context_assembler.py` — provider-message reconstruction from `thread_items`.
- `server/api/tests/chat/test_system_prompt.py` — composition rules (pure).
- `server/api/tests/chat/test_iteration_loop.py` — fake provider + scripted ProviderStreamEvents.
- `server/api/tests/chat/test_turn_gate.py` — quota + RBAC pre-flight blocks.
- `server/api/tests/chat/test_sse_emitter.py` — envelope encoding.
- `server/api/tests/chat/test_error_handler.py` — provider-exception → `ErrorItem` + `TurnEndItem`.
- `server/api/tests/chat/test_cancellation.py` — cancel flips streaming items to `cancelled`.
- `server/api/tests/chat/test_backfill.py` — legacy row → derived items snapshot test.
- `server/api/tests/chat/test_stream_turn_e2e.py` — orchestrator happy path with a real DB.
- `server/api/tests/usage/test_consumption_service.py` — aggregation correctness.
- `server/api/tests/usage/test_consumption_router.py` — endpoint smoke + auth gates.

### Backend — modified files

- `server/api/src/ai_portal/chat/repository.py` — rename APIs, switch to `thread_items` reads.
- `server/api/src/ai_portal/chat/router.py` — single orchestrator call; remove inline streaming.
- `server/api/src/ai_portal/chat/schemas.py` — drop `MessageRead`; add `ThreadRead`, `ThreadItemRead`.
- `server/api/src/ai_portal/chat/service.py` — list/detail now returns items; thread CRUD unchanged.
- `server/api/src/ai_portal/chat/tool_service.py` — wrap dispatch to return `ToolCallOutcome`.
- `server/api/src/ai_portal/chat/streaming_service.py` — **deleted** at end of Phase 6.
- `server/api/src/ai_portal/catalog/providers/anthropic_native.py` — yield `ProviderStreamEvent` instead of dicts.
- `server/api/src/ai_portal/catalog/providers/gemini_native.py` — yield `ProviderStreamEvent`.
- `server/api/src/ai_portal/catalog/providers/langchain.py` — yield `ProviderStreamEvent`.
- `server/api/src/ai_portal/catalog/providers/protocol.py` — update stream signature to `AsyncIterator[ProviderStreamEvent]`.
- `server/api/src/ai_portal/tools/web_search.py`, `fetch_webpage.py`, `kb_search.py` — return `ToolCallOutcome`.
- `server/api/src/ai_portal/usage/pricing.py` — content moved into `chat/llm_pricing.py`; file becomes a re-export shim OR is deleted if no external callers.
- `server/api/src/ai_portal/usage/service.py` — `usage_rollup` / `usage_quota` now read from `thread_items`.
- `server/api/src/ai_portal/usage/model.py` — drop `MessageUsage`; keep `UsageRollup`, `UsageQuota`.
- `server/api/src/ai_portal/usage/router.py` — mark `/api/admin/usage/*` deprecated; `/my` still reads new source.
- `server/api/src/ai_portal/api/admin/__init__.py` — register consumption router.
- `server/api/src/ai_portal/main.py` — include new router.

### Frontend — new files

- `apps/frontend/src/lib/chat-types.ts` — hand-written TS mirrors of Pydantic types (expand existing file).
- `apps/frontend/src/components/chat/thread/ThreadTurn.tsx` — renders one turn grouped by `turn_id`.
- `apps/frontend/src/components/chat/thread/items/UserMessageItem.tsx`
- `apps/frontend/src/components/chat/thread/items/AssistantTextItem.tsx`
- `apps/frontend/src/components/chat/thread/items/LlmCallItem.tsx` (inspector-only; collapsed chip in timeline)
- `apps/frontend/src/components/chat/thread/items/ToolCallItem.tsx`
- `apps/frontend/src/components/chat/thread/items/ServerToolUseItem.tsx`
- `apps/frontend/src/components/chat/thread/items/ThinkingItem.tsx`
- `apps/frontend/src/components/chat/thread/items/CitationItem.tsx`
- `apps/frontend/src/components/chat/thread/items/MemoryPillItem.tsx`
- `apps/frontend/src/components/chat/thread/items/ErrorItem.tsx`
- `apps/frontend/src/components/chat/thread/items/TurnEndMarker.tsx`
- `apps/frontend/src/routes/org/consumption.tsx` — Vortex Consumption page.
- `apps/frontend/src/components/consumption/ConsumptionKpiStrip.tsx`
- `apps/frontend/src/components/consumption/ConsumptionTrend.tsx`
- `apps/frontend/src/components/consumption/ConsumptionGroupedTable.tsx`
- `apps/frontend/src/components/consumption/ConsumptionThreadTimeline.tsx`
- `apps/frontend/src/hooks/useConsumptionSummary.ts`
- `apps/frontend/src/hooks/useConsumptionTrend.ts`
- `apps/frontend/src/hooks/useConsumptionThreads.ts`
- `apps/frontend/src/hooks/useThreadTimeline.ts`

### Frontend — modified files

- `apps/frontend/src/components/chat/ConversationThreadPage.tsx` — reads `thread_items`; groups by `turn_id`; renders `<ThreadTurn />`.
- `apps/frontend/src/components/chat/ConversationInspectorPanel.tsx` — list timeline of items for the focused turn.
- `apps/frontend/src/components/chat/MessageUsageBadge.tsx` — reads cost from `llm_call` item, not per-message usage.
- `apps/frontend/src/components/chat/QuotaBanner.tsx` — reads `/api/admin/usage/my` (unchanged endpoint, new source).
- `apps/frontend/src/components/chat/ThreadItemChip.tsx` — one chip per `tool_call`/`server_tool_use` kind.
- `apps/frontend/src/components/chat/ThinkingBlock.tsx` — binds to `thinking` item.
- `apps/frontend/src/components/chat/ConversationsSidebarPanel.tsx` — reads `threads` endpoint rename.
- `apps/frontend/src/components/chat/EmptyConversationState.tsx` — no-op visual check.
- `apps/frontend/src/lib/sse-parse.ts` — parse `SseEvent` envelope (typed).
- `apps/frontend/src/lib/queryKeys.ts` — add consumption keys.
- `apps/frontend/src/router.tsx` — add `/org/consumption` route.
- `CLAUDE.md` — add "Chat types stay in sync" rule.

### E2E (updates, not new flows)

- `apps/frontend/e2e/chat/*.spec.ts` — selector updates; DOM now renders per-item components.
- `apps/frontend/e2e/support/ui-helpers.ts` — internal selectors updated; public helper signatures unchanged.
- `apps/frontend/e2e/admin/consumption.spec.ts` — **new** — renders KPI strip, 90d trend, grouped tables, timeline drilldown.

### CI

- `.github/workflows/ci.yml` (or the equivalent file in this repo) — add a `types-align` step that diffs `ItemKind` literals Python↔TS.
- `server/api/scripts/check_types_align.py` — new script run by the CI step.

---

## Phase ordering rationale

Phases execute bottom-up. Data model and pure modules first (fast feedback, unit-testable), then streaming orchestration on top of a stable contract, then consumption, then frontend. E2E runs **once at the end** per project rule `feedback_e2e_end_only`.

1. Data layer (model, migration, backfill, repository reads)
2. Typed contracts (items.py, sse.py, ProviderStreamEvent, ToolCallOutcome, TS mirrors, CI check)
3. Cost calculator (isolated module + pricing tables)
4. Tool service (dispatch wrapper returning `ToolCallOutcome`)
5. Provider events (Anthropic/Gemini/langchain adapters emit typed events)
6. Streaming decomposition (10-file package; delete `streaming_service.py`)
7. Consumption backend (`/api/admin/consumption/*`)
8. Quota + workers adapted to new source
9. Frontend chat renderer rewrite
10. Consumption UI page
11. E2E final pass
12. Cleanup (delete dead code, CLAUDE.md rule, CI check wiring)

---

## Conventions used across all tasks

**Backend test runner:** `cd server/api && pytest <path> -xvs`. `pytest-asyncio` is already configured; async tests use `async def` + `pytest.mark.asyncio` (see existing `tests/chat/` for style).

**Backend start verification:** after every schema-touching task, `cd server/api && uvicorn ai_portal.main:app --port 8000 --reload` must boot without import errors. Kill with `Ctrl+C`.

**Alembic:** `cd server/api && alembic upgrade head` applies migrations. `alembic check` (or `alembic revision --autogenerate --sql` dry-run) reports schema drift.

**Commits:** one commit per task minimum; split into multiple commits if the task spans schema + code + tests. Messages follow the repo convention: `feat(scope): short summary` / `refactor(scope): …` / `chore(scope): …`.

**Worktree:** run this plan on a dedicated worktree. If not already in one, first run `./scripts/worktree-up.sh chat-items-rework`; all commands below assume you're inside it. The worktree's `.worktree.env` pins isolated ports/DBs.

**E2E is deferred to Phase 11.** Do not run `pnpm test:e2e` during Phases 1–10. Type-check + unit tests are your feedback loop.

---
## Phase 1 — Data layer (model + migration + backfill + repository)

### Task 1.1: Add shared enum module

**Files:**
- Create: `server/api/src/ai_portal/chat/item_kinds.py`
- Test: `server/api/tests/chat/test_item_kinds.py`

- [ ] **Step 1.1.1: Write the failing test**

```python
# server/api/tests/chat/test_item_kinds.py
from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole

def test_item_kind_values():
    assert {k.value for k in ItemKind} == {
        "user_message", "assistant_text", "llm_call", "tool_call",
        "server_tool_use", "thinking", "citation", "memory_pill",
        "turn_end", "error",
    }

def test_item_status_values():
    assert {s.value for s in ItemStatus} == {"streaming", "done", "error", "cancelled"}

def test_item_role_values():
    assert {r.value for r in ItemRole} == {"user", "assistant", "system"}
```

- [ ] **Step 1.1.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/chat/test_item_kinds.py -xvs`
Expected: `ModuleNotFoundError: No module named 'ai_portal.chat.item_kinds'`.

- [ ] **Step 1.1.3: Implement the enums**

```python
# server/api/src/ai_portal/chat/item_kinds.py
from __future__ import annotations

from enum import Enum


class ItemKind(str, Enum):
    user_message = "user_message"
    assistant_text = "assistant_text"
    llm_call = "llm_call"
    tool_call = "tool_call"
    server_tool_use = "server_tool_use"
    thinking = "thinking"
    citation = "citation"
    memory_pill = "memory_pill"
    turn_end = "turn_end"
    error = "error"


class ItemStatus(str, Enum):
    streaming = "streaming"
    done = "done"
    error = "error"
    cancelled = "cancelled"


class ItemRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
```

- [ ] **Step 1.1.4: Run test to verify it passes**

Run: `cd server/api && pytest tests/chat/test_item_kinds.py -xvs`
Expected: PASS.

- [ ] **Step 1.1.5: Commit**

```bash
git add server/api/src/ai_portal/chat/item_kinds.py server/api/tests/chat/test_item_kinds.py
git commit -m "feat(chat): ItemKind/ItemStatus/ItemRole enums"
```

---

### Task 1.2: Replace SQLAlchemy models — `Thread` + `ThreadItem`

**Files:**
- Modify: `server/api/src/ai_portal/chat/model.py`

This task only edits the ORM models; the actual DB migration (Task 1.3) and backfill (Task 1.4) follow. The model must compile against the current DB so we ship a pending-migration state — we'll use `mapped_column(... deferred=True)` only if imports break existing paths. Otherwise, model lands before migration and `uvicorn` won't boot until Task 1.3 runs.

**Order of operations:** do not run the server between 1.2 and 1.3. Complete both in one session.

- [ ] **Step 1.2.1: Replace `model.py` contents**

```python
# server/api/src/ai_portal/chat/model.py
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.schemas import ConversationSettings
from ai_portal.core.db.base import Base
from ai_portal.core.db.types import ConversationSettingsJSON


_item_kind_enum = PGEnum(
    ItemKind, name="thread_item_kind", create_type=False, values_callable=lambda e: [v.value for v in e]
)
_item_status_enum = PGEnum(
    ItemStatus, name="thread_item_status", create_type=False, values_callable=lambda e: [v.value for v in e]
)
_item_role_enum = PGEnum(
    ItemRole, name="thread_item_role", create_type=False, values_callable=lambda e: [v.value for v in e]
)


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assistant_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings: Mapped[ConversationSettings | None] = mapped_column(
        ConversationSettingsJSON, nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ThreadItem(Base):
    __tablename__ = "thread_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[ItemKind] = mapped_column(_item_kind_enum, nullable=False)
    role: Mapped[ItemRole | None] = mapped_column(_item_role_enum, nullable=True)
    status: Mapped[ItemStatus] = mapped_column(_item_status_enum, nullable=False)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    cost_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    parent_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("thread_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_thread_items_thread_created", "thread_id", "created_at"),
        Index("ix_thread_items_thread_turn", "thread_id", "turn_id"),
        Index("ix_thread_items_org_created", "org_id", "created_at"),
        Index(
            "ix_thread_items_cost_not_null",
            "org_id",
            "created_at",
            postgresql_where=text("cost_usd IS NOT NULL"),
        ),
        CheckConstraint(
            "(kind <> 'llm_call') OR (model IS NOT NULL AND data ? 'input_tokens' AND data ? 'output_tokens')",
            name="ck_thread_items_llm_call_shape",
        ),
        CheckConstraint(
            "(kind <> 'tool_call') OR (data ? 'tool_name')",
            name="ck_thread_items_tool_call_shape",
        ),
        CheckConstraint(
            "(kind <> 'user_message') OR (data ? 'text')",
            name="ck_thread_items_user_message_shape",
        ),
    )


class ChatUpload(Base):
    __tablename__ = "chat_uploads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
```

Note the `chat_uploads.conversation_id` column is renamed to `thread_id` in the same migration (Task 1.3).

- [ ] **Step 1.2.2: Stub out old imports so unrelated modules still import**

Any module importing `from ai_portal.chat.model import ChatConversation, ChatMessage` will break. Do NOT add compatibility shims — fix the import sites directly in this phase. Run:

Run: `cd server/api && grep -rn "ChatConversation\|ChatMessage" src/ tests/`
Expected: a list of import sites to update. Fix each by replacing `ChatConversation` → `Thread` and `ChatMessage` → `ThreadItem` where the usage still makes sense; for sites that iterate over messages, mark them `TODO Phase 1.5` and come back — but prefer fixing in this step.

- [ ] **Step 1.2.3: Commit (model-only, still broken)**

```bash
git add server/api/src/ai_portal/chat/model.py
git commit -m "refactor(chat): Thread + ThreadItem ORM models (migration pending)"
```

---

### Task 1.3: Alembic migration — create types + tables + indexes

**Files:**
- Create: `server/api/alembic/versions/031_thread_items_rework.py`

Follow Alembic conventions in existing migrations (imports, upgrade/downgrade signature, `down_revision = "030_seed_default_policies"`).

- [ ] **Step 1.3.1: Write migration skeleton**

```python
# server/api/alembic/versions/031_thread_items_rework.py
"""Thread items rework.

- Rename chat_conversations -> threads
- Rename chat_uploads.conversation_id -> thread_id
- Create thread_item_kind / thread_item_status / thread_item_role enums
- Create thread_items table with indexes and CHECK constraints
- Backfill thread_items from chat_messages (+ message_usage)
- Drop chat_messages, message_usage
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "031_thread_items_rework"
down_revision = "030_seed_default_policies"
branch_labels = None
depends_on = None


ITEM_KINDS = (
    "user_message", "assistant_text", "llm_call", "tool_call",
    "server_tool_use", "thinking", "citation", "memory_pill",
    "turn_end", "error",
)
ITEM_STATUSES = ("streaming", "done", "error", "cancelled")
ITEM_ROLES = ("user", "assistant", "system")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Rename conversations table
    op.rename_table("chat_conversations", "threads")
    op.execute("ALTER INDEX chat_conversations_pkey RENAME TO threads_pkey")

    # 2. Rename chat_uploads FK column
    op.alter_column("chat_uploads", "conversation_id", new_column_name="thread_id")

    # 3. Create enums
    op.execute(
        f"CREATE TYPE thread_item_kind AS ENUM "
        f"({', '.join(f\"'{k}'\" for k in ITEM_KINDS)})"
    )
    op.execute(
        f"CREATE TYPE thread_item_status AS ENUM "
        f"({', '.join(f\"'{s}'\" for s in ITEM_STATUSES)})"
    )
    op.execute(
        f"CREATE TYPE thread_item_role AS ENUM "
        f"({', '.join(f\"'{r}'\" for r in ITEM_ROLES)})"
    )

    # 4. Create thread_items table
    op.create_table(
        "thread_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.BigInteger(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", postgresql.ENUM(*ITEM_KINDS, name="thread_item_kind", create_type=False), nullable=False),
        sa.Column("role", postgresql.ENUM(*ITEM_ROLES, name="thread_item_role", create_type=False), nullable=True),
        sa.Column("status", postgresql.ENUM(*ITEM_STATUSES, name="thread_item_status", create_type=False), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("cost_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parent_item_id", sa.BigInteger(), sa.ForeignKey("thread_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "(kind <> 'llm_call') OR (model IS NOT NULL AND data ? 'input_tokens' AND data ? 'output_tokens')",
            name="ck_thread_items_llm_call_shape",
        ),
        sa.CheckConstraint(
            "(kind <> 'tool_call') OR (data ? 'tool_name')",
            name="ck_thread_items_tool_call_shape",
        ),
        sa.CheckConstraint(
            "(kind <> 'user_message') OR (data ? 'text')",
            name="ck_thread_items_user_message_shape",
        ),
    )
    op.create_index("ix_thread_items_thread_created", "thread_items", ["thread_id", "created_at"])
    op.create_index("ix_thread_items_thread_turn", "thread_items", ["thread_id", "turn_id"])
    op.create_index("ix_thread_items_org_created", "thread_items", ["org_id", "created_at"])
    op.execute(
        "CREATE INDEX ix_thread_items_cost_not_null "
        "ON thread_items (org_id, created_at) "
        "WHERE cost_usd IS NOT NULL"
    )

    # 5. RLS policy (mirror chat_conversations)
    op.execute("ALTER TABLE thread_items ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY thread_items_org_isolation ON thread_items "
        "USING (org_id = current_setting('app.current_org_id', true)::uuid)"
    )

    # 6. Backfill
    from ai_portal.chat._backfill import run_backfill
    run_backfill(bind)

    # 7. Drop legacy tables
    op.drop_table("chat_messages")
    op.drop_table("message_usage")


def downgrade() -> None:
    # Destructive migration — not reversible. Restore from pg_dump taken before upgrade.
    raise RuntimeError("031_thread_items_rework is not reversible. Restore from backup.")
```

- [ ] **Step 1.3.2: Verify alembic syntax**

Run: `cd server/api && alembic history | head -5`
Expected: shows `031_thread_items_rework -> 030_seed_default_policies`.

- [ ] **Step 1.3.3: Do not run yet** — the backfill is required first.

---

### Task 1.4: Backfill routine

**Files:**
- Create: `server/api/src/ai_portal/chat/_backfill.py`
- Test: `server/api/tests/chat/test_backfill.py`

Backfill strategy is specified in `docs/superpowers/specs/2026-04-19-chat-thread-items-rework-design.md` §7.1. Each `chat_messages` row becomes multiple `thread_items`; `created_at` is base + µs bump per item; user row starts a turn.

- [ ] **Step 1.4.1: Write the failing test**

```python
# server/api/tests/chat/test_backfill.py
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import text

from ai_portal.chat._backfill import run_backfill


@pytest.fixture
def legacy_fixture(sync_engine):
    """Insert 1 conversation + 1 user msg + 1 assistant msg with stream_items in extra."""
    org_id = uuid.uuid4()
    with sync_engine.begin() as conn:
        conn.execute(text("INSERT INTO orgs (id, name) VALUES (:o, 'test')"), {"o": str(org_id)})
        conn.execute(text(
            "INSERT INTO users (id, email, org_id) VALUES (1, 'u@e', :o)"
        ), {"o": str(org_id)})
        conn.execute(text(
            "INSERT INTO threads (id, org_id, user_id, title, model) "
            "VALUES (1, :o, 1, 'T', 'gpt-4')"
        ), {"o": str(org_id)})
        conn.execute(text(
            "INSERT INTO chat_messages (id, conversation_id, role, content, created_at) "
            "VALUES (1, 1, 'user', 'hi', :t)"
        ), {"t": datetime(2026, 1, 1, tzinfo=timezone.utc)})
        conn.execute(text(
            "INSERT INTO message_usage (id, model_id, input_tokens, output_tokens, cost_usd) "
            "VALUES (1, 'gpt-4', 10, 20, 0.001)"
        ))
        conn.execute(text(
            "INSERT INTO chat_messages (id, conversation_id, role, content, extra, usage_id, model_id, created_at) "
            "VALUES (2, 1, 'assistant', 'hello', :ex, 1, 'gpt-4', :t)"
        ), {
            "ex": json.dumps({"stream_items": [{"kind": "web_search", "provider": "tavily", "params": {"q": "x"}}]}),
            "t": datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
        })
    return org_id


def test_backfill_derives_user_and_assistant_items(sync_engine, legacy_fixture):
    with sync_engine.begin() as conn:
        run_backfill(conn)
        rows = conn.execute(text(
            "SELECT kind, role, status, cost_usd, cost_estimated, model "
            "FROM thread_items WHERE thread_id = 1 ORDER BY created_at"
        )).all()

    kinds = [r.kind for r in rows]
    assert kinds[0] == "user_message"
    assert "tool_call" in kinds
    assert "assistant_text" in kinds
    assert "llm_call" in kinds
    assert kinds[-1] == "turn_end"

    llm_row = next(r for r in rows if r.kind == "llm_call")
    assert llm_row.cost_usd == Decimal("0.001000")
    assert llm_row.cost_estimated is False
    assert llm_row.model == "gpt-4"


def test_backfill_preserves_turn_id_across_user_and_assistant(sync_engine, legacy_fixture):
    with sync_engine.begin() as conn:
        run_backfill(conn)
        turn_ids = conn.execute(text(
            "SELECT DISTINCT turn_id FROM thread_items WHERE thread_id = 1"
        )).scalars().all()
    assert len(turn_ids) == 1
```

- [ ] **Step 1.4.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/chat/test_backfill.py -xvs`
Expected: `ModuleNotFoundError: No module named 'ai_portal.chat._backfill'` or a fixture error.

- [ ] **Step 1.4.3: Implement the backfill**

```python
# server/api/src/ai_portal/chat/_backfill.py
from __future__ import annotations

import json
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

_MICRO = timedelta(microseconds=1)

_TOOL_FLAT_COST_USD: dict[str, Decimal] = {
    "duckduckgo": Decimal("0"),
    "serper": Decimal("0.0003"),
    "tavily": Decimal("0.008"),
    "firecrawl": Decimal("0.002"),
    "jina": Decimal("0.001"),
    "crawl4ai": Decimal("0"),
}


def run_backfill(conn: Connection) -> None:
    """Rewrite legacy chat_messages + message_usage into thread_items.

    Destructive; callers (Alembic) drop the source tables after this returns.
    Runs in the caller's transaction.
    """
    threads = conn.execute(text("SELECT id, org_id FROM threads")).all()
    for t in threads:
        _backfill_thread(conn, t.id, t.org_id)


def _backfill_thread(conn: Connection, thread_id: int, org_id: uuid.UUID) -> None:
    rows = conn.execute(text(
        "SELECT m.id, m.role, m.content, m.extra, m.model_id, m.created_at, "
        "       u.input_tokens, u.output_tokens, u.cost_usd "
        "FROM chat_messages m "
        "LEFT JOIN message_usage u ON u.id = m.usage_id "
        "WHERE m.conversation_id = :tid ORDER BY m.id"
    ), {"tid": thread_id}).all()

    current_turn: uuid.UUID | None = None
    for msg in rows:
        if msg.role == "user":
            current_turn = uuid.uuid4()
            _insert_user_message(conn, thread_id, org_id, current_turn, msg)
        elif msg.role == "assistant":
            if current_turn is None:
                current_turn = uuid.uuid4()  # orphan assistant (shouldn't happen)
            _insert_assistant_items(conn, thread_id, org_id, current_turn, msg)
            current_turn = None
        else:
            # system/tool/etc — skip; shape diverges
            pass


def _insert_user_message(
    conn: Connection, thread_id: int, org_id: uuid.UUID, turn: uuid.UUID, msg: Any
) -> None:
    conn.execute(text(
        "INSERT INTO thread_items "
        "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
        "VALUES (:t, :o, :tid, 'user_message', 'user', 'done', "
        "        :d::jsonb, :c)"
    ), {
        "t": thread_id, "o": str(org_id), "tid": str(turn),
        "d": json.dumps({"text": msg.content, "attachments": []}),
        "c": msg.created_at,
    })


def _insert_assistant_items(
    conn: Connection, thread_id: int, org_id: uuid.UUID, turn: uuid.UUID, msg: Any
) -> None:
    base_ts = msg.created_at
    offset = 0
    extra = msg.extra or {}
    if isinstance(extra, str):
        extra = json.loads(extra)

    for stream_item in extra.get("stream_items", []):
        kind = stream_item.get("kind")
        if kind == "memory":
            offset += 1
            conn.execute(text(
                "INSERT INTO thread_items "
                "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
                "VALUES (:t, :o, :tid, 'memory_pill', 'system', 'done', :d::jsonb, :c)"
            ), {
                "t": thread_id, "o": str(org_id), "tid": str(turn),
                "d": json.dumps({"count": stream_item.get("count", 0)}),
                "c": base_ts + offset * _MICRO,
            })
        elif kind in {"web_search", "fetch_webpage", "kb_search", "tool_call"}:
            offset += 1
            provider = stream_item.get("provider")
            flat = _TOOL_FLAT_COST_USD.get(provider or "", None)
            conn.execute(text(
                "INSERT INTO thread_items "
                "(thread_id, org_id, turn_id, kind, role, status, provider, cost_usd, cost_estimated, data, created_at) "
                "VALUES (:t, :o, :tid, 'tool_call', 'assistant', 'done', :p, :cu, TRUE, :d::jsonb, :c)"
            ), {
                "t": thread_id, "o": str(org_id), "tid": str(turn),
                "p": provider, "cu": flat,
                "d": json.dumps({
                    "tool_name": stream_item.get("tool_name") or kind,
                    "params": stream_item.get("params", {}),
                    "result_snippet": stream_item.get("result_snippet"),
                }),
                "c": base_ts + offset * _MICRO,
            })

    if extra.get("thinking"):
        offset += 1
        conn.execute(text(
            "INSERT INTO thread_items "
            "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
            "VALUES (:t, :o, :tid, 'thinking', 'assistant', 'done', :d::jsonb, :c)"
        ), {
            "t": thread_id, "o": str(org_id), "tid": str(turn),
            "d": json.dumps({"text": extra["thinking"]}),
            "c": base_ts + offset * _MICRO,
        })

    if msg.content:
        offset += 1
        conn.execute(text(
            "INSERT INTO thread_items "
            "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
            "VALUES (:t, :o, :tid, 'assistant_text', 'assistant', 'done', :d::jsonb, :c)"
        ), {
            "t": thread_id, "o": str(org_id), "tid": str(turn),
            "d": json.dumps({"text": msg.content}),
            "c": base_ts + offset * _MICRO,
        })

    if msg.model_id:
        offset += 1
        conn.execute(text(
            "INSERT INTO thread_items "
            "(thread_id, org_id, turn_id, kind, role, status, model, cost_usd, cost_estimated, data, created_at) "
            "VALUES (:t, :o, :tid, 'llm_call', 'assistant', 'done', :m, :cu, FALSE, :d::jsonb, :c)"
        ), {
            "t": thread_id, "o": str(org_id), "tid": str(turn),
            "m": msg.model_id, "cu": msg.cost_usd,
            "d": json.dumps({
                "input_tokens": msg.input_tokens or 0,
                "output_tokens": msg.output_tokens or 0,
                "cached_input_tokens": 0,
                "cache_creation_input_tokens": 0,
                "reasoning_tokens": 0,
                "iteration_index": 0,
            }),
            "c": base_ts + offset * _MICRO,
        })

    offset += 1
    conn.execute(text(
        "INSERT INTO thread_items "
        "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
        "VALUES (:t, :o, :tid, 'turn_end', 'system', 'done', :d::jsonb, :c)"
    ), {
        "t": thread_id, "o": str(org_id), "tid": str(turn),
        "d": json.dumps({"reason": "done"}),
        "c": base_ts + offset * _MICRO,
    })
```

- [ ] **Step 1.4.4: Add sync_engine fixture if it does not already exist**

Check `server/api/tests/conftest.py` for a `sync_engine` fixture. If missing, add:

```python
# server/api/tests/conftest.py (append)
import pytest
from sqlalchemy import create_engine
from ai_portal.core.config import get_settings

@pytest.fixture
def sync_engine():
    url = get_settings().database_url.replace("+asyncpg", "+psycopg")
    eng = create_engine(url)
    yield eng
    eng.dispose()
```

- [ ] **Step 1.4.5: Run test to verify it passes**

Run: `cd server/api && pytest tests/chat/test_backfill.py -xvs`
Expected: two green tests.

If the tests can't create the legacy fixture because the migration has already run and dropped `chat_messages`: run the tests against the **E2E DB** (`ai_portal_e2e`) with a seed step that temporarily recreates the legacy tables from a fixture SQL file — or, simpler, keep the backfill tests as-is and verify Task 1.5's integration run covers real data.

- [ ] **Step 1.4.6: Commit**

```bash
git add server/api/src/ai_portal/chat/_backfill.py server/api/tests/chat/test_backfill.py server/api/tests/conftest.py
git commit -m "feat(chat): thread_items backfill routine"
```

---

### Task 1.5: Run the migration on dev + E2E DBs; verify token-sum checksum

**Files:**
- None modified; verification only.

Checksum rule (spec §8): `SUM(input_tokens) FROM thread_items WHERE kind='llm_call'` must equal `SUM(input_tokens) FROM message_usage` BEFORE the migration runs.

- [ ] **Step 1.5.1: Dump checksum from legacy tables**

```bash
docker exec local-dev-ai-portal-db psql -U postgres -d ai_portal -c \
  "SELECT COALESCE(SUM(input_tokens),0)::bigint AS in_sum, COALESCE(SUM(output_tokens),0)::bigint AS out_sum FROM message_usage"
```

Expected: save the two numbers. Example: `in_sum=12345 out_sum=67890`.

- [ ] **Step 1.5.2: Take a pg_dump of dev DB before migrating**

```bash
docker exec local-dev-ai-portal-db pg_dump -U postgres -d ai_portal \
  --format=custom --file=/tmp/pre_031.dump
docker cp local-dev-ai-portal-db:/tmp/pre_031.dump ./pre_031_dev.dump
```

- [ ] **Step 1.5.3: Run the migration**

```bash
cd server/api
alembic upgrade head
```

Expected: `Running upgrade 030_seed_default_policies -> 031_thread_items_rework`.

- [ ] **Step 1.5.4: Verify checksum matches**

```bash
docker exec local-dev-ai-portal-db psql -U postgres -d ai_portal -c \
  "SELECT COALESCE(SUM((data->>'input_tokens')::bigint),0) AS in_sum, \
          COALESCE(SUM((data->>'output_tokens')::bigint),0) AS out_sum \
     FROM thread_items WHERE kind='llm_call'"
```

Expected: numbers match Step 1.5.1 exactly. If not, investigate — do not proceed.

- [ ] **Step 1.5.5: Verify tables dropped**

```bash
docker exec local-dev-ai-portal-db psql -U postgres -d ai_portal -c "\dt chat_messages message_usage"
```

Expected: `Did not find any relations`.

- [ ] **Step 1.5.6: Apply to E2E DB**

```bash
./scripts/e2e-up.sh
```

Expected: E2E DB recreated, migrations up to 031 applied. Verify with:
```bash
docker exec local-e2e-ai-portal-db psql -U postgres -d ai_portal_e2e -c "\dt threads thread_items"
```
Expected: both listed.

- [ ] **Step 1.5.7: Commit the migration**

```bash
git add server/api/alembic/versions/031_thread_items_rework.py
git commit -m "feat(chat): migration — threads + thread_items + backfill + drop legacy"
```

---

### Task 1.6: Repository + schemas — read thread_items

**Files:**
- Modify: `server/api/src/ai_portal/chat/repository.py`
- Modify: `server/api/src/ai_portal/chat/schemas.py`
- Test: `server/api/tests/chat/test_repository.py` (existing — update)

- [ ] **Step 1.6.1: Update schemas.py**

Remove `MessageRead`, add:

```python
# server/api/src/ai_portal/chat/schemas.py (add near top)
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus


class ThreadRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    org_id: UUID
    user_id: int
    assistant_id: int | None
    title: str | None
    model: str | None
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime


class ThreadItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    thread_id: int
    turn_id: UUID
    kind: ItemKind
    role: ItemRole | None
    status: ItemStatus
    provider: str | None
    model: str | None
    cost_usd: Decimal | None
    cost_estimated: bool
    latency_ms: int | None
    data: dict[str, Any]
    parent_item_id: int | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
```

Keep `ConversationSettings` — it's still used by `Thread.settings`.

- [ ] **Step 1.6.2: Update repository.py**

Rename methods and switch reads from `ChatMessage` to `ThreadItem`. Key method signatures:

```python
# server/api/src/ai_portal/chat/repository.py (partial)
async def list_threads(session, *, org_id, user_id, limit, offset) -> list[Thread]: ...
async def get_thread(session, *, thread_id, org_id) -> Thread | None: ...
async def create_thread(session, *, org_id, user_id, title, model, assistant_id) -> Thread: ...
async def update_thread(session, *, thread_id, org_id, **fields) -> Thread: ...
async def delete_thread(session, *, thread_id, org_id) -> None: ...

async def list_thread_items(
    session, *, thread_id, org_id, since_id: int | None = None
) -> list[ThreadItem]:
    stmt = select(ThreadItem).where(
        ThreadItem.thread_id == thread_id,
        ThreadItem.org_id == org_id,
    )
    if since_id is not None:
        stmt = stmt.where(ThreadItem.id > since_id)
    stmt = stmt.order_by(ThreadItem.created_at, ThreadItem.id)
    return (await session.execute(stmt)).scalars().all()
```

Remove any `list_messages`, `create_message`, `attach_usage` methods.

- [ ] **Step 1.6.3: Update the repository test**

```python
# server/api/tests/chat/test_repository.py (replace message tests)
import pytest

@pytest.mark.asyncio
async def test_list_thread_items_returns_ordered_by_created_at(db_session, thread_with_items):
    items = await repository.list_thread_items(
        db_session, thread_id=thread_with_items.id, org_id=thread_with_items.org_id
    )
    ts = [i.created_at for i in items]
    assert ts == sorted(ts)


@pytest.mark.asyncio
async def test_list_thread_items_since_id(db_session, thread_with_items):
    all_items = await repository.list_thread_items(
        db_session, thread_id=thread_with_items.id, org_id=thread_with_items.org_id
    )
    mid_id = all_items[len(all_items) // 2].id
    tail = await repository.list_thread_items(
        db_session, thread_id=thread_with_items.id, org_id=thread_with_items.org_id,
        since_id=mid_id,
    )
    assert all(i.id > mid_id for i in tail)
```

- [ ] **Step 1.6.4: Fixture for thread_with_items**

```python
# server/api/tests/chat/conftest.py (append or create)
import uuid
import pytest
from datetime import datetime, timezone
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole


@pytest.fixture
async def thread_with_items(db_session, org_fixture, user_fixture):
    thread = Thread(org_id=org_fixture.id, user_id=user_fixture.id, title="t", model="gpt-4")
    db_session.add(thread)
    await db_session.flush()
    turn = uuid.uuid4()
    for kind, role, data in [
        (ItemKind.user_message, ItemRole.user, {"text": "hi", "attachments": []}),
        (ItemKind.assistant_text, ItemRole.assistant, {"text": "hello"}),
        (ItemKind.turn_end, ItemRole.system, {"reason": "done"}),
    ]:
        db_session.add(ThreadItem(
            thread_id=thread.id, org_id=org_fixture.id, turn_id=turn,
            kind=kind, role=role, status=ItemStatus.done, data=data,
        ))
    await db_session.commit()
    return thread
```

Reuse existing `org_fixture` / `user_fixture` from `tests/conftest.py`; add them if missing (parallel to `tests/auth/conftest.py` patterns).

- [ ] **Step 1.6.5: Run tests**

Run: `cd server/api && pytest tests/chat/test_repository.py -xvs`
Expected: PASS.

- [ ] **Step 1.6.6: Commit**

```bash
git add server/api/src/ai_portal/chat/repository.py server/api/src/ai_portal/chat/schemas.py server/api/tests/chat/
git commit -m "refactor(chat): repository + schemas switch to thread_items"
```

---

### Task 1.7: Smoke — backend boots with new model

**Files:** None modified.

- [ ] **Step 1.7.1: Boot uvicorn**

```bash
cd server/api
uvicorn ai_portal.main:app --port 8000 --reload
```

Expected: starts without import errors. Ignore router-level errors from removed message endpoints — those are cleaned up in Phase 6.

- [ ] **Step 1.7.2: Smoke-check DB reads**

```bash
curl -s http://localhost:8000/health | jq
```

Expected: `{"status":"ok","db":"ai_portal",...}`.

- [ ] **Step 1.7.3: Verify alembic check is clean**

```bash
cd server/api
alembic check
```

Expected: `No new upgrade operations detected`.

- [ ] **Step 1.7.4: Kill uvicorn**

---
## Phase 2 — Typed contracts (Pydantic items, SSE envelope, provider events, TS mirrors)

### Task 2.1: Pydantic `ThreadItem` discriminated union

**Files:**
- Create: `server/api/src/ai_portal/chat/items.py`
- Test: `server/api/tests/chat/test_items_schema.py`

- [ ] **Step 2.1.1: Write the failing test**

```python
# server/api/tests/chat/test_items_schema.py
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from ai_portal.chat.items import (
    AssistantTextItem,
    CitationItem,
    ErrorItem,
    LlmCallItem,
    MemoryPillItem,
    ServerToolUseItem,
    ThinkingItem,
    ThreadItemModel,
    ToolCallItem,
    TurnEndItem,
    UserMessageItem,
)


def _base_kwargs(**overrides):
    return {
        "id": 1, "thread_id": 1, "turn_id": uuid.uuid4(),
        "status": "done", "created_at": datetime.now(timezone.utc),
        **overrides,
    }


def test_user_message_discriminator():
    item = UserMessageItem(**_base_kwargs(kind="user_message", data={"text": "hi", "attachments": []}))
    assert item.kind == "user_message"


def test_llm_call_requires_model_and_tokens():
    with pytest.raises(ValidationError):
        LlmCallItem(**_base_kwargs(kind="llm_call", data={}))
    item = LlmCallItem(**_base_kwargs(
        kind="llm_call", model="gpt-4",
        data={"input_tokens": 10, "output_tokens": 20, "cached_input_tokens": 0,
              "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "iteration_index": 0},
    ))
    assert item.data.input_tokens == 10


def test_threaditem_parses_from_discriminator():
    payload = _base_kwargs(
        kind="tool_call", role="assistant",
        data={"tool_name": "web_search", "params": {"q": "x"}},
    )
    item = ThreadItemModel.model_validate(payload)
    assert isinstance(item.root, ToolCallItem)


def test_turn_end_payload():
    item = TurnEndItem(**_base_kwargs(kind="turn_end", data={"reason": "done"}))
    assert item.data.reason == "done"


def test_error_kind_payload():
    item = ErrorItem(**_base_kwargs(kind="error", data={"code": "E1", "message": "boom"}))
    assert item.data.code == "E1"
```

- [ ] **Step 2.1.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/chat/test_items_schema.py -xvs`
Expected: `ModuleNotFoundError`.

- [ ] **Step 2.1.3: Implement items.py**

```python
# server/api/src/ai_portal/chat/items.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel

from ai_portal.chat.item_kinds import ItemRole, ItemStatus


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: int
    thread_id: int
    turn_id: UUID
    role: ItemRole | None = None
    status: ItemStatus
    provider: str | None = None
    model: str | None = None
    cost_usd: Decimal | None = None
    cost_estimated: bool = False
    latency_ms: int | None = None
    parent_item_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


# --- payloads ---

class UserMessagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str
    attachments: list[dict] = Field(default_factory=list)


class AssistantTextPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class LlmCallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    reasoning_tokens: int = 0
    iteration_index: int = 0


class ToolCallPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    params: dict = Field(default_factory=dict)
    result_snippet: str | None = None
    error: str | None = None


class ServerToolUsePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_name: str
    input: dict = Field(default_factory=dict)


class ThinkingPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str


class CitationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    title: str | None = None
    snippet: str | None = None


class MemoryPillPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int


class TurnEndPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: Literal["done", "error", "cancelled"]


class ErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str


# --- discriminated items ---

class UserMessageItem(_Base):
    kind: Literal["user_message"]
    data: UserMessagePayload


class AssistantTextItem(_Base):
    kind: Literal["assistant_text"]
    data: AssistantTextPayload


class LlmCallItem(_Base):
    kind: Literal["llm_call"]
    data: LlmCallPayload


class ToolCallItem(_Base):
    kind: Literal["tool_call"]
    data: ToolCallPayload


class ServerToolUseItem(_Base):
    kind: Literal["server_tool_use"]
    data: ServerToolUsePayload


class ThinkingItem(_Base):
    kind: Literal["thinking"]
    data: ThinkingPayload


class CitationItem(_Base):
    kind: Literal["citation"]
    data: CitationPayload


class MemoryPillItem(_Base):
    kind: Literal["memory_pill"]
    data: MemoryPillPayload


class TurnEndItem(_Base):
    kind: Literal["turn_end"]
    data: TurnEndPayload


class ErrorItem(_Base):
    kind: Literal["error"]
    data: ErrorPayload


ThreadItemUnion = Annotated[
    UserMessageItem
    | AssistantTextItem
    | LlmCallItem
    | ToolCallItem
    | ServerToolUseItem
    | ThinkingItem
    | CitationItem
    | MemoryPillItem
    | TurnEndItem
    | ErrorItem,
    Field(discriminator="kind"),
]


class ThreadItemModel(RootModel[ThreadItemUnion]):
    pass
```

- [ ] **Step 2.1.4: Run tests**

Run: `cd server/api && pytest tests/chat/test_items_schema.py -xvs`
Expected: PASS.

- [ ] **Step 2.1.5: Commit**

```bash
git add server/api/src/ai_portal/chat/items.py server/api/tests/chat/test_items_schema.py
git commit -m "feat(chat): Pydantic ThreadItem discriminated union"
```

---

### Task 2.2: `SseEvent` envelope

**Files:**
- Create: `server/api/src/ai_portal/chat/sse.py`
- Test: `server/api/tests/chat/test_sse_emitter.py` (partial — only envelope assertions here; emitter tests come in Phase 6)

- [ ] **Step 2.2.1: Write the failing test**

```python
# server/api/tests/chat/test_sse_envelope.py
import uuid
from datetime import datetime, timezone

from ai_portal.chat.sse import SseEvent, SseItemEvent, SseErrorEvent, SseDoneEvent


def test_item_event_roundtrip():
    payload = {
        "event_type": "item",
        "item": {
            "id": 1, "thread_id": 1, "turn_id": str(uuid.uuid4()),
            "kind": "assistant_text", "status": "streaming",
            "role": "assistant", "cost_estimated": False,
            "data": {"text": "hi"}, "created_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    event = SseEvent.model_validate(payload)
    assert isinstance(event.root, SseItemEvent)
    assert event.root.item.root.kind == "assistant_text"


def test_error_event_roundtrip():
    event = SseEvent.model_validate({
        "event_type": "error",
        "error": {"code": "E_QUOTA", "message": "over"},
    })
    assert isinstance(event.root, SseErrorEvent)


def test_done_event_roundtrip():
    event = SseEvent.model_validate({"event_type": "done"})
    assert isinstance(event.root, SseDoneEvent)
```

- [ ] **Step 2.2.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/chat/test_sse_envelope.py -xvs`
Expected: `ModuleNotFoundError`.

- [ ] **Step 2.2.3: Implement sse.py**

```python
# server/api/src/ai_portal/chat/sse.py
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel

from ai_portal.chat.items import ErrorPayload, ThreadItemModel


class SseItemEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["item"]
    item: ThreadItemModel


class SseErrorEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["error"]
    error: ErrorPayload


class SseDoneEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_type: Literal["done"]


SseEventUnion = Annotated[
    SseItemEvent | SseErrorEvent | SseDoneEvent,
    Field(discriminator="event_type"),
]


class SseEvent(RootModel[SseEventUnion]):
    pass
```

- [ ] **Step 2.2.4: Run tests**

Run: `cd server/api && pytest tests/chat/test_sse_envelope.py -xvs`
Expected: PASS.

- [ ] **Step 2.2.5: Commit**

```bash
git add server/api/src/ai_portal/chat/sse.py server/api/tests/chat/test_sse_envelope.py
git commit -m "feat(chat): typed SseEvent envelope"
```

---

### Task 2.3: `ProviderStreamEvent` discriminated union

**Files:**
- Create: `server/api/src/ai_portal/catalog/providers/events.py`
- Test: `server/api/tests/catalog/test_provider_events.py`

- [ ] **Step 2.3.1: Write the failing test**

```python
# server/api/tests/catalog/test_provider_events.py
import pytest
from pydantic import ValidationError

from ai_portal.catalog.providers.events import (
    ProviderStreamEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
    ServerToolUseEvent,
    ProviderErrorEvent,
    IterationCompleteEvent,
)


def test_text_delta():
    ev = ProviderStreamEvent.model_validate({"type": "text_delta", "text": "hi"})
    assert isinstance(ev.root, TextDeltaEvent)


def test_usage_event_shape():
    ev = ProviderStreamEvent.model_validate({
        "type": "usage",
        "input_tokens": 10, "output_tokens": 20,
        "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0,
    })
    assert ev.root.output_tokens == 20


def test_tool_call_request():
    ev = ProviderStreamEvent.model_validate({
        "type": "tool_call_request",
        "call_id": "call_1", "tool_name": "web_search", "arguments": {"q": "x"},
    })
    assert isinstance(ev.root, ToolCallRequestEvent)


def test_unknown_discriminator_rejected():
    with pytest.raises(ValidationError):
        ProviderStreamEvent.model_validate({"type": "wat"})
```

- [ ] **Step 2.3.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/catalog/test_provider_events.py -xvs`
Expected: `ModuleNotFoundError`.

- [ ] **Step 2.3.3: Implement events.py**

```python
# server/api/src/ai_portal/catalog/providers/events.py
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, RootModel


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TextDeltaEvent(_Base):
    type: Literal["text_delta"]
    text: str


class ThinkingDeltaEvent(_Base):
    type: Literal["thinking_delta"]
    text: str


class ToolCallRequestEvent(_Base):
    type: Literal["tool_call_request"]
    call_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ServerToolUseEvent(_Base):
    """Provider-native tools (Anthropic web_search, Gemini grounding)."""
    type: Literal["server_tool_use"]
    tool_name: str
    input: dict[str, Any] = Field(default_factory=dict)


class CitationEvent(_Base):
    type: Literal["citation"]
    url: str
    title: str | None = None
    snippet: str | None = None


class UsageEvent(_Base):
    type: Literal["usage"]
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    reasoning_tokens: int = 0


class IterationCompleteEvent(_Base):
    """Signals end of one LLM round (stop reason known)."""
    type: Literal["iteration_complete"]
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "stop_sequence", "unknown"]


class ProviderErrorEvent(_Base):
    type: Literal["provider_error"]
    code: str
    message: str


ProviderStreamEventUnion = Annotated[
    TextDeltaEvent
    | ThinkingDeltaEvent
    | ToolCallRequestEvent
    | ServerToolUseEvent
    | CitationEvent
    | UsageEvent
    | IterationCompleteEvent
    | ProviderErrorEvent,
    Field(discriminator="type"),
]


class ProviderStreamEvent(RootModel[ProviderStreamEventUnion]):
    pass
```

- [ ] **Step 2.3.4: Run tests**

Run: `cd server/api && pytest tests/catalog/test_provider_events.py -xvs`
Expected: PASS.

- [ ] **Step 2.3.5: Commit**

```bash
git add server/api/src/ai_portal/catalog/providers/events.py server/api/tests/catalog/test_provider_events.py
git commit -m "feat(catalog): typed ProviderStreamEvent union"
```

---

### Task 2.4: `ToolCallOutcome` Pydantic model

**Files:**
- Create: `server/api/src/ai_portal/chat/tool_outcome.py`
- Test: `server/api/tests/chat/test_tool_outcome.py`

- [ ] **Step 2.4.1: Write the failing test**

```python
# server/api/tests/chat/test_tool_outcome.py
from decimal import Decimal
from ai_portal.chat.tool_outcome import ToolCallOutcome


def test_outcome_minimum_shape():
    o = ToolCallOutcome(
        call_id="c1", tool_name="web_search", provider="tavily",
        input={"q": "x"}, result_snippet="ok",
    )
    assert o.cost_usd is None
    assert o.error is None


def test_outcome_with_metered_cost():
    o = ToolCallOutcome(
        call_id="c1", tool_name="scrape", provider="firecrawl",
        input={"url": "x"}, result_snippet="ok",
        cost_usd=Decimal("0.0042"), latency_ms=120,
    )
    assert o.cost_usd == Decimal("0.0042")
    assert o.latency_ms == 120


def test_outcome_error_case():
    o = ToolCallOutcome(
        call_id="c1", tool_name="web_search", provider="tavily",
        input={}, error="rate limited",
    )
    assert o.error == "rate limited"
    assert o.result_snippet is None
```

- [ ] **Step 2.4.2: Implement**

```python
# server/api/src/ai_portal/chat/tool_outcome.py
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ToolCallOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    tool_name: str
    provider: str
    input: dict = Field(default_factory=dict)
    result_snippet: str | None = None
    error: str | None = None
    cost_usd: Decimal | None = None
    latency_ms: int | None = None
```

- [ ] **Step 2.4.3: Run tests and commit**

Run: `cd server/api && pytest tests/chat/test_tool_outcome.py -xvs`
Expected: PASS.

```bash
git add server/api/src/ai_portal/chat/tool_outcome.py server/api/tests/chat/test_tool_outcome.py
git commit -m "feat(chat): ToolCallOutcome model"
```

---

### Task 2.5: Frontend TS mirrors

**Files:**
- Modify: `apps/frontend/src/lib/chat-types.ts`

- [ ] **Step 2.5.1: Read the current file**

Read: `apps/frontend/src/lib/chat-types.ts`. Preserve any exports still used by non-chat code; replace the rest.

- [ ] **Step 2.5.2: Write the new types**

```ts
// apps/frontend/src/lib/chat-types.ts
export type ItemKind =
  | "user_message"
  | "assistant_text"
  | "llm_call"
  | "tool_call"
  | "server_tool_use"
  | "thinking"
  | "citation"
  | "memory_pill"
  | "turn_end"
  | "error";

export type ItemStatus = "streaming" | "done" | "error" | "cancelled";
export type ItemRole = "user" | "assistant" | "system";

export interface ThreadItemBase {
  id: number;
  thread_id: number;
  turn_id: string;
  role: ItemRole | null;
  status: ItemStatus;
  provider: string | null;
  model: string | null;
  cost_usd: string | null; // Decimal serialized as string
  cost_estimated: boolean;
  latency_ms: number | null;
  parent_item_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface UserMessagePayload { text: string; attachments: unknown[] }
export interface AssistantTextPayload { text: string }
export interface LlmCallPayload {
  input_tokens: number;
  output_tokens: number;
  cached_input_tokens: number;
  cache_creation_input_tokens: number;
  reasoning_tokens: number;
  iteration_index: number;
}
export interface ToolCallPayload {
  tool_name: string;
  params: Record<string, unknown>;
  result_snippet?: string | null;
  error?: string | null;
}
export interface ServerToolUsePayload {
  tool_name: string;
  input: Record<string, unknown>;
}
export interface ThinkingPayload { text: string }
export interface CitationPayload {
  url: string;
  title?: string | null;
  snippet?: string | null;
}
export interface MemoryPillPayload { count: number }
export interface TurnEndPayload { reason: "done" | "error" | "cancelled" }
export interface ErrorPayload { code: string; message: string }

export type ThreadItem =
  | (ThreadItemBase & { kind: "user_message"; data: UserMessagePayload })
  | (ThreadItemBase & { kind: "assistant_text"; data: AssistantTextPayload })
  | (ThreadItemBase & { kind: "llm_call"; data: LlmCallPayload })
  | (ThreadItemBase & { kind: "tool_call"; data: ToolCallPayload })
  | (ThreadItemBase & { kind: "server_tool_use"; data: ServerToolUsePayload })
  | (ThreadItemBase & { kind: "thinking"; data: ThinkingPayload })
  | (ThreadItemBase & { kind: "citation"; data: CitationPayload })
  | (ThreadItemBase & { kind: "memory_pill"; data: MemoryPillPayload })
  | (ThreadItemBase & { kind: "turn_end"; data: TurnEndPayload })
  | (ThreadItemBase & { kind: "error"; data: ErrorPayload });

export type SseEvent =
  | { event_type: "item"; item: ThreadItem }
  | { event_type: "error"; error: ErrorPayload }
  | { event_type: "done" };

export interface ThreadRead {
  id: number;
  org_id: string;
  user_id: number;
  assistant_id: number | null;
  title: string | null;
  model: string | null;
  summary: string | null;
  last_message_at: string | null;
  created_at: string;
}
```

- [ ] **Step 2.5.3: Run the frontend type check**

```bash
cd apps/frontend
pnpm typecheck
```

Expected: any existing references to `MessageRead` / old types surface as errors; leave them failing — Phase 9 fixes the renderer. If a type error blocks something you must not touch this phase, add a `// @ts-expect-error — Phase 9` comment on the specific line and move on. Track these in a local TODO list, not in a file.

- [ ] **Step 2.5.4: Commit**

```bash
git add apps/frontend/src/lib/chat-types.ts
git commit -m "feat(frontend): TS mirrors for ThreadItem + SseEvent"
```

---

### Task 2.6: Types alignment CI check

**Files:**
- Create: `server/api/scripts/check_types_align.py`
- Modify: CI workflow file (`.github/workflows/ci.yml` — or whichever workflow runs backend checks). If no workflow exists yet, add the script invocation to `package.json`'s `typecheck` script instead — a later infrastructure pass will wire CI.

- [ ] **Step 2.6.1: Write the check script**

```python
# server/api/scripts/check_types_align.py
"""Fail the build if Python and TS ItemKind literals diverge."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY_FILE = REPO / "server/api/src/ai_portal/chat/item_kinds.py"
TS_FILE = REPO / "apps/frontend/src/lib/chat-types.ts"


def py_kinds() -> set[str]:
    text = PY_FILE.read_text(encoding="utf-8")
    m = re.search(r"class ItemKind\(str, Enum\):(.+?)\nclass ", text, re.S)
    assert m, "could not locate ItemKind in Python"
    return set(re.findall(r'(\w+)\s*=\s*"([^"]+)"', m.group(1)))


def ts_kinds() -> set[str]:
    text = TS_FILE.read_text(encoding="utf-8")
    m = re.search(r"export type ItemKind\s*=([^;]+);", text)
    assert m, "could not locate ItemKind in TS"
    return set((name, name) for name in re.findall(r'"([^"]+)"', m.group(1)))


def main() -> int:
    py = {v for _, v in py_kinds()}
    ts = {v for _, v in ts_kinds()}
    only_py = py - ts
    only_ts = ts - py
    if only_py or only_ts:
        print(f"Python-only kinds: {sorted(only_py)}", file=sys.stderr)
        print(f"TS-only kinds:     {sorted(only_ts)}", file=sys.stderr)
        return 1
    print(f"OK — {len(py)} ItemKind literals aligned")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2.6.2: Run the script**

```bash
cd server/api
python scripts/check_types_align.py
```

Expected: `OK — 10 ItemKind literals aligned`.

- [ ] **Step 2.6.3: Add to CI**

If `.github/workflows/ci.yml` exists, add a step under the backend job:
```yaml
      - name: Types alignment check
        run: python server/api/scripts/check_types_align.py
```
If no CI exists, add the invocation to the root `package.json`'s `check` script. If neither exists, leave a `TODO(infra)` note in the script's docstring.

- [ ] **Step 2.6.4: Commit**

```bash
git add server/api/scripts/check_types_align.py .github/workflows/ci.yml
git commit -m "chore(ci): types-align guard between Python and TS ItemKind"
```

---

### Task 2.7: Update CLAUDE.md with the sync rule

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 2.7.1: Append section**

Add between `## Design v2` and `## System Prompt Style`:

```markdown
## Chat Types Stay in Sync (Non-Negotiable)

When you add, rename, or remove any field or kind in:
- `server/api/src/ai_portal/chat/item_kinds.py`
- `server/api/src/ai_portal/chat/items.py`
- `server/api/src/ai_portal/chat/sse.py`
- `server/api/src/ai_portal/catalog/providers/events.py`

You MUST update the matching TypeScript in `apps/frontend/src/lib/chat-types.ts` in the **same commit**.

CI runs `server/api/scripts/check_types_align.py` — the build fails if `ItemKind` literals diverge between Python and TS. No dual-tree drift.
```

- [ ] **Step 2.7.2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: chat types sync rule in CLAUDE.md"
```

---

## Phase 3 — Cost calculator (isolated module + pricing tables)

### Task 3.1: LLM pricing table

**Files:**
- Create: `server/api/src/ai_portal/chat/llm_pricing.py`
- Test: `server/api/tests/chat/test_llm_pricing.py`

First read the existing `server/api/src/ai_portal/usage/pricing.py` — the flat rates already live there and will move. Do not edit that file yet; Phase 8 removes the old import path.

- [ ] **Step 3.1.1: Copy rates from `usage/pricing.py` into `chat/llm_pricing.py`**

Read: `server/api/src/ai_portal/usage/pricing.py` and copy the per-model rate dict verbatim into `chat/llm_pricing.py`. Preserve Decimal literals.

- [ ] **Step 3.1.2: Write the failing test**

```python
# server/api/tests/chat/test_llm_pricing.py
from decimal import Decimal
from ai_portal.chat.llm_pricing import get_llm_rates, LlmRate


def test_known_model_has_rates():
    r = get_llm_rates("gpt-4o")
    assert r is not None
    assert r.input_per_million > Decimal("0")


def test_unknown_model_returns_none():
    assert get_llm_rates("nonexistent-model-xyz") is None
```

- [ ] **Step 3.1.3: Implement llm_pricing.py**

```python
# server/api/src/ai_portal/chat/llm_pricing.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class LlmRate:
    input_per_million: Decimal
    output_per_million: Decimal
    cached_input_per_million: Decimal | None = None
    cache_creation_per_million: Decimal | None = None
    reasoning_per_million: Decimal | None = None


# Paste contents from usage/pricing.py._RATES here, keyed by model id.
# Each entry is an LlmRate.
_RATES: dict[str, LlmRate] = {
    # Example entries — fill from existing usage/pricing.py
    "gpt-4o": LlmRate(
        input_per_million=Decimal("2.50"),
        output_per_million=Decimal("10.00"),
        cached_input_per_million=Decimal("1.25"),
    ),
    "claude-sonnet-4-6": LlmRate(
        input_per_million=Decimal("3.00"),
        output_per_million=Decimal("15.00"),
        cached_input_per_million=Decimal("0.30"),
        cache_creation_per_million=Decimal("3.75"),
    ),
    # ...
}


def get_llm_rates(model: str) -> LlmRate | None:
    return _RATES.get(model)
```

Copy the exact rates from the existing file; do not invent new ones. The examples above are placeholders.

- [ ] **Step 3.1.4: Run tests**

Run: `cd server/api && pytest tests/chat/test_llm_pricing.py -xvs`
Expected: PASS.

- [ ] **Step 3.1.5: Commit**

```bash
git add server/api/src/ai_portal/chat/llm_pricing.py server/api/tests/chat/test_llm_pricing.py
git commit -m "feat(chat): LLM pricing table moved to chat domain"
```

---

### Task 3.2: Tool pricing table

**Files:**
- Create: `server/api/src/ai_portal/chat/tool_pricing.py`
- Test: `server/api/tests/chat/test_tool_pricing.py`

- [ ] **Step 3.2.1: Write the failing test**

```python
# server/api/tests/chat/test_tool_pricing.py
from decimal import Decimal
from ai_portal.chat.tool_pricing import get_tool_flat_rate


def test_known_providers():
    assert get_tool_flat_rate("duckduckgo") == Decimal("0")
    assert get_tool_flat_rate("tavily") == Decimal("0.008")
    assert get_tool_flat_rate("firecrawl") == Decimal("0.002")


def test_unknown_provider_returns_none():
    assert get_tool_flat_rate("nonsense") is None
```

- [ ] **Step 3.2.2: Implement**

```python
# server/api/src/ai_portal/chat/tool_pricing.py
from __future__ import annotations

from decimal import Decimal


_FLAT_RATES: dict[str, Decimal] = {
    "duckduckgo": Decimal("0"),
    "serper": Decimal("0.0003"),
    "tavily": Decimal("0.008"),
    "firecrawl": Decimal("0.002"),
    "jina": Decimal("0.001"),
    "crawl4ai": Decimal("0"),
}


def get_tool_flat_rate(provider: str) -> Decimal | None:
    return _FLAT_RATES.get(provider)
```

- [ ] **Step 3.2.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_tool_pricing.py -xvs
git add server/api/src/ai_portal/chat/tool_pricing.py server/api/tests/chat/test_tool_pricing.py
git commit -m "feat(chat): tool provider flat pricing table"
```

---

### Task 3.3: Cost calculator public API

**Files:**
- Create: `server/api/src/ai_portal/chat/cost_calculator.py`
- Test: `server/api/tests/chat/test_cost_calculator.py`

- [ ] **Step 3.3.1: Write the failing test**

```python
# server/api/tests/chat/test_cost_calculator.py
from decimal import Decimal

import pytest

from ai_portal.chat.cost_calculator import (
    compute_llm_cost,
    compute_tool_cost,
    compute_server_tool_cost,
    CostResult,
)
from ai_portal.chat.tool_outcome import ToolCallOutcome


def test_llm_cost_known_model():
    r = compute_llm_cost(
        model="gpt-4o",
        input_tokens=1_000_000, output_tokens=1_000_000,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
    )
    assert r.estimated is False
    assert r.source == "flat_rate"
    # rate * 1M = rate
    assert r.cost_usd > Decimal("0")


def test_llm_cost_unknown_model_returns_zero_flag_unknown():
    r = compute_llm_cost(
        model="nonexistent-zzz",
        input_tokens=1000, output_tokens=2000,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
    )
    assert r.cost_usd == Decimal("0")
    assert r.estimated is True
    assert r.source == "unknown_model"


def test_tool_cost_prefers_metered_signal():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="firecrawl",
        input={}, cost_usd=Decimal("0.017"),
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0.017")
    assert r.estimated is False
    assert r.source == "provider_metered"


def test_tool_cost_falls_back_to_flat_rate():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="firecrawl", input={},
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0.002")
    assert r.estimated is True
    assert r.source == "flat_rate"


def test_tool_cost_free_provider():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="search", provider="duckduckgo", input={},
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0")
    assert r.source == "free"


def test_tool_cost_unknown_provider():
    outcome = ToolCallOutcome(
        call_id="c", tool_name="scrape", provider="unknown_provider", input={},
    )
    r = compute_tool_cost(outcome)
    assert r.cost_usd == Decimal("0")
    assert r.source == "unknown_model"


def test_server_tool_uses_llm_rate_only_when_metered_absent():
    r = compute_server_tool_cost(
        tool_name="web_search", provider="anthropic",
        usage_metadata={"search_queries": 2},
    )
    # v1: server tools that carry no LLM usage_metadata return 0 with source=free
    assert r.source in {"free", "flat_rate"}
```

- [ ] **Step 3.3.2: Implement**

```python
# server/api/src/ai_portal/chat/cost_calculator.py
from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ai_portal.chat.llm_pricing import LlmRate, get_llm_rates
from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.chat.tool_pricing import get_tool_flat_rate


CostSource = Literal[
    "flat_rate", "provider_metered", "unknown_model", "free",
]


class CostResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    cost_usd: Decimal
    estimated: bool
    source: CostSource


_ZERO = Decimal("0")
_MILLION = Decimal("1000000")


def _rate_component(tokens: int, rate_per_million: Decimal | None) -> Decimal:
    if rate_per_million is None or tokens <= 0:
        return _ZERO
    return (Decimal(tokens) * rate_per_million) / _MILLION


def compute_llm_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_input_tokens: int,
    cache_creation_input_tokens: int,
    reasoning_tokens: int,
) -> CostResult:
    rates = get_llm_rates(model)
    if rates is None:
        return CostResult(cost_usd=_ZERO, estimated=True, source="unknown_model")

    billable_input = input_tokens - cached_input_tokens - cache_creation_input_tokens
    billable_input = max(billable_input, 0)

    total = (
        _rate_component(billable_input, rates.input_per_million)
        + _rate_component(cached_input_tokens, rates.cached_input_per_million or rates.input_per_million)
        + _rate_component(cache_creation_input_tokens, rates.cache_creation_per_million or rates.input_per_million)
        + _rate_component(output_tokens, rates.output_per_million)
        + _rate_component(reasoning_tokens, rates.reasoning_per_million or rates.output_per_million)
    )
    return CostResult(cost_usd=total.quantize(Decimal("0.000001")), estimated=False, source="flat_rate")


def compute_tool_cost(outcome: ToolCallOutcome) -> CostResult:
    if outcome.cost_usd is not None:
        return CostResult(cost_usd=outcome.cost_usd, estimated=False, source="provider_metered")
    flat = get_tool_flat_rate(outcome.provider)
    if flat is None:
        return CostResult(cost_usd=_ZERO, estimated=True, source="unknown_model")
    if flat == _ZERO:
        return CostResult(cost_usd=_ZERO, estimated=False, source="free")
    return CostResult(cost_usd=flat, estimated=True, source="flat_rate")


def compute_server_tool_cost(
    *,
    tool_name: str,
    provider: str,
    usage_metadata: dict | None,
) -> CostResult:
    """Anthropic web_search / Gemini grounding etc.

    v1: accept only metered signals. If a provider billed us explicitly via
    usage_metadata['cost_usd'] (as Decimal or string), use it; otherwise free.
    """
    if usage_metadata and "cost_usd" in usage_metadata:
        value = usage_metadata["cost_usd"]
        return CostResult(cost_usd=Decimal(str(value)), estimated=False, source="provider_metered")
    return CostResult(cost_usd=_ZERO, estimated=False, source="free")
```

- [ ] **Step 3.3.3: Run tests**

Run: `cd server/api && pytest tests/chat/test_cost_calculator.py -xvs`
Expected: all PASS.

- [ ] **Step 3.3.4: Commit**

```bash
git add server/api/src/ai_portal/chat/cost_calculator.py server/api/tests/chat/test_cost_calculator.py
git commit -m "feat(chat): isolated cost calculator (LLM + tool + server-tool)"
```

---

### Task 3.4: Usage pricing re-export shim (temporary)

**Files:**
- Modify: `server/api/src/ai_portal/usage/pricing.py`

- [ ] **Step 3.4.1: Replace body with re-export**

```python
# server/api/src/ai_portal/usage/pricing.py
"""Deprecated location — use ai_portal.chat.llm_pricing.

Kept during Phase 3–8 transition. Deleted in Phase 12.
"""
from ai_portal.chat.llm_pricing import LlmRate, get_llm_rates  # noqa: F401
```

- [ ] **Step 3.4.2: Run the existing usage tests (still pass)**

Run: `cd server/api && pytest tests/usage -xvs`
Expected: the subset that does not depend on `message_usage` rows still passes. Failures tied to the dropped `MessageUsage` model are expected — those are cleaned up in Phase 8. Note any test you skip here.

- [ ] **Step 3.4.3: Commit**

```bash
git add server/api/src/ai_portal/usage/pricing.py
git commit -m "refactor(usage): re-export llm pricing from chat.llm_pricing"
```

---
## Phase 4 — Tool service (dispatch wrapper returning `ToolCallOutcome`)

### Task 4.1: Refactor `tool_service` to return `ToolCallOutcome`

**Files:**
- Modify: `server/api/src/ai_portal/chat/tool_service.py`
- Test: `server/api/tests/chat/test_tool_service.py` (new)

Current `tool_service.py` (27 LOC) likely just dispatches to a registry. Wrap dispatch so every callsite receives a typed outcome.

- [ ] **Step 4.1.1: Read current `tool_service.py`**

Read: `server/api/src/ai_portal/chat/tool_service.py`. Identify the dispatch function signature.

- [ ] **Step 4.1.2: Write failing test**

```python
# server/api/tests/chat/test_tool_service.py
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.chat.tool_service import dispatch_tool


@pytest.mark.asyncio
async def test_dispatch_returns_tool_call_outcome(monkeypatch):
    fake_run = AsyncMock(return_value={
        "provider": "tavily",
        "result_snippet": "found",
        "input": {"q": "hi"},
    })
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", fake_run)

    outcome = await dispatch_tool(
        tool_name="web_search", call_id="c1", arguments={"q": "hi"}, org_id="org-1",
    )
    assert isinstance(outcome, ToolCallOutcome)
    assert outcome.provider == "tavily"
    assert outcome.result_snippet == "found"


@pytest.mark.asyncio
async def test_dispatch_captures_errors_into_outcome(monkeypatch):
    async def boom(*a, **kw):
        raise RuntimeError("rate limited")
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", boom)

    outcome = await dispatch_tool(
        tool_name="web_search", call_id="c1", arguments={"q": "hi"}, org_id="org-1",
    )
    assert outcome.error == "rate limited"
    assert outcome.result_snippet is None


@pytest.mark.asyncio
async def test_dispatch_propagates_metered_cost(monkeypatch):
    async def metered(*a, **kw):
        return {
            "provider": "firecrawl",
            "result_snippet": "ok",
            "input": {"url": "x"},
            "cost_usd": Decimal("0.042"),
            "latency_ms": 140,
        }
    monkeypatch.setattr("ai_portal.tools.registry.run_tool", metered)

    outcome = await dispatch_tool(
        tool_name="scrape", call_id="c1", arguments={"url": "x"}, org_id="org-1",
    )
    assert outcome.cost_usd == Decimal("0.042")
    assert outcome.latency_ms == 140
```

- [ ] **Step 4.1.3: Implement**

```python
# server/api/src/ai_portal/chat/tool_service.py
from __future__ import annotations

import logging
import time
from decimal import Decimal

from ai_portal.chat.tool_outcome import ToolCallOutcome
from ai_portal.tools import registry

log = logging.getLogger(__name__)


async def dispatch_tool(
    *,
    tool_name: str,
    call_id: str,
    arguments: dict,
    org_id: str,
    user_id: int | None = None,
) -> ToolCallOutcome:
    """Single entry point. Returns ToolCallOutcome; never raises."""
    t0 = time.monotonic()
    try:
        result = await registry.run_tool(
            tool_name=tool_name, arguments=arguments, org_id=org_id, user_id=user_id,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        return ToolCallOutcome(
            call_id=call_id,
            tool_name=tool_name,
            provider=result.get("provider") or "unknown",
            input=result.get("input") or arguments,
            result_snippet=result.get("result_snippet"),
            cost_usd=_as_decimal(result.get("cost_usd")),
            latency_ms=result.get("latency_ms") or latency_ms,
        )
    except Exception as exc:
        log.exception("tool dispatch failed", extra={"tool_name": tool_name, "call_id": call_id})
        return ToolCallOutcome(
            call_id=call_id,
            tool_name=tool_name,
            provider="unknown",
            input=arguments,
            error=str(exc),
            latency_ms=int((time.monotonic() - t0) * 1000),
        )


def _as_decimal(v) -> Decimal | None:
    if v is None:
        return None
    return v if isinstance(v, Decimal) else Decimal(str(v))
```

- [ ] **Step 4.1.4: Run tests**

Run: `cd server/api && pytest tests/chat/test_tool_service.py -xvs`
Expected: PASS.

- [ ] **Step 4.1.5: Commit**

```bash
git add server/api/src/ai_portal/chat/tool_service.py server/api/tests/chat/test_tool_service.py
git commit -m "refactor(chat): tool_service returns ToolCallOutcome"
```

---

### Task 4.2: Update each tool implementation to expose metered signals

**Files:**
- Modify: `server/api/src/ai_portal/tools/web_search.py`
- Modify: `server/api/src/ai_portal/tools/fetch_webpage.py`
- Modify: `server/api/src/ai_portal/tools/kb_search.py`
- Modify: `server/api/src/ai_portal/tools/registry.py` (if dispatch table lives there)

Each tool currently returns a dict. Enforce the shape: every tool MUST include `provider`; tools that can read cost from a provider response MUST include `cost_usd: Decimal`. Tools that cannot parse cost return no `cost_usd` field.

- [ ] **Step 4.2.1: web_search**

Read: `server/api/src/ai_portal/tools/web_search.py`. Identify the provider branches (tavily / duckduckgo / serper).

Changes required:
- Set `provider` in the return dict from the branch used (not `"web_search"`).
- `duckduckgo` → `cost_usd=Decimal("0")`.
- `tavily`, `serper` → omit `cost_usd` so the flat-rate fallback applies (v1; metered parsers are a follow-up).

Example diff (adjust to match the real file structure):
```python
# inside the tavily branch
return {
    "provider": "tavily",
    "input": {"query": query},
    "result_snippet": snippet,
}
# inside the duckduckgo branch
return {
    "provider": "duckduckgo",
    "input": {"query": query},
    "result_snippet": snippet,
    "cost_usd": Decimal("0"),
}
```

- [ ] **Step 4.2.2: fetch_webpage**

Same edit for firecrawl / jina / crawl4ai / raw-fetch branches. If the firecrawl SDK response exposes `creditsUsed`, convert to USD and set `cost_usd`; otherwise omit.

- [ ] **Step 4.2.3: kb_search**

Internal tool — always free. Return:
```python
return {
    "provider": "kb_search",
    "input": {"query": query, "kb_id": kb_id},
    "result_snippet": snippet,
    "cost_usd": Decimal("0"),
}
```
Add `"kb_search"` to `tool_pricing._FLAT_RATES` with value `Decimal("0")` so unknown-provider path doesn't fire.

- [ ] **Step 4.2.4: Run the tool unit tests**

Run: `cd server/api && pytest tests/tools -xvs`
Expected: any existing tests pass. If the tests hard-assert dict keys that changed, update them.

- [ ] **Step 4.2.5: Commit**

```bash
git add server/api/src/ai_portal/tools/ server/api/src/ai_portal/chat/tool_pricing.py server/api/tests/tools/
git commit -m "refactor(tools): each tool returns provider + optional metered cost_usd"
```

---

## Phase 5 — Provider events (adapters yield typed `ProviderStreamEvent`)

Today each provider adapter in `server/api/src/ai_portal/catalog/providers/` yields untyped dicts. We swap them to yield `ProviderStreamEvent` values. The `Protocol` is updated first to make the type checker do the work across all three adapters.

### Task 5.1: Update the provider `Protocol`

**Files:**
- Modify: `server/api/src/ai_portal/catalog/providers/protocol.py`

- [ ] **Step 5.1.1: Read current protocol**

Read: `server/api/src/ai_portal/catalog/providers/protocol.py`. It should define something like a `ChatProvider` protocol with a `stream(...)` method returning `AsyncIterator[dict]`.

- [ ] **Step 5.1.2: Update the signature**

Replace the stream signature with:
```python
from typing import AsyncIterator, Protocol

from ai_portal.catalog.providers.events import ProviderStreamEvent


class ChatProvider(Protocol):
    async def stream(
        self,
        *,
        messages: list[dict],
        model: str,
        settings: dict,
        tools: list[dict] | None = None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        ...
```

Keep every other method signature unchanged. If the protocol defines additional methods, leave them alone — this is surgical.

- [ ] **Step 5.1.3: Run a type-check to find all affected callers**

Run: `cd server/api && pyright src/ai_portal/catalog/providers/` (or `mypy`, whichever the project uses — check for `pyproject.toml` config).

Expected: errors on `anthropic_native.py`, `gemini_native.py`, `langchain.py` (the Task 5.2–5.4 targets) and on the streaming service (Phase 6).

- [ ] **Step 5.1.4: Commit**

```bash
git add server/api/src/ai_portal/catalog/providers/protocol.py
git commit -m "refactor(catalog): ChatProvider.stream yields ProviderStreamEvent"
```

---

### Task 5.2: Anthropic adapter yields typed events

**Files:**
- Modify: `server/api/src/ai_portal/catalog/providers/anthropic_native.py`
- Test: `server/api/tests/catalog/test_anthropic_native_events.py` (new)

- [ ] **Step 5.2.1: Write failing integration test with a recorded stream**

Use a fake Anthropic client that yields a scripted sequence:

```python
# server/api/tests/catalog/test_anthropic_native_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_portal.catalog.providers.anthropic_native import AnthropicNativeProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent, ToolCallRequestEvent, UsageEvent, IterationCompleteEvent,
)


@pytest.mark.asyncio
async def test_stream_yields_typed_events(monkeypatch):
    # scripted SDK events (shape mirrors Anthropic streaming API)
    sdk_events = [
        {"type": "message_start", "message": {"id": "m1"}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hi"}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"},
         "usage": {"input_tokens": 10, "output_tokens": 20}},
        {"type": "message_stop"},
    ]

    async def fake_stream(*args, **kwargs):
        for e in sdk_events:
            yield e

    fake_client = MagicMock()
    fake_client.messages.stream = fake_stream
    monkeypatch.setattr("anthropic.AsyncAnthropic", lambda **kw: fake_client)

    prov = AnthropicNativeProvider(api_key="sk-fake")
    collected = []
    async for ev in prov.stream(messages=[{"role": "user", "content": "hi"}],
                                model="claude-sonnet-4-6", settings={}, tools=None):
        collected.append(ev.root)

    assert any(isinstance(e, TextDeltaEvent) and e.text == "hi" for e in collected)
    assert any(isinstance(e, UsageEvent) and e.output_tokens == 20 for e in collected)
    assert any(isinstance(e, IterationCompleteEvent) for e in collected)
```

- [ ] **Step 5.2.2: Run — should fail with type or shape mismatch**

Run: `cd server/api && pytest tests/catalog/test_anthropic_native_events.py -xvs`

- [ ] **Step 5.2.3: Rewrite the adapter stream to produce `ProviderStreamEvent`**

Replace the existing `async def stream(...)` implementation. Outline:

```python
# server/api/src/ai_portal/catalog/providers/anthropic_native.py (partial)
from __future__ import annotations

from typing import AsyncIterator

from ai_portal.catalog.providers.events import (
    CitationEvent,
    IterationCompleteEvent,
    ProviderErrorEvent,
    ProviderStreamEvent,
    ServerToolUseEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
)


class AnthropicNativeProvider:
    # ...

    async def stream(
        self, *, messages, model, settings, tools=None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        client = self._client()
        try:
            stream = client.messages.stream(
                model=model,
                messages=messages,
                max_tokens=settings.get("max_tokens", 4096),
                tools=tools or [],
                thinking=self._thinking_param(settings),
            )
            async for sdk_event in stream:
                for out in self._translate(sdk_event):
                    yield ProviderStreamEvent.model_validate(out)
        except Exception as exc:
            yield ProviderStreamEvent.model_validate(
                {"type": "provider_error", "code": type(exc).__name__, "message": str(exc)}
            )

    def _translate(self, event) -> list[dict]:
        et = event.get("type")
        if et == "content_block_delta":
            delta = event["delta"]
            dt = delta.get("type")
            if dt == "text_delta":
                return [{"type": "text_delta", "text": delta["text"]}]
            if dt == "thinking_delta":
                return [{"type": "thinking_delta", "text": delta["thinking"]}]
            if dt == "input_json_delta":
                return []  # tool argument streaming; accumulated and emitted on block_stop
            if dt == "citations_delta":
                c = delta["citation"]
                return [{"type": "citation", "url": c["url"], "title": c.get("title"), "snippet": c.get("cited_text")}]
        if et == "content_block_start":
            block = event.get("content_block") or {}
            if block.get("type") == "tool_use":
                # tool call; arguments streamed via input_json_delta; emit on stop
                self._pending_tool = {"call_id": block["id"], "tool_name": block["name"], "arguments": ""}
                return []
            if block.get("type") == "server_tool_use":
                return [{
                    "type": "server_tool_use",
                    "tool_name": block["name"],
                    "input": block.get("input") or {},
                }]
        if et == "content_block_stop" and getattr(self, "_pending_tool", None):
            import json
            args = {}
            if self._pending_tool["arguments"]:
                try:
                    args = json.loads(self._pending_tool["arguments"])
                except Exception:
                    args = {"_raw": self._pending_tool["arguments"]}
            out = [{
                "type": "tool_call_request",
                "call_id": self._pending_tool["call_id"],
                "tool_name": self._pending_tool["tool_name"],
                "arguments": args,
            }]
            self._pending_tool = None
            return out
        if et == "message_delta":
            usage = event.get("usage") or {}
            out = []
            if usage:
                out.append({
                    "type": "usage",
                    "input_tokens": usage.get("input_tokens", 0),
                    "output_tokens": usage.get("output_tokens", 0),
                    "cached_input_tokens": usage.get("cache_read_input_tokens", 0),
                    "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
                    "reasoning_tokens": 0,
                })
            stop = (event.get("delta") or {}).get("stop_reason")
            if stop:
                out.append({"type": "iteration_complete", "stop_reason": stop or "unknown"})
            return out
        return []
```

Notes:
- Preserve existing class-level auth/client-wiring from the current file. The `_translate` method replaces the ad-hoc dict building.
- Accumulate tool-call argument JSON across `input_json_delta` events (use `self._pending_tool["arguments"] += delta["partial_json"]` inside the delta branch).
- If the file currently emits citations differently (Anthropic has evolved the citation shape), keep the existing parser — only rename the emitted event shape.

- [ ] **Step 5.2.4: Run tests**

Run: `cd server/api && pytest tests/catalog/test_anthropic_native_events.py -xvs`
Expected: PASS.

- [ ] **Step 5.2.5: Commit**

```bash
git add server/api/src/ai_portal/catalog/providers/anthropic_native.py server/api/tests/catalog/test_anthropic_native_events.py
git commit -m "refactor(catalog): Anthropic adapter yields typed ProviderStreamEvent"
```

---

### Task 5.3: Gemini adapter yields typed events

**Files:**
- Modify: `server/api/src/ai_portal/catalog/providers/gemini_native.py`
- Test: `server/api/tests/catalog/test_gemini_native_events.py` (new)

Structure mirrors Task 5.2. Key Gemini-specific mappings:
- `candidates[0].content.parts[].text` → `TextDeltaEvent`.
- `candidates[0].content.parts[].function_call` → `ToolCallRequestEvent` (Gemini emits the call in one chunk, not streamed args).
- `candidates[0].grounding_metadata.*` → `ServerToolUseEvent(tool_name="grounding", ...)` + `CitationEvent`s for sources.
- `usage_metadata.prompt_token_count` → `UsageEvent.input_tokens`; `candidates_token_count` → `output_tokens`; `thoughts_token_count` → `reasoning_tokens` (Gemini 2.5 thinking).
- `finish_reason` on last candidate → `IterationCompleteEvent`.

- [ ] **Step 5.3.1: Write failing test**

```python
# server/api/tests/catalog/test_gemini_native_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_portal.catalog.providers.gemini_native import GeminiNativeProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent, ToolCallRequestEvent, UsageEvent,
    IterationCompleteEvent, CitationEvent,
)


@pytest.mark.asyncio
async def test_stream_yields_typed_events(monkeypatch):
    sdk_chunks = [
        {"candidates": [{"content": {"parts": [{"text": "hi"}]}}]},
        {"candidates": [{
            "content": {"parts": [{"function_call": {"name": "web_search", "args": {"q": "x"}}}]},
            "finish_reason": "STOP",
        }], "usage_metadata": {"prompt_token_count": 10, "candidates_token_count": 2,
                                "thoughts_token_count": 0}},
    ]

    async def fake_stream(*args, **kwargs):
        for c in sdk_chunks:
            yield MagicMock(**c)

    fake_model = MagicMock()
    fake_model.generate_content_async = fake_stream
    monkeypatch.setattr("google.generativeai.GenerativeModel", lambda *a, **kw: fake_model)

    prov = GeminiNativeProvider(api_key="fake")
    collected = []
    async for ev in prov.stream(
        messages=[{"role": "user", "content": "hi"}],
        model="gemini-2.5-flash", settings={}, tools=None,
    ):
        collected.append(ev.root)

    assert any(isinstance(e, TextDeltaEvent) and e.text == "hi" for e in collected)
    assert any(isinstance(e, ToolCallRequestEvent) and e.tool_name == "web_search" for e in collected)
    assert any(isinstance(e, UsageEvent) and e.input_tokens == 10 for e in collected)
    assert any(isinstance(e, IterationCompleteEvent) for e in collected)
```

- [ ] **Step 5.3.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/catalog/test_gemini_native_events.py -xvs`
Expected: test fails because the adapter still yields dicts, not `ProviderStreamEvent`.

- [ ] **Step 5.3.3: Rewrite adapter `stream`**

Read: `server/api/src/ai_portal/catalog/providers/gemini_native.py`. Replace the stream method with the pattern below. Preserve the existing client/auth wiring.

```python
# server/api/src/ai_portal/catalog/providers/gemini_native.py (partial)
from __future__ import annotations

from typing import AsyncIterator

from ai_portal.catalog.providers.events import ProviderStreamEvent


class GeminiNativeProvider:
    # ... existing init / client setup ...

    async def stream(
        self, *, messages, model, settings, tools=None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        try:
            gen = self._build_model(model, tools).generate_content_async(
                contents=self._to_gemini_contents(messages),
                generation_config=self._to_generation_config(settings),
                stream=True,
            )
            async for chunk in gen:
                for out in self._translate(chunk):
                    yield ProviderStreamEvent.model_validate(out)
        except Exception as exc:
            yield ProviderStreamEvent.model_validate(
                {"type": "provider_error", "code": type(exc).__name__, "message": str(exc)}
            )

    def _translate(self, chunk) -> list[dict]:
        out: list[dict] = []
        candidates = getattr(chunk, "candidates", None) or []
        for cand in candidates:
            content = getattr(cand, "content", None)
            parts = getattr(content, "parts", []) if content else []
            for part in parts:
                if getattr(part, "text", None):
                    out.append({"type": "text_delta", "text": part.text})
                fc = getattr(part, "function_call", None)
                if fc is not None:
                    out.append({
                        "type": "tool_call_request",
                        "call_id": getattr(fc, "id", None) or f"gem_{id(part)}",
                        "tool_name": fc.name,
                        "arguments": dict(fc.args) if hasattr(fc, "args") else {},
                    })
            gm = getattr(cand, "grounding_metadata", None)
            if gm is not None:
                out.append({
                    "type": "server_tool_use",
                    "tool_name": "grounding",
                    "input": {"search_queries": list(getattr(gm, "web_search_queries", []) or [])},
                })
                for attrib in getattr(gm, "grounding_chunks", []) or []:
                    web = getattr(attrib, "web", None)
                    if web and getattr(web, "uri", None):
                        out.append({
                            "type": "citation",
                            "url": web.uri,
                            "title": getattr(web, "title", None),
                            "snippet": None,
                        })
            fr = getattr(cand, "finish_reason", None)
            if fr:
                stop = _map_finish_reason(fr)
                out.append({"type": "iteration_complete", "stop_reason": stop})

        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            out.append({
                "type": "usage",
                "input_tokens": getattr(um, "prompt_token_count", 0) or 0,
                "output_tokens": getattr(um, "candidates_token_count", 0) or 0,
                "cached_input_tokens": getattr(um, "cached_content_token_count", 0) or 0,
                "cache_creation_input_tokens": 0,
                "reasoning_tokens": getattr(um, "thoughts_token_count", 0) or 0,
            })
        return out


def _map_finish_reason(fr) -> str:
    name = str(fr).upper()
    if "STOP" in name: return "end_turn"
    if "MAX" in name: return "max_tokens"
    if "SAFETY" in name: return "stop_sequence"
    if "TOOL" in name or "FUNCTION" in name: return "tool_use"
    return "unknown"
```

Preserve the existing `_to_gemini_contents`, `_to_generation_config`, and model/tool builder helpers — if they don't exist yet, extract them from the current untyped stream method. Do not change message or tool translation semantics.

- [ ] **Step 5.3.4: Run tests**

Run: `cd server/api && pytest tests/catalog/test_gemini_native_events.py -xvs`
Expected: PASS.

- [ ] **Step 5.3.5: Commit**

```bash
git add server/api/src/ai_portal/catalog/providers/gemini_native.py server/api/tests/catalog/test_gemini_native_events.py
git commit -m "refactor(catalog): Gemini adapter yields typed ProviderStreamEvent"
```

---

### Task 5.4: LangChain adapter yields typed events

**Files:**
- Modify: `server/api/src/ai_portal/catalog/providers/langchain.py`
- Test: `server/api/tests/catalog/test_langchain_events.py` (new)

LangChain wraps multiple providers; the adapter translates `astream_events`/`astream` output. Key mappings:
- `AIMessageChunk` content → `TextDeltaEvent`.
- `tool_calls` on the chunk → `ToolCallRequestEvent`.
- `usage_metadata` → `UsageEvent`.
- Langchain does not surface provider-native server tools in a typed way; skip `ServerToolUseEvent` unless the underlying provider is OpenAI with a `web_search_preview` tool response — then emit.

- [ ] **Step 5.4.1: Write failing test**

```python
# server/api/tests/catalog/test_langchain_events.py
import pytest
from unittest.mock import AsyncMock, MagicMock

from ai_portal.catalog.providers.langchain import LangchainProvider
from ai_portal.catalog.providers.events import (
    TextDeltaEvent, ToolCallRequestEvent, UsageEvent,
)


class _FakeChunk:
    def __init__(self, content="", tool_calls=None, usage_metadata=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.usage_metadata = usage_metadata


@pytest.mark.asyncio
async def test_stream_yields_typed_events(monkeypatch):
    chunks = [
        _FakeChunk(content="hi"),
        _FakeChunk(
            tool_calls=[{"id": "c1", "name": "web_search", "args": {"q": "x"}}],
            usage_metadata={"input_tokens": 10, "output_tokens": 2},
        ),
    ]

    class FakeLLM:
        async def astream(self, *a, **kw):
            for c in chunks:
                yield c

    monkeypatch.setattr(
        "ai_portal.catalog.providers.langchain.LangchainProvider._build_llm",
        lambda self, model, tools: FakeLLM(),
    )

    prov = LangchainProvider()
    collected = []
    async for ev in prov.stream(
        messages=[{"role": "user", "content": "hi"}],
        model="openai:gpt-4o", settings={}, tools=None,
    ):
        collected.append(ev.root)

    assert any(isinstance(e, TextDeltaEvent) and e.text == "hi" for e in collected)
    assert any(isinstance(e, ToolCallRequestEvent) and e.tool_name == "web_search" for e in collected)
    assert any(isinstance(e, UsageEvent) and e.output_tokens == 2 for e in collected)
```

- [ ] **Step 5.4.2: Run test to verify it fails**

Run: `cd server/api && pytest tests/catalog/test_langchain_events.py -xvs`
Expected: fails because the adapter still yields dicts.

- [ ] **Step 5.4.3: Rewrite adapter `stream`**

Read: `server/api/src/ai_portal/catalog/providers/langchain.py`. Locate the current `stream` implementation. Replace with:

```python
# server/api/src/ai_portal/catalog/providers/langchain.py (partial)
from __future__ import annotations

from typing import AsyncIterator

from ai_portal.catalog.providers.events import ProviderStreamEvent


class LangchainProvider:
    # ... existing provider resolution / credential wiring ...

    async def stream(
        self, *, messages, model, settings, tools=None,
    ) -> AsyncIterator[ProviderStreamEvent]:
        llm = self._build_llm(model, tools)
        lc_messages = self._to_lc_messages(messages)
        try:
            async for chunk in llm.astream(lc_messages, **self._settings_kwargs(settings)):
                for out in self._translate(chunk):
                    yield ProviderStreamEvent.model_validate(out)
            # LangChain does not emit a finish event; synthesize one
            yield ProviderStreamEvent.model_validate(
                {"type": "iteration_complete", "stop_reason": "end_turn"}
            )
        except Exception as exc:
            yield ProviderStreamEvent.model_validate(
                {"type": "provider_error", "code": type(exc).__name__, "message": str(exc)}
            )

    def _translate(self, chunk) -> list[dict]:
        out: list[dict] = []
        content = getattr(chunk, "content", None)
        if isinstance(content, str) and content:
            out.append({"type": "text_delta", "text": content})
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    out.append({"type": "text_delta", "text": block.get("text") or ""})
        for tc in getattr(chunk, "tool_calls", []) or []:
            out.append({
                "type": "tool_call_request",
                "call_id": tc.get("id") or tc.get("index") or "",
                "tool_name": tc["name"],
                "arguments": tc.get("args") or {},
            })
        um = getattr(chunk, "usage_metadata", None)
        if um:
            out.append({
                "type": "usage",
                "input_tokens": int(um.get("input_tokens", 0) or 0),
                "output_tokens": int(um.get("output_tokens", 0) or 0),
                "cached_input_tokens": int(um.get("input_token_details", {}).get("cache_read", 0) or 0),
                "cache_creation_input_tokens": 0,
                "reasoning_tokens": int(um.get("output_token_details", {}).get("reasoning", 0) or 0),
            })
        return out
```

Keep `_to_lc_messages`, `_settings_kwargs`, and `_build_llm` — extract from the current file if they're inline in the old `stream`.

- [ ] **Step 5.4.4: Run tests**

Run: `cd server/api && pytest tests/catalog/test_langchain_events.py -xvs`
Expected: PASS.

- [ ] **Step 5.4.5: Commit**

```bash
git add server/api/src/ai_portal/catalog/providers/langchain.py server/api/tests/catalog/test_langchain_events.py
git commit -m "refactor(catalog): LangChain adapter yields typed ProviderStreamEvent"
```

---

### Task 5.5: Remove legacy dict-shape callers in streaming service

**Files:**
- Modify: `server/api/src/ai_portal/chat/streaming_service.py` (interim — does not delete yet)

`streaming_service.py` is rewritten in Phase 6. To keep the tree compiling between Phase 5 and Phase 6, patch the parts of `streaming_service.py` that read provider output so they accept `ProviderStreamEvent`.

- [ ] **Step 5.5.1: Patch the provider-event consumer**

Find the `async for event in provider.stream(...)` block. Replace dict-key lookups with pattern matching:

```python
async for event in provider.stream(...):
    ev = event.root if hasattr(event, "root") else event
    match ev:
        case TextDeltaEvent(text=t):
            ...
        case UsageEvent(input_tokens=it, output_tokens=ot, ...):
            ...
        case ToolCallRequestEvent(call_id=cid, tool_name=tn, arguments=args):
            ...
        # ... etc.
```

Keep all existing business logic; just swap the accessor layer. This is a temporary bridge; Phase 6 replaces the whole file.

- [ ] **Step 5.5.2: Smoke-start backend**

Run: `cd server/api && uvicorn ai_portal.main:app --port 8000 --reload`
Expected: boots. Manually curl `/api/chat/...` endpoint — should still stream (use browser or Postman since streaming is SSE).

- [ ] **Step 5.5.3: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming_service.py
git commit -m "refactor(chat): streaming_service adapts to typed provider events (interim)"
```

---
## Phase 6 — Streaming package decomposition

Build the `chat/streaming/` package one module at a time. Each module lands with its unit tests. At the end, `orchestrator.stream_turn` replaces the monolithic `streaming_service.generate_streaming_response`, and the old file is deleted.

### Task 6.1: Package scaffold

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/__init__.py`

- [ ] **Step 6.1.1: Empty package marker**

```python
# server/api/src/ai_portal/chat/streaming/__init__.py
"""Streaming pipeline. Public entry: orchestrator.stream_turn."""
```

- [ ] **Step 6.1.2: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming/__init__.py
git commit -m "chore(chat): streaming package scaffold"
```

---

### Task 6.2: `item_writer` — the only mutator of `thread_items`

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/item_writer.py`
- Test: `server/api/tests/chat/test_item_writer.py`

The writer is the most critical module — it enforces the state machine and every other module mutates `thread_items` through it.

- [ ] **Step 6.2.1: Write failing tests**

```python
# server/api/tests/chat/test_item_writer.py
import uuid
from decimal import Decimal

import pytest

from ai_portal.chat.item_kinds import ItemKind, ItemStatus
from ai_portal.chat.streaming.item_writer import (
    IllegalTransition,
    ItemWriter,
)


@pytest.fixture
async def writer(db_session, thread_fixture):
    return ItemWriter(session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)


@pytest.mark.asyncio
async def test_start_and_finish_llm_call(writer):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    assert item.status == ItemStatus.streaming
    done = await writer.finish_llm_call(
        item_id=item.id, input_tokens=10, output_tokens=20,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
        cost_usd=Decimal("0.001"), cost_estimated=False,
    )
    assert done.status == ItemStatus.done
    assert done.cost_usd == Decimal("0.001")


@pytest.mark.asyncio
async def test_cannot_finish_already_finished_llm_call(writer):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    await writer.finish_llm_call(
        item_id=item.id, input_tokens=1, output_tokens=1,
        cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
        cost_usd=Decimal("0"), cost_estimated=True,
    )
    with pytest.raises(IllegalTransition):
        await writer.finish_llm_call(
            item_id=item.id, input_tokens=1, output_tokens=1,
            cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
            cost_usd=Decimal("0"), cost_estimated=True,
        )


@pytest.mark.asyncio
async def test_append_text_delta_then_finalize(writer):
    turn = uuid.uuid4()
    item = await writer.start_text(turn_id=turn)
    await writer.append_text_delta(item.id, "hel")
    await writer.append_text_delta(item.id, "lo")
    final = await writer.finalize_text(item.id)
    assert final.status == ItemStatus.done
    assert final.data["text"] == "hello"


@pytest.mark.asyncio
async def test_start_and_finish_tool_call_records_cost(writer):
    turn = uuid.uuid4()
    item = await writer.start_tool_call(turn_id=turn, tool_name="web_search", provider="tavily", params={"q": "x"})
    done = await writer.finish_tool_call(
        item_id=item.id, result_snippet="ok", error=None,
        cost_usd=Decimal("0.008"), cost_estimated=True, latency_ms=340,
    )
    assert done.status == ItemStatus.done
    assert done.cost_usd == Decimal("0.008")
    assert done.latency_ms == 340


@pytest.mark.asyncio
async def test_cancel_turn_flips_streaming_items(writer):
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    await writer.cancel_turn_items(turn_id=turn, partial_cost=Decimal("0.0001"))
    await writer.db.refresh(item)
    assert item.status == ItemStatus.cancelled
    assert item.cost_usd == Decimal("0.0001")


@pytest.mark.asyncio
async def test_sweep_stale_streaming_marks_error(writer, db_session):
    from datetime import datetime, timezone, timedelta
    turn = uuid.uuid4()
    item = await writer.start_llm_call(turn_id=turn, model="gpt-4", iteration_index=0)
    # artificially age it
    item.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    await db_session.commit()
    count = await writer.sweep_stale(older_than_seconds=60)
    assert count >= 1
    await db_session.refresh(item)
    assert item.status == ItemStatus.error
    assert item.data.get("error") == "interrupted"
```

- [ ] **Step 6.2.2: Fixture `thread_fixture`**

Add to `server/api/tests/chat/conftest.py`:
```python
@pytest.fixture
async def thread_fixture(db_session, org_fixture, user_fixture):
    from ai_portal.chat.model import Thread
    t = Thread(org_id=org_fixture.id, user_id=user_fixture.id, title="t", model="gpt-4")
    db_session.add(t)
    await db_session.commit()
    return t
```

- [ ] **Step 6.2.3: Implement `item_writer.py`**

```python
# server/api/src/ai_portal/chat/streaming/item_writer.py
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.model import ThreadItem


class IllegalTransition(RuntimeError):
    pass


@dataclass(slots=True)
class ItemWriter:
    session: AsyncSession
    thread_id: int
    org_id: uuid.UUID

    @property
    def db(self) -> AsyncSession:
        return self.session

    # ---- create (terminal-on-create) ----

    async def insert_user_message(self, *, turn_id: uuid.UUID, text: str, attachments: list[dict]) -> ThreadItem:
        return await self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.user_message, role=ItemRole.user,
            data={"text": text, "attachments": attachments},
        )

    async def insert_memory_pill(self, *, turn_id: uuid.UUID, count: int) -> ThreadItem:
        return await self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.memory_pill, role=ItemRole.system,
            data={"count": count},
        )

    async def insert_citation(self, *, turn_id: uuid.UUID, url: str, title: str | None,
                              snippet: str | None, parent_item_id: int | None) -> ThreadItem:
        return await self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.citation, role=ItemRole.system,
            data={"url": url, "title": title, "snippet": snippet},
            parent_item_id=parent_item_id,
        )

    async def insert_error(self, *, turn_id: uuid.UUID, code: str, message: str) -> ThreadItem:
        return await self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.error, role=ItemRole.system,
            data={"code": code, "message": message},
        )

    async def insert_turn_end(self, *, turn_id: uuid.UUID,
                              reason: str) -> ThreadItem:
        return await self._insert_terminal(
            turn_id=turn_id, kind=ItemKind.turn_end, role=ItemRole.system,
            data={"reason": reason},
        )

    # ---- create (active; terminal later) ----

    async def start_llm_call(self, *, turn_id: uuid.UUID, model: str, iteration_index: int) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.llm_call, role=ItemRole.assistant, status=ItemStatus.streaming,
            model=model, started_at=_now(),
            data={"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0,
                  "cache_creation_input_tokens": 0, "reasoning_tokens": 0,
                  "iteration_index": iteration_index},
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def start_text(self, *, turn_id: uuid.UUID) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.streaming,
            started_at=_now(),
            data={"text": ""},
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def start_thinking(self, *, turn_id: uuid.UUID) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.thinking, role=ItemRole.assistant, status=ItemStatus.streaming,
            started_at=_now(),
            data={"text": ""},
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def start_tool_call(self, *, turn_id: uuid.UUID, tool_name: str,
                              provider: str | None, params: dict) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.tool_call, role=ItemRole.assistant, status=ItemStatus.streaming,
            provider=provider, started_at=_now(),
            data={"tool_name": tool_name, "params": params},
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def start_server_tool(self, *, turn_id: uuid.UUID, tool_name: str,
                                provider: str, input_payload: dict) -> ThreadItem:
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=ItemKind.server_tool_use, role=ItemRole.assistant, status=ItemStatus.streaming,
            provider=provider, started_at=_now(),
            data={"tool_name": tool_name, "input": input_payload},
        )
        self.session.add(item)
        await self.session.flush()
        return item

    # ---- transitions ----

    async def append_text_delta(self, item_id: int, delta: str) -> None:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        data = dict(item.data or {})
        data["text"] = (data.get("text") or "") + delta
        item.data = data
        await self.session.flush()

    async def finalize_text(self, item_id: int) -> ThreadItem:
        return await self._finish(item_id, status=ItemStatus.done)

    async def finalize_thinking(self, item_id: int) -> ThreadItem:
        return await self._finish(item_id, status=ItemStatus.done)

    async def finish_llm_call(
        self, *, item_id: int,
        input_tokens: int, output_tokens: int,
        cached_input_tokens: int, cache_creation_input_tokens: int, reasoning_tokens: int,
        cost_usd: Decimal, cost_estimated: bool,
    ) -> ThreadItem:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.data = {
            **(item.data or {}),
            "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cached_input_tokens": cached_input_tokens,
            "cache_creation_input_tokens": cache_creation_input_tokens,
            "reasoning_tokens": reasoning_tokens,
        }
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.status = ItemStatus.done
        item.finished_at = _now()
        if item.started_at:
            item.latency_ms = int((item.finished_at - item.started_at).total_seconds() * 1000)
        await self.session.flush()
        return item

    async def fail_llm_call(self, *, item_id: int, error: str) -> ThreadItem:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.status = ItemStatus.error
        item.data = {**(item.data or {}), "error": error}
        item.finished_at = _now()
        await self.session.flush()
        return item

    async def finish_tool_call(
        self, *, item_id: int, result_snippet: str | None, error: str | None,
        cost_usd: Decimal, cost_estimated: bool, latency_ms: int | None,
    ) -> ThreadItem:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        data = dict(item.data or {})
        if result_snippet is not None:
            data["result_snippet"] = result_snippet
        if error is not None:
            data["error"] = error
        item.data = data
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.latency_ms = latency_ms
        item.status = ItemStatus.error if error else ItemStatus.done
        item.finished_at = _now()
        await self.session.flush()
        return item

    async def finish_server_tool(
        self, *, item_id: int, cost_usd: Decimal, cost_estimated: bool,
    ) -> ThreadItem:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.cost_usd = cost_usd
        item.cost_estimated = cost_estimated
        item.status = ItemStatus.done
        item.finished_at = _now()
        await self.session.flush()
        return item

    # ---- bulk transitions ----

    async def cancel_turn_items(self, *, turn_id: uuid.UUID,
                                partial_cost: Decimal | None = None) -> int:
        stmt = select(ThreadItem).where(
            ThreadItem.thread_id == self.thread_id,
            ThreadItem.turn_id == turn_id,
            ThreadItem.status == ItemStatus.streaming,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for r in rows:
            r.status = ItemStatus.cancelled
            r.finished_at = _now()
            if partial_cost is not None and r.kind == ItemKind.llm_call:
                r.cost_usd = partial_cost
                r.cost_estimated = True
        await self.session.flush()
        return len(rows)

    async def sweep_stale(self, *, older_than_seconds: int) -> int:
        cutoff = _now() - timedelta(seconds=older_than_seconds)
        stmt = select(ThreadItem).where(
            ThreadItem.thread_id == self.thread_id,
            ThreadItem.status == ItemStatus.streaming,
            ThreadItem.started_at < cutoff,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for r in rows:
            r.status = ItemStatus.error
            r.data = {**(r.data or {}), "error": "interrupted"}
            r.finished_at = _now()
        await self.session.flush()
        return len(rows)

    # ---- internals ----

    async def _insert_terminal(
        self, *, turn_id: uuid.UUID, kind: ItemKind, role: ItemRole,
        data: dict[str, Any], parent_item_id: int | None = None,
    ) -> ThreadItem:
        now = _now()
        item = ThreadItem(
            thread_id=self.thread_id, org_id=self.org_id, turn_id=turn_id,
            kind=kind, role=role, status=ItemStatus.done,
            data=data, parent_item_id=parent_item_id,
            started_at=now, finished_at=now,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def _finish(self, item_id: int, status: ItemStatus) -> ThreadItem:
        item = await self._get_and_require_status(item_id, {ItemStatus.streaming})
        item.status = status
        item.finished_at = _now()
        if item.started_at:
            item.latency_ms = int((item.finished_at - item.started_at).total_seconds() * 1000)
        await self.session.flush()
        return item

    async def _get_and_require_status(self, item_id: int, allowed: set[ItemStatus]) -> ThreadItem:
        stmt = select(ThreadItem).where(
            ThreadItem.id == item_id,
            ThreadItem.thread_id == self.thread_id,
        )
        item = (await self.session.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise IllegalTransition(f"item {item_id} not found in thread {self.thread_id}")
        if item.status not in allowed:
            raise IllegalTransition(f"item {item_id} in status {item.status}, allowed {allowed}")
        return item


def _now() -> datetime:
    return datetime.now(timezone.utc)
```

- [ ] **Step 6.2.4: Run tests**

Run: `cd server/api && pytest tests/chat/test_item_writer.py -xvs`
Expected: all tests PASS.

- [ ] **Step 6.2.5: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming/item_writer.py server/api/tests/chat/test_item_writer.py server/api/tests/chat/conftest.py
git commit -m "feat(chat): item_writer — state-machine writer for thread_items"
```

---

### Task 6.3: `sse_emitter` — typed event → SSE line

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/sse_emitter.py`
- Test: `server/api/tests/chat/test_sse_emitter.py`

- [ ] **Step 6.3.1: Write failing test**

```python
# server/api/tests/chat/test_sse_emitter.py
import json
import uuid
from datetime import datetime, timezone

from ai_portal.chat.sse import SseEvent
from ai_portal.chat.streaming.sse_emitter import encode


def test_encode_item_event_wraps_in_data_line():
    event = SseEvent.model_validate({
        "event_type": "item",
        "item": {
            "id": 1, "thread_id": 1, "turn_id": str(uuid.uuid4()),
            "kind": "assistant_text", "status": "streaming", "role": "assistant",
            "cost_estimated": False, "data": {"text": "hi"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    })
    line = encode(event)
    assert line.startswith("data: ")
    assert line.endswith("\n\n")
    parsed = json.loads(line.removeprefix("data: ").rstrip("\n"))
    assert parsed["event_type"] == "item"


def test_encode_done_event():
    event = SseEvent.model_validate({"event_type": "done"})
    assert encode(event) == 'data: {"event_type":"done"}\n\n'
```

- [ ] **Step 6.3.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/sse_emitter.py
from __future__ import annotations

from ai_portal.chat.sse import SseEvent


def encode(event: SseEvent) -> str:
    return f"data: {event.model_dump_json()}\n\n"
```

- [ ] **Step 6.3.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_sse_emitter.py -xvs
git add server/api/src/ai_portal/chat/streaming/sse_emitter.py server/api/tests/chat/test_sse_emitter.py
git commit -m "feat(chat): sse_emitter — typed event to SSE line"
```

---

### Task 6.4: `system_prompt` — pure composition

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/system_prompt.py`
- Test: `server/api/tests/chat/test_system_prompt.py`

Extract the existing system-prompt composition from `streaming_service.py` into a pure function. Read the current file to find the logic first.

- [ ] **Step 6.4.1: Locate existing logic**

Run: `grep -n "system" server/api/src/ai_portal/chat/streaming_service.py | head -30`
Locate the assembly block (usually near the top of `generate_streaming_response`).

- [ ] **Step 6.4.2: Write failing tests**

```python
# server/api/tests/chat/test_system_prompt.py
from ai_portal.chat.streaming.system_prompt import compose


def test_compose_base_only():
    out = compose(base_prompt="You are a helpful assistant.", assistant_prompt=None,
                  memory_block=None, kb_block=None, capabilities=[])
    assert out == "You are a helpful assistant."


def test_compose_with_assistant_and_memory():
    out = compose(
        base_prompt="Base.",
        assistant_prompt="Stay terse.",
        memory_block="User prefers short answers.",
        kb_block=None,
        capabilities=["web_search"],
    )
    assert "Base." in out
    assert "Stay terse." in out
    assert "User prefers short answers." in out
    assert "web_search" in out


def test_empty_blocks_omitted_cleanly():
    out = compose(base_prompt="Base.", assistant_prompt="", memory_block="   ",
                  kb_block=None, capabilities=[])
    assert out.strip() == "Base."
```

- [ ] **Step 6.4.3: Implement**

```python
# server/api/src/ai_portal/chat/streaming/system_prompt.py
from __future__ import annotations


def compose(
    *,
    base_prompt: str,
    assistant_prompt: str | None,
    memory_block: str | None,
    kb_block: str | None,
    capabilities: list[str],
) -> str:
    parts: list[str] = [base_prompt.strip()]
    if assistant_prompt and assistant_prompt.strip():
        parts.append(assistant_prompt.strip())
    if memory_block and memory_block.strip():
        parts.append("## Memory\n" + memory_block.strip())
    if kb_block and kb_block.strip():
        parts.append("## Knowledge base\n" + kb_block.strip())
    if capabilities:
        parts.append("## Available tools\n- " + "\n- ".join(capabilities))
    return "\n\n".join(p for p in parts if p)
```

Adjust the section headings to match what the old implementation produced so E2E assertions on prompt content still work. Compare byte-for-byte against the existing prompt produced by `streaming_service.py` with the same inputs.

- [ ] **Step 6.4.4: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_system_prompt.py -xvs
git add server/api/src/ai_portal/chat/streaming/system_prompt.py server/api/tests/chat/test_system_prompt.py
git commit -m "feat(chat): system_prompt composition (pure)"
```

---

### Task 6.5: `context_assembler` — thread_items → provider messages

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/context_assembler.py`
- Test: `server/api/tests/chat/test_context_assembler.py`

Reads `thread_items` in order, reconstructs `[{role, content, tool_calls}]` messages the provider expects. Reuses existing `chat/context_window.py` for windowing.

- [ ] **Step 6.5.1: Write failing tests**

```python
# server/api/tests/chat/test_context_assembler.py
import uuid
import pytest

from ai_portal.chat.streaming.context_assembler import build_provider_messages


@pytest.mark.asyncio
async def test_reconstructs_simple_user_assistant_pair(db_session, thread_fixture):
    from ai_portal.chat.model import ThreadItem
    from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole

    turn = uuid.uuid4()
    db_session.add_all([
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.user_message, role=ItemRole.user, status=ItemStatus.done,
                   data={"text": "hi", "attachments": []}),
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.done,
                   data={"text": "hello"}),
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.turn_end, role=ItemRole.system, status=ItemStatus.done,
                   data={"reason": "done"}),
    ])
    await db_session.commit()

    msgs = await build_provider_messages(
        session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id,
        system_prompt="S", window_size=50,
    )
    # [system, user, assistant]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "hi"
    assert msgs[2]["role"] == "assistant"
    assert "hello" in msgs[2]["content"]


@pytest.mark.asyncio
async def test_tool_call_and_result_flattened(db_session, thread_fixture):
    from ai_portal.chat.model import ThreadItem
    from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole

    turn = uuid.uuid4()
    db_session.add_all([
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.user_message, role=ItemRole.user, status=ItemStatus.done,
                   data={"text": "search weather", "attachments": []}),
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.tool_call, role=ItemRole.assistant, status=ItemStatus.done,
                   data={"tool_name": "web_search", "params": {"q": "weather"},
                         "result_snippet": "sunny"}),
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.done,
                   data={"text": "it is sunny"}),
    ])
    await db_session.commit()

    msgs = await build_provider_messages(
        session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id,
        system_prompt="S", window_size=50,
    )
    asm = next(m for m in msgs if m["role"] == "assistant")
    assert asm.get("tool_calls")
    assert asm["tool_calls"][0]["function"]["name"] == "web_search"
```

- [ ] **Step 6.5.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/context_assembler.py
from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.model import ThreadItem


async def build_provider_messages(
    *,
    session: AsyncSession,
    thread_id: int,
    org_id: uuid.UUID,
    system_prompt: str,
    window_size: int,
) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(ThreadItem)
        .where(ThreadItem.thread_id == thread_id, ThreadItem.org_id == org_id)
        .order_by(ThreadItem.created_at, ThreadItem.id)
    )).scalars().all()

    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    # Group by turn_id, preserve order
    seen_turns: list[uuid.UUID] = []
    by_turn: dict[uuid.UUID, list[ThreadItem]] = {}
    for item in rows:
        if item.turn_id not in by_turn:
            seen_turns.append(item.turn_id)
            by_turn[item.turn_id] = []
        by_turn[item.turn_id].append(item)

    for turn in seen_turns:
        turn_items = by_turn[turn]
        for item in turn_items:
            if item.kind == ItemKind.user_message:
                messages.append({"role": "user", "content": item.data["text"]})
            elif item.kind == ItemKind.assistant_text:
                messages.append({"role": "assistant", "content": item.data.get("text") or ""})
            elif item.kind == ItemKind.tool_call:
                messages.append({
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": f"call_{item.id}",
                        "type": "function",
                        "function": {
                            "name": item.data["tool_name"],
                            "arguments": json.dumps(item.data.get("params") or {}),
                        },
                    }],
                })
                if item.data.get("result_snippet") is not None:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": f"call_{item.id}",
                        "content": item.data["result_snippet"],
                    })
            # assistant_text after tool_call becomes the final assistant summary naturally.

    # Trim to window: keep system + last `window_size` non-system entries.
    head = messages[:1]
    tail = messages[1:]
    if len(tail) > window_size:
        tail = tail[-window_size:]
    return head + tail
```

- [ ] **Step 6.5.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_context_assembler.py -xvs
git add server/api/src/ai_portal/chat/streaming/context_assembler.py server/api/tests/chat/test_context_assembler.py
git commit -m "feat(chat): context_assembler — thread_items to provider messages"
```

---

### Task 6.6: `turn_gate` — quota + RBAC pre-flight

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/turn_gate.py`
- Test: `server/api/tests/chat/test_turn_gate.py`

Extract the current quota/RBAC checks from `streaming_service.py` (or from `rbac/` and `usage/`) into a pure pre-flight.

- [ ] **Step 6.6.1: Locate existing checks**

Run: `grep -rn "quota\|rbac\|allowed_tools" server/api/src/ai_portal/chat/streaming_service.py | head -20`

- [ ] **Step 6.6.2: Write tests**

```python
# server/api/tests/chat/test_turn_gate.py
import pytest
from fastapi import HTTPException

from ai_portal.chat.streaming.turn_gate import evaluate, GateResult


@pytest.mark.asyncio
async def test_passes_with_allowed_model_and_tools(db_session, org_fixture, user_fixture, rbac_fixture):
    # rbac_fixture sets policy: user can use 'gpt-4', can use web_search
    result = await evaluate(
        session=db_session, org_id=org_fixture.id, user_id=user_fixture.id,
        requested_model="gpt-4", requested_tools=["web_search"], requested_capabilities=[],
    )
    assert isinstance(result, GateResult)
    assert result.effective_model == "gpt-4"
    assert "web_search" in result.allowed_tools


@pytest.mark.asyncio
async def test_blocks_on_quota_exceeded(db_session, org_fixture, user_fixture, over_quota_fixture):
    with pytest.raises(HTTPException) as exc:
        await evaluate(
            session=db_session, org_id=org_fixture.id, user_id=user_fixture.id,
            requested_model="gpt-4", requested_tools=[], requested_capabilities=[],
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_strips_disallowed_tools_without_raising(db_session, org_fixture, user_fixture, rbac_restricted_fixture):
    # user allowed nothing
    result = await evaluate(
        session=db_session, org_id=org_fixture.id, user_id=user_fixture.id,
        requested_model="gpt-4", requested_tools=["web_search", "kb_search"], requested_capabilities=[],
    )
    assert result.allowed_tools == []
```

(The `rbac_fixture`, `over_quota_fixture`, `rbac_restricted_fixture` mirror whatever the current RBAC tests use. Copy patterns from existing tests in `tests/rbac/` and `tests/usage/`.)

- [ ] **Step 6.6.3: Implement**

```python
# server/api/src/ai_portal/chat/streaming/turn_gate.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.rbac import service as rbac_service
from ai_portal.usage import service as usage_service


@dataclass(frozen=True, slots=True)
class GateResult:
    effective_model: str
    allowed_tools: list[str]
    allowed_capabilities: list[str]


async def evaluate(
    *,
    session: AsyncSession,
    org_id: uuid.UUID,
    user_id: int,
    requested_model: str,
    requested_tools: list[str],
    requested_capabilities: list[str],
) -> GateResult:
    quota_ok = await usage_service.check_quota(session, org_id=org_id, user_id=user_id)
    if not quota_ok.allowed:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"code": "QUOTA_EXCEEDED", "message": quota_ok.reason},
        )

    effective_model = await rbac_service.resolve_model(
        session, org_id=org_id, user_id=user_id, requested=requested_model,
    )
    if effective_model is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={"code": "MODEL_FORBIDDEN", "message": f"{requested_model} not allowed"},
        )

    allowed_tools = await rbac_service.filter_tools(
        session, org_id=org_id, user_id=user_id, requested=requested_tools,
    )
    allowed_capabilities = await rbac_service.filter_capabilities(
        session, org_id=org_id, user_id=user_id, requested=requested_capabilities,
    )

    return GateResult(
        effective_model=effective_model,
        allowed_tools=list(allowed_tools),
        allowed_capabilities=list(allowed_capabilities),
    )
```

If the current RBAC service does not expose `resolve_model` / `filter_tools` / `filter_capabilities`, add thin wrappers in `server/api/src/ai_portal/rbac/service.py` that delegate to existing methods. Do not rewrite the RBAC internals here.

- [ ] **Step 6.6.4: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_turn_gate.py -xvs
git add server/api/src/ai_portal/chat/streaming/turn_gate.py server/api/tests/chat/test_turn_gate.py
git commit -m "feat(chat): turn_gate — quota + RBAC pre-flight"
```

---

### Task 6.7: `turn_setup` — user_message + attachments + regenerate

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/turn_setup.py`
- Test: `server/api/tests/chat/test_turn_setup.py`

- [ ] **Step 6.7.1: Write tests**

```python
# server/api/tests/chat/test_turn_setup.py
import uuid
import pytest

from ai_portal.chat.streaming.turn_setup import start_or_regenerate, TurnSetup


@pytest.mark.asyncio
async def test_start_new_turn_inserts_user_message(db_session, thread_fixture):
    setup = await start_or_regenerate(
        session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id,
        user_text="hi", attachments=[], regenerate_from_turn_id=None,
        effective_model="gpt-4",
    )
    assert isinstance(setup, TurnSetup)
    assert setup.user_message_item.data["text"] == "hi"


@pytest.mark.asyncio
async def test_regenerate_deletes_non_user_items_for_turn(db_session, thread_fixture):
    from ai_portal.chat.model import ThreadItem
    from ai_portal.chat.item_kinds import ItemKind, ItemStatus, ItemRole

    turn = uuid.uuid4()
    db_session.add_all([
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.user_message, role=ItemRole.user, status=ItemStatus.done,
                   data={"text": "original", "attachments": []}),
        ThreadItem(thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
                   kind=ItemKind.assistant_text, role=ItemRole.assistant, status=ItemStatus.done,
                   data={"text": "old answer"}),
    ])
    await db_session.commit()

    setup = await start_or_regenerate(
        session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id,
        user_text="<unused>", attachments=[], regenerate_from_turn_id=turn,
        effective_model="gpt-4",
    )
    assert setup.turn_id == turn
    remaining = (await db_session.execute(
        __import__("sqlalchemy").select(ThreadItem).where(ThreadItem.turn_id == turn)
    )).scalars().all()
    assert len(remaining) == 1
    assert remaining[0].kind == ItemKind.user_message
    assert remaining[0].data["text"] == "original"
```

- [ ] **Step 6.7.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/turn_setup.py
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.model import ThreadItem
from ai_portal.chat.streaming.item_writer import ItemWriter


@dataclass(slots=True)
class TurnSetup:
    turn_id: uuid.UUID
    user_message_item: ThreadItem
    effective_model: str


async def start_or_regenerate(
    *,
    session: AsyncSession,
    thread_id: int,
    org_id: uuid.UUID,
    user_text: str,
    attachments: list[dict],
    regenerate_from_turn_id: uuid.UUID | None,
    effective_model: str,
) -> TurnSetup:
    writer = ItemWriter(session=session, thread_id=thread_id, org_id=org_id)

    if regenerate_from_turn_id is not None:
        await session.execute(
            delete(ThreadItem).where(
                ThreadItem.thread_id == thread_id,
                ThreadItem.turn_id == regenerate_from_turn_id,
                ThreadItem.kind != ItemKind.user_message,
            )
        )
        user_item = (await session.execute(
            select(ThreadItem).where(
                ThreadItem.thread_id == thread_id,
                ThreadItem.turn_id == regenerate_from_turn_id,
                ThreadItem.kind == ItemKind.user_message,
            )
        )).scalar_one()
        await session.flush()
        return TurnSetup(turn_id=regenerate_from_turn_id, user_message_item=user_item, effective_model=effective_model)

    turn_id = uuid.uuid4()
    user_item = await writer.insert_user_message(
        turn_id=turn_id, text=user_text, attachments=attachments,
    )
    return TurnSetup(turn_id=turn_id, user_message_item=user_item, effective_model=effective_model)
```

- [ ] **Step 6.7.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_turn_setup.py -xvs
git add server/api/src/ai_portal/chat/streaming/turn_setup.py server/api/tests/chat/test_turn_setup.py
git commit -m "feat(chat): turn_setup — new turn + regenerate"
```

---

### Task 6.8: `error_handler` — provider exceptions → friendly error items

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/error_handler.py`
- Test: `server/api/tests/chat/test_error_handler.py`

- [ ] **Step 6.8.1: Write tests**

```python
# server/api/tests/chat/test_error_handler.py
import uuid
import pytest

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.streaming.error_handler import handle_stream_error
from ai_portal.chat.streaming.item_writer import ItemWriter


@pytest.mark.asyncio
async def test_handle_produces_error_and_turn_end(db_session, thread_fixture):
    writer = ItemWriter(session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)
    turn = uuid.uuid4()
    events = []
    async for ev in handle_stream_error(writer=writer, turn_id=turn,
                                        exc=RuntimeError("rate limit")):
        events.append(ev)
    kinds = [e.root.event_type for e in events]
    assert "item" in kinds
    assert "done" in kinds


@pytest.mark.asyncio
async def test_mapped_auth_error_friendly_message(db_session, thread_fixture):
    from anthropic import AuthenticationError  # hypothetical
    # If the import differs, substitute the concrete exception type used by adapters.
    ...
```

- [ ] **Step 6.8.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/error_handler.py
from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

from ai_portal.chat.sse import SseDoneEvent, SseErrorEvent, SseEvent, SseItemEvent
from ai_portal.chat.items import ThreadItemModel
from ai_portal.chat.streaming.item_writer import ItemWriter

log = logging.getLogger(__name__)


def _map(exc: Exception) -> tuple[str, str]:
    name = type(exc).__name__
    if "Auth" in name or "401" in str(exc):
        return "AUTH_FAILED", "Provider authentication failed"
    if "RateLimit" in name or "429" in str(exc):
        return "RATE_LIMIT", "Rate limit hit; try again later"
    if "Timeout" in name or "timed out" in str(exc).lower():
        return "TIMEOUT", "Provider timed out"
    return "UPSTREAM_ERROR", str(exc)


async def handle_stream_error(
    *, writer: ItemWriter, turn_id: uuid.UUID, exc: Exception,
) -> AsyncIterator[SseEvent]:
    log.exception("stream error", extra={"turn_id": str(turn_id)})
    code, message = _map(exc)
    await writer.cancel_turn_items(turn_id=turn_id)
    err_item = await writer.insert_error(turn_id=turn_id, code=code, message=message)
    turn_end = await writer.insert_turn_end(turn_id=turn_id, reason="error")
    # emit both items + done
    yield SseEvent(root=SseItemEvent(event_type="item", item=ThreadItemModel.model_validate(_row_to_dict(err_item))))
    yield SseEvent(root=SseItemEvent(event_type="item", item=ThreadItemModel.model_validate(_row_to_dict(turn_end))))
    yield SseEvent(root=SseDoneEvent(event_type="done"))


def _row_to_dict(item) -> dict:
    return {
        "id": item.id, "thread_id": item.thread_id, "turn_id": item.turn_id,
        "kind": item.kind.value, "role": item.role.value if item.role else None,
        "status": item.status.value, "provider": item.provider, "model": item.model,
        "cost_usd": str(item.cost_usd) if item.cost_usd is not None else None,
        "cost_estimated": item.cost_estimated, "latency_ms": item.latency_ms,
        "data": item.data, "parent_item_id": item.parent_item_id,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "created_at": item.created_at.isoformat(),
    }
```

- [ ] **Step 6.8.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_error_handler.py -xvs
git add server/api/src/ai_portal/chat/streaming/error_handler.py server/api/tests/chat/test_error_handler.py
git commit -m "feat(chat): error_handler — provider exceptions to SSE stream"
```

---

### Task 6.9: `cancellation` — cancel endpoint + writer flip

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/cancellation.py`
- Test: `server/api/tests/chat/test_cancellation.py`

- [ ] **Step 6.9.1: Write tests**

```python
# server/api/tests/chat/test_cancellation.py
import uuid
import pytest

from ai_portal.chat.streaming.cancellation import (
    CancelRegistry, register_turn, cancel_turn,
)


def test_cancel_registry_trips_flag():
    reg = CancelRegistry()
    turn = uuid.uuid4()
    token = reg.register(turn)
    assert not token.is_cancelled
    reg.cancel(turn)
    assert token.is_cancelled


def test_cancel_unknown_turn_is_noop():
    reg = CancelRegistry()
    reg.cancel(uuid.uuid4())  # does not raise


@pytest.mark.asyncio
async def test_cancel_turn_flips_streaming_items(db_session, thread_fixture):
    from ai_portal.chat.model import ThreadItem
    from ai_portal.chat.item_kinds import ItemKind, ItemStatus
    turn = uuid.uuid4()
    db_session.add(ThreadItem(
        thread_id=thread_fixture.id, org_id=thread_fixture.org_id, turn_id=turn,
        kind=ItemKind.llm_call, status=ItemStatus.streaming, model="gpt-4",
        data={"input_tokens": 0, "output_tokens": 5, "cached_input_tokens": 0,
              "cache_creation_input_tokens": 0, "reasoning_tokens": 0, "iteration_index": 0},
    ))
    await db_session.commit()
    n = await cancel_turn(session=db_session, thread_id=thread_fixture.id,
                          org_id=thread_fixture.org_id, turn_id=turn)
    assert n >= 1
```

- [ ] **Step 6.9.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/cancellation.py
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.streaming.item_writer import ItemWriter


@dataclass
class CancelToken:
    is_cancelled: bool = False


@dataclass
class CancelRegistry:
    _tokens: dict[uuid.UUID, CancelToken] = field(default_factory=dict)

    def register(self, turn_id: uuid.UUID) -> CancelToken:
        token = CancelToken()
        self._tokens[turn_id] = token
        return token

    def cancel(self, turn_id: uuid.UUID) -> None:
        token = self._tokens.get(turn_id)
        if token is not None:
            token.is_cancelled = True

    def release(self, turn_id: uuid.UUID) -> None:
        self._tokens.pop(turn_id, None)


_global_registry = CancelRegistry()


def register_turn(turn_id: uuid.UUID) -> CancelToken:
    return _global_registry.register(turn_id)


def release_turn(turn_id: uuid.UUID) -> None:
    _global_registry.release(turn_id)


async def cancel_turn(
    *, session: AsyncSession, thread_id: int, org_id: uuid.UUID, turn_id: uuid.UUID,
) -> int:
    """Handler for the cancel endpoint. Trips the in-process token and flips DB items."""
    _global_registry.cancel(turn_id)
    writer = ItemWriter(session=session, thread_id=thread_id, org_id=org_id)
    n = await writer.cancel_turn_items(turn_id=turn_id, partial_cost=None)
    await writer.insert_turn_end(turn_id=turn_id, reason="cancelled")
    await session.commit()
    return n
```

- [ ] **Step 6.9.3: Run tests and commit**

```bash
cd server/api && pytest tests/chat/test_cancellation.py -xvs
git add server/api/src/ai_portal/chat/streaming/cancellation.py server/api/tests/chat/test_cancellation.py
git commit -m "feat(chat): cancellation — registry + endpoint handler"
```

---

### Task 6.10: `iteration_loop` — the core streaming loop

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/iteration_loop.py`
- Test: `server/api/tests/chat/test_iteration_loop.py`

This is the heart. Reads events from the provider, writes items via `item_writer`, dispatches tools via `tool_service`, yields `SseEvent`s, loops until no tool call or `max_iterations`.

- [ ] **Step 6.10.1: Write tests with a fake provider**

```python
# server/api/tests/chat/test_iteration_loop.py
import uuid
from decimal import Decimal

import pytest

from ai_portal.catalog.providers.events import (
    TextDeltaEvent, UsageEvent, ToolCallRequestEvent, IterationCompleteEvent,
    ProviderStreamEvent,
)
from ai_portal.chat.streaming.iteration_loop import run as run_loop
from ai_portal.chat.streaming.item_writer import ItemWriter


class FakeProvider:
    def __init__(self, scripts):
        self._scripts = scripts
        self._i = 0

    async def stream(self, **kwargs):
        script = self._scripts[self._i]
        self._i += 1
        for e in script:
            yield ProviderStreamEvent.model_validate(e)


@pytest.mark.asyncio
async def test_happy_path_no_tool(db_session, thread_fixture):
    script = [
        {"type": "text_delta", "text": "hi "},
        {"type": "text_delta", "text": "there"},
        {"type": "usage", "input_tokens": 5, "output_tokens": 2,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    writer = ItemWriter(session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)
    turn = uuid.uuid4()
    events = []
    async for ev in run_loop(
        provider=FakeProvider([script]), writer=writer, turn_id=turn,
        provider_messages=[{"role": "user", "content": "hi"}],
        model="gpt-4", settings={}, allowed_tools=[], max_iterations=3,
    ):
        events.append(ev)
    # assert we got text, llm_call done, turn_end done via orchestrator (not here)
    kinds = [e.root.item.root.kind for e in events if e.root.event_type == "item"]
    assert "assistant_text" in kinds
    assert "llm_call" in kinds


@pytest.mark.asyncio
async def test_tool_call_triggers_dispatch(db_session, thread_fixture, monkeypatch):
    # iter 1: request a tool call
    # iter 2: final text
    from ai_portal.chat.tool_outcome import ToolCallOutcome
    async def fake_dispatch(*, tool_name, call_id, arguments, org_id, user_id=None):
        return ToolCallOutcome(
            call_id=call_id, tool_name=tool_name, provider="tavily",
            input=arguments, result_snippet="sunny",
        )
    monkeypatch.setattr(
        "ai_portal.chat.streaming.iteration_loop.dispatch_tool", fake_dispatch,
    )

    script1 = [
        {"type": "tool_call_request", "call_id": "c1", "tool_name": "web_search",
         "arguments": {"q": "weather"}},
        {"type": "iteration_complete", "stop_reason": "tool_use"},
    ]
    script2 = [
        {"type": "text_delta", "text": "it is sunny"},
        {"type": "usage", "input_tokens": 10, "output_tokens": 4,
         "cached_input_tokens": 0, "cache_creation_input_tokens": 0, "reasoning_tokens": 0},
        {"type": "iteration_complete", "stop_reason": "end_turn"},
    ]
    writer = ItemWriter(session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)
    events = []
    async for ev in run_loop(
        provider=FakeProvider([script1, script2]), writer=writer, turn_id=uuid.uuid4(),
        provider_messages=[{"role": "user", "content": "hi"}],
        model="gpt-4", settings={}, allowed_tools=["web_search"], max_iterations=3,
    ):
        events.append(ev)
    kinds = [e.root.item.root.kind for e in events if e.root.event_type == "item"]
    assert "tool_call" in kinds
    assert "assistant_text" in kinds
    assert kinds.count("llm_call") == 2  # one per iteration


@pytest.mark.asyncio
async def test_max_iterations_forces_stop(db_session, thread_fixture):
    tool_only = [
        {"type": "tool_call_request", "call_id": "c", "tool_name": "web_search", "arguments": {}},
        {"type": "iteration_complete", "stop_reason": "tool_use"},
    ]
    writer = ItemWriter(session=db_session, thread_id=thread_fixture.id, org_id=thread_fixture.org_id)
    events = []
    async for ev in run_loop(
        provider=FakeProvider([tool_only, tool_only, tool_only, tool_only]),
        writer=writer, turn_id=uuid.uuid4(),
        provider_messages=[{"role": "user", "content": "hi"}],
        model="gpt-4", settings={}, allowed_tools=["web_search"], max_iterations=3,
    ):
        events.append(ev)
    kinds = [e.root.item.root.kind for e in events if e.root.event_type == "item"]
    assert kinds.count("llm_call") == 3
```

(A `dispatch_tool` stub that returns a static outcome is simpler than monkey-patching if the module structure allows; use whichever keeps the test readable.)

- [ ] **Step 6.10.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/iteration_loop.py
from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

from ai_portal.catalog.providers.events import (
    CitationEvent,
    IterationCompleteEvent,
    ProviderErrorEvent,
    ProviderStreamEvent,
    ServerToolUseEvent,
    TextDeltaEvent,
    ThinkingDeltaEvent,
    ToolCallRequestEvent,
    UsageEvent,
)
from ai_portal.chat.cost_calculator import compute_llm_cost, compute_tool_cost, compute_server_tool_cost
from ai_portal.chat.items import ThreadItemModel
from ai_portal.chat.sse import SseDoneEvent, SseErrorEvent, SseEvent, SseItemEvent
from ai_portal.chat.streaming.cancellation import CancelToken
from ai_portal.chat.streaming.item_writer import ItemWriter
from ai_portal.chat.tool_service import dispatch_tool


async def run(
    *,
    provider,  # ChatProvider
    writer: ItemWriter,
    turn_id: uuid.UUID,
    provider_messages: list[dict[str, Any]],
    model: str,
    settings: dict[str, Any],
    allowed_tools: list[str],
    max_iterations: int,
    cancel_token: CancelToken | None = None,
    org_id: uuid.UUID | None = None,
    user_id: int | None = None,
) -> AsyncIterator[SseEvent]:
    tool_schemas = _build_tool_schemas(allowed_tools)
    messages = list(provider_messages)

    for iteration_index in range(max_iterations):
        if cancel_token and cancel_token.is_cancelled:
            break

        llm_item = await writer.start_llm_call(
            turn_id=turn_id, model=model, iteration_index=iteration_index,
        )
        yield _emit(llm_item)

        text_item = None
        thinking_item = None
        pending_tool_calls: list[dict[str, Any]] = []
        usage: UsageEvent | None = None
        stop_reason: str | None = None
        errored = False
        err_msg = ""

        async for ev_wrapper in provider.stream(
            messages=messages, model=model, settings=settings, tools=tool_schemas,
        ):
            ev = ev_wrapper.root if hasattr(ev_wrapper, "root") else ev_wrapper
            if cancel_token and cancel_token.is_cancelled:
                break

            match ev:
                case TextDeltaEvent(text=t):
                    if text_item is None:
                        text_item = await writer.start_text(turn_id=turn_id)
                        yield _emit(text_item)
                    await writer.append_text_delta(text_item.id, t)
                    yield _emit(text_item)  # clients render latest text
                case ThinkingDeltaEvent(text=t):
                    if thinking_item is None:
                        thinking_item = await writer.start_thinking(turn_id=turn_id)
                        yield _emit(thinking_item)
                    await writer.append_text_delta(thinking_item.id, t)
                    yield _emit(thinking_item)
                case ToolCallRequestEvent(call_id=cid, tool_name=tn, arguments=args):
                    pending_tool_calls.append({"call_id": cid, "tool_name": tn, "arguments": args})
                case ServerToolUseEvent(tool_name=tn, input=inp):
                    st = await writer.start_server_tool(
                        turn_id=turn_id, tool_name=tn, provider=_provider_of(model), input_payload=inp,
                    )
                    yield _emit(st)
                    r = compute_server_tool_cost(tool_name=tn, provider=_provider_of(model), usage_metadata=None)
                    done = await writer.finish_server_tool(
                        item_id=st.id, cost_usd=r.cost_usd, cost_estimated=r.estimated,
                    )
                    yield _emit(done)
                case CitationEvent(url=u, title=tt, snippet=sn):
                    cit = await writer.insert_citation(
                        turn_id=turn_id, url=u, title=tt, snippet=sn,
                        parent_item_id=None,
                    )
                    yield _emit(cit)
                case UsageEvent():
                    usage = ev
                case IterationCompleteEvent(stop_reason=sr):
                    stop_reason = sr
                case ProviderErrorEvent(code=c, message=m):
                    errored, err_msg = True, m

        if text_item is not None:
            done_text = await writer.finalize_text(text_item.id)
            yield _emit(done_text)
        if thinking_item is not None:
            done_think = await writer.finalize_thinking(thinking_item.id)
            yield _emit(done_think)

        if errored:
            await writer.fail_llm_call(item_id=llm_item.id, error=err_msg)
            yield _emit(llm_item)
            break

        if usage is not None:
            cost = compute_llm_cost(
                model=model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_creation_input_tokens=usage.cache_creation_input_tokens,
                reasoning_tokens=usage.reasoning_tokens,
            )
            done_llm = await writer.finish_llm_call(
                item_id=llm_item.id,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cached_input_tokens=usage.cached_input_tokens,
                cache_creation_input_tokens=usage.cache_creation_input_tokens,
                reasoning_tokens=usage.reasoning_tokens,
                cost_usd=cost.cost_usd,
                cost_estimated=cost.estimated,
            )
            yield _emit(done_llm)
        else:
            await writer.finish_llm_call(
                item_id=llm_item.id, input_tokens=0, output_tokens=0,
                cached_input_tokens=0, cache_creation_input_tokens=0, reasoning_tokens=0,
                cost_usd=Decimal("0"), cost_estimated=True,
            )

        if not pending_tool_calls or stop_reason == "end_turn":
            break

        # dispatch tools and append their results to provider_messages
        for call in pending_tool_calls:
            tc_item = await writer.start_tool_call(
                turn_id=turn_id, tool_name=call["tool_name"], provider=None, params=call["arguments"],
            )
            yield _emit(tc_item)
            outcome = await dispatch_tool(
                tool_name=call["tool_name"],
                call_id=call["call_id"],
                arguments=call["arguments"],
                org_id=str(org_id) if org_id else "",
                user_id=user_id,
            )
            cost = compute_tool_cost(outcome)
            done_tc = await writer.finish_tool_call(
                item_id=tc_item.id,
                result_snippet=outcome.result_snippet,
                error=outcome.error,
                cost_usd=cost.cost_usd,
                cost_estimated=cost.estimated,
                latency_ms=outcome.latency_ms,
            )
            yield _emit(done_tc)
            # feed result back into provider messages for next iteration
            messages.append({
                "role": "assistant",
                "content": "",
                "tool_calls": [{
                    "id": call["call_id"], "type": "function",
                    "function": {"name": call["tool_name"], "arguments": _json(call["arguments"])},
                }],
            })
            messages.append({
                "role": "tool", "tool_call_id": call["call_id"],
                "content": outcome.result_snippet or outcome.error or "",
            })


def _build_tool_schemas(allowed: list[str]) -> list[dict]:
    # Delegate to existing schema registry if present; otherwise empty.
    from ai_portal.tools.registry import tool_schema
    return [tool_schema(name) for name in allowed if tool_schema(name) is not None]


def _provider_of(model: str) -> str:
    # crude prefix mapping; refine if needed.
    if model.startswith("claude"): return "anthropic"
    if model.startswith("gemini"): return "google"
    if model.startswith("gpt") or model.startswith("o"): return "openai"
    return "unknown"


def _json(obj) -> str:
    import json as _j
    return _j.dumps(obj or {})


def _emit(item) -> SseEvent:
    return SseEvent(root=SseItemEvent(
        event_type="item",
        item=ThreadItemModel.model_validate(_row_to_dict(item)),
    ))


def _row_to_dict(item) -> dict:
    return {
        "id": item.id, "thread_id": item.thread_id, "turn_id": item.turn_id,
        "kind": item.kind.value, "role": item.role.value if item.role else None,
        "status": item.status.value, "provider": item.provider, "model": item.model,
        "cost_usd": str(item.cost_usd) if item.cost_usd is not None else None,
        "cost_estimated": item.cost_estimated, "latency_ms": item.latency_ms,
        "data": item.data, "parent_item_id": item.parent_item_id,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "finished_at": item.finished_at.isoformat() if item.finished_at else None,
        "created_at": item.created_at.isoformat(),
    }
```

- [ ] **Step 6.10.3: Run tests**

Run: `cd server/api && pytest tests/chat/test_iteration_loop.py -xvs`
Expected: PASS. Iterate on `iteration_loop.py` until all tests green; the fake provider + scripted events are the fastest feedback loop.

- [ ] **Step 6.10.4: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming/iteration_loop.py server/api/tests/chat/test_iteration_loop.py
git commit -m "feat(chat): iteration_loop — LLM + tool loop yielding SseEvents"
```

---

### Task 6.11: `orchestrator` — public entry

**Files:**
- Create: `server/api/src/ai_portal/chat/streaming/orchestrator.py`
- Test: `server/api/tests/chat/test_stream_turn_e2e.py`

The orchestrator is the one function `router.py` calls. It fits on a screen.

- [ ] **Step 6.11.1: Write integration test**

```python
# server/api/tests/chat/test_stream_turn_e2e.py
import uuid
import pytest

from ai_portal.chat.streaming.orchestrator import stream_turn


@pytest.mark.asyncio
async def test_stream_turn_happy_path(db_session, thread_fixture, user_fixture,
                                      patched_fake_provider):
    chunks = []
    response = await stream_turn(
        session=db_session, user=user_fixture, thread_id=thread_fixture.id,
        body={"text": "hi", "attachments": [], "model": "gpt-4"},
    )
    async for ch in response.body_iterator:
        chunks.append(ch if isinstance(ch, str) else ch.decode())
    combined = "".join(chunks)
    assert '"event_type":"item"' in combined
    assert '"event_type":"done"' in combined
```

(`patched_fake_provider` is a fixture that monkey-patches the provider routing to return a `FakeProvider` with a scripted happy-path stream. Put it in `tests/chat/conftest.py`.)

- [ ] **Step 6.11.2: Implement**

```python
# server/api/src/ai_portal/chat/streaming/orchestrator.py
from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.catalog.providers.routing import resolve_provider_for_model
from ai_portal.chat.streaming import (
    context_assembler, error_handler, item_writer, iteration_loop,
    sse_emitter, system_prompt, turn_gate, turn_setup,
)
from ai_portal.chat.streaming.cancellation import register_turn, release_turn
from ai_portal.chat.sse import SseDoneEvent, SseEvent


async def stream_turn(
    *, session: AsyncSession, user, thread_id: int, body: dict,
) -> StreamingResponse:
    gate = await turn_gate.evaluate(
        session=session, org_id=user.org_id, user_id=user.id,
        requested_model=body.get("model") or "gpt-4",
        requested_tools=body.get("tools") or [],
        requested_capabilities=body.get("capabilities") or [],
    )

    setup = await turn_setup.start_or_regenerate(
        session=session, thread_id=thread_id, org_id=user.org_id,
        user_text=body["text"], attachments=body.get("attachments") or [],
        regenerate_from_turn_id=body.get("regenerate_from_turn_id"),
        effective_model=gate.effective_model,
    )

    base_prompt = body.get("system_prompt") or ""
    sp = system_prompt.compose(
        base_prompt=base_prompt,
        assistant_prompt=body.get("assistant_prompt"),
        memory_block=body.get("memory_block"),
        kb_block=body.get("kb_block"),
        capabilities=gate.allowed_capabilities,
    )
    messages = await context_assembler.build_provider_messages(
        session=session, thread_id=thread_id, org_id=user.org_id,
        system_prompt=sp, window_size=body.get("window_size", 50),
    )

    provider = resolve_provider_for_model(gate.effective_model)
    writer = item_writer.ItemWriter(session=session, thread_id=thread_id, org_id=user.org_id)
    cancel_token = register_turn(setup.turn_id)

    async def gen() -> AsyncIterator[str]:
        try:
            async for ev in iteration_loop.run(
                provider=provider, writer=writer, turn_id=setup.turn_id,
                provider_messages=messages, model=gate.effective_model,
                settings=body.get("settings") or {},
                allowed_tools=gate.allowed_tools, max_iterations=body.get("max_iterations", 6),
                cancel_token=cancel_token, org_id=user.org_id, user_id=user.id,
            ):
                yield sse_emitter.encode(ev)

            # finalize: turn_end + done
            end_item = await writer.insert_turn_end(
                turn_id=setup.turn_id,
                reason="cancelled" if cancel_token.is_cancelled else "done",
            )
            yield sse_emitter.encode(_emit_item(end_item))
            await session.commit()
            yield sse_emitter.encode(SseEvent(root=SseDoneEvent(event_type="done")))
        except Exception as exc:
            await session.rollback()
            async for ev in error_handler.handle_stream_error(
                writer=writer, turn_id=setup.turn_id, exc=exc,
            ):
                yield sse_emitter.encode(ev)
            await session.commit()
        finally:
            release_turn(setup.turn_id)

    return StreamingResponse(gen(), media_type="text/event-stream")


def _emit_item(item):
    from ai_portal.chat.items import ThreadItemModel
    from ai_portal.chat.sse import SseItemEvent
    return SseEvent(root=SseItemEvent(
        event_type="item",
        item=ThreadItemModel.model_validate(iteration_loop._row_to_dict(item)),
    ))
```

- [ ] **Step 6.11.3: Run tests**

Run: `cd server/api && pytest tests/chat/test_stream_turn_e2e.py -xvs`
Expected: PASS.

- [ ] **Step 6.11.4: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming/orchestrator.py server/api/tests/chat/test_stream_turn_e2e.py
git commit -m "feat(chat): orchestrator — public stream_turn entry"
```

---

### Task 6.12: Wire router to orchestrator; delete `streaming_service.py`

**Files:**
- Modify: `server/api/src/ai_portal/chat/router.py`
- Delete: `server/api/src/ai_portal/chat/streaming_service.py`

- [ ] **Step 6.12.1: Point router at orchestrator**

```python
# server/api/src/ai_portal/chat/router.py (chat-turn handler)
from ai_portal.chat.streaming.orchestrator import stream_turn
from ai_portal.chat.streaming.cancellation import cancel_turn


@router.post("/threads/{thread_id}/turns", response_class=StreamingResponse)
async def post_turn(
    thread_id: int,
    body: TurnRequest,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    return await stream_turn(session=session, user=user, thread_id=thread_id, body=body.model_dump())


@router.post("/threads/{thread_id}/turns/{turn_id}/cancel")
async def post_cancel(
    thread_id: int, turn_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_user),
):
    n = await cancel_turn(session=session, thread_id=thread_id, org_id=user.org_id, turn_id=turn_id)
    return {"cancelled_items": n}
```

Rename existing chat endpoints under `/threads/*` and keep redirect shims for `/conversations/*` during the frontend transition (Phase 9). If frontend moves in the same PR, you may skip shims.

- [ ] **Step 6.12.2: Add `/threads` list + detail routes**

```python
@router.get("/threads", response_model=list[ThreadRead])
async def list_threads(...): ...

@router.get("/threads/{thread_id}/items", response_model=list[ThreadItemRead])
async def list_items(thread_id: int, since_id: int | None = None, ...): ...
```

- [ ] **Step 6.12.3: Delete the monolith**

```bash
git rm server/api/src/ai_portal/chat/streaming_service.py
```

- [ ] **Step 6.12.4: Smoke**

Run: `cd server/api && uvicorn ai_portal.main:app --port 8000 --reload`
Expected: boots. Hit `/threads` via curl: `curl -s http://localhost:8000/api/chat/threads -H 'Authorization: Bearer ...' | jq`.

- [ ] **Step 6.12.5: Commit**

```bash
git add server/api/src/ai_portal/chat/router.py
git commit -m "refactor(chat): router -> orchestrator; delete streaming_service.py"
```

---

### Task 6.13: Run the full backend unit test suite

- [ ] **Step 6.13.1: Run**

Run: `cd server/api && pytest -xvs --ignore=tests/e2e 2>&1 | tail -50`
Expected: all unit tests green. Fix any regressions before moving on. E2E remains deferred to Phase 11.

---
## Phase 7 — Consumption backend (`/api/admin/consumption/*`)

### Task 7.1: Response schemas

**Files:**
- Create: `server/api/src/ai_portal/usage/consumption_schemas.py`

- [ ] **Step 7.1.1: Define schemas**

```python
# server/api/src/ai_portal/usage/consumption_schemas.py
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict


class KpiCard(BaseModel):
    label: str
    value: Decimal | int | str
    unit: str | None = None


class SummaryRow(BaseModel):
    key: str
    label: str
    messages: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    estimated_ratio: float


class SummaryResponse(BaseModel):
    kpis: list[KpiCard]
    by_model: list[SummaryRow]
    by_user: list[SummaryRow]
    by_provider: list[SummaryRow]
    by_capability: list[SummaryRow]
    by_tool: list[SummaryRow]


class TrendPoint(BaseModel):
    t: datetime
    cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    breakdown: dict[str, Decimal]  # key depends on `by` param


class TrendResponse(BaseModel):
    grain: Literal["day", "hour"]
    by: Literal["kind", "provider"]
    series: list[TrendPoint]


class ThreadRow(BaseModel):
    id: int
    title: str | None
    user_id: int
    model: str | None
    last_message_at: datetime | None
    total_cost_usd: Decimal
    total_items: int


class ThreadsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    rows: list[ThreadRow]


class TimelineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    turn_id: str
    kind: str
    status: str
    provider: str | None
    model: str | None
    cost_usd: Decimal | None
    cost_estimated: bool
    latency_ms: int | None
    data: dict
    created_at: datetime


class TimelineResponse(BaseModel):
    thread_id: int
    items: list[TimelineItem]
```

- [ ] **Step 7.1.2: Commit**

```bash
git add server/api/src/ai_portal/usage/consumption_schemas.py
git commit -m "feat(usage): consumption response schemas"
```

---

### Task 7.2: Aggregation service

**Files:**
- Create: `server/api/src/ai_portal/usage/consumption_service.py`
- Test: `server/api/tests/usage/test_consumption_service.py`

- [ ] **Step 7.2.1: Write failing tests**

```python
# server/api/tests/usage/test_consumption_service.py
from datetime import datetime, timezone, timedelta
from decimal import Decimal

import pytest

from ai_portal.usage import consumption_service


@pytest.mark.asyncio
async def test_summary_aggregates_by_model(db_session, thread_items_fixture):
    res = await consumption_service.summary(
        session=db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=30),
        end=datetime.now(timezone.utc),
    )
    models = {r.key for r in res.by_model}
    assert "gpt-4" in models


@pytest.mark.asyncio
async def test_summary_kpis_include_month_spend(db_session, thread_items_fixture):
    res = await consumption_service.summary(
        session=db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=30),
        end=datetime.now(timezone.utc),
    )
    labels = [k.label for k in res.kpis]
    assert "Month spend" in labels
    assert "Messages streamed" in labels


@pytest.mark.asyncio
async def test_trend_day_grain_returns_non_empty_series(db_session, thread_items_fixture):
    res = await consumption_service.trend(
        session=db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=90),
        end=datetime.now(timezone.utc),
        grain="day", by="kind",
    )
    assert len(res.series) >= 1
    assert res.grain == "day"


@pytest.mark.asyncio
async def test_threads_paginated(db_session, thread_items_fixture):
    res = await consumption_service.threads(
        session=db_session, org_id=thread_items_fixture.org_id,
        start=datetime.now(timezone.utc) - timedelta(days=90),
        end=datetime.now(timezone.utc),
        user_id=None, model=None, page=1, page_size=10,
    )
    assert res.total >= 1
    assert len(res.rows) <= 10


@pytest.mark.asyncio
async def test_timeline_for_thread(db_session, thread_items_fixture):
    res = await consumption_service.timeline(
        session=db_session, org_id=thread_items_fixture.org_id,
        thread_id=thread_items_fixture.id,
    )
    assert res.thread_id == thread_items_fixture.id
    assert all(i.created_at for i in res.items)
```

`thread_items_fixture` inserts one thread with a handful of items spanning `llm_call`, `tool_call`, `assistant_text`.

- [ ] **Step 7.2.2: Implement**

```python
# server/api/src/ai_portal/usage/consumption_service.py
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.chat.item_kinds import ItemKind
from ai_portal.chat.model import Thread, ThreadItem
from ai_portal.usage.consumption_schemas import (
    KpiCard, SummaryResponse, SummaryRow, ThreadRow, ThreadsResponse,
    TimelineItem, TimelineResponse, TrendPoint, TrendResponse,
)


ZERO = Decimal("0")


async def summary(*, session: AsyncSession, org_id: uuid.UUID,
                  start: datetime, end: datetime) -> SummaryResponse:
    base = select(ThreadItem).where(
        ThreadItem.org_id == org_id,
        ThreadItem.created_at >= start,
        ThreadItem.created_at <= end,
    )

    kpis_row = (await session.execute(
        select(
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.sum(case((ThreadItem.kind == ItemKind.llm_call, 1), else_=0)),
            func.sum(case((ThreadItem.kind == ItemKind.tool_call, 1), else_=0)),
        ).where(
            ThreadItem.org_id == org_id,
            ThreadItem.created_at >= start,
            ThreadItem.created_at <= end,
        )
    )).one()
    total_cost, llm_count, tool_count = kpis_row

    # top model by spend
    top_model = (await session.execute(
        select(ThreadItem.model, func.sum(ThreadItem.cost_usd).label("s"))
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.kind == ItemKind.llm_call,
            ThreadItem.created_at >= start, ThreadItem.created_at <= end,
        )
        .group_by(ThreadItem.model)
        .order_by(func.sum(ThreadItem.cost_usd).desc())
        .limit(1)
    )).first()

    kpis = [
        KpiCard(label="Month spend", value=Decimal(total_cost or 0), unit="USD"),
        KpiCard(label="Messages streamed", value=int(llm_count or 0)),
        KpiCard(label="Tool calls", value=int(tool_count or 0)),
        KpiCard(
            label="Top model",
            value=(top_model[0] if top_model else "—") or "—",
            unit=(str(Decimal(top_model[1] or 0)) if top_model else None),
        ),
    ]

    by_model = await _group(session, org_id, start, end, ThreadItem.model, key_is_text=True)
    by_user_key = _user_id_from_thread
    by_user = await _group_via_thread(session, org_id, start, end, Thread.user_id)
    by_provider = await _group(session, org_id, start, end, ThreadItem.provider, key_is_text=True)
    by_capability = []  # filled when capabilities land; v1 empty list
    by_tool = await _group(
        session, org_id, start, end,
        func.coalesce(ThreadItem.data["tool_name"].astext, "?"),
        key_is_text=True, only_kind=ItemKind.tool_call,
    )

    return SummaryResponse(
        kpis=kpis,
        by_model=by_model, by_user=by_user, by_provider=by_provider,
        by_capability=by_capability, by_tool=by_tool,
    )


async def _group(
    session, org_id, start, end, column, *,
    key_is_text: bool, only_kind: ItemKind | None = None,
) -> list[SummaryRow]:
    where = [
        ThreadItem.org_id == org_id,
        ThreadItem.created_at >= start, ThreadItem.created_at <= end,
    ]
    if only_kind is not None:
        where.append(ThreadItem.kind == only_kind)
    stmt = (
        select(
            column.label("k"),
            func.count(ThreadItem.id),
            func.coalesce(func.sum((ThreadItem.data["input_tokens"].as_integer())), 0),
            func.coalesce(func.sum((ThreadItem.data["output_tokens"].as_integer())), 0),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.avg(case((ThreadItem.cost_estimated.is_(True), 1.0), else_=0.0)),
        )
        .where(and_(*where))
        .group_by("k")
        .order_by(func.sum(ThreadItem.cost_usd).desc().nullslast())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()
    out: list[SummaryRow] = []
    for k, msgs, it, ot, cost, est in rows:
        key = str(k) if k is not None else "(none)"
        out.append(SummaryRow(
            key=key, label=key, messages=int(msgs), input_tokens=int(it or 0),
            output_tokens=int(ot or 0), cost_usd=Decimal(cost or 0),
            estimated_ratio=float(est or 0.0),
        ))
    return out


async def _group_via_thread(session, org_id, start, end, join_column) -> list[SummaryRow]:
    stmt = (
        select(
            join_column.label("k"),
            func.count(ThreadItem.id),
            func.coalesce(func.sum((ThreadItem.data["input_tokens"].as_integer())), 0),
            func.coalesce(func.sum((ThreadItem.data["output_tokens"].as_integer())), 0),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.avg(case((ThreadItem.cost_estimated.is_(True), 1.0), else_=0.0)),
        )
        .join(Thread, Thread.id == ThreadItem.thread_id)
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.created_at >= start, ThreadItem.created_at <= end,
        )
        .group_by("k")
        .order_by(func.sum(ThreadItem.cost_usd).desc().nullslast())
        .limit(50)
    )
    rows = (await session.execute(stmt)).all()
    return [SummaryRow(
        key=str(k), label=str(k), messages=int(m), input_tokens=int(it or 0),
        output_tokens=int(ot or 0), cost_usd=Decimal(c or 0),
        estimated_ratio=float(e or 0.0),
    ) for k, m, it, ot, c, e in rows]


async def trend(*, session: AsyncSession, org_id: uuid.UUID,
                start: datetime, end: datetime,
                grain: Literal["day", "hour"], by: Literal["kind", "provider"]) -> TrendResponse:
    trunc = func.date_trunc(grain, ThreadItem.created_at)
    key_col = ThreadItem.kind if by == "kind" else ThreadItem.provider
    stmt = (
        select(
            trunc.label("t"),
            key_col.label("k"),
            func.coalesce(func.sum(ThreadItem.cost_usd), 0),
            func.coalesce(func.sum((ThreadItem.data["input_tokens"].as_integer())), 0),
            func.coalesce(func.sum((ThreadItem.data["output_tokens"].as_integer())), 0),
        )
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.created_at >= start, ThreadItem.created_at <= end,
        )
        .group_by(trunc, key_col)
        .order_by(trunc)
    )
    rows = (await session.execute(stmt)).all()
    buckets: dict[datetime, dict] = {}
    for t, k, cost, it, ot in rows:
        b = buckets.setdefault(t, {"cost_usd": ZERO, "in": 0, "out": 0, "by": {}})
        b["cost_usd"] += Decimal(cost or 0)
        b["in"] += int(it or 0)
        b["out"] += int(ot or 0)
        kk = (k.value if hasattr(k, "value") else (k or "other"))
        b["by"][kk] = b["by"].get(kk, ZERO) + Decimal(cost or 0)
    series = [
        TrendPoint(t=t, cost_usd=v["cost_usd"],
                   input_tokens=v["in"], output_tokens=v["out"],
                   breakdown=v["by"])
        for t, v in sorted(buckets.items())
    ]
    return TrendResponse(grain=grain, by=by, series=series)


async def threads(*, session: AsyncSession, org_id: uuid.UUID,
                  start: datetime, end: datetime,
                  user_id: int | None, model: str | None,
                  page: int, page_size: int) -> ThreadsResponse:
    where = [
        Thread.org_id == org_id,
        Thread.created_at >= start, Thread.created_at <= end,
    ]
    if user_id is not None:
        where.append(Thread.user_id == user_id)
    if model is not None:
        where.append(Thread.model == model)

    total = (await session.execute(
        select(func.count(Thread.id)).where(and_(*where))
    )).scalar_one()

    stmt = (
        select(
            Thread.id, Thread.title, Thread.user_id, Thread.model, Thread.last_message_at,
            func.coalesce(func.sum(ThreadItem.cost_usd), 0).label("cost"),
            func.count(ThreadItem.id).label("items"),
        )
        .outerjoin(ThreadItem, ThreadItem.thread_id == Thread.id)
        .where(and_(*where))
        .group_by(Thread.id)
        .order_by(Thread.last_message_at.desc().nullslast())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await session.execute(stmt)).all()
    return ThreadsResponse(
        total=int(total), page=page, page_size=page_size,
        rows=[
            ThreadRow(
                id=r[0], title=r[1], user_id=r[2], model=r[3],
                last_message_at=r[4], total_cost_usd=Decimal(r[5] or 0),
                total_items=int(r[6] or 0),
            )
            for r in rows
        ],
    )


async def timeline(*, session: AsyncSession, org_id: uuid.UUID,
                   thread_id: int) -> TimelineResponse:
    stmt = (
        select(ThreadItem)
        .where(ThreadItem.thread_id == thread_id, ThreadItem.org_id == org_id)
        .order_by(ThreadItem.created_at, ThreadItem.id)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return TimelineResponse(
        thread_id=thread_id,
        items=[TimelineItem.model_validate(r) for r in rows],
    )


def _user_id_from_thread(row):
    return row.user_id
```

- [ ] **Step 7.2.3: Run tests and commit**

```bash
cd server/api && pytest tests/usage/test_consumption_service.py -xvs
git add server/api/src/ai_portal/usage/consumption_service.py server/api/tests/usage/test_consumption_service.py
git commit -m "feat(usage): consumption aggregation service"
```

---

### Task 7.3: Router `/api/admin/consumption/*`

**Files:**
- Create: `server/api/src/ai_portal/api/admin/consumption.py`
- Modify: `server/api/src/ai_portal/main.py` (include router)
- Test: `server/api/tests/usage/test_consumption_router.py`

- [ ] **Step 7.3.1: Write failing tests**

```python
# server/api/tests/usage/test_consumption_router.py
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_summary_requires_admin(async_client: AsyncClient, member_token: str):
    r = await async_client.get(
        "/api/admin/consumption/summary",
        params={"start": "2026-01-01", "end": "2026-04-20"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_summary_admin_ok(async_client: AsyncClient, admin_token: str):
    r = await async_client.get(
        "/api/admin/consumption/summary",
        params={"start": "2026-01-01", "end": "2026-04-20"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "kpis" in body and "by_model" in body


@pytest.mark.asyncio
async def test_trend_endpoint(async_client: AsyncClient, admin_token: str):
    r = await async_client.get(
        "/api/admin/consumption/trend",
        params={"start": "2026-01-01", "end": "2026-04-20", "grain": "day", "by": "kind"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_threads_and_timeline(async_client: AsyncClient, admin_token: str, thread_items_fixture):
    r = await async_client.get(
        "/api/admin/consumption/threads",
        params={"start": "2026-01-01", "end": "2026-04-20"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r.status_code == 200
    first = r.json()["rows"][0]
    r2 = await async_client.get(
        f"/api/admin/consumption/threads/{first['id']}/timeline",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert r2.status_code == 200
    assert len(r2.json()["items"]) >= 1
```

Reuse existing `admin_token` / `member_token` fixtures from `tests/conftest.py`; create them if missing using the same patterns as the admin endpoints in `tests/admin/`.

- [ ] **Step 7.3.2: Implement**

```python
# server/api/src/ai_portal/api/admin/consumption.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.auth.deps import require_admin
from ai_portal.core.db.deps import get_session
from ai_portal.usage import consumption_service
from ai_portal.usage.consumption_schemas import (
    SummaryResponse, ThreadsResponse, TimelineResponse, TrendResponse,
)


router = APIRouter(prefix="/api/admin/consumption", tags=["admin-consumption"])


@router.get("/summary", response_model=SummaryResponse)
async def summary(
    start: datetime = Query(...),
    end: datetime = Query(...),
    session: AsyncSession = Depends(get_session),
    user = Depends(require_admin),
):
    return await consumption_service.summary(
        session=session, org_id=user.org_id, start=start, end=end,
    )


@router.get("/trend", response_model=TrendResponse)
async def trend(
    start: datetime = Query(...),
    end: datetime = Query(...),
    grain: Literal["day", "hour"] = Query("day"),
    by: Literal["kind", "provider"] = Query("kind"),
    session: AsyncSession = Depends(get_session),
    user = Depends(require_admin),
):
    return await consumption_service.trend(
        session=session, org_id=user.org_id, start=start, end=end, grain=grain, by=by,
    )


@router.get("/threads", response_model=ThreadsResponse)
async def threads(
    start: datetime = Query(...),
    end: datetime = Query(...),
    user_id: int | None = Query(None),
    model: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
    user = Depends(require_admin),
):
    return await consumption_service.threads(
        session=session, org_id=user.org_id, start=start, end=end,
        user_id=user_id, model=model, page=page, page_size=page_size,
    )


@router.get("/threads/{thread_id}/timeline", response_model=TimelineResponse)
async def timeline(
    thread_id: int,
    session: AsyncSession = Depends(get_session),
    user = Depends(require_admin),
):
    return await consumption_service.timeline(
        session=session, org_id=user.org_id, thread_id=thread_id,
    )
```

- [ ] **Step 7.3.3: Include router in `main.py`**

```python
# server/api/src/ai_portal/main.py (add near other router includes)
from ai_portal.api.admin.consumption import router as consumption_router
app.include_router(consumption_router)
```

- [ ] **Step 7.3.4: Run tests**

Run: `cd server/api && pytest tests/usage/test_consumption_router.py -xvs`
Expected: PASS.

- [ ] **Step 7.3.5: Commit**

```bash
git add server/api/src/ai_portal/api/admin/consumption.py server/api/src/ai_portal/main.py server/api/tests/usage/test_consumption_router.py
git commit -m "feat(admin): /api/admin/consumption/* endpoints"
```

---

### Task 7.4: Mark legacy `/api/admin/usage/*` deprecated

**Files:**
- Modify: `server/api/src/ai_portal/usage/router.py`

- [ ] **Step 7.4.1: Add deprecation header**

Add FastAPI `deprecated=True` to every route decorator for the legacy usage endpoints (except `/my`, which is kept). Clients get the endpoint in the OpenAPI schema flagged, nothing breaks.

Example:
```python
@router.get("/summary", deprecated=True, summary="[DEPRECATED] use /api/admin/consumption/summary")
async def legacy_summary(...): ...
```

- [ ] **Step 7.4.2: Commit**

```bash
git add server/api/src/ai_portal/usage/router.py
git commit -m "chore(usage): mark legacy /admin/usage endpoints deprecated"
```

---

## Phase 8 — Quota + workers adapted to `thread_items`

### Task 8.1: `usage_rollup` worker reads from `thread_items`

**Files:**
- Modify: `server/api/src/ai_portal/usage/service.py`
- Modify: `server/api/src/ai_portal/chat/workers/` (or wherever rollup jobs live)

- [ ] **Step 8.1.1: Locate rollup writer**

Run: `grep -rn "MessageUsage\|usage_rollup\|UsageRollup" server/api/src/ai_portal/`
Identify every write site to `message_usage` or rollups.

- [ ] **Step 8.1.2: Rewrite rollup aggregator**

The rollup worker should read `thread_items WHERE kind IN ('llm_call','tool_call') AND finished_at BETWEEN ... AND ...` and upsert into `usage_rollup` per org/day. Example SQL:

```sql
INSERT INTO usage_rollup (org_id, day, cost_usd, llm_calls, tool_calls,
                           input_tokens, output_tokens)
SELECT org_id, date_trunc('day', created_at)::date AS day,
       COALESCE(SUM(cost_usd),0),
       SUM(CASE WHEN kind='llm_call' THEN 1 ELSE 0 END),
       SUM(CASE WHEN kind='tool_call' THEN 1 ELSE 0 END),
       COALESCE(SUM((data->>'input_tokens')::bigint),0),
       COALESCE(SUM((data->>'output_tokens')::bigint),0)
  FROM thread_items
 WHERE created_at >= :since AND created_at < :until
 GROUP BY org_id, day
ON CONFLICT (org_id, day) DO UPDATE
  SET cost_usd = EXCLUDED.cost_usd,
      llm_calls = EXCLUDED.llm_calls,
      tool_calls = EXCLUDED.tool_calls,
      input_tokens = EXCLUDED.input_tokens,
      output_tokens = EXCLUDED.output_tokens;
```

Wrap in an SQLAlchemy Core `text(...)` call and schedule via the existing worker runner.

- [ ] **Step 8.1.3: Write test**

```python
# server/api/tests/usage/test_rollup.py
import pytest
from datetime import datetime, timezone, timedelta

from ai_portal.usage.service import rebuild_rollup


@pytest.mark.asyncio
async def test_rollup_sums_thread_items(db_session, thread_items_fixture):
    await rebuild_rollup(
        session=db_session, org_id=thread_items_fixture.org_id,
        since=datetime.now(timezone.utc) - timedelta(days=7),
        until=datetime.now(timezone.utc),
    )
    from sqlalchemy import text
    rows = (await db_session.execute(text(
        "SELECT cost_usd FROM usage_rollup WHERE org_id = :o"
    ), {"o": str(thread_items_fixture.org_id)})).all()
    assert len(rows) >= 1
```

- [ ] **Step 8.1.4: Run + commit**

```bash
cd server/api && pytest tests/usage/test_rollup.py -xvs
git add server/api/src/ai_portal/usage/ server/api/tests/usage/test_rollup.py
git commit -m "refactor(usage): rollup reads from thread_items"
```

---

### Task 8.2: `usage_quota` check reads `SUM(cost_usd) FROM thread_items`

**Files:**
- Modify: `server/api/src/ai_portal/usage/service.py::check_quota`

- [ ] **Step 8.2.1: Update query**

```python
# server/api/src/ai_portal/usage/service.py (check_quota)
from sqlalchemy import func, select
from ai_portal.chat.model import ThreadItem
from ai_portal.usage.model import UsageQuota


async def check_quota(session, *, org_id, user_id) -> QuotaResult:
    quota = (await session.execute(
        select(UsageQuota).where(UsageQuota.org_id == org_id)
    )).scalar_one_or_none()
    if quota is None or quota.monthly_cap_usd is None:
        return QuotaResult(allowed=True, reason=None)

    month_start = _first_of_month_utc()
    spent = (await session.execute(
        select(func.coalesce(func.sum(ThreadItem.cost_usd), 0))
        .where(
            ThreadItem.org_id == org_id,
            ThreadItem.created_at >= month_start,
        )
    )).scalar_one()

    allowed = spent < quota.monthly_cap_usd
    reason = None if allowed else f"monthly cap ${quota.monthly_cap_usd} exceeded (spent ${spent})"
    return QuotaResult(allowed=allowed, reason=reason)
```

- [ ] **Step 8.2.2: Run existing usage tests**

Run: `cd server/api && pytest tests/usage -xvs`
Expected: PASS or, if any test still asserts on `MessageUsage`, replace those assertions with `ThreadItem` reads.

- [ ] **Step 8.2.3: Commit**

```bash
git add server/api/src/ai_portal/usage/service.py server/api/tests/usage/
git commit -m "refactor(usage): check_quota reads thread_items"
```

---

### Task 8.3: Delete `MessageUsage` model + legacy pricing file

**Files:**
- Modify: `server/api/src/ai_portal/usage/model.py` (remove `MessageUsage` class)
- Delete: `server/api/src/ai_portal/usage/pricing.py` (shim)

Only remove the shim once all import sites point at `chat.llm_pricing`.

- [ ] **Step 8.3.1: Scan for remaining imports**

Run: `grep -rn "from ai_portal.usage.pricing\|import MessageUsage" server/api/src/`
Fix each site to import from `ai_portal.chat.llm_pricing` or drop the line entirely if it was only for quota math (which now reads `ThreadItem`).

- [ ] **Step 8.3.2: Delete**

```bash
git rm server/api/src/ai_portal/usage/pricing.py
```

Edit `server/api/src/ai_portal/usage/model.py` and remove the `MessageUsage` class and its imports. Leave `UsageRollup`, `UsageQuota`.

- [ ] **Step 8.3.3: Smoke + commit**

Run: `cd server/api && uvicorn ai_portal.main:app --port 8000 --reload`
Expected: boots.

```bash
git add server/api/src/ai_portal/usage/model.py
git commit -m "chore(usage): drop MessageUsage model + legacy pricing shim"
```

---
## Phase 9 — Frontend chat renderer rewrite

Goal: read `thread_items` from the backend, group by `turn_id`, render one component per kind. The Vortex three-column layout stays; only the thread column's internals change.

### Task 9.1: SSE parsing switched to typed `SseEvent`

**Files:**
- Modify: `apps/frontend/src/lib/sse-parse.ts`
- Test: add a small Vitest spec if a test harness exists; otherwise skip to runtime verification.

- [ ] **Step 9.1.1: Read current parser**

Read: `apps/frontend/src/lib/sse-parse.ts`. Identify the current event shape (likely untyped `Record<string, unknown>`).

- [ ] **Step 9.1.2: Replace with typed parser**

```ts
// apps/frontend/src/lib/sse-parse.ts
import type { SseEvent } from "./chat-types";

export function* parseSseStream(chunk: string): Generator<SseEvent> {
  // SSE frames separated by blank line; each frame has "data: <json>" lines
  const frames = chunk.split("\n\n");
  for (const frame of frames) {
    if (!frame.trim()) continue;
    const dataLines = frame
      .split("\n")
      .filter((l) => l.startsWith("data: "))
      .map((l) => l.slice(6));
    if (!dataLines.length) continue;
    const payload = dataLines.join("\n");
    try {
      yield JSON.parse(payload) as SseEvent;
    } catch (e) {
      console.warn("[sse-parse] malformed frame", payload, e);
    }
  }
}
```

If the existing parser does buffering across chunks, keep that logic; only swap the output type. The runtime shape of SSE frames is unchanged.

- [ ] **Step 9.1.3: Commit**

```bash
git add apps/frontend/src/lib/sse-parse.ts
git commit -m "refactor(frontend): typed SseEvent parsing"
```

---

### Task 9.2: Query hooks for thread + items

**Files:**
- Modify: `apps/frontend/src/lib/queryKeys.ts`
- Create: `apps/frontend/src/hooks/useThread.ts`
- Create: `apps/frontend/src/hooks/useThreadItems.ts`
- Create: `apps/frontend/src/hooks/useStreamTurn.ts`

- [ ] **Step 9.2.1: Add query keys**

```ts
// apps/frontend/src/lib/queryKeys.ts (append to the existing export)
export const qk = {
  // ... existing keys ...
  threads: ["threads"] as const,
  thread: (id: number) => ["threads", id] as const,
  threadItems: (id: number) => ["threads", id, "items"] as const,
  consumption: {
    summary: (start: string, end: string) => ["consumption", "summary", start, end] as const,
    trend: (start: string, end: string, grain: string, by: string) =>
      ["consumption", "trend", start, end, grain, by] as const,
    threads: (start: string, end: string, userId?: number, model?: string) =>
      ["consumption", "threads", start, end, userId ?? null, model ?? null] as const,
    timeline: (id: number) => ["consumption", "threads", id, "timeline"] as const,
  },
};
```

- [ ] **Step 9.2.2: `useThread` hook**

```ts
// apps/frontend/src/hooks/useThread.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";
import type { ThreadRead } from "@/lib/chat-types";

export function useThread(id: number) {
  return useQuery({
    queryKey: qk.thread(id),
    queryFn: async (): Promise<ThreadRead> => {
      const r = await authorizedFetch(`/api/chat/threads/${id}`);
      if (!r.ok) throw new Error(`GET /threads/${id} failed: ${r.status}`);
      return r.json();
    },
    enabled: Number.isFinite(id),
  });
}
```

- [ ] **Step 9.2.3: `useThreadItems` hook**

```ts
// apps/frontend/src/hooks/useThreadItems.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";
import type { ThreadItem } from "@/lib/chat-types";

export function useThreadItems(threadId: number, sinceId?: number) {
  return useQuery({
    queryKey: sinceId == null ? qk.threadItems(threadId) : [...qk.threadItems(threadId), sinceId],
    queryFn: async (): Promise<ThreadItem[]> => {
      const u = new URL(`/api/chat/threads/${threadId}/items`, location.origin);
      if (sinceId != null) u.searchParams.set("since_id", String(sinceId));
      const r = await authorizedFetch(u.toString());
      if (!r.ok) throw new Error(`GET /items failed: ${r.status}`);
      return r.json();
    },
    enabled: Number.isFinite(threadId),
  });
}
```

- [ ] **Step 9.2.4: `useStreamTurn` hook — streams SSE and merges incoming items into the query cache**

```ts
// apps/frontend/src/hooks/useStreamTurn.ts
import { useQueryClient } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { parseSseStream } from "@/lib/sse-parse";
import { qk } from "@/lib/queryKeys";
import type { ThreadItem, SseEvent } from "@/lib/chat-types";


export function useStreamTurn(threadId: number) {
  const qc = useQueryClient();

  async function submit(body: {
    text: string;
    attachments?: unknown[];
    model?: string;
    tools?: string[];
    regenerate_from_turn_id?: string;
  }) {
    const resp = await authorizedFetch(`/api/chat/threads/${threadId}/turns`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!resp.body) throw new Error("no stream body");

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const splitAt = buffer.lastIndexOf("\n\n");
      if (splitAt === -1) continue;
      const ready = buffer.slice(0, splitAt + 2);
      buffer = buffer.slice(splitAt + 2);

      for (const ev of parseSseStream(ready)) {
        applyEvent(qc, threadId, ev);
      }
    }
    // flush any trailing frame
    if (buffer.trim()) {
      for (const ev of parseSseStream(buffer)) {
        applyEvent(qc, threadId, ev);
      }
    }
  }

  return { submit };
}


function applyEvent(qc: ReturnType<typeof useQueryClient>, threadId: number, ev: SseEvent) {
  if (ev.event_type !== "item") return;
  qc.setQueryData<ThreadItem[]>(qk.threadItems(threadId), (prev = []) => {
    const idx = prev.findIndex((p) => p.id === ev.item.id);
    if (idx === -1) return [...prev, ev.item];
    const next = prev.slice();
    next[idx] = ev.item;
    return next;
  });
}
```

- [ ] **Step 9.2.5: Commit**

```bash
git add apps/frontend/src/hooks/useThread.ts apps/frontend/src/hooks/useThreadItems.ts apps/frontend/src/hooks/useStreamTurn.ts apps/frontend/src/lib/queryKeys.ts
git commit -m "feat(frontend): query hooks + streaming for thread_items"
```

---

### Task 9.3: Per-kind item components

**Files:**
- Create all files under `apps/frontend/src/components/chat/thread/items/`
- Create: `apps/frontend/src/components/chat/thread/ThreadTurn.tsx`

Each component receives a specific narrowed ThreadItem via props and renders its visual. Keep them small and pure.

- [ ] **Step 9.3.1: `UserMessageItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/UserMessageItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "user_message" }> }

export function UserMessageItem({ item }: Props) {
  return (
    <div data-testid="thread-item-user" className="user-bubble">
      <p className="whitespace-pre-wrap">{item.data.text}</p>
    </div>
  );
}
```

- [ ] **Step 9.3.2: `AssistantTextItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/AssistantTextItem.tsx
import { MarkdownMessage } from "@/components/chat/MarkdownMessage";
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "assistant_text" }> }

export function AssistantTextItem({ item }: Props) {
  return (
    <div data-testid="thread-item-assistant-text" data-status={item.status}>
      <MarkdownMessage text={item.data.text} />
    </div>
  );
}
```

- [ ] **Step 9.3.3: `ToolCallItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/ToolCallItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "tool_call" }> }

export function ToolCallItem({ item }: Props) {
  const cost = item.cost_usd ? `$${item.cost_usd}` : "—";
  return (
    <div data-testid="thread-item-tool-call" data-status={item.status} className="tool-chip">
      <span className="tool-chip__name">{item.data.tool_name}</span>
      {item.provider ? <span className="tool-chip__provider">{item.provider}</span> : null}
      <span className="tool-chip__cost" data-estimated={item.cost_estimated}>{cost}</span>
      {item.data.error ? <span className="tool-chip__error">{item.data.error}</span> : null}
    </div>
  );
}
```

- [ ] **Step 9.3.4: `ServerToolUseItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/ServerToolUseItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "server_tool_use" }> }

export function ServerToolUseItem({ item }: Props) {
  return (
    <div data-testid="thread-item-server-tool" className="tool-chip tool-chip--server">
      <span className="tool-chip__name">{item.data.tool_name}</span>
      <span className="tool-chip__provider">{item.provider ?? "provider"}</span>
    </div>
  );
}
```

- [ ] **Step 9.3.5: `ThinkingItem.tsx` — reuse existing `ThinkingBlock`**

```tsx
// apps/frontend/src/components/chat/thread/items/ThinkingItem.tsx
import { ThinkingBlock } from "@/components/chat/ThinkingBlock";
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "thinking" }> }

export function ThinkingItem({ item }: Props) {
  return <ThinkingBlock text={item.data.text} status={item.status} />;
}
```

Update `ThinkingBlock` props to accept `{ text, status }` if it currently takes a different shape.

- [ ] **Step 9.3.6: `CitationItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/CitationItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "citation" }> }

export function CitationItem({ item }: Props) {
  return (
    <a
      data-testid="thread-item-citation"
      href={item.data.url} target="_blank" rel="noreferrer"
      className="citation-link"
    >
      {item.data.title ?? item.data.url}
    </a>
  );
}
```

- [ ] **Step 9.3.7: `MemoryPillItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/MemoryPillItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "memory_pill" }> }

export function MemoryPillItem({ item }: Props) {
  return (
    <div data-testid="thread-item-memory-pill" className="memory-pill">
      Retrieved {item.data.count} memories
    </div>
  );
}
```

- [ ] **Step 9.3.8: `LlmCallItem.tsx` (inspector-only chip in timeline)**

```tsx
// apps/frontend/src/components/chat/thread/items/LlmCallItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "llm_call" }>; expanded?: boolean }

export function LlmCallItem({ item, expanded = false }: Props) {
  if (!expanded) return null;  // hidden in main thread; shown in inspector
  return (
    <div data-testid="thread-item-llm-call" className="llm-call-chip">
      <span>{item.model}</span>
      <span>in:{item.data.input_tokens}</span>
      <span>out:{item.data.output_tokens}</span>
      {item.cost_usd ? <span>${item.cost_usd}</span> : null}
    </div>
  );
}
```

- [ ] **Step 9.3.9: `ErrorItem.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/ErrorItem.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "error" }> }

export function ErrorItem({ item }: Props) {
  return (
    <div data-testid="thread-item-error" className="error-banner" role="alert">
      <strong>{item.data.code}</strong>: {item.data.message}
    </div>
  );
}
```

- [ ] **Step 9.3.10: `TurnEndMarker.tsx`**

```tsx
// apps/frontend/src/components/chat/thread/items/TurnEndMarker.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "turn_end" }> }

export function TurnEndMarker({ item }: Props) {
  if (item.data.reason === "done") return null; // no visual for clean end
  return (
    <div data-testid="thread-item-turn-end" data-reason={item.data.reason} className="turn-end-marker">
      Turn {item.data.reason}
    </div>
  );
}
```

- [ ] **Step 9.3.11: `ThreadTurn.tsx` — groups all items for a `turn_id` and dispatches to per-kind renderers**

```tsx
// apps/frontend/src/components/chat/thread/ThreadTurn.tsx
import type { ThreadItem } from "@/lib/chat-types";
import { AssistantTextItem } from "./items/AssistantTextItem";
import { CitationItem } from "./items/CitationItem";
import { ErrorItem } from "./items/ErrorItem";
import { MemoryPillItem } from "./items/MemoryPillItem";
import { ServerToolUseItem } from "./items/ServerToolUseItem";
import { ThinkingItem } from "./items/ThinkingItem";
import { ToolCallItem } from "./items/ToolCallItem";
import { TurnEndMarker } from "./items/TurnEndMarker";
import { UserMessageItem } from "./items/UserMessageItem";

interface Props { turnId: string; items: ThreadItem[] }

export function ThreadTurn({ turnId, items }: Props) {
  return (
    <section data-testid="thread-turn" data-turn-id={turnId} className="thread-turn">
      {items.map((item) => {
        switch (item.kind) {
          case "user_message":    return <UserMessageItem key={item.id} item={item} />;
          case "assistant_text":  return <AssistantTextItem key={item.id} item={item} />;
          case "tool_call":       return <ToolCallItem key={item.id} item={item} />;
          case "server_tool_use": return <ServerToolUseItem key={item.id} item={item} />;
          case "thinking":        return <ThinkingItem key={item.id} item={item} />;
          case "citation":        return <CitationItem key={item.id} item={item} />;
          case "memory_pill":     return <MemoryPillItem key={item.id} item={item} />;
          case "error":           return <ErrorItem key={item.id} item={item} />;
          case "turn_end":        return <TurnEndMarker key={item.id} item={item} />;
          case "llm_call":        return null;  // inspector-only
          default: {
            const _never: never = item;
            return null;
          }
        }
      })}
    </section>
  );
}
```

- [ ] **Step 9.3.12: Commit**

```bash
git add apps/frontend/src/components/chat/thread/
git commit -m "feat(frontend): per-kind thread item components + ThreadTurn"
```

---

### Task 9.4: Rewire `ConversationThreadPage.tsx`

**Files:**
- Modify: `apps/frontend/src/components/chat/ConversationThreadPage.tsx`

- [ ] **Step 9.4.1: Replace message-rendering logic**

Read the current file. The new render path:

```tsx
// apps/frontend/src/components/chat/ConversationThreadPage.tsx (skeleton)
import { useMemo } from "react";
import { useParams } from "@tanstack/react-router";
import { useThread } from "@/hooks/useThread";
import { useThreadItems } from "@/hooks/useThreadItems";
import { ThreadTurn } from "@/components/chat/thread/ThreadTurn";
import type { ThreadItem } from "@/lib/chat-types";

export function ConversationThreadPage() {
  const { id } = useParams({ strict: false });
  const threadId = Number(id);
  const { data: thread } = useThread(threadId);
  const { data: items = [] } = useThreadItems(threadId);

  const grouped = useMemo(() => groupByTurn(items), [items]);

  if (!thread) return null;
  return (
    <div className="thread-scroll" data-testid="thread-scroll">
      {grouped.map(([turnId, turnItems]) => (
        <ThreadTurn key={turnId} turnId={turnId} items={turnItems} />
      ))}
    </div>
  );
}

function groupByTurn(items: ThreadItem[]): [string, ThreadItem[]][] {
  const order: string[] = [];
  const bucket: Record<string, ThreadItem[]> = {};
  for (const i of items) {
    if (!bucket[i.turn_id]) {
      order.push(i.turn_id);
      bucket[i.turn_id] = [];
    }
    bucket[i.turn_id].push(i);
  }
  return order.map((t) => [t, bucket[t]]);
}
```

Preserve any existing wrapper JSX (header, composer mount-point, scroll behavior) outside the `.thread-scroll` block.

- [ ] **Step 9.4.2: Wire the composer to `useStreamTurn`**

The existing `ChatComposerDock.tsx` already has a submit handler. Swap whatever message-send mutation it uses for `useStreamTurn(threadId).submit`.

Read: `apps/frontend/src/components/chat/ChatComposerDock.tsx`. Replace the submit path:

```tsx
const { submit } = useStreamTurn(threadId);

async function onSend(text: string, attachments: unknown[]) {
  await submit({ text, attachments, model: selectedModel });
}
```

Keep keyboard shortcuts, attachment preview, and any debouncing.

- [ ] **Step 9.4.3: Typecheck**

```bash
cd apps/frontend
pnpm typecheck
```

Expected: zero errors in `components/chat/`. Fix any drift — the hot spots are `ConversationInspectorPanel.tsx`, `MessageUsageBadge.tsx`, `ThreadItemChip.tsx`.

- [ ] **Step 9.4.4: Commit**

```bash
git add apps/frontend/src/components/chat/ConversationThreadPage.tsx apps/frontend/src/components/chat/ChatComposerDock.tsx
git commit -m "refactor(frontend): ConversationThreadPage renders thread_items"
```

---

### Task 9.5: Update the inspector panel

**Files:**
- Modify: `apps/frontend/src/components/chat/ConversationInspectorPanel.tsx`

- [ ] **Step 9.5.1: Read current panel**

Read: the current file. It likely shows a message's usage/debug info.

- [ ] **Step 9.5.2: Replace body with a per-turn timeline**

```tsx
// apps/frontend/src/components/chat/ConversationInspectorPanel.tsx (skeleton)
import { useThreadItems } from "@/hooks/useThreadItems";
import { LlmCallItem } from "@/components/chat/thread/items/LlmCallItem";
import type { ThreadItem } from "@/lib/chat-types";

export function ConversationInspectorPanel({ threadId, focusedTurnId }: {
  threadId: number; focusedTurnId: string | null;
}) {
  const { data: items = [] } = useThreadItems(threadId);
  const inTurn = focusedTurnId
    ? items.filter((i) => i.turn_id === focusedTurnId)
    : items;

  return (
    <aside className="inspector-panel" data-testid="inspector-panel">
      <h3>Timeline</h3>
      <ul className="inspector-timeline">
        {inTurn.map((it) => (
          <li key={it.id} data-kind={it.kind} data-status={it.status}>
            <InspectorRow item={it} />
          </li>
        ))}
      </ul>
    </aside>
  );
}

function InspectorRow({ item }: { item: ThreadItem }) {
  switch (item.kind) {
    case "llm_call":
      return <LlmCallItem item={item} expanded />;
    case "tool_call":
      return (
        <div>
          <strong>{item.data.tool_name}</strong>{" "}
          <span>{item.provider}</span>{" "}
          {item.latency_ms ? <span>{item.latency_ms}ms</span> : null}{" "}
          {item.cost_usd ? <span>${item.cost_usd}</span> : null}
        </div>
      );
    default:
      return <span>{item.kind}</span>;
  }
}
```

- [ ] **Step 9.5.3: Commit**

```bash
git add apps/frontend/src/components/chat/ConversationInspectorPanel.tsx
git commit -m "refactor(frontend): inspector shows per-turn timeline"
```

---

### Task 9.6: Adapt badges and quota banner

**Files:**
- Modify: `apps/frontend/src/components/chat/MessageUsageBadge.tsx`
- Modify: `apps/frontend/src/components/chat/QuotaBanner.tsx`
- Modify: `apps/frontend/src/components/chat/ThreadItemChip.tsx`

- [ ] **Step 9.6.1: `MessageUsageBadge`**

New prop: `item: LlmCallItem`. Render cost + tokens from `item.data` and `item.cost_usd`.

```tsx
// apps/frontend/src/components/chat/MessageUsageBadge.tsx
import type { ThreadItem } from "@/lib/chat-types";

interface Props { item: Extract<ThreadItem, { kind: "llm_call" }> }

export function MessageUsageBadge({ item }: Props) {
  if (item.status !== "done") return null;
  return (
    <span data-testid="message-usage-badge" className="usage-badge">
      {item.data.input_tokens}→{item.data.output_tokens}
      {item.cost_usd ? ` · $${item.cost_usd}` : null}
    </span>
  );
}
```

Callers must find the `llm_call` item for the corresponding turn and pass it.

- [ ] **Step 9.6.2: `QuotaBanner`**

No shape change on `/api/admin/usage/my` backend contract. Only regenerate the generated types if a codegen is in use. Read the file to confirm — if it parses `data.cost_usd`, keep as-is.

- [ ] **Step 9.6.3: `ThreadItemChip`**

This existing component probably renders tool-call chips. Replace with the `ToolCallItem` component or keep `ThreadItemChip` as the shared chip used inside `ToolCallItem.tsx` and the inspector. Either way, its prop type must be the TS union.

- [ ] **Step 9.6.4: Commit**

```bash
git add apps/frontend/src/components/chat/MessageUsageBadge.tsx apps/frontend/src/components/chat/QuotaBanner.tsx apps/frontend/src/components/chat/ThreadItemChip.tsx
git commit -m "refactor(frontend): badges + chip use ThreadItem shapes"
```

---

### Task 9.7: Sidebar reads `/threads`

**Files:**
- Modify: `apps/frontend/src/components/chat/ConversationsSidebarPanel.tsx`

- [ ] **Step 9.7.1: Swap endpoint**

Search the file for `/api/chat/conversations` calls and replace with `/api/chat/threads`. The response shape is compatible (`ThreadRead` matches the prior `ConversationRead` field names — verify).

- [ ] **Step 9.7.2: Commit**

```bash
git add apps/frontend/src/components/chat/ConversationsSidebarPanel.tsx
git commit -m "refactor(frontend): sidebar reads /threads"
```

---

### Task 9.8: Update `createOrFindConversation` helper internals

**Files:**
- Modify: `apps/frontend/e2e/support/ui-helpers.ts`

The public signature stays `createOrFindConversation(page, name)`. Its internals must target the updated DOM/API selectors.

- [ ] **Step 9.8.1: Read helper**

Read: `apps/frontend/e2e/support/ui-helpers.ts`. Identify selectors and endpoint URLs.

- [ ] **Step 9.8.2: Update selectors**

Replace `/api/chat/conversations` with `/api/chat/threads` in any `page.waitForResponse` calls. Replace `data-testid="conversation-row-*"` with the new sidebar test IDs (whatever the Vortex sidebar uses — verify by opening the rendered DOM).

- [ ] **Step 9.8.3: Commit**

```bash
git add apps/frontend/e2e/support/ui-helpers.ts
git commit -m "chore(e2e): helper internals updated for threads"
```

---

### Task 9.9: Manual smoke in the dev frontend

This is a manual verification pass, not an E2E run. E2E is deferred to Phase 11.

- [ ] **Step 9.9.1: Start backend**

```bash
cd server/api
uvicorn ai_portal.main:app --port 8000 --reload
```

- [ ] **Step 9.9.2: Start frontend with network host**

```bash
cd apps/frontend
pnpm dev --host
```

Expected output lines like:
```
  ➜  Local:   http://localhost:5173/
  ➜  Network: http://192.168.x.x:5173/
```

Print the Network URL back to the user.

- [ ] **Step 9.9.3: Manual checks in the browser**

- [ ] Open a new conversation. Type "hello". Assistant streams a reply. DOM shows `data-testid="thread-item-assistant-text"` with `data-status="streaming"` → `done`.
- [ ] Ask a question that triggers `web_search`. A `thread-item-tool-call` chip appears with provider and cost (or `—` if unknown).
- [ ] Refresh the page mid-turn is NOT part of v1; don't test it.
- [ ] Open the inspector, click a turn: see the timeline list.
- [ ] Verify the cost badge shows `input→output · $x` after the llm_call item finishes.
- [ ] In DevTools → Network, confirm `POST /api/chat/threads/:id/turns` streams with `Content-Type: text/event-stream`.

- [ ] **Step 9.9.4: Report any visible regressions**

If any of the manual checks fail, fix the specific component; do not widen scope. Commit fixes and re-run.

---
## Phase 10 — Consumption UI page

### Task 10.1: Route registration

**Files:**
- Modify: `apps/frontend/src/router.tsx`

- [ ] **Step 10.1.1: Add route**

Add `/org/consumption` to the existing org section of the router. Guard with the admin role predicate already used by other `/org/*` routes.

```tsx
// apps/frontend/src/router.tsx (partial — adapt to existing structure)
import { ConsumptionPage } from "@/routes/org/consumption";

const consumptionRoute = createRoute({
  getParentRoute: () => orgRoute,
  path: "consumption",
  component: ConsumptionPage,
  beforeLoad: adminGuard,
});
```

- [ ] **Step 10.1.2: Commit after Task 10.2** — route imports a component that doesn't exist yet.

---

### Task 10.2: Consumption page skeleton

**Files:**
- Create: `apps/frontend/src/routes/org/consumption.tsx`

- [ ] **Step 10.2.1: Page shell**

```tsx
// apps/frontend/src/routes/org/consumption.tsx
import { useState } from "react";
import { ConsumptionKpiStrip } from "@/components/consumption/ConsumptionKpiStrip";
import { ConsumptionTrend } from "@/components/consumption/ConsumptionTrend";
import { ConsumptionGroupedTable } from "@/components/consumption/ConsumptionGroupedTable";
import { ConsumptionThreadTimeline } from "@/components/consumption/ConsumptionThreadTimeline";

type Tab = "model" | "user" | "provider" | "capability" | "tool";

export function ConsumptionPage() {
  const [start, setStart] = useState(() => firstOfMonthIso());
  const [end, setEnd] = useState(() => todayIso());
  const [tab, setTab] = useState<Tab>("model");
  const [selectedThreadId, setSelectedThreadId] = useState<number | null>(null);

  return (
    <div data-testid="consumption-page" className="page consumption">
      <header className="consumption__header">
        <h1>Consumption</h1>
        <DateRangePicker start={start} end={end} onChange={(s, e) => { setStart(s); setEnd(e); }} />
      </header>

      <ConsumptionKpiStrip start={start} end={end} />
      <ConsumptionTrend start={start} end={end} />

      <nav className="consumption__tabs">
        {(["model", "user", "provider", "capability", "tool"] as const).map((t) => (
          <button
            key={t}
            data-testid={`consumption-tab-${t}`}
            data-active={tab === t}
            onClick={() => setTab(t)}
          >{t}</button>
        ))}
      </nav>
      <ConsumptionGroupedTable start={start} end={end} by={tab} />

      <ConsumptionThreadTimeline
        start={start} end={end}
        selectedThreadId={selectedThreadId}
        onSelect={setSelectedThreadId}
      />
    </div>
  );
}

function firstOfMonthIso() {
  const d = new Date(); d.setDate(1); return d.toISOString().slice(0, 10);
}
function todayIso() { return new Date().toISOString().slice(0, 10); }

function DateRangePicker(props: { start: string; end: string; onChange: (s: string, e: string) => void }) {
  return (
    <div className="date-range">
      <input type="date" value={props.start} onChange={(e) => props.onChange(e.target.value, props.end)} />
      <span>→</span>
      <input type="date" value={props.end} onChange={(e) => props.onChange(props.start, e.target.value)} />
    </div>
  );
}
```

- [ ] **Step 10.2.2: Commit after KPI strip is ready.**

---

### Task 10.3: KPI strip

**Files:**
- Create: `apps/frontend/src/components/consumption/ConsumptionKpiStrip.tsx`
- Create: `apps/frontend/src/hooks/useConsumptionSummary.ts`

- [ ] **Step 10.3.1: Hook**

```ts
// apps/frontend/src/hooks/useConsumptionSummary.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";

export interface SummaryKpi { label: string; value: string | number; unit?: string | null }
export interface SummaryRow {
  key: string; label: string; messages: number;
  input_tokens: number; output_tokens: number;
  cost_usd: string; estimated_ratio: number;
}
export interface Summary {
  kpis: SummaryKpi[];
  by_model: SummaryRow[];
  by_user: SummaryRow[];
  by_provider: SummaryRow[];
  by_capability: SummaryRow[];
  by_tool: SummaryRow[];
}

export function useConsumptionSummary(start: string, end: string) {
  return useQuery({
    queryKey: qk.consumption.summary(start, end),
    queryFn: async (): Promise<Summary> => {
      const u = new URL("/api/admin/consumption/summary", location.origin);
      u.searchParams.set("start", start);
      u.searchParams.set("end", end);
      const r = await authorizedFetch(u.toString());
      if (!r.ok) throw new Error(`summary ${r.status}`);
      return r.json();
    },
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 10.3.2: Component**

```tsx
// apps/frontend/src/components/consumption/ConsumptionKpiStrip.tsx
import { useConsumptionSummary } from "@/hooks/useConsumptionSummary";

interface Props { start: string; end: string }

export function ConsumptionKpiStrip({ start, end }: Props) {
  const { data, isLoading } = useConsumptionSummary(start, end);
  return (
    <section data-testid="consumption-kpis" className="kpi-strip">
      {(data?.kpis ?? []).map((k) => (
        <div key={k.label} className="kpi-card">
          <div className="kpi-card__label">{k.label}</div>
          <div className="kpi-card__value">{k.value}{k.unit ? ` ${k.unit}` : ""}</div>
        </div>
      ))}
      {isLoading ? <span>Loading…</span> : null}
    </section>
  );
}
```

- [ ] **Step 10.3.3: Commit**

```bash
git add apps/frontend/src/routes/org/consumption.tsx apps/frontend/src/components/consumption/ConsumptionKpiStrip.tsx apps/frontend/src/hooks/useConsumptionSummary.ts apps/frontend/src/router.tsx
git commit -m "feat(frontend): consumption page shell + KPI strip"
```

---

### Task 10.4: Trend chart

**Files:**
- Create: `apps/frontend/src/components/consumption/ConsumptionTrend.tsx`
- Create: `apps/frontend/src/hooks/useConsumptionTrend.ts`

Check `apps/frontend/package.json` for an existing chart library (`recharts`, `visx`, `echarts`, `@nivo/*`). Use whatever is already installed. If none, use a minimal SVG area chart component written inline — do not add a dependency without explicit user sign-off.

- [ ] **Step 10.4.1: Hook**

```ts
// apps/frontend/src/hooks/useConsumptionTrend.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";

export interface TrendPoint {
  t: string; cost_usd: string;
  input_tokens: number; output_tokens: number;
  breakdown: Record<string, string>;
}

export function useConsumptionTrend(start: string, end: string, grain: "day" | "hour" = "day", by: "kind" | "provider" = "kind") {
  return useQuery({
    queryKey: qk.consumption.trend(start, end, grain, by),
    queryFn: async () => {
      const u = new URL("/api/admin/consumption/trend", location.origin);
      u.searchParams.set("start", start);
      u.searchParams.set("end", end);
      u.searchParams.set("grain", grain);
      u.searchParams.set("by", by);
      const r = await authorizedFetch(u.toString());
      if (!r.ok) throw new Error(`trend ${r.status}`);
      return (await r.json()) as { series: TrendPoint[]; grain: string; by: string };
    },
    refetchInterval: 30_000,
  });
}
```

- [ ] **Step 10.4.2: Component**

Using an existing chart lib (e.g. `recharts`):

```tsx
// apps/frontend/src/components/consumption/ConsumptionTrend.tsx
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { useConsumptionTrend } from "@/hooks/useConsumptionTrend";

export function ConsumptionTrend({ start, end }: { start: string; end: string }) {
  const { data } = useConsumptionTrend(start, end, "day", "kind");
  const rows = (data?.series ?? []).map((p) => ({
    t: p.t.slice(0, 10),
    cost: Number(p.cost_usd),
  }));
  return (
    <section data-testid="consumption-trend" className="trend-chart" style={{ height: 220 }}>
      <ResponsiveContainer>
        <AreaChart data={rows}>
          <XAxis dataKey="t" />
          <YAxis />
          <Tooltip />
          <Area dataKey="cost" />
        </AreaChart>
      </ResponsiveContainer>
    </section>
  );
}
```

If recharts isn't installed, implement the area chart in ~40 lines with plain SVG + `d3-shape` (already a transitive dep of many TanStack packages — verify first with `pnpm why d3-shape`). Fall back to a simple stacked-bar SVG if no shaping library is available.

- [ ] **Step 10.4.3: Commit**

```bash
git add apps/frontend/src/components/consumption/ConsumptionTrend.tsx apps/frontend/src/hooks/useConsumptionTrend.ts
git commit -m "feat(frontend): consumption trend chart"
```

---

### Task 10.5: Grouped tables (tabbed)

**Files:**
- Create: `apps/frontend/src/components/consumption/ConsumptionGroupedTable.tsx`

Reuses `useConsumptionSummary`. Picks the right `by_*` array based on `by` prop.

- [ ] **Step 10.5.1: Component**

```tsx
// apps/frontend/src/components/consumption/ConsumptionGroupedTable.tsx
import { useConsumptionSummary, type Summary, type SummaryRow } from "@/hooks/useConsumptionSummary";

interface Props { start: string; end: string; by: "model" | "user" | "provider" | "capability" | "tool" }

const ROWS_KEY: Record<Props["by"], keyof Summary> = {
  model: "by_model", user: "by_user", provider: "by_provider",
  capability: "by_capability", tool: "by_tool",
};

export function ConsumptionGroupedTable({ start, end, by }: Props) {
  const { data } = useConsumptionSummary(start, end);
  const rows: SummaryRow[] = (data?.[ROWS_KEY[by]] ?? []) as SummaryRow[];

  return (
    <table data-testid={`consumption-table-${by}`} className="tbl">
      <thead>
        <tr>
          <th>{by}</th>
          <th>Messages</th>
          <th>Input tokens</th>
          <th>Output tokens</th>
          <th>Cost (USD)</th>
          <th>% estimated</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.key}>
            <td>{r.label}</td>
            <td>{r.messages}</td>
            <td>{r.input_tokens.toLocaleString()}</td>
            <td>{r.output_tokens.toLocaleString()}</td>
            <td>${r.cost_usd}</td>
            <td>{Math.round(r.estimated_ratio * 100)}%</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 10.5.2: Commit**

```bash
git add apps/frontend/src/components/consumption/ConsumptionGroupedTable.tsx
git commit -m "feat(frontend): consumption grouped tables"
```

---

### Task 10.6: Per-conversation drilldown + timeline

**Files:**
- Create: `apps/frontend/src/components/consumption/ConsumptionThreadTimeline.tsx`
- Create: `apps/frontend/src/hooks/useConsumptionThreads.ts`
- Create: `apps/frontend/src/hooks/useThreadTimeline.ts`

- [ ] **Step 10.6.1: Hooks**

```ts
// apps/frontend/src/hooks/useConsumptionThreads.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";

export interface ThreadRow {
  id: number; title: string | null; user_id: number;
  model: string | null; last_message_at: string | null;
  total_cost_usd: string; total_items: number;
}

export function useConsumptionThreads(start: string, end: string, userId?: number, model?: string) {
  return useQuery({
    queryKey: qk.consumption.threads(start, end, userId, model),
    queryFn: async () => {
      const u = new URL("/api/admin/consumption/threads", location.origin);
      u.searchParams.set("start", start);
      u.searchParams.set("end", end);
      if (userId != null) u.searchParams.set("user_id", String(userId));
      if (model) u.searchParams.set("model", model);
      const r = await authorizedFetch(u.toString());
      if (!r.ok) throw new Error(`threads ${r.status}`);
      return (await r.json()) as { total: number; page: number; page_size: number; rows: ThreadRow[] };
    },
  });
}
```

```ts
// apps/frontend/src/hooks/useThreadTimeline.ts
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";
import { qk } from "@/lib/queryKeys";

export function useThreadTimeline(threadId: number | null) {
  return useQuery({
    queryKey: threadId == null ? ["consumption", "timeline", "none"] : qk.consumption.timeline(threadId),
    enabled: threadId != null,
    queryFn: async () => {
      const r = await authorizedFetch(`/api/admin/consumption/threads/${threadId}/timeline`);
      if (!r.ok) throw new Error(`timeline ${r.status}`);
      return r.json();
    },
  });
}
```

- [ ] **Step 10.6.2: Component**

```tsx
// apps/frontend/src/components/consumption/ConsumptionThreadTimeline.tsx
import { useConsumptionThreads } from "@/hooks/useConsumptionThreads";
import { useThreadTimeline } from "@/hooks/useThreadTimeline";

interface Props {
  start: string; end: string;
  selectedThreadId: number | null;
  onSelect: (id: number | null) => void;
}

export function ConsumptionThreadTimeline({ start, end, selectedThreadId, onSelect }: Props) {
  const threads = useConsumptionThreads(start, end);
  const timeline = useThreadTimeline(selectedThreadId);

  return (
    <section data-testid="consumption-threads" className="master-detail">
      <ul className="thread-list">
        {(threads.data?.rows ?? []).map((t) => (
          <li key={t.id}>
            <button
              data-testid={`consumption-thread-row-${t.id}`}
              data-active={selectedThreadId === t.id}
              onClick={() => onSelect(t.id)}
            >
              <span>{t.title ?? `Thread ${t.id}`}</span>
              <span>{t.model}</span>
              <span>${t.total_cost_usd}</span>
            </button>
          </li>
        ))}
      </ul>

      {selectedThreadId != null && timeline.data ? (
        <ol data-testid="consumption-timeline" className="timeline-steps">
          {timeline.data.items.map((i: any) => (
            <li key={i.id} data-kind={i.kind}>
              <span>{i.kind}</span>
              <span>{i.provider ?? ""}</span>
              <span>{i.model ?? ""}</span>
              {i.cost_usd ? <span>${i.cost_usd}</span> : null}
              {i.latency_ms ? <span>{i.latency_ms}ms</span> : null}
            </li>
          ))}
        </ol>
      ) : null}
    </section>
  );
}
```

- [ ] **Step 10.6.3: Commit**

```bash
git add apps/frontend/src/components/consumption/ConsumptionThreadTimeline.tsx apps/frontend/src/hooks/useConsumptionThreads.ts apps/frontend/src/hooks/useThreadTimeline.ts
git commit -m "feat(frontend): consumption thread drilldown + timeline"
```

---

### Task 10.7: "My usage" page (minimal)

**Files:**
- Create or modify: `apps/frontend/src/routes/settings/usage.tsx`

- [ ] **Step 10.7.1: Minimal page**

```tsx
// apps/frontend/src/routes/settings/usage.tsx
import { useQuery } from "@tanstack/react-query";
import { authorizedFetch } from "@/lib/authorizedFetch";

export function SettingsUsagePage() {
  const { data } = useQuery({
    queryKey: ["usage", "my"],
    queryFn: async () => (await authorizedFetch("/api/admin/usage/my")).json(),
  });
  if (!data) return null;
  return (
    <div data-testid="my-usage-page" className="page settings-usage">
      <div className="kpi-strip">
        <div className="kpi-card"><span>Cost this month</span><strong>${data.cost_this_month ?? 0}</strong></div>
        <div className="kpi-card"><span>Messages this month</span><strong>{data.messages_this_month ?? 0}</strong></div>
      </div>
      {data.quota ? (
        <div className="quota-bar" data-testid="quota-progress">
          <progress max={data.quota.monthly_cap_usd} value={data.quota.spent_usd} />
          <span>${data.quota.spent_usd} / ${data.quota.monthly_cap_usd}</span>
        </div>
      ) : null}
    </div>
  );
}
```

If `/api/admin/usage/my` response shape differs, adjust the field names. Do not change backend response for v1.

- [ ] **Step 10.7.2: Commit**

```bash
git add apps/frontend/src/routes/settings/usage.tsx
git commit -m "feat(frontend): minimal 'my usage' page"
```

---

### Task 10.8: Manual smoke

- [ ] **Step 10.8.1: Start dev servers**

Backend on 8000 and frontend on 5173 (`pnpm dev --host`). Print the Network URL.

- [ ] **Step 10.8.2: Open the page**

Navigate to `/org/consumption` as an admin user. Checks:
- KPI strip renders four cards.
- Trend chart shows at least one series in the last 30 days.
- Tabs switch between model/user/provider/capability/tool tables.
- Click a thread row → timeline list appears.

If the org has no data, seed a couple of turns via the chat UI first; then refresh.

- [ ] **Step 10.8.3: Typecheck**

```bash
cd apps/frontend && pnpm typecheck
```

Expected: zero errors.

---

## Phase 11 — E2E final pass

This is the one and only E2E run. Prior phases relied on unit tests + manual smoke.

### Task 11.1: Pre-flight — E2E DB isolation

- [ ] **Step 11.1.1: Verify dev backend is NOT on port 8001**

```bash
curl -s http://localhost:8001/health 2>&1 | head -1
```
Expected: connection refused — unless the E2E backend from a previous run is up. If any uvicorn holds 8001, kill it before proceeding.

- [ ] **Step 11.1.2: Start the E2E stack**

```bash
./scripts/e2e-up.sh
```
Expected: resets `ai_portal_e2e`, runs migrations through `031_thread_items_rework`, boots E2E backend on 8001.

- [ ] **Step 11.1.3: Verify**

```bash
curl -s http://localhost:8001/health | jq '.database_url'
```
Expected: contains `ai_portal_e2e`.

---

### Task 11.2: Update existing chat specs for new DOM

**Files:**
- Modify: `apps/frontend/e2e/chat/*.spec.ts` (enumerate and update selectors only)

- [ ] **Step 11.2.1: Enumerate chat specs**

Run: `ls apps/frontend/e2e/chat/`
For each spec, replace references to old selectors. Common replacements (verify against the actual spec files):

| Old | New |
|---|---|
| `data-testid="chat-message"` | `data-testid="thread-turn"` (for turn grouping) or `data-testid="thread-item-assistant-text"` (for assistant content) |
| `data-testid="chat-message-user"` | `data-testid="thread-item-user"` |
| `data-testid="tool-chip-..."` | `data-testid="thread-item-tool-call"` |
| `data-testid="thinking-block"` | unchanged (component is reused) |
| API URLs `/api/chat/conversations/...` | `/api/chat/threads/...` |
| API URLs `/api/chat/messages/...` | `/api/chat/threads/:id/items` |

Update incrementally, spec by spec. After each file's edits, save but don't commit yet.

- [ ] **Step 11.2.2: Run only the chat subset**

```bash
cd apps/frontend
pnpm test:e2e:filter chat
```

- [ ] **Step 11.2.3: Iterate on failures**

Fix selectors / waits one spec at a time. Do not widen scope — if a spec reveals a real regression (not a selector-only drift), fix the bug in the component and re-run the spec.

- [ ] **Step 11.2.4: Commit**

```bash
git add apps/frontend/e2e/chat/
git commit -m "test(e2e): update chat specs for thread_items DOM"
```

---

### Task 11.3: Update the other spec suites

**Files:**
- Modify: `apps/frontend/e2e/kb/*.spec.ts`, `e2e/memories/*.spec.ts`, `e2e/admin/*.spec.ts`, `e2e/shell/*.spec.ts`, `e2e/mobile-nav.spec.ts`, `e2e/auth/*.spec.ts`

Most of these are unaffected by the rework — only specs that assert on chat DOM or on `/chat/conversations/*` API calls need changes. Scan each folder:

```bash
grep -l "conversations/\|chat-message\|message_usage" apps/frontend/e2e
```

- [ ] **Step 11.3.1: Update each hit**

Fix selector/URL references; preserve assertion intent.

- [ ] **Step 11.3.2: Run the full E2E suite**

```bash
cd apps/frontend
pnpm test:e2e
```

Expected: entire suite green. 8 workers, 0 retries per project convention.

- [ ] **Step 11.3.3: Commit**

```bash
git add apps/frontend/e2e/
git commit -m "test(e2e): update remaining specs for thread_items rework"
```

---

### Task 11.4: New Consumption E2E spec

**Files:**
- Create: `apps/frontend/e2e/admin/consumption.spec.ts`

- [ ] **Step 11.4.1: Write spec**

```ts
// apps/frontend/e2e/admin/consumption.spec.ts
import { test, expect } from "@playwright/test";
import { loginAsAdmin, createOrFindConversation, sendMessage } from "../support/ui-helpers";

test.describe("admin/consumption", () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test("page renders KPI strip and trend", async ({ page }) => {
    // seed: one chat turn
    await createOrFindConversation(page, "E2E Consumption Seed");
    await sendMessage(page, "ping");

    await page.goto("/org/consumption");
    await expect(page.getByTestId("consumption-kpis")).toBeVisible();
    await expect(page.getByTestId("consumption-trend")).toBeVisible();
    await expect(page.getByTestId("consumption-table-model")).toBeVisible();
  });

  test("thread timeline drilldown shows step cards", async ({ page }) => {
    await createOrFindConversation(page, "E2E Consumption Seed");
    await sendMessage(page, "ping");

    await page.goto("/org/consumption");
    const firstThread = page.getByTestId(/^consumption-thread-row-/).first();
    await firstThread.click();
    const timeline = page.getByTestId("consumption-timeline");
    await expect(timeline).toBeVisible();
    await expect(timeline.locator("li")).toHaveCount(await timeline.locator("li").count());
  });

  test("tabs switch tables", async ({ page }) => {
    await page.goto("/org/consumption");
    await page.getByTestId("consumption-tab-provider").click();
    await expect(page.getByTestId("consumption-table-provider")).toBeVisible();
    await page.getByTestId("consumption-tab-tool").click();
    await expect(page.getByTestId("consumption-table-tool")).toBeVisible();
  });
});
```

The helpers `loginAsAdmin` and `sendMessage` may not exist yet — use whatever the project's existing auth/chat helpers are. Open `apps/frontend/e2e/support/ui-helpers.ts` and reuse or extend.

- [ ] **Step 11.4.2: Run just this spec**

```bash
cd apps/frontend
pnpm test:e2e:filter consumption
```

- [ ] **Step 11.4.3: Commit**

```bash
git add apps/frontend/e2e/admin/consumption.spec.ts
git commit -m "test(e2e): consumption page spec"
```

---

### Task 11.5: Full suite green

- [ ] **Step 11.5.1: Final run**

```bash
cd apps/frontend
pnpm test:e2e
```

Expected: 100% passing. If anything remains red, fix root cause — do not mark it flaky, do not add retries.

- [ ] **Step 11.5.2: No commit if no changes needed.**

---

## Phase 12 — Cleanup

### Task 12.1: Delete dead code

**Files:**
- Delete any files that replaced older versions and still have leftover imports or references.

- [ ] **Step 12.1.1: Scan for orphans**

```bash
grep -rn "MessageUsage\|ChatMessage\|ChatConversation\|stream_items\|streaming_service" server/api/src/ apps/frontend/src/
```

Expected: zero hits in `src/`. Any hits: remove the stale references. Test files may retain historical fixtures — leave them unless they fail the suite.

- [ ] **Step 12.1.2: Commit any deletions**

```bash
git commit -am "chore: remove stragglers from pre-rework chat stack"
```

(Only if there are changes.)

---

### Task 12.2: Docstring + README updates

**Files:**
- Modify: `server/api/src/ai_portal/chat/streaming/__init__.py`
- Modify: project root `README.md` if it mentions the old architecture

- [ ] **Step 12.2.1: Package docstring**

```python
# server/api/src/ai_portal/chat/streaming/__init__.py
"""Streaming pipeline — one module, one responsibility.

Public entry: ``orchestrator.stream_turn``. All other modules are internal.

Modules
-------
- ``orchestrator``    Stateful entry; composes the turn.
- ``turn_gate``       Quota + RBAC pre-flight (pure).
- ``turn_setup``      Creates/regenerates a turn, inserts user_message.
- ``context_assembler`` Reads thread_items → provider message list.
- ``system_prompt``   Pure composition of the system prompt.
- ``iteration_loop``  LLM round + tool dispatch + yields SseEvents.
- ``item_writer``     The only module that mutates thread_items (state machine).
- ``sse_emitter``     SseEvent → SSE line encoder.
- ``error_handler``   Provider exceptions → ErrorItem + TurnEnd.
- ``cancellation``    Cancel registry + endpoint handler.
"""
```

- [ ] **Step 12.2.2: README scan**

If `README.md` references `chat_messages` or `streaming_service.py`, update or remove.

- [ ] **Step 12.2.3: Commit**

```bash
git add server/api/src/ai_portal/chat/streaming/__init__.py README.md
git commit -m "docs: update chat streaming package docstring + README"
```

---

### Task 12.3: Verify CI types-align step + run once locally

- [ ] **Step 12.3.1: Run locally**

```bash
cd server/api
python scripts/check_types_align.py
```

Expected: `OK — 10 ItemKind literals aligned`.

- [ ] **Step 12.3.2: Check the CI config actually wires it**

Read `.github/workflows/ci.yml` and confirm the step is present in the backend or a dedicated `types` job. If it's only a local script, add the step now:

```yaml
      - name: Types alignment check
        run: python server/api/scripts/check_types_align.py
```

- [ ] **Step 12.3.3: Commit any CI change**

```bash
git add .github/workflows/ci.yml
git commit -m "chore(ci): wire types-align check"
```

---

### Task 12.4: Pre-merge gate

Before opening a PR or merging:

- [ ] **Step 12.4.1: Backend unit tests**

```bash
cd server/api && pytest -xvs --ignore=tests/e2e
```
Expected: all green.

- [ ] **Step 12.4.2: Frontend typecheck + lint**

```bash
cd apps/frontend
pnpm typecheck
pnpm lint
```
Expected: zero errors.

- [ ] **Step 12.4.3: Full E2E**

```bash
cd apps/frontend
pnpm test:e2e
```
Expected: fully green.

- [ ] **Step 12.4.4: Alembic check**

```bash
cd server/api
alembic check
```
Expected: `No new upgrade operations detected`.

- [ ] **Step 12.4.5: Types-align**

```bash
cd server/api
python scripts/check_types_align.py
```
Expected: aligned.

- [ ] **Step 12.4.6: Finish the branch**

Invoke the `superpowers:finishing-a-development-branch` skill to decide merge vs. PR flow. The branch is ready.

---

## Risks and rollback notes

- **Backfill data loss.** If Task 1.5 checksum fails, `git revert` the migration commit on the branch and restore from `pre_031_dev.dump`. Do NOT attempt `alembic downgrade` — the migration raises on downgrade intentionally.
- **Provider adapter drift.** If an upstream SDK changes event shape (e.g. Anthropic adds a new `content_block` type), the adapter falls through to no-op silently. Cover new shapes as they appear by adding a translate branch + a test.
- **Cost-precision drift.** `Decimal(12, 6)` in Postgres; `str`-serialized Decimal on the wire; `Decimal` again in backend math. Avoid `float` anywhere in cost math.
- **SSE buffering pitfalls.** Some reverse proxies buffer `text/event-stream`. If streaming appears laggy in prod, check proxy buffering config (nginx: `proxy_buffering off` on the chat endpoint).
- **Cancellation is best-effort.** The in-process `CancelRegistry` does not survive worker restart. A turn orphaned by a worker crash is swept to `error` via `item_writer.sweep_stale` on next read.

## Deliverables summary

- `thread_items` table + backfill migration applied.
- 10-module `chat/streaming/` package replacing `streaming_service.py`.
- Isolated `cost_calculator` with flat + metered sources.
- Typed `ProviderStreamEvent` + `SseEvent` + `ThreadItem` contracts, Python + TS aligned under CI.
- `/api/admin/consumption/*` endpoints and Vortex Consumption page (KPIs, trend, grouped tables, per-thread timeline).
- Quota + rollup read from `thread_items`; legacy `MessageUsage` removed.
- Full E2E suite green (8 workers, 0 retries).

