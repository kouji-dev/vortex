"""Reciprocal Rank Fusion correctness."""
from __future__ import annotations

import pytest

from ai_portal.rag.search.rrf import fuse_to_ids, reciprocal_rank_fusion


def test_rrf_returns_sorted_descending():
    result = reciprocal_rank_fusion(["a", "b", "c"], ["b", "a", "d"], k=60)
    ids = [r[0] for r in result]
    scores = [r[1] for r in result]
    assert ids[0] in {"a", "b"}
    assert scores == sorted(scores, reverse=True)
    assert set(ids) == {"a", "b", "c", "d"}


def test_rrf_shared_top_wins_over_singletons():
    # 'a' appears at rank 0 in both lists -> highest fused score.
    result = reciprocal_rank_fusion(["a", "b", "c"], ["a", "x", "y"], k=60)
    assert result[0][0] == "a"


def test_rrf_empty_inputs():
    assert reciprocal_rank_fusion([], []) == []


def test_rrf_single_list_passes_through():
    out = fuse_to_ids(["x", "y", "z"])
    assert out == ["x", "y", "z"]


def test_rrf_weights_amplify_first_list():
    base = fuse_to_ids(["a", "b"], ["b", "a"], k=60)
    weighted = fuse_to_ids(["a", "b"], ["b", "a"], k=60, weights=(10.0, 1.0))
    assert weighted[0] == "a"
    # base is symmetric → either order is acceptable; assert set equality.
    assert set(base) == {"a", "b"}


def test_rrf_k_must_be_positive():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(["a"], k=0)


def test_rrf_weights_length_mismatch():
    with pytest.raises(ValueError):
        reciprocal_rank_fusion(["a"], ["b"], weights=(1.0,))


def test_rrf_k_smaller_amplifies_top_rank():
    # With small k, the top of one list strongly dominates.
    res = reciprocal_rank_fusion(["x", "y", "z"], ["z", "y", "x"], k=1)
    assert res[0][0] in {"x", "z"}
