"""Phase G3 — SAML provider (python3-saml).

The test builds a self-signed cert, crafts a SAML Response, signs the
Assertion with that cert, base64-encodes it and feeds it to
:meth:`SamlProvider.complete`. The provider's underlying ``python3-saml``
toolkit verifies the signature against the configured x509 cert before any
claims are exposed — proving the signed-assertion path end-to-end.
"""

from __future__ import annotations

import base64
import textwrap
import uuid
from datetime import datetime, timedelta, timezone

import lxml.etree as ET
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from onelogin.saml2.utils import OneLogin_Saml2_Utils

from ai_portal.auth.idp.protocol import IdentityProvider
from ai_portal.auth.idp.providers.saml import SamlError, SamlProvider
from ai_portal.auth.idp.registry import get_provider


SP_ENTITY = "https://app.example.com/sp"
SP_ACS = "https://app.example.com/v1/auth/sso/callback"
IDP_ENTITY = "https://idp.example.com/saml"
IDP_SSO = "https://idp.example.com/saml/sso"


# ──────────────────────────────────────────────────────────────────────────
# fixtures — self-signed cert/key + signed SAML response
# ──────────────────────────────────────────────────────────────────────────
def _gen_cert() -> tuple[str, str]:
    """Return (pem_cert, pem_key) for a fresh self-signed RSA cert."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "idp-test")]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc) - timedelta(minutes=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    pem_cert = cert.public_bytes(serialization.Encoding.PEM).decode()
    pem_key = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return pem_cert, pem_key


def _saml_response_xml(
    *,
    email: str,
    name: str,
    groups: tuple[str, ...] = (),
    in_response_to: str = "REQ_TEST_1",
) -> tuple[str, str]:
    """Build (response_id, response_xml) for a SAML Response with one Assertion."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    not_after = (
        datetime.now(timezone.utc) + timedelta(minutes=5)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    response_id = f"_R{uuid.uuid4().hex}"
    assertion_id = f"_A{uuid.uuid4().hex}"

    group_xml = "".join(
        f"<saml:AttributeValue>{g}</saml:AttributeValue>" for g in groups
    )
    attrs_xml = f"""
        <saml:AttributeStatement>
          <saml:Attribute Name="email">
            <saml:AttributeValue>{email}</saml:AttributeValue>
          </saml:Attribute>
          <saml:Attribute Name="displayName">
            <saml:AttributeValue>{name}</saml:AttributeValue>
          </saml:Attribute>
          <saml:Attribute Name="groups">
            {group_xml}
          </saml:Attribute>
        </saml:AttributeStatement>
    """ if groups else f"""
        <saml:AttributeStatement>
          <saml:Attribute Name="email">
            <saml:AttributeValue>{email}</saml:AttributeValue>
          </saml:Attribute>
          <saml:Attribute Name="displayName">
            <saml:AttributeValue>{name}</saml:AttributeValue>
          </saml:Attribute>
        </saml:AttributeStatement>
    """

    xml = f"""<samlp:Response
  xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol"
  xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion"
  ID="{response_id}" Version="2.0" IssueInstant="{now}"
  Destination="{SP_ACS}" InResponseTo="{in_response_to}">
  <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
  <samlp:Status>
    <samlp:StatusCode Value="urn:oasis:names:tc:SAML:2.0:status:Success"/>
  </samlp:Status>
  <saml:Assertion ID="{assertion_id}" Version="2.0" IssueInstant="{now}">
    <saml:Issuer>{IDP_ENTITY}</saml:Issuer>
    <saml:Subject>
      <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">{email}</saml:NameID>
      <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
        <saml:SubjectConfirmationData NotOnOrAfter="{not_after}"
          Recipient="{SP_ACS}" InResponseTo="{in_response_to}"/>
      </saml:SubjectConfirmation>
    </saml:Subject>
    <saml:Conditions NotBefore="{now}" NotOnOrAfter="{not_after}">
      <saml:AudienceRestriction>
        <saml:Audience>{SP_ENTITY}</saml:Audience>
      </saml:AudienceRestriction>
    </saml:Conditions>
    <saml:AuthnStatement AuthnInstant="{now}" SessionIndex="_session_1">
      <saml:AuthnContext>
        <saml:AuthnContextClassRef>urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport</saml:AuthnContextClassRef>
      </saml:AuthnContext>
    </saml:AuthnStatement>
    {attrs_xml}
  </saml:Assertion>
</samlp:Response>"""
    return response_id, textwrap.dedent(xml).strip()


_SAML_NS = "urn:oasis:names:tc:SAML:2.0:assertion"
_SAMLP_NS = "urn:oasis:names:tc:SAML:2.0:protocol"


def _sign_assertion(xml: str, cert: str, key: str) -> str:
    """Sign just the inner ``<saml:Assertion>`` using python3-saml's helper.

    OneLogin's ``add_sign`` signs the parent of the first ``saml:Issuer`` it
    finds. We isolate the Assertion subtree, sign it standalone, then splice
    the signed Assertion back into the Response.
    """
    root = ET.fromstring(xml.encode())
    assertion = root.find(f"{{{_SAML_NS}}}Assertion")
    assert assertion is not None, "Response missing Assertion"

    # Serialize Assertion as a standalone document so add_sign signs IT.
    assertion_xml = ET.tostring(assertion, encoding="unicode")
    signed = OneLogin_Saml2_Utils.add_sign(
        assertion_xml,
        key.encode(),
        cert.encode(),
    )
    signed_assertion = ET.fromstring(
        signed if isinstance(signed, bytes) else signed.encode()
    )

    # Replace original Assertion with the signed one.
    root.replace(assertion, signed_assertion)
    return ET.tostring(root, encoding="unicode")


