"""Usage metering — record_usage writes a row with correct cost."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import requires_postgres


@requires_postgres
def test_record_usage_creates_row_with_cost():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.usage.service import record_usage
    from ai_portal.usage.model import MessageUsage

    db = SessionLocal()
    try:
        org_id = uuid.uuid4()
        row = record_usage(
            db,
            org_id=org_id,
            user_id=1,
            conversation_id=None,
            message_id=None,
            api_model_id="claude-sonnet-4-6",
            usage={
                "input_tokens": 1000,
                "output_tokens": 500,
                "cached_input_tokens": 200,
            },
            latency_ms=800,
        )

        assert row.id is not None
        assert row.input_tokens == 1000
        assert row.output_tokens == 500
        assert row.cached_input_tokens == 200
        # Cost should be > 0 (model has non-zero pricing).
        assert float(row.cost_usd) > 0

        # Confirm in DB.
        with bypass_rls(db):
            fetched = db.get(MessageUsage, row.id)
        assert fetched is not None
        assert fetched.provider == "anthropic"

    finally:
        db.close()


@requires_postgres
def test_record_usage_unknown_model_yields_zero_cost():
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.usage.service import record_usage

    db = SessionLocal()
    try:
        row = record_usage(
            db,
            org_id=uuid.uuid4(),
            user_id=None,
            conversation_id=None,
            message_id=None,
            api_model_id="totally-unknown-model-xyz",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        # Unknown model → cost table has no entry → $0.
        assert float(row.cost_usd) == 0.0
    finally:
        db.close()


def test_compute_cost_usd_anthropic():
    """Pricing is deterministic for known models."""
    from ai_portal.usage.pricing import compute_cost_usd
    from decimal import Decimal

    cost = compute_cost_usd(
        "claude-sonnet-4-6",
        input_tokens=1_000_000,
        output_tokens=0,
        cached_input_tokens=0,
        cache_creation_input_tokens=0,
    )
    # claude-sonnet-4-6 input price is $3/Mtok = $3 for 1M tokens
    assert cost == Decimal("3.000000")


def test_compute_cost_usd_cache_discount():
    """Cached tokens are cheaper than uncached input tokens."""
    from ai_portal.usage.pricing import compute_cost_usd

    cost_full = compute_cost_usd("claude-sonnet-4-6", 1000, 0, 0, 0)
    cost_cached = compute_cost_usd("claude-sonnet-4-6", 0, 0, 1000, 0)
    assert cost_cached < cost_full
