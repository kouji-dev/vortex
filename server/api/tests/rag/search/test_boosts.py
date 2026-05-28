"""Boost behaviour: freshness decay + source priority."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_portal.rag.search.boosts import (
    apply_boosts,
    freshness_boost,
    source_priority_boost,
)
from ai_portal.rag.search.types import SearchHit


def _h(meta=None, score=1.0, cid="c"):
    return SearchHit(chunk_id=cid, document_id="d", kb_id=1, text="t", score=score, meta=meta or {})


def test_freshness_boost_recent_higher_than_old():
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    recent = _h({"created_at": (now - timedelta(days=1)).isoformat()})
    old = _h({"created_at": (now - timedelta(days=365)).isoformat()})
    assert freshness_boost(recent, now=now) > freshness_boost(old, now=now)


def test_freshness_boost_no_date_returns_one():
    assert freshness_boost(_h({})) == 1.0


def test_source_priority_boost_multiplies():
    weights = {"wiki": 2.0, "old": 0.5}
    assert source_priority_boost(_h({"source": "wiki"}), weights) == 2.0
    assert source_priority_boost(_h({"source": "old"}), weights) == 0.5
    # Unknown source → 1.0.
    assert source_priority_boost(_h({"source": "x"}), weights) == 1.0


def test_apply_boosts_reorders_by_freshness():
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    a = _h({"created_at": (now - timedelta(days=400)).isoformat()}, score=1.0, cid="old")
    b = _h({"created_at": now.isoformat()}, score=1.0, cid="new")
    out = apply_boosts([a, b], freshness=True, now=now)
    assert out[0].chunk_id == "new"


def test_apply_boosts_source_weights():
    a = _h({"source": "low"}, score=1.0, cid="a")
    b = _h({"source": "hi"}, score=1.0, cid="b")
    out = apply_boosts([a, b], source_weights={"hi": 3.0, "low": 1.0})
    assert out[0].chunk_id == "b"
    assert out[0].score == 3.0
