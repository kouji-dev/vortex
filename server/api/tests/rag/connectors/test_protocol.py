"""Connector framework contract tests.

Covers:
- manifest validation (name + auth_kinds required)
- registry register / get / duplicate / unknown
- Connector runtime_checkable protocol acceptance
- SourceDoc / FetchedDoc / AclSet shapes
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from ai_portal.rag.connectors import (
    AclSet,
    Connector,
    ConnectorManifest,
    DuplicateConnector,
    FetchedDoc,
    SourceDoc,
    UnknownConnector,
    get,
    register,
    registered_names,
)
from ai_portal.rag.connectors.registry import _reset_for_tests


# ---------------------------------------------------------------- fixtures --

@pytest.fixture(autouse=True)
def _isolated_registry():
    _reset_for_tests()
    yield
    _reset_for_tests()


class _FakeConn:
    manifest = ConnectorManifest(
        name="fake",
        auth_kinds=("none",),
        schedulable=True,
        supports_delta=False,
        supports_acl=False,
        supports_webhook=False,
        config_schema={"type": "object"},
    )
    _cursor: str | None = None

    @classmethod
    async def setup(cls, config: dict[str, Any], secret_store: Any) -> "_FakeConn":
        return cls()

    async def discover(self, cursor: str | None) -> AsyncIterator[SourceDoc]:
        if False:  # pragma: no cover - shape only
            yield  # type: ignore[unreachable]

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        return FetchedDoc(data=b"", mime="text/plain")

    async def acls(self, sd: SourceDoc) -> AclSet:
        return AclSet(public=True)

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


# ---------------------------------------------------------------- manifest --

def test_manifest_requires_name():
    with pytest.raises(ValueError):
        ConnectorManifest(
            name="",
            auth_kinds=("none",),
            schedulable=False,
            supports_delta=False,
            supports_acl=False,
            supports_webhook=False,
        )


def test_manifest_requires_auth_kinds():
    with pytest.raises(ValueError):
        ConnectorManifest(
            name="x",
            auth_kinds=(),
            schedulable=False,
            supports_delta=False,
            supports_acl=False,
            supports_webhook=False,
        )


# ---------------------------------------------------------------- registry --

def test_register_then_get_round_trip():
    register(_FakeConn)
    assert get("fake") is _FakeConn
    assert registered_names() == ("fake",)


def test_register_rejects_missing_manifest():
    class _NoManifest:
        pass

    with pytest.raises(Exception):
        register(_NoManifest)


def test_register_rejects_duplicate():
    register(_FakeConn)
    with pytest.raises(DuplicateConnector):
        register(_FakeConn)


def test_get_unknown_raises():
    with pytest.raises(UnknownConnector):
        get("does-not-exist")


# ---------------------------------------------------------------- protocol --

def test_fake_satisfies_connector_protocol():
    assert isinstance(_FakeConn(), Connector)


def test_source_doc_defaults():
    sd = SourceDoc(
        source_uri="http://x", title="t", mime="text/html",
        size=None, modified_at=None,
    )
    assert sd.cursor_token is None
    assert sd.raw == {}


def test_aclset_defaults_to_empty_non_public():
    a = AclSet()
    assert a.user_ids == set()
    assert a.group_ids == set()
    assert a.public is False
