"""Phase Polish-T3 — export format serializers."""
from __future__ import annotations

import json

import pytest

from ai_portal.memory import export_formats as ef


SAMPLE = {
    "memories": [
        {
            "id": "abc",
            "type": "fact",
            "scope_kind": "user",
            "scope_ids": ["1"],
            "text": "user likes pgvector",
            "importance": 0.7,
            "confidence": 0.9,
            "pinned": True,
            "tags": ["explicit_remember", "tech"],
            "source_conversation_id": 12,
            "extractor_model": "llm_default",
            "created_at": "2026-05-01T00:00:00Z",
            "last_used_at": None,
            "expires_at": None,
            "deleted_at": None,
        },
        {
            "id": "def",
            "type": "preference",
            "scope_kind": "user",
            "scope_ids": ["1"],
            "text": "dark mode",
            "importance": 0.5,
            "confidence": 0.8,
            "pinned": False,
            "tags": [],
            "source_conversation_id": None,
            "extractor_model": "rule_based",
            "created_at": "2026-05-02T00:00:00Z",
            "last_used_at": None,
            "expires_at": None,
            "deleted_at": None,
        },
    ]
}


def test_supported_formats_set() -> None:
    assert set(ef.SUPPORTED) == {"json", "jsonl", "csv", "md"}


def test_content_types_distinct() -> None:
    cts = {ef.content_type(f) for f in ef.SUPPORTED}
    assert len(cts) == 4


def test_to_json_roundtrip() -> None:
    out = ef.to_json(SAMPLE)
    assert isinstance(out, bytes)
    assert json.loads(out)["memories"][0]["id"] == "abc"


def test_to_jsonl_one_per_line() -> None:
    out = ef.to_jsonl(SAMPLE).decode("utf-8")
    lines = [l for l in out.split("\n") if l.strip()]
    assert len(lines) == 2
    for l in lines:
        json.loads(l)


def test_to_csv_has_header_and_rows() -> None:
    out = ef.to_csv(SAMPLE).decode("utf-8")
    rows = out.strip().split("\n")
    assert rows[0].startswith("id,type,scope_kind,")
    assert len(rows) == 3
    assert "user likes pgvector" in rows[1]


def test_to_csv_json_encodes_lists() -> None:
    out = ef.to_csv(SAMPLE).decode("utf-8")
    # tags list must be json-encoded inside the cell
    assert '"[""explicit_remember""' in out or '[\"explicit_remember\"' in out


def test_to_markdown_groups_by_type() -> None:
    md = ef.to_markdown(SAMPLE).decode("utf-8")
    assert "# Memory Export" in md
    assert "## fact (1)" in md
    assert "## preference (1)" in md
    assert "user likes pgvector" in md
    assert "**[pinned]**" in md


def test_to_markdown_empty() -> None:
    md = ef.to_markdown({"memories": []}).decode("utf-8")
    assert "No memories" in md


def test_render_dispatch() -> None:
    for f in ef.SUPPORTED:
        assert isinstance(ef.render(f, SAMPLE), bytes)


def test_render_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        ef.render("xml", SAMPLE)


def test_router_export_accepts_format() -> None:
    import inspect

    from ai_portal.memory.v1_router import export_endpoint

    sig = inspect.signature(export_endpoint)
    assert "format" in sig.parameters
