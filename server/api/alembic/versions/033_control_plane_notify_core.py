"""control_plane: notify core.

Revision ID: 033_control_plane_notify_core
Revises: 032_dev_user_admin_role
Create Date: 2026-05-28

Adds two tables for the notification subsystem:
- ``notifications``: in-app inbox row. ``payload`` JSONB carries template vars.
- ``user_notification_prefs``: per-(user, event_type, channel) toggle.

RLS follows the existing pattern: enforced via ``org_id`` on ``notifications``
(membership-derived for prefs — no direct org_id column).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "033_control_plane_notify_core"
down_revision = "032_dev_user_admin_role"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
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
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column("template_id", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_notifications_org_id", "notifications", ["org_id"])
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index(
        "ix_notifications_user_unread",
        "notifications",
        ["user_id", "read_at"],
    )

    # RLS — match existing enterprise-table pattern.
    op.execute("ALTER TABLE notifications ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE notifications FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY notifications_org_isolation ON notifications
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )

    op.create_table(
        "user_notification_prefs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("channel", sa.String(32), nullable=False),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "user_id",
            "event_type",
            "channel",
            name="uq_user_notif_pref",
        ),
    )
    op.create_index(
        "ix_user_notif_prefs_user_id",
        "user_notification_prefs",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_notif_prefs_user_id", table_name="user_notification_prefs")
    op.drop_table("user_notification_prefs")

    op.execute("DROP POLICY IF EXISTS notifications_org_isolation ON notifications")
    op.drop_index("ix_notifications_user_unread", table_name="notifications")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_index("ix_notifications_org_id", table_name="notifications")
    op.drop_table("notifications")
