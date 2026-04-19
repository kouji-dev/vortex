"""Knowledge base connectors and sync job orchestration.

Revision ID: 014_kb_connectors
Revises: 013_kb_conv
Create Date: 2026-03-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "014_kb_connectors"
down_revision: str | None = "013_kb_conv"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_base_connectors",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=255), server_default="", nullable=False),
        sa.Column(
            "settings",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind in ('files','github','gitlab','confluence','s3')",
            name="ck_kb_connector_kind",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_base_connectors_knowledge_base_id"),
        "knowledge_base_connectors",
        ["knowledge_base_id"],
        unique=False,
    )

    op.create_table(
        "connector_sync_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.Column("connector_id", sa.Integer(), nullable=False),
        sa.Column(
            "job_type",
            sa.String(length=32),
            server_default="full_sync",
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=32),
            server_default="queued",
            nullable=False,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('queued','running','succeeded','failed')",
            name="ck_connector_sync_job_status",
        ),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["knowledge_base_connectors.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_connector_sync_jobs_connector_id"),
        "connector_sync_jobs",
        ["connector_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_connector_sync_jobs_knowledge_base_id"),
        "connector_sync_jobs",
        ["knowledge_base_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_connector_sync_jobs_knowledge_base_id"),
        table_name="connector_sync_jobs",
    )
    op.drop_index(
        op.f("ix_connector_sync_jobs_connector_id"),
        table_name="connector_sync_jobs",
    )
    op.drop_table("connector_sync_jobs")
    op.drop_index(
        op.f("ix_knowledge_base_connectors_knowledge_base_id"),
        table_name="knowledge_base_connectors",
    )
    op.drop_table("knowledge_base_connectors")
