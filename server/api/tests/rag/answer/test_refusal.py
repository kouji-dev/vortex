"""Refusal gate behaviour."""
from __future__ import annotations

from ai_portal.rag.answer.refusal import RefusalPolicy, should_refuse
from ai_portal.rag.search.types import SearchHit


def _h(score):
    return SearchHit(chunk_id="c", document_id="d", kb_id=1, text="t", score=score)


def test_refuse_when_no_hits():
    assert should_refuse([], RefusalPolicy()) is True


def test_refuse_when_top_score_below_min():
    assert should_refuse([_h(0.05)], RefusalPolicy(min_score=0.2)) is True


def test_allow_when_above_min():
    assert should_refuse([_h(0.5)], RefusalPolicy(min_score=0.2)) is False


def test_min_supporting_threshold():
    pol = RefusalPolicy(min_score=0.5, min_supporting=2)
    assert should_refuse([_h(0.9)], pol) is True
    assert should_refuse([_h(0.9), _h(0.8)], pol) is False
