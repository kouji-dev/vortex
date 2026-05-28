"""Metadata filters for retrieval (source / language / date / tag / author).

Filters apply to ``KbChunk.meta_json`` keys and the parent ``KbDocument``
columns. We keep filter evaluation pure-Python so it works against any
list-of-hits backend (pgvector hits already loaded; in-memory tests).
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ai_portal.rag.search.types import SearchFilter, SearchHit


def _matches_terms(value: object, allowed: tuple[str, ...]) -> bool:
    if not allowed:
        return True
    if value is None:
        return False
    if isinstance(value, (list, tuple, set)):
        return any(str(v) in allowed for v in value)
    return str(value) in allowed


def _parse_date(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(float(value))
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def hit_matches_filter(hit: SearchHit, flt: SearchFilter) -> bool:
    """True if a hit's meta satisfies all filter constraints."""
    if flt.is_empty():
        return True
    meta = hit.meta or {}

    if not _matches_terms(meta.get("source"), flt.sources):
        return False
    if not _matches_terms(meta.get("language"), flt.languages):
        return False
    if not _matches_terms(meta.get("author"), flt.authors):
        return False
    if not _matches_terms(meta.get("tags"), flt.tags):
        return False

    if flt.date_from or flt.date_to:
        dt = _parse_date(meta.get("created_at") or meta.get("date"))
        if dt is None:
            return False
        if flt.date_from and dt < flt.date_from:
            return False
        if flt.date_to and dt > flt.date_to:
            return False
    return True


def apply_filter(hits: Iterable[SearchHit], flt: SearchFilter) -> list[SearchHit]:
    """Return only hits matching the filter."""
    if flt.is_empty():
        return list(hits)
    return [h for h in hits if hit_matches_filter(h, flt)]
