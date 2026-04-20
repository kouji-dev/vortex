# server/api/src/ai_portal/chat/_backfill.py
from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

_LOG = logging.getLogger(__name__)

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
    threads = conn.execute(text("SELECT id, org_id FROM threads WHERE org_id IS NOT NULL")).all()
    for t in threads:
        _backfill_thread(conn, t.id, t.org_id)


def _backfill_thread(conn: Connection, thread_id: int, org_id: Any) -> None:
    rows = conn.execute(text(
        "SELECT m.id, m.role, m.content, m.extra, m.model_id, m.created_at, "
        "       u.input_tokens, u.output_tokens, u.cost_usd "
        "FROM chat_messages m "
        "LEFT JOIN message_usage u ON u.id = m.usage_id "
        "WHERE m.conversation_id = :tid ORDER BY m.created_at, m.id"
    ), {"tid": thread_id}).all()

    current_turn: uuid.UUID | None = None
    for msg in rows:
        if msg.role == "user":
            current_turn = uuid.uuid4()
            _insert_user_message(conn, thread_id, org_id, current_turn, msg)
        elif msg.role == "assistant":
            if current_turn is None:
                current_turn = uuid.uuid4()
            _insert_assistant_items(conn, thread_id, org_id, current_turn, msg)
            current_turn = None


def _insert_user_message(
    conn: Connection, thread_id: int, org_id: Any, turn: uuid.UUID, msg: Any
) -> None:
    conn.execute(text(
        "INSERT INTO thread_items "
        "(thread_id, org_id, turn_id, kind, role, status, data, created_at) "
        "VALUES (:t, :o, :tid, 'user_message', 'user', 'done', "
        "        cast(:d as jsonb), :c)"
    ), {
        "t": thread_id, "o": str(org_id), "tid": str(turn),
        "d": json.dumps({"text": msg.content, "attachments": []}),
        "c": msg.created_at,
    })


def _insert_assistant_items(
    conn: Connection, thread_id: int, org_id: Any, turn: uuid.UUID, msg: Any
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
                "VALUES (:t, :o, :tid, 'memory_pill', 'system', 'done', cast(:d as jsonb), :c)"
            ), {
                "t": thread_id, "o": str(org_id), "tid": str(turn),
                "d": json.dumps({"count": stream_item.get("count", 0)}),
                "c": base_ts + offset * _MICRO,
            })
        elif kind in {"web_search", "fetch_webpage", "kb_search", "tool_call"}:
            offset += 1
            provider = stream_item.get("provider")
            flat = _TOOL_FLAT_COST_USD.get(provider or "", None)
            if provider and provider not in _TOOL_FLAT_COST_USD:
                _LOG.warning("backfill: unknown tool provider %r — cost_usd will be NULL", provider)
            conn.execute(text(
                "INSERT INTO thread_items "
                "(thread_id, org_id, turn_id, kind, role, status, provider, cost_usd, cost_estimated, data, created_at) "
                "VALUES (:t, :o, :tid, 'tool_call', 'assistant', 'done', :p, :cu, TRUE, cast(:d as jsonb), :c)"
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
            "VALUES (:t, :o, :tid, 'thinking', 'assistant', 'done', cast(:d as jsonb), :c)"
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
            "VALUES (:t, :o, :tid, 'assistant_text', 'assistant', 'done', cast(:d as jsonb), :c)"
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
            "VALUES (:t, :o, :tid, 'llm_call', 'assistant', 'done', :m, :cu, FALSE, cast(:d as jsonb), :c)"
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
        "VALUES (:t, :o, :tid, 'turn_end', 'system', 'done', cast(:d as jsonb), :c)"
    ), {
        "t": thread_id, "o": str(org_id), "tid": str(turn),
        "d": json.dumps({"reason": "done"}),
        "c": base_ts + offset * _MICRO,
    })
