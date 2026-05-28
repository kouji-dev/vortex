# server/api/alembic/versions/035_kb_search_shape_check.py
"""Shape check for thread_items where kind='kb_search'.

Splits from 034 because Postgres rejects referencing a newly-added enum
value inside the same transaction it was added in.

Payload contract enforced:
    data = {
        "tool_name": "search_knowledge_base",
        "query": str,
        "kb_ids": [int, ...],
        "chunks": [
            {"document_id", "document_name", "kb_id", "kb_name", "score", "snippet"},
            ...
        ],
        "result_snippet": str | null,
    }
"""

from __future__ import annotations

from alembic import op

revision = "035_kb_search_shape_check"
down_revision = "034_kb_search_thread_item_kind"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # New enum values from 034 must be COMMITted before they can be referenced
    # in a CHECK constraint. Alembic wraps the upgrade chain in a single
    # transaction by default, so we explicitly commit here before adding the
    # constraint that uses the new 'kb_search' enum value.
    op.execute("COMMIT")
    op.execute(
        """
        ALTER TABLE thread_items ADD CONSTRAINT ck_thread_items_kb_search_shape
        CHECK (
            kind <> 'kb_search'
            OR (data ? 'tool_name' AND data ? 'query' AND data ? 'kb_ids')
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE thread_items DROP CONSTRAINT IF EXISTS ck_thread_items_kb_search_shape"
    )
