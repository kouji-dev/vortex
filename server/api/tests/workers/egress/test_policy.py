"""Tests for the egress allow-list policy (default deny)."""

from __future__ import annotations

import pytest

from ai_portal.workers.egress.policy import (
    EgressBlocked,
    EgressPolicy,
    check_host,
    check_url,
)


def test_default_deny_when_empty() -> None:
    p = EgressPolicy()
    assert not p.check("anything.com").allowed


def test_exact_host_match() -> None:
    p = EgressPolicy.from_list(["api.openai.com"])
    d = p.check("api.openai.com")
    assert d.allowed
    assert d.matched == "api.openai.com"
    assert not p.check("evil.com").allowed


def test_star_wildcard_only_matches_subdomains() -> None:
    p = EgressPolicy.from_list(["*.openai.com"])
    assert p.check("api.openai.com").allowed
    assert p.check("x.api.openai.com").allowed
    # apex must NOT match *.openai.com
    assert not p.check("openai.com").allowed


def test_dot_prefix_matches_apex_and_subs() -> None:
    p = EgressPolicy.from_list([".openai.com"])
    assert p.check("openai.com").allowed
    assert p.check("api.openai.com").allowed


def test_case_insensitive() -> None:
    p = EgressPolicy.from_list(["API.OPENAI.COM"])
    assert p.check("api.openai.com").allowed


def test_url_helper_strips_scheme() -> None:
    p = EgressPolicy.from_list(["api.openai.com"])
    d = check_url(p, "https://api.openai.com/v1/chat")
    assert d.allowed
    assert d.host == "api.openai.com"


def test_url_helper_handles_schemeless() -> None:
    p = EgressPolicy.from_list(["api.openai.com"])
    assert check_url(p, "api.openai.com/path").allowed


def test_empty_host_blocked() -> None:
    p = EgressPolicy.from_list(["foo.com"])
    d = check_host(p, "")
    assert not d.allowed
    assert "empty" in (d.reason or "")


def test_blocked_exception_carries_context() -> None:
    e = EgressBlocked("bad.tld", reason="x")
    assert e.host == "bad.tld" and e.reason == "x"
    assert "bad.tld" in str(e)
