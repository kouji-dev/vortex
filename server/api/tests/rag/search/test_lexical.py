"""In-memory BM25 used by tests + the internal_kbs search provider."""
from __future__ import annotations

from ai_portal.rag.search.lexical import bm25_rank_in_memory


def test_bm25_returns_doc_containing_query_term():
    docs = [
        "python web frameworks like fastapi",
        "javascript runtimes node deno bun",
        "postgres tuning notes",
    ]
    ranked = bm25_rank_in_memory("fastapi python", docs, top_k=2)
    assert ranked[0][0] == 0


def test_bm25_returns_empty_for_no_overlap():
    docs = ["alpha bravo", "charlie delta"]
    ranked = bm25_rank_in_memory("xxx yyy", docs)
    assert ranked == []


def test_bm25_handles_empty_docs():
    assert bm25_rank_in_memory("q", []) == []


def test_bm25_top_k_truncation():
    docs = [f"common word {i}" for i in range(5)]
    ranked = bm25_rank_in_memory("common word", docs, top_k=2)
    assert len(ranked) == 2
