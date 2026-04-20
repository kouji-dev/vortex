"""SQLAlchemy ORM models for the usage domain."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class UsageRollup(Base):
    __tablename__ = "usage_rollup"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    api_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_grain: Mapped[str] = mapped_column(String(16), nullable=False, default="day")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cached_input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False, default=Decimal("0"))
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class UsageQuota(Base):
    __tablename__ = "usage_quota"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    api_model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    period: Mapped[str] = mapped_column(String(8), nullable=False, default="month")
    max_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    max_input_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_output_tokens: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    action_on_breach: Mapped[str] = mapped_column(String(16), nullable=False, default="block")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
