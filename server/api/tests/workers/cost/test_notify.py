"""Tests for breach notification builder."""

from __future__ import annotations

from ai_portal.workers.cost.notify import build_breach_notification
from ai_portal.workers.cost.tracker import BudgetBreach


def test_warning_notification_shape() -> None:
    breach = BudgetBreach(
        threshold_pct=50,
        total_cents=500,
        budget_cents=1000,
        is_hard_cap=False,
    )
    n = build_breach_notification(
        breach, task_id="t-1", task_title="Fix bug", org_id="org-1"
    )
    assert n.event_type == "workers.task.budget.warning"
    assert "50%" in n.subject
    assert n.payload["task_id"] == "t-1"
    assert n.payload["threshold_pct"] == 50
    assert n.payload["is_hard_cap"] is False


def test_hard_cap_notification_event_type() -> None:
    breach = BudgetBreach(
        threshold_pct=100,
        total_cents=1000,
        budget_cents=1000,
        is_hard_cap=True,
    )
    n = build_breach_notification(
        breach, task_id="t-2", task_title="Big refactor", org_id="org-1"
    )
    assert n.event_type == "workers.task.budget.exceeded"
    assert "paused" in n.body
    assert n.payload["is_hard_cap"] is True
