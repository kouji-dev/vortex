"""Stripe billing provider — exercised with a fake stripe client.

We don't hit Stripe.  Instead we inject a fake module-like object that mimics
the small slice of the SDK surface the provider touches.  This is faster than
``stripe-mock`` and avoids network in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
import stripe as real_stripe

from ai_portal.billing.protocol import (
    BillingProviderError,
    Plan,
    PlanKind,
    SubscriptionStatus,
    UnknownCustomer,
)
from ai_portal.billing.providers.stripe import (
    StripeBillingProvider,
    StripePlanPriceMap,
)

# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakeCustomer:
    def __init__(self) -> None:
        self.last_kwargs: dict = {}

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return {"id": "cus_test_123", **kwargs}


class _FakeSubscription:
    def __init__(self, list_data=None, create_resp=None) -> None:
        self.last_create_kwargs: dict = {}
        self.canceled_ids: list[str] = []
        self._list_data = list_data or {"data": []}
        self._create_resp = create_resp or {
            "id": "sub_test_999",
            "status": "active",
            "current_period_start": 1717000000,
            "current_period_end": 1719678400,
        }

    def create(self, **kwargs):
        self.last_create_kwargs = kwargs
        return self._create_resp

    def list(self, **kwargs):
        return self._list_data

    def cancel(self, sub_id):
        self.canceled_ids.append(sub_id)
        return {"id": sub_id, "status": "canceled"}


class _FakeSubscriptionItem:
    def __init__(self) -> None:
        self.usage_records: list[dict] = []

    def create_usage_record(self, item_id, **kwargs):
        self.usage_records.append({"item_id": item_id, **kwargs})
        return {"id": "mbur_test", **kwargs}


def _make_client(
    *,
    list_data=None,
    create_resp=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        Customer=_FakeCustomer(),
        Subscription=_FakeSubscription(
            list_data=list_data, create_resp=create_resp,
        ),
        SubscriptionItem=_FakeSubscriptionItem(),
    )


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_customer_calls_stripe_with_metadata() -> None:
    client = _make_client()
    provider = StripeBillingProvider(api_key="sk_test", client=client)
    cid = await provider.create_customer(
        org_id="org-1", name="Acme", email="a@b.com",
    )
    assert cid == "cus_test_123"
    kw = client.Customer.last_kwargs
    assert kw["name"] == "Acme"
    assert kw["email"] == "a@b.com"
    assert kw["metadata"] == {"org_id": "org-1"}


@pytest.mark.asyncio
async def test_update_subscription_seat_only_sends_quantity() -> None:
    client = _make_client()
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=client,
        plan_prices={
            "pro-seat": StripePlanPriceMap(seat_price_id="price_seat_123"),
        },
    )
    plan = Plan(code="pro-seat", kind=PlanKind.seat, seat_price_cents=2000)
    sub = await provider.update_subscription(
        customer_id="cus_x", plan=plan, seats=7,
    )
    kw = client.Subscription.last_create_kwargs
    assert kw["customer"] == "cus_x"
    assert kw["items"] == [{"price": "price_seat_123", "quantity": 7}]
    assert sub.status == SubscriptionStatus.active
    assert sub.seats == 7
    assert sub.current_period_start is not None


@pytest.mark.asyncio
async def test_update_subscription_hybrid_includes_metered_items() -> None:
    client = _make_client()
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=client,
        plan_prices={
            "team-hybrid": StripePlanPriceMap(
                seat_price_id="price_seat",
                usage_price_ids={
                    "tokens_in": "price_tin",
                    "embeddings": "price_emb",
                },
            ),
        },
    )
    plan = Plan(
        code="team-hybrid",
        kind=PlanKind.hybrid,
        seat_price_cents=1000,
        usage_unit_prices={"tokens_in": 1, "embeddings": 2},
    )
    await provider.update_subscription(customer_id="cus_x", plan=plan, seats=3)
    items = client.Subscription.last_create_kwargs["items"]
    # 1 seat line + 2 metered lines
    assert len(items) == 3
    assert items[0] == {"price": "price_seat", "quantity": 3}
    assert {it["price"] for it in items[1:]} == {"price_tin", "price_emb"}


@pytest.mark.asyncio
async def test_update_subscription_unknown_plan_raises() -> None:
    provider = StripeBillingProvider(api_key="sk_test", client=_make_client())
    plan = Plan(code="ghost", kind=PlanKind.seat, seat_price_cents=100)
    with pytest.raises(BillingProviderError):
        await provider.update_subscription(customer_id="cus_x", plan=plan)


@pytest.mark.asyncio
async def test_report_usage_resolves_item_and_increments() -> None:
    # Stripe subscription with a metered item that carries metadata.unit
    list_data = {
        "data": [
            {
                "id": "sub_1",
                "items": {
                    "data": [
                        {
                            "id": "si_seat",
                            "metadata": {},  # seat, no unit
                        },
                        {
                            "id": "si_tokens_in",
                            "metadata": {"unit": "tokens_in"},
                        },
                    ]
                },
            }
        ]
    }
    client = _make_client(list_data=list_data)
    provider = StripeBillingProvider(api_key="sk_test", client=client)
    await provider.report_usage(
        customer_id="cus_x",
        unit="tokens_in",
        quantity=12345,
        ts=datetime(2026, 5, 28, 12, 0, tzinfo=UTC),
    )
    assert len(client.SubscriptionItem.usage_records) == 1
    rec = client.SubscriptionItem.usage_records[0]
    assert rec["item_id"] == "si_tokens_in"
    assert rec["quantity"] == 12345
    assert rec["action"] == "increment"


@pytest.mark.asyncio
async def test_report_usage_missing_item_raises_unknown_customer() -> None:
    client = _make_client(list_data={"data": []})
    provider = StripeBillingProvider(api_key="sk_test", client=client)
    with pytest.raises(UnknownCustomer):
        await provider.report_usage(
            customer_id="cus_unknown",
            unit="tokens_in",
            quantity=1,
            ts=datetime(2026, 5, 28, tzinfo=UTC),
        )


@pytest.mark.asyncio
async def test_void_calls_subscription_cancel() -> None:
    client = _make_client()
    provider = StripeBillingProvider(api_key="sk_test", client=client)
    await provider.void(subscription_id="sub_xyz")
    assert client.Subscription.canceled_ids == ["sub_xyz"]


@pytest.mark.asyncio
async def test_void_swallows_not_found() -> None:
    client = _make_client()
    def _raise(sub_id):
        raise real_stripe.error.InvalidRequestError(
            "No such subscription", "sub_id"
        )
    client.Subscription.cancel = _raise  # type: ignore[method-assign]
    provider = StripeBillingProvider(api_key="sk_test", client=client)
    # Must not raise
    await provider.void(subscription_id="sub_ghost")


# ── Webhook signature verification ──────────────────────────────────────────


def test_verify_webhook_rejects_unsigned() -> None:
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=_make_client(),
        webhook_secret="whsec_t0p_secret",
    )
    with pytest.raises(BillingProviderError):
        provider.verify_webhook(
            payload=b'{"id":"evt_1"}',
            sig_header="t=1,v1=bad",
        )


def test_verify_webhook_accepts_valid_signature(monkeypatch) -> None:
    """Patch ``stripe.Webhook.construct_event`` to skip live HMAC math."""
    sample_event = {"id": "evt_1", "type": "invoice.paid", "data": {"object": {}}}
    monkeypatch.setattr(
        real_stripe.Webhook, "construct_event",
        lambda payload, sig_header, secret, tolerance=300: sample_event,
    )
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=_make_client(),
        webhook_secret="whsec_x",
    )
    event = provider.verify_webhook(
        payload=b'{"id":"evt_1"}',
        sig_header="t=1,v1=ok",
    )
    assert event["id"] == "evt_1"
    assert event["type"] == "invoice.paid"


def test_verify_webhook_without_secret_raises() -> None:
    provider = StripeBillingProvider(api_key="sk_test", client=_make_client())
    with pytest.raises(BillingProviderError):
        provider.verify_webhook(payload=b"{}", sig_header="t=1,v1=x")
