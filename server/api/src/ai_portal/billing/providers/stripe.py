"""Stripe billing provider — wraps the stripe-python SDK.

Maps the :class:`BillingProvider` protocol onto Stripe primitives:

- ``create_customer``      -> ``stripe.Customer.create``
- ``update_subscription``  -> ``stripe.Subscription.create`` /
                              ``stripe.Subscription.modify``
- ``report_usage``         -> ``stripe.SubscriptionItem.create_usage_record``
- ``void``                 -> ``stripe.Subscription.cancel``

The SDK is sync; calls are dispatched through :func:`asyncio.to_thread` so
they don't block the FastAPI event loop.

Plan -> Price mapping
----------------------
A Stripe ``Price`` id is required for every billable line.  Pass them via
:class:`StripePlanPriceMap`:

- ``seat_price_id``        — the recurring price for the seat line.
- ``usage_price_ids``      — dict mapping metered ``unit`` -> price id.

The provider looks the plan up by ``plan.code`` in the price-map dict you
pass to the constructor.
"""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime

import stripe

from ai_portal.billing.protocol import (
    BillingProvider,
    BillingProviderError,
    Plan,
    Subscription,
    SubscriptionStatus,
    UnknownCustomer,
)

logger = logging.getLogger(__name__)


# ── Plan -> Stripe price mapping ────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class StripePlanPriceMap:
    """Stripe Price ids backing a single :class:`Plan` code."""

    seat_price_id: str | None = None
    usage_price_ids: dict[str, str] = field(default_factory=dict)


# ── Status mapping ───────────────────────────────────────────────────────────


_STATUS_MAP = {
    "trialing": SubscriptionStatus.trialing,
    "active": SubscriptionStatus.active,
    "past_due": SubscriptionStatus.past_due,
    "canceled": SubscriptionStatus.canceled,
    "unpaid": SubscriptionStatus.past_due,
    "incomplete": SubscriptionStatus.incomplete,
    "incomplete_expired": SubscriptionStatus.canceled,
}


def _map_status(raw: str | None) -> SubscriptionStatus:
    return _STATUS_MAP.get(raw or "", SubscriptionStatus.incomplete)


def _ts(epoch: int | None) -> datetime | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(int(epoch), tz=UTC)


# ── Provider ─────────────────────────────────────────────────────────────────


