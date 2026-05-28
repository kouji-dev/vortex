"""Gateway-shape guardrail protocol + Verdict.

A guardrail inspects one text payload (prompt or completion) and returns
a :class:`Verdict`. The verdict is advisory; the orchestrating service
maps it to ``allow | redact | block`` per workspace policy.

Owned by :mod:`ai_portal.guardrails.gateway_shape` — the consolidated
home. ``ai_portal.gateway.guardrails`` re-exports this for backward
compat.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol, runtime_checkable

Action = Literal["allow", "redact", "block"]


@dataclass(frozen=True)
class Hit:
    """One detection — category name + score + optional span."""

    category: str
    score: float
    start: int | None = None
    end: int | None = None
    matched: str | None = None


@dataclass(frozen=True)
class Verdict:
    """Outcome of a guardrail scan."""

    flagged: bool
    action: Action = "allow"
    hits: list[Hit] = field(default_factory=list)
    masked_text: str | None = None
    # Free-form provider metadata (model name, latency, raw score, …).
    metadata: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Guardrail(Protocol):
    """Scan one text payload, return a Verdict."""

    name: str

    async def scan(self, text: str) -> Verdict: ...


def clean() -> Verdict:
    """Convenience: an empty / passing verdict."""
    return Verdict(flagged=False, action="allow")


__all__ = ["Guardrail", "Verdict", "Hit", "Action", "clean"]
