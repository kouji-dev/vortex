"""Retrieval metrics — recall@k, MRR, nDCG.

Pure functions: deterministic, side-effect-free, no I/O. Inputs are doc-id
lists (the order returned by the retriever) plus the relevance ground truth
expressed either as a set (binary) or a graded dict.
"""
from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Mapping


def recall_at_k(retrieved: Iterable[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant docs present in the top-k of ``retrieved``.

    Returns 0.0 when no docs are relevant (prevents div-by-zero on empty truth).
    """
    if not relevant:
        return 0.0
    top = list(retrieved)[: max(0, k)]
    hits = sum(1 for d in top if d in relevant)
    return hits / len(relevant)


def mrr(retrieved: Iterable[str], relevant: set[str]) -> float:
    """Mean Reciprocal Rank for a single query — 1/(rank of first hit)."""
    if not relevant:
        return 0.0
    for i, d in enumerate(retrieved, start=1):
        if d in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(
    retrieved: Iterable[str],
    relevance_grades: Mapping[str, int],
    k: int,
) -> float:
    """Normalised Discounted Cumulative Gain at k with graded relevance.

    Uses the standard ``(2^rel - 1) / log2(rank+1)`` gain formula. Returns 0.0
    when ideal DCG is zero (no positive grades in truth).
    """
    top = list(retrieved)[: max(0, k)]
    dcg = sum(
        (2 ** relevance_grades.get(d, 0) - 1) / math.log2(i + 2)
        for i, d in enumerate(top)
    )
    ideal = sorted(relevance_grades.values(), reverse=True)[: max(0, k)]
    idcg = sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def aggregate_mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


__all__ = ["aggregate_mean", "mrr", "ndcg_at_k", "recall_at_k"]
