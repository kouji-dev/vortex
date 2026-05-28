"""Topic deny/allow guardrail — sentence-level keyword classifier.

Two modes, combinable:

- ``deny``: any matched term in the text → block (or redact/flag).
- ``allow``: when non-empty, text must contain at least one allow term —
  otherwise blocked (``topic_allow_miss``).

Matching is case-insensitive and word-boundary aware so ``arm`` does not hit
``alarm``. Multi-word phrases (``"prompt injection"``) match across spaces.

For semantic-level topic classification, use ``custom_classifier`` with an
embedding-based classifier instead.
"""

from __future__ import annotations

import re
from typing import Literal

from ai_portal.guardrails.protocol import (
    Decision,
    GuardrailCtx,
    Match,
    Verdict,
)

_PLACEHOLDER = "[REDACTED]"


def _compile_terms(terms: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Return list of (original_term, regex) with word-boundary matching."""
    out: list[tuple[str, re.Pattern[str]]] = []
    for t in terms:
        if not t:
            continue
        # Escape per-char then re-allow whitespace between escaped words so
        # ``prompt injection`` still matches ``prompt   injection``.
        escaped = re.escape(t).replace(r"\ ", r"\s+")
        pattern = re.compile(rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])", re.IGNORECASE)
        out.append((t, pattern))
    return out


class TopicFilter:
    """Deny/allow list keyword guardrail."""

    name = "topic_filter"

    def __init__(
        self,
        *,
        deny: list[str] | None = None,
        allow: list[str] | None = None,
        on_violation: Literal["block", "redact", "flag"] = "block",
    ) -> None:
        self._deny_terms = list(deny or [])
        self._allow_terms = list(allow or [])
        self._on_violation: Decision = on_violation

    async def check_input(self, prompt: str, ctx: GuardrailCtx) -> Verdict:
        return self._evaluate(prompt, ctx)

    async def check_output(self, response: str, ctx: GuardrailCtx) -> Verdict:
        return self._evaluate(response, ctx)

    def _evaluate(self, text: str, ctx: GuardrailCtx) -> Verdict:
        deny = ctx.config.get("deny", self._deny_terms)
        allow = ctx.config.get("allow", self._allow_terms)
        deny_compiled = _compile_terms(list(deny))
        allow_compiled = _compile_terms(list(allow))

        # 1. Deny check beats allow check.
        deny_matches: list[Match] = []
        for term, pattern in deny_compiled:
            for m in pattern.finditer(text):
                deny_matches.append(
                    Match(
                        rule="topic_deny",
                        span=(m.start(), m.end()),
                        detail=term,
                    )
                )
        if deny_matches:
            reason = (
                f"denied topic(s): {', '.join(sorted({m.detail or '' for m in deny_matches}))}"
            )
            if self._on_violation == "redact":
                redacted = text
                # remove all denied spans (largest first to keep offsets stable)
                spans = sorted(
                    (m.span for m in deny_matches if m.span is not None),
                    key=lambda s: -s[0],
                )
                for start, end in spans:
                    redacted = redacted[:start] + _PLACEHOLDER + redacted[end:]
                return Verdict(
                    decision="redact",
                    matches=deny_matches,
                    redacted_text=redacted,
                    reason=reason,
                )
            return Verdict(
                decision=self._on_violation,
                matches=deny_matches,
                reason=reason,
            )

        # 2. Allow-list gate (only when configured).
        if allow_compiled:
            for _, pattern in allow_compiled:
                if pattern.search(text):
                    return Verdict(decision="allow")
            return Verdict(
                decision=self._on_violation if self._on_violation != "redact" else "block",
                matches=[Match(rule="topic_allow_miss", detail="none of allow terms hit")],
                reason="text does not mention any allowed topic",
            )

        return Verdict(decision="allow")


def _check_protocol() -> None:  # pragma: no cover
    from ai_portal.guardrails.protocol import Guardrail

    _: Guardrail = TopicFilter()


__all__ = ["TopicFilter"]
