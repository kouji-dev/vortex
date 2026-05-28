"""Per-pool egress allow-list — default deny.

The policy holds a set of host patterns (exact host, or ``*.suffix.tld``).
A request to a host is allowed iff it matches at least one pattern. IP
addresses are matched exactly (no CIDR-fancy logic in v1).

The check helpers also perform a basic URL parse so a tool can ask either
``check_host("api.openai.com")`` or ``check_url("https://api.openai.com/v1/...")``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urlsplit


class EgressBlocked(Exception):
    """Raised when an egress attempt is rejected by policy."""

    def __init__(self, host: str, reason: str = "not in allow list") -> None:
        super().__init__(f"egress blocked: {host} ({reason})")
        self.host = host
        self.reason = reason


@dataclass(frozen=True)
class EgressDecision:
    """Outcome of a single check — used for audit / event emission."""

    host: str
    allowed: bool
    matched: str | None = None
    reason: str | None = None


@dataclass
class EgressPolicy:
    """Allow-list for a single pool.

    Patterns are case-insensitive. Supported forms:
    - exact host: ``api.openai.com``
    - wildcard:   ``*.openai.com`` (matches any subdomain — not the apex)
    - apex+sub:   ``.openai.com`` (matches apex + subdomains)
    """

    allow_patterns: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_list(cls, items: Iterable[str]) -> "EgressPolicy":
        clean = tuple(p.strip().lower() for p in items if p and p.strip())
        return cls(allow_patterns=clean)

    def check(self, host: str) -> EgressDecision:
        if not host:
            return EgressDecision(host="", allowed=False, reason="empty host")
        h = host.lower().strip()
        for pat in self.allow_patterns:
            if _matches(pat, h):
                return EgressDecision(host=h, allowed=True, matched=pat)
        return EgressDecision(host=h, allowed=False, reason="not in allow list")


def _matches(pattern: str, host: str) -> bool:
    """Return True iff host matches pattern."""
    if pattern == host:
        return True
    if pattern.startswith("*."):
        suffix = pattern[1:]  # ".openai.com"
        return host.endswith(suffix) and host != suffix.lstrip(".")
    if pattern.startswith("."):
        # ".openai.com" → apex + subs
        suffix = pattern
        return host == suffix.lstrip(".") or host.endswith(suffix)
    return False


def check_host(policy: EgressPolicy, host: str) -> EgressDecision:
    return policy.check(host)


def check_url(policy: EgressPolicy, url: str) -> EgressDecision:
    """Parse a URL and check its host. Schemeless URLs default to https."""
    if "://" not in url:
        url = "https://" + url
    parts = urlsplit(url)
    host = parts.hostname or ""
    return policy.check(host)
