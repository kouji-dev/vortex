"""Tests for hashing + excerpt helpers."""

from __future__ import annotations

from ai_portal.workers.audit_hooks.hashing import excerpt, sha256_hex


def test_sha256_string() -> None:
    h = sha256_hex("hello")
    assert h == "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"


def test_sha256_bytes() -> None:
    assert sha256_hex(b"hello") == sha256_hex("hello")


def test_sha256_empty() -> None:
    assert sha256_hex("") == sha256_hex(b"")


def test_excerpt_short_text_unchanged() -> None:
    assert excerpt("hello") == "hello"


def test_excerpt_truncates_long_text() -> None:
    long = "a" * 1000
    out = excerpt(long, head=10, tail=5)
    assert out.startswith("a" * 10)
    assert out.endswith("a" * 5)
    assert "…" in out
    assert len(out) < len(long)


def test_excerpt_empty() -> None:
    assert excerpt("") == ""
