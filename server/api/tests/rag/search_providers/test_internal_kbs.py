"""InternalKbsProvider wraps the federated hybrid search."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_portal.rag.search.types import SearchHit
from ai_portal.rag.search_providers.providers.internal_kbs import InternalKbsProvider


def test_internal_kbs_no_db_returns_empty():
    p = InternalKbsProvider(db_factory=None, kb_ids=[1])
    assert p.search("q") == []


def test_internal_kbs_no_ids_returns_empty():
    p = InternalKbsProvider(db_factory=lambda: MagicMock(), kb_ids=[])
    assert p.search("q") == []


def test_internal_kbs_wraps_federated():
    fake_hits = [
        SearchHit(
            chunk_id=f"c{i}",
            document_id=f"d{i}",
            kb_id=1,
            text=f"chunk {i} content",
            score=0.5 - i * 0.1,
            meta={"title": f"Doc {i}", "source_uri": f"https://ex/{i}"},
        )
        for i in range(2)
    ]
    with patch(
        "ai_portal.rag.search.federated.federated_search",
        return_value=fake_hits,
    ):
        p = InternalKbsProvider(db_factory=lambda: MagicMock(), kb_ids=[1])
        out = p.search("q", num_results=2)
    assert len(out) == 2
    assert out[0].title == "Doc 0"
    assert out[0].source == "kb:1"
    assert out[0].meta["chunk_id"] == "c0"


def test_internal_kbs_kwarg_overrides_default_ids():
    with patch(
        "ai_portal.rag.search.federated.federated_search",
        return_value=[],
    ) as mock_fed:
        p = InternalKbsProvider(db_factory=lambda: MagicMock(), kb_ids=[1])
        p.search("q", kb_ids=[2, 3])
        # The federated request should have been built with the override.
        called_req = mock_fed.call_args[0][1]
        assert called_req.kb_ids == [2, 3]
