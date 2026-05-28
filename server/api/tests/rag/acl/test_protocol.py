"""ACL provider protocol + registry contract tests.

Covers:
- ``ResolvedAcl`` defaults + ``is_empty()``.
- ``AclProvider`` runtime_checkable acceptance.
- ``register`` / ``get`` round trip.
- ``register`` rejects missing ``connector_kind``.
- ``register`` rejects duplicate kind.
- ``get`` falls back to ``default`` when kind unknown.
- ``get`` raises ``UnknownAclProvider`` when neither specific nor default
  is registered.
"""

from __future__ import annotations

import pytest

from ai_portal.rag.acl import (
    AclProvider,
    DuplicateAclProvider,
    ResolvedAcl,
    UnknownAclProvider,
    get_provider,
    register_provider,
)
from ai_portal.rag.acl.registry import _reset_for_tests
from ai_portal.rag.connectors.protocol import AclSet


@pytest.fixture(autouse=True)
def _isolated_registry():
    _reset_for_tests()
    yield
    _reset_for_tests()


class _FakeProvider:
    connector_kind = "fake"

    async def map(self, source_acls: AclSet, org_id: str) -> ResolvedAcl:
        return ResolvedAcl(public=source_acls.public)


class _DefaultProvider:
    connector_kind = "default"

    async def map(self, source_acls: AclSet, org_id: str) -> ResolvedAcl:
        return ResolvedAcl()


def test_resolved_acl_defaults():
    a = ResolvedAcl()
    assert a.user_ids == set()
    assert a.group_ids == set()
    assert a.public is False
    assert a.unresolved == set()
    assert a.is_empty() is True


def test_resolved_acl_is_empty_false_when_user_present():
    assert ResolvedAcl(user_ids={"u1"}).is_empty() is False


def test_resolved_acl_is_empty_false_when_public():
    assert ResolvedAcl(public=True).is_empty() is False


def test_fake_satisfies_provider_protocol():
    assert isinstance(_FakeProvider(), AclProvider)


def test_register_then_get_round_trip():
    p = _FakeProvider()
    register_provider(p)
    assert get_provider("fake") is p


def test_register_rejects_missing_kind():
    class _NoKind:
        async def map(self, source_acls, org_id):
            return ResolvedAcl()

    with pytest.raises(Exception):
        register_provider(_NoKind())


def test_register_rejects_empty_kind():
    class _EmptyKind:
        connector_kind = ""

        async def map(self, source_acls, org_id):
            return ResolvedAcl()

    with pytest.raises(Exception):
        register_provider(_EmptyKind())


def test_register_rejects_duplicate():
    register_provider(_FakeProvider())
    with pytest.raises(DuplicateAclProvider):
        register_provider(_FakeProvider())


def test_get_falls_back_to_default():
    d = _DefaultProvider()
    register_provider(d)
    assert get_provider("missing-kind") is d


def test_get_unknown_with_no_default_raises():
    with pytest.raises(UnknownAclProvider):
        get_provider("nope")
