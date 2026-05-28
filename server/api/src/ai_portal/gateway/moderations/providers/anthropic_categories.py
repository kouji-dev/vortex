"""Anthropic-derived moderation.

Anthropic does not publish a moderation endpoint. We approximate by routing
the input through a Claude classifier prompt that emits a JSON object of
``{category: score}`` pairs. Provider then thresholds the scores into
boolean categories and fills the OpenAI-style category map.

The classifier call itself is injected (``classifier`` arg) so callers can
wire it through the gateway service (with caching, audit, etc.) without
this provider knowing about HTTP at all.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ai_portal.gateway.moderations.protocol import (
    CATEGORIES,
    ModerationResult,
)

Classifier = Callable[[str], Awaitable[dict[str, float]]]


class AnthropicCategoriesModerator:
    """Anthropic-classifier-derived moderation."""

    name = "anthropic_categories"

    def __init__(
        self,
        *,
        api_key: str,
        classifier: Classifier,
        threshold: float = 0.5,
    ) -> None:
        self._api_key = api_key
        self._classifier = classifier
        self._threshold = threshold

    async def moderate(
        self, inputs: list[str], *, model: str | None = None
    ) -> list[ModerationResult]:
        out: list[ModerationResult] = []
        for text in inputs:
            raw = await self._classifier(text)
            scores: dict[str, float] = {c: 0.0 for c in CATEGORIES}
            for k, v in (raw or {}).items():
                if k in scores:
                    scores[k] = float(v)
            cats = {c: scores[c] >= self._threshold for c in CATEGORIES}
            flagged = any(cats.values())
            out.append(
                ModerationResult(
                    flagged=flagged, categories=cats, category_scores=scores
                )
            )
        return out


__all__ = ["AnthropicCategoriesModerator"]
