"""GitLab consumer OAuth (sign-in with GitLab).

Config (env):
- ``SOCIAL_GITLAB_CLIENT_ID`` (required)
- ``SOCIAL_GITLAB_CLIENT_SECRET`` (required)
- ``SOCIAL_GITLAB_BASE_URL`` (optional — self-managed GitLab; default gitlab.com)
"""

from __future__ import annotations

import os
from typing import Any

from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.social.providers._base import (
    OAuth2SocialProvider,
    SocialOAuthError,
)
from ai_portal.auth.social.registry import (
    SocialProviderNotConfigured,
    register_social_provider,
)

_DEFAULT_BASE = "https://gitlab.com"


class GitLabSocialProvider(OAuth2SocialProvider):
    name = "gitlab"
    default_scopes = ("read_user",)

    def __init__(self, *, base_url: str = _DEFAULT_BASE, **kwargs: Any) -> None:
        base = base_url.rstrip("/")
        self.authorize_endpoint = f"{base}/oauth/authorize"
        self.token_endpoint = f"{base}/oauth/token"
        self.userinfo_endpoint = f"{base}/api/v4/user"
        super().__init__(**kwargs)

    @classmethod
    def from_env(cls) -> GitLabSocialProvider:
        cid = os.environ.get("SOCIAL_GITLAB_CLIENT_ID", "").strip()
        secret = os.environ.get("SOCIAL_GITLAB_CLIENT_SECRET", "").strip()
        if not cid or not secret:
            raise SocialProviderNotConfigured("gitlab")
        base = os.environ.get("SOCIAL_GITLAB_BASE_URL", "").strip() or _DEFAULT_BASE
        return cls(client_id=cid, client_secret=secret, base_url=base)

    def claims_from_profile(
        self, profile: dict[str, Any], *, token: dict[str, Any]
    ) -> UserClaims:
        email = profile.get("email")
        sub = profile.get("id")
        if not email or sub is None:
            raise SocialOAuthError("gitlab profile missing 'id' or 'email'")
        return UserClaims(
            subject=str(sub),
            email=str(email),
            name=profile.get("name") or profile.get("username"),
            raw=profile,
        )


register_social_provider("gitlab", GitLabSocialProvider.from_env)
