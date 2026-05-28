"""Prompt-injection guardrail.

Two-layer detection:

1. Heuristics — regex patterns for the dominant attack shapes
   (ignore-instructions, role override, jailbreak personas, encoded
   payloads). Cheap, deterministic, ~zero latency.

2. Optional async classifier — callable that takes text and returns a
   score in [0, 1]. Wired by the orchestrator to ``gateway.complete``
   against an injection-detection model. Disabled by default.

Verdict policy:

- any heuristic ``block`` rule fires → ``action="block"``
- classifier score ≥ threshold → adds ``injection.classifier`` hit and
  forces ``block``
- encoding hint without an instruction-override is still flagged but
  reflected in metadata as a soft signal (block, since blobs are a
  known bypass channel and the buyer audience errs strict)
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable

from ai_portal.guardrails.gateway_shape.protocol import Hit, Verdict

# Each rule = (regex, category, score). Score is informational; presence
# of any match in this list forces a block.
_BLOCK_RULES: tuple[tuple[re.Pattern[str], str, float], ...] = (
    (
        re.compile(
            r"\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b"
            r"(?:previous|prior|above|earlier|all)\b[^.\n]{0,40}\b"
            r"(?:instruction|prompt|rule|direction|message)s?\b",
            re.IGNORECASE,
        ),
        "injection.override",
        0.95,
    ),
    (
        re.compile(
            r"\b(?:reveal|print|show|leak|dump|expose|repeat)\b[^.\n]{0,40}\b"
            r"(?:system|hidden|secret|internal|developer)\b[^.\n]{0,40}\b"
            r"(?:prompt|instructions?|message)\b",
            re.IGNORECASE,
        ),
        "injection.override",
        0.9,
    ),
    (
        re.compile(
            r"\b(?:enable|activate|switch\s+to|turn\s+on)\b[^.\n]{0,40}\b"
            r"(?:developer|dev|debug|god|admin|unrestricted|jailbreak)\b"
            r"[^.\n]{0,20}mode\b",
            re.IGNORECASE,
        ),
        "injection.jailbreak",
        0.9,
    ),
    (
        re.compile(
            r"\b(?:you\s+are\s+now|act\s+as|pretend\s+to\s+be|roleplay\s+as)\b"
            r"[^.\n]{0,40}\b(?:dan|stan|dude|evil|unrestricted|jailbroken)\b",
            re.IGNORECASE,
        ),
        "injection.jailbreak",
        0.92,
    ),
    (
        re.compile(r"\bDAN\s+(?:can|will)\b[^.\n]{0,40}\banything\b", re.IGNORECASE),
        "injection.jailbreak",
        0.85,
    ),
    (
        re.compile(
            r"<\s*(?:system|admin|developer|root|sudo)\s*>", re.IGNORECASE
        ),
        "injection.delimiter",
        0.85,
    ),
    (
        re.compile(
            r"\b(?:ignore|bypass|disable)\b[^.\n]{0,40}\b"
            r"(?:safety|content|moderation|guard|filter)s?\b",
            re.IGNORECASE,
        ),
        "injection.override",
        0.9,
    ),
)

# Encoding-bypass hints — long base64-shaped strings.
_BASE64_BLOB = re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")


def _heuristic_hits(text: str) -> list[Hit]:
    hits: list[Hit] = []
    for pattern, category, score in _BLOCK_RULES:
        for m in pattern.finditer(text):
            hits.append(
                Hit(
                    category=category,
                    score=score,
                    start=m.start(),
                    end=m.end(),
                    matched=m.group(0),
                )
            )
    for m in _BASE64_BLOB.finditer(text):
        hits.append(
            Hit(
                category="injection.encoding",
                score=0.7,
                start=m.start(),
                end=m.end(),
                matched=m.group(0)[:40] + "…",
            )
        )
    return hits


class PromptInjectionGuardrail:
    """Detects prompt-injection / jailbreak attempts in user input."""

    name = "prompt_injection"

    def __init__(
        self,
        *,
        classifier: Callable[[str], Awaitable[float]] | None = None,
        classifier_threshold: float = 0.5,
    ) -> None:
        self._classifier = classifier
        self._classifier_threshold = classifier_threshold

    async def scan(self, text: str) -> Verdict:
        hits = _heuristic_hits(text)
        heuristic_score = max((h.score for h in hits), default=0.0)
        metadata: dict[str, object] = {"heuristic_score": heuristic_score}

        if self._classifier is not None:
            try:
                cls_score = float(await self._classifier(text))
                metadata["classifier_score"] = cls_score
                if cls_score >= self._classifier_threshold:
                    hits.append(
                        Hit(category="injection.classifier", score=cls_score)
                    )
            except Exception as exc:  # noqa: BLE001 — classifier is best-effort
                metadata["classifier_error"] = repr(exc)

        flagged = bool(hits)
        action = "block" if flagged else "allow"
        return Verdict(
            flagged=flagged, action=action, hits=hits, metadata=metadata
        )


__all__ = ["PromptInjectionGuardrail"]
