"""Metadata filter behaviour."""
from __future__ import annotations

from datetime import datetime, timezone

from ai_portal.rag.search.filters import apply_filter, hit_matches_filter
from ai_portal.rag.search.types import SearchFilter, SearchHit


def _h(meta: dict | None = None, *, cid: str = "c1") -> SearchHit:
    return SearchHit(
        chunk_id=cid,
        document_id="d1",
        kb_id=1,
        text="hello",
        score=1.0,
        meta=meta or {},
    )


def test_empty_filter_passes_everything():
    flt = SearchFilter()
    assert hit_matches_filter(_h({"source": "anything"}), flt)


def test_filter_by_source_keeps_matching():
    flt = SearchFilter(sources=("docs", "wiki"))
    assert hit_matches_filter(_h({"source": "docs"}), flt)
    assert not hit_matches_filter(_h({"source": "other"}), flt)


def test_filter_by_language():
    flt = SearchFilter(languages=("en",))
    assert hit_matches_filter(_h({"language": "en"}), flt)
    assert not hit_matches_filter(_h({"language": "fr"}), flt)


def test_filter_by_tag_handles_list():
    flt = SearchFilter(tags=("urgent",))
    assert hit_matches_filter(_h({"tags": ["urgent", "review"]}), flt)
    assert not hit_matches_filter(_h({"tags": ["other"]}), flt)


def test_filter_date_range():
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    flt = SearchFilter(date_from=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert hit_matches_filter(_h({"created_at": now.isoformat()}), flt)
    old = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert not hit_matches_filter(_h({"created_at": old.isoformat()}), flt)


def test_filter_missing_required_field_excludes():
    flt = SearchFilter(authors=("alice",))
    assert not hit_matches_filter(_h({}), flt)


def test_apply_filter_returns_only_matching():
    hits = [
        _h({"source": "a"}, cid="1"),
        _h({"source": "b"}, cid="2"),
        _h({"source": "a"}, cid="3"),
    ]
    out = apply_filter(hits, SearchFilter(sources=("a",)))
    assert [h.chunk_id for h in out] == ["1", "3"]
