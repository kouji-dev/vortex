"""Okta preset — thin OIDC wrapper.

Fills in the Okta-org discovery URL from a ``domain`` config key. Scheme
and trailing slash on the supplied domain are stripped so callers can pass
either ``acme.okta.com`` or ``https://acme.okta.com/``.

Config keys:
- ``client_id`` (required)
- ``domain`` (required) — Okta org domain, e.g. ``acme.okta.com``.
- ``client_secret`` (optional)
- ``scopes`` (optional)
- ``authorization_server`` (optional) — defaults to the org-level discovery
  endpoint. Set to e.g. ``default`` to point at the ``default`` auth server.
"""

from __future__ import annotations

from typing import Any

from ai_portal.auth.idp.providers.oidc import OidcError, OidcProvider
from ai_portal.auth.idp.registry import register_provider


def _normalize_domain(raw: str) -> str:
    host = raw.strip()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix):]
    return host.rstrip("/")


def _discovery_url(domain: str, authorization_server: str | None) -> str:
    host = _normalize_domain(domain)
    if authorization_server:
        return f"https://{host}/oauth2/{authorization_server}/.well-known/openid-configuration"
    return f"https://{host}/.well-known/openid-configuration"


class OktaProvider(OidcProvider):
    """Okta OIDC wrapper."""

    name = "okta"

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "OktaProvider":
        missing = [k for k in ("client_id", "domain") if not config.get(k)]
        if missing:
            raise OidcError(f"okta config missing keys: {missing}")
        scopes = tuple(config.get("scopes") or ("openid", "email", "profile"))
        return cls(
            client_id=config["client_id"],
            client_secret=config.get("client_secret"),
            discovery_url=_discovery_url(
                config["domain"], config.get("authorization_server")
            ),
            scopes=scopes,
        )


register_provider("okta", OktaProvider.from_config)
