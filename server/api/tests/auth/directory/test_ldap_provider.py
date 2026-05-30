"""LDAP/AD provider — group→role mapping, filter escaping, AD preset, secret box.

These exercise the pure logic that does not require a live directory server.
"""

from __future__ import annotations

import pytest

from ai_portal.auth.directory.protocol import DirectoryProvider
from ai_portal.auth.directory.providers.active_directory import (
    ActiveDirectoryProvider,
)
from ai_portal.auth.directory.providers.ldap import (
    DirectoryConnectionError,
    LdapProvider,
    _escape,
)
from ai_portal.auth.directory.registry import (
    available_directory_providers,
    get_directory_provider,
)
from ai_portal.auth.directory.secret_box import decrypt_secret, encrypt_secret


def _ldap(**over) -> LdapProvider:
    base = dict(
        host="ldap.acme.com",
        bind_dn="cn=svc,dc=acme,dc=com",
        bind_secret="svc-pass",
        base_dn="dc=acme,dc=com",
    )
    base.update(over)
    return LdapProvider(**base)


# ── registry / protocol ──────────────────────────────────────────────────────
def test_registry_has_ldap_and_ad():
    assert {"ldap", "active_directory"} <= set(available_directory_providers())
    inst = get_directory_provider(
        "ldap",
        {
            "host": "h",
            "bind_dn": "cn=svc",
            "bind_secret": "p",
            "base_dn": "dc=x",
        },
    )
    assert isinstance(inst, DirectoryProvider)


def test_from_config_requires_keys():
    with pytest.raises(DirectoryConnectionError):
        LdapProvider.from_config({"host": "h"})  # missing bind/base


# ── defaults + preset ─────────────────────────────────────────────────────────
def test_ldap_default_filter_and_port():
    p = _ldap()
    assert p.user_filter == "(uid={username})"
    assert p.port == 389


def test_ldaps_default_port_636():
    p = _ldap(tls_mode="ldaps")
    assert p.port == 636


def test_ad_preset_uses_samaccountname():
    p = ActiveDirectoryProvider.from_config(
        {
            "host": "ad.acme.com",
            "bind_dn": "cn=svc",
            "bind_secret": "p",
            "base_dn": "dc=acme,dc=com",
        }
    )
    assert p.user_filter == "(sAMAccountName={username})"
    assert p.attr_map["email"] == "mail"
    assert p.attr_map["name"] == "displayName"


# ── group → role ──────────────────────────────────────────────────────────────
def test_group_role_map_by_bare_name():
    p = _ldap(group_role_map={"admins": "admin", "viewers": "viewer"})
    roles = p.map_groups_to_roles(("admins", "engineers"))
    assert roles == ["admin"]


def test_group_role_map_by_dn_cn():
    p = _ldap(group_role_map={"platform-admins": "admin"})
    roles = p.map_groups_to_roles(
        ("CN=platform-admins,OU=Groups,DC=acme,DC=com",)
    )
    assert roles == ["admin"]


def test_group_role_map_empty_returns_no_roles():
    assert _ldap().map_groups_to_roles(("anything",)) == []


# ── filter escaping ───────────────────────────────────────────────────────────
def test_escape_neutralizes_filter_metachars():
    assert _escape("a*b(c)\\d") == "a\\2ab\\28c\\29\\5cd"


# ── secret box ────────────────────────────────────────────────────────────────
def test_secret_box_roundtrip_plain_marker(monkeypatch):
    monkeypatch.delenv("DIRECTORY_KEK", raising=False)
    monkeypatch.delenv("AUDIT_KEK", raising=False)
    tok = encrypt_secret("hunter2")
    assert tok.startswith("plain:")
    assert decrypt_secret(tok) == "hunter2"


def test_secret_box_roundtrip_with_kek(monkeypatch):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode("ascii")
    monkeypatch.setenv("DIRECTORY_KEK", key)
    monkeypatch.delenv("AUDIT_KEK", raising=False)
    tok = encrypt_secret("topsecret")
    assert not tok.startswith("plain:")
    assert decrypt_secret(tok) == "topsecret"
