"""Pattern-list regex guardrail.

Configure with a list of named patterns. Each match becomes a
:class:`Match`. The action (block / redact / flag) is decided by the
guardrail's mode; redact mode replaces every match with a configurable
placeholder.

Typical use:

.. code-block:: python

    rg = RegexGuardrail(
        name="custom-pii",
        patterns=[("EMAIL", r"[\\w.-]+@[\\w.-]+\\.\\w+")],
        mode="redact",
        placeholder="[REDACTED:{kind}]",
    )

Modes:

- ``block`` — any match returns :func:`block`.
- ``redact`` — substitutes every match with ``placeholder``.
- ``flag``  — records every match, does not edit.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Literal

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


class RegexGuardrail:
    """A guardrail backed by a list of named regex patterns."""

    def __init__(
        self,
        *,
        name: str = "regex",
        patterns: Sequence[tuple[str, str]],
        mode: Mode = "redact",
        placeholder: str = "[REDACTED:{kind}]",
        flags: int = re.IGNORECASE,
        check_phase: Literal["input", "output", "both"] = "both",
    ) -> None:
        self.name = name
        self._mode: Mode = mode
        self._placeholder = placeholder
        self._check_phase = check_phase
        self._patterns: list[tuple[str, re.Pattern[str]]] = [
            (kind, re.compile(p, flags)) for kind, p in patterns
        ]

    def _scan(self, text: str) -> list[Match]:
        out: list[Match] = []
        for kind, pat in self._patterns:
            for m in pat.finditer(text):
                out.append(
                    Match(
                        kind=kind,
                        start=m.start(),
                        end=m.end(),
                        snippet=m.group(0),
                    )
                )
        return out

    def _decide(self, text: str) -> Verdict:
        matches = self._scan(text)
        if not matches:
            return allow()
        if self._mode == "block":
            return block(
                matches=matches,
                reason=f"matched {len(matches)} pattern(s): "
                + ", ".join(sorted({m.kind for m in matches})),
            )
        if self._mode == "redact":
            edited = self._apply_redactions(text, matches)
            return redact(
                matches=matches,
                redacted_text=edited,
                reason="regex matches redacted",
            )
        return flag(matches=matches, reason="regex matches flagged")

    def _apply_redactions(self, text: str, matches: list[Match]) -> str:
        # Sort by start descending so substring offsets don't shift.
        ordered = sorted(matches, key=lambda m: m.start, reverse=True)
        out = text
        for m in ordered:
            replacement = self._placeholder.format(kind=m.kind)
            out = out[: m.start] + replacement + out[m.end :]
        return out

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        if self._check_phase == "output":
            return allow()
        return self._decide(prompt)

    async def check_output(
        self, response: str, ctx: GuardrailContext
    ) -> Verdict:
        if self._check_phase == "input":
            return allow()
        return self._decide(response)


__all__ = ["RegexGuardrail", "Mode"]
