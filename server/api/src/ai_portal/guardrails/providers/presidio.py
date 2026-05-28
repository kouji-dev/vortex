"""Presidio-backed PII guardrail.

Wraps the `presidio-analyzer` library. Detects PII entities (EMAIL,
PHONE_NUMBER, CREDIT_CARD, ...). Configurable list of entities + score
threshold + action (block / redact / flag).

Lazy import: ``presidio-analyzer`` pulls in spaCy + an NLP model. We
import it only when the guardrail is instantiated so the rest of the
codebase stays cheap to load.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from ai_portal.guardrails.protocol import (
    GuardrailContext,
    Match,
    Verdict,
    allow,
    block,
    flag,
    redact,
)

Mode = Literal["block", "redact", "flag"]

DEFAULT_ENTITIES: tuple[str, ...] = (
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "US_SSN",
    "IBAN_CODE",
    "IP_ADDRESS",
    "PERSON",
)


class PresidioGuardrail:
    """PII detection via Microsoft Presidio.

    Construction is lazy: the analyzer is instantiated on first call.
    Tests can inject a fake analyzer via the ``analyzer`` kwarg.
    """

    name = "presidio"

    def __init__(
        self,
        *,
        entities: Sequence[str] = DEFAULT_ENTITIES,
        score_threshold: float = 0.5,
        mode: Mode = "redact",
        placeholder: str = "[REDACTED:{kind}]",
        analyzer: Any | None = None,
        language: str = "en",
    ) -> None:
        self._entities = list(entities)
        self._threshold = score_threshold
        self._mode: Mode = mode
        self._placeholder = placeholder
        self._language = language
        self._analyzer = analyzer

    def _get_analyzer(self) -> Any:
        if self._analyzer is not None:
            return self._analyzer
        try:
            from presidio_analyzer import (
                AnalyzerEngine,  # type: ignore[import-not-found]
            )
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "presidio-analyzer not installed. "
                "Install with `pip install presidio-analyzer`"
            ) from e
        self._analyzer = AnalyzerEngine()
        return self._analyzer

    def _analyze(self, text: str) -> list[Match]:
        analyzer = self._get_analyzer()
        results = analyzer.analyze(
            text=text,
            entities=self._entities,
            language=self._language,
        )
        matches: list[Match] = []
        for r in results:
            if float(getattr(r, "score", 0.0)) < self._threshold:
                continue
            start = int(getattr(r, "start", -1))
            end = int(getattr(r, "end", -1))
            snippet = text[start:end] if 0 <= start < end <= len(text) else ""
            matches.append(
                Match(
                    kind=str(getattr(r, "entity_type", "PII")),
                    start=start,
                    end=end,
                    snippet=snippet,
                    score=float(getattr(r, "score", 0.0)),
                )
            )
        return matches

    def _apply_redaction(self, text: str, matches: list[Match]) -> str:
        ordered = sorted(matches, key=lambda m: m.start, reverse=True)
        out = text
        for m in ordered:
            if m.start < 0 or m.end < 0:
                continue
            out = out[: m.start] + self._placeholder.format(kind=m.kind) + out[m.end :]
        return out

    def _decide(self, text: str) -> Verdict:
        matches = self._analyze(text)
        if not matches:
            return allow()
        kinds = sorted({m.kind for m in matches})
        if self._mode == "block":
            return block(
                matches=matches,
                reason=f"PII detected: {', '.join(kinds)}",
            )
        if self._mode == "redact":
            return redact(
                matches=matches,
                redacted_text=self._apply_redaction(text, matches),
                reason=f"PII redacted: {', '.join(kinds)}",
            )
        return flag(matches=matches, reason=f"PII flagged: {', '.join(kinds)}")

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        return self._decide(prompt)

    async def check_output(
        self, response: str, ctx: GuardrailContext
    ) -> Verdict:
        return self._decide(response)


__all__ = ["PresidioGuardrail", "DEFAULT_ENTITIES", "Mode"]
