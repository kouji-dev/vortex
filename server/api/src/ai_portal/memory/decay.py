"""TTL + importance decay defaults.

Per-type retention defaults:
- preference, entity: no TTL (None)
- fact:               365d
- relation:           180d
- episode:             90d
- procedure:          180d

Org policy ``retention_days_json`` overrides per-type.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from typing import Any

DEFAULT_RETENTION_DAYS: dict[str, int | None] = {
    "preference": None,
    "entity": None,
    "fact": 365,
    "relation": 180,
    "episode": 90,
    "procedure": 180,
}


def compute_expires_at(
    type: str,
    *,
    retention_days: dict[str, int] | None = None,
    now: datetime | None = None,
    pinned: bool = False,
) -> datetime | None:
    """Return UTC datetime when a memory of ``type`` expires, or None for no TTL."""
    if pinned:
        return None
    now = now or datetime.utcnow()
    days: int | None
    if retention_days and type in retention_days:
        days = int(retention_days[type])
    else:
        days = DEFAULT_RETENTION_DAYS.get(type)
    if days is None or days <= 0:
        return None
    return now + timedelta(days=days)


def decay_importance(
    current: float,
    *,
    days_since_use: float,
    recent_use_count: int,
    half_life_days: float = 45.0,
) -> float:
    """Compute new importance with exponential decay + use-count boost.

    importance' = current * exp(-Δdays/45) + 0.01 * recent_use_count
    Clamped to [0, 1].
    """
    decayed = float(current) * math.exp(-max(0.0, days_since_use) / half_life_days)
    boosted = decayed + 0.01 * max(0, recent_use_count)
    return max(0.0, min(1.0, boosted))
