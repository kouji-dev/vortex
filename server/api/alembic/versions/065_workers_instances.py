"""workers: worker-centric instance tables (v1 "a worker IS a task").

Adds the worker-centric layer that coexists with the legacy task-centric
tables from ``058_workers_core``:

- ``workers``               — first-class spawned worker (mode/state/model/
                              runtime/connector/repo/sandbox/trigger). Org-scoped
                              + RLS isolated.
- ``worker_instance_runs``  — one row per user-message → agent-work cycle.
- ``worker_run_changes``    — files changed during a run (drives the diff pane).
- ``worker_messages``       — the worker's own agent-SDK chat thread.

Only ``workers`` is org-scoped (RLS). The child tables are reached through the
worker FK and inherit isolation transitively (cascade delete on worker).

Revision ID: 065_workers_instances
Revises: 064_memory_encryption_config
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "065_workers_instances"
down_revision = "064_memory_encryption_config"
branch_labels = None
depends_on = None


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


def _drop_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")


def upgrade() -> None:
    op.create_table(
        "workers",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_pools.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="provisioning",
        ),
        sa.Column(
            "mode",
            sa.String(16),
            nullable=False,
            server_default="interactive",
        ),
        sa.Column("model", sa.String(128), nullable=False),
        sa.Column(
            "runtime", sa.String(16), nullable=False, server_default="claude"
        ),
        sa.Column(
            "connector_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("repo_url", sa.String(1024), nullable=True),
        sa.Column("sandbox_id", UUID(as_uuid=True), nullable=True),
        sa.Column("trigger_source", sa.String(32), nullable=True),
        sa.Column(
            "trigger_payload_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_workers_org_id", "workers", ["org_id"])
    op.create_index("ix_workers_pool_id", "workers", ["pool_id"])
    op.create_index("ix_workers_state", "workers", ["state"])
    _enable_rls("workers")

    op.create_table(
        "worker_instance_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "worker_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("seq_no", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("user_message", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "status", sa.String(16), nullable=False, server_default="running"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sandbox_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "cost_cents", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("error", sa.String(2048), nullable=True),
        sa.UniqueConstraint(
            "worker_id", "seq_no", name="uq_worker_instance_runs_seq"
        ),
    )
    op.create_index(
        "ix_worker_instance_runs_worker",
        "worker_instance_runs",
        ["worker_id", "seq_no"],
    )

    op.create_table(
        "worker_run_changes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_instance_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("change_kind", sa.String(16), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deletions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("diff_ref", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_worker_run_changes_run", "worker_run_changes", ["run_id"]
    )

    op.create_table(
        "worker_messages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "worker_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_instance_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_worker_messages_worker_ts", "worker_messages", ["worker_id", "ts"]
    )
    op.create_index(
        "ix_worker_messages_run", "worker_messages", ["run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_worker_messages_run", table_name="worker_messages")
    op.drop_index("ix_worker_messages_worker_ts", table_name="worker_messages")
    op.drop_table("worker_messages")

    op.drop_index("ix_worker_run_changes_run", table_name="worker_run_changes")
    op.drop_table("worker_run_changes")

    op.drop_index(
        "ix_worker_instance_runs_worker", table_name="worker_instance_runs"
    )
    op.drop_table("worker_instance_runs")

    _drop_rls("workers")
    op.drop_index("ix_workers_state", table_name="workers")
    op.drop_index("ix_workers_pool_id", table_name="workers")
    op.drop_index("ix_workers_org_id", table_name="workers")
    op.drop_table("workers")
