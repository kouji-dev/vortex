"""Moderation provider protocol.

One ``moderate`` call → list of :class:`ModerationResult`, one per input.
Each result has:

- ``flagged`` — overall verdict
- ``categories`` — per-category boolean map (OpenAI shape)
- ``category_scores`` — per-category float in [0, 1]

Categories follow OpenAI's moderation schema so the wire shape can be a
drop-in. Providers that return fewer categories must fill missing keys
with ``False`` / ``0.0``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# OpenAI moderation categories (current as of 2024 onwards).
CATEGORIES: tuple[str, ...] = (
    "sexual",
    "hate",
    "harassment",
    "self-harm",
    "sexual/minors",
    "hate/threatening",
    "violence/graphic",
    "self-harm/intent",
    "self-harm/instructions",
    "harassment/threatening",
    "violence",
)


@dataclass(frozen=True)
class ModerationResult:
    flagged: bool
    categories: dict[str, bool] = field(default_factory=dict)
    category_scores: dict[str, float] = field(default_factory=dict)


@runtime_checkable
class Moderator(Protocol):
    """Score arbitrary text for safety categories."""

    name: str

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        """Return one :class:`ModerationResult` per input, in order."""
        ...


def empty_result(*, flagged: bool = False) -> ModerationResult:
    """Build a zero-score result (handy when a provider declines to score)."""
    return ModerationResult(
        flagged=flagged,
        categories={c: False for c in CATEGORIES},
        category_scores={c: 0.0 for c in CATEGORIES},
    )


__all__ = ["Moderator", "ModerationResult", "CATEGORIES", "empty_result"]
