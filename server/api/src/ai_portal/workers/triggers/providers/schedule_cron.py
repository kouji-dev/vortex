"""Schedule-cron trigger — emits a TaskInput from a stored template + cron.

This module exposes a stateless ``parse`` that turns a schedule-fire
payload into a ``TaskInput``, plus a minimal ``next_fire_at`` helper using
a small built-in cron evaluator (no croniter dep needed for tests).

The cron evaluator supports ``minute hour day month weekday`` with ``*``,
comma lists, and ``a-b`` ranges. Step (``*/n``) is supported on the minute
field only — enough for the bundled scheduler use cases. Production deploys
can swap in croniter via ``next_fire_at_with_croniter``.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ai_portal.workers.triggers.protocol import TriggerSource  # noqa: F401
from ai_portal.workers.types import TaskInput, TriggerSourceKind


class ScheduleCronTrigger:
    """Trigger fired by the in-process scheduler on cron boundary."""

    kind = TriggerSourceKind.schedule_cron

    def parse(
        self, payload: dict, headers: dict | None = None
    ) -> TaskInput | None:
        tpl = payload.get("template") or payload
        title = tpl.get("title")
        repo = tpl.get("repo")
        if not title or not repo:
            return None
        return TaskInput(
            title=title,
            description=tpl.get("description", "") or "",
            repo=repo,
            base_branch=tpl.get("base_branch", "main"),
            extra={
                "schedule_id": payload.get("schedule_id"),
                "fired_at": (payload.get("fired_at") or "").strip()
                or datetime.utcnow().isoformat() + "Z",
                "source": "schedule_cron",
            },
        )


def _match_field(part: str, value: int, *, lo: int, hi: int) -> bool:
    if part == "*":
        return True
    if part.startswith("*/"):
        step = int(part[2:])
        return value % step == 0
    for spec in part.split(","):
        if "-" in spec:
            a, b = spec.split("-", 1)
            if int(a) <= value <= int(b):
                return True
        else:
            if int(spec) == value:
                return True
    return False


def cron_matches(expr: str, dt: datetime) -> bool:
    """Return True iff ``dt`` matches the cron ``expr``."""
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"bad cron expr: {expr}")
    mi, hr, dom, mo, dow = parts
    return all(
        [
            _match_field(mi, dt.minute, lo=0, hi=59),
            _match_field(hr, dt.hour, lo=0, hi=23),
            _match_field(dom, dt.day, lo=1, hi=31),
            _match_field(mo, dt.month, lo=1, hi=12),
            _match_field(dow, dt.weekday() + 1 % 7, lo=0, hi=6)
            or _match_field(dow, dt.isoweekday() % 7, lo=0, hi=6),
        ]
    )


def next_fire_at(expr: str, *, after: datetime) -> datetime:
    """Find the next minute boundary at or after ``after`` matching ``expr``.

    Bounded search up to 1 year to avoid pathological hangs.
    """
    cur = (after.replace(second=0, microsecond=0) + timedelta(minutes=1))
    limit = cur + timedelta(days=366)
    while cur < limit:
        if cron_matches(expr, cur):
            return cur
        cur += timedelta(minutes=1)
    raise RuntimeError(f"no fire window within a year for {expr}")
