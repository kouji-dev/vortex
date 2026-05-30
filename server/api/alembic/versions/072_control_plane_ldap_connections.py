"""control_plane: ldap_connections — LDAP/AD direct-bind config.

Per-org (org_id set) or per-deployment (org_id NULL) connection rows. The
service-account ``bind_secret`` is stored envelope-encrypted in
``bind_secret_enc``. RLS allows a row when its org matches the tenant context
OR the row is a per-deployment row (org_id IS NULL) OR RLS is bypassed.

Revision ID: 072_control_plane_ldap_connections
Revises: 071_control_plane_api_key_rate_limits
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "072_control_plane_ldap_connections"
down_revision = "071_control_plane_api_key_rate_limits"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ldap_connections",
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
            nullable=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False, server_default="ldap"),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False, server_default="389"),
        sa.Column("bind_dn", sa.String(512), nullable=False),
        sa.Column("bind_secret_enc", sa.Text(), nullable=False),
        sa.Column("base_dn", sa.String(512), nullable=False),
        sa.Column(
            "user_filter",
            sa.String(512),
            nullable=False,
            server_default="(uid={username})",
        ),
        sa.Column("group_filter", sa.String(512), nullable=True),
        sa.Column("tls_mode", sa.String(16), nullable=False, server_default="none"),
        sa.Column("attr_map_json", JSONB, nullable=True),
        sa.Column("group_role_map_json", JSONB, nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.true()
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
    op.create_index(
        "ix_ldap_connections_org_id", "ldap_connections", ["org_id"]
    )

    op.execute("ALTER TABLE ldap_connections ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ldap_connections FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY ldap_connections_org_or_deployment ON ldap_connections
        USING (
            org_id IS NULL
            OR org_id = app.current_org_id()
            OR app.is_rls_bypassed()
        )
        WITH CHECK (
            org_id IS NULL
            OR org_id = app.current_org_id()
            OR app.is_rls_bypassed()
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS ldap_connections_org_or_deployment ON ldap_connections"
    )
    op.drop_index("ix_ldap_connections_org_id", table_name="ldap_connections")
    op.drop_table("ldap_connections")