def _build_signed_response_b64(
    *,
    cert: str,
    key: str,
    email: str = "alice@acme.com",
    name: str = "Alice",
    groups: tuple[str, ...] = ("eng", "admins"),
) -> str:
    _, xml = _saml_response_xml(email=email, name=name, groups=groups)
    signed = _sign_assertion(xml, cert, key)
    return base64.b64encode(signed.encode()).decode()


def _make_provider(cert: str) -> SamlProvider:
    return SamlProvider(
        sp_entity_id=SP_ENTITY,
        sp_acs_url=SP_ACS,
        idp_entity_id=IDP_ENTITY,
        idp_sso_url=IDP_SSO,
        idp_x509_cert=cert,
    )


# ──────────────────────────────────────────────────────────────────────────
# Construction / factory
# ──────────────────────────────────────────────────────────────────────────
def test_from_config_requires_keys():
    with pytest.raises(SamlError):
        SamlProvider.from_config({"sp_entity_id": SP_ENTITY})


def test_from_config_builds_instance():
    cert, _ = _gen_cert()
    p = SamlProvider.from_config(
        {
            "sp_entity_id": SP_ENTITY,
            "sp_acs_url": SP_ACS,
            "idp_entity_id": IDP_ENTITY,
            "idp_sso_url": IDP_SSO,
            "idp_x509_cert": cert,
        }
    )
    assert isinstance(p, SamlProvider)


def test_registry_resolves_saml_kind():
    # Re-register (idempotent) — another test file may have cleared the registry.
    from ai_portal.auth.idp.registry import register_provider as _reg

    _reg("saml", SamlProvider.from_config)
    cert, _ = _gen_cert()
    inst = get_provider(
        "saml",
        {
            "sp_entity_id": SP_ENTITY,
            "sp_acs_url": SP_ACS,
            "idp_entity_id": IDP_ENTITY,
            "idp_sso_url": IDP_SSO,
            "idp_x509_cert": cert,
        },
    )
    assert isinstance(inst, SamlProvider)


def test_saml_provider_satisfies_protocol():
    cert, _ = _gen_cert()
    assert isinstance(_make_provider(cert), IdentityProvider)


# ──────────────────────────────────────────────────────────────────────────
# initiate — AuthnRequest redirect URL
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_initiate_returns_idp_sso_redirect():
    cert, _ = _gen_cert()
    p = _make_provider(cert)
    url = await p.initiate(state="rs-1", redirect_uri=SP_ACS)
    assert url.startswith(IDP_SSO + "?")
    assert "SAMLRequest=" in url
    assert "RelayState=rs-1" in url


# ──────────────────────────────────────────────────────────────────────────
# complete — verify signed assertion + extract claims
# ──────────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_complete_verifies_signed_assertion_and_extracts_claims():
    cert, key = _gen_cert()
    p = _make_provider(cert)
    b64 = _build_signed_response_b64(cert=cert, key=key)
    claims = await p.complete(
        params={"SAMLResponse": b64, "RelayState": "rs-1"}, state="rs-1"
    )
    assert claims.email == "alice@acme.com"
    assert claims.subject == "alice@acme.com"
    assert claims.name == "Alice"
    assert claims.groups == ("eng", "admins")


@pytest.mark.asyncio
async def test_complete_rejects_missing_response():
    cert, _ = _gen_cert()
    p = _make_provider(cert)
    with pytest.raises(SamlError, match="missing SAMLResponse"):
        await p.complete(params={}, state="rs-1")


@pytest.mark.asyncio
async def test_complete_rejects_tampered_assertion():
    cert, key = _gen_cert()
    p = _make_provider(cert)
    b64 = _build_signed_response_b64(cert=cert, key=key)
    raw = base64.b64decode(b64).decode()
    # Flip the email value AFTER signing — signature must no longer match.
    tampered = raw.replace("alice@acme.com", "mallory@evil.com")
    bad_b64 = base64.b64encode(tampered.encode()).decode()
    with pytest.raises(SamlError, match="saml validation failed"):
        await p.complete(
            params={"SAMLResponse": bad_b64, "RelayState": "rs-1"}, state="rs-1"
        )


@pytest.mark.asyncio
async def test_complete_rejects_response_signed_by_other_cert():
    cert_idp, _ = _gen_cert()
    _, attacker_key = _gen_cert()
    # Provider was configured with cert_idp, attacker signs with their own key.
    p = _make_provider(cert_idp)
    # Pass a placeholder cert so add_sign can build a KeyInfo block — but the
    # outer x509cert verified by python3-saml is cert_idp, so signature check
    # must fail.
    attacker_cert, _ = _gen_cert()
    b64 = _build_signed_response_b64(cert=attacker_cert, key=attacker_key)
    with pytest.raises(SamlError, match="saml validation failed"):
        await p.complete(
            params={"SAMLResponse": b64, "RelayState": "rs-1"}, state="rs-1"
        )
