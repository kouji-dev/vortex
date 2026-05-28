"""LLM-as-judge.

Routes a structured-grading prompt through the gateway facade. The judge
model is **disclosed** in :class:`JudgeVerdict.detail` so test runs are
auditable.

Prompt is intentionally caveman-style: short, direct, asks for a binary
verdict in the first line.
"""

from __future__ import annotations

import uuid
from typing import Any

from ai_portal.gateway import facade as gateway_facade
from ai_portal.gateway.evals.judges.custom import JudgeVerdict
from ai_portal.gateway.facade import Actor
from ai_portal.gateway.types import LLMRequest, Message, TextBlock

_DEFAULT_JUDGE_MODEL = "gpt-4o-mini"


def _judge_prompt(*, output: str, expected: str, criteria: str | None) -> str:
    """Build the judge prompt. Caveman style — short, no filler."""
    parts = [
        "Grade output against expected. Reply PASS or FAIL on line 1.",
        "Line 2: brief reason (one sentence).",
    ]
    if criteria:
        parts.append(f"Criteria: {criteria}")
    parts.append(f"Expected:\n{expected}")
    parts.append(f"Output:\n{output}")
    return "\n\n".join(parts)


def _parse_verdict(text: str) -> tuple[bool, str]:
    head = (text or "").strip().splitlines()
    if not head:
        return False, "judge returned empty"
    line1 = head[0].strip().upper()
    passed = line1.startswith("PASS")
    detail = head[1].strip() if len(head) > 1 else ""
    return passed, detail


async def llm_judge(
    *,
    output: str,
    expected: str,
    config: dict[str, Any] | None = None,
    actor: Actor | None = None,
) -> JudgeVerdict:
    """Run an LLM-as-judge through the gateway facade.

    ``config["model"]`` selects the judge model (default
    ``gpt-4o-mini``). ``config["criteria"]`` is an optional rubric line.
    """
    cfg = config or {}
    judge_model = str(cfg.get("model") or _DEFAULT_JUDGE_MODEL)
    criteria = cfg.get("criteria")

    prompt = _judge_prompt(output=output, expected=expected, criteria=criteria)
    req = LLMRequest(
        model=judge_model,
        messages=[
            Message(role="user", content=[TextBlock(text=prompt)]),
        ],
        temperature=0.0,
        max_tokens=128,
    )
    act = actor or Actor(
        org_id=uuid.UUID("00000000-0000-0000-0000-000000000000"),
        kind="service",
    )
    try:
        resp = await gateway_facade.complete(req, act)
    except Exception as exc:  # noqa: BLE001
        return JudgeVerdict(passed=False, detail=f"judge call failed: {exc}")

    text_out = ""
    for block in resp.content:
        t = getattr(block, "text", None)
        if t:
            text_out += t
    passed, detail = _parse_verdict(text_out)
    return JudgeVerdict(
        passed=passed,
        detail=f"judge={judge_model}: {detail}" if detail else f"judge={judge_model}",
    )


__all__ = ["llm_judge"]
