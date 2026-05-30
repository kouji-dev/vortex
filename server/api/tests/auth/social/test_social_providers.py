"""Social OAuth providers — authorize URL + token/userinfo exchange (respx)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from ai_portal.auth.social.providers._base import SocialOAuthError
from ai_portal.auth.social.providers.github import GitHubSocialProvider
from ai_portal.auth.social.providers.gitlab import GitLabSocialProvider
from ai_portal.auth.social.providers.google import GoogleSocialProvider
from ai_portal.auth.social.protocol import SocialProvider
from ai_portal.auth.social.registry import (
    SocialProviderNotConfigured,
    available_social_providers,
    get_social_provider,
    registered_names,
)

REDIRECT = "https://app.example.com/v1/auth/social/google/callback"


def _google() -> GoogleSocialProvider:
    return GoogleSocialProvider(client_id="cid", client_secret="secret")


# ── protocol / registry ─────────────────────────────────────────────────────
def test_providers_satisfy_protocol():
    assert isinstance(_google(), SocialProvider)
    assert isinstance(
        GitHubSocialProvider(client_id="c", client_secret="s"), SocialProvider
    )
    assert isinstance(
        GitLabSocialProvider(client_id="c", client_secret="s"), SocialProvider
    )


def test_registry_lists_known_names():
    names = registered_names()
    assert {"google", "github", "gitlab"} <= set(names)


def test_unconfigured_provider_not_advertised(monkeypatch):
    for k in (
        "SOCIAL_GOOGLE_CLIENT_ID",
        "SOCIAL_GOOGLE_CLIENT_SECRET",
        "SOCIAL_GITHUB_CLIENT_ID",
        "SOCIAL_GITHUB_CLIENT_SECRET",
        "SOCIAL_GITLAB_CLIENT_ID",
        "SOCIAL_GITLAB_CLIENT_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)
    # None configured → none advertised, and get_social_provider raises.
    assert available_social_providers() == ()
    with pytest.raises(SocialProviderNotConfigured):
        get_social_provider("google")


def test_configured_provider_is_advertised(monkeypatch):
    monkeypatch.setenv("SOCIAL_GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("SOCIAL_GOOGLE_CLIENT_SECRET", "sec")
    assert "google" in available_social_providers()
    prov = get_social_provider("google")
    assert isinstance(prov, GoogleSocialProvider)


# ── authorize url ───────────────────────────────────────────────────────────
def test_authorize_url_has_oauth_params():
    url = _google().authorize_url(state="st-1", redirect_uri=REDIRECT)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.netloc == "accounts.google.com"
    assert qs["client_id"] == ["cid"]
    assert qs["redirect_uri"] == [REDIRECT]
    assert qs["state"] == ["st-1"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["openid email profile"]


def test_gitlab_self_managed_base_url():
    prov = GitLabSocialProvider(
        client_id="c", client_secret="s", base_url="https://git.acme.io"
    )
    url = prov.authorize_url(state="x", redirect_uri=REDIRECT)
    assert url.startswith("https://git.acme.io/oauth/authorize")


# ── exchange ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_google_exchange_returns_claims(respx_mock):
    respx_mock.post("https://oauth2.googleapis.com/token").mock(
        return_value=httpx.Response(200, json={"access_token": "at"})
    )
    respx_mock.get("https://openidconnect.googleapis.com/v1/userinfo").mock(
        return_value=httpx.Response(
            200,
            json={"sub": "g-1", "email": "alice@acme.com", "name": "Alice"},
        )
    )
    claims = await _google().exchange(
        params={"code": "c", "state": "st"}, state="st", redirect_uri=REDIRECT
    )
    assert claims.subject == "g-1"
    assert claims.email == "alice@acme.com"
    assert claims.name == "Alice"


@pytest.mark.asyncio
async def test_exchange_rejects_state_mismatch():
    with pytest.raises(SocialOAuthError, match="state mismatch"):
        await _google().exchange(
            params={"code": "c", "state": "bad"}, state="good", redirect_uri=REDIRECT
        )


@pytest.mark.asyncio
async def test_github_falls_back_to_emails_endpoint(respx_mock):
    prov = GitHubSocialProvider(client_id="c", client_secret="s")
    respx_mock.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "at"})
    )
    respx_mock.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"id": 42, "login": "octocat", "email": None})
    )
    respx_mock.get("https://api.github.com/user/emails").mock(
        return_value=httpx.Response(
            200,
            json=[
                {"email": "octo@acme.com", "primary": True, "verified": True},
                {"email": "other@acme.com", "primary": False, "verified": True},
            ],
        )
    )
    claims = await prov.exchange(
        params={"code": "c", "state": "st"}, state="st", redirect_uri=REDIRECT
    )
    assert claims.email == "octo@acme.com"
    assert claims.subject == "42"
    assert claims.name == "octocat"
