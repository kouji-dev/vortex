"""Phase G2 — OIDC provider (authlib + PKCE)."""

from __future__ import annotations

import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from ai_portal.auth.idp.protocol import IdentityProvider
from ai_portal.auth.idp.providers.oidc import (
    OidcError,
    OidcProvider,
)
from ai_portal.auth.idp.registry import get_provider


DISCOVERY_URL = "https://idp.example.com/.well-known/openid-configuration"
AUTH_EP = "https://idp.example.com/authorize"
TOKEN_EP = "https://idp.example.com/token"
REDIRECT = "https://app.example.com/v1/auth/sso/callback"


def _id_token(claims: dict) -> str:
    """Build a non-signed compact JWT (header.payload.sig). MVP only."""
    header = base64.urlsafe_b64encode(b'{"alg":"none"}').rstrip(b"=").decode()
    payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode())
        .rstrip(b"=")
        .decode()
    )
    return f"{header}.{payload}.sig"


def _make_provider() -> OidcProvider:
    return OidcProvider(
        client_id="cid",
        client_secret="csecret",
        discovery_url=DISCOVERY_URL,
    )


# ──────────────────────────────────────────────────────────────────────────
# Construction / factory
# ──────────────────────────────────────────────────────────────────────────
def test_from_config_requires_keys():
    with pytest.raises(OidcError):
        OidcProvider.from_config({"client_id": "cid"})  # missing discovery_url


def test_from_config_builds_instance():
    p = OidcProvider.from_config(
        {
            "client_id": "cid",
            "client_secret": "x",
            "discovery_url": DISCOVERY_URL,
            "scopes": ["openid", "email"],
        }
    )
    assert p.scopes == ("openid", "email")
    assert p.client_secret == "x"


def test_registry_resolves_oidc_kind():
    # importing the providers module triggers self-registration
    import ai_portal.auth.idp.providers.oidc  # noqa: F401

    inst = get_provider(
        "oidc",
        {"client_id": "cid", "discovery_url": DISCOVERY_URL},
    )
    assert isinstance(inst, OidcProvider)


def test_oidc_provider_satisfies_protocol():
    assert isinstance(_make_provider(), IdentityProvider)


# ──────────────────────────────────────────────────────────────────────────
# initiate — authorize URL with PKCE
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_initiate_returns_authorize_url_with_pkce(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    p = _make_provider()
    url = await p.initiate(state="opaque-state-1", redirect_uri=REDIRECT)
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == AUTH_EP
    assert qs["client_id"] == ["cid"]
    assert qs["redirect_uri"] == [REDIRECT]
    assert qs["state"] == ["opaque-state-1"]
    assert qs["response_type"] == ["code"]
    assert qs["scope"] == ["openid email profile"]
    assert qs["code_challenge_method"] == ["S256"]
    # base64url SHA256 → 43 chars
    assert len(qs["code_challenge"][0]) == 43


# ──────────────────────────────────────────────────────────────────────────
# complete — token exchange + claims extraction
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_complete_exchanges_code_and_returns_claims(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": AUTH_EP,
                "token_endpoint": TOKEN_EP,
            },
        )
    )
    id_token = _id_token(
        {
            "sub": "user-42",
            "email": "alice@acme.com",
            "name": "Alice",
            "groups": ["eng", "admins"],
        }
    )
    captured: dict = {}

    def _token_handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = parse_qs(request.content.decode())
        return httpx.Response(
            200,
            json={"access_token": "at", "id_token": id_token, "token_type": "Bearer"},
        )

    respx_mock.post(TOKEN_EP).mock(side_effect=_token_handler)

    p = _make_provider()
    await p.initiate(state="st-7", redirect_uri=REDIRECT)
    claims = await p.complete(
        params={"code": "the-code", "state": "st-7", "redirect_uri": REDIRECT},
        state="st-7",
    )

    assert captured["body"]["grant_type"] == ["authorization_code"]
    assert captured["body"]["code"] == ["the-code"]
    assert captured["body"]["client_id"] == ["cid"]
    assert captured["body"]["client_secret"] == ["csecret"]
    # PKCE verifier sent on exchange
    assert "code_verifier" in captured["body"]

    assert claims.subject == "user-42"
    assert claims.email == "alice@acme.com"
    assert claims.name == "Alice"
    assert claims.groups == ("eng", "admins")


@pytest.mark.asyncio
async def test_complete_rejects_state_mismatch(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200, json={"authorization_endpoint": AUTH_EP, "token_endpoint": TOKEN_EP}
        )
    )
    p = _make_provider()
    await p.initiate(state="st-a", redirect_uri=REDIRECT)
    with pytest.raises(OidcError, match="state mismatch"):
        await p.complete(
            params={"code": "c", "state": "st-b", "redirect_uri": REDIRECT},
            state="st-a",
        )


@pytest.mark.asyncio
async def test_complete_rejects_unknown_state(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200, json={"authorization_endpoint": AUTH_EP, "token_endpoint": TOKEN_EP}
        )
    )
    p = _make_provider()
    with pytest.raises(OidcError, match="PKCE verifier"):
        await p.complete(
            params={"code": "c", "state": "missing", "redirect_uri": REDIRECT},
            state="missing",
        )


@pytest.mark.asyncio
async def test_complete_rejects_missing_code(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200, json={"authorization_endpoint": AUTH_EP, "token_endpoint": TOKEN_EP}
        )
    )
    p = _make_provider()
    await p.initiate(state="st-1", redirect_uri=REDIRECT)
    with pytest.raises(OidcError, match="missing 'code'"):
        await p.complete(
            params={"state": "st-1", "redirect_uri": REDIRECT}, state="st-1"
        )


@pytest.mark.asyncio
async def test_complete_rejects_id_token_missing_email(respx_mock):
    respx_mock.get(DISCOVERY_URL).mock(
        return_value=httpx.Response(
            200, json={"authorization_endpoint": AUTH_EP, "token_endpoint": TOKEN_EP}
        )
    )
    id_token = _id_token({"sub": "u1"})  # no email
    respx_mock.post(TOKEN_EP).mock(
        return_value=httpx.Response(200, json={"id_token": id_token})
    )
    p = _make_provider()
    await p.initiate(state="st-x", redirect_uri=REDIRECT)
    with pytest.raises(OidcError, match="sub.*email"):
        await p.complete(
            params={"code": "c", "state": "st-x", "redirect_uri": REDIRECT},
            state="st-x",
        )
