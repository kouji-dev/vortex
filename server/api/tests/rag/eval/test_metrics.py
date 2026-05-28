"""Retrieval metrics — pure functions, no DB."""
from __future__ import annotations

import math

from ai_portal.rag.eval.metrics import (
    aggregate_mean,
    mrr,
    ndcg_at_k,
    recall_at_k,
)


def test_recall_at_k_basic() -> None:
    retrieved = ["a", "b", "c", "d", "e"]
    relevant = {"b", "d", "z"}
    # at k=5, 2 of 3 relevant docs are present
    assert recall_at_k(retrieved, relevant, 5) == 2 / 3


def test_recall_at_k_truncation() -> None:
    retrieved = ["a", "b", "c"]
    relevant = {"c"}
    # k=2 → c is at index 2 so not within top-2
    assert recall_at_k(retrieved, relevant, 2) == 0.0
    assert recall_at_k(retrieved, relevant, 3) == 1.0


def test_recall_empty_relevant_is_zero() -> None:
    assert recall_at_k(["a"], set(), 5) == 0.0


def test_mrr_first_hit() -> None:
    # first relevant at rank 2 → 1/2
    assert mrr(["x", "b", "a"], {"a", "b"}) == 0.5


def test_mrr_no_hit_is_zero() -> None:
    assert mrr(["x", "y"], {"z"}) == 0.0


def test_ndcg_monotonic() -> None:
    grades = {"a": 3, "b": 2, "c": 1}
    perfect = ndcg_at_k(["a", "b", "c"], grades, 3)
    swapped = ndcg_at_k(["c", "b", "a"], grades, 3)
    assert perfect == 1.0
    assert swapped < perfect


def test_ndcg_empty_truth_is_zero() -> None:
    assert ndcg_at_k(["a"], {}, 5) == 0.0


def test_aggregate_mean() -> None:
    assert aggregate_mean([]) == 0.0
    assert math.isclose(aggregate_mean([1.0, 2.0, 3.0]), 2.0)
