"""Google preset — thin OIDC wrapper.

Google's discovery URL is fixed. The only required config key is the OAuth
``client_id`` issued from the Google Cloud console.

Config keys:
- ``client_id`` (required)
- ``client_secret`` (optional — required for confidential clients).
- ``scopes`` (optional).
- ``hd`` (optional) — restrict to a G-Suite/Workspace hosted domain. Forwarded
  on the authorize URL via the ``hd`` query parameter.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from ai_portal.auth.idp.providers.oidc import OidcError, OidcProvider
from ai_portal.auth.idp.registry import register_provider

DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"


class GoogleProvider(OidcProvider):
    """Google OIDC wrapper.

    Adds an optional ``hd`` (hosted-domain) query parameter on the authorize
    URL — the Google-recommended way to lock the consent screen to a single
    Workspace domain.
    """

    name = "google"

    def __init__(self, *, hd: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.hd = hd

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "GoogleProvider":
        if not config.get("client_id"):
            raise OidcError("google config missing keys: ['client_id']")
        scopes = tuple(config.get("scopes") or ("openid", "email", "profile"))
        return cls(
            client_id=config["client_id"],
            client_secret=config.get("client_secret"),
            discovery_url=DISCOVERY_URL,
            scopes=scopes,
            hd=config.get("hd"),
        )

    async def initiate(self, *, state: str, redirect_uri: str) -> str:
        url = await super().initiate(state=state, redirect_uri=redirect_uri)
        if self.hd:
            joiner = "&" if "?" in url else "?"
            url = f"{url}{joiner}{urlencode({'hd': self.hd})}"
        return url


register_provider("google", GoogleProvider.from_config)
