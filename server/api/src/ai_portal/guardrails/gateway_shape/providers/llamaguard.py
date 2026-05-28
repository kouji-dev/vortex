"""LlamaGuard guardrail — self-hosted, gateway-routed.

Wraps the existing :class:`LlamaGuardModerator` (or any Moderator
named ``llamaguard``) and adapts the result to a :class:`Verdict`.

LlamaGuard returns binary categories (1.0 or 0.0), so the threshold
defaults to ``0.5`` and any flagged category becomes a hit.
"""

from __future__ import annotations

from ai_portal.gateway.moderations.protocol import Moderator
from ai_portal.guardrails.gateway_shape.protocol import Hit, Verdict


class LlamaGuardGuardrail:
    """Block-on-flag guardrail backed by a LlamaGuard moderation provider."""

    name = "llamaguard"

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
            Hit(category=cat, score=result.category_scores.get(cat, 1.0))
            for cat, on in result.categories.items()
            if on and result.category_scores.get(cat, 1.0) >= self._threshold
        ]
        flagged = bool(hits) or result.flagged
        action = "block" if flagged else "allow"
        metadata["raw_flagged"] = result.flagged
        return Verdict(
            flagged=flagged, action=action, hits=hits, metadata=metadata
        )


__all__ = ["LlamaGuardGuardrail"]
