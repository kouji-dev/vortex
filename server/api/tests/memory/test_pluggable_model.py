"""Phase A1 — model column / enum sanity check.

These tests don't hit Postgres; they only verify the SQLAlchemy mapping is
well-formed and the enum literals match the spec.
"""
from __future__ import annotations

import uuid

from ai_portal.memory.model import (
    ConflictStrategy,
    Memory,
    MemoryExtractionPolicy,
    MemoryJob,
    MemoryPause,
    MemoryRecallPolicy,
    MemoryScope,
    MemoryType,
    MemoryUse,
    ScopeKind,
)


def test_scope_kind_enum() -> None:
    assert {e.value for e in ScopeKind} == {
        "user",
        "conversation",
        "assistant",
        "team",
        "org",
    }


def test_memory_type_enum() -> None:
    assert {e.value for e in MemoryType} == {
        "fact",
        "preference",
        "entity",
        "relation",
        "episode",
        "procedure",
    }


def test_conflict_strategy_enum() -> None:
    assert {e.value for e in ConflictStrategy} == {
        "newer_wins",
        "keep_both",
        "prompt_user",
    }


def test_memory_instantiation_defaults() -> None:
    m = Memory(
        org_id=uuid.uuid4(),
        actor_owner_json={"kind": "user", "id": "1"},
        scope_kind=ScopeKind.user,
        scope_ids_json=["1"],
        type=MemoryType.fact,
        text="prefers TypeScript",
        extractor_model="claude-sonnet-4-6",
    )
    assert m.text == "prefers TypeScript"
    assert m.scope_kind is ScopeKind.user
    assert m.type is MemoryType.fact
    # defaults filled by SQLAlchemy at flush; raw instance keeps None.
    assert m.deleted_at is None
    assert m.expires_at is None


def test_all_new_tables_registered() -> None:
    expected = {
        "memories": Memory,
        "memory_scopes": MemoryScope,
        "memory_extraction_policies": MemoryExtractionPolicy,
        "memory_recall_policies": MemoryRecallPolicy,
        "memory_jobs": MemoryJob,
        "memory_uses": MemoryUse,
        "memory_pauses": MemoryPause,
    }
    for name, cls in expected.items():
        assert cls.__tablename__ == name


def test_memory_use_has_score_and_response_message_id() -> None:
    use = MemoryUse(
        memory_id=uuid.uuid4(),
        query_text_hash="abc",
        response_message_id="msg-1",
        score=0.42,
    )
    assert use.score == 0.42
    assert use.response_message_id == "msg-1"
