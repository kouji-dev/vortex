"""OpenAI-moderation guardrail.

Wraps a :class:`Moderator` (typically the OpenAI moderation provider
under :mod:`ai_portal.gateway.moderations.providers.openai_moderation`)
and adapts its :class:`ModerationResult` into a :class:`Verdict`.

Why the wrapper exists:

- Moderators answer "is this text harmful, by which category?" — that
  shape is wire-compatible with the OpenAI moderations endpoint.
- Guardrails answer "what should the gateway do — allow, redact, block?"
- Threshold + action policy live here, not in the moderation provider.

Construction takes an already-built ``Moderator`` so the orchestrator
can compose this with any HTTP-routed implementation (gateway-routed
OpenAI, or any other Moderator implementation).
"""

from __future__ import annotations

from ai_portal.gateway.moderations.protocol import Moderator
from ai_portal.guardrails.gateway_shape.protocol import Hit, Verdict


class OpenAIModerationGuardrail:
    """Block-on-flag guardrail backed by an OpenAI moderation provider."""

    name = "openai_moderation"

    def __init__(
        self,
        *,
        moderator: Moderator,
        threshold: float = 0.5,
        model: str | None = None,
    ) -> None:
        self._moderator = moderator
        self._threshold = threshold
        self._model = model

    async def scan(self, text: str) -> Verdict:
        results = await self._moderator.moderate([text], model=self._model)
        metadata: dict[str, object] = {
            "provider": self.name,
            "upstream": getattr(self._moderator, "name", "unknown"),
        }
        if not results:
            return Verdict(
                flagged=False, action="allow", hits=[], metadata=metadata
            )
        result = results[0]
        hits = [
            Hit(category=cat, score=result.category_scores.get(cat, 0.0))
            for cat, on in result.categories.items()
            if on and result.category_scores.get(cat, 0.0) >= self._threshold
        ]
        flagged = bool(hits) or (
            result.flagged
            and any(s >= self._threshold for s in result.category_scores.values())
        )
        action = "block" if flagged else "allow"
        metadata["raw_flagged"] = result.flagged
        return Verdict(
            flagged=flagged, action=action, hits=hits, metadata=metadata
        )


__all__ = ["OpenAIModerationGuardrail"]
