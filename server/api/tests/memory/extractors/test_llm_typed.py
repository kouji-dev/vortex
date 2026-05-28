"""Phase C4 — llm_typed extractor (one call per type)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from ai_portal.memory.extractors import get, llm_typed
from ai_portal.memory.extractors.llm_typed import LlmTypedExtractor
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn


def _resp(text: str) -> object:
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
async def test_one_call_per_allowed_type(monkeypatch, scope) -> None:
    calls: list[str] = []

    async def fake_complete(req, actor):
        typ = req.metadata.get("type")
        calls.append(typ)
        return _resp(
            f'{{"memories":[{{"type":"{typ}","text":"x for {typ}","confidence":0.9,"source_turn_ids":[]}}]}}'
        )

    monkeypatch.setattr(llm_typed, "gw_complete", fake_complete)
    e = LlmTypedExtractor()
    out = await e.extract(
        [Turn(role="user", content="x", turn_id="t1")],
        scope,
        ExtractOpts(),
    )
    assert set(calls) == {"fact", "preference", "entity", "relation", "episode", "procedure"}
    assert {c.type for c in out} == {
        "fact",
        "preference",
        "entity",
        "relation",
        "episode",
        "procedure",
    }


@pytest.mark.asyncio
async def test_respects_allowed_types(monkeypatch, scope) -> None:
    calls: list[str] = []

    async def fake_complete(req, actor):
        typ = req.metadata.get("type")
        calls.append(typ)
        return _resp(
            f'{{"memories":[{{"type":"{typ}","text":"x","confidence":0.9,"source_turn_ids":[]}}]}}'
        )

    monkeypatch.setattr(llm_typed, "gw_complete", fake_complete)
    e = LlmTypedExtractor()
    await e.extract(
        [Turn(role="user", content="x", turn_id="t1")],
        scope,
        ExtractOpts(allowed_types=["fact", "preference"]),
    )
    assert set(calls) == {"fact", "preference"}


def test_registered() -> None:
    assert get("llm_typed").name == "llm_typed"
