"""Guardrail protocol + Verdict dataclass.

A guardrail is anything that inspects a prompt (pre-call) or a model
response (post-call) and returns a :class:`Verdict`. The pipeline chooses
how to react to each verdict's :class:`Decision`:

- ``allow``  → keep going, unchanged
- ``redact`` → keep going with ``verdict.redacted_text`` substituted
- ``block``  → abort the request; gateway translates to HTTP 422
- ``flag``   → keep going, record violation, no edit

Guardrails are async so a provider can call out to e.g. Presidio or a
self-hosted classifier without blocking the worker.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

Decision = Literal["allow", "redact", "block", "flag"]


@dataclass(frozen=True)
class Match:
    """One span flagged by a guardrail.

    ``kind`` is provider-defined (e.g. ``"EMAIL"``, ``"AWS_ACCESS_KEY"``).
    ``start`` / ``end`` are half-open byte offsets into the inspected text;
    ``-1`` / ``-1`` is valid for classifiers that don't return spans.
    """

    kind: str
    start: int = -1
    end: int = -1
    snippet: str = ""
    score: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Verdict:
    """Result of a single ``check_input`` / ``check_output`` call."""

    decision: Decision
    matches: list[Match] = field(default_factory=list)
    redacted_text: str | None = None
    reason: str = ""


def allow(reason: str = "") -> Verdict:
    return Verdict(decision="allow", reason=reason)


def block(
    *,
    matches: list[Match] | None = None,
    reason: str,
) -> Verdict:
    return Verdict(decision="block", matches=matches or [], reason=reason)


def redact(
    *,
    matches: list[Match],
    redacted_text: str,
    reason: str = "",
) -> Verdict:
    return Verdict(
        decision="redact",
        matches=matches,
        redacted_text=redacted_text,
        reason=reason,
    )


def flag(
    *,
    matches: list[Match] | None = None,
    reason: str = "",
) -> Verdict:
    return Verdict(decision="flag", matches=matches or [], reason=reason)


@dataclass
class GuardrailContext:
    """Per-call context passed to every guardrail.

    Carries identity (``org_id``, ``actor``) plus a free-form ``metadata``
    bag for things like the request id, key id, route, model.
    """

    org_id: str | None = None
    actor: dict[str, Any] = field(default_factory=dict)
    request_id: str | None = None
    route: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Guardrail(Protocol):
    """A pre- and/or post-call inspector.

    Implementations that only handle one direction can return
    :func:`allow` for the other; they will be a no-op in that phase.
    """

    name: str

    async def check_input(
        self, prompt: str, ctx: GuardrailContext
    ) -> Verdict:  # pragma: no cover - protocol shape
        ...

    async def check_output(
        self, response: str, ctx: GuardrailContext
    ) -> Verdict:  # pragma: no cover - protocol shape
        ...


class GuardrailBlocked(Exception):
    """Raised by the pipeline when any guardrail returns ``block``.

    The gateway HTTP layer catches this and renders an HTTP 422 with the
    offending guardrail name, reason, and matches.
    """

    def __init__(
        self,
        *,
        guardrail: str,
        verdict: Verdict,
        phase: Literal["input", "output"],
    ) -> None:
        self.guardrail = guardrail
        self.verdict = verdict
        self.phase = phase
        super().__init__(
            f"blocked by guardrail '{guardrail}' ({phase}): {verdict.reason}"
        )


__all__ = [
    "Decision",
    "Guardrail",
    "GuardrailBlocked",
    "GuardrailContext",
    "Match",
    "Verdict",
    "allow",
    "block",
    "flag",
    "redact",
]
