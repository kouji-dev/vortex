"""TraceWriter — submits trace records, writes all fields to DB."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC

import pytest
from sqlalchemy import text

from tests.conftest import requires_postgres


def _ensure_request_traces_table(engine) -> None:
    """Create request_traces (idempotent) so the test runs in any DB state.

    Mirrors alembic 033_gateway_request_traces. The real migration is
    authoritative; this is a safety net so the writer can be exercised
    against any developer/CI DB.
    """
    from datetime import datetime, timedelta

    def _next_month(d):
        year = d.year + (d.month // 12)
        month = (d.month % 12) + 1
        return d.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('public.request_traces')")
        ).scalar()
        if exists:
            return
        conn.execute(text(
            """
            CREATE TABLE request_traces (
                id UUID NOT NULL DEFAULT gen_random_uuid(),
                org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
                actor_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                route VARCHAR(64) NOT NULL,
                model_requested VARCHAR(128),
                model_used VARCHAR(128),
                provider VARCHAR(32),
                status VARCHAR(16) NOT NULL DEFAULT 'ok',
                latency_ms INTEGER,
                ttft_ms INTEGER,
                tokens_in INTEGER NOT NULL DEFAULT 0,
                tokens_out INTEGER NOT NULL DEFAULT 0,
                tokens_cache_read INTEGER NOT NULL DEFAULT 0,
                tokens_cache_write INTEGER NOT NULL DEFAULT 0,
                cost_cents NUMERIC(14, 6) NOT NULL DEFAULT 0,
                cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
                error TEXT,
                request_hash VARCHAR(64),
                ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                PRIMARY KEY (id, ts)
            ) PARTITION BY RANGE (ts)
            """
        ))
        now = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month = (now - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        months = [prev_month, now, _next_month(now), _next_month(_next_month(now))]
        for start in months:
            end = _next_month(start)
            name = f"request_traces_{start.strftime('%Y_%m')}"
            conn.execute(text(
                f"CREATE TABLE {name} PARTITION OF request_traces "
                f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
            ))
        conn.execute(text(
            "CREATE TABLE request_traces_default PARTITION OF request_traces DEFAULT"
        ))
        conn.commit()


def test_trace_record_has_all_fields():
    """TraceRecord exposes every field on request_traces table."""
    from ai_portal.gateway.traces.writer import TraceRecord

    rec = TraceRecord(
        org_id=uuid.uuid4(),
        route="/v1/chat/completions",
        actor_json={"user_id": 7, "api_key_id": "k_123"},
        model_requested="claude-sonnet-4-6",
        model_used="claude-sonnet-4-6-20260101",
        provider="anthropic",
        status="ok",
        latency_ms=842,
        ttft_ms=210,
        tokens_in=1200,
        tokens_out=350,
        tokens_cache_read=900,
        tokens_cache_write=300,
        cost_cents=4.250000,
        cache_hit=True,
        error=None,
        request_hash="abc123def456",
    )
    row = rec.to_row()
    for field in (
        "id", "org_id", "actor_json", "route", "model_requested", "model_used",
        "provider", "status", "latency_ms", "ttft_ms", "tokens_in", "tokens_out",
        "tokens_cache_read", "tokens_cache_write", "cost_cents", "cache_hit",
        "error", "request_hash", "ts",
    ):
        assert field in row, f"missing field {field}"


@requires_postgres
def test_writer_writes_row_with_all_fields(sync_engine):
    """Submit a TraceRecord, flush, and verify DB row matches every field."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.traces.model import RequestTrace
    from ai_portal.gateway.traces.writer import TraceRecord, TraceWriter, reset_writer

    reset_writer()
    org_id = uuid.uuid4()

    # Ensure request_traces table exists (idempotent — the alembic
    # migration is authoritative; this lets the test run in any DB state).
    _ensure_request_traces_table(sync_engine)

    # Make sure org exists for FK.
    with sync_engine.connect() as conn:
        conn.execute(
            text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'Trace Test') ON CONFLICT DO NOTHING"),
            {"id": str(org_id), "slug": f"trace-test-{org_id.hex[:8]}"},
        )
        conn.commit()

    async def run():
        writer = TraceWriter(batch_size=10, flush_interval=0.05)
        await writer.start()
        rec = TraceRecord(
            org_id=org_id,
            route="/v1/chat/completions",
            actor_json={"user_id": 99, "api_key_id": "k_test"},
            model_requested="gpt-4o",
            model_used="gpt-4o-2026-01-01",
            provider="openai",
            status="ok",
            latency_ms=500,
            ttft_ms=100,
            tokens_in=200,
            tokens_out=80,
            tokens_cache_read=50,
            tokens_cache_write=10,
            cost_cents=1.234567,
            cache_hit=False,
            error=None,
            request_hash="hash_xyz",
        )
        writer.submit(rec)
        await writer.stop()
        return rec.id

    rec_id = asyncio.run(run())

    db = SessionLocal()
    try:
        with bypass_rls(db):
            row = db.query(RequestTrace).filter(RequestTrace.id == rec_id).one_or_none()
        assert row is not None
        assert row.org_id == org_id
        assert row.route == "/v1/chat/completions"
        assert row.actor_json == {"user_id": 99, "api_key_id": "k_test"}
        assert row.model_requested == "gpt-4o"
        assert row.model_used == "gpt-4o-2026-01-01"
        assert row.provider == "openai"
        assert row.status == "ok"
        assert row.latency_ms == 500
        assert row.ttft_ms == 100
        assert row.tokens_in == 200
        assert row.tokens_out == 80
        assert row.tokens_cache_read == 50
        assert row.tokens_cache_write == 10
        assert float(row.cost_cents) == pytest.approx(1.234567)
        assert row.cache_hit is False
        assert row.request_hash == "hash_xyz"
    finally:
        db.close()


def test_writer_submit_is_non_blocking():
    """submit() returns immediately even with many records queued."""
    from ai_portal.gateway.traces.writer import TraceRecord, TraceWriter

    async def run():
        writer = TraceWriter(batch_size=100, flush_interval=10.0)
        # Do not start; just verify submit doesn't block.
        for i in range(500):
            writer.submit(
                TraceRecord(
                    org_id=uuid.uuid4(),
                    route="/v1/chat/completions",
                    tokens_in=i,
                )
            )
        # All sit in queue, none flushed.
        assert writer._queue.qsize() == 500
        await writer.stop()

    asyncio.run(run())
