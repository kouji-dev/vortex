"""B6: POST /v1/moderations — OpenAI-compatible shape.

Backend selection is policy-driven (per-org setting → openai|anthropic|
llamaguard). We use a stub moderator injected via the route dep.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ai_portal.gateway.moderations import (
    CATEGORIES,
    ModerationResult,
    Moderator,
)


class _StubModerator:
    """Flags inputs whose text contains ``"bad"``."""

    name = "stub"
    last_inputs: list[str] | None = None

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        _StubModerator.last_inputs = list(inputs)
        out = []
        for s in inputs:
            cats = {c: False for c in CATEGORIES}
            scores = {c: 0.0 for c in CATEGORIES}
            if "bad" in s:
                cats["hate"] = True
                scores["hate"] = 0.91
            out.append(
                ModerationResult(
                    flagged=any(cats.values()),
                    categories=cats,
                    category_scores=scores,
                )
            )
        return out


def _build_app(*, actor, moderator: Moderator) -> FastAPI:
    from ai_portal.control_plane.deps import require_actor
    from ai_portal.gateway.compat.moderations import (
        get_moderator,
        router,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_actor] = lambda: actor
    app.dependency_overrides[get_moderator] = lambda: moderator
    return app


@pytest.fixture(autouse=True)
def _reset_stub():
    _StubModerator.last_inputs = None
    yield


def test_moderations_string_input_flagged():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, moderator=_StubModerator()))
    res = client.post(
        "/v1/moderations", json={"input": "this is bad content"}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["model"]  # echoed
    assert isinstance(body["results"], list)
    assert len(body["results"]) == 1
    assert body["results"][0]["flagged"] is True
    assert body["results"][0]["categories"]["hate"] is True
    assert body["results"][0]["category_scores"]["hate"] > 0.5
    # Every OpenAI category must be present.
    for c in CATEGORIES:
        assert c in body["results"][0]["categories"]
        assert c in body["results"][0]["category_scores"]


def test_moderations_string_input_safe():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, moderator=_StubModerator()))
    res = client.post("/v1/moderations", json={"input": "good morning"})
    assert res.status_code == 200
    assert res.json()["results"][0]["flagged"] is False


def test_moderations_batch_list_input():
    """``input`` may be a list of strings — return one result per item."""
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, moderator=_StubModerator()))
    res = client.post(
        "/v1/moderations",
        json={"input": ["hello", "bad thing", "another bad one"]},
    )
    assert res.status_code == 200
    results = res.json()["results"]
    assert len(results) == 3
    assert results[0]["flagged"] is False
    assert results[1]["flagged"] is True
    assert results[2]["flagged"] is True
    assert _StubModerator.last_inputs == ["hello", "bad thing", "another bad one"]


def test_moderations_rejects_empty_input():
    from ai_portal.rbac.service import Actor

    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, moderator=_StubModerator()))
    res = client.post("/v1/moderations", json={"input": []})
    assert res.status_code == 422


def test_moderations_passes_model_through():
    from ai_portal.rbac.service import Actor

    class _Recorder(_StubModerator):
        last_model: str | None = None

        async def moderate(self, inputs, *, model=None):
            type(self).last_model = model
            return await super().moderate(inputs, model=model)

    rec = _Recorder()
    actor = Actor(org_id=uuid.uuid4(), kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor, moderator=rec))
    client.post(
        "/v1/moderations",
        json={"input": "x", "model": "omni-moderation-2024-09-26"},
    )
    assert _Recorder.last_model == "omni-moderation-2024-09-26"
