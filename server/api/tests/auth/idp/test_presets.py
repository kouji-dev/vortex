"""Phase G4 — IdP presets (Entra, Okta, Google).

Each preset is a thin OIDC wrapper that fills in the provider-specific
discovery URL and default scopes. Tests assert the redirect URL contains
the expected authorize host for each provider.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from ai_portal.auth.idp.protocol import IdentityProvider
from ai_portal.auth.idp.providers.entra import EntraProvider
from ai_portal.auth.idp.providers.google import GoogleProvider
from ai_portal.auth.idp.providers.okta import OktaProvider
from ai_portal.auth.idp.registry import get_provider

REDIRECT = "https://app.example.com/v1/auth/sso/callback"


# ──────────────────────────────────────────────────────────────────────────
# Entra (Azure AD)
# ──────────────────────────────────────────────────────────────────────────
def test_entra_from_config_builds_discovery_url():
    p = EntraProvider.from_config(
        {"client_id": "cid", "tenant_id": "tenant-abc"}
    )
    assert "tenant-abc" in p.discovery_url
    assert p.discovery_url.startswith("https://login.microsoftonline.com/")
    assert p.discovery_url.endswith("/v2.0/.well-known/openid-configuration")


def test_entra_from_config_defaults_scopes():
    p = EntraProvider.from_config(
        {"client_id": "cid", "tenant_id": "tenant-abc"}
    )
    assert p.scopes == ("openid", "email", "profile")


def test_entra_satisfies_protocol():
    p = EntraProvider.from_config(
        {"client_id": "cid", "tenant_id": "tenant-abc"}
    )
    assert isinstance(p, IdentityProvider)


def test_entra_registered_under_name():
    inst = get_provider("entra", {"client_id": "cid", "tenant_id": "t"})
    assert isinstance(inst, EntraProvider)


@pytest.mark.asyncio
async def test_entra_initiate_redirects_to_microsoft(respx_mock):
    discovery_url = (
        "https://login.microsoftonline.com/tenant-abc/v2.0/.well-known/openid-configuration"
    )
    auth_ep = "https://login.microsoftonline.com/tenant-abc/oauth2/v2.0/authorize"
    respx_mock.get(discovery_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": auth_ep,
                "token_endpoint": "https://login.microsoftonline.com/tenant-abc/oauth2/v2.0/token",
            },
        )
    )
    p = EntraProvider.from_config({"client_id": "cid", "tenant_id": "tenant-abc"})
    url = await p.initiate(state="st-1", redirect_uri=REDIRECT)
    parsed = urlparse(url)
    assert parsed.netloc == "login.microsoftonline.com"
    qs = parse_qs(parsed.query)
    assert qs["client_id"] == ["cid"]


# ──────────────────────────────────────────────────────────────────────────
# Okta
# ──────────────────────────────────────────────────────────────────────────
def test_okta_from_config_builds_discovery_url():
    p = OktaProvider.from_config(
        {"client_id": "cid", "domain": "acme.okta.com"}
    )
    assert p.discovery_url == "https://acme.okta.com/.well-known/openid-configuration"


def test_okta_satisfies_protocol():
    p = OktaProvider.from_config({"client_id": "cid", "domain": "acme.okta.com"})
    assert isinstance(p, IdentityProvider)


def test_okta_registered_under_name():
    inst = get_provider("okta", {"client_id": "cid", "domain": "acme.okta.com"})
    assert isinstance(inst, OktaProvider)


@pytest.mark.asyncio
async def test_okta_initiate_redirects_to_okta_domain(respx_mock):
    discovery_url = "https://acme.okta.com/.well-known/openid-configuration"
    auth_ep = "https://acme.okta.com/oauth2/v1/authorize"
    respx_mock.get(discovery_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": auth_ep,
                "token_endpoint": "https://acme.okta.com/oauth2/v1/token",
            },
        )
    )
    p = OktaProvider.from_config({"client_id": "cid", "domain": "acme.okta.com"})
    url = await p.initiate(state="st-1", redirect_uri=REDIRECT)
    parsed = urlparse(url)
    assert parsed.netloc == "acme.okta.com"


def test_okta_normalizes_domain_strips_scheme():
    p = OktaProvider.from_config(
        {"client_id": "cid", "domain": "https://acme.okta.com/"}
    )
    assert p.discovery_url == "https://acme.okta.com/.well-known/openid-configuration"


# ──────────────────────────────────────────────────────────────────────────
# Google
# ──────────────────────────────────────────────────────────────────────────
def test_google_from_config_uses_fixed_discovery_url():
    p = GoogleProvider.from_config({"client_id": "cid"})
    assert p.discovery_url == "https://accounts.google.com/.well-known/openid-configuration"


def test_google_satisfies_protocol():
    p = GoogleProvider.from_config({"client_id": "cid"})
    assert isinstance(p, IdentityProvider)


def test_google_registered_under_name():
    inst = get_provider("google", {"client_id": "cid"})
    assert isinstance(inst, GoogleProvider)


@pytest.mark.asyncio
async def test_google_initiate_redirects_to_accounts_google(respx_mock):
    discovery_url = "https://accounts.google.com/.well-known/openid-configuration"
    auth_ep = "https://accounts.google.com/o/oauth2/v2/auth"
    respx_mock.get(discovery_url).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": auth_ep,
                "token_endpoint": "https://oauth2.googleapis.com/token",
            },
        )
    )
    p = GoogleProvider.from_config({"client_id": "cid"})
    url = await p.initiate(state="st-1", redirect_uri=REDIRECT)
    parsed = urlparse(url)
    assert parsed.netloc == "accounts.google.com"
