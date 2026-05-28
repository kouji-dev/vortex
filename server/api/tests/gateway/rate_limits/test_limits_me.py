"""D2: GET /v1/limits/me — introspect effective rate limits.

Builds a minimal FastAPI app around just :mod:`gateway.rate_limits.router`
+ the dep stubs it needs — this keeps the test independent of the rest of
``main.py`` (which has cross-module work in flight in sibling worktrees).
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import ai_portal.auth.model  # noqa: F401  — register Org for FK
import ai_portal.gateway.rate_limits.model  # noqa: F401
from tests.conftest import requires_postgres

# ── helpers ──────────────────────────────────────────────────────────────


def _mk_org(db: Session, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'LM') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def _build_app(*, actor) -> FastAPI:
    """Standalone app — only the limits/me route + auth stub."""
    from ai_portal.auth.deps import get_db
    from ai_portal.control_plane.deps import require_actor
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.router import router

    app = FastAPI()
    app.include_router(router)

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[require_actor] = lambda: actor
    return app


# ── tests ────────────────────────────────────────────────────────────────


@requires_postgres
def test_limits_me_returns_effective_rules_with_remaining():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import RateLimitService
    from ai_portal.rbac.service import Actor

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "lm-eff")
            svc = RateLimitService(db, bucket=bucket)
            svc.create(
                org_id=org_id,
                dimension="rpm",
                limit_value=60,
                period_seconds=60,
                burst=10,
                scope={},
            )
            svc.create(
                org_id=org_id,
                dimension="concurrent_requests",
                limit_value=5,
                period_seconds=1,
                scope={"actor_user_id": 42},
            )
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=42)
    app = _build_app(actor=actor)
    client = TestClient(app)

    res = client.get("/v1/limits/me")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["actor"]["org_id"] == str(org_id)
    assert body["actor"]["user_id"] == 42
    by_dim = {r["dimension"]: r for r in body["limits"]}
    assert "rpm" in by_dim
    assert "concurrent_requests" in by_dim
    assert by_dim["rpm"]["limit"] == 60
    assert by_dim["rpm"]["burst"] == 10
    # Bucket reset → remaining = capacity = limit + burst.
    assert by_dim["rpm"]["remaining"] == 70
    assert by_dim["concurrent_requests"]["limit"] == 5
    assert by_dim["concurrent_requests"]["remaining"] == 5


@requires_postgres
def test_limits_me_only_returns_rules_matching_actor_scope():
    """User-scoped rules don't leak to other actors in the same org."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import RateLimitService
    from ai_portal.rbac.service import Actor

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "lm-scope")
            svc = RateLimitService(db, bucket=bucket)
            # Rule that only applies to user 1.
            svc.create(
                org_id=org_id,
                dimension="rpm",
                limit_value=10,
                period_seconds=60,
                scope={"actor_user_id": 1},
            )
            db.commit()
    finally:
        db.close()

    # User 2 sees no matching rules.
    actor = Actor(org_id=org_id, kind="user", user_id=2)
    app = _build_app(actor=actor)
    client = TestClient(app)
    res = client.get("/v1/limits/me")
    assert res.status_code == 200
    assert res.json()["limits"] == []

    # User 1 sees the rule.
    actor1 = Actor(org_id=org_id, kind="user", user_id=1)
    app1 = _build_app(actor=actor1)
    res1 = TestClient(app1).get("/v1/limits/me")
    assert res1.status_code == 200
    assert len(res1.json()["limits"]) == 1
    assert res1.json()["limits"][0]["limit"] == 10


@requires_postgres
def test_limits_me_remaining_reflects_consumption():
    """After consuming N tokens, remaining drops by N."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.rate_limits.bucket import InMemoryBucket
    from ai_portal.gateway.rate_limits.service import RateLimitService
    from ai_portal.rbac.service import Actor

    bucket = InMemoryBucket()
    bucket.reset()

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "lm-cons")
            svc = RateLimitService(db, bucket=bucket)
            svc.create(
                org_id=org_id,
                dimension="rpm",
                limit_value=10,
                period_seconds=60,
                scope={},
            )
            db.commit()

            # Consume 3 against this user's bucket. limits/me must use the
            # *same* module-level in-memory bucket state to read remaining,
            # so we share via the default RateLimitService (no explicit
            # bucket arg — uses module-level state).
            shared = RateLimitService(db)  # uses module-level InMemory state
            for _ in range(3):
                shared.check(
                    org_id=org_id,
                    actor_scope={"actor_user_id": 99},
                    dimension="rpm",
                )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=99)
    app = _build_app(actor=actor)
    res = TestClient(app).get("/v1/limits/me")
    assert res.status_code == 200
    rpm = next(r for r in res.json()["limits"] if r["dimension"] == "rpm")
    # 10 capacity − 3 consumed = 7 remaining.
    assert rpm["remaining"] == 7
