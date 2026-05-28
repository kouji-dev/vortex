"""Reciprocal Rank Fusion.

Reference: Cormack et al., "Reciprocal Rank Fusion outperforms Condorcet
and individual rank learning methods" (SIGIR 2009).

score(d) = sum_over_systems 1 / (k + rank(d, system))

Higher score = better. Default k=60 follows the canonical paper.
"""
from __future__ import annotations

from typing import Hashable, Iterable, TypeVar

T = TypeVar("T", bound=Hashable)


def reciprocal_rank_fusion(
    *ranked_lists: Iterable[T],
    k: int = 60,
    weights: tuple[float, ...] | None = None,
) -> list[tuple[T, float]]:
    """Fuse N ranked lists by reciprocal-rank.

    Args:
        ranked_lists: ordered iterables (rank 0 = best).
        k: smoothing constant. Smaller → top-rank items dominate.
        weights: optional per-list weight tuple, same length as ranked_lists.

    Returns:
        list of (item, fused_score) sorted by score desc.
    """
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError("weights length must match number of ranked lists")
    if k <= 0:
        raise ValueError("k must be positive")

    scores: dict[T, float] = {}
    for idx, lst in enumerate(ranked_lists):
        w = weights[idx] if weights else 1.0
        for rank, item in enumerate(lst):
            scores[item] = scores.get(item, 0.0) + w / (k + rank + 1)

    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def fuse_to_ids(
    *ranked_lists: Iterable[T],
    k: int = 60,
    weights: tuple[float, ...] | None = None,
) -> list[T]:
    """Same as reciprocal_rank_fusion but returns just the ordered ids."""
    return [item for item, _ in reciprocal_rank_fusion(*ranked_lists, k=k, weights=weights)]
