# server/api/tests/chat/test_backfill.py
"""Unit tests for the thread_items backfill.

The backfill runs *after* `chat_conversations` has been renamed to `threads`
(step 1 of migration 031).  These tests simulate that post-rename state using
direct psycopg connections with autocommit=True for DDL, then clean up in the
module teardown.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import psycopg
import pytest
from sqlalchemy import text

from ai_portal.chat._backfill import run_backfill

# Fixed IDs so teardown is reliable across reruns.
_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000bf1")
_THREAD_ID = 88881
_USER_ID = 88881
_MSG_USER_ID = 88881
_MSG_ASST_ID = 88880
_USAGE_ID = 88881


def _pg_dsn(sync_engine) -> str:
    """Extract a psycopg-compatible DSN from the SQLAlchemy engine."""
    url = sync_engine.url
    return (
        f"postgresql://{url.username}:{url.password}"
        f"@{url.host}:{url.port}/{url.database}"
    )


@pytest.fixture(scope="module")
def backfill_setup(sync_engine):
    """Module-scoped fixture: set up pre-backfill DB state, run backfill, yield, teardown."""
    dsn = _pg_dsn(sync_engine)

    # Use a direct psycopg connection with autocommit for DDL.
    ddl_conn = psycopg.connect(dsn, autocommit=True)
    try:
        # 1. Simulate migration 031 step 1: rename conversations → threads.
        #    PK index is chat_sessions_pkey (from migration 007, before rename to chat_conversations).
        ddl_conn.execute("ALTER TABLE chat_conversations RENAME TO threads")
        ddl_conn.execute("ALTER INDEX chat_sessions_pkey RENAME TO threads_pkey")

        # 2. Create enums (migration step 3).
        ddl_conn.execute(
            "CREATE TYPE thread_item_kind AS ENUM ("
            "'user_message','assistant_text','llm_call','tool_call',"
            "'server_tool_use','thinking','citation','memory_pill','turn_end','error')"
        )
        ddl_conn.execute(
            "CREATE TYPE thread_item_status AS ENUM ('streaming','done','error','cancelled')"
        )
        ddl_conn.execute(
            "CREATE TYPE thread_item_role AS ENUM ('user','assistant','system')"
        )

        # 3. Create thread_items table (migration step 4).
        ddl_conn.execute(
            "CREATE TABLE thread_items ("
            "  id bigserial PRIMARY KEY,"
            "  thread_id bigint NOT NULL REFERENCES threads(id) ON DELETE CASCADE,"
            "  org_id uuid NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,"
            "  turn_id uuid NOT NULL,"
            "  kind thread_item_kind NOT NULL,"
            "  role thread_item_role,"
            "  status thread_item_status NOT NULL,"
            "  provider varchar(64),"
            "  model varchar(128),"
            "  cost_usd numeric(12,6),"
            "  cost_estimated boolean NOT NULL DEFAULT false,"
            "  latency_ms integer,"
            "  data jsonb NOT NULL DEFAULT '{}'::jsonb,"
            "  parent_item_id bigint REFERENCES thread_items(id) ON DELETE SET NULL,"
            "  started_at timestamptz,"
            "  finished_at timestamptz,"
            "  created_at timestamptz NOT NULL DEFAULT clock_timestamp(),"
            "  CONSTRAINT ck_thread_items_llm_call_shape CHECK ("
            "    (kind <> 'llm_call') OR (model IS NOT NULL AND data ? 'input_tokens' AND data ? 'output_tokens')"
            "  ),"
            "  CONSTRAINT ck_thread_items_tool_call_shape CHECK ("
            "    (kind <> 'tool_call') OR (data ? 'tool_name')"
            "  ),"
            "  CONSTRAINT ck_thread_items_user_message_shape CHECK ("
            "    (kind <> 'user_message') OR (data ? 'text')"
            "  )"
            ")"
        )

        # 4. Insert test data via SQLAlchemy (DML — no autocommit needed).
        with sync_engine.begin() as conn:
            conn.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:o, 'bf-test-org', 'test')"),
                {"o": str(_ORG_ID)},
            )
            conn.execute(
                text("INSERT INTO users (id, email, uuid, org_id) VALUES (:uid, 'bf@e', gen_random_uuid(), :o)"),
                {"uid": _USER_ID, "o": str(_ORG_ID)},
            )
            conn.execute(
                text(
                    "INSERT INTO threads (id, org_id, user_id, title, model) "
                    "VALUES (:tid, :o, :uid, 'T', 'gpt-4')"
                ),
                {"tid": _THREAD_ID, "o": str(_ORG_ID), "uid": _USER_ID},
            )
            conn.execute(
                text(
                    "INSERT INTO chat_messages (id, conversation_id, role, content, created_at) "
                    "VALUES (:id, :tid, 'user', 'hi', :t)"
                ),
                {"id": _MSG_USER_ID, "tid": _THREAD_ID, "t": datetime(2026, 1, 1, tzinfo=timezone.utc)},
            )
            conn.execute(
                text(
                    "INSERT INTO message_usage (id, org_id, api_model_id, input_tokens, output_tokens, cost_usd) "
                    "VALUES (:id, :o, 'gpt-4', 10, 20, 0.001)"
                ),
                {"id": _USAGE_ID, "o": str(_ORG_ID)},
            )
            conn.execute(
                text(
                    "INSERT INTO chat_messages (id, conversation_id, role, content, extra, usage_id, model_id, created_at) "
                    "VALUES (:id, :tid, 'assistant', 'hello', cast(:ex as jsonb), :uid, 'gpt-4', :t)"
                ),
                {
                    "id": _MSG_ASST_ID,
                    "tid": _THREAD_ID,
                    "ex": json.dumps(
                        {"stream_items": [{"kind": "web_search", "provider": "tavily", "params": {"q": "x"}}]}
                    ),
                    "uid": _USAGE_ID,
                    "t": datetime(2026, 1, 1, 0, 0, 1, tzinfo=timezone.utc),
                },
            )

        # 5. Run the backfill.
        with sync_engine.connect() as sa_conn:
            run_backfill(sa_conn)
            sa_conn.commit()

        yield  # tests run here

    finally:
        # Teardown: remove test data and undo DDL.
        try:
            with sync_engine.begin() as conn:
                conn.execute(text("DELETE FROM thread_items WHERE thread_id = :tid"), {"tid": _THREAD_ID})
                conn.execute(text("DELETE FROM chat_messages WHERE conversation_id = :tid"), {"tid": _THREAD_ID})
                conn.execute(text("DELETE FROM message_usage WHERE id = :id"), {"id": _USAGE_ID})
                conn.execute(text("DELETE FROM threads WHERE id = :tid"), {"tid": _THREAD_ID})
                conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": _USER_ID})
                conn.execute(text("DELETE FROM orgs WHERE id = :o"), {"o": str(_ORG_ID)})
        except Exception:
            pass
        try:
            ddl_conn.execute("DROP TABLE IF EXISTS thread_items CASCADE")
        except Exception:
            pass
        try:
            ddl_conn.execute("DROP TYPE IF EXISTS thread_item_kind")
            ddl_conn.execute("DROP TYPE IF EXISTS thread_item_status")
            ddl_conn.execute("DROP TYPE IF EXISTS thread_item_role")
        except Exception:
            pass
        try:
            ddl_conn.execute("ALTER INDEX IF EXISTS threads_pkey RENAME TO chat_sessions_pkey")
            ddl_conn.execute("ALTER TABLE IF EXISTS threads RENAME TO chat_conversations")
        except Exception:
            pass
        ddl_conn.close()


def test_backfill_derives_user_and_assistant_items(sync_engine, backfill_setup):
    with sync_engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT kind, role, status, cost_usd, cost_estimated, model "
            "FROM thread_items WHERE thread_id = :tid ORDER BY created_at"
        ), {"tid": _THREAD_ID}).all()

    kinds = [r.kind for r in rows]
    assert kinds[0] == "user_message", f"expected user_message first, got {kinds}"
    assert "tool_call" in kinds, f"tool_call missing from {kinds}"
    assert "assistant_text" in kinds, f"assistant_text missing from {kinds}"
    assert "llm_call" in kinds, f"llm_call missing from {kinds}"
    assert kinds[-1] == "turn_end", f"expected turn_end last, got {kinds}"

    llm_row = next(r for r in rows if r.kind == "llm_call")
    assert llm_row.cost_usd == Decimal("0.001000"), f"unexpected cost_usd: {llm_row.cost_usd}"
    assert llm_row.cost_estimated is False
    assert llm_row.model == "gpt-4"


def test_backfill_preserves_turn_id_across_user_and_assistant(sync_engine, backfill_setup):
    with sync_engine.connect() as conn:
        turn_ids = conn.execute(text(
            "SELECT DISTINCT turn_id FROM thread_items WHERE thread_id = :tid"
        ), {"tid": _THREAD_ID}).scalars().all()
    assert len(turn_ids) == 1, f"expected 1 turn_id, got {len(turn_ids)}: {turn_ids}"
