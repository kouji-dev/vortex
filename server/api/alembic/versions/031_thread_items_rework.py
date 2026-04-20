# server/api/alembic/versions/031_thread_items_rework.py
"""Thread items rework.

- Rename chat_conversations -> threads
- Rename chat_uploads.conversation_id -> thread_id
- Create thread_item_kind / thread_item_status / thread_item_role enums
- Create thread_items table with indexes and CHECK constraints
- Backfill thread_items from chat_messages (+ message_usage)
- Drop chat_messages, message_usage
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "031_thread_items_rework"
down_revision = "030_seed_default_policies"
branch_labels = None
depends_on = None


ITEM_KINDS = (
    "user_message", "assistant_text", "llm_call", "tool_call",
    "server_tool_use", "thinking", "citation", "memory_pill",
    "turn_end", "error",
)
ITEM_STATUSES = ("streaming", "done", "error", "cancelled")
ITEM_ROLES = ("user", "assistant", "system")


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Rename conversations table
    op.rename_table("chat_conversations", "threads")
    # Note: PK index is still named chat_sessions_pkey from the original table name.
    # Rename it to threads_pkey for consistency.
    op.execute("ALTER INDEX chat_sessions_pkey RENAME TO threads_pkey")

    # 2. Rename chat_uploads FK column
    op.alter_column("chat_uploads", "conversation_id", new_column_name="thread_id")
    # Rename stale FK constraint name to match new column name
    op.execute(
        "ALTER TABLE chat_uploads RENAME CONSTRAINT "
        "chat_uploads_conversation_id_fkey TO chat_uploads_thread_id_fkey"
    )

    # 3. Create enums
    op.execute(
        f"CREATE TYPE thread_item_kind AS ENUM "
        f"({', '.join(repr(k) for k in ITEM_KINDS)})"
    )
    op.execute(
        f"CREATE TYPE thread_item_status AS ENUM "
        f"({', '.join(repr(s) for s in ITEM_STATUSES)})"
    )
    op.execute(
        f"CREATE TYPE thread_item_role AS ENUM "
        f"({', '.join(repr(r) for r in ITEM_ROLES)})"
    )

    # 4. Create thread_items table
    op.create_table(
        "thread_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("thread_id", sa.BigInteger(), sa.ForeignKey("threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", postgresql.ENUM(*ITEM_KINDS, name="thread_item_kind", create_type=False), nullable=False),
        sa.Column("role", postgresql.ENUM(*ITEM_ROLES, name="thread_item_role", create_type=False), nullable=True),
        sa.Column("status", postgresql.ENUM(*ITEM_STATUSES, name="thread_item_status", create_type=False), nullable=False),
        sa.Column("provider", sa.String(64), nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("cost_estimated", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("data", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("parent_item_id", sa.BigInteger(), sa.ForeignKey("thread_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("clock_timestamp()"), nullable=False),
        sa.CheckConstraint(
            "(kind <> 'llm_call') OR (model IS NOT NULL AND data ? 'input_tokens' AND data ? 'output_tokens')",
            name="ck_thread_items_llm_call_shape",
        ),
        sa.CheckConstraint(
            "(kind <> 'tool_call') OR (data ? 'tool_name')",
            name="ck_thread_items_tool_call_shape",
        ),
        sa.CheckConstraint(
            "(kind <> 'user_message') OR (data ? 'text')",
            name="ck_thread_items_user_message_shape",
        ),
    )
    op.create_index("ix_thread_items_thread_created", "thread_items", ["thread_id", "created_at"])
    op.create_index("ix_thread_items_thread_turn", "thread_items", ["thread_id", "turn_id"])
    op.create_index("ix_thread_items_org_created", "thread_items", ["org_id", "created_at"])
    op.execute(
        "CREATE INDEX ix_thread_items_cost_not_null "
        "ON thread_items (org_id, created_at) "
        "WHERE cost_usd IS NOT NULL"
    )

    # 5. RLS policy (mirror threads)
    op.execute("ALTER TABLE thread_items ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY thread_items_org_isolation ON thread_items "
        "USING (org_id = current_setting('app.current_org_id', true)::uuid)"
    )

    # 6. Backfill
    from ai_portal.chat._backfill import run_backfill
    run_backfill(bind)

    # 7. Drop legacy tables — break circular FK then drop both
    op.execute(
        "ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS chat_messages_usage_id_fkey"
    )
    op.drop_table("message_usage")  # message_usage has FKs to chat_messages; drop it first now that chat_messages no longer references it
    op.drop_table("chat_messages")


def downgrade() -> None:
    raise RuntimeError("031_thread_items_rework is not reversible. Restore from backup.")
