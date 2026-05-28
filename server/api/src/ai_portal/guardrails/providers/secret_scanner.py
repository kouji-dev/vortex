"""Secret-scanner guardrail.

Catches high-confidence secret formats — AWS access keys, GitHub PATs,
JWTs, Slack bot tokens, private keys, generic API-key-ish strings.

Defaults to **block** for input (no secret should leave the perimeter)
and **redact** for output (model leaked something). Override via
``input_mode`` / ``output_mode``.

The pattern catalog is intentionally conservative — false-positives
generate user pain. Adding a pattern means writing one test case that
asserts it catches the canonical example.
"""

from __future__ import annotations

import re
from typing import Literal

from ai_portal.guardrails.protocol import (
    GuardrailContext,
    Match,
    Verdict,
    allow,
    block,
    redact,
)

Mode = Literal["block", "redact", "flag"]


# Canonical secret patterns. (kind, regex). All anchored to whole-token
# boundaries so we don't match inside larger random strings.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "AWS_ACCESS_KEY",
        re.compile(r"\b((?:AKIA|ASIA|AIDA|AGPA|AROA|AIPA|ANPA|ANVA|ABIA|ACCA)[0-9A-Z]{16})\b"),
    ),
    (
        "AWS_SECRET_KEY",
        re.compile(
            r"(?<![A-Za-z0-9/+])([A-Za-z0-9/+]{40})(?![A-Za-z0-9/+])"
        ),
    ),
    (
        "GITHUB_PAT",
        re.compile(r"\b(ghp_[A-Za-z0-9]{36,})\b"),
    ),
    (
        "GITHUB_FINE_GRAINED_PAT",
        re.compile(r"\b(github_pat_[A-Za-z0-9_]{50,})\b"),
    ),
    (
        "SLACK_TOKEN",
        re.compile(r"\b(xox[abprs]-[A-Za-z0-9-]{10,})\b"),
    ),
    (
        "GOOGLE_API_KEY",
        re.compile(r"\b(AIza[0-9A-Za-z\-_]{35})\b"),
    ),
    (
        "STRIPE_LIVE_KEY",
        re.compile(r"\b(sk_live_[0-9A-Za-z]{24,})\b"),
    ),
    (
        "OPENAI_API_KEY",
        re.compile(r"\b(sk-[A-Za-z0-9_-]{20,})\b"),
    ),
    (
        "ANTHROPIC_API_KEY",
        re.compile(r"\b(sk-ant-[A-Za-z0-9_-]{30,})\b"),
    ),
    (
        "JWT",
        re.compile(
            r"\b(eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b"
        ),
    ),
    (
        "PRIVATE_KEY_BLOCK",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        ),
    ),
)


def _scan(text: str, *, skip_aws_secret_if_no_access: bool = True) -> list[Match]:
    """Run every pattern, return matches.

    ``AWS_SECRET_KEY`` is high false-positive (any 40-char base64 string
    matches). When ``skip_aws_secret_if_no_access`` is set we only report
    it if an ``AWS_ACCESS_KEY`` was also seen, mirroring trufflehog
    heuristics.

    Two-pass implementation: first detect AWS access keys so the secret
    pattern can decide whether to fire, then run every other pattern.
    """
    has_aws_access = bool(_AWS_ACCESS_PATTERN.search(text))

    matches: list[Match] = []
    for kind, pat in _SECRET_PATTERNS:
        if kind == "AWS_SECRET_KEY" and skip_aws_secret_if_no_access and not has_aws_access:
            continue
        for m in pat.finditer(text):
            matches.append(
                Match(
                    kind=kind,
                    start=m.start(),
                    end=m.end(),
                    snippet=m.group(0)[:64],
                )
            )

    # Sort + dedupe identical spans (some patterns overlap).
    seen: set[tuple[int, int, str]] = set()
    uniq: list[Match] = []
    for m in sorted(matches, key=lambda x: (x.start, x.end)):
        key = (m.start, m.end, m.kind)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)
    return uniq


_AWS_ACCESS_PATTERN = next(pat for kind, pat in _SECRET_PATTERNS if kind == "AWS_ACCESS_KEY")


def _apply_redaction(text: str, matches: list[Match], placeholder: str) -> str:
    ordered = sorted(matches, key=lambda m: m.start, reverse=True)
    out = text
    for m in ordered:
        out = out[: m.start] + placeholder.format(kind=m.kind) + out[m.end :]
    return out


class SecretScannerGuardrail:
    """Detects AWS keys, JWTs, GitHub PATs, etc."""

    name = "secret_scanner"

    def __init__(
        self,
        *,
        input_mode: Mode = "block",
        output_mode: Mode = "redact",
        placeholder: str = "[REDACTED:{kind}]",
    ) -> None:
        self._input_mode: Mode = input_mode
        self._output_mode: Mode = output_mode
        self._placeholder = placeholder

    def _verdict(self, text: str, mode: Mode) -> Verdict:
        matches = _scan(text)
        if not matches:
            return allow()
        kinds = sorted({m.kind for m in matches})
        if mode == "block":
            return block(
                matches=matches,
                reason=f"secret detected: {', '.join(kinds)}",
            )
        if mode == "redact":
            edited = _apply_redaction(text, matches, self._placeholder)
            return redact(
                matches=matches,
                redacted_text=edited,
                reason=f"secret redacted: {', '.join(kinds)}",
            )
        # flag
        from ai_portal.guardrails.protocol import flag

        return flag(
            matches=matches,
            reason=f"secret flagged: {', '.join(kinds)}",
        )

    async def check_input(self, prompt: str, ctx: GuardrailContext) -> Verdict:
        return self._verdict(prompt, self._input_mode)

    async def check_output(
        self, response: str, ctx: GuardrailContext
    ) -> Verdict:
        return self._verdict(response, self._output_mode)


__all__ = ["SecretScannerGuardrail", "Mode"]
