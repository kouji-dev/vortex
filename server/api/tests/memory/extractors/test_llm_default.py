"""Phase C3 — llm_default extractor.

Gateway facade is mocked: the test installs a fake ``gw_complete`` that
returns a canonical response with one text block of JSON.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_portal.memory.extractors import get, llm_default
from ai_portal.memory.extractors.llm_default import LlmDefaultExtractor
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn


def _fake_response(text: str) -> object:
    return SimpleNamespace(content=[{"type": "text", "text": text}])


@pytest.fixture
def scope() -> ExtractScope:
    return ExtractScope(
        org_id="00000000-0000-0000-0000-000000000001",
        actor_user_id="1",
        scope_kind="user",
        scope_id="1",
    )


@pytest.mark.asyncio
async def test_parses_one_memory(monkeypatch, scope) -> None:
    async def fake_complete(req, actor):
        return _fake_response(
            '{"memories":[{"type":"preference","text":"user likes typescript",'
            '"confidence":0.9,"source_turn_ids":["t-1"]}]}'
        )

    monkeypatch.setattr(llm_default, "gw_complete", fake_complete)
    e = LlmDefaultExtractor()
    out = await e.extract(
        [Turn(role="user", content="I like TS", turn_id="t-1")],
        scope,
        ExtractOpts(),
    )
    assert len(out) == 1
    assert out[0].type == "preference"
    assert out[0].confidence == 0.9
    assert out[0].source_turn_ids == ["t-1"]


@pytest.mark.asyncio
async def test_filters_disallowed_type(monkeypatch, scope) -> None:
    async def fake_complete(req, actor):
        return _fake_response(
            '{"memories":[{"type":"preference","text":"x","confidence":0.9,"source_turn_ids":[]},'
            '{"type":"unknown_type","text":"y","confidence":0.9,"source_turn_ids":[]}]}'
        )

    monkeypatch.setattr(llm_default, "gw_complete", fake_complete)
    e = LlmDefaultExtractor()
    out = await e.extract(
        [Turn(role="user", content="anything", turn_id="t-1")],
        scope,
        ExtractOpts(),
    )
    assert len(out) == 1
    assert out[0].type == "preference"


@pytest.mark.asyncio
async def test_drops_below_confidence_floor(monkeypatch, scope) -> None:
    async def fake_complete(req, actor):
        return _fake_response(
            '{"memories":[{"type":"fact","text":"low conf","confidence":0.1,"source_turn_ids":[]}]}'
        )

    monkeypatch.setattr(llm_default, "gw_complete", fake_complete)
    e = LlmDefaultExtractor()
    out = await e.extract(
        [Turn(role="user", content="x", turn_id="t-1")],
        scope,
        ExtractOpts(confidence_floor=0.5),
    )
    assert out == []


@pytest.mark.asyncio
async def test_tolerates_non_json(monkeypatch, scope) -> None:
    async def fake_complete(req, actor):
        return _fake_response("Here you go:\n```\nnonsense\n```")

    monkeypatch.setattr(llm_default, "gw_complete", fake_complete)
    e = LlmDefaultExtractor()
    out = await e.extract(
        [Turn(role="user", content="x", turn_id="t-1")],
        scope,
        ExtractOpts(),
    )
    assert out == []


@pytest.mark.asyncio
async def test_gateway_exception_returns_empty(monkeypatch, scope) -> None:
    async def fake_complete(req, actor):
        raise RuntimeError("boom")

    monkeypatch.setattr(llm_default, "gw_complete", fake_complete)
    e = LlmDefaultExtractor()
    out = await e.extract(
        [Turn(role="user", content="x", turn_id="t-1")],
        scope,
        ExtractOpts(),
    )
    assert out == []


def test_registered() -> None:
    assert get("llm_default").name == "llm_default"
