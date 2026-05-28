"""Score boosts applied after RRF / before final sort.

Boosts are *multiplicative*: a boost factor of 1.0 is a no-op. We keep them
small (typical range 0.5 – 2.0) so they nudge rather than dominate the base
relevance score.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Iterable

from ai_portal.rag.search.types import SearchHit


def freshness_boost(
    hit: SearchHit, *, half_life_days: float = 90.0, now: datetime | None = None
) -> float:
    """Exponential decay toward 1.0 as docs age.

    Newer doc → boost ~ 1 + 0.5; very old doc → boost ~ 1.0.
    """
    if half_life_days <= 0:
        return 1.0
    meta = hit.meta or {}
    raw = meta.get("created_at") or meta.get("date") or meta.get("modified_at")
    if not raw:
        return 1.0
    try:
        if isinstance(raw, (int, float)):
            dt = datetime.fromtimestamp(float(raw), tz=timezone.utc)
        else:
            dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return 1.0
    ref = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (ref - dt).total_seconds() / 86400.0)
    decay = math.exp(-math.log(2) * age_days / half_life_days)
    return 1.0 + 0.5 * decay


def source_priority_boost(hit: SearchHit, weights: dict[str, float]) -> float:
    """Multiplier from a per-source weights table."""
    if not weights:
        return 1.0
    meta = hit.meta or {}
    src = meta.get("source")
    if not src:
        return 1.0
    return float(weights.get(str(src), 1.0))


def apply_boosts(
    hits: Iterable[SearchHit],
    *,
    freshness: bool = False,
    source_weights: dict[str, float] | None = None,
    now: datetime | None = None,
) -> list[SearchHit]:
    """Apply enabled boosts to each hit's ``score`` (in-place on a copy)."""
    out: list[SearchHit] = []
    weights = source_weights or {}
    for h in hits:
        boost = 1.0
        if freshness:
            boost *= freshness_boost(h, now=now)
        if weights:
            boost *= source_priority_boost(h, weights)
        new = SearchHit(
            chunk_id=h.chunk_id,
            document_id=h.document_id,
            kb_id=h.kb_id,
            text=h.text,
            score=h.score * boost,
            meta=dict(h.meta or {}),
            lexical_rank=h.lexical_rank,
            dense_rank=h.dense_rank,
            rerank_score=h.rerank_score,
        )
        out.append(new)
    out.sort(key=lambda x: x.score, reverse=True)
    return out
