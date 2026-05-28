"""Stripe webhook receiver — signature verification + event application.

These tests exercise the ``BillingService.apply_webhook_event`` dispatcher
and the ``StripeBillingProvider.verify_webhook`` boundary against synthetic
events.  We do not boot FastAPI — the wiring is tested via direct calls.
"""

from __future__ import annotations

import uuid as _uuid
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import stripe as real_stripe

from ai_portal.billing.protocol import BillingProviderError
from ai_portal.billing.providers.manual import ManualBillingProvider
from ai_portal.billing.providers.stripe import StripeBillingProvider
from ai_portal.billing.service import BillingService

# ── Webhook signature verification (provider boundary) ─────────────────────


def test_verify_webhook_invalid_signature_rejected(monkeypatch) -> None:
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=SimpleNamespace(),
        webhook_secret="whsec_x",
    )

    def _raise(payload, sig_header, secret, tolerance=300):
        raise real_stripe.error.SignatureVerificationError(
            "bad sig", sig_header
        )

    monkeypatch.setattr(real_stripe.Webhook, "construct_event", _raise)
    with pytest.raises(BillingProviderError, match="invalid webhook signature"):
        provider.verify_webhook(payload=b"{}", sig_header="t=1,v1=bad")


def test_verify_webhook_returns_event_dict(monkeypatch) -> None:
    event = {
        "id": "evt_1",
        "type": "invoice.paid",
        "data": {"object": {"id": "in_1"}},
    }
    provider = StripeBillingProvider(
        api_key="sk_test",
        client=SimpleNamespace(),
        webhook_secret="whsec_x",
    )
    monkeypatch.setattr(
        real_stripe.Webhook, "construct_event",
        lambda payload, sig_header, secret, tolerance=300: event,
    )
    out = provider.verify_webhook(payload=b"{}", sig_header="t=1,v1=ok")
    assert out["type"] == "invoice.paid"


# ── apply_webhook_event dispatcher (service layer) ─────────────────────────


def _stub_db() -> MagicMock:
    """Minimal stub: provides .execute(...).scalar_one_or_none(), .add, .flush."""
    db = MagicMock()
    db.flush = MagicMock()
    db.add = MagicMock()
    return db


def test_apply_webhook_unknown_event_returns_ignored() -> None:
    svc = BillingService(_stub_db(), ManualBillingProvider())
    tag = svc.apply_webhook_event({"type": "foo.bar", "data": {"object": {}}})
    assert tag == "ignored"


def test_apply_subscription_updated_marks_row(monkeypatch) -> None:
    db = _stub_db()
    fake_row = SimpleNamespace(
        external_id="sub_1",
        status="active",
        current_period_start=None,
        current_period_end=None,
        canceled_at=None,
        updated_at=None,
    )
    db.execute.return_value.scalar_one_or_none.return_value = fake_row
    svc = BillingService(db, ManualBillingProvider())
    tag = svc.apply_webhook_event(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {
                "id": "sub_1",
                "status": "past_due",
                "current_period_start": 1717000000,
                "current_period_end": 1719678400,
            }},
        }
    )
    assert tag == "subscription_updated"
    assert fake_row.status == "past_due"
    assert fake_row.current_period_start is not None
    assert fake_row.current_period_end is not None


def test_apply_subscription_deleted_cancels_row() -> None:
    db = _stub_db()
    fake_row = SimpleNamespace(
        external_id="sub_1",
        status="active",
        current_period_start=None,
        current_period_end=None,
        canceled_at=None,
        updated_at=None,
    )
    db.execute.return_value.scalar_one_or_none.return_value = fake_row
    svc = BillingService(db, ManualBillingProvider())
    tag = svc.apply_webhook_event(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"id": "sub_1", "status": "canceled"}},
        }
    )
    assert tag == "subscription_updated"
    assert fake_row.status == "canceled"
    assert fake_row.canceled_at is not None


def test_apply_invoice_paid_creates_row_when_new() -> None:
    db = _stub_db()
    sub_row = SimpleNamespace(
        id=_uuid.uuid4(),
        org_id=_uuid.uuid4(),
        external_id="sub_1",
    )
    invoice_lookup = MagicMock()
    invoice_lookup.scalar_one_or_none.return_value = None
    sub_lookup = MagicMock()
    sub_lookup.scalar_one_or_none.return_value = sub_row
    # First execute = subscription lookup, second = invoice lookup
    db.execute.side_effect = [sub_lookup, invoice_lookup]

    svc = BillingService(db, ManualBillingProvider())
    tag = svc.apply_webhook_event(
        {
            "type": "invoice.paid",
            "data": {"object": {
                "id": "in_999",
                "subscription": "sub_1",
                "amount_paid": 12345,
                "currency": "usd",
                "invoice_pdf": "https://stripe.example/inv.pdf",
            }},
        }
    )
    assert tag == "invoice_created"
    db.add.assert_called_once()
    added = db.add.call_args.args[0]
    assert added.amount_cents == 12345
    assert added.status == "paid"
    assert added.pdf_url == "https://stripe.example/inv.pdf"
    assert added.paid_at is not None


def test_apply_invoice_updates_existing_row() -> None:
    db = _stub_db()
    sub_row = SimpleNamespace(id=_uuid.uuid4(), org_id=_uuid.uuid4())
    existing = SimpleNamespace(
        external_id="in_999",
        status="open",
        amount_cents=0,
        currency="usd",
        pdf_url=None,
        paid_at=None,
    )
    sub_lookup = MagicMock()
    sub_lookup.scalar_one_or_none.return_value = sub_row
    inv_lookup = MagicMock()
    inv_lookup.scalar_one_or_none.return_value = existing
    db.execute.side_effect = [sub_lookup, inv_lookup]
    svc = BillingService(db, ManualBillingProvider())
    tag = svc.apply_webhook_event(
        {
            "type": "invoice.paid",
            "data": {"object": {
                "id": "in_999",
                "subscription": "sub_1",
                "amount_paid": 7777,
                "currency": "usd",
            }},
        }
    )
    assert tag == "invoice_updated"
    assert existing.status == "paid"
    assert existing.amount_cents == 7777


def test_apply_orphan_invoice_drops() -> None:
    db = _stub_db()
    sub_lookup = MagicMock()
    sub_lookup.scalar_one_or_none.return_value = None
    inv_lookup = MagicMock()
    inv_lookup.scalar_one_or_none.return_value = None
    db.execute.side_effect = [sub_lookup, inv_lookup]
    svc = BillingService(db, ManualBillingProvider())
    tag = svc.apply_webhook_event(
        {
            "type": "invoice.finalized",
            "data": {"object": {
                "id": "in_ghost",
                "subscription": "sub_ghost",
                "total": 999,
                "currency": "usd",
            }},
        }
    )
    assert tag == "orphan_invoice"
    db.add.assert_not_called()
