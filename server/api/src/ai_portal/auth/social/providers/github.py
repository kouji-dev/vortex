"""GitHub consumer OAuth (sign-in with GitHub).

Config (env):
- ``SOCIAL_GITHUB_CLIENT_ID`` (required)
- ``SOCIAL_GITHUB_CLIENT_SECRET`` (required)

GitHub may hide a user's email on the public profile; we fall back to the
``/user/emails`` endpoint to find the primary verified address.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.social.providers._base import (
    OAuth2SocialProvider,
    SocialOAuthError,
)
from ai_portal.auth.social.registry import (
    SocialProviderNotConfigured,
    register_social_provider,
)

_EMAILS_ENDPOINT = "https://api.github.com/user/emails"


class GitHubSocialProvider(OAuth2SocialProvider):
    name = "github"
    authorize_endpoint = "https://github.com/login/oauth/authorize"
    token_endpoint = "https://github.com/login/oauth/access_token"
    userinfo_endpoint = "https://api.github.com/user"
    default_scopes = ("read:user", "user:email")

    @classmethod
    def from_env(cls) -> GitHubSocialProvider:
        cid = os.environ.get("SOCIAL_GITHUB_CLIENT_ID", "").strip()
        secret = os.environ.get("SOCIAL_GITHUB_CLIENT_SECRET", "").strip()
        if not cid or not secret:
            raise SocialProviderNotConfigured("github")
        return cls(client_id=cid, client_secret=secret)

    async def exchange(
        self, *, params: dict[str, Any], state: str, redirect_uri: str
    ) -> UserClaims:
        # Reuse the base flow but capture the access token for the email lookup.
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
        if not profile.get("email"):
            profile["email"] = await self._primary_email(access_token)
        return self.claims_from_profile(profile, token=token)

    async def _primary_email(self, access_token: str) -> str | None:
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }
        resp = await self._get(_EMAILS_ENDPOINT, headers=headers)
        if resp.status_code >= 400:
            return None
        try:
            emails = resp.json()
        except (ValueError, httpx.HTTPError):
            return None
        if not isinstance(emails, list):
            return None
        verified = [e for e in emails if e.get("verified")]
        primary = next((e for e in verified if e.get("primary")), None)
        chosen = primary or (verified[0] if verified else None)
        return chosen.get("email") if chosen else None

    def claims_from_profile(
        self, profile: dict[str, Any], *, token: dict[str, Any]
    ) -> UserClaims:
        email = profile.get("email")
        sub = profile.get("id")
        if not email or sub is None:
            raise SocialOAuthError("github profile missing 'id' or verified email")
        return UserClaims(
            subject=str(sub),
            email=str(email),
            name=profile.get("name") or profile.get("login"),
            raw=profile,
        )


register_social_provider("github", GitHubSocialProvider.from_env)
