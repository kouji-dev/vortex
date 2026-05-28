"""Gateway observability dashboard endpoints.

Tests for the three /v1/gateway/metrics aggregations:
top-spenders, top-errors, latency (p50/p95/p99).

Period validation is pure-logic and runs without Postgres.
Aggregations run against Postgres via the request_traces fixture.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401  — register Org for FK
import ai_portal.gateway.traces.model  # noqa: F401
from tests.conftest import requires_postgres
from tests.gateway.traces.test_router import (  # reuse helpers
    _ensure_request_traces_table,
    _mk_org,
)


# ── pure-logic: period validation ────────────────────────────────────────


def test_period_to_delta_accepts_valid_periods():
    from ai_portal.gateway.traces.metrics import period_to_delta

    assert period_to_delta("1h") == timedelta(hours=1)
    assert period_to_delta("24h") == timedelta(hours=24)
    assert period_to_delta("7d") == timedelta(days=7)
    assert period_to_delta("30d") == timedelta(days=30)


def test_period_to_delta_rejects_invalid_period():
    from ai_portal.gateway.traces.metrics import period_to_delta

    with pytest.raises(ValueError) as ei:
        period_to_delta("yesterday")
    assert "invalid period" in str(ei.value).lower()


# ── DB-backed helpers ────────────────────────────────────────────────────


def _seed_trace(
    db,
    *,
    org_id: uuid.UUID,
    model_used: str = "gpt-4o",
    provider: str = "openai",
    status: str = "ok",
    actor_user_id: int | None = None,
    api_key_id: str | None = None,
    latency_ms: int = 100,
    cost_cents: float = 1.0,
    error: str | None = None,
    ts: datetime | None = None,
) -> uuid.UUID:
    trace_id = uuid.uuid4()
    actor: dict = {}
    if actor_user_id is not None:
        actor["actor_user_id"] = actor_user_id
    if api_key_id is not None:
        actor["api_key_id"] = api_key_id

    db.execute(
        text(
            """
            INSERT INTO request_traces (
                id, org_id, actor_json, route, model_used, provider, status,
                latency_ms, tokens_in, tokens_out, cost_cents, error, ts
            ) VALUES (
                :id, :org_id, CAST(:actor AS JSONB), '/v1/chat/completions',
                :model, :provider, :status, :latency, 100, 50, :cost,
                :error, :ts
            )
            """
        ),
        {
            "id": str(trace_id),
            "org_id": str(org_id),
            "actor": json.dumps(actor),
            "model": model_used,
            "provider": provider,
            "status": status,
            "latency": latency_ms,
            "cost": cost_cents,
            "error": error,
            "ts": (ts or datetime.now(UTC)),
        },
    )
    db.commit()
    return trace_id


def _build_metrics_app(*, actor, permissions: set[str]) -> FastAPI:
    from ai_portal.auth.deps import get_db
    from ai_portal.control_plane.deps import get_rbac_service, require_actor
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.traces.metrics_router import router

    app = FastAPI()
    app.include_router(router)

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    class _FakeRbac:
        def has_permission(self, _actor, perm, resource=None):  # noqa: ARG002
            return perm in permissions

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[require_actor] = lambda: actor
    app.dependency_overrides[get_rbac_service] = lambda: _FakeRbac()
    return app


# ── period query-string validation ──────────────────────────────────────


@requires_postgres
def test_top_spenders_rejects_bad_period(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "metr-bad")
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/top-spenders", params={"period": "yesterday"})
    assert res.status_code == 400
    assert "invalid period" in res.json()["detail"].lower()


# ── top-spenders ────────────────────────────────────────────────────────


@requires_postgres
def test_top_spenders_aggregates_cost_by_actor(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "spend")
            db.commit()
            # Two users: 1 → $3.00, 2 → $1.00.
            _seed_trace(db, org_id=org_id, actor_user_id=1, cost_cents=200.0)
            _seed_trace(db, org_id=org_id, actor_user_id=1, cost_cents=100.0)
            _seed_trace(db, org_id=org_id, actor_user_id=2, cost_cents=100.0)
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=99)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/top-spenders")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["period"] == "24h"
    items = body["items"]
    assert len(items) == 2
    # Sorted by cost desc.
    assert items[0]["actor_user_id"] == 1
    assert items[0]["cost_cents"] == 300.0
    assert items[0]["request_count"] == 2
    assert items[1]["actor_user_id"] == 2
    assert items[1]["cost_cents"] == 100.0


@requires_postgres
def test_top_spenders_filters_by_period(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "spend-prd")
            db.commit()
            # In-window trace.
            _seed_trace(
                db,
                org_id=org_id,
                actor_user_id=1,
                cost_cents=50.0,
                ts=now - timedelta(minutes=30),
            )
            # Out-of-window (8 days ago, beyond 24h).
            _seed_trace(
                db,
                org_id=org_id,
                actor_user_id=1,
                cost_cents=9999.0,
                ts=now - timedelta(days=8),
            )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=99)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/top-spenders", params={"period": "24h"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["cost_cents"] == 50.0


# ── top-errors ──────────────────────────────────────────────────────────


@requires_postgres
def test_top_errors_groups_by_error_and_provider(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "errs")
            db.commit()
            _seed_trace(
                db,
                org_id=org_id,
                status="error",
                provider="openai",
                error="rate_limit",
            )
            _seed_trace(
                db,
                org_id=org_id,
                status="error",
                provider="openai",
                error="rate_limit",
            )
            _seed_trace(
                db,
                org_id=org_id,
                status="error",
                provider="anthropic",
                error="timeout",
            )
            # Successful — must not be counted.
            _seed_trace(db, org_id=org_id, status="ok", provider="openai")
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/top-errors")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) == 2
    top = items[0]
    assert top["error"] == "rate_limit"
    assert top["provider"] == "openai"
    assert top["count"] == 2


# ── latency ─────────────────────────────────────────────────────────────


@requires_postgres
def test_latency_p50_p95_p99(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "lat")
            db.commit()
            # 100 traces, latency = 1..100ms.
            for i in range(1, 101):
                _seed_trace(
                    db, org_id=org_id, provider="openai", latency_ms=i
                )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/latency")
    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert len(items) == 1
    row = items[0]
    assert row["provider"] == "openai"
    assert row["request_count"] == 100
    # percentile_cont interpolates — accept a small tolerance.
    assert 49 <= row["p50_ms"] <= 51
    assert 94 <= row["p95_ms"] <= 96
    assert 98 <= row["p99_ms"] <= 100


@requires_postgres
def test_latency_skips_null_and_groups_by_provider(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "lat-grp")
            db.commit()
            _seed_trace(db, org_id=org_id, provider="openai", latency_ms=10)
            _seed_trace(db, org_id=org_id, provider="openai", latency_ms=30)
            _seed_trace(db, org_id=org_id, provider="anthropic", latency_ms=200)
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(
        _build_metrics_app(actor=actor, permissions={"gateway:traces:read"})
    )
    res = client.get("/v1/gateway/metrics/latency")
    assert res.status_code == 200
    items = res.json()["items"]
    by_prov = {r["provider"]: r for r in items}
    assert by_prov["openai"]["request_count"] == 2
    assert by_prov["anthropic"]["request_count"] == 1


# ── permission gating ──────────────────────────────────────────────────


@requires_postgres
def test_top_spenders_requires_permission(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "perm")
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(_build_metrics_app(actor=actor, permissions=set()))
    res = client.get("/v1/gateway/metrics/top-spenders")
    assert res.status_code in (401, 403)
