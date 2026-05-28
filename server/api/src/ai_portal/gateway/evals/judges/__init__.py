"""Judges — verdict functions that score one (output, expected) pair.

Bundled implementations:

- :func:`exact_judge`    — equality after .strip() / case-fold
- :func:`regex_judge`    — re.search(expected, output)
- :func:`llm_judge`      — gateway-routed call to a disclosed judge model
- :func:`custom_judge`   — callable supplied by the caller

All judges return :class:`JudgeVerdict`; the runner only cares about the
``passed`` bool. ``detail`` surfaces in the per-record result.
"""

from __future__ import annotations

from ai_portal.gateway.evals.judges.custom import (
    CustomJudge,
    JudgeVerdict,
    custom_judge,
    register_custom_judge,
)
from ai_portal.gateway.evals.judges.exact import exact_judge
from ai_portal.gateway.evals.judges.llm import llm_judge
from ai_portal.gateway.evals.judges.regex import regex_judge

__all__ = [
    "CustomJudge",
    "JudgeVerdict",
    "custom_judge",
    "exact_judge",
    "llm_judge",
    "regex_judge",
    "register_custom_judge",
]
