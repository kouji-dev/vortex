"""Tests for secret binding selection."""

from __future__ import annotations

from ai_portal.workers.secrets.bindings import (
    SecretBinding,
    SecretRef,
    select_secrets_for_run,
)


def test_pool_wide_binding_applies_to_any_repo() -> None:
    b = SecretBinding(secret_ref="aws/key", allow_repos=())
    assert b.applies_to("acme/api")
    assert b.applies_to(None)


def test_per_repo_binding_only_matches_listed_repo() -> None:
    b = SecretBinding(secret_ref="npm/token", allow_repos=("acme/web",))
    assert b.applies_to("acme/web")
    assert not b.applies_to("acme/api")
    assert not b.applies_to(None)


def test_select_filters_by_repo_and_dedupes() -> None:
    bs = [
        SecretBinding("aws/key"),
        SecretBinding("npm/token", allow_repos=("acme/web",)),
        SecretBinding("gh/pat", allow_repos=("acme/api",)),
        SecretBinding("aws/key"),  # dupe should drop
    ]
    refs = select_secrets_for_run(bs, repo="acme/web")
    names = [r.ref for r in refs]
    assert names == ["aws/key", "npm/token"]


def test_select_no_match_returns_empty() -> None:
    bs = [SecretBinding("gh/pat", allow_repos=("acme/api",))]
    assert select_secrets_for_run(bs, repo="other/repo") == []


def test_secret_ref_str_roundtrip() -> None:
    assert str(SecretRef("aws/key")) == "aws/key"
