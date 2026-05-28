"""Pydantic schemas for the budgets/quotas domain."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class QuotaCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scope_kind: str = Field(pattern=r"^(org|user|api_key|team)$")
    scope_id: str | None = None
    unit: str
    period: str = Field(default="month", pattern=r"^(day|month|custom)$")
    max_qty: Decimal
    action_on_breach: str = Field(default="block", pattern=r"^(block|warn|allow)$")


class QuotaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scope_kind: str
    scope_id: str | None
    unit: str
    period: str
    max_qty: Decimal
    action_on_breach: str
    disabled_at: datetime | None


class BudgetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    scope_kind: str = Field(pattern=r"^(org|user|api_key|team)$")
    scope_id: str | None = None
    limit_usd: Decimal = Field(gt=Decimal("0"))
    period: str = Field(default="month", pattern=r"^(day|month|custom)$")
    period_start: datetime | None = None
    period_end: datetime | None = None
    warn_at_pcts: list[int] = Field(default_factory=lambda: [50, 80, 100])
    hard_cutoff: bool = True
    webhook_on_threshold: bool = True


class BudgetGraceExtend(BaseModel):
    grace_extension_usd: Decimal = Field(gt=Decimal("0"))
    grace_expires_at: datetime


class BudgetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scope_kind: str
    scope_id: str | None
    limit_usd: Decimal
    period: str
    period_start: datetime | None
    period_end: datetime | None
    warn_at_pcts: list[int]
    hard_cutoff: bool
    grace_extension_usd: Decimal | None
    grace_expires_at: datetime | None
    webhook_on_threshold: bool
    disabled_at: datetime | None


class BudgetStatus(BaseModel):
    budget_id: int
    period_start: datetime
    period_end: datetime
    spent_usd: Decimal
    limit_usd: Decimal
    effective_limit_usd: Decimal
    used_pct: float
    blocked: bool
    grace_active: bool
