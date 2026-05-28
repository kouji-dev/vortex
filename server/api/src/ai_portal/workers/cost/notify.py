"""Build webhook + notify payloads for budget breaches.

The orchestrator hands a :class:`BudgetBreach` to
:func:`build_breach_notification`, which returns a structured
:class:`BreachNotification` ready to fan out via
``ai_portal.control_plane.emit_webhook`` and ``NotifyService``.
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_portal.workers.cost.tracker import BudgetBreach


@dataclass(frozen=True)
class BreachNotification:
    event_type: str
    payload: dict
    subject: str
    body: str


def build_breach_notification(
    breach: BudgetBreach,
    *,
    task_id: str,
    task_title: str,
    org_id: str,
) -> BreachNotification:
    """Pure builder — no I/O."""
    if breach.is_hard_cap:
        event_type = "workers.task.budget.exceeded"
        subject = f"Worker task paused: budget reached ({task_title})"
        body = (
            f"Task {task_title} ({task_id}) hit 100% of its "
            f"{breach.budget_cents}c budget. The run is paused pending approval."
        )
    else:
        event_type = "workers.task.budget.warning"
        subject = (
            f"Worker task at {breach.threshold_pct}% of budget ({task_title})"
        )
        body = (
            f"Task {task_title} ({task_id}) has used "
            f"{breach.total_cents}c of {breach.budget_cents}c "
            f"({breach.threshold_pct}% threshold)."
        )
    payload = {
        "task_id": task_id,
        "task_title": task_title,
        "org_id": org_id,
        "threshold_pct": breach.threshold_pct,
        "total_cents": breach.total_cents,
        "budget_cents": breach.budget_cents,
        "is_hard_cap": breach.is_hard_cap,
    }
    return BreachNotification(
        event_type=event_type, payload=payload, subject=subject, body=body
    )
