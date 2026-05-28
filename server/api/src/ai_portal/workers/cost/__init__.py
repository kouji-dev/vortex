"""Worker cost + budget tracking.

Tracks per-task spend across three buckets:

- LLM tokens (cents from gateway usage rollups)
- Sandbox minutes (cents-per-minute from pool config)
- Storage (cents-per-MB-day for artifacts retained)

A :class:`Budget` represents the pool cap. The :class:`CostTracker` is a
per-task accumulator. On breach it returns a :class:`BudgetBreach` event
the caller fans out to webhook + notification.
"""

from ai_portal.workers.cost.tracker import (
    Budget,
    CostBucket,
    CostTracker,
    BudgetBreach,
)
from ai_portal.workers.cost.notify import (
    BreachNotification,
    build_breach_notification,
)

__all__ = [
    "Budget",
    "CostBucket",
    "CostTracker",
    "BudgetBreach",
    "BreachNotification",
    "build_breach_notification",
]
