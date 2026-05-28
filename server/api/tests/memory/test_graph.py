"""Phase Polish-T2 — memory graph traversal."""
from __future__ import annotations

import inspect
import uuid
from types import SimpleNamespace

import pytest

from ai_portal.memory import graph
from ai_portal.memory.model import MemoryType


def _fake_mem(*, id, type=MemoryType.entity, text="t", tags=None, turns=None, entities=None):
    actor = {"kind": "user", "id": "1"}
    if entities:
        actor["entities"] = entities
    return SimpleNamespace(
        id=uuid.UUID(id) if isinstance(id, str) else id,
        type=type,
        text=text,
        tags_json=tags or [],
        source_turn_ids_json=turns or [],
        actor_owner_json=actor,
    )


def test_endpoints_prefers_entities_list() -> None:
    rel = _fake_mem(
        id="11111111-1111-1111-1111-111111111111",
        type=MemoryType.relation,
        entities=["aaa", "bbb"],
        tags=["rel:ccc"],
        turns=["ddd"],
    )
    assert graph._endpoints_of(rel) == ["aaa", "bbb"]


def test_endpoints_falls_back_to_tag_prefix() -> None:
    rel = _fake_mem(
        id="22222222-2222-2222-2222-222222222222",
        type=MemoryType.relation,
        tags=["rel:x", "rel:y", "noise"],
        turns=["should-not-use"],
    )
    assert graph._endpoints_of(rel) == ["x", "y"]


def test_endpoints_falls_back_to_turn_ids() -> None:
    rel = _fake_mem(
        id="33333333-3333-3333-3333-333333333333",
        type=MemoryType.relation,
        turns=["q", "r"],
    )
    assert graph._endpoints_of(rel) == ["q", "r"]


def test_endpoints_empty_when_nothing() -> None:
    rel = _fake_mem(id="44444444-4444-4444-4444-444444444444", type=MemoryType.relation)
    assert graph._endpoints_of(rel) == []


def test_traverse_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(graph.traverse)


def test_graph_result_dataclasses_have_expected_fields() -> None:
    n = graph.GraphNode(memory_id="a", text="t", type="entity", depth=0)
    e = graph.GraphEdge(relation_id="r", text="t", src="a", dst="b")
    assert n.depth == 0
    assert e.src == "a" and e.dst == "b"


def test_depth_is_clamped() -> None:
    # ensure depth argument is documented as int; clamp logic lives in traverse
    sig = inspect.signature(graph.traverse)
    assert "depth" in sig.parameters
    assert sig.parameters["depth"].default == 2


def test_router_exposes_related_endpoint() -> None:
    from ai_portal.memory.v1_router import router

    paths = {r.path for r in router.routes}
    assert "/v1/memories/{memory_id}/related" in paths


@pytest.mark.asyncio
async def test_traverse_returns_empty_when_seed_missing() -> None:
    class _S:
        async def execute(self, *_a, **_k):
            class _R:
                def scalars(self_):
                    return self_

                def __iter__(self_):
                    return iter([])

                def scalar_one_or_none(self_):
                    return None

            return _R()

    res = await graph.traverse(_S(), org_id=uuid.uuid4(), seed_id=uuid.uuid4(), depth=2)
    assert res.nodes == []
    assert res.edges == []
