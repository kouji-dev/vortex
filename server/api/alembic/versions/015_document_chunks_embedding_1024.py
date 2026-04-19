"""Resize document chunk embeddings to 1024 dims (Voyage default).

Revision ID: 015_emb_1024
Revises: 014_kb_connectors
Create Date: 2026-03-30

Existing vectors were 1536-d (OpenAI text-embedding-3-small). Voyage models
used by this app default to 1024 dimensions. All chunk rows are cleared and
``ready`` documents are marked ``failed`` so users re-upload or re-ingest.

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "015_emb_1024"
down_revision: str | None = "014_kb_connectors"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.text("DELETE FROM document_chunks"))
    op.execute(
        sa.text("UPDATE documents SET status = 'failed' WHERE status = 'ready'")
    )
    op.execute(
        sa.text(
            "ALTER TABLE document_chunks "
            "ALTER COLUMN embedding TYPE vector(1024)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM document_chunks"))
    op.execute(
        sa.text("UPDATE documents SET status = 'failed' WHERE status = 'ready'")
    )
    op.execute(
        sa.text(
            "ALTER TABLE document_chunks "
            "ALTER COLUMN embedding TYPE vector(1536)"
        )
    )
