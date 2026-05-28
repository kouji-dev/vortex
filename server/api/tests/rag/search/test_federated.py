"""Federated multi-KB merge correctness.

We don't hit Postgres here: we patch the per-KB hybrid_search to inject
canned hit lists, then assert that the global RRF + rerank produces a
merged ordering with proportional representation from each KB.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from ai_portal.rag.search.federated import FederatedRequest, federated_search
from ai_portal.rag.search.types import SearchHit


def _h(cid, kb):
    return SearchHit(
        chunk_id=cid,
        document_id=f"doc-{cid}",
        kb_id=kb,
        text=f"chunk {cid}",
        score=0.5,
        meta={},
    )


def test_federated_merges_hits_from_all_kbs():
    db = MagicMock()
    kb_hits = {
        1: [_h(f"k1-{i}", 1) for i in range(3)],
        2: [_h(f"k2-{i}", 2) for i in range(3)],
        3: [_h(f"k3-{i}", 3) for i in range(3)],
    }

    def fake_hybrid(_db, sub, **_kw):
        return kb_hits[sub.kb_ids[0]]

    with patch(
        "ai_portal.rag.search.federated.hybrid_search", side_effect=fake_hybrid
    ), patch("ai_portal.rag.search.federated.rerank_hits", side_effect=lambda q, hits, top_k: hits):
        out = federated_search(
            db, FederatedRequest(query="q", kb_ids=[1, 2, 3], top_k=6)
        )

    assert len(out) == 6
    # All three KBs represented (top-rank chunk from each must appear).
    kbs_seen = {h.kb_id for h in out[:3]}
    assert kbs_seen == {1, 2, 3}


def test_federated_empty_kbs_returns_empty():
    db = MagicMock()
    assert federated_search(db, FederatedRequest(query="q", kb_ids=[])) == []


def test_federated_respects_top_k_truncation():
    db = MagicMock()
    kb_hits = {1: [_h(f"a{i}", 1) for i in range(10)]}
    with patch(
        "ai_portal.rag.search.federated.hybrid_search",
        side_effect=lambda _db, sub, **_kw: kb_hits[sub.kb_ids[0]],
    ), patch("ai_portal.rag.search.federated.rerank_hits", side_effect=lambda q, hits, top_k: hits):
        out = federated_search(db, FederatedRequest(query="q", kb_ids=[1], top_k=3))
    assert len(out) == 3
