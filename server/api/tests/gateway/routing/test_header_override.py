"""C3: header parsing for ``x-gateway-routing-policy``.

Pure-Python — no DB.
"""

from __future__ import annotations

from ai_portal.gateway.routing.service import (
    ROUTING_POLICY_HEADER,
    extract_policy_override,
)


def test_header_constant_is_canonical_lowercase():
    assert ROUTING_POLICY_HEADER == "x-gateway-routing-policy"


def test_returns_none_for_empty_headers():
    assert extract_policy_override(None) is None
    assert extract_policy_override({}) is None


def test_returns_value_case_insensitive():
    assert extract_policy_override({"x-gateway-routing-policy": "cheap"}) == "cheap"
    assert extract_policy_override({"X-Gateway-Routing-Policy": "cheap"}) == "cheap"
    assert extract_policy_override({"X-GATEWAY-ROUTING-POLICY": "cheap"}) == "cheap"


def test_strips_whitespace():
    assert extract_policy_override({ROUTING_POLICY_HEADER: "  cheap  "}) == "cheap"


def test_empty_value_returns_none():
    assert extract_policy_override({ROUTING_POLICY_HEADER: ""}) is None
    assert extract_policy_override({ROUTING_POLICY_HEADER: "   "}) is None


def test_other_headers_ignored():
    assert extract_policy_override({"x-other": "policy-name", "x-foo": "bar"}) is None
