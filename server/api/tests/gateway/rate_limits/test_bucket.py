"""D1: rate-limit token bucket + RateLimitService enforcement.

These tests are pure-Python (no DB) except for two integration cases that
exercise :class:`RateLimitService` via Postgres + RLS bypass.

Covered:

- Pure in-memory bucket: refill math + denial semantics + retry_after >= 1.
- 10 RPM rule: 10 requests pass, 11th returns ``RateLimitExceeded`` with
  ``Retry-After`` ≥ 1 second.
- ``concurrent_requests`` cap: N parallel requests pass, N+1 denied; after
  releasing one slot the next request passes again.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401  — register Org for FK
import ai_portal.gateway.rate_limits.model  # noqa: F401  — register table
from tests.conftest import requires_postgres

# ── pure bucket tests ───────────────────────────────────────────────────


def test_inmemory_bucket_allows_until_capacity_then_denies():
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket

    b = InMemoryBucket()
    b.reset()  # isolate from other tests
    key = f"bucket-{uuid.uuid4()}"

    # 10 RPM → capacity=10, refill≈0.166/s. At t=0 bucket starts full.
    out = []
    for _ in range(10):
        out.append(
            b.consume(
                key, capacity=10.0, refill_per_second=10 / 60, tokens=1.0, now=0.0
            )
        )
    assert all(r.allowed for r in out)
    # 11th call at the same instant → denied.
    denied = b.consume(
        key, capacity=10.0, refill_per_second=10 / 60, tokens=1.0, now=0.0
    )
    assert denied.allowed is False
    assert denied.retry_after >= 1
    # Remaining is 0 (we drained the bucket).
    assert denied.remaining == 0


def test_inmemory_bucket_refills_over_time():
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket

    b = InMemoryBucket()
    b.reset()
    key = f"bucket-refill-{uuid.uuid4()}"

    # Drain.
    for _ in range(5):
        b.consume(key, capacity=5.0, refill_per_second=1.0, tokens=1.0, now=0.0)
    denied = b.consume(key, capacity=5.0, refill_per_second=1.0, tokens=1.0, now=0.0)
    assert denied.allowed is False

    # 6 seconds later → bucket has refilled.
    ok = b.consume(key, capacity=5.0, refill_per_second=1.0, tokens=1.0, now=6.0)
    assert ok.allowed is True


def test_inmemory_bucket_release_returns_tokens():
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket

    b = InMemoryBucket()
    b.reset()
    key = f"bucket-release-{uuid.uuid4()}"

    # concurrent_requests: refill_rate=0, capacity=2.
    a = b.consume(key, capacity=2.0, refill_per_second=0.0, tokens=1.0, now=0.0)
    c = b.consume(key, capacity=2.0, refill_per_second=0.0, tokens=1.0, now=0.0)
    d = b.consume(key, capacity=2.0, refill_per_second=0.0, tokens=1.0, now=0.0)
    assert a.allowed and c.allowed
    assert d.allowed is False
    assert d.retry_after >= 1

    # Release one slot → next request passes.
    b.release(key, tokens=1.0)
    after = b.consume(key, capacity=2.0, refill_per_second=0.0, tokens=1.0, now=0.0)
    assert after.allowed is True


# ── DB-backed service tests ─────────────────────────────────────────────


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'RL') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_rpm_rule_allows_n_then_429s_with_retry_after():
    """10 RPM limit: 10 requests pass, 11th raises with Retry-After ≥ 1."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import (
        RateLimitExceeded,
        RateLimitService,
    )

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-rpm")
            svc = RateLimitService(db, bucket=bucket)
            rule = svc.create(
                org_id=org_id,
                dimension="rpm",
                limit_value=10,
                period_seconds=60,
                scope={"actor_user_id": 42},
            )
            assert rule.id is not None

            scope = {"actor_user_id": 42}
            # 10 requests pass.
            for _ in range(10):
                svc.check(
                    org_id=org_id,
                    actor_scope=scope,
                    dimension="rpm",
                    tokens=1,
                )

            # 11th raises with Retry-After.
            with pytest.raises(RateLimitExceeded) as exc:
                svc.check(
                    org_id=org_id,
                    actor_scope=scope,
                    dimension="rpm",
                    tokens=1,
                )
            assert exc.value.retry_after >= 1
            assert exc.value.dimension == "rpm"
            assert exc.value.limit == 10
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_concurrent_requests_caps_and_release_restores_slot():
    """concurrent_requests cap of 2 → 3rd request denied; release frees slot."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import (
        RateLimitExceeded,
        RateLimitService,
    )

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-conc")
            svc = RateLimitService(db, bucket=bucket)
            svc.create(
                org_id=org_id,
                dimension="concurrent_requests",
                limit_value=2,
                period_seconds=1,  # ignored for concurrent
                scope={"actor_user_id": 7},
            )
            scope = {"actor_user_id": 7}

            # Two in-flight requests OK.
            svc.check(
                org_id=org_id,
                actor_scope=scope,
                dimension="concurrent_requests",
            )
            svc.check(
                org_id=org_id,
                actor_scope=scope,
                dimension="concurrent_requests",
            )
            # Third denied.
            with pytest.raises(RateLimitExceeded) as exc:
                svc.check(
                    org_id=org_id,
                    actor_scope=scope,
                    dimension="concurrent_requests",
                )
            assert exc.value.dimension == "concurrent_requests"

            # Release one slot → next request passes.
            svc.release_concurrent(org_id=org_id, actor_scope=scope)
            svc.check(
                org_id=org_id,
                actor_scope=scope,
                dimension="concurrent_requests",
            )
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_scope_matching_separates_users():
    """User A's quota does not deplete User B's bucket."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import RateLimitService

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-scope")
            svc = RateLimitService(db, bucket=bucket)
            # Org-default rule (empty scope) — matches every user.
            svc.create(
                org_id=org_id,
                dimension="rpm",
                limit_value=2,
                period_seconds=60,
                scope={},
            )

            # User A drains.
            for _ in range(2):
                svc.check(
                    org_id=org_id,
                    actor_scope={"actor_user_id": 1},
                    dimension="rpm",
                )
            # User B still has full quota.
            views_b = svc.limits_for_actor(
                org_id=org_id, actor_scope={"actor_user_id": 2}
            )
            assert len(views_b) == 1
            assert views_b[0].remaining == 2
            db.commit()
    finally:
        db.rollback()
        db.close()
