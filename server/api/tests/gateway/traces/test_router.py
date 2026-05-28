"""H3: gateway traces — search + replay router.

Verifies:

- ``GET /v1/gateway/traces`` filters by model / status / actor + time range,
  paginates via cursor.
- ``GET /v1/gateway/traces/{id}`` returns full row.
- ``POST /v1/gateway/traces/{id}/replay`` re-runs through a fake provider,
  writes a *new* trace row, optionally swaps the model.
- Permission gating: ``gateway:traces:read`` for GET, ``gateway:replay`` for
  POST.

All HTTP traffic goes through a tiny standalone FastAPI app — same pattern
as the existing ``test_limits_me.py`` — so the tests don't depend on
``main.py`` wiring.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401  — register Org for FK
import ai_portal.gateway.traces.model  # noqa: F401
from tests.conftest import requires_postgres

# ── shared fake provider for replay tests ────────────────────────────────


class _FakeProvider:
    """Captures last LLMRequest; returns a canned LLMResponse."""

    name = "fake"

    def __init__(self) -> None:
        from ai_portal.gateway.types import Capability

        self.capabilities: set[Capability] = {"chat"}
        self.last_request = None

    async def complete_canonical(self, req):
        from ai_portal.gateway.types import LLMResponse, TextBlock, Usage

        self.last_request = req
        return LLMResponse(
            id=f"resp_{uuid.uuid4().hex[:8]}",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text="ok")],
            tool_calls=[],
            usage=Usage(input_tokens=10, output_tokens=5, total_tokens=15),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(self, req):  # pragma: no cover
        raise NotImplementedError

    async def embed(self, texts, model):  # pragma: no cover
        raise NotImplementedError


# ── helpers ──────────────────────────────────────────────────────────────


def _ensure_request_traces_table(engine) -> None:
    """Idempotent CREATE TABLE matching the alembic migration + the
    request_json column added for replay support.
    """

    def _next_month(d):
        year = d.year + (d.month // 12)
        month = (d.month % 12) + 1
        return d.replace(
            year=year, month=month, day=1, hour=0, minute=0, second=0, microsecond=0
        )

    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT to_regclass('public.request_traces')")
        ).scalar()
        if not exists:
            conn.execute(
                text(
                    """
                    CREATE TABLE request_traces (
                        id UUID NOT NULL DEFAULT gen_random_uuid(),
                        org_id UUID NOT NULL REFERENCES orgs(id) ON DELETE CASCADE,
                        actor_json JSONB NOT NULL DEFAULT '{}'::jsonb,
                        route VARCHAR(64) NOT NULL,
                        model_requested VARCHAR(128),
                        model_used VARCHAR(128),
                        provider VARCHAR(32),
                        status VARCHAR(16) NOT NULL DEFAULT 'ok',
                        latency_ms INTEGER,
                        ttft_ms INTEGER,
                        tokens_in INTEGER NOT NULL DEFAULT 0,
                        tokens_out INTEGER NOT NULL DEFAULT 0,
                        tokens_cache_read INTEGER NOT NULL DEFAULT 0,
                        tokens_cache_write INTEGER NOT NULL DEFAULT 0,
                        cost_cents NUMERIC(14, 6) NOT NULL DEFAULT 0,
                        cache_hit BOOLEAN NOT NULL DEFAULT FALSE,
                        error TEXT,
                        request_hash VARCHAR(64),
                        request_json JSONB,
                        ts TIMESTAMPTZ NOT NULL DEFAULT now(),
                        PRIMARY KEY (id, ts)
                    ) PARTITION BY RANGE (ts)
                    """
                )
            )
            now = datetime.now(UTC).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            prev_month = (now - timedelta(days=1)).replace(
                day=1, hour=0, minute=0, second=0, microsecond=0
            )
            months = [prev_month, now, _next_month(now), _next_month(_next_month(now))]
            for start in months:
                end = _next_month(start)
                name = f"request_traces_{start.strftime('%Y_%m')}"
                conn.execute(
                    text(
                        f"CREATE TABLE {name} PARTITION OF request_traces "
                        f"FOR VALUES FROM ('{start.isoformat()}') TO ('{end.isoformat()}')"
                    )
                )
            conn.execute(
                text(
                    "CREATE TABLE request_traces_default PARTITION OF request_traces DEFAULT"
                )
            )
            conn.commit()
        else:
            # Existing table — ensure request_json column exists.
            conn.execute(
                text(
                    "ALTER TABLE request_traces ADD COLUMN IF NOT EXISTS request_json JSONB"
                )
            )
            conn.commit()


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'TR') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def _seed_trace(
    db,
    *,
    org_id: uuid.UUID,
    model_used: str = "gpt-4o",
    provider: str = "openai",
    status: str = "ok",
    actor_user_id: int | None = 42,
    ts: datetime | None = None,
    request_json: dict | None = None,
    tokens_in: int = 100,
    tokens_out: int = 50,
    cost_cents: float = 1.0,
) -> uuid.UUID:
    """Insert one trace row directly. Returns id."""
    trace_id = uuid.uuid4()
    actor: dict = {}
    if actor_user_id is not None:
        actor["actor_user_id"] = actor_user_id
    db.execute(
        text(
            """
            INSERT INTO request_traces (
                id, org_id, actor_json, route, model_requested, model_used,
                provider, status, latency_ms, tokens_in, tokens_out, cost_cents,
                request_json, ts
            ) VALUES (
                :id, :org_id, CAST(:actor AS JSONB), :route, :model, :model,
                :provider, :status, 100, :tokens_in, :tokens_out, :cost_cents,
                CAST(:req AS JSONB), :ts
            )
            """
        ),
        {
            "id": str(trace_id),
            "org_id": str(org_id),
            "actor": __import__("json").dumps(actor),
            "route": "/v1/chat/completions",
            "model": model_used,
            "provider": provider,
            "status": status,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "cost_cents": cost_cents,
            "req": __import__("json").dumps(request_json or {}),
            "ts": (ts or datetime.now(UTC)),
        },
    )
    db.commit()
    return trace_id


def _build_app(*, actor, permissions: set[str], provider=None) -> FastAPI:
    """Standalone app exposing only the traces router."""
    from ai_portal.auth.deps import get_db
    from ai_portal.control_plane.deps import get_rbac_service, require_actor
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway import service as gateway_service
    from ai_portal.gateway.traces.router import router

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
    if provider is not None:
        app.dependency_overrides[gateway_service.get_llm_provider] = lambda: provider
    return app


# ── tests: search ────────────────────────────────────────────────────────


@requires_postgres
def test_search_filters_by_model(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-model")
            db.commit()
            _seed_trace(db, org_id=org_id, model_used="gpt-4o")
            _seed_trace(db, org_id=org_id, model_used="gpt-4o")
            _seed_trace(db, org_id=org_id, model_used="claude-sonnet-4-6")
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    res = client.get("/v1/gateway/traces", params={"model": "gpt-4o"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert len(body["items"]) == 2
    assert all(r["model_used"] == "gpt-4o" for r in body["items"])


@requires_postgres
def test_search_filters_by_status_and_actor(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-sa")
            db.commit()
            _seed_trace(db, org_id=org_id, status="ok", actor_user_id=10)
            _seed_trace(db, org_id=org_id, status="error", actor_user_id=10)
            _seed_trace(db, org_id=org_id, status="ok", actor_user_id=99)
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    res = client.get("/v1/gateway/traces", params={"status": "error"})
    assert res.status_code == 200
    rows = res.json()["items"]
    assert len(rows) == 1
    assert rows[0]["status"] == "error"

    res2 = client.get("/v1/gateway/traces", params={"actor_user_id": 10})
    assert res2.status_code == 200
    rows2 = res2.json()["items"]
    assert len(rows2) == 2
    assert all(r["actor_json"]["actor_user_id"] == 10 for r in rows2)


@requires_postgres
def test_search_filters_by_time_range(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-time")
            db.commit()
            _seed_trace(db, org_id=org_id, ts=now - timedelta(days=5))
            _seed_trace(db, org_id=org_id, ts=now - timedelta(hours=1))
            _seed_trace(db, org_id=org_id, ts=now - timedelta(minutes=1))
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    since = (now - timedelta(hours=2)).isoformat()
    res = client.get("/v1/gateway/traces", params={"from": since})
    assert res.status_code == 200
    rows = res.json()["items"]
    assert len(rows) == 2


@requires_postgres
def test_search_paginates_with_cursor(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    now = datetime.now(UTC)
    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-page")
            db.commit()
            for i in range(5):
                _seed_trace(
                    db,
                    org_id=org_id,
                    model_used=f"m{i}",
                    ts=now - timedelta(minutes=i),
                )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    res1 = client.get("/v1/gateway/traces", params={"limit": 2})
    assert res1.status_code == 200
    body1 = res1.json()
    assert len(body1["items"]) == 2
    assert body1["next_cursor"] is not None

    res2 = client.get(
        "/v1/gateway/traces", params={"limit": 2, "cursor": body1["next_cursor"]}
    )
    assert res2.status_code == 200
    body2 = res2.json()
    assert len(body2["items"]) == 2
    # Disjoint pages.
    ids1 = {r["id"] for r in body1["items"]}
    ids2 = {r["id"] for r in body2["items"]}
    assert not (ids1 & ids2)


# ── tests: get one ───────────────────────────────────────────────────────


@requires_postgres
def test_get_trace_returns_full_detail(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-get")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                model_used="claude-sonnet-4-6",
                request_json={
                    "model": "claude-sonnet-4-6",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    res = client.get(f"/v1/gateway/traces/{tid}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] == str(tid)
    assert body["model_used"] == "claude-sonnet-4-6"
    assert body["request_json"]["model"] == "claude-sonnet-4-6"


@requires_postgres
def test_get_trace_404_for_other_org(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_a = _mk_org(db, "tr-a")
            org_b = _mk_org(db, "tr-b")
            db.commit()
            tid = _seed_trace(db, org_id=org_a)
    finally:
        db.close()

    actor = Actor(org_id=org_b, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions={"gateway:traces:read"})
    client = TestClient(app)

    res = client.get(f"/v1/gateway/traces/{tid}")
    assert res.status_code == 404


# ── tests: replay ────────────────────────────────────────────────────────


@requires_postgres
def test_replay_creates_new_trace_row(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.traces.model import RequestTrace
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-rep")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                model_used="gpt-4o",
                request_json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "ping"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )
    finally:
        db.close()

    provider = _FakeProvider()
    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(
        actor=actor,
        permissions={"gateway:traces:read", "gateway:replay"},
        provider=provider,
    )
    client = TestClient(app)

    res = client.post(f"/v1/gateway/traces/{tid}/replay")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["trace_id"] != str(tid)
    assert body["model_used"] == "gpt-4o"
    assert provider.last_request is not None
    assert provider.last_request.model == "gpt-4o"

    # New row landed.
    from sqlalchemy import select

    db = SessionLocal()
    try:
        with bypass_rls(db):
            row = db.scalar(
                select(RequestTrace).where(
                    RequestTrace.id == uuid.UUID(body["trace_id"])
                )
            )
            assert row is not None
            assert row.model_used == "gpt-4o"
            assert row.org_id == org_id
    finally:
        db.close()


@requires_postgres
def test_replay_swaps_model(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-swap")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                model_used="gpt-4o",
                request_json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "hi"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )
    finally:
        db.close()

    provider = _FakeProvider()
    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(
        actor=actor,
        permissions={"gateway:traces:read", "gateway:replay"},
        provider=provider,
    )
    client = TestClient(app)

    res = client.post(
        f"/v1/gateway/traces/{tid}/replay",
        params={"model": "claude-sonnet-4-6"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model_used"] == "claude-sonnet-4-6"
    # Provider received the swapped model.
    assert provider.last_request.model == "claude-sonnet-4-6"


@requires_postgres
def test_replay_records_routing_policy_override(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-pol")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                request_json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "x"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )
    finally:
        db.close()

    provider = _FakeProvider()
    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(
        actor=actor,
        permissions={"gateway:traces:read", "gateway:replay"},
        provider=provider,
    )
    client = TestClient(app)

    policy_id = str(uuid.uuid4())
    res = client.post(
        f"/v1/gateway/traces/{tid}/replay",
        params={"routing_policy_id": policy_id},
    )
    assert res.status_code == 200, res.text
    # Override flows into the canonical request metadata so downstream
    # routing logic can pick it up.
    assert provider.last_request is not None
    assert provider.last_request.metadata.get("routing_policy_id") == policy_id


# ── tests: permission gating ─────────────────────────────────────────────


@requires_postgres
def test_search_requires_traces_read_permission(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-perm")
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    app = _build_app(actor=actor, permissions=set())  # no perms
    client = TestClient(app)

    res = client.get("/v1/gateway/traces")
    assert res.status_code == 403


@requires_postgres
def test_replay_requires_replay_permission(sync_engine):
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-prep")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                request_json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "x"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    # Only traces:read — missing gateway:replay.
    app = _build_app(
        actor=actor,
        permissions={"gateway:traces:read"},
        provider=_FakeProvider(),
    )
    client = TestClient(app)

    res = client.post(f"/v1/gateway/traces/{tid}/replay")
    assert res.status_code == 403


# ── tests: service unit ──────────────────────────────────────────────────


@requires_postgres
def test_service_search_returns_paginated_rows(sync_engine):
    """Direct unit test of the service helper bypassing HTTP."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.traces.service import TracesService

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-svc")
            db.commit()
            for _ in range(3):
                _seed_trace(db, org_id=org_id, model_used="gpt-4o")
            svc = TracesService(db)
            page = svc.search(org_id=org_id, limit=10)
            assert len(page.items) == 3
            assert all(r.model_used == "gpt-4o" for r in page.items)
    finally:
        db.close()


@requires_postgres
def test_service_replay_uses_overrides(sync_engine):
    """Service replay applies model + policy overrides to LLMRequest."""
    import asyncio

    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.traces.service import TracesService

    _ensure_request_traces_table(sync_engine)

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "tr-svc-r")
            db.commit()
            tid = _seed_trace(
                db,
                org_id=org_id,
                request_json={
                    "model": "old",
                    "messages": [
                        {"role": "user", "content": [{"type": "text", "text": "y"}]}
                    ],
                    "stream": False,
                    "metadata": {},
                },
            )

            provider = _FakeProvider()
            svc = TracesService(db)
            new_id = asyncio.run(
                svc.replay(
                    org_id=org_id,
                    trace_id=tid,
                    provider=provider,
                    model_override="new",
                    routing_policy_id_override="pol-1",
                    actor_json={"actor_user_id": 1},
                )
            )
            assert new_id is not None
            assert new_id != tid
            assert provider.last_request.model == "new"
            assert provider.last_request.metadata["routing_policy_id"] == "pol-1"
    finally:
        db.close()


@pytest.mark.skip(reason="placeholder for future async writer-flush coverage")
def test_replay_emits_audit_and_usage():  # pragma: no cover
    pass
