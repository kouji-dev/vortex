"""CitationTracker + marker injection."""
from __future__ import annotations

from ai_portal.rag.answer.citations import (
    CitationTracker,
    inject_citation_markers,
    used_marker_indices,
)
from ai_portal.rag.search.types import SearchHit


def _h(cid, doc, kb=1, meta=None, text="some chunk text"):
    return SearchHit(
        chunk_id=cid,
        document_id=doc,
        kb_id=kb,
        text=text,
        score=1.0,
        meta=meta or {},
    )


def test_tracker_assigns_one_based_indices():
    t = CitationTracker()
    a = t.register(_h("c1", "d1", meta={"title": "A"}))
    b = t.register(_h("c2", "d2", meta={"title": "B"}))
    assert a.index == 1
    assert b.index == 2


def test_tracker_dedupes_same_chunk():
    t = CitationTracker()
    a = t.register(_h("c1", "d1", meta={"title": "X"}))
    a_again = t.register(_h("c1", "d1", meta={"title": "X"}))
    assert a is a_again
    assert len(t) == 1


def test_tracker_truncates_snippets():
    t = CitationTracker()
    long_text = "lorem ipsum " * 50
    c = t.register(_h("c", "d", text=long_text))
    assert c.snippet.endswith("…")
    assert len(c.snippet) <= 240


def test_tracker_extracts_permalink_from_meta():
    t = CitationTracker()
    c = t.register(_h("c", "d", meta={"title": "T", "source_uri": "https://e/1"}))
    assert c.permalink == "https://e/1"


def test_used_marker_indices_parses_brackets():
    assert used_marker_indices("Foo [1] bar [3] baz") == [1, 3]


def test_inject_markers_noop_when_present():
    text = "hello [1] world"
    assert inject_citation_markers(text, fallback_indices=[2, 3]) == text


def test_inject_markers_appends_when_missing():
    out = inject_citation_markers("answer body", fallback_indices=[1, 2])
    assert "[1]" in out and "[2]" in out


def test_inject_markers_no_fallback_returns_input():
    assert inject_citation_markers("hi", fallback_indices=None) == "hi"
