"""Phase A3 — Pydantic schema sanity checks."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from ai_portal.memory.schemas import (
    BulkDeleteRequest,
    ExtractRequest,
    ExtractTurnDTO,
    MemoryCreate,
    MemoryPatch,
    PauseRequest,
    RecallRequest,
)


def test_memory_create_rejects_empty_text() -> None:
    with pytest.raises(ValidationError):
        MemoryCreate(type="fact", scope_kind="user", text="")
    with pytest.raises(ValidationError):
        MemoryCreate(type="fact", scope_kind="user", text="   ")


def test_memory_create_strips_text() -> None:
    m = MemoryCreate(type="fact", scope_kind="user", text="  hello  ")
    assert m.text == "hello"


def test_recall_request_defaults() -> None:
    r = RecallRequest(query="hi")
    assert r.top_k == 8
    assert r.recency_weight == 0.2
    assert r.importance_weight == 0.3


def test_recall_request_rejects_empty_query() -> None:
    with pytest.raises(ValidationError):
        RecallRequest(query="")


def test_extract_request_defaults_allowed_types() -> None:
    req = ExtractRequest(
        turns=[ExtractTurnDTO(role="user", content="hi", turn_id="t1")],
        scope_kind="user",
        scope_id="1",
    )
    assert set(req.allowed_types) == {
        "fact",
        "preference",
        "entity",
        "relation",
        "episode",
        "procedure",
    }
    assert req.extractor == "llm_default"
    assert req.confidence_floor == 0.4


def test_memory_patch_all_optional() -> None:
    p = MemoryPatch()
    assert p.text is None
    p2 = MemoryPatch(text="x", pinned=True)
    assert p2.pinned is True


def test_bulk_delete_request_optional() -> None:
    b = BulkDeleteRequest()
    assert b.ids is None
    assert b.type is None


def test_pause_request_optional() -> None:
    p = PauseRequest()
    assert p.scope_kind is None
