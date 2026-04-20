# server/api/src/ai_portal/chat/model.py
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.chat.item_kinds import ItemKind, ItemRole, ItemStatus
from ai_portal.chat.schemas import ConversationSettings
from ai_portal.core.db.base import Base
from ai_portal.core.db.types import ConversationSettingsJSON


_item_kind_enum = PGEnum(
    ItemKind, name="thread_item_kind", create_type=False, values_callable=lambda e: [v.value for v in e]
)
_item_status_enum = PGEnum(
    ItemStatus, name="thread_item_status", create_type=False, values_callable=lambda e: [v.value for v in e]
)
_item_role_enum = PGEnum(
    ItemRole, name="thread_item_role", create_type=False, values_callable=lambda e: [v.value for v in e]
)


class Thread(Base):
    __tablename__ = "threads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    assistant_id: Mapped[int | None] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    settings: Mapped[ConversationSettings | None] = mapped_column(
        ConversationSettingsJSON, nullable=True
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ThreadItem(Base):
    __tablename__ = "thread_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    org_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    kind: Mapped[ItemKind] = mapped_column(_item_kind_enum, nullable=False)
    role: Mapped[ItemRole | None] = mapped_column(_item_role_enum, nullable=True)
    status: Mapped[ItemStatus] = mapped_column(_item_status_enum, nullable=False)

    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)

    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    cost_estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    parent_item_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("thread_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("clock_timestamp()"),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_thread_items_thread_created", "thread_id", "created_at"),
        Index("ix_thread_items_thread_turn", "thread_id", "turn_id"),
        Index("ix_thread_items_org_created", "org_id", "created_at"),
        Index(
            "ix_thread_items_cost_not_null",
            "org_id",
            "created_at",
            postgresql_where=text("cost_usd IS NOT NULL"),
        ),
        CheckConstraint(
            "(kind <> 'llm_call') OR (model IS NOT NULL AND data ? 'input_tokens' AND data ? 'output_tokens')",
            name="ck_thread_items_llm_call_shape",
        ),
        CheckConstraint(
            "(kind <> 'tool_call') OR (data ? 'tool_name')",
            name="ck_thread_items_tool_call_shape",
        ),
        CheckConstraint(
            "(kind <> 'user_message') OR (data ? 'text')",
            name="ck_thread_items_user_message_shape",
        ),
    )


class ChatUpload(Base):
    __tablename__ = "chat_uploads"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(Text, nullable=False)
    stored_path: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    content_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
