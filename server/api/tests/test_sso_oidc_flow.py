"""Unit tests for the OIDC SSO login/callback flow.

Tests:
- login URL generation via OidcProvider.initiate
- callback claim-verification path with real RSA-signed id_token
- id_token signature rejection (wrong key / tampered)
- missing id_token raises OidcError
- metadata missing jwks_uri/issuer raises OidcError

All HTTP is mocked with respx (discovery doc, JWKS endpoint, token endpoint).
No DB required — these tests are pure-unit.
"""
from __future__ import annotations

import json
import time
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import respx
from httpx import Response

from ai_portal.auth.idp.providers.oidc import OidcError, OidcProvider

# ── Constants ────────────────────────────────────────────────────────────────

ISSUER = "https://idp.test"
DISCOVERY_URL = f"{ISSUER}/.well-known/openid-configuration"
JWKS_URI = f"{ISSUER}/jwks"
TOKEN_ENDPOINT = f"{ISSUER}/token"
AUTHORIZATION_ENDPOINT = f"{ISSUER}/authorize"
CLIENT_ID = "vortex-app"
REDIRECT_URI = "https://app.test/v1/auth/sso/callback/oidc"

DISCOVERY_DOC = {
    "issuer": ISSUER,
    "authorization_endpoint": AUTHORIZATION_ENDPOINT,
    "token_endpoint": TOKEN_ENDPOINT,
    "jwks_uri": JWKS_URI,
}


# ── Helpers ───────────────────────────────────────────────────────────────────


def _jwks(private_key, kid: str = "k1") -> dict:
    """Build a JWKS JSON from an RSA private key."""
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private_key.public_key()))
    jwk["kid"] = kid
    return {"keys": [jwk]}


def _make_id_token(
    private_key,
    *,
    sub: str = "kc|42",
    email: str = "alice@acme.test",
    name: str = "Alice",
    groups: list[str] | None = None,
    iss: str = ISSUER,
    aud: str = CLIENT_ID,
    kid: str = "k1",
    extra: dict | None = None,
) -> str:
    now = int(time.time())
    payload: dict = {
        "sub": sub,
        "email": email,
        "name": name,
        "iss": iss,
        "aud": aud,
        "exp": now + 3600,
        "iat": now,
    }
    if groups is not None:
        payload["groups"] = groups
    if extra:
        payload.update(extra)
    return jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})


def _provider(*, discovery_url: str = DISCOVERY_URL) -> OidcProvider:
    return OidcProvider(
        client_id=CLIENT_ID,
        client_secret="secret",
        discovery_url=discovery_url,
    )


# ── Login URL generation ──────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_initiate_returns_authorization_url():
    """initiate() → URL that points at the IdP's authorization_endpoint."""
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)

    provider = _provider()
    url = await provider.initiate(state="test-state-1", redirect_uri=REDIRECT_URI)

    parsed = urlparse(url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "idp.test"
    assert parsed.path == "/authorize"

    qs = parse_qs(parsed.query)
    assert qs["client_id"] == [CLIENT_ID]
    assert qs["response_type"] == ["code"]
    assert qs["state"] == ["test-state-1"]
    assert qs["redirect_uri"] == [REDIRECT_URI]
    assert qs["code_challenge_method"] == ["S256"]
    assert "code_challenge" in qs
    assert "openid" in qs["scope"][0]


@pytest.mark.asyncio
@respx.mock
async def test_initiate_discovery_cached():
    """Second call to initiate() reuses cached metadata (only 1 HTTP GET)."""
    mock = respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)

    provider = _provider()
    await provider.initiate(state="s1", redirect_uri=REDIRECT_URI)
    await provider.initiate(state="s2", redirect_uri=REDIRECT_URI)

    assert mock.call_count == 1


# ── Callback: verified claims ─────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_complete_returns_verified_claims(rsa_key, mock_jwks_client):
    """Happy-path: valid code → token exchange → verified id_token → UserClaims."""
    id_token = _make_id_token(rsa_key, groups=["IT-Admins"])

    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    # Seed state cache via initiate first.
    await provider.initiate(state="st-1", redirect_uri=REDIRECT_URI)

    claims = await provider.complete(
        params={
            "code": "auth-code-xyz",
            "state": "st-1",
            "redirect_uri": REDIRECT_URI,
        },
        state="st-1",
    )

    assert claims.subject == "kc|42"
    assert claims.email == "alice@acme.test"
    assert claims.name == "Alice"
    assert "IT-Admins" in claims.groups


