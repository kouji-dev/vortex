"""control_plane: scim — provisioning endpoints + group->role mapping.

Revision ID: 046_control_plane_scim
Revises: 045_control_plane_settings
Create Date: 2026-05-28

Phase H of the Control Plane plan. Adds three tables:

- ``scim_endpoints``: one per org. Stores the bearer-token SHA-256 hash plus
  an optional preset name (``okta`` / ``entra`` / generic). ``last_sync_at``
  bumps on every SCIM operation. ``enabled`` allows admins to pause
  provisioning without deleting the endpoint.
- ``scim_groups``: shadow record per SCIM Group. Maps display_name -> role
  inside the org. ``external_id`` is the IdP's stable id (Entra ``objectId``,
  Okta group id).
- ``scim_group_members``: link rows joining a shadow group to either a user
  (resolved during provisioning) or a not-yet-resolved external user id.

All three tables are org-scoped with the standard RLS policy.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "046_control_plane_scim"
down_revision = "045_control_plane_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── scim_endpoints ──────────────────────────────────────────────────────
    op.create_table(
        "scim_endpoints",
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
        sa.Column("name", sa.String(128), nullable=False),
        # Preset: ``generic`` | ``okta`` | ``entra``. Selects the attribute
        # mapper used by the SCIM service to translate inbound payloads.
        sa.Column(
            "preset",
            sa.String(32),
            nullable=False,
            server_default="generic",
        ),
        # SHA-256 hex of the bearer token. Token itself is shown once at
        # creation and never persisted in plaintext.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "last_sync_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "revoked_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("token_hash", name="uq_scim_endpoints_token_hash"),
    )
    op.create_index("ix_scim_endpoints_org_id", "scim_endpoints", ["org_id"])
    op.create_index("ix_scim_endpoints_token_hash", "scim_endpoints", ["token_hash"])

    op.execute("ALTER TABLE scim_endpoints ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scim_endpoints FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY scim_endpoints_org_isolation ON scim_endpoints
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── scim_groups ─────────────────────────────────────────────────────────
    # Shadow record per SCIM Group, with optional role mapping.
    op.create_table(
        "scim_groups",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "endpoint_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scim_endpoints.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        # If set, members of this group are assigned the named system role
        # (owner / admin / member / viewer / service).
        sa.Column("role_name", sa.String(32), nullable=True),
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
        sa.UniqueConstraint(
            "endpoint_id", "display_name", name="uq_scim_groups_endpoint_display"
        ),
    )
    op.create_index("ix_scim_groups_org_id", "scim_groups", ["org_id"])
    op.create_index("ix_scim_groups_endpoint_id", "scim_groups", ["endpoint_id"])
    op.create_index("ix_scim_groups_external_id", "scim_groups", ["external_id"])

    op.execute("ALTER TABLE scim_groups ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scim_groups FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY scim_groups_org_isolation ON scim_groups
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── scim_group_members ──────────────────────────────────────────────────
    op.create_table(
        "scim_group_members",
        sa.Column(
            "id",
            sa.Integer(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "group_id",
            UUID(as_uuid=True),
            sa.ForeignKey("scim_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=True,
        ),
        # Used when the SCIM member ref points to a user we haven't seen yet.
        sa.Column("external_user_id", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "group_id", "user_id", name="uq_scim_group_members_group_user"
        ),
    )
    op.create_index(
        "ix_scim_group_members_org_id", "scim_group_members", ["org_id"]
    )
    op.create_index(
        "ix_scim_group_members_group_id", "scim_group_members", ["group_id"]
    )

    op.execute("ALTER TABLE scim_group_members ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE scim_group_members FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY scim_group_members_org_isolation ON scim_group_members
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── users: add external_id for SCIM provisioning ────────────────────────
    # ``external_id`` is the stable IdP-side identifier (Entra ``objectId``,
    # Okta user id, generic SCIM ``externalId``). Additive-only column.
    op.add_column(
        "users",
        sa.Column("scim_external_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_users_scim_external_id", "users", ["scim_external_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_users_scim_external_id", table_name="users")
    op.drop_column("users", "scim_external_id")

    op.execute(
        "DROP POLICY IF EXISTS scim_group_members_org_isolation ON scim_group_members"
    )
    op.drop_index("ix_scim_group_members_group_id", table_name="scim_group_members")
    op.drop_index("ix_scim_group_members_org_id", table_name="scim_group_members")
    op.drop_table("scim_group_members")

    op.execute("DROP POLICY IF EXISTS scim_groups_org_isolation ON scim_groups")
    op.drop_index("ix_scim_groups_external_id", table_name="scim_groups")
    op.drop_index("ix_scim_groups_endpoint_id", table_name="scim_groups")
    op.drop_index("ix_scim_groups_org_id", table_name="scim_groups")
    op.drop_table("scim_groups")

    op.execute("DROP POLICY IF EXISTS scim_endpoints_org_isolation ON scim_endpoints")
    op.drop_index("ix_scim_endpoints_token_hash", table_name="scim_endpoints")
    op.drop_index("ix_scim_endpoints_org_id", table_name="scim_endpoints")
    op.drop_table("scim_endpoints")
