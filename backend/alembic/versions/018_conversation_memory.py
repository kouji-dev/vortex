"""Add summary and last_message_at to chat_conversations

Revision ID: 018_conversation_memory
Revises: 017_ingest_progress_tsvector
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "018_conversation_memory"
down_revision = "017_ingest_progress_tsvector"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("chat_conversations", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "chat_conversations",
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_conversations", "last_message_at")
    op.drop_column("chat_conversations", "summary")
