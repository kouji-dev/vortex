"""BillingProvider protocol — uniform surface across billing back-ends.

Implementations:
- ``providers.manual.ManualBillingProvider`` — no-op, prints invoices.
- ``providers.stripe.StripeBillingProvider`` — Stripe API.

Plans come in three shapes (``PlanKind``):
- ``seat``   — fixed price per user/month
- ``usage``  — overage billed on metered units
- ``hybrid`` — seat base + usage overage
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


class PlanKind(enum.StrEnum):
    seat = "seat"
    usage = "usage"
    hybrid = "hybrid"


class SubscriptionStatus(enum.StrEnum):
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    incomplete = "incomplete"


class InvoiceStatus(enum.StrEnum):
    draft = "draft"
    open = "open"
    paid = "paid"
    void = "void"
    uncollectible = "uncollectible"


@dataclass(frozen=True, slots=True)
class Plan:
    """Plan definition. ``code`` is provider-agnostic; providers map it.

    - ``seat_price_cents`` per user/month (seat + hybrid plans)
    - ``usage_unit_prices`` cents per metered unit (usage + hybrid plans)
    """

    code: str
    kind: PlanKind
    currency: str = "usd"
    seat_price_cents: int = 0
    usage_unit_prices: dict[str, int] = field(default_factory=dict)
    included_units: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Subscription:
    """Result of ``update_subscription``."""

    id: str
    customer_id: str
    plan_code: str
    status: SubscriptionStatus
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    seats: int = 1


@dataclass(frozen=True, slots=True)
class Invoice:
    """Invoice record exposed to callers / persisted in the ``invoices`` table."""

    id: str
    subscription_id: str
    amount_cents: int
    currency: str
    status: InvoiceStatus
    pdf_url: str | None = None
    due_at: datetime | None = None
    issued_at: datetime | None = None


class BillingProviderError(Exception):
    """Base class for billing-provider failures."""


class UnknownCustomer(BillingProviderError):
    """Customer id not found at the provider."""


@runtime_checkable
class BillingProvider(Protocol):
    """Uniform contract for billing back-ends.

    Implementations MUST be safe to call from async handlers. Sync SDKs
    (e.g. ``stripe-python``) should be wrapped with ``asyncio.to_thread``.
    """

    name: str

    async def create_customer(
        self,
        *,
        org_id: str,
        name: str,
        email: str | None = None,
    ) -> str:
        """Provision a customer record. Returns the provider-side customer id."""

    async def update_subscription(
        self,
        *,
        customer_id: str,
        plan: Plan,
        seats: int = 1,
    ) -> Subscription:
        """Create or update a subscription for ``customer_id``."""

    async def report_usage(
        self,
        *,
        customer_id: str,
        unit: str,
        quantity: int,
        ts: datetime,
    ) -> None:
        """Push a metered-usage record. Idempotent on (customer, unit, ts)."""

    async def void(self, *, subscription_id: str) -> None:
        """Cancel / void a subscription. Idempotent."""
