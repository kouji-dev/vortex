"""Tests for guardrail policy resolution in gateway.service.

Resolution precedence (highest → lowest):

1. API-key scope (key.guardrail_policy_id)
2. Route default (per ``route`` string, e.g. ``v1/chat/completions``)
3. Org default

Resolution is cached per :class:`PolicyResolutionRequest` for the request's
lifetime so guardrail bundles fetched once are reused across input + output
checks within the same call.
"""

from __future__ import annotations

import uuid

import pytest

from ai_portal.gateway.service import (
    PolicyResolutionRequest,
    PolicyResolver,
    PolicySource,
)


# ── fakes ───────────────────────────────────────────────────────────────────


class FakePolicyStore:
    """In-memory policy store fake."""

    def __init__(self) -> None:
        self.keys: dict[uuid.UUID, uuid.UUID | None] = {}
        self.route_defaults: dict[tuple[uuid.UUID, str], uuid.UUID] = {}
        self.org_defaults: dict[uuid.UUID, uuid.UUID] = {}
        self.policies: dict[uuid.UUID, dict] = {}
        self.calls: list[str] = []

    def get_key_policy(
        self, *, org_id: uuid.UUID, key_id: uuid.UUID
    ) -> uuid.UUID | None:
        self.calls.append("get_key_policy")
        return self.keys.get(key_id)

    def get_route_default(
        self, *, org_id: uuid.UUID, route: str
    ) -> uuid.UUID | None:
        self.calls.append("get_route_default")
        return self.route_defaults.get((org_id, route))

    def get_org_default(self, *, org_id: uuid.UUID) -> uuid.UUID | None:
        self.calls.append("get_org_default")
        return self.org_defaults.get(org_id)

    def load_policy(self, policy_id: uuid.UUID) -> dict | None:
        self.calls.append("load_policy")
        return self.policies.get(policy_id)


# ── fixtures ────────────────────────────────────────────────────────────────


def _make_req(
    *,
    org_id: uuid.UUID,
    key_id: uuid.UUID | None = None,
    route: str = "v1/chat/completions",
) -> PolicyResolutionRequest:
    return PolicyResolutionRequest(org_id=org_id, key_id=key_id, route=route)


# ── tests ───────────────────────────────────────────────────────────────────


def test_resolves_from_key_scope_when_present() -> None:
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    key_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    store.keys[key_id] = policy_id
    store.policies[policy_id] = {"name": "key-policy", "bundle": []}
    store.org_defaults[org_id] = uuid.uuid4()  # would be overridden

    resolver = PolicyResolver(store)
    result = resolver.resolve(_make_req(org_id=org_id, key_id=key_id))

    assert result is not None
    assert result.policy_id == policy_id
    assert result.source == PolicySource.KEY
    assert result.policy["name"] == "key-policy"


def test_falls_back_to_route_default_when_key_has_none() -> None:
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    key_id = uuid.uuid4()
    route_pid = uuid.uuid4()
    org_pid = uuid.uuid4()
    store.keys[key_id] = None  # key explicitly has no override
    store.route_defaults[(org_id, "v1/chat/completions")] = route_pid
    store.org_defaults[org_id] = org_pid
    store.policies[route_pid] = {"name": "route", "bundle": []}
    store.policies[org_pid] = {"name": "org", "bundle": []}

    resolver = PolicyResolver(store)
    result = resolver.resolve(_make_req(org_id=org_id, key_id=key_id))

    assert result is not None
    assert result.policy_id == route_pid
    assert result.source == PolicySource.ROUTE


def test_falls_back_to_org_default_when_neither_key_nor_route() -> None:
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    org_pid = uuid.uuid4()
    store.org_defaults[org_id] = org_pid
    store.policies[org_pid] = {"name": "org", "bundle": []}

    resolver = PolicyResolver(store)
    result = resolver.resolve(_make_req(org_id=org_id, key_id=None))

    assert result is not None
    assert result.policy_id == org_pid
    assert result.source == PolicySource.ORG


def test_returns_none_when_no_policy_at_any_layer() -> None:
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    resolver = PolicyResolver(store)
    result = resolver.resolve(_make_req(org_id=org_id))
    assert result is None


def test_resolution_is_cached_per_request() -> None:
    """Two .resolve() calls with the same key tuple → one set of store hits."""
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    key_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    store.keys[key_id] = policy_id
    store.policies[policy_id] = {"name": "p", "bundle": []}

    resolver = PolicyResolver(store)
    req = _make_req(org_id=org_id, key_id=key_id)
    r1 = resolver.resolve(req)
    calls_after_first = len(store.calls)
    r2 = resolver.resolve(req)

    assert r1 is r2  # same cached object
    assert len(store.calls) == calls_after_first  # no extra store hits


def test_resolution_cache_keyed_on_route() -> None:
    """Different route on same org → independent cache entries."""
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    p_chat = uuid.uuid4()
    p_embed = uuid.uuid4()
    store.route_defaults[(org_id, "v1/chat/completions")] = p_chat
    store.route_defaults[(org_id, "v1/embeddings")] = p_embed
    store.policies[p_chat] = {"name": "chat"}
    store.policies[p_embed] = {"name": "embed"}

    resolver = PolicyResolver(store)
    r1 = resolver.resolve(_make_req(org_id=org_id, route="v1/chat/completions"))
    r2 = resolver.resolve(_make_req(org_id=org_id, route="v1/embeddings"))

    assert r1 is not None and r2 is not None
    assert r1.policy_id == p_chat
    assert r2.policy_id == p_embed


def test_key_lookup_short_circuits_lower_layers() -> None:
    """Key policy found → route + org never queried."""
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    key_id = uuid.uuid4()
    policy_id = uuid.uuid4()
    store.keys[key_id] = policy_id
    store.policies[policy_id] = {"name": "k"}

    resolver = PolicyResolver(store)
    resolver.resolve(_make_req(org_id=org_id, key_id=key_id))

    assert "get_key_policy" in store.calls
    assert "get_route_default" not in store.calls
    assert "get_org_default" not in store.calls


def test_route_lookup_short_circuits_org() -> None:
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    p_route = uuid.uuid4()
    store.route_defaults[(org_id, "v1/chat/completions")] = p_route
    store.policies[p_route] = {"name": "r"}

    resolver = PolicyResolver(store)
    resolver.resolve(_make_req(org_id=org_id))

    assert "get_route_default" in store.calls
    assert "get_org_default" not in store.calls


def test_handles_dangling_policy_id_gracefully() -> None:
    """Store returns a policy_id that no longer loads — fall through."""
    store = FakePolicyStore()
    org_id = uuid.uuid4()
    key_id = uuid.uuid4()
    dangling = uuid.uuid4()
    org_pid = uuid.uuid4()
    store.keys[key_id] = dangling  # no entry in store.policies
    store.org_defaults[org_id] = org_pid
    store.policies[org_pid] = {"name": "org"}

    resolver = PolicyResolver(store)
    result = resolver.resolve(_make_req(org_id=org_id, key_id=key_id))

    assert result is not None
    assert result.policy_id == org_pid
    assert result.source == PolicySource.ORG
