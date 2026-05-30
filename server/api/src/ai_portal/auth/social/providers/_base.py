"""Shared OAuth2 authorization-code helper for social providers.

Implements the common dance: build the authorize URL, exchange the code for an
access token at the token endpoint, then call a userinfo endpoint to read the
profile. Subclasses supply endpoints, scopes, and a ``claims_from_profile``
mapper. State is verified by the caller (route) AND cross-checked here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

import httpx

from ai_portal.auth.idp.protocol import UserClaims


class SocialOAuthError(Exception):
    """OAuth handshake failure (state mismatch, token/userinfo error)."""


class OAuth2SocialProvider:
    """Base authorization-code social provider.

    Subclasses set ``name``, ``authorize_endpoint``, ``token_endpoint``,
    ``userinfo_endpoint``, ``default_scopes`` and implement
    :meth:`claims_from_profile`.
    """

    name: str = "oauth2"
    authorize_endpoint: str = ""
    token_endpoint: str = ""
    userinfo_endpoint: str = ""
    default_scopes: tuple[str, ...] = ()
    # Some providers (GitHub) want Accept: application/json on token exchange.
    token_accept_json: bool = True

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        scopes: tuple[str, ...] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.scopes = scopes or self.default_scopes
        self._http = http_client

    # ── public protocol surface ──────────────────────────────────────────
    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.scopes),
            "state": state,
        }
        return f"{self.authorize_endpoint}?{urlencode(params)}"

    async def exchange(
        self, *, params: dict[str, Any], state: str, redirect_uri: str
    ) -> UserClaims:
        if params.get("state") != state:
            raise SocialOAuthError("state mismatch")
        code = params.get("code")
        if not code:
            raise SocialOAuthError("missing 'code' in callback params")
        token = await self._exchange_code(code=code, redirect_uri=redirect_uri)
        access_token = token.get("access_token")
        if not access_token:
            raise SocialOAuthError("token response missing 'access_token'")
        profile = await self._fetch_userinfo(access_token)
        return self.claims_from_profile(profile, token=token)

    # ── overridable mapping ──────────────────────────────────────────────
    def claims_from_profile(
        self, profile: dict[str, Any], *, token: dict[str, Any]
    ) -> UserClaims:
        raise NotImplementedError

    # ── internals ────────────────────────────────────────────────────────
    async def _exchange_code(
        self, *, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        headers = {"Accept": "application/json"} if self.token_accept_json else {}
        resp = await self._post(self.token_endpoint, data=data, headers=headers)
        if resp.status_code >= 400:
            raise SocialOAuthError(
                f"token exchange failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

    async def _fetch_userinfo(self, access_token: str) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        resp = await self._get(self.userinfo_endpoint, headers=headers)
        if resp.status_code >= 400:
            raise SocialOAuthError(
                f"userinfo failed: {resp.status_code} {resp.text[:200]}"
            )
        return resp.json()

    async def _get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        if self._http is not None:
            return await self._http.get(url, headers=headers)
        async with httpx.AsyncClient(timeout=10.0) as http:
            return await http.get(url, headers=headers)

    async def _post(
        self, url: str, *, data: dict[str, str], headers: dict[str, str]
    ) -> httpx.Response:
        if self._http is not None:
            return await self._http.post(url, data=data, headers=headers)
        async with httpx.AsyncClient(timeout=10.0) as http:
            return await http.post(url, data=data, headers=headers)
