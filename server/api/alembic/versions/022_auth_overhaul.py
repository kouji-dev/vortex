"""Auth overhaul: create orgs table, extend users with uuid/org_id/role/auth flags

Revision ID: 022_auth_overhaul
Revises: 021_user_mem_is_system
Create Date: 2026-04-05
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "022_auth_overhaul"
down_revision = "021_user_mem_is_system"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Create orgs table
    op.create_table(
        "orgs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("instance_mode", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # 2. Insert default org for existing data
    op.execute(
        "INSERT INTO orgs (id, slug, name) VALUES (gen_random_uuid(), 'default', 'Default Org')"
    )

    # 3. Add new columns to users
    op.add_column("users", sa.Column(
        "uuid", UUID(as_uuid=True),
        nullable=True,  # nullable during migration; backfilled below
    ))
    op.add_column("users", sa.Column(
        "org_id", UUID(as_uuid=True), nullable=True
    ))
    op.add_column("users", sa.Column(
        "role", sa.String(16), nullable=False, server_default="member"
    ))
    op.add_column("users", sa.Column(
        "is_active", sa.Boolean(), nullable=False, server_default="true"
    ))
    op.add_column("users", sa.Column(
        "is_verified", sa.Boolean(), nullable=False, server_default="false"
    ))
    op.add_column("users", sa.Column(
        "is_superuser", sa.Boolean(), nullable=False, server_default="false"
    ))

    # 4. Backfill: give every existing user a UUID and assign to default org
    op.execute("UPDATE users SET uuid = gen_random_uuid()")
    op.execute("UPDATE users SET org_id = (SELECT id FROM orgs WHERE slug = 'default')")

    # 5. Make uuid NOT NULL + unique now that it's backfilled
    op.alter_column("users", "uuid", nullable=False)
    op.create_unique_constraint("uq_users_uuid", "users", ["uuid"])

    # 6. Add FK from users.org_id -> orgs.id
    op.create_foreign_key("fk_users_org_id", "users", "orgs", ["org_id"], ["id"])
    op.create_index("ix_users_org_id", "users", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_users_org_id", "users")
    op.drop_constraint("fk_users_org_id", "users", type_="foreignkey")
    op.drop_constraint("uq_users_uuid", "users", type_="unique")
    op.drop_column("users", "is_superuser")
    op.drop_column("users", "is_verified")
    op.drop_column("users", "is_active")
    op.drop_column("users", "role")
    op.drop_column("users", "org_id")
    op.drop_column("users", "uuid")
    op.drop_table("orgs")
