"""control_plane: teams + team_members (org -> team -> user hierarchy).

Adds two tables:

- ``teams``: org-scoped team rows (slug unique per org).
- ``team_members``: join of org users to teams with an optional per-team role.
  ``org_id`` is denormalized so RLS scopes membership rows directly.

Also seeds the new ``teams:read`` / ``teams:write`` permissions into the
catalog and grants them to the ``owner`` + ``admin`` system roles.

API keys stay owned by individuals — there is NO team_id on api_keys. Per-team
key counts are derived by joining team_members to api_keys.actor_user_id.

Revision ID: 070_control_plane_teams
Revises: 043_control_plane_idp_connections
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "070_control_plane_teams"
down_revision = "065_workers_instances"
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


def upgrade() -> None:
    op.create_table(
        "teams",
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
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "slug", name="uq_teams_org_slug"),
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "team_id",
            UUID(as_uuid=True),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
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
            nullable=False,
        ),
        sa.Column("role", sa.String(32), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "team_id", "user_id", name="uq_team_members_team_user"
        ),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_org_id", "team_members", ["org_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])

    _enable_rls("teams")
    _enable_rls("team_members")

    # ── seed new permissions + owner/admin grants ─────────────────────────
    op.execute(
        """
        INSERT INTO permissions(key, description, module) VALUES
          ('teams:read',  'List teams + members + per-team key/usage stats', 'control_plane'),
          ('teams:write', 'Create / update / delete teams + memberships',    'control_plane')
        ON CONFLICT (key) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO role_permissions(role_id, permission_key, resource_scope)
        SELECT r.id, p.key, NULL
        FROM roles r
        CROSS JOIN (VALUES ('teams:read'), ('teams:write')) AS p(key)
        WHERE r.is_system = true
          AND r.org_id IS NULL
          AND r.name IN ('owner', 'admin')
        ON CONFLICT (role_id, permission_key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM role_permissions WHERE permission_key IN ('teams:read', 'teams:write')"
    )
    op.execute(
        "DELETE FROM permissions WHERE key IN ('teams:read', 'teams:write')"
    )
    op.execute("DROP POLICY IF EXISTS team_members_org_isolation ON team_members")
    op.execute("DROP POLICY IF EXISTS teams_org_isolation ON teams")
    op.drop_index("ix_team_members_user_id", table_name="team_members")
    op.drop_index("ix_team_members_org_id", table_name="team_members")
    op.drop_index("ix_team_members_team_id", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_org_id", table_name="teams")
    op.drop_table("teams")
