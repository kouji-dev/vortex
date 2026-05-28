"""rag: connector tables.

Adds three tables that own the RAG connector subsystem:

- ``kb_connectors``  — per-KB connector configuration (cipher-text config).
- ``kb_sync_runs``   — one row per orchestrated sync.
- ``kb_sync_errors`` — per-document failure log, scoped to a sync run.

Revision ID: 056_rag_connectors
Revises: 055_gateway_playground_evals
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "056_rag_connectors"
down_revision = "055_gateway_playground_evals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kb_connectors",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "kb_id",
            sa.Integer(),
            sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column(
            "config_encrypted",
            sa.LargeBinary(),
            nullable=False,
            server_default=sa.text("''::bytea"),
        ),
        sa.Column("schedule_cron", sa.String(64), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_cursor", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_connectors_kb_id", "kb_connectors", ["kb_id"])
    op.create_index("ix_kb_connectors_kind", "kb_connectors", ["kind"])

    op.create_table(
        "kb_sync_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "connector_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_connectors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="running",
        ),
        sa.Column(
            "docs_added",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "docs_updated",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "docs_deleted",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "errors_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("cursor_after", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_kb_sync_runs_connector_id", "kb_sync_runs", ["connector_id"]
    )
    op.create_index(
        "ix_kb_sync_runs_started_at", "kb_sync_runs", ["started_at"]
    )

    op.create_table(
        "kb_sync_errors",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("kb_sync_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_uri", sa.String(2048), nullable=False),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_kb_sync_errors_run_id", "kb_sync_errors", ["run_id"])


def downgrade() -> None:
    op.drop_index("ix_kb_sync_errors_run_id", table_name="kb_sync_errors")
    op.drop_table("kb_sync_errors")
    op.drop_index("ix_kb_sync_runs_started_at", table_name="kb_sync_runs")
    op.drop_index("ix_kb_sync_runs_connector_id", table_name="kb_sync_runs")
    op.drop_table("kb_sync_runs")
    op.drop_index("ix_kb_connectors_kind", table_name="kb_connectors")
    op.drop_index("ix_kb_connectors_kb_id", table_name="kb_connectors")
    op.drop_table("kb_connectors")
