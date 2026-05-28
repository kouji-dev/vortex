"""Regex judge.

``expected`` is treated as a regex pattern; ``re.search`` succeeds → pass.
``config["flags"]`` may be the str ``"i"`` (case-insensitive) or an int of
``re`` flags.
"""

from __future__ import annotations

import re
from typing import Any

from ai_portal.gateway.evals.judges.custom import JudgeVerdict


def _compile_flags(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        flags = 0
        if "i" in value.lower():
            flags |= re.IGNORECASE
        if "m" in value.lower():
            flags |= re.MULTILINE
        if "s" in value.lower():
            flags |= re.DOTALL
        return flags
    return 0


async def regex_judge(
    *, output: str, expected: str, config: dict[str, Any] | None = None
) -> JudgeVerdict:
    cfg = config or {}
    flags = _compile_flags(cfg.get("flags", 0))
    try:
        match = re.search(expected, output, flags=flags)
    except re.error as exc:
        return JudgeVerdict(passed=False, detail=f"invalid regex: {exc}")
    if match is None:
        return JudgeVerdict(passed=False, detail=f"no match for {expected!r}")
    return JudgeVerdict(
        passed=True, detail=f"matched at {match.start()}..{match.end()}"
    )


__all__ = ["regex_judge"]
