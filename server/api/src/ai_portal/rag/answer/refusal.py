"""Refusal gate — return "I don't know" when no high-confidence source.

A gate is triggered when:
  - no hits at all
  - top hit score below ``min_score``
  - too few hits above the threshold (``min_supporting``)
"""
from __future__ import annotations

from dataclasses import dataclass

from ai_portal.rag.search.types import SearchHit


@dataclass
class RefusalPolicy:
    min_score: float = 0.2
    min_supporting: int = 1
    refusal_text: str = "I don't know based on the provided sources."


def should_refuse(hits: list[SearchHit], policy: RefusalPolicy) -> bool:
    if not hits:
        return True
    qualified = [h for h in hits if h.score >= policy.min_score]
    if len(qualified) < policy.min_supporting:
        return True
    return False
