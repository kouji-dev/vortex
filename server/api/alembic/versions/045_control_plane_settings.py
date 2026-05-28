"""control_plane: settings module flags — per-org KV + module on/off + gates.

Revision ID: 045_control_plane_settings
Revises: 044_control_plane_billing
Create Date: 2026-05-28

Phase L of the Control Plane plan. Adds two tables:

- ``org_settings``: generic per-org KV. ``value_json`` is JSONB so callers
  can store any JSON-serialisable shape (strings, numbers, dicts, lists).
- ``module_flags``: per-module enable/disable per org with optional named
  feature gates inside ``gates_json``. Absence of a row implies the module
  is enabled (default-on); gates default to false (opt-in).

Both tables are org-scoped with RLS policies matching the other control-plane
tables (see ``webhooks``, ``audit_events``).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "045_control_plane_settings"
down_revision = "044_control_plane_billing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_settings ────────────────────────────────────────────────────────
    op.create_table(
        "org_settings",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("org_id", "key", name="pk_org_settings"),
    )
    op.create_index("ix_org_settings_org_id", "org_settings", ["org_id"])

    op.execute("ALTER TABLE org_settings ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE org_settings FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY org_settings_org_isolation ON org_settings
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    # ── module_flags ────────────────────────────────────────────────────────
    op.create_table(
        "module_flags",
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "gates_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("org_id", "module", name="pk_module_flags"),
    )
    op.create_index("ix_module_flags_org_id", "module_flags", ["org_id"])

    op.execute("ALTER TABLE module_flags ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE module_flags FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY module_flags_org_isolation ON module_flags
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS module_flags_org_isolation ON module_flags")
    op.drop_index("ix_module_flags_org_id", table_name="module_flags")
    op.drop_table("module_flags")

    op.execute("DROP POLICY IF EXISTS org_settings_org_isolation ON org_settings")
    op.drop_index("ix_org_settings_org_id", table_name="org_settings")
    op.drop_table("org_settings")
