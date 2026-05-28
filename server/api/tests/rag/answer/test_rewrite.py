"""Multi-turn question rewrite."""
from __future__ import annotations

from ai_portal.rag.answer.rewrite import ChatTurn, rewrite_question


def test_no_prior_turns_returns_question_as_is():
    assert rewrite_question("What is RAG?") == "What is RAG?"


def test_uses_injected_complete_fn():
    fn = lambda system, user, model: "What is retrieval-augmented generation?"
    out = rewrite_question(
        "What is it?",
        prior_turns=[ChatTurn("user", "Tell me about RAG.")],
        complete_fn=fn,
    )
    assert "retrieval" in out.lower()


def test_fallback_concatenates_last_user_turn():
    def boom(*a, **kw):
        raise RuntimeError("no llm")

    out = rewrite_question(
        "How fast?",
        prior_turns=[
            ChatTurn("user", "Tell me about RAG."),
            ChatTurn("assistant", "It's a pattern."),
        ],
        complete_fn=boom,
    )
    assert "RAG" in out
    assert "How fast" in out
