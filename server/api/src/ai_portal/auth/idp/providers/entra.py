"""Microsoft Entra ID (Azure AD) preset — thin OIDC wrapper.

Fills in the tenant-scoped discovery URL and Entra's default scopes. All
heavy lifting (PKCE, token exchange, ID-token decoding) is inherited from
:class:`OidcProvider`.

Config keys:
- ``client_id`` (required)
- ``tenant_id`` (required) — Entra tenant GUID, ``common``, ``organizations``
  or a verified-domain alias.
- ``client_secret`` (optional)
- ``scopes`` (optional) — override the default ``openid email profile``.
"""

from __future__ import annotations

from typing import Any

from ai_portal.auth.idp.providers.oidc import OidcError, OidcProvider
from ai_portal.auth.idp.registry import register_provider


def _discovery_url(tenant_id: str) -> str:
    return (
        f"https://login.microsoftonline.com/{tenant_id}/v2.0"
        "/.well-known/openid-configuration"
    )


class EntraProvider(OidcProvider):
    """Entra ID (Azure AD) OIDC wrapper."""

    name = "entra"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "EntraProvider":
        missing = [k for k in ("client_id", "tenant_id") if not config.get(k)]
        if missing:
            raise OidcError(f"entra config missing keys: {missing}")
        scopes = tuple(config.get("scopes") or ("openid", "email", "profile"))
        return cls(
            client_id=config["client_id"],
            client_secret=config.get("client_secret"),
            discovery_url=_discovery_url(config["tenant_id"]),
            scopes=scopes,
        )


register_provider("entra", EntraProvider.from_config)
