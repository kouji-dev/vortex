"""Rerank stage — exercises the injectable rerank_fn path."""
from __future__ import annotations

from ai_portal.rag.search.rerank import rerank_hits
from ai_portal.rag.search.types import SearchHit


def _h(cid, text):
    return SearchHit(chunk_id=cid, document_id="d", kb_id=1, text=text, score=0.0)


def test_rerank_uses_injected_fn_order():
    hits = [_h("a", "alpha"), _h("b", "beta"), _h("c", "gamma")]
    # Reverse-order rerank: last input first.
    fn = lambda q, docs, model, top_k: [(2, 0.9), (1, 0.5), (0, 0.1)]
    out = rerank_hits("q", hits, top_k=3, rerank_fn=fn)
    assert [h.chunk_id for h in out] == ["c", "b", "a"]
    assert out[0].rerank_score == 0.9


def test_rerank_truncates_to_top_k():
    hits = [_h(str(i), str(i)) for i in range(5)]
    fn = lambda q, docs, model, top_k: [(i, float(5 - i)) for i in range(5)]
    out = rerank_hits("q", hits, top_k=2, rerank_fn=fn)
    assert len(out) == 2


def test_rerank_empty_input():
    assert rerank_hits("q", [], top_k=5) == []


def test_rerank_fn_failure_returns_original_truncated():
    hits = [_h("a", "x"), _h("b", "y")]
    def bad(*a, **kw):
        raise RuntimeError("boom")
    out = rerank_hits("q", hits, top_k=1, rerank_fn=bad)
    assert len(out) == 1
    assert out[0].chunk_id == "a"
