"""Knowledge bases; documents owned by KB; conversation ↔ KB links.

Revision ID: 013_kb_conv
Revises: 012_rm_example_locked
Create Date: 2026-03-25

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision: str = "013_kb_conv"
down_revision: str | None = "012_rm_example_locked"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_knowledge_bases_owner_user_id"),
        "knowledge_bases",
        ["owner_user_id"],
        unique=False,
    )

    op.create_table(
        "conversation_knowledge_bases",
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["chat_conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["knowledge_bases.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("conversation_id", "knowledge_base_id"),
    )

    op.add_column(
        "documents",
        sa.Column("knowledge_base_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_documents_knowledge_base_id",
        "documents",
        "knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_documents_knowledge_base_id"),
        "documents",
        ["knowledge_base_id"],
        unique=False,
    )

    conn = op.get_bind()

    assistants_with_docs = conn.execute(
        text("SELECT DISTINCT assistant_id FROM documents")
    ).fetchall()
    for (assistant_id,) in assistants_with_docs:
        owner_row = conn.execute(
            text("SELECT owner_user_id FROM assistants WHERE id = :aid"),
            {"aid": assistant_id},
        ).fetchone()
        if owner_row is None:
            continue
        owner_user_id = owner_row[0]
        kb_id = conn.execute(
            text(
                "INSERT INTO knowledge_bases (name, description, owner_user_id) "
                "VALUES (:name, '', :uid) RETURNING id"
            ),
            {
                "name": f"Migrated corpus (assistant {assistant_id})",
                "uid": owner_user_id,
            },
        ).scalar_one()
        conn.execute(
            text(
                "UPDATE documents SET knowledge_base_id = :kb "
                "WHERE assistant_id = :aid"
            ),
            {"kb": kb_id, "aid": assistant_id},
        )
        conn.execute(
            text(
                "INSERT INTO conversation_knowledge_bases "
                "(conversation_id, knowledge_base_id) "
                "SELECT id, :kb FROM chat_conversations WHERE assistant_id = :aid "
                "ON CONFLICT DO NOTHING"
            ),
            {"kb": kb_id, "aid": assistant_id},
        )

    op.alter_column("documents", "knowledge_base_id", nullable=False)

    op.drop_index(op.f("ix_documents_assistant_id"), table_name="documents")
    op.drop_constraint("documents_assistant_id_fkey", "documents", type_="foreignkey")
    op.drop_column("documents", "assistant_id")


def downgrade() -> None:
    raise NotImplementedError(
        "013_kb_conv downgrade would lose assistant_id mapping; restore from backup instead."
    )
