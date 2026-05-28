"""control_plane: idp connections

Revision ID: 043_control_plane_idp_connections
Revises: 041_control_plane_webhooks
Create Date: 2026-05-28

Adds ``idp_connections`` — per-org SSO configuration. Phase G1 of the
Control Plane plan. SSO routes (G5) and "sso_required" enforcement (G6)
arrive in later commits — this revision is just the table.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "043_control_plane_idp_connections"
down_revision = "041_control_plane_webhooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idp_connections",
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
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "domain",
            sa.String(255),
            nullable=False,
            server_default="",
        ),
        sa.Column("config_encrypted", sa.Text(), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "sso_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("description", sa.String(255), nullable=True),
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
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "org_id",
            "kind",
            "domain",
            name="uq_idp_connections_org_kind_domain",
        ),
    )
    op.create_index("ix_idp_connections_org_id", "idp_connections", ["org_id"])
    # Domain lookup for /v1/auth/sso/start (Phase G5).
    op.create_index(
        "ix_idp_connections_domain",
        "idp_connections",
        ["domain"],
        postgresql_where=sa.text("domain <> ''"),
    )

    # Row-level security — same shape as other control-plane tables.
    op.execute("ALTER TABLE idp_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE idp_connections FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY idp_connections_org_isolation ON idp_connections
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS idp_connections_org_isolation ON idp_connections"
    )
    op.drop_index("ix_idp_connections_domain", table_name="idp_connections")
    op.drop_index("ix_idp_connections_org_id", table_name="idp_connections")
    op.drop_table("idp_connections")
