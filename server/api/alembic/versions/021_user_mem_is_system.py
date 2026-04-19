"""Add is_system flag on user_memories (one profile row per user)

Revision ID: 021_user_mem_is_system
Revises: 020_document_ingest_error
Create Date: 2026-04-04
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "021_user_mem_is_system"
down_revision = "020_document_ingest_error"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove junction table if a previous draft of this revision was applied.
    op.execute("DROP TABLE IF EXISTS conversation_memories")

    op.add_column(
        "user_memories",
        sa.Column(
            "is_system",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    conn = op.get_bind()

    # Legacy rows created with source='system' (if any) become the flagged profile row.
    conn.execute(
        sa.text("UPDATE user_memories SET is_system = true WHERE source = 'system'")
    )

    # Drop auto-derived rows for users who already have a system profile row.
    conn.execute(
        sa.text("""
            DELETE FROM user_memories AS um
            WHERE um.source = 'auto' AND um.is_system IS NOT TRUE
              AND EXISTS (
                SELECT 1 FROM user_memories s
                WHERE s.user_id = um.user_id AND s.is_system IS TRUE
              )
        """)
    )

    # Merge remaining legacy ``auto`` rows into one profile per user.
    conn.execute(
        sa.text("""
            INSERT INTO user_memories (user_id, content, source, is_active, is_system)
            SELECT user_id, string_agg(content, E'\n' ORDER BY id), 'auto', true, true
            FROM user_memories
            WHERE source = 'auto' AND is_active IS TRUE AND is_system IS NOT TRUE
            GROUP BY user_id
        """)
    )

    conn.execute(
        sa.text("""
            DELETE FROM user_memories
            WHERE source = 'auto' AND is_system IS NOT TRUE
        """)
    )

    conn.execute(
        sa.text("""
            UPDATE user_memories SET source = 'auto' WHERE is_system IS TRUE AND source = 'system'
        """)
    )

    op.execute(
        """
        CREATE UNIQUE INDEX uq_user_memories_one_system_per_user
        ON user_memories (user_id)
        WHERE is_system IS TRUE
        """
    )

    op.alter_column(
        "user_memories",
        "is_system",
        server_default=None,
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_user_memories_one_system_per_user")
    op.drop_column("user_memories", "is_system")
