"""SQLAlchemy ORM model for retention_policy."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class RetentionPolicy(Base):
    __tablename__ = "retention_policy"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False, unique=True)
    conversation_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audit_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)
    usage_retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=2555)
    upload_retention_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
