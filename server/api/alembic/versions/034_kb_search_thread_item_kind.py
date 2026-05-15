# server/api/alembic/versions/034_kb_search_thread_item_kind.py
"""Add `kb_search` to the thread_item_kind enum.

Constraint that references this enum value lives in the follow-up migration
(035) because Postgres forbids using a newly-added enum value in the same
transaction it was added in ("unsafe use of new value").
"""

from __future__ import annotations

from alembic import op

revision = "034_kb_search_thread_item_kind"
down_revision = "033_fix_thread_items_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside a transaction in Postgres.
    op.execute("COMMIT")
    op.execute(
        "ALTER TYPE thread_item_kind ADD VALUE IF NOT EXISTS 'kb_search'"
    )


def downgrade() -> None:
    # Postgres doesn't support removing enum values. Downgrade is a no-op;
    # to roll back fully you'd need to dump/restore a new enum without the
    # value (after migrating any rows away from kind='kb_search').
    pass
