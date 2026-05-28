"""Tests for the cost / budget tracker."""

from __future__ import annotations

import pytest

from ai_portal.workers.cost.tracker import (
    Budget,
    BudgetBreach,
    CostBucket,
    CostTracker,
)


def test_initial_state() -> None:
    t = CostTracker(budget=Budget(cents=1000))
    assert t.total_cents == 0
    assert t.remaining_cents == 1000
    assert not t.is_over_budget()


def test_basic_add() -> None:
    t = CostTracker(budget=Budget(cents=1000))
    breaches = t.add(CostBucket.llm, 100)
    assert breaches == []
    assert t.total_cents == 100
    assert t.remaining_cents == 900


def test_warn_threshold_fires_once() -> None:
    t = CostTracker(budget=Budget(cents=1000, warn_thresholds_pct=(50, 80)))
    # 60% — should emit 50%
    bs = t.add(CostBucket.llm, 600)
    kinds = [b.threshold_pct for b in bs]
    assert 50 in kinds
    # next add — even staying below 80% — must NOT re-emit 50%
    bs2 = t.add(CostBucket.llm, 100)  # 70% total
    assert all(b.threshold_pct != 50 for b in bs2)


def test_multiple_thresholds_in_one_jump() -> None:
    t = CostTracker(budget=Budget(cents=1000, warn_thresholds_pct=(50, 80)))
    bs = t.add(CostBucket.llm, 850)
    kinds = sorted(b.threshold_pct for b in bs)
    assert kinds == [50, 80]


def test_hard_cap_fires() -> None:
    t = CostTracker(budget=Budget(cents=1000, warn_thresholds_pct=()))
    bs = t.add(CostBucket.llm, 1000)
    hard = [b for b in bs if b.is_hard_cap]
    assert len(hard) == 1 and hard[0].threshold_pct == 100
    assert t.is_over_budget()


def test_hard_cap_only_fires_once() -> None:
    t = CostTracker(budget=Budget(cents=100, warn_thresholds_pct=()))
    t.add(CostBucket.llm, 100)
    bs2 = t.add(CostBucket.llm, 50)
    assert all(b.threshold_pct != 100 for b in bs2)


def test_zero_budget_never_breaches() -> None:
    t = CostTracker(budget=Budget(cents=0))
    bs = t.add(CostBucket.llm, 99999)
    assert bs == []
    assert not t.is_over_budget()


def test_sandbox_minutes_rounding() -> None:
    t = CostTracker(budget=Budget(cents=10000))
    bs = t.add_sandbox_minutes(minutes=2.5, cents_per_minute=20)
    assert t.spend[CostBucket.sandbox] == 50
    assert bs == []


def test_storage_mb_days_rounding() -> None:
    t = CostTracker(budget=Budget(cents=10000))
    t.add_storage_mb_days(mb_days=10, cents_per_mb_day=1)
    assert t.spend[CostBucket.storage] == 10


def test_negative_delta_raises() -> None:
    t = CostTracker(budget=Budget(cents=1000))
    with pytest.raises(ValueError):
        t.add(CostBucket.llm, -10)


def test_negative_budget_raises() -> None:
    with pytest.raises(ValueError):
        Budget(cents=-1)


def test_breach_payload_fields() -> None:
    t = CostTracker(budget=Budget(cents=1000, warn_thresholds_pct=(50,)))
    bs = t.add(CostBucket.llm, 500)
    assert isinstance(bs[0], BudgetBreach)
    assert bs[0].budget_cents == 1000
    assert bs[0].total_cents == 500
    assert not bs[0].is_hard_cap
