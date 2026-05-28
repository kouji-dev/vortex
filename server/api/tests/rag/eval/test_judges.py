"""LLM-as-judge prompt + response parser."""
from __future__ import annotations

from ai_portal.rag.eval.judges import (
    build_judge_prompt,
    parse_judge_response,
)


def test_parse_judge_response_plain_json() -> None:
    s = parse_judge_response('{"correctness": 0.8, "faithfulness": 0.9}')
    assert s.correctness == 0.8
    assert s.faithfulness == 0.9


def test_parse_judge_response_with_prose() -> None:
    text = (
        "Here is my evaluation.\n"
        "Score: {\"correctness\": 0.5, \"faithfulness\": 1.0}\n"
        "End of reasoning."
    )
    s = parse_judge_response(text)
    assert s.correctness == 0.5
    assert s.faithfulness == 1.0


def test_parse_judge_response_clamps_out_of_range() -> None:
    s = parse_judge_response('{"correctness": 1.5, "faithfulness": -0.3}')
    assert s.correctness == 1.0
    assert s.faithfulness == 0.0


def test_parse_judge_response_missing_keys_zero() -> None:
    s = parse_judge_response("garbage")
    assert s.correctness == 0.0
    assert s.faithfulness == 0.0


def test_build_judge_prompt_contains_all_inputs() -> None:
    p = build_judge_prompt(
        query="what is X?",
        gold_answer="X is Y",
        answer="X is Z",
        context_chunks=["chunk1", "chunk2"],
    )
    assert "what is X?" in p
    assert "X is Y" in p
    assert "X is Z" in p
    assert "chunk1" in p
    assert "chunk2" in p
