"""I1: playground router — sessions CRUD + ``/run``.

Tests use a standalone FastAPI app with the service swapped via
``dependency_overrides[get_playground_service]`` so they don't depend on
Postgres. The router translates HTTP shapes to/from the service layer and
that is what we lock down — the persistence path is owned by the
:class:`PlaygroundSession` ORM model + alembic migration.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.facade import (
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.playground.router import (
    get_playground_service,
)
from ai_portal.gateway.playground.router import (
    router as playground_router,
)
from ai_portal.gateway.playground.service import SessionView
from ai_portal.gateway.types import (
    Capability,
    Embeddings,
    LLMRequest,
    LLMResponse,
    StreamChunk,
    TextBlock,
    Usage,
)
from ai_portal.rbac.service import Actor


class _StubProvider:
    name = "stub"
    capabilities: set[Capability] = {"chat"}

    async def complete_canonical(self, req: LLMRequest) -> LLMResponse:
        return LLMResponse(
            id="resp_1",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text=f"out:{req.model}")],
            tool_calls=[],
            usage=Usage(input_tokens=4, output_tokens=2),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:  # pragma: no cover
        if False:
            yield StreamChunk.model_validate({"type": "text_delta", "text": ""})

    async def embed(
        self, texts: list[str], model: str
    ) -> Embeddings:  # pragma: no cover
        raise NotImplementedError


def _build_app(actor: Actor):
    """Standalone app with an in-memory :class:`PlaygroundService` substitute.

    Uses ``dependency_overrides`` so the real service class is untouched.
    """
    from datetime import UTC, datetime

    from ai_portal.control_plane.deps import require_actor

    app = FastAPI()
    app.include_router(playground_router)

    store: dict[uuid.UUID, SessionView] = {}

    class _Svc:
        def list_sessions(self, *, org_id, user_id=None):  # noqa: ARG002
            return list(store.values())

        def create_session(self, *, org_id, user_id, name, snapshot):  # noqa: ARG002
            sid = uuid.uuid4()
            now = datetime.now(UTC)
            view = SessionView(
                id=sid,
                name=name or "",
                snapshot=dict(snapshot or {}),
                created_at=now,
                updated_at=now,
            )
            store[sid] = view
            return view

        def get_session(self, *, org_id, session_id):  # noqa: ARG002
            return store.get(session_id)

        def delete_session(self, *, org_id, session_id):  # noqa: ARG002
            return store.pop(session_id, None) is not None

        async def run_snapshot(self, *, org_id, user_id, snapshot):  # noqa: ARG002
            # Delegate to the real run_snapshot for facade dispatch coverage.
            from ai_portal.gateway.playground.service import PlaygroundService

            real = PlaygroundService(db=None)  # type: ignore[arg-type]
            return await real.run_snapshot(
                org_id=org_id, user_id=user_id, snapshot=snapshot
            )

    svc = _Svc()
    app.dependency_overrides[get_playground_service] = lambda: svc
    app.dependency_overrides[require_actor] = lambda: actor
    return app


def _actor() -> Actor:
    return Actor(
        org_id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        kind="user",
        user_id=42,
    )


# ── tests: sessions CRUD ─────────────────────────────────────────────────


def test_save_then_get_roundtrips_snapshot() -> None:
    app = _build_app(_actor())
    client = TestClient(app)

    snapshot = {
        "prompt": "hello",
        "system": "be brief",
        "model": "gpt-4o",
        "temperature": 0.3,
        "tools": [{"name": "search", "description": "web search"}],
    }
    res = client.post(
        "/v1/gateway/playground/sessions",
        json={"name": "exploration", "snapshot": snapshot},
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "exploration"
    assert body["snapshot"] == snapshot
    sid = body["id"]

    # Reload — same shape comes back.
    res = client.get(f"/v1/gateway/playground/sessions/{sid}")
    assert res.status_code == 200
    assert res.json()["snapshot"] == snapshot


def test_list_returns_saved_sessions() -> None:
    app = _build_app(_actor())
    client = TestClient(app)

    for name in ("alpha", "beta", "gamma"):
        res = client.post(
            "/v1/gateway/playground/sessions",
            json={"name": name, "snapshot": {"prompt": name}},
        )
        assert res.status_code == 201

    res = client.get("/v1/gateway/playground/sessions")
    assert res.status_code == 200
    names = {row["name"] for row in res.json()}
    assert names == {"alpha", "beta", "gamma"}


def test_get_missing_session_returns_404() -> None:
    app = _build_app(_actor())
    client = TestClient(app)
    res = client.get(f"/v1/gateway/playground/sessions/{uuid.uuid4()}")
    assert res.status_code == 404


def test_delete_session_removes_it() -> None:
    app = _build_app(_actor())
    client = TestClient(app)
    res = client.post(
        "/v1/gateway/playground/sessions",
        json={"name": "tmp", "snapshot": {"prompt": "x"}},
    )
    sid = res.json()["id"]
    res = client.delete(f"/v1/gateway/playground/sessions/{sid}")
    assert res.status_code == 204
    res = client.get(f"/v1/gateway/playground/sessions/{sid}")
    assert res.status_code == 404


# ── tests: run ───────────────────────────────────────────────────────────


def test_run_dispatches_via_facade_returns_results() -> None:
    cfg = FacadeConfig(
        resolve_provider=lambda _req, _actor: _StubProvider(),
    )
    facade = GatewayFacade(cfg)
    prev = set_default_facade(facade)
    try:
        app = _build_app(_actor())
        client = TestClient(app)
        res = client.post(
            "/v1/gateway/playground/run",
            json={
                "prompt": "hello",
                "models": ["gpt-4o", "claude-sonnet-4-6"],
            },
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert "results" in body
        assert len(body["results"]) == 2
        models = [r["model"] for r in body["results"]]
        assert "gpt-4o" in models
        assert "claude-sonnet-4-6" in models
        for r in body["results"]:
            assert r["output"].startswith("out:")
            assert r["tokens_in"] == 4
            assert r["tokens_out"] == 2
    finally:
        set_default_facade(prev)


def test_run_with_no_models_returns_empty_results() -> None:
    cfg = FacadeConfig(
        resolve_provider=lambda _req, _actor: _StubProvider(),
    )
    facade = GatewayFacade(cfg)
    prev = set_default_facade(facade)
    try:
        app = _build_app(_actor())
        client = TestClient(app)
        res = client.post("/v1/gateway/playground/run", json={"prompt": "hi"})
        assert res.status_code == 200
        assert res.json() == {"results": []}
    finally:
        set_default_facade(prev)
