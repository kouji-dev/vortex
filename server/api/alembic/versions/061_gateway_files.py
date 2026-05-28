"""gateway: files API.

Adds:
- ``gateway_files`` — uploaded files (proxy for Anthropic Files / OpenAI
  Assistants compat). Backed by Control Plane :class:`BlobStore`; the row
  holds the blob key + metadata so admins can list/audit/delete files.

Revision ID: 061_gateway_files
Revises: 060_rag_eval_analytics
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "061_gateway_files"
down_revision = "060_rag_eval_analytics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gateway_files",
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
        sa.Column("actor_user_id", sa.Integer(), nullable=True),
        sa.Column("blob_key", sa.String(512), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_type", sa.String(128), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column(
            "purpose",
            sa.String(64),
            nullable=False,
            server_default="user_data",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_gateway_files_org_id", "gateway_files", ["org_id"]
    )

    op.execute("ALTER TABLE gateway_files ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE gateway_files FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY gateway_files_org_isolation ON gateway_files
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS gateway_files_org_isolation ON gateway_files"
    )
    op.drop_index("ix_gateway_files_org_id", table_name="gateway_files")
    op.drop_table("gateway_files")
