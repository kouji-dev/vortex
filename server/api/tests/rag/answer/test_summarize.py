"""Multi-turn history compression tests."""

from __future__ import annotations

import pytest

from ai_portal.rag.answer.rewrite import ChatTurn
from ai_portal.rag.answer.summarize import compress_history


def _turns(n: int) -> list[ChatTurn]:
    out = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        out.append(ChatTurn(role=role, text=f"turn-{i}"))
    return out


def test_short_history_passes_through_unchanged():
    history = _turns(3)
    out = compress_history(history, threshold_turns=6, keep_recent=2)
    assert out.compressed is False
    assert out.summary == ""
    assert [t.text for t in out.recent] == ["turn-0", "turn-1", "turn-2"]


def test_at_threshold_passes_through():
    history = _turns(6)
    out = compress_history(history, threshold_turns=6, keep_recent=4)
    assert out.compressed is False


def test_long_history_compresses_older_and_keeps_recent():
    history = _turns(12)
    captured: dict = {}

    def fake_llm(system: str, user: str, model: str) -> str:
        captured["system"] = system
        captured["user"] = user
        return "USER discussed onboarding flow; ASSISTANT cited policy doc."

    out = compress_history(
        history,
        threshold_turns=6,
        keep_recent=4,
        budget_tokens=1000,
        complete_fn=fake_llm,
    )
    assert out.compressed is True
    assert out.summary.startswith("USER")
    assert len(out.recent) == 4
    # The last 4 turns kept verbatim
    assert [t.text for t in out.recent] == ["turn-8", "turn-9", "turn-10", "turn-11"]
    # Older turns went into the summarizer
    assert "turn-0" in captured["user"]
    assert "turn-7" in captured["user"]
    assert "turn-8" not in captured["user"]


def test_budget_cap_enforced_on_summary_output():
    history = _turns(20)

    def fake_llm(system: str, user: str, model: str) -> str:
        return "A" * 100_000  # way over budget

    out = compress_history(
        history,
        threshold_turns=6,
        keep_recent=4,
        budget_tokens=200,  # 200 * 4 chars = 800 chars
        complete_fn=fake_llm,
    )
    assert out.compressed is True
    assert len(out.summary) <= 1000  # tight cap (budget + ellipsis)


def test_llm_failure_falls_back_to_heuristic():
    history = _turns(10)

    def broken_llm(system: str, user: str, model: str) -> str:
        raise RuntimeError("boom")

    out = compress_history(
        history,
        threshold_turns=6,
        keep_recent=2,
        budget_tokens=1000,
        complete_fn=broken_llm,
    )
    assert out.compressed is True
    # Heuristic uses recent tail of older turns
    assert "turn" in out.summary
    assert len(out.recent) == 2


def test_empty_llm_output_falls_back_to_heuristic():
    history = _turns(10)

    def empty_llm(system: str, user: str, model: str) -> str:
        return ""

    out = compress_history(history, threshold_turns=6, keep_recent=2, complete_fn=empty_llm)
    assert out.compressed is True
    assert out.summary != ""  # heuristic kicked in


def test_keep_recent_zero_summarizes_everything():
    history = _turns(10)

    def fake_llm(system: str, user: str, model: str) -> str:
        return "compressed."

    out = compress_history(
        history,
        threshold_turns=6,
        keep_recent=0,
        complete_fn=fake_llm,
    )
    assert out.compressed is True
    assert out.recent == []
    assert out.summary == "compressed."


def test_empty_history_returns_no_compression():
    out = compress_history([], threshold_turns=6, keep_recent=4)
    assert out.compressed is False
    assert out.summary == ""
    assert out.recent == []
