"""Billing domain — subscription + invoice management.

Bundled providers (under ``providers/``):
- :mod:`manual` — no-op: prints invoice, no external integration.
- :mod:`stripe` — Stripe API via ``stripe-python``.

The :class:`BillingProvider` protocol is the only stable surface. Services
depend on the protocol, not on a concrete provider.
"""

from ai_portal.billing.protocol import (
    BillingProvider,
    Invoice,
    InvoiceStatus,
    Plan,
    PlanKind,
    Subscription,
    SubscriptionStatus,
)

__all__ = [
    "BillingProvider",
    "Invoice",
    "InvoiceStatus",
    "Plan",
    "PlanKind",
    "Subscription",
    "SubscriptionStatus",
]
