"""Phase M — analytics rollup signatures."""
from __future__ import annotations

import inspect

from ai_portal.memory import analytics


def test_rollup_all_is_coroutine() -> None:
    assert inspect.iscoroutinefunction(analytics.rollup_all)


def test_top_recalled_signature() -> None:
    sig = inspect.signature(analytics.top_recalled)
    assert {"session", "org_id"} <= set(sig.parameters)
    assert "days" in sig.parameters and "limit" in sig.parameters


def test_recall_hit_rate_signature() -> None:
    assert inspect.iscoroutinefunction(analytics.recall_hit_rate)


def test_extraction_outcomes_signature() -> None:
    assert inspect.iscoroutinefunction(analytics.extraction_outcomes)
