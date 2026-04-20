# server/api/alembic/versions/032_dev_user_admin_role.py
"""Upgrade dev@localhost role to owner so admin endpoints work in dev mode."""

from __future__ import annotations

from alembic import op

revision = "032_dev_user_admin_role"
down_revision = "031_thread_items_rework"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE users SET role = 'owner' WHERE email = 'dev@localhost' AND role = 'member'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE users SET role = 'member' WHERE email = 'dev@localhost' AND role = 'owner'"
    )
