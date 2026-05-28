"""LLM-as-judge for answer correctness + faithfulness.

The judge is routed through ``gateway.facade.complete`` (no provider SDK
imported here). Disclosed via ``judge_model`` and ``judge_temperature`` so
runs are reproducible.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

JUDGE_PROMPT = """You are an evaluation judge.
Score the assistant ANSWER against the GOLD ANSWER and CONTEXT chunks.
- correctness: 0.0 to 1.0 (factually matches the gold answer)
- faithfulness: 0.0 to 1.0 (every claim is supported by the context)
Return JSON only: {"correctness": <float>, "faithfulness": <float>}.
"""


@dataclass(slots=True)
class JudgeScores:
    correctness: float
    faithfulness: float


def parse_judge_response(text: str) -> JudgeScores:
    """Extract correctness + faithfulness floats from a judge response.

    Robust to extra prose around the JSON block: locates the first ``{...}``
    in the text. Missing keys default to 0.0; out-of-range clamps to [0, 1].
    """
    m = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    raw = m.group(0) if m else "{}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {}
    return JudgeScores(
        correctness=_clamp01(data.get("correctness")),
        faithfulness=_clamp01(data.get("faithfulness")),
    )


def _clamp01(v) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def build_judge_prompt(
    *,
    query: str,
    gold_answer: str,
    answer: str,
    context_chunks: list[str],
) -> str:
    """Compose a caveman-style judge prompt — short, direct, no filler."""
    ctx = "\n---\n".join(context_chunks[:8])
    return (
        f"{JUDGE_PROMPT}\n"
        f"QUERY: {query}\n"
        f"GOLD ANSWER: {gold_answer}\n"
        f"ANSWER: {answer}\n"
        f"CONTEXT:\n{ctx}\n"
    )


__all__ = ["JUDGE_PROMPT", "JudgeScores", "build_judge_prompt", "parse_judge_response"]
