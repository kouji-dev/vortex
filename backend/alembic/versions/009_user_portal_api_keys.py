"""User-issued portal API keys (agents, CLI tools).

Revision ID: 009_portal_api_keys
Revises: 008_settings_object
Create Date: 2026-03-22

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_portal_api_keys"
down_revision: str | None = "008_settings_object"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_portal_api_keys",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("key_prefix", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_hash", name="uq_user_portal_api_keys_key_hash"),
    )
    op.create_index(
        "ix_user_portal_api_keys_user_id",
        "user_portal_api_keys",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_portal_api_keys_user_id", table_name="user_portal_api_keys")
    op.drop_table("user_portal_api_keys")
