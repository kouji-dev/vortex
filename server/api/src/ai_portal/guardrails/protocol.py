"""Guardrail protocol + Verdict (minimal F1 stub).

This is the seam every concrete guardrail (regex, presidio, schema_validator,
topic_filter, custom_classifier, …) implements. The full F1 work — pipeline
runner, policy bundle model, alembic — is handled by a parallel agent. This
stub carries just the types F5 providers and F6 policy-resolution depend on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

# Verdict decision taxonomy. ``flag`` is non-blocking (observability only).
Decision = Literal["allow", "redact", "block", "flag"]


@dataclass(frozen=True)
class Match:
    """One evidence row inside a Verdict — what was hit + where."""

    rule: str
    span: tuple[int, int] | None = None
    detail: str | None = None


@dataclass(frozen=True)
class Verdict:
    """Outcome of one guardrail check.

    - ``decision="allow"`` — pass through unchanged
    - ``decision="redact"`` — return ``redacted_text`` instead of original
    - ``decision="block"`` — request rejected; pipeline halts
    - ``decision="flag"`` — observability only, request proceeds
    """

    decision: Decision
    matches: list[Match] = field(default_factory=list)
    redacted_text: str | None = None
    reason: str = ""


@dataclass
class GuardrailCtx:
    """Per-request execution context handed to every guardrail.

    Carries free-form config supplied by the policy bundle plus optional
    actor metadata for audit / classifier dispatch.
    """

    config: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    org_id: str | None = None
    request_id: str | None = None


@runtime_checkable
class Guardrail(Protocol):
    """Bidirectional input/output policy hook.

    Implementations may choose to short-circuit one direction by returning
    an ``allow`` Verdict — both methods are always called, never overridden.
    """

    name: str

    async def check_input(self, prompt: str, ctx: GuardrailCtx) -> Verdict: ...
    async def check_output(self, response: str, ctx: GuardrailCtx) -> Verdict: ...


__all__ = [
    "Decision",
    "Guardrail",
    "GuardrailCtx",
    "Match",
    "Verdict",
]
