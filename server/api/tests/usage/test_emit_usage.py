"""E1: emit_usage writes a UsageEvent with frozen pricing snapshot."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.conftest import requires_postgres


@requires_postgres
def test_emit_usage_writes_row_with_frozen_cost():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.events_model import UsageEvent
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        # Ensure org exists so FK constraint passes.
        with bypass_rls(db):
            db.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'E1') ON CONFLICT DO NOTHING"),
                {"id": str(org_id), "slug": f"e1-{org_id.hex[:8]}"},
            )
            event = emit_usage(
                db,
                org_id=org_id,
                unit=UsageUnit.tokens_in.value,
                qty=1_000_000,
                actor_kind="user",
                module="gateway",
                model="claude-sonnet-4-6",
                actor_user_id=None,
            )
            db.commit()

            assert event.id is not None
            assert event.unit == "tokens_in"
            assert event.qty == Decimal("1000000")
            # claude-sonnet-4-6 input is $3 / 1M → exact match.
            assert event.cost_usd == Decimal("3.000000")
            assert event.pricing_snapshot is not None
            assert event.pricing_snapshot["source"] == "llm_pricing"
            assert event.pricing_snapshot["per_million_usd"] == "3.0"

            # Persisted.
            fetched = (
                db.execute(
                    text("SELECT cost_usd, unit FROM usage_events WHERE id = :id"),
                    {"id": event.id},
                )
                .one()
            )
            assert fetched.unit == "tokens_in"
            assert fetched.cost_usd == Decimal("3.000000")
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_emit_usage_unknown_model_uses_default_unit_price():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'E1b') ON CONFLICT DO NOTHING"),
                {"id": str(org_id), "slug": f"e1b-{org_id.hex[:8]}"},
            )
            event = emit_usage(
                db,
                org_id=org_id,
                unit=UsageUnit.worker_minutes.value,
                qty=10,
                actor_kind="service",
                module="workers",
            )
            db.commit()
            # 10 * $0.05/min = $0.50
            assert event.cost_usd == Decimal("0.500000")
            assert event.pricing_snapshot["source"] == "default"
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_emit_usage_unit_price_override_freezes_snapshot():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'E1c') ON CONFLICT DO NOTHING"),
                {"id": str(org_id), "slug": f"e1c-{org_id.hex[:8]}"},
            )
            event = emit_usage(
                db,
                org_id=org_id,
                unit=UsageUnit.storage_gb.value,
                qty=Decimal("100"),
                actor_kind="system",
                module="rag",
                unit_price_usd=Decimal("0.10"),
            )
            db.commit()
            assert event.cost_usd == Decimal("10.000000")
            assert event.pricing_snapshot["source"] == "override"
            assert event.pricing_snapshot["unit_price_usd"] == "0.10"
    finally:
        db.rollback()
        db.close()


def test_emit_usage_rejects_unknown_unit():
    from ai_portal.usage.emit import emit_usage

    with pytest.raises(ValueError, match="unknown usage unit"):
        emit_usage(
            db=None,  # type: ignore[arg-type]
            org_id=uuid.uuid4(),
            unit="not_a_unit",
            qty=1,
            actor_kind="user",
            module="gateway",
        )


def test_compute_event_cost_token_unit():
    from decimal import Decimal as D
    from ai_portal.usage.emit import compute_event_cost

    cost, snap = compute_event_cost(
        unit="tokens_out", qty=D("500000"), model="claude-sonnet-4-6", unit_price_usd=None
    )
    # output rate is $15/M, half a million → $7.50
    assert cost == D("7.500000")
    assert snap["source"] == "llm_pricing"
