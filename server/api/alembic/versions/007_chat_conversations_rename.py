"""Rename chat_sessions → chat_conversations; session_id → conversation_id; nullable assistant.

Revision ID: 007_conv_rename
Revises: 006_drop_roles
Create Date: 2026-03-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "007_conv_rename"
down_revision: Union[str, None] = "006_drop_roles"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "chat_messages_session_id_fkey", "chat_messages", type_="foreignkey"
    )
    op.drop_index(op.f("ix_chat_messages_session_id"), table_name="chat_messages")

    op.alter_column(
        "chat_sessions",
        "assistant_id",
        existing_type=sa.Integer(),
        nullable=True,
    )

    op.rename_table("chat_sessions", "chat_conversations")

    op.add_column(
        "chat_conversations",
        sa.Column("title", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "chat_conversations",
        sa.Column("model", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "chat_conversations",
        sa.Column("settings", JSONB(), nullable=True),
    )

    op.execute(sa.text("ALTER TABLE chat_messages RENAME COLUMN session_id TO conversation_id"))

    op.create_index(
        op.f("ix_chat_messages_conversation_id"),
        "chat_messages",
        ["conversation_id"],
        unique=False,
    )
    op.create_foreign_key(
        "chat_messages_conversation_id_fkey",
        "chat_messages",
        "chat_conversations",
        ["conversation_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "chat_messages_conversation_id_fkey", "chat_messages", type_="foreignkey"
    )
    op.drop_index(op.f("ix_chat_messages_conversation_id"), table_name="chat_messages")

    op.execute(sa.text("ALTER TABLE chat_messages RENAME COLUMN conversation_id TO session_id"))

    op.drop_column("chat_conversations", "settings")
    op.drop_column("chat_conversations", "model")
    op.drop_column("chat_conversations", "title")

    op.rename_table("chat_conversations", "chat_sessions")

    op.alter_column(
        "chat_sessions",
        "assistant_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.create_index(
        op.f("ix_chat_messages_session_id"),
        "chat_messages",
        ["session_id"],
        unique=False,
    )
    op.create_foreign_key(
        "chat_messages_session_id_fkey",
        "chat_messages",
        "chat_sessions",
        ["session_id"],
        ["id"],
        ondelete="CASCADE",
    )
