"""Google consumer OAuth (sign-in with Google).

Config (env):
- ``SOCIAL_GOOGLE_CLIENT_ID`` (required)
- ``SOCIAL_GOOGLE_CLIENT_SECRET`` (required)

Distinct from the enterprise Google Workspace SSO preset in ``auth/idp``.
"""

from __future__ import annotations

import os
from typing import Any

from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.social.providers._base import OAuth2SocialProvider
from ai_portal.auth.social.registry import (
    SocialProviderNotConfigured,
    register_social_provider,
)


class GoogleSocialProvider(OAuth2SocialProvider):
    name = "google"
    authorize_endpoint = "https://accounts.google.com/o/oauth2/v2/auth"
    token_endpoint = "https://oauth2.googleapis.com/token"
    userinfo_endpoint = "https://openidconnect.googleapis.com/v1/userinfo"
    default_scopes = ("openid", "email", "profile")

    @classmethod
    def from_env(cls) -> GoogleSocialProvider:
        cid = os.environ.get("SOCIAL_GOOGLE_CLIENT_ID", "").strip()
        secret = os.environ.get("SOCIAL_GOOGLE_CLIENT_SECRET", "").strip()
        if not cid or not secret:
            raise SocialProviderNotConfigured("google")
        return cls(client_id=cid, client_secret=secret)

    def claims_from_profile(
        self, profile: dict[str, Any], *, token: dict[str, Any]
    ) -> UserClaims:
        email = profile.get("email")
        sub = profile.get("sub")
        if not email or not sub:
            from ai_portal.auth.social.providers._base import SocialOAuthError

            raise SocialOAuthError("google profile missing 'sub' or 'email'")
        return UserClaims(
            subject=str(sub),
            email=str(email),
            name=profile.get("name"),
            raw=profile,
        )


register_social_provider("google", GoogleSocialProvider.from_env)