@pytest.mark.asyncio
@respx.mock
async def test_complete_user_claims_no_groups(rsa_key, mock_jwks_client):
    """id_token without groups claim → groups tuple is empty."""
    id_token = _make_id_token(rsa_key)  # no groups

    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    await provider.initiate(state="st-2", redirect_uri=REDIRECT_URI)
    claims = await provider.complete(
        params={"code": "code-abc", "state": "st-2", "redirect_uri": REDIRECT_URI},
        state="st-2",
    )
    assert claims.groups == ()


# ── Signature verification — rejection cases ──────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_complete_rejects_token_signed_by_wrong_key(rsa_key, mock_jwks_client):
    """id_token signed by a different key → OidcError (sig verification fails)."""
    from cryptography.hazmat.primitives.asymmetric import rsa as _rsa

    wrong_key = _rsa.generate_private_key(public_exponent=65537, key_size=2048)
    id_token = _make_id_token(wrong_key)  # signed by wrong_key

    # mock_jwks_client exposes rsa_key's public key → mismatch → rejection
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    await provider.initiate(state="st-3", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="id_token verification failed"):
        await provider.complete(
            params={"code": "code-xyz", "state": "st-3", "redirect_uri": REDIRECT_URI},
            state="st-3",
        )


@pytest.mark.asyncio
@respx.mock
async def test_complete_rejects_wrong_audience(rsa_key, mock_jwks_client):
    """id_token with wrong audience → OidcError."""
    id_token = _make_id_token(rsa_key, aud="other-app")

    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    await provider.initiate(state="st-4", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="id_token verification failed"):
        await provider.complete(
            params={"code": "code-xyz", "state": "st-4", "redirect_uri": REDIRECT_URI},
            state="st-4",
        )


@pytest.mark.asyncio
@respx.mock
async def test_complete_rejects_wrong_issuer(rsa_key, mock_jwks_client):
    """id_token with wrong issuer → OidcError."""
    id_token = _make_id_token(rsa_key, iss="https://evil.test")

    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    await provider.initiate(state="st-5", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="id_token verification failed"):
        await provider.complete(
            params={"code": "code-xyz", "state": "st-5", "redirect_uri": REDIRECT_URI},
            state="st-5",
        )


# ── Error cases ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_complete_missing_id_token(rsa_key):
    """Token endpoint response without id_token → OidcError."""
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"access_token": "at", "token_type": "bearer"}  # no id_token
    )

    provider = _provider()
    await provider.initiate(state="st-6", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="missing 'id_token'"):
        await provider.complete(
            params={"code": "code-xyz", "state": "st-6", "redirect_uri": REDIRECT_URI},
            state="st-6",
        )


@pytest.mark.asyncio
@respx.mock
async def test_complete_missing_code_raises():
    """Callback params without 'code' → OidcError immediately."""
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)

    provider = _provider()
    await provider.initiate(state="st-7", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="missing 'code'"):
        await provider.complete(
            params={"state": "st-7", "redirect_uri": REDIRECT_URI},
            state="st-7",
        )


@pytest.mark.asyncio
@respx.mock
async def test_complete_unknown_state_raises():
    """State not in cache (e.g., expired or replayed) → OidcError."""
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)

    provider = _provider()
    with pytest.raises(OidcError, match="PKCE verifier not found"):
        await provider.complete(
            params={"code": "code-xyz", "state": "ghost-state", "redirect_uri": REDIRECT_URI},
            state="ghost-state",
        )


@pytest.mark.asyncio
@respx.mock
async def test_complete_state_mismatch_raises():
    """State in params != state arg → OidcError."""
    respx.get(DISCOVERY_URL).respond(json=DISCOVERY_DOC)

    provider = _provider()
    await provider.initiate(state="real-state", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="state mismatch"):
        await provider.complete(
            params={"code": "code-xyz", "state": "tampered", "redirect_uri": REDIRECT_URI},
            state="real-state",
        )


@pytest.mark.asyncio
@respx.mock
async def test_metadata_missing_jwks_uri_raises(rsa_key):
    """Discovery doc without jwks_uri → OidcError before token verification."""
    bad_doc = {**DISCOVERY_DOC}
    del bad_doc["jwks_uri"]
    id_token = _make_id_token(rsa_key)

    respx.get(DISCOVERY_URL).respond(json=bad_doc)
    respx.post(TOKEN_ENDPOINT).respond(
        json={"id_token": id_token, "access_token": "at", "token_type": "bearer"}
    )

    provider = _provider()
    await provider.initiate(state="st-8", redirect_uri=REDIRECT_URI)
    with pytest.raises(OidcError, match="jwks_uri"):
        await provider.complete(
            params={"code": "code-xyz", "state": "st-8", "redirect_uri": REDIRECT_URI},
            state="st-8",
        )
