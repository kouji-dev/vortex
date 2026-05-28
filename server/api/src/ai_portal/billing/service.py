"""BillingService — provider-agnostic persistence over a :class:`BillingProvider`.

Responsibilities:
- Look up / create a Subscription row for an org.
- Patch plan / seats / cancel — delegates to the provider, updates the row.
- List invoices.
- Apply incoming Stripe webhook events (subscription updates + invoice
  paid/finalized).
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.billing.model import InvoiceRow, SubscriptionRow
from ai_portal.billing.protocol import (
    BillingProvider,
    Plan,
    PlanKind,
    Subscription,
    SubscriptionStatus,
)

logger = logging.getLogger(__name__)


class BillingService:
    """Thin orchestrator. One instance per (db session, provider)."""

    def __init__(self, db: Session, provider: BillingProvider) -> None:
        self.db = db
        self.provider = provider

    # ── Read ────────────────────────────────────────────────────────────

    def get_subscription(self, *, org_id: _uuid.UUID) -> SubscriptionRow | None:
        stmt = (
            select(SubscriptionRow)
            .where(SubscriptionRow.org_id == org_id)
            .where(SubscriptionRow.provider == self.provider.name)
            .order_by(SubscriptionRow.created_at.desc())
            .limit(1)
        )
        return self.db.execute(stmt).scalars().first()

    def list_invoices(
        self,
        *,
        org_id: _uuid.UUID,
        limit: int = 50,
    ) -> list[InvoiceRow]:
        stmt = (
            select(InvoiceRow)
            .where(InvoiceRow.org_id == org_id)
            .order_by(InvoiceRow.created_at.desc())
            .limit(min(max(limit, 1), 200))
        )
        return list(self.db.execute(stmt).scalars().all())

    # ── Mutations ──────────────────────────────────────────────────────

    async def ensure_customer(
        self,
        *,
        org_id: _uuid.UUID,
        org_name: str,
        org_email: str | None = None,
    ) -> str:
        """Return existing customer_id or create one at the provider."""
        existing = self.get_subscription(org_id=org_id)
        if existing:
            return existing.customer_id
        return await self.provider.create_customer(
            org_id=str(org_id), name=org_name, email=org_email,
        )

    async def set_plan(
        self,
        *,
        org_id: _uuid.UUID,
        org_name: str,
        plan: Plan,
        seats: int = 1,
        org_email: str | None = None,
    ) -> SubscriptionRow:
        """Set / change the plan for ``org_id``.  Provider syncs subscription."""
        row = self.get_subscription(org_id=org_id)

        if row is None:
            customer_id = await self.provider.create_customer(
                org_id=str(org_id), name=org_name, email=org_email,
            )
        else:
            customer_id = row.customer_id

        result: Subscription = await self.provider.update_subscription(
            customer_id=customer_id, plan=plan, seats=seats,
        )

        now = datetime.now(UTC)
        if row is None:
            row = SubscriptionRow(
                org_id=org_id,
                provider=self.provider.name,
                customer_id=customer_id,
                external_id=result.id,
                plan_kind=plan.kind.value,
                plan_code=plan.code,
                status=result.status.value,
                currency=plan.currency,
                seats=seats,
                config_json={"unit_prices": plan.usage_unit_prices,
                             "seat_price_cents": plan.seat_price_cents,
                             "included_units": plan.included_units},
                current_period_start=result.current_period_start,
                current_period_end=result.current_period_end,
                created_at=now,
                updated_at=now,
            )
            self.db.add(row)
        else:
            row.external_id = result.id
            row.plan_kind = plan.kind.value
            row.plan_code = plan.code
            row.status = result.status.value
            row.currency = plan.currency
            row.seats = seats
            row.config_json = {
                "unit_prices": plan.usage_unit_prices,
                "seat_price_cents": plan.seat_price_cents,
                "included_units": plan.included_units,
            }
            row.current_period_start = result.current_period_start
            row.current_period_end = result.current_period_end
            row.updated_at = now
        self.db.flush()
        return row

    async def cancel(self, *, org_id: _uuid.UUID) -> SubscriptionRow:
        row = self.get_subscription(org_id=org_id)
        if row is None:
            raise NoSubscriptionForOrg(org_id)
        if row.external_id:
            await self.provider.void(subscription_id=row.external_id)
        row.status = SubscriptionStatus.canceled.value
        row.canceled_at = datetime.now(UTC)
        row.updated_at = row.canceled_at
        self.db.flush()
        return row

    # ── Webhook application ────────────────────────────────────────────

    def apply_webhook_event(self, event: dict) -> str:
        """Apply a verified Stripe event. Returns a short tag for logging."""
        etype = event.get("type", "")
        obj = (event.get("data") or {}).get("object") or {}

        if etype.startswith("customer.subscription."):
            return self._apply_subscription_event(etype, obj)
        if etype.startswith("invoice."):
            return self._apply_invoice_event(etype, obj)
        logger.info("billing.webhook ignored event=%s", etype)
        return "ignored"

    def _apply_subscription_event(self, etype: str, obj: dict) -> str:
        ext_id = obj.get("id")
        if not ext_id:
            return "no_subscription_id"
        row = self.db.execute(
            select(SubscriptionRow).where(SubscriptionRow.external_id == ext_id)
        ).scalar_one_or_none()
        if row is None:
            return "unknown_subscription"
        status = obj.get("status") or row.status
        # Map Stripe statuses onto our enum.
        row.status = _normalize_status(status)
        if etype == "customer.subscription.deleted":
            row.status = SubscriptionStatus.canceled.value
            row.canceled_at = datetime.now(UTC)
        cps = obj.get("current_period_start")
        cpe = obj.get("current_period_end")
        if cps:
            row.current_period_start = datetime.fromtimestamp(int(cps), tz=UTC)
        if cpe:
            row.current_period_end = datetime.fromtimestamp(int(cpe), tz=UTC)
        row.updated_at = datetime.now(UTC)
        self.db.flush()
        return "subscription_updated"

    def _apply_invoice_event(self, etype: str, obj: dict) -> str:
        ext_id = obj.get("id")
        if not ext_id:
            return "no_invoice_id"
        sub_ext_id = obj.get("subscription")
        sub_row = None
        if sub_ext_id:
            sub_row = self.db.execute(
                select(SubscriptionRow).where(
                    SubscriptionRow.external_id == sub_ext_id
                )
            ).scalar_one_or_none()

        existing = self.db.execute(
            select(InvoiceRow).where(InvoiceRow.external_id == ext_id)
        ).scalar_one_or_none()

        status_map = {
            "invoice.created": "open",
            "invoice.finalized": "open",
            "invoice.paid": "paid",
            "invoice.payment_succeeded": "paid",
            "invoice.payment_failed": "open",
            "invoice.voided": "void",
            "invoice.marked_uncollectible": "uncollectible",
        }
        status = status_map.get(etype, obj.get("status") or "open")
        amount = int(
            obj.get("amount_due")
            or obj.get("amount_paid")
            or obj.get("total")
            or 0
        )
        currency = obj.get("currency") or "usd"
        pdf_url = obj.get("invoice_pdf") or obj.get("hosted_invoice_url")

        if existing:
            existing.status = status
            existing.amount_cents = amount
            existing.currency = currency
            existing.pdf_url = pdf_url or existing.pdf_url
            if status == "paid":
                existing.paid_at = datetime.now(UTC)
            self.db.flush()
            return "invoice_updated"

        if sub_row is None:
            # Without a subscription row we have no org binding — drop.
            return "orphan_invoice"

        row = InvoiceRow(
            org_id=sub_row.org_id,
            subscription_id=sub_row.id,
            external_id=ext_id,
            amount_cents=amount,
            currency=currency,
            status=status,
            pdf_url=pdf_url,
            issued_at=datetime.now(UTC),
            paid_at=datetime.now(UTC) if status == "paid" else None,
        )
        self.db.add(row)
        self.db.flush()
        return "invoice_created"


# ── Errors / helpers ────────────────────────────────────────────────────────


class NoSubscriptionForOrg(Exception):
    def __init__(self, org_id: _uuid.UUID) -> None:
        super().__init__(f"no subscription for org {org_id}")
        self.org_id = org_id


_STATUS_NORMALIZE = {
    "trialing": "trialing",
    "active": "active",
    "past_due": "past_due",
    "canceled": "canceled",
    "unpaid": "past_due",
    "incomplete": "incomplete",
    "incomplete_expired": "canceled",
}


def _normalize_status(raw: str) -> str:
    return _STATUS_NORMALIZE.get(raw, raw or "incomplete")


# ── Plan helpers exposed for routes ─────────────────────────────────────────


_BUILTIN_PLANS: dict[str, Plan] = {
    "free": Plan(code="free", kind=PlanKind.usage),
    "pro-seat": Plan(
        code="pro-seat", kind=PlanKind.seat, seat_price_cents=2000,
    ),
    "team-hybrid": Plan(
        code="team-hybrid",
        kind=PlanKind.hybrid,
        seat_price_cents=1500,
        usage_unit_prices={
            "tokens_in": 1,
            "tokens_out": 3,
            "embeddings": 1,
        },
        included_units={
            "tokens_in": 1_000_000,
            "tokens_out": 250_000,
            "embeddings": 500_000,
        },
    ),
    "enterprise-usage": Plan(
        code="enterprise-usage",
        kind=PlanKind.usage,
        usage_unit_prices={
            "tokens_in": 1,
            "tokens_out": 3,
            "embeddings": 1,
            "documents_ingested": 50,
        },
    ),
}


def get_plan(code: str) -> Plan:
    plan = _BUILTIN_PLANS.get(code)
    if plan is None:
        raise UnknownPlan(code)
    return plan


class UnknownPlan(Exception):
    pass
