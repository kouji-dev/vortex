"""I2: evals router — test set CRUD + run + list runs.

Uses ``dependency_overrides[get_evals_service]`` with an in-memory stub so
tests don't depend on Postgres. The /run path delegates to the real
:class:`EvalRunner` through a stubbed facade so the wire format used by
the UI is locked down end-to-end.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.evals.router import (
    get_evals_service,
)
from ai_portal.gateway.evals.router import (
    router as evals_router,
)
from ai_portal.gateway.evals.schemas import (
    EvalRecord,
    EvalRunRowResult,
    EvalRunSummary,
)
from ai_portal.gateway.evals.service import EvalRunView, EvalView
from ai_portal.gateway.facade import (
    FacadeConfig,
    GatewayFacade,
    set_default_facade,
)
from ai_portal.gateway.types import (
    Capability,
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
        # Echo "ok" for everything so exact-match passes when expected=="ok".
        return LLMResponse(
            id="r_1",
            model_used=req.model,
            provider=self.name,
            content=[TextBlock(text="ok")],
            tool_calls=[],
            usage=Usage(input_tokens=4, output_tokens=1),
            stop_reason="end_turn",
            raw={},
        )

    async def stream_canonical(
        self, req: LLMRequest
    ) -> AsyncIterator[StreamChunk]:  # pragma: no cover
        if False:
            yield StreamChunk.model_validate({"type": "text_delta", "text": ""})


def _build_app(actor: Actor):
    from ai_portal.control_plane.deps import require_actor
    from ai_portal.gateway.evals.runner import EvalRunner, make_actor_for_run

    app = FastAPI()
    app.include_router(evals_router)

    eval_store: dict[uuid.UUID, EvalView] = {}
    run_store: dict[uuid.UUID, list[EvalRunView]] = {}

    class _Svc:
        # ── eval CRUD ────────────────────────────────────────────────
        def list_evals(self, *, org_id):  # noqa: ARG002
            return list(eval_store.values())

        def create_eval(self, *, org_id, name, records):  # noqa: ARG002
            eid = uuid.uuid4()
            now = datetime.now(UTC)
            view = EvalView(
                id=eid,
                name=name,
                records=list(records),
                created_at=now,
                updated_at=now,
            )
            eval_store[eid] = view
            return view

        def update_eval(self, *, org_id, eval_id, name=None, records=None):  # noqa: ARG002
            cur = eval_store.get(eval_id)
            if cur is None:
                return None
            new = EvalView(
                id=cur.id,
                name=name if name is not None else cur.name,
                records=list(records) if records is not None else cur.records,
                created_at=cur.created_at,
                updated_at=datetime.now(UTC),
            )
            eval_store[eval_id] = new
            return new

        def get_eval(self, *, org_id, eval_id):  # noqa: ARG002
            return eval_store.get(eval_id)

        def delete_eval(self, *, org_id, eval_id):  # noqa: ARG002
            return eval_store.pop(eval_id, None) is not None

        # ── runs ─────────────────────────────────────────────────────
        def list_runs(self, *, org_id, eval_id):  # noqa: ARG002
            return list(run_store.get(eval_id, []))

        def get_previous_run(self, *, org_id, eval_id, target_model):  # noqa: ARG002
            runs = [
                r for r in run_store.get(eval_id, []) if r.target_model == target_model
            ]
            return runs[-1] if runs else None

        async def run_eval(
            self,
            *,
            org_id,
            eval_id,
            target_models,
            user_id,
            regression_threshold=0.05,
        ):
            view = eval_store.get(eval_id)
            if view is None:
                return []
            runner = EvalRunner(regression_threshold=regression_threshold)
            actor = make_actor_for_run(org_id=org_id, user_id=user_id)
            out: list[EvalRunView] = []
            for m in target_models:
                outcome = await runner.run(
                    records=view.records, target_model=m, actor=actor
                )
                prev = self.get_previous_run(
                    org_id=org_id, eval_id=eval_id, target_model=m
                )
                outcome.summary = runner.detect_regression(
                    current=outcome.summary,
                    previous=prev.summary if prev else None,
                )
                rv = EvalRunView(
                    id=uuid.uuid4(),
                    eval_id=eval_id,
                    target_model=outcome.target_model,
                    summary=outcome.summary,
                    results=outcome.results,
                    ran_at=datetime.now(UTC),
                )
                run_store.setdefault(eval_id, []).append(rv)
                out.append(rv)
            return out

    svc = _Svc()
    app.dependency_overrides[get_evals_service] = lambda: svc
    app.dependency_overrides[require_actor] = lambda: actor
    return app


def _actor() -> Actor:
    return Actor(
        org_id=uuid.UUID("00000000-0000-0000-0000-0000000000aa"),
        kind="user",
        user_id=42,
    )


# ── tests ────────────────────────────────────────────────────────────────


def test_create_then_get_roundtrips_records() -> None:
    app = _build_app(_actor())
    client = TestClient(app)

    res = client.post(
        "/v1/gateway/evals",
        json={
            "name": "math",
            "records": [
                {"id": "r1", "input": "2+2=", "expected": "4", "judge": "exact"},
                {"id": "r2", "input": "3+3=", "expected": "6", "judge": "exact"},
            ],
        },
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["name"] == "math"
    assert len(body["records"]) == 2
    eid = body["id"]

    res = client.get(f"/v1/gateway/evals/{eid}")
    assert res.status_code == 200
    assert len(res.json()["records"]) == 2


def test_list_returns_saved_evals() -> None:
    app = _build_app(_actor())
    client = TestClient(app)
    for name in ("a", "b"):
        client.post(
            "/v1/gateway/evals",
            json={"name": name, "records": []},
        )
    res = client.get("/v1/gateway/evals")
    assert res.status_code == 200
    names = {row["name"] for row in res.json()}
    assert names == {"a", "b"}


def test_update_replaces_records() -> None:
    app = _build_app(_actor())
    client = TestClient(app)
    res = client.post(
        "/v1/gateway/evals",
        json={"name": "x", "records": []},
    )
    eid = res.json()["id"]
    res = client.put(
        f"/v1/gateway/evals/{eid}",
        json={
            "name": "x2",
            "records": [{"id": "r1", "input": "i", "expected": "e", "judge": "exact"}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "x2"
    assert len(body["records"]) == 1


def test_delete_removes_eval() -> None:
    app = _build_app(_actor())
    client = TestClient(app)
    res = client.post("/v1/gateway/evals", json={"name": "tmp", "records": []})
    eid = res.json()["id"]
    res = client.delete(f"/v1/gateway/evals/{eid}")
    assert res.status_code == 204
    res = client.get(f"/v1/gateway/evals/{eid}")
    assert res.status_code == 404


def test_run_endpoint_executes_and_returns_summary() -> None:
    cfg = FacadeConfig(resolve_provider=lambda _req, _actor: _StubProvider())
    facade = GatewayFacade(cfg)
    prev = set_default_facade(facade)
    try:
        app = _build_app(_actor())
        client = TestClient(app)

        res = client.post(
            "/v1/gateway/evals",
            json={
                "name": "ok-set",
                "records": [
                    {"id": "r1", "input": "say ok", "expected": "ok", "judge": "exact"},
                    {
                        "id": "r2",
                        "input": "say ok again",
                        "expected": "ok",
                        "judge": "exact",
                    },
                ],
            },
        )
        eid = res.json()["id"]

        res = client.post(
            f"/v1/gateway/evals/{eid}/run",
            json={"target_models": ["gpt-4o", "claude-sonnet-4-6"]},
        )
        assert res.status_code == 200, res.text
        body = res.json()
        assert len(body["runs"]) == 2
        for run in body["runs"]:
            assert run["summary"]["passed"] == 2
            assert run["summary"]["pass_rate"] == pytest.approx(1.0)
            assert len(run["results"]) == 2
    finally:
        set_default_facade(prev)


def test_runs_listing_returns_persisted_runs() -> None:
    cfg = FacadeConfig(resolve_provider=lambda _req, _actor: _StubProvider())
    facade = GatewayFacade(cfg)
    prev = set_default_facade(facade)
    try:
        app = _build_app(_actor())
        client = TestClient(app)
        res = client.post(
            "/v1/gateway/evals",
            json={
                "name": "rs",
                "records": [
                    {"id": "r1", "input": "x", "expected": "ok", "judge": "exact"}
                ],
            },
        )
        eid = res.json()["id"]
        client.post(f"/v1/gateway/evals/{eid}/run", json={"target_models": ["gpt-4o"]})
        client.post(f"/v1/gateway/evals/{eid}/run", json={"target_models": ["gpt-4o"]})
        res = client.get(f"/v1/gateway/evals/{eid}/runs")
        assert res.status_code == 200
        assert len(res.json()) == 2
    finally:
        set_default_facade(prev)


def test_run_on_missing_eval_returns_404() -> None:
    cfg = FacadeConfig(resolve_provider=lambda _req, _actor: _StubProvider())
    facade = GatewayFacade(cfg)
    prev = set_default_facade(facade)
    try:
        app = _build_app(_actor())
        client = TestClient(app)
        res = client.post(
            f"/v1/gateway/evals/{uuid.uuid4()}/run",
            json={"target_models": ["gpt-4o"]},
        )
        assert res.status_code == 404
    finally:
        set_default_facade(prev)


# Reference the unused symbols so mypy/lint don't whine.
_ = (EvalRecord, EvalRunRowResult, EvalRunSummary)
