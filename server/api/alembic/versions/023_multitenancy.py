"""Add org_id to all tenant-scoped tables

Revision ID: 023_multitenancy
Revises: 022_auth_overhaul
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "023_multitenancy"
down_revision = "022_auth_overhaul"
branch_labels = None
depends_on = None

TABLES = [
    "assistants",
    "chat_conversations",
    "knowledge_bases",
    "user_memories",
    "catalog_models",
    "user_portal_api_keys",
]


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("org_id", UUID(as_uuid=True), nullable=True),
        )
        # Backfill from users table via the existing user FK
        # Each table has either owner_user_id or user_id referencing users.id
        if table in ("assistants", "knowledge_bases"):
            user_col = "owner_user_id"
        elif table == "catalog_models":
            user_col = None  # no user FK
        else:
            user_col = "user_id"

        if user_col is None:
            # catalog_models: assign to default org directly
            op.execute(
                f"UPDATE {table} SET org_id = (SELECT id FROM orgs WHERE slug = 'default')"
            )
        else:
            op.execute(
                f"UPDATE {table} SET org_id = ("
                f"  SELECT org_id FROM users WHERE users.id = {table}.{user_col}"
                f")"
            )

        # Make NOT NULL after backfill
        op.alter_column(table, "org_id", nullable=False)
        op.create_foreign_key(
            f"fk_{table}_org_id", table, "orgs", ["org_id"], ["id"]
        )
        op.create_index(f"ix_{table}_org_id", table, ["org_id"])


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(f"ix_{table}_org_id", table)
        op.drop_constraint(f"fk_{table}_org_id", table, type_="foreignkey")
        op.drop_column(table, "org_id")
