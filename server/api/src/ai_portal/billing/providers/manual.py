"""Manual billing provider — no external integration.

Use for self-hosted deployments that handle invoicing out-of-band (PO,
bank transfer, manual Stripe Dashboard work). All operations succeed
locally; ``report_usage`` and invoices are persisted via the platform's
own tables / logged to the application logger.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from ai_portal.billing.protocol import (
    BillingProvider,
    Plan,
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


def _mint(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(10)}"


class ManualBillingProvider(BillingProvider):
    """No-op billing provider — used when no external billing system is wired."""

    name = "manual"

    def __init__(self) -> None:
        # In-memory log so tests can assert what would have been billed.
        self.usage_log: list[dict[str, object]] = []
        self.invoices_log: list[dict[str, object]] = []

    async def create_customer(
        self,
        *,
        org_id: str,
        name: str,
        email: str | None = None,
    ) -> str:
        customer_id = _mint("cus_manual")
        logger.info(
            "manual-billing.create_customer org=%s name=%s email=%s -> %s",
            org_id, name, email, customer_id,
        )
        return customer_id

    async def update_subscription(
        self,
        *,
        customer_id: str,
        plan: Plan,
        seats: int = 1,
    ) -> Subscription:
        sub_id = _mint("sub_manual")
        logger.info(
            "manual-billing.update_subscription customer=%s plan=%s seats=%d",
            customer_id, plan.code, seats,
        )
        return Subscription(
            id=sub_id,
            customer_id=customer_id,
            plan_code=plan.code,
            status=SubscriptionStatus.active,
            seats=seats,
        )

    async def report_usage(
        self,
        *,
        customer_id: str,
        unit: str,
        quantity: int,
        ts: datetime,
    ) -> None:
        entry = {
            "customer_id": customer_id,
            "unit": unit,
            "quantity": int(quantity),
            "ts": ts.isoformat(),
        }
        self.usage_log.append(entry)
        logger.info("manual-billing.report_usage %s", entry)

    async def void(self, *, subscription_id: str) -> None:
        logger.info("manual-billing.void subscription=%s", subscription_id)

    # ── Manual-only helper: pretend-print an invoice (used by tests / docs) ─

    def print_invoice(
        self,
        *,
        subscription_id: str,
        amount_cents: int,
        currency: str = "usd",
        memo: str | None = None,
    ) -> str:
        invoice_id = _mint("in_manual")
        record = {
            "id": invoice_id,
            "subscription_id": subscription_id,
            "amount_cents": int(amount_cents),
            "currency": currency,
            "memo": memo,
            "issued_at": datetime.now(UTC).isoformat(),
        }
        self.invoices_log.append(record)
        logger.info(
            "manual-billing.print_invoice id=%s sub=%s amount=%s %s",
            invoice_id, subscription_id, amount_cents, currency.upper(),
        )
        return invoice_id
