"""Guardrails module — pre/post-call input/output policy enforcement.

Public surface:

- :class:`Verdict`, :class:`Match`, :class:`GuardrailCtx`
- :class:`Guardrail` Protocol — runtime-checkable

Providers live in :mod:`ai_portal.guardrails.providers`. The runtime pipeline
(F1) assembles a policy bundle and runs each guardrail in order.
"""

from __future__ import annotations

from ai_portal.guardrails.protocol import (
    Guardrail,
    GuardrailCtx,
    Match,
    Verdict,
)

__all__ = [
    "Guardrail",
    "GuardrailCtx",
    "Match",
    "Verdict",
]
