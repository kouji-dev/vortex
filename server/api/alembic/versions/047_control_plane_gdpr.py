"""control_plane: GDPR lifecycle — data_export_jobs + data_delete_jobs.

Revision ID: 046_control_plane_gdpr
Revises: 045_control_plane_settings
Create Date: 2026-05-28

Phase N. Two job tables tracking async GDPR workflows:

- ``data_export_jobs``: Article 15 — async fan-out to module exporters,
  zips the dump, uploads via BlobStore, emails presigned URL.
- ``data_delete_jobs``: Article 17 — async fan-out to module deleters,
  cascades across all module tables, emits an audit event on completion.

Both tables are org-scoped with RLS policies matching the other
control-plane tables.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "047_control_plane_gdpr"
down_revision = "046_control_plane_scim"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── data_export_jobs ────────────────────────────────────────────────────
    op.create_table(
        "data_export_jobs",
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
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("result_url", sa.Text(), nullable=True),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_data_export_jobs_org_id", "data_export_jobs", ["org_id"]
    )
    op.create_index(
        "ix_data_export_jobs_status", "data_export_jobs", ["status"]
    )

    op.execute("ALTER TABLE data_export_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_export_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY data_export_jobs_org_isolation ON data_export_jobs
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── data_delete_jobs ────────────────────────────────────────────────────
    op.create_table(
        "data_delete_jobs",
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
            "scope_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="queued",
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_data_delete_jobs_org_id", "data_delete_jobs", ["org_id"]
    )
    op.create_index(
        "ix_data_delete_jobs_status", "data_delete_jobs", ["status"]
    )

    op.execute("ALTER TABLE data_delete_jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE data_delete_jobs FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY data_delete_jobs_org_isolation ON data_delete_jobs
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS data_delete_jobs_org_isolation ON data_delete_jobs"
    )
    op.drop_index("ix_data_delete_jobs_status", table_name="data_delete_jobs")
    op.drop_index("ix_data_delete_jobs_org_id", table_name="data_delete_jobs")
    op.drop_table("data_delete_jobs")

    op.execute(
        "DROP POLICY IF EXISTS data_export_jobs_org_isolation ON data_export_jobs"
    )
    op.drop_index("ix_data_export_jobs_status", table_name="data_export_jobs")
    op.drop_index("ix_data_export_jobs_org_id", table_name="data_export_jobs")
    op.drop_table("data_export_jobs")
