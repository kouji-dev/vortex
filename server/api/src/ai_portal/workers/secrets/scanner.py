"""Secret-leak detection on diffs / commit text / shell output.

Used before a commit / PR is allowed. If any pattern matches, the worker
must block the commit and emit a ``secret_blocked`` event.

Patterns are conservative — common provider tokens and high-entropy
markers (``BEGIN PRIVATE KEY`` blocks). Custom secret values can also be
passed in explicitly (e.g. resolved plaintexts the worker just injected)
to catch accidental dumps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# Provider-prefixed tokens.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "aws_access_key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "aws_secret": re.compile(
        r"(?i)aws(.{0,20})?(secret|access).{0,20}?[\"'`= ]([A-Za-z0-9/+=]{40})"
    ),
    "github_pat": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "stripe_live": re.compile(r"\bsk_live_[A-Za-z0-9]{16,}\b"),
    "stripe_test": re.compile(r"\bsk_test_[A-Za-z0-9]{16,}\b"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "anthropic_key": re.compile(r"\bsk-ant-[A-Za-z0-9-_]{20,}\b"),
    "google_api": re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    "slack_token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"),
    "private_key_block": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\."
                      r"[A-Za-z0-9_-]{10,}\b"),
}


@dataclass(frozen=True)
class LeakHit:
    """One leak finding."""

    kind: str
    excerpt: str
    line_no: int | None = None


def _redact(s: str, max_len: int = 24) -> str:
    if len(s) <= max_len:
        return s[:8] + "***"
    return s[:8] + "***" + s[-4:]


def scan_for_leaks(
    text: str,
    *,
    known_secrets: Iterable[str] = (),
) -> list[LeakHit]:
    """Scan ``text`` against the bundled patterns + any known plaintexts.

    Returns a list of hits with redacted excerpts so the result itself is
    safe to log / store in audit.
    """
    hits: list[LeakHit] = []
    for kind, pat in _PATTERNS.items():
        for m in pat.finditer(text):
            hits.append(LeakHit(kind=kind, excerpt=_redact(m.group(0))))
    for needle in known_secrets:
        if not needle:
            continue
        if needle in text:
            hits.append(LeakHit(kind="known_secret", excerpt=_redact(needle)))
    return hits


def scan_diff_for_leaks(
    diff_text: str,
    *,
    known_secrets: Iterable[str] = (),
) -> list[LeakHit]:
    """Scan only the *added* lines of a unified diff.

    Lines that begin with ``+`` (but not ``+++``) are scanned. Other lines
    are ignored — we don't care about secrets that are being removed.
    """
    hits: list[LeakHit] = []
    for i, line in enumerate(diff_text.splitlines(), start=1):
        if not line.startswith("+") or line.startswith("+++"):
            continue
        added = line[1:]
        for h in scan_for_leaks(added, known_secrets=known_secrets):
            hits.append(LeakHit(kind=h.kind, excerpt=h.excerpt, line_no=i))
    return hits
