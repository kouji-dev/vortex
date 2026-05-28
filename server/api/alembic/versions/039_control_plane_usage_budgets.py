"""control_plane: usage budgets — usage_events (monthly partitioned), quotas, budgets.

Revision ID: 039_control_plane_usage_budgets
Revises: 038_control_plane_notify_core
Create Date: 2026-05-28

Adds:
- ``usage_events``: append-only fact table for every metered action.
  Partitioned by RANGE on ``ts`` (monthly). Each row carries a frozen pricing
  snapshot so cost remains stable across rate updates.
- ``quotas``: hard cap per unit per period, scoped by org/user/key/team/model.
- ``budgets``: USD-denominated soft+hard cutoff with grace period extension.
- ``budget_alerts``: warning + cutoff fired log.

RLS follows the existing pattern: ``org_id``-scoped via ``app.current_org_id()``
with ``app.is_rls_bypassed()`` escape hatch for system jobs (rollups).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "039_control_plane_usage_budgets"
# Chains after RBAC migration (039_control_plane_rbac) which itself chains
# off 038. Keeps single linear head: 038 → rbac → usage_budgets → … .
down_revision = "039_control_plane_rbac"
branch_labels = None
depends_on = None


_RLS_TABLES = ("usage_events", "quotas", "budgets", "budget_alerts")


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def _month_start(d: datetime) -> datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _next_month(d: datetime) -> datetime:
    year = d.year + (d.month // 12)
    month = (d.month % 12) + 1
    return d.replace(year=year, month=month, day=1)


def _create_usage_events_partitions() -> None:
    """Create monthly partitions covering last 3 months → next 13 months."""
    now = datetime.now(timezone.utc)
    start = _month_start(now) - timedelta(days=92)
    start = _month_start(start)
    cur = start
    for _ in range(16):
        nxt = _next_month(cur)
        name = f"usage_events_{cur.year:04d}_{cur.month:02d}"
        op.execute(
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF usage_events "
            f"FOR VALUES FROM ('{cur.isoformat()}') TO ('{nxt.isoformat()}')"
        )
        cur = nxt
    # default catches inserts outside the prepared range (e.g. backfills)
    op.execute(
        "CREATE TABLE IF NOT EXISTS usage_events_default PARTITION OF usage_events DEFAULT"
    )


def upgrade() -> None:
    # ── usage_events (partitioned by ts month) ───────────────────────────────
    op.execute(
        """
        CREATE TABLE usage_events (
            id BIGSERIAL NOT NULL,
            org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            ts TIMESTAMPTZ NOT NULL,
            unit VARCHAR(32) NOT NULL,
            qty NUMERIC(20, 6) NOT NULL DEFAULT 0,
            cost_usd NUMERIC(14, 6) NOT NULL DEFAULT 0,
            pricing_snapshot JSONB,
            actor_kind VARCHAR(16) NOT NULL,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            actor_api_key_id BIGINT,
            actor_team_id BIGINT,
            module VARCHAR(32) NOT NULL,
            model VARCHAR(128),
            resource_kind VARCHAR(32),
            resource_id VARCHAR(64),
            request_id UUID,
            idempotency_key VARCHAR(128),
            meta JSONB,
            PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts)
        """
    )
    op.create_index(
        "ix_usage_events_org_ts", "usage_events", ["org_id", "ts"]
    )
    op.create_index(
        "ix_usage_events_org_unit_ts", "usage_events", ["org_id", "unit", "ts"]
    )
    op.create_index(
        "ix_usage_events_org_actor_ts",
        "usage_events",
        ["org_id", "actor_kind", "ts"],
    )
    op.create_index(
        "ix_usage_events_org_model_ts",
        "usage_events",
        ["org_id", "model", "ts"],
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_usage_events_idem ON usage_events "
        "(org_id, idempotency_key, ts) WHERE idempotency_key IS NOT NULL"
    )
    _create_usage_events_partitions()

    # ── quotas ───────────────────────────────────────────────────────────────
    op.create_table(
        "quotas",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),  # org|user|api_key|team
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("unit", sa.String(32), nullable=False),
        sa.Column("period", sa.String(16), nullable=False, server_default="month"),
        sa.Column("max_qty", sa.Numeric(20, 6), nullable=False),
        sa.Column(
            "action_on_breach", sa.String(16), nullable=False, server_default="block"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_quotas_org_scope_unit", "quotas", ["org_id", "scope_kind", "unit"])

    # ── budgets ──────────────────────────────────────────────────────────────
    op.create_table(
        "budgets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("scope_kind", sa.String(16), nullable=False),  # org|user|api_key|team
        sa.Column("scope_id", sa.String(64), nullable=True),
        sa.Column("limit_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("period", sa.String(16), nullable=False, server_default="month"),
        # custom cadence: explicit window
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "warn_at_pcts",
            JSONB,
            nullable=False,
            server_default=sa.text("'[50, 80, 100]'::jsonb"),
        ),
        sa.Column("hard_cutoff", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("grace_extension_usd", sa.Numeric(14, 6), nullable=True),
        sa.Column("grace_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "webhook_on_threshold", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_budgets_org_scope", "budgets", ["org_id", "scope_kind", "scope_id"])

    # ── budget_alerts ────────────────────────────────────────────────────────
    op.create_table(
        "budget_alerts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "budget_id",
            sa.BigInteger(),
            sa.ForeignKey("budgets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("threshold_pct", sa.Integer(), nullable=False),
        sa.Column("amount_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "fired_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "budget_id", "period_start", "threshold_pct",
            name="uq_budget_alerts_period_threshold",
        ),
    )
    op.create_index(
        "ix_budget_alerts_budget_fired", "budget_alerts", ["budget_id", "fired_at"]
    )

    # ── enable RLS on all four ──────────────────────────────────────────────
    for t in _RLS_TABLES:
        _enable_rls(t)


def downgrade() -> None:
    for t in reversed(_RLS_TABLES):
        op.execute(f"DROP POLICY IF EXISTS {t}_org_isolation ON {t}")

    op.drop_index("ix_budget_alerts_budget_fired", "budget_alerts")
    op.drop_table("budget_alerts")

    op.drop_index("ix_budgets_org_scope", "budgets")
    op.drop_table("budgets")

    op.drop_index("ix_quotas_org_scope_unit", "quotas")
    op.drop_table("quotas")

    op.execute("DROP TABLE IF EXISTS usage_events CASCADE")