class StripeBillingProvider(BillingProvider):
    """Stripe-backed billing provider."""

    name = "stripe"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        plan_prices: dict[str, StripePlanPriceMap] | None = None,
        webhook_secret: str | None = None,
        client: object | None = None,
    ) -> None:
        self.api_key = api_key or os.environ.get("STRIPE_API_KEY") or ""
        self.plan_prices = dict(plan_prices or {})
        self.webhook_secret = webhook_secret or os.environ.get(
            "STRIPE_WEBHOOK_SECRET"
        )
        # Injected client used by tests. When unset, the global ``stripe``
        # module is used directly (its sub-modules read ``stripe.api_key``).
        self._client = client
        if self.api_key and not client:
            stripe.api_key = self.api_key

    # ── Internal helpers ────────────────────────────────────────────────

    def _stripe(self):  # type: ignore[no-untyped-def]
        return self._client if self._client is not None else stripe

    def _prices_for(self, plan: Plan) -> StripePlanPriceMap:
        mapping = self.plan_prices.get(plan.code)
        if mapping is None:
            raise BillingProviderError(
                f"no Stripe price ids configured for plan {plan.code!r}"
            )
        return mapping

    # ── BillingProvider impl ────────────────────────────────────────────

    async def create_customer(
        self,
        *,
        org_id: str,
        name: str,
        email: str | None = None,
    ) -> str:
        def _call():  # type: ignore[no-untyped-def]
            return self._stripe().Customer.create(
                name=name,
                email=email,
                metadata={"org_id": org_id},
            )

        try:
            customer = await asyncio.to_thread(_call)
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            raise BillingProviderError(str(exc)) from exc
        cid = customer["id"] if isinstance(customer, dict) else customer.id
        logger.info("stripe.create_customer org=%s -> %s", org_id, cid)
        return cid

    async def update_subscription(
        self,
        *,
        customer_id: str,
        plan: Plan,
        seats: int = 1,
    ) -> Subscription:
        prices = self._prices_for(plan)
        items: list[dict[str, object]] = []
        if prices.seat_price_id and plan.kind.value in ("seat", "hybrid"):
            items.append({"price": prices.seat_price_id, "quantity": seats})
        if plan.kind.value in ("usage", "hybrid"):
            for unit, price_id in prices.usage_price_ids.items():
                items.append({"price": price_id, "metadata": {"unit": unit}})
        if not items:
            raise BillingProviderError(
                f"no Stripe items resolved for plan {plan.code!r}"
            )

        def _call():  # type: ignore[no-untyped-def]
            return self._stripe().Subscription.create(
                customer=customer_id,
                items=items,
                metadata={"plan_code": plan.code},
            )

        try:
            sub = await asyncio.to_thread(_call)
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            raise BillingProviderError(str(exc)) from exc

        return Subscription(
            id=sub["id"],
            customer_id=customer_id,
            plan_code=plan.code,
            status=_map_status(sub.get("status")),
            current_period_start=_ts(sub.get("current_period_start")),
            current_period_end=_ts(sub.get("current_period_end")),
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
        # Resolve subscription_item id for this customer/unit.
        def _resolve():  # type: ignore[no-untyped-def]
            subs = self._stripe().Subscription.list(customer=customer_id, limit=10)
            data = subs.get("data") if isinstance(subs, dict) else subs.data
            for sub in data or []:
                items = sub.get("items", {}) if isinstance(sub, dict) else sub.items
                items_data = (
                    items.get("data") if isinstance(items, dict) else items.data
                )
                for item in items_data or []:
                    meta = item.get("metadata") or {}
                    if meta.get("unit") == unit:
                        return item["id"]
            return None

        try:
            item_id = await asyncio.to_thread(_resolve)
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            raise BillingProviderError(str(exc)) from exc
        if not item_id:
            raise UnknownCustomer(
                f"no metered subscription item for customer={customer_id} unit={unit}"
            )

        def _report():  # type: ignore[no-untyped-def]
            return self._stripe().SubscriptionItem.create_usage_record(
                item_id,
                quantity=int(quantity),
                timestamp=int(ts.timestamp()),
                action="increment",
            )

        try:
            await asyncio.to_thread(_report)
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            raise BillingProviderError(str(exc)) from exc

    async def void(self, *, subscription_id: str) -> None:
        def _call():  # type: ignore[no-untyped-def]
            return self._stripe().Subscription.cancel(subscription_id)

        try:
            await asyncio.to_thread(_call)
        except stripe.error.InvalidRequestError as exc:  # type: ignore[attr-defined]
            # Idempotent: ignore "No such subscription".
            logger.info("stripe.void noop: %s", exc)
        except stripe.error.StripeError as exc:  # type: ignore[attr-defined]
            raise BillingProviderError(str(exc)) from exc

    # ── Webhook helpers ─────────────────────────────────────────────────

    def verify_webhook(
        self,
        *,
        payload: bytes,
        sig_header: str,
        tolerance: int = 300,
    ) -> dict:
        """Verify a Stripe webhook signature and return the parsed event dict.

        Raises :class:`BillingProviderError` if the signature is invalid.
        """
        if not self.webhook_secret:
            raise BillingProviderError("webhook secret not configured")
        try:
            event = stripe.Webhook.construct_event(
                payload=payload,
                sig_header=sig_header,
                secret=self.webhook_secret,
                tolerance=tolerance,
            )
        except (
            ValueError,
            stripe.error.SignatureVerificationError,  # type: ignore[attr-defined]
        ) as exc:
            raise BillingProviderError(f"invalid webhook signature: {exc}") from exc
        return event if isinstance(event, dict) else event.to_dict()
