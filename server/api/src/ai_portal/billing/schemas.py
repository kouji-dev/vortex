"""Pydantic schemas for the billing HTTP surface."""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# ── Subscriptions ───────────────────────────────────────────────────────────


class SubscriptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    provider: str
    customer_id: str
    external_id: str | None
    plan_kind: str
    plan_code: str
    status: str
    currency: str
    seats: int
    current_period_start: datetime | None
    current_period_end: datetime | None
    canceled_at: datetime | None


class SubscriptionPatch(BaseModel):
    """Patch a subscription's plan / seats. Triggers provider sync."""

    plan_code: str | None = Field(default=None, max_length=64)
    seats: int | None = Field(default=None, ge=1, le=10_000)
    cancel: bool = False


# ── Invoices ────────────────────────────────────────────────────────────────


class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: _uuid.UUID
    org_id: _uuid.UUID
    subscription_id: _uuid.UUID | None
    external_id: str | None
    amount_cents: int
    currency: str
    status: str
    pdf_url: str | None
    memo: str | None
    issued_at: datetime | None
    due_at: datetime | None
    paid_at: datetime | None


class InvoiceList(BaseModel):
    items: list[InvoiceOut]
    next_cursor: str | None = None
