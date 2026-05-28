"""Exact-match judge.

Compares ``output`` to ``expected`` after stripping whitespace and (by
default) lower-casing. ``config["case_sensitive"] = True`` disables the
case fold; ``config["strip"] = False`` disables the strip.
"""

from __future__ import annotations

from typing import Any

from ai_portal.gateway.evals.judges.custom import JudgeVerdict


async def exact_judge(
    *, output: str, expected: str, config: dict[str, Any] | None = None
) -> JudgeVerdict:
    cfg = config or {}
    case_sensitive = bool(cfg.get("case_sensitive", False))
    strip = bool(cfg.get("strip", True))
    a, b = output, expected
    if strip:
        a, b = a.strip(), b.strip()
    if not case_sensitive:
        a, b = a.lower(), b.lower()
    passed = a == b
    return JudgeVerdict(
        passed=passed,
        detail="" if passed else f"expected {expected!r}, got {output!r}",
    )


__all__ = ["exact_judge"]
