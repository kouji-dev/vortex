"""Phase H1 — TTL + importance decay computation (pure functions)."""
from __future__ import annotations

from datetime import datetime, timedelta

from ai_portal.memory.decay import (
    DEFAULT_RETENTION_DAYS,
    compute_expires_at,
    decay_importance,
)


def test_episode_default_is_90_days() -> None:
    now = datetime(2026, 1, 1)
    exp = compute_expires_at("episode", now=now)
    assert exp == now + timedelta(days=90)


def test_preference_no_expiry() -> None:
    assert compute_expires_at("preference", now=datetime(2026, 1, 1)) is None


def test_pinned_overrides_ttl() -> None:
    assert compute_expires_at("episode", now=datetime(2026, 1, 1), pinned=True) is None


def test_org_retention_override() -> None:
    now = datetime(2026, 1, 1)
    exp = compute_expires_at("episode", retention_days={"episode": 7}, now=now)
    assert exp == now + timedelta(days=7)


def test_unknown_type_returns_none() -> None:
    assert compute_expires_at("unknown_thing") is None


def test_defaults_have_expected_keys() -> None:
    assert DEFAULT_RETENTION_DAYS["fact"] == 365
    assert DEFAULT_RETENTION_DAYS["episode"] == 90
    assert DEFAULT_RETENTION_DAYS["preference"] is None


def test_decay_importance_drops_over_time() -> None:
    fresh = decay_importance(0.8, days_since_use=0, recent_use_count=0)
    aged = decay_importance(0.8, days_since_use=90, recent_use_count=0)
    assert fresh > aged
    assert 0.0 <= aged <= 1.0


def test_decay_importance_boosted_by_uses() -> None:
    base = decay_importance(0.5, days_since_use=10, recent_use_count=0)
    used = decay_importance(0.5, days_since_use=10, recent_use_count=5)
    assert used > base


def test_decay_importance_clamped() -> None:
    val = decay_importance(0.99, days_since_use=0, recent_use_count=10000)
    assert val == 1.0
    val = decay_importance(0.0, days_since_use=1000, recent_use_count=0)
    assert val == 0.0
