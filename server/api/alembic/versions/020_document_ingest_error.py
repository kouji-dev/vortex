"""Add documents.ingest_error for failed ingest visibility

Revision ID: 020_document_ingest_error
Revises: 019_user_memories
Create Date: 2026-04-04
"""

import sqlalchemy as sa
from alembic import op

revision = "020_document_ingest_error"
down_revision = "019_user_memories"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ingest_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "ingest_error")
