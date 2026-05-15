# server/api/alembic/versions/036_threads_activity_index.py
"""Index threads on (org_id, last_message_at DESC NULLS LAST).

Supports both the consumption-page thread listing (filter by org +
last_message_at range, order DESC) and the chat sidebar (per-user list
ordered by activity recency). Without it both queries seq-scan threads.
"""

from __future__ import annotations

from alembic import op

revision = "036_threads_activity_index"
down_revision = "035_kb_search_shape_check"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_threads_org_last_message_at "
        "ON threads (org_id, last_message_at DESC NULLS LAST)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_threads_org_last_message_at")
