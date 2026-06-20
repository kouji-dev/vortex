"""OIDC Identity Provider — Authorization Code + PKCE.

Discovers endpoints from the IdP's ``.well-known/openid-configuration`` and
exchanges the authorization code for an ID token at the token endpoint.

PKCE state: ``initiate`` generates a ``code_verifier`` and stores it in an
in-memory map keyed by the caller-supplied ``state`` value. ``complete``
pops the verifier and includes it in the token exchange. Callers using a
multi-process deployment must wrap this with their own state store (e.g.
Redis) and supply a custom ``state_store`` on construction.

This module registers itself as ``oidc`` in the IdP registry on import.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
from typing import Any
from urllib.parse import urlencode

import httpx

from ai_portal.auth.idp.protocol import IdentityProvider, UserClaims
from ai_portal.auth.idp.registry import register_provider
from ai_portal.auth.oidc.jwks import make_claims, verify_id_token


class OidcError(Exception):
    """Generic OIDC failure (discovery, token exchange, missing state)."""


class _MemoryStateStore:
    """Tiny in-process store. Replace in prod with Redis-backed implementation."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._data: dict[str, str] = {}

    async def put(self, state: str, verifier: str) -> None:
        async with self._lock:
            self._data[state] = verifier

    async def pop(self, state: str) -> str | None:
        async with self._lock:
            return self._data.pop(state, None)


def _pkce_pair() -> tuple[str, str]:
    """Return (verifier, challenge) per RFC 7636 — SHA256, URL-safe base64."""
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class OidcProvider(IdentityProvider):
    """OpenID Connect provider with PKCE (RFC 7636)."""

    name = "oidc"

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str | None,
        discovery_url: str,
        scopes: tuple[str, ...] = ("openid", "email", "profile"),
        http_client: httpx.AsyncClient | None = None,
        state_store: _MemoryStateStore | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.discovery_url = discovery_url
        self.scopes = scopes
        self._http = http_client
        self._state_store = state_store or _MemoryStateStore()
        self._metadata: dict[str, Any] | None = None

    # ── factory ───────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OidcProvider":
        """Build from the JSON blob stored in ``IdpConnection.config_encrypted``.

        Required keys: ``client_id``, ``discovery_url``. Optional:
        ``client_secret``, ``scopes`` (list of strings).
        """
        missing = [k for k in ("client_id", "discovery_url") if k not in config]
        if missing:
            raise OidcError(f"oidc config missing keys: {missing}")
        scopes = tuple(config.get("scopes") or ("openid", "email", "profile"))
        return cls(
            client_id=config["client_id"],
            client_secret=config.get("client_secret"),
            discovery_url=config["discovery_url"],
            scopes=scopes,
        )

    # ── public protocol surface ───────────────────────────────────────────
    async def initiate(self, *, state: str, redirect_uri: str) -> str:
        meta = await self._discover()
        verifier, challenge = _pkce_pair()
        await self._state_store.put(state, verifier)
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return f"{meta['authorization_endpoint']}?{urlencode(params)}"

    async def complete(
        self, *, params: dict[str, Any], state: str
    ) -> UserClaims:
        code = params.get("code")
        if not code:
            raise OidcError("missing 'code' in callback params")
        if params.get("state") != state:
            raise OidcError("state mismatch")
        verifier = await self._state_store.pop(state)
        if verifier is None:
            raise OidcError("unknown state — PKCE verifier not found")
        token = await self._exchange_code(
            code=code,
            verifier=verifier,
            redirect_uri=params["redirect_uri"],
        )
        return await self._claims_from_token(token)

    # ── internals ─────────────────────────────────────────────────────────
    async def _discover(self) -> dict[str, Any]:
        if self._metadata is not None:
            return self._metadata
        resp = await self._get(self.discovery_url)
        resp.raise_for_status()
        self._metadata = resp.json()
        return self._metadata

    async def _exchange_code(
        self, *, code: str, verifier: str, redirect_uri: str
    ) -> dict[str, Any]:
        meta = await self._discover()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "code_verifier": verifier,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        resp = await self._post(meta["token_endpoint"], data=data)
        resp.raise_for_status()
        return resp.json()

    async def _get(self, url: str) -> httpx.Response:
        if self._http is not None:
            return await self._http.get(url)
        async with httpx.AsyncClient(timeout=10.0) as http:
            return await http.get(url)

    async def _post(self, url: str, *, data: dict[str, str]) -> httpx.Response:
        if self._http is not None:
            return await self._http.post(url, data=data)
        async with httpx.AsyncClient(timeout=10.0) as http:
            return await http.post(url, data=data)

    async def _claims_from_token(self, token: dict[str, Any]) -> UserClaims:
        """Verify the id_token signature against the IdP's JWKS and return claims.

        Replaces the old MVP base64-decode-without-verification path.
        ``jwks_uri`` and ``issuer`` come from the already-discovered metadata;
        ``audience`` is this provider's ``client_id``.
        """
        id_token = token.get("id_token")
        if not id_token:
            raise OidcError("token response missing 'id_token'")
        meta = await self._discover()
        jwks_uri = meta.get("jwks_uri")
        issuer = meta.get("issuer")
        if not jwks_uri or not issuer:
            raise OidcError("oidc metadata missing 'jwks_uri' or 'issuer'")
        try:
            payload = verify_id_token(
                id_token,
                jwks_uri=jwks_uri,
                issuer=issuer,
                audience=self.client_id,
            )
        except Exception as exc:
            raise OidcError(f"id_token verification failed: {exc}") from exc
        return make_claims(payload)


# Register on import so consumers only need `import ai_portal.auth.idp.providers`.
register_provider("oidc", OidcProvider.from_config)
