"""Hybrid pipeline tail: fuse + filter + boost + rerank.

We test the pure-python tail (`_fuse_filter_boost_rerank`) directly so we
don't need a database.
"""
from __future__ import annotations

from ai_portal.rag.search.hybrid import _fuse_filter_boost_rerank
from ai_portal.rag.search.types import SearchFilter, SearchHit, SearchRequest


def _h(cid, kb=1, meta=None, dense=None, lex=None):
    return SearchHit(
        chunk_id=cid,
        document_id=f"doc-{cid}",
        kb_id=kb,
        text=f"text for {cid}",
        score=0.0,
        meta=meta or {"source": "docs", "language": "en"},
        dense_rank=dense,
        lexical_rank=lex,
    )


def test_fuse_keeps_chunk_in_both_lists_first():
    dense = [_h("a", dense=0), _h("b", dense=1), _h("c", dense=2)]
    lex = [_h("a", lex=0), _h("x", lex=1)]
    req = SearchRequest(query="q", kb_ids=[1], top_k=10, rerank=False)
    out = _fuse_filter_boost_rerank(req, dense, lex)
    assert out[0].chunk_id == "a"
    assert {h.chunk_id for h in out} == {"a", "b", "c", "x"}


def test_fuse_applies_filter():
    dense = [
        _h("a", meta={"source": "docs"}),
        _h("b", meta={"source": "other"}),
    ]
    lex = [_h("c", meta={"source": "docs"})]
    req = SearchRequest(
        query="q", kb_ids=[1], top_k=10, rerank=False,
        filter=SearchFilter(sources=("docs",)),
    )
    out = _fuse_filter_boost_rerank(req, dense, lex)
    assert {h.chunk_id for h in out} == {"a", "c"}


def test_fuse_respects_top_k():
    dense = [_h(f"d{i}") for i in range(5)]
    lex = [_h(f"l{i}") for i in range(5)]
    req = SearchRequest(query="q", kb_ids=[1], top_k=3, rerank=False)
    out = _fuse_filter_boost_rerank(req, dense, lex)
    assert len(out) == 3


def test_fuse_with_source_weights_boosts():
    dense = [_h("low", meta={"source": "low"}), _h("hi", meta={"source": "hi"})]
    lex = []
    req = SearchRequest(
        query="q",
        kb_ids=[1],
        top_k=5,
        rerank=False,
        boost_source_priority={"hi": 5.0, "low": 1.0},
    )
    out = _fuse_filter_boost_rerank(req, dense, lex)
    assert out[0].chunk_id == "hi"
