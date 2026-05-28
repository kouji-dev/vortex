"""Tests for the kb_search tool — wraps rag.search_knowledge_base_tool."""

from __future__ import annotations

import pytest

from ai_portal.workers.tools.providers import kb_search as kb_search_mod
from ai_portal.workers.tools.providers.kb_search import KbSearchTool


@pytest.mark.asyncio
async def test_kb_search_calls_rag_with_kb_ids(harness, monkeypatch) -> None:
    captured: dict = {}

    def _fake_search(db, *, query, kb_ids, top_k=None):
        captured["query"] = query
        captured["kb_ids"] = list(kb_ids)
        captured["top_k"] = top_k
        return {
            "context": "ctx",
            "used_kbs": [{"kb_id": 1, "kb_name": "X", "chunks_used": 2}],
            "citations": [
                {"chunk_id": 1, "document_id": 10, "kb_id": 1, "snippet": "s"}
            ],
        }

    monkeypatch.setattr(
        kb_search_mod, "_search_knowledge_base", _fake_search, raising=True
    )

    _sb, _h, ctx, rec = await harness(
        pool_settings={"kb_ids": [1, 2], "rag_session": object()}
    )
    r = await KbSearchTool().invoke({"query": "find me"}, ctx)
    assert r.ok is True
    assert captured["query"] == "find me"
    assert captured["kb_ids"] == [1, 2]
    assert r.output["citations"][0]["kb_id"] == 1
    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds


@pytest.mark.asyncio
async def test_kb_search_no_kb_configured_returns_empty(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await KbSearchTool().invoke({"query": "x"}, ctx)
    assert r.ok is True
    assert r.output["citations"] == []
    assert r.output["used_kbs"] == []


@pytest.mark.asyncio
async def test_kb_search_respects_actor_acl(harness, monkeypatch) -> None:
    """Pool's ``kb_ids`` is the ACL surface — kb ids outside it must not be
    queried even if args override is attempted."""
    captured: dict = {}

    def _fake_search(db, *, query, kb_ids, top_k=None):
        captured["kb_ids"] = list(kb_ids)
        return {"context": "", "used_kbs": [], "citations": []}

    monkeypatch.setattr(
        kb_search_mod, "_search_knowledge_base", _fake_search, raising=True
    )

    _sb, _h, ctx, _rec = await harness(
        pool_settings={"kb_ids": [1], "rag_session": object()}
    )
    # Caller tries to query KB 99 — must be filtered to allowed [1].
    await KbSearchTool().invoke({"query": "x", "kb_ids": [99, 1]}, ctx)
    assert captured["kb_ids"] == [1]


@pytest.mark.asyncio
async def test_kb_search_audits_query_and_count(harness, monkeypatch) -> None:
    def _fake_search(db, *, query, kb_ids, top_k=None):
        return {
            "context": "x",
            "used_kbs": [],
            "citations": [{"chunk_id": 1, "document_id": 10, "kb_id": 1, "snippet": "s"}],
        }

    monkeypatch.setattr(
        kb_search_mod, "_search_knowledge_base", _fake_search, raising=True
    )

    _sb, _h, ctx, rec = await harness(
        pool_settings={"kb_ids": [1], "rag_session": object()}
    )
    await KbSearchTool().invoke({"query": "hello"}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.kb_search"
    assert audit["payload"]["query"] == "hello"
    assert audit["payload"]["citation_count"] == 1
