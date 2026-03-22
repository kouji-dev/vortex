"""Core catalog: users, roles, assistants, ACL.

Revision ID: 002_core_catalog
Revises: 001
Create Date: 2026-03-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002_core_catalog"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)

    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=False)

    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role_id"),
        sa.UniqueConstraint("user_id", "role_id", name="uq_user_role"),
    )

    op.create_table(
        "assistants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("system_prompt", sa.Text(), server_default="", nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "assistant_acl",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("assistant_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["assistant_id"],
            ["assistants.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assistant_id", "user_id", name="uq_assistant_acl_user"),
    )
    op.create_index(
        op.f("ix_assistant_acl_assistant_id"), "assistant_acl", ["assistant_id"], unique=False
    )
    op.create_index(
        op.f("ix_assistant_acl_user_id"), "assistant_acl", ["user_id"], unique=False
    )

    op.execute(
        sa.text(
            "INSERT INTO roles (name) VALUES ('admin'), ('member') ON CONFLICT (name) DO NOTHING"
        )
    )
    # roles need unique on name - ON CONFLICT requires constraint. We have unique on name.
    op.execute(
        sa.text(
            "INSERT INTO users (email) VALUES ('dev@localhost') ON CONFLICT (email) DO NOTHING"
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_roles (user_id, role_id)
            SELECT u.id, r.id FROM users u, roles r
            WHERE u.email = 'dev@localhost' AND r.name = 'member'
            ON CONFLICT (user_id, role_id) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_assistant_acl_user_id"), table_name="assistant_acl")
    op.drop_index(op.f("ix_assistant_acl_assistant_id"), table_name="assistant_acl")
    op.drop_table("assistant_acl")
    op.drop_table("assistants")
    op.drop_table("user_roles")
    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_table("roles")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
