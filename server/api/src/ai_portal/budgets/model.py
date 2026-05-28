"""Quotas + budgets + budget_alerts ORM models."""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base


class Quota(Base):
    """Hard cap per unit per period. Scoped by org/user/api_key/team."""

    __tablename__ = "quotas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="month")
    max_qty: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    action_on_breach: Mapped[str] = mapped_column(String(16), nullable=False, default="block")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Budget(Base):
    """USD-denominated budget. Soft warnings at warn_at_pcts, hard cutoff at 100%."""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    scope_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    scope_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    limit_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    period: Mapped[str] = mapped_column(String(16), nullable=False, default="month")
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    warn_at_pcts: Mapped[list[int]] = mapped_column(JSONB, nullable=False, default=lambda: [50, 80, 100])
    hard_cutoff: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    grace_extension_usd: Mapped[Decimal | None] = mapped_column(Numeric(14, 6), nullable=True)
    grace_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_on_threshold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BudgetAlert(Base):
    """One row per (budget, period, threshold_pct) — used to dedupe warning fires."""

    __tablename__ = "budget_alerts"
    __table_args__ = (
        UniqueConstraint(
            "budget_id", "period_start", "threshold_pct",
            name="uq_budget_alerts_period_threshold",
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("orgs.id", ondelete="CASCADE"), nullable=False
    )
    budget_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("budgets.id", ondelete="CASCADE"), nullable=False
    )
    threshold_pct: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_usd: Mapped[Decimal] = mapped_column(Numeric(14, 6), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
