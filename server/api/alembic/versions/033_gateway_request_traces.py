"""gateway: request_traces.

Monthly partitioned by ``ts`` (RANGE). One row per LLM gateway request.

Revision ID: 033_gateway_request_traces
Revises: 032_dev_user_admin_role
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from alembic import op

revision = "033_gateway_request_traces"
down_revision = "032_dev_user_admin_role"
branch_labels = None
depends_on = None


def _next_month(d: datetime) -> datetime:
    year = d.year + (d.month // 12)
    month = (d.month % 12) + 1
    return d.replace(year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0)


def upgrade() -> None:
    op.execute(
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
    )

    op.create_index(
        "ix_request_traces_org_ts",
        "request_traces",
        ["org_id", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_request_traces_org_model_ts",
        "request_traces",
        ["org_id", "model_used", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_request_traces_org_status_ts",
        "request_traces",
        ["org_id", "status", sa.text("ts DESC")],
    )
    op.create_index(
        "ix_request_traces_request_hash",
        "request_traces",
        ["request_hash"],
    )

    # RLS — org isolation.
    op.execute("ALTER TABLE request_traces ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE request_traces FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY request_traces_org_isolation ON request_traces
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # Seed partitions: current month + next 2 months + previous month.
    now = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    prev_month = (now - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months = [prev_month, now, _next_month(now), _next_month(_next_month(now))]
    for start in months:
        end = _next_month(start)
        name = f"request_traces_{start.strftime('%Y_%m')}"
        op.execute(
            f"""
            CREATE TABLE {name} PARTITION OF request_traces
            FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')
            """
        )

    # Default partition catches any out-of-range insert (safety net).
    op.execute(
        """
        CREATE TABLE request_traces_default PARTITION OF request_traces DEFAULT
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS request_traces CASCADE")
