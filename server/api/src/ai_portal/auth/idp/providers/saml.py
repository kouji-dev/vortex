"""SAML 2.0 Identity Provider — wraps ``python3-saml``.

``initiate`` builds an AuthnRequest via OneLogin's SAML toolkit and returns
the SSO redirect URL (HTTP-Redirect binding). ``complete`` parses + verifies
the signed SAML response (HTTP-POST binding) and returns the verified claims.

The IdP-side metadata (entity id, SSO URL, x509 cert) is carried in the
``IdpConnection.config_encrypted`` JSON blob. The SP-side config (entity id,
ACS URL) is passed alongside it.

Registers itself as ``saml`` in the IdP registry on import.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from onelogin.saml2.auth import OneLogin_Saml2_Auth

from ai_portal.auth.idp.protocol import IdentityProvider, UserClaims
from ai_portal.auth.idp.registry import register_provider


class SamlError(Exception):
    """SAML validation / config failure."""


# Standard SAML attribute URIs we map onto :class:`UserClaims` fields.
_EMAIL_ATTRS = (
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
    "urn:oid:0.9.2342.19200300.100.1.3",
    "email",
    "mail",
)
_NAME_ATTRS = (
    "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
    "urn:oid:2.16.840.1.113730.3.1.241",
    "displayName",
    "name",
)
_GROUP_ATTRS = (
    "http://schemas.xmlsoap.org/claims/Group",
    "groups",
    "memberOf",
)


def _build_settings(
    *,
    sp_entity_id: str,
    sp_acs_url: str,
    idp_entity_id: str,
    idp_sso_url: str,
    idp_x509_cert: str,
) -> dict[str, Any]:
    """Build a OneLogin SAML settings dict from flat config fields."""
    return {
        "strict": True,
        "debug": False,
        "sp": {
            "entityId": sp_entity_id,
            "assertionConsumerService": {
                "url": sp_acs_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
        },
        "idp": {
            "entityId": idp_entity_id,
            "singleSignOnService": {
                "url": idp_sso_url,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
            },
            "x509cert": idp_x509_cert,
        },
        "security": {
            "wantAssertionsSigned": True,
            "wantMessagesSigned": False,
            "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
        },
    }


def _request_data(
    *,
    acs_url: str,
    saml_response: str | None = None,
    relay_state: str | None = None,
) -> dict[str, Any]:
    parsed = urlparse(acs_url)
    https = parsed.scheme == "https"
    port = parsed.port or (443 if https else 80)
    return {
        "https": "on" if https else "off",
        "http_host": parsed.hostname or "",
        "server_port": port,
        "script_name": parsed.path or "/",
        "get_data": {},
        "post_data": {
            "SAMLResponse": saml_response or "",
            "RelayState": relay_state or "",
        },
    }


class SamlProvider(IdentityProvider):
    """SAML 2.0 provider (SP-initiated, HTTP-POST ACS)."""

    name = "saml"

    def __init__(
        self,
        *,
        sp_entity_id: str,
        sp_acs_url: str,
        idp_entity_id: str,
        idp_sso_url: str,
        idp_x509_cert: str,
    ) -> None:
        self._settings = _build_settings(
            sp_entity_id=sp_entity_id,
            sp_acs_url=sp_acs_url,
            idp_entity_id=idp_entity_id,
            idp_sso_url=idp_sso_url,
            idp_x509_cert=idp_x509_cert,
        )
        self._acs_url = sp_acs_url

    # ── factory ───────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SamlProvider":
        required = (
            "sp_entity_id",
            "sp_acs_url",
            "idp_entity_id",
            "idp_sso_url",
            "idp_x509_cert",
        )
        missing = [k for k in required if k not in config]
        if missing:
            raise SamlError(f"saml config missing keys: {missing}")
        return cls(
            sp_entity_id=config["sp_entity_id"],
            sp_acs_url=config["sp_acs_url"],
            idp_entity_id=config["idp_entity_id"],
            idp_sso_url=config["idp_sso_url"],
            idp_x509_cert=config["idp_x509_cert"],
        )

    # ── protocol surface ──────────────────────────────────────────────────
    async def initiate(self, *, state: str, redirect_uri: str) -> str:
        # ``redirect_uri`` overrides the configured ACS — useful when the SP
        # serves multiple environments behind one IdP config.
        settings = dict(self._settings)
        settings["sp"] = dict(settings["sp"])
        settings["sp"]["assertionConsumerService"] = dict(
            settings["sp"]["assertionConsumerService"]
        )
        settings["sp"]["assertionConsumerService"]["url"] = redirect_uri
        request_data = _request_data(acs_url=redirect_uri)
        auth = OneLogin_Saml2_Auth(request_data, old_settings=settings)
        # OneLogin's ``login`` builds the AuthnRequest and returns the redirect URL.
        return auth.login(return_to=state)

    async def complete(
        self, *, params: dict[str, Any], state: str
    ) -> UserClaims:
        saml_response = params.get("SAMLResponse")
        if not saml_response:
            raise SamlError("missing SAMLResponse in callback")
        acs_url = params.get("acs_url") or self._acs_url
        request_data = _request_data(
            acs_url=acs_url,
            saml_response=saml_response,
            relay_state=params.get("RelayState"),
        )
        auth = OneLogin_Saml2_Auth(request_data, old_settings=self._settings)
        auth.process_response()
        errors = auth.get_errors()
        if errors:
            reason = auth.get_last_error_reason() or ",".join(errors)
            raise SamlError(f"saml validation failed: {reason}")
        if not auth.is_authenticated():
            raise SamlError("saml response not authenticated")

        attrs = auth.get_attributes() or {}
        nameid = auth.get_nameid() or ""
        email = _first_attr(attrs, _EMAIL_ATTRS) or nameid
        if not email:
            raise SamlError("saml response missing email / NameID")
        name = _first_attr(attrs, _NAME_ATTRS)
        groups = _all_values(attrs, _GROUP_ATTRS)
        return UserClaims(
            subject=nameid or email,
            email=email,
            name=name,
            groups=tuple(groups),
            raw={"attributes": attrs, "nameid": nameid},
        )


def _first_attr(attrs: dict[str, list], keys: tuple[str, ...]) -> str | None:
    for k in keys:
        v = attrs.get(k)
        if v:
            return str(v[0])
    return None


def _all_values(attrs: dict[str, list], keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    for k in keys:
        v = attrs.get(k) or []
        out.extend(str(x) for x in v)
    return out


register_provider("saml", SamlProvider.from_config)
