"""Phase G1 — IdP protocol + registry + IdpConnection model."""

from __future__ import annotations

from typing import Any

import pytest

from ai_portal.auth.idp import (
    IdentityProvider,
    IdpConnection,
    IdpProviderNotFound,
    UserClaims,
    available_providers,
    get_provider,
    register_provider,
)
from ai_portal.auth.idp.registry import _clear_for_tests


@pytest.fixture(autouse=True)
def _isolate_registry():
    _clear_for_tests()
    yield
    _clear_for_tests()


# ──────────────────────────────────────────────────────────────────────────
# UserClaims dataclass
# ──────────────────────────────────────────────────────────────────────────
def test_user_claims_defaults_are_safe():
    c = UserClaims(subject="abc", email="a@b.com")
    assert c.name is None
    assert c.groups == ()
    assert c.raw == {}


def test_user_claims_is_frozen():
    c = UserClaims(subject="abc", email="a@b.com")
    with pytest.raises(Exception):
        c.subject = "other"  # type: ignore[misc]


# ──────────────────────────────────────────────────────────────────────────
# Protocol compliance (runtime_checkable)
# ──────────────────────────────────────────────────────────────────────────
class _FakeProvider:
    name = "fake"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config

    async def initiate(self, *, state: str, redirect_uri: str) -> str:
        return f"https://idp.example/auth?state={state}&redirect_uri={redirect_uri}"

    async def complete(
        self, *, params: dict[str, Any], state: str
    ) -> UserClaims:
        return UserClaims(subject=params["sub"], email=params["email"])


def test_fake_provider_satisfies_protocol():
    p = _FakeProvider({})
    assert isinstance(p, IdentityProvider)


# ──────────────────────────────────────────────────────────────────────────
# Registry — name → factory
# ──────────────────────────────────────────────────────────────────────────
def test_registry_resolves_registered_provider():
    register_provider("fake", _FakeProvider)
    inst = get_provider("fake", {"hello": "world"})
    assert isinstance(inst, _FakeProvider)
    assert inst.config == {"hello": "world"}


def test_registry_raises_on_unknown_provider():
    with pytest.raises(IdpProviderNotFound):
        get_provider("does-not-exist", {})


def test_available_providers_returns_sorted_keys():
    register_provider("zeta", _FakeProvider)
    register_provider("alpha", _FakeProvider)
    register_provider("mu", _FakeProvider)
    assert available_providers() == ("alpha", "mu", "zeta")


def test_register_provider_replaces_existing():
    register_provider("dup", _FakeProvider)

    class _Other(_FakeProvider):
        name = "other"

    register_provider("dup", _Other)
    inst = get_provider("dup", {})
    assert isinstance(inst, _Other)


# ──────────────────────────────────────────────────────────────────────────
# IdpConnection model — column shape only (no DB roundtrip).
# Migration is covered by the alembic suite.
# ──────────────────────────────────────────────────────────────────────────
def test_idp_connection_table_name():
    assert IdpConnection.__tablename__ == "idp_connections"


def test_idp_connection_columns():
    cols = {c.name for c in IdpConnection.__table__.columns}
    expected = {
        "id",
        "org_id",
        "kind",
        "domain",
        "config_encrypted",
        "enabled",
        "sso_required",
        "description",
        "created_at",
        "updated_at",
        "disabled_at",
    }
    assert expected <= cols


def test_idp_connection_unique_constraint():
    names = {
        c.name
        for c in IdpConnection.__table__.constraints
        if c.name is not None
    }
    assert "uq_idp_connections_org_kind_domain" in names
