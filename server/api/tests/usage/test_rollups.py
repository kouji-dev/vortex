"""E2: rollups aggregate usage_events by dimension over a period."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import text

from tests.conftest import requires_postgres


@requires_postgres
def test_rollup_by_key_sums_correctly():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.rollups import aggregate
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'E2') ON CONFLICT DO NOTHING"),
                {"id": str(org_id), "slug": f"e2-{org_id.hex[:8]}"},
            )

            ts = datetime(2026, 5, 28, 12, 0, 0, tzinfo=timezone.utc)
            # 5 events for key=1001, 5 for key=1002 in the same hour.
            for i in range(5):
                emit_usage(
                    db,
                    org_id=org_id,
                    unit=UsageUnit.queries.value,
                    qty=1,
                    actor_kind="api_key",
                    module="gateway",
                    actor_api_key_id=1001,
                    unit_price_usd=Decimal("0.01"),
                    ts=ts,
                )
            for i in range(5):
                emit_usage(
                    db,
                    org_id=org_id,
                    unit=UsageUnit.queries.value,
                    qty=2,
                    actor_kind="api_key",
                    module="gateway",
                    actor_api_key_id=1002,
                    unit_price_usd=Decimal("0.01"),
                    ts=ts,
                )
            db.commit()

            buckets = aggregate(db, org_id=org_id, grain="hour", dim="key", period_start=ts)
            by_key = {b.dim_value: b for b in buckets}
            assert set(by_key.keys()) == {"1001", "1002"}
            assert by_key["1001"].qty == Decimal("5")
            assert by_key["1001"].cost_usd == Decimal("0.050000")
            assert by_key["1002"].qty == Decimal("10")
            assert by_key["1002"].cost_usd == Decimal("0.100000")
            assert by_key["1001"].event_count == 5
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_rollup_by_model_daily():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.rollups import aggregate
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        with bypass_rls(db):
            db.execute(
                text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'E2b') ON CONFLICT DO NOTHING"),
                {"id": str(org_id), "slug": f"e2b-{org_id.hex[:8]}"},
            )

            base = datetime(2026, 5, 27, 0, 30, 0, tzinfo=timezone.utc)
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value, qty=1_000_000,
                actor_kind="user", module="gateway",
                model="claude-sonnet-4-6", ts=base,
            )
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value, qty=500_000,
                actor_kind="user", module="gateway",
                model="claude-sonnet-4-6", ts=base.replace(hour=10),
            )
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value, qty=1_000_000,
                actor_kind="user", module="gateway",
                model="gpt-4o", ts=base.replace(hour=15),
            )
            db.commit()

            buckets = aggregate(db, org_id=org_id, grain="day", dim="model", period_start=base)
            by_model = {b.dim_value: b for b in buckets}
            assert by_model["claude-sonnet-4-6"].qty == Decimal("1500000")
            # 1.5M * $3/M = $4.50
            assert by_model["claude-sonnet-4-6"].cost_usd == Decimal("4.500000")
            assert by_model["gpt-4o"].qty == Decimal("1000000")
            # gpt-4o input $2.5/M → $2.50
            assert by_model["gpt-4o"].cost_usd == Decimal("2.500000")
    finally:
        db.rollback()
        db.close()
