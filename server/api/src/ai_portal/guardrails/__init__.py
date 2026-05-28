"""Guardrails module — pre/post call safety pipeline.

Public surface:

- :class:`Guardrail` — protocol for any check_input/check_output provider.
- :class:`Verdict`, :class:`Match` — return value of every check.
- :class:`GuardrailPipeline` — runs a bundle of guardrails in order, applies
  the action (allow / redact / block / flag) and returns the (possibly
  edited) text. Block raises :class:`GuardrailBlocked` so the gateway HTTP
  layer can translate to 422.
- :class:`GuardrailService` — persistence layer for ``guardrail_policies``
  + ``guardrail_violations``.

See :mod:`ai_portal.guardrails.providers` for bundled implementations.
"""
from __future__ import annotations

from ai_portal.guardrails.protocol import (
    Decision,
    Guardrail,
    GuardrailBlocked,
    GuardrailContext,
    Match,
    Verdict,
    allow,
    block,
    flag,
    redact,
)
from ai_portal.guardrails.service import (
    GuardrailPipeline,
    GuardrailService,
    PipelineResult,
    PipelineStep,
)

__all__ = [
    "Decision",
    "Guardrail",
    "GuardrailBlocked",
    "GuardrailContext",
    "GuardrailPipeline",
    "GuardrailService",
    "Match",
    "PipelineResult",
    "PipelineStep",
    "Verdict",
    "allow",
    "block",
    "flag",
    "redact",
]
