"""Manual billing provider — no-op operations + invoice print log."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ai_portal.billing.protocol import (
    BillingProvider,
    Plan,
    PlanKind,
    SubscriptionStatus,
)
from ai_portal.billing.providers.manual import ManualBillingProvider


def test_manual_satisfies_protocol() -> None:
    assert isinstance(ManualBillingProvider(), BillingProvider)


@pytest.mark.asyncio
async def test_create_customer_returns_prefixed_id() -> None:
    p = ManualBillingProvider()
    cid = await p.create_customer(org_id="org-1", name="Acme", email="a@b.com")
    assert cid.startswith("cus_manual_")


@pytest.mark.asyncio
async def test_update_subscription_returns_active_sub() -> None:
    p = ManualBillingProvider()
    plan = Plan(code="pro-seat", kind=PlanKind.seat, seat_price_cents=2000)
    sub = await p.update_subscription(customer_id="cus_x", plan=plan, seats=5)
    assert sub.customer_id == "cus_x"
    assert sub.plan_code == "pro-seat"
    assert sub.seats == 5
    assert sub.status == SubscriptionStatus.active
    assert sub.id.startswith("sub_manual_")


@pytest.mark.asyncio
async def test_report_usage_appends_to_log() -> None:
    p = ManualBillingProvider()
    ts = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    await p.report_usage(customer_id="cus_x", unit="tokens_in", quantity=1234, ts=ts)
    assert len(p.usage_log) == 1
    entry = p.usage_log[0]
    assert entry["customer_id"] == "cus_x"
    assert entry["unit"] == "tokens_in"
    assert entry["quantity"] == 1234


@pytest.mark.asyncio
async def test_void_is_idempotent_noop() -> None:
    p = ManualBillingProvider()
    await p.void(subscription_id="sub_x")
    await p.void(subscription_id="sub_x")  # second call must not raise


def test_print_invoice_logs_record() -> None:
    p = ManualBillingProvider()
    invoice_id = p.print_invoice(
        subscription_id="sub_x",
        amount_cents=12300,
        currency="usd",
        memo="May usage",
    )
    assert invoice_id.startswith("in_manual_")
    assert len(p.invoices_log) == 1
    rec = p.invoices_log[0]
    assert rec["subscription_id"] == "sub_x"
    assert rec["amount_cents"] == 12300


def test_plan_kinds_cover_seat_usage_hybrid() -> None:
    seat = Plan(code="s", kind=PlanKind.seat, seat_price_cents=2000)
    usage = Plan(
        code="u",
        kind=PlanKind.usage,
        usage_unit_prices={"tokens_in": 1},
    )
    hybrid = Plan(
        code="h",
        kind=PlanKind.hybrid,
        seat_price_cents=1000,
        usage_unit_prices={"tokens_in": 1},
        included_units={"tokens_in": 1_000_000},
    )
    assert seat.kind == PlanKind.seat
    assert usage.kind == PlanKind.usage
    assert hybrid.kind == PlanKind.hybrid
