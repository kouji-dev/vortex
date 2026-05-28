"""E3: budgets — soft warns at 50/80/100, hard cutoff at 100, grace extension."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import text

# Ensure all referenced tables are registered in Base.metadata before any
# FK on quotas/budgets resolves.
import ai_portal.auth.model  # noqa: F401
import ai_portal.usage.events_model  # noqa: F401
import ai_portal.budgets.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'BudT') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_check_budget_blocks_when_projected_exceeds_limit():
    from ai_portal.budgets.model import Budget
    from ai_portal.budgets.service import check_budget
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "bud-block")
            b = Budget(
                org_id=org_id, name="org-monthly", scope_kind="org", scope_id=None,
                limit_usd=Decimal("10.00"), period="month",
                warn_at_pcts=[50, 80, 100], hard_cutoff=True,
            )
            db.add(b)
            db.flush()
            # Emit $9 of spend.
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.queries.value, qty=900,
                actor_kind="user", module="gateway", actor_user_id=None,
                unit_price_usd=Decimal("0.01"),
            )
            db.commit()

            # Projected $9 + $2 = $11 > $10 → block.
            decision = check_budget(db, org_id=org_id, incoming_cost_usd=Decimal("2.00"))
            assert decision.is_blocked
            assert decision.action == "block"
            assert decision.spent_usd == Decimal("9.000000")
            assert decision.effective_limit_usd == Decimal("10.00")

            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_check_budget_fires_warns_at_50_80():
    from ai_portal.budgets.model import Budget, BudgetAlert
    from ai_portal.budgets.service import check_budget
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit
    from sqlalchemy import select

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "bud-warn")
            b = Budget(
                org_id=org_id, name="org-month", scope_kind="org", scope_id=None,
                limit_usd=Decimal("100.00"), period="month",
                warn_at_pcts=[50, 80, 100], hard_cutoff=False,
            )
            db.add(b)
            db.flush()
            # $50 spend so projected $80 hits 50% + 80%.
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.queries.value, qty=5000,
                actor_kind="user", module="gateway", unit_price_usd=Decimal("0.01"),
            )
            db.commit()

            decision = check_budget(db, org_id=org_id, incoming_cost_usd=Decimal("30.00"))
            assert decision.action == "warn"
            assert set(decision.fired_thresholds) == {50, 80}
            assert 100 not in decision.fired_thresholds

            # Alerts persisted exactly once per threshold.
            alerts = db.scalars(
                select(BudgetAlert).where(BudgetAlert.budget_id == b.id)
            ).all()
            assert {a.threshold_pct for a in alerts} == {50, 80}

            # Calling again with the same projection does NOT duplicate alerts.
            check_budget(db, org_id=org_id, incoming_cost_usd=Decimal("30.00"))
            alerts2 = db.scalars(
                select(BudgetAlert).where(BudgetAlert.budget_id == b.id)
            ).all()
            assert len(alerts2) == len(alerts)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_grace_extension_allows_overage_until_expiry():
    from ai_portal.budgets.model import Budget
    from ai_portal.budgets.service import check_budget, extend_budget_grace
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "bud-grace")
            b = Budget(
                org_id=org_id, name="org-grace", scope_kind="org", scope_id=None,
                limit_usd=Decimal("10.00"), period="month",
                warn_at_pcts=[100], hard_cutoff=True,
            )
            db.add(b)
            db.flush()
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.queries.value, qty=900,
                actor_kind="user", module="gateway", unit_price_usd=Decimal("0.01"),
            )
            db.commit()

            # No grace → projected $11 blocks.
            d1 = check_budget(db, org_id=org_id, incoming_cost_usd=Decimal("2.00"))
            assert d1.is_blocked

            # Extend grace by $5 until tomorrow.
            extend_budget_grace(
                db, budget_id=b.id,
                grace_extension_usd=Decimal("5.00"),
                grace_expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            db.commit()

            d2 = check_budget(db, org_id=org_id, incoming_cost_usd=Decimal("2.00"))
            assert d2.action == "allow" or d2.action == "warn"
            assert not d2.is_blocked
            assert d2.effective_limit_usd == Decimal("15.00")
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_check_quota_blocks_over_max_qty():
    from ai_portal.budgets.model import Quota
    from ai_portal.budgets.service import check_quota
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.emit import emit_usage
    from ai_portal.usage.units import UsageUnit

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "qta")
            db.add(Quota(
                org_id=org_id, name="cap-tokens", scope_kind="org", scope_id=None,
                unit=UsageUnit.tokens_in.value, period="day",
                max_qty=Decimal("1000"), action_on_breach="block",
            ))
            db.flush()
            emit_usage(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value, qty=900,
                actor_kind="user", module="gateway",
            )
            db.commit()

            d = check_quota(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value,
                incoming_qty=Decimal("200"),
            )
            assert d.is_blocked
            assert d.action == "block"

            # Under-limit allow.
            d2 = check_quota(
                db, org_id=org_id, unit=UsageUnit.tokens_in.value,
                incoming_qty=Decimal("50"),
            )
            assert d2.action == "allow"
            db.commit()
    finally:
        db.rollback()
        db.close()
