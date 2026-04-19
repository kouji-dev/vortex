"""Enforce chat_conversations.settings is a JSON object (or null).

Revision ID: 008_settings_object
Revises: 007_conv_rename
Create Date: 2026-03-22

"""

from typing import Sequence, Union

from alembic import op

revision: str = "008_settings_object"
down_revision: Union[str, None] = "007_conv_rename"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_chat_conversations_settings_is_object",
        "chat_conversations",
        "settings IS NULL OR jsonb_typeof(settings) = 'object'",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_chat_conversations_settings_is_object",
        "chat_conversations",
        type_="check",
    )
