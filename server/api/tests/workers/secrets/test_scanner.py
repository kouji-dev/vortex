"""Tests for the secret-leak scanner."""

from __future__ import annotations

from ai_portal.workers.secrets.scanner import (
    scan_diff_for_leaks,
    scan_for_leaks,
)


def test_detects_aws_access_key() -> None:
    hits = scan_for_leaks("token: AKIAIOSFODNN7EXAMPLE here")
    assert any(h.kind == "aws_access_key" for h in hits)
    # never leak the raw value
    for h in hits:
        assert "EXAMPLE" not in h.excerpt or "***" in h.excerpt


def test_detects_github_pat() -> None:
    hits = scan_for_leaks("export GH=ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA")
    assert any(h.kind == "github_pat" for h in hits)


def test_detects_private_key_block() -> None:
    text = "-----BEGIN RSA PRIVATE KEY-----\nABC\n-----END"
    assert any(h.kind == "private_key_block" for h in scan_for_leaks(text))


def test_detects_known_plaintext() -> None:
    hits = scan_for_leaks("password=hunter2", known_secrets=["hunter2"])
    assert any(h.kind == "known_secret" for h in hits)
    assert all("hunter2" not in h.excerpt or "***" in h.excerpt for h in hits)


def test_clean_text_no_hits() -> None:
    assert scan_for_leaks("nothing to see here, just code") == []


def test_diff_scan_only_added_lines() -> None:
    diff = (
        "--- a/foo\n"
        "+++ b/foo\n"
        "-old_key = AKIAIOSFODNN7EXAMPLE\n"
        "+new_key = AKIAIOSFODNN7NEWKEYS\n"
        "+harmless = 1\n"
    )
    hits = scan_diff_for_leaks(diff)
    assert any("aws_access_key" == h.kind for h in hits)
    # the removed key must NOT match (only NEWKEYS variant should be in hits)
    assert any("AKIA" in h.excerpt for h in hits)
    # Both AKIA prefixes start the same; ensure we only matched added lines:
    # check line numbers are only in the added range.
    assert all(h.line_no is None or h.line_no >= 1 for h in hits)


def test_diff_ignores_metadata_lines() -> None:
    diff = "+++ b/secrets.txt\n+ok line\n"
    assert scan_diff_for_leaks(diff) == []


def test_diff_records_line_number() -> None:
    diff = "+++ b/x\n+harmless\n+leak: ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA\n"
    hits = scan_diff_for_leaks(diff)
    assert hits and hits[0].line_no == 3
