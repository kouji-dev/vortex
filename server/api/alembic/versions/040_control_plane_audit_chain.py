"""control_plane: audit chain + sinks.

Revision ID: 040_control_plane_audit_chain
Revises: 039_control_plane_usage_budgets
Create Date: 2026-05-28

Phase D of the Control Plane plan. Extends the existing ``audit_events`` table
with a tamper-evident Merkle hash chain and converts it to PostgreSQL native
RANGE partitioning by ``created_at`` (monthly). Adds a per-org retention +
sink-configuration table.

Why partition: audit volume scales with traffic; monthly partitions let
retention sweeps DROP whole partitions (O(1) vs row-by-row DELETE).

Why hash chain: each event carries ``prev_hash`` (the previous event's
``hash`` within the same org) and its own ``hash``. Re-walking the chain
detects any single-row tampering. The DB-level append-only trigger from
029 already blocks UPDATE/DELETE outside ``bypass_rls``.

Strategy for the existing table:
1. Rename ``audit_events`` → ``audit_events_legacy``
2. Create new partitioned ``audit_events`` with hash columns + composite PK
3. Pre-create partitions for [prev month, this month, next month]
4. Copy rows from legacy with NULL hash columns (chain restarts post-migration)
5. Drop legacy
6. Re-apply append-only trigger + RLS policy
7. Create ``audit_retention_config`` per-org retention + sink config table
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID

revision = "040_control_plane_audit_chain"
down_revision = "039_control_plane_usage_budgets"
branch_labels = None
depends_on = None


def _month_floor(d: datetime) -> datetime:
    return d.replace(day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc)


def _next_month(d: datetime) -> datetime:
    if d.month == 12:
        return d.replace(year=d.year + 1, month=1)
    return d.replace(month=d.month + 1)


def _partition_name(start: datetime) -> str:
    return f"audit_events_p{start.strftime('%Y_%m')}"


def upgrade() -> None:
    # ---- 1. Drop triggers + policy on legacy table -------------------------
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update ON audit_events")
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_delete ON audit_events")
    op.execute("DROP POLICY IF EXISTS audit_events_org_isolation ON audit_events")

    op.execute("ALTER TABLE audit_events RENAME TO audit_events_legacy")
    op.execute("ALTER INDEX ix_audit_events_org_created RENAME TO ix_audit_events_legacy_org_created")
    op.execute("ALTER INDEX ix_audit_events_org_resource RENAME TO ix_audit_events_legacy_org_resource")
    op.execute("ALTER INDEX ix_audit_events_org_type_created RENAME TO ix_audit_events_legacy_org_type_created")

    # ---- 2. Create partitioned audit_events --------------------------------
    op.execute(
        """
        CREATE TABLE audit_events (
            id BIGSERIAL,
            event_id UUID NOT NULL DEFAULT gen_random_uuid(),
            org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
            actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
            actor_type VARCHAR(16) NOT NULL DEFAULT 'user',
            actor_json JSONB,
            event_type VARCHAR(64) NOT NULL,
            resource_type VARCHAR(32) NOT NULL,
            resource_id VARCHAR(128),
            action VARCHAR(32) NOT NULL,
            payload_json JSONB,
            metadata JSONB,
            request_id VARCHAR(64),
            ip_address INET,
            user_agent TEXT,
            prev_hash VARCHAR(64),
            hash VARCHAR(64) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
        """
    )

    op.create_index("ix_audit_events_org_created", "audit_events", ["org_id", "created_at"])
    op.create_index("ix_audit_events_org_resource", "audit_events", ["org_id", "resource_type", "resource_id"])
    op.create_index("ix_audit_events_org_type_created", "audit_events", ["org_id", "event_type", "created_at"])
    op.create_index("ix_audit_events_event_id", "audit_events", ["event_id"])
    op.create_index("ix_audit_events_hash", "audit_events", ["hash"])

    # ---- 3. Pre-create partitions: prev month, this month, next month ------
    now = datetime.now(tz=timezone.utc)
    this_m = _month_floor(now)
    months = [
        _month_floor((now - timedelta(days=31))),
        this_m,
        _next_month(this_m),
    ]
    # Also a catch-all for legacy rows older than prev month
    legacy_start = datetime(2020, 1, 1, tzinfo=timezone.utc)
    op.execute(
        f"CREATE TABLE audit_events_p_legacy PARTITION OF audit_events "
        f"FOR VALUES FROM ('{legacy_start.isoformat()}') TO ('{months[0].isoformat()}')"
    )
    for m in months:
        end = _next_month(m)
        op.execute(
            f"CREATE TABLE {_partition_name(m)} PARTITION OF audit_events "
            f"FOR VALUES FROM ('{m.isoformat()}') TO ('{end.isoformat()}')"
        )

    # ---- 4. Copy legacy rows; hash chain restarts (prev_hash=NULL, hash=sha256(row)) -
    # We compute a deterministic hash inline so post-migration the chain has a value.
    # This is acceptable: the historical chain is just a single epoch with no prev_hash,
    # validating that nothing was tampered with post-migration.
    op.execute(
        """
        INSERT INTO audit_events (
            id, event_id, org_id, actor_user_id, actor_type, event_type,
            resource_type, resource_id, action, metadata, request_id,
            ip_address, user_agent, prev_hash, hash, created_at
        )
        SELECT
            id,
            gen_random_uuid(),
            org_id,
            actor_user_id,
            actor_type,
            event_type,
            resource_type,
            resource_id,
            action,
            metadata,
            request_id,
            ip_address,
            user_agent,
            NULL,
            encode(sha256(
                (id::text || '|' || org_id::text || '|' || event_type ||
                 '|' || resource_type || '|' || COALESCE(resource_id, '') ||
                 '|' || action || '|' || created_at::text
                )::bytea
            ), 'hex'),
            created_at
        FROM audit_events_legacy
        """
    )

    # Bump the BIGSERIAL beyond legacy max
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('audit_events', 'id'),
            COALESCE((SELECT MAX(id) FROM audit_events), 1)
        )
        """
    )

    # ---- 5. Drop legacy ----------------------------------------------------
    op.execute("DROP TABLE audit_events_legacy")

    # ---- 6. Re-enable RLS + append-only trigger ----------------------------
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_events_org_isolation ON audit_events
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )
    # Re-use existing block function (still present from 029)
    op.execute(
        """
        CREATE TRIGGER audit_events_no_update
        BEFORE UPDATE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION app.audit_events_block_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_no_delete
        BEFORE DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION app.audit_events_block_mutation();
        """
    )

    # ---- 7. audit_retention_config ----------------------------------------
    op.create_table(
        "audit_retention_config",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="2555"),
        sa.Column("sink_configs", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.execute("ALTER TABLE audit_retention_config ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_retention_config FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_retention_config_org_isolation ON audit_retention_config
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ---- 8. audit_export_jobs ---------------------------------------------
    op.create_table(
        "audit_export_jobs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("requested_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("fmt", sa.String(16), nullable=False),
        sa.Column("destination", sa.String(32), nullable=False, server_default="download"),
        sa.Column("filter_json", JSONB, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("blob_url", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_audit_export_jobs_org_status", "audit_export_jobs", ["org_id", "status"])
    op.execute("ALTER TABLE audit_export_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_export_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY audit_export_jobs_org_isolation ON audit_export_jobs
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    # Audit chain migrations are not reversible — historical hash linkage would break.
    raise RuntimeError("039_control_plane_audit_chain is not reversible. Restore from backup.")
