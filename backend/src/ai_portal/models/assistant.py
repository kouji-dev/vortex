from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_portal.db.base import Base


class Assistant(Base):
    __tablename__ = "assistants"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    owner_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AssistantAcl(Base):
    __tablename__ = "assistant_acl"
    __table_args__ = (
        UniqueConstraint("assistant_id", "user_id", name="uq_assistant_acl_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    assistant_id: Mapped[int] = mapped_column(
        ForeignKey("assistants.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
