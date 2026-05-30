"""Provider registry + resolver tests (no network).

- registry maps kind → adapter, drives compatible backends off base_url
- build_from_settings reads env-config keys off a Settings-like object
- ProviderResolver: infers kind from model, prefers per-org secret, falls back
  to env, caches by (org, kind, fingerprint), and rotates on key change
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from ai_portal.gateway.providers.anthropic import AnthropicProvider
from ai_portal.gateway.providers.openai import OpenAIProvider
from ai_portal.gateway.providers.registry import (
    ProviderNotRegistered,
    build_from_secret,
    build_from_settings,
    supported_provider_kinds,
)
from ai_portal.gateway.providers.resolution import (
    NoProviderCredential,
    ProviderResolver,
    infer_provider_kind,
)


def test_supported_kinds_includes_core_and_compatible():
    kinds = supported_provider_kinds()
    assert "anthropic" in kinds
    assert "openai" in kinds
    assert {"groq", "together", "fireworks", "mistral"} <= set(kinds)


def test_build_from_secret_anthropic_and_openai():
    a = build_from_secret(provider="anthropic", api_key="sk-ant")
    o = build_from_secret(provider="openai", api_key="sk-oai")
    assert isinstance(a, AnthropicProvider)
    assert isinstance(o, OpenAIProvider)


def test_build_from_secret_compatible_backend_uses_default_base():
    g = build_from_secret(provider="groq", api_key="gsk")
    assert isinstance(g, OpenAIProvider)
    assert g.name == "groq"
    assert g._base_url == "https://api.groq.com/openai/v1"


def test_build_from_secret_unknown_kind_raises():
    with pytest.raises(ProviderNotRegistered):
        build_from_secret(provider="nope", api_key="x")


def test_build_from_settings_reads_env_keys():
    st = SimpleNamespace(
        anthropic_api_key="sk-ant-env",
        openai_api_key="sk-oai-env",
        openai_api_base="https://proxy.local/v1",
    )
    a = build_from_settings(provider="anthropic", settings=st)
    o = build_from_settings(provider="openai", settings=st)
    assert isinstance(a, AnthropicProvider)
    assert isinstance(o, OpenAIProvider)
    assert o._base_url == "https://proxy.local/v1"


def test_build_from_settings_missing_key_raises():
    st = SimpleNamespace(anthropic_api_key="", openai_api_key="", openai_api_base="")
    with pytest.raises(ValueError):
        build_from_settings(provider="openai", settings=st)


@pytest.mark.parametrize(
    "model,kind",
    [
        ("claude-opus-4-8", "anthropic"),
        ("anthropic-claude-haiku-4-5", "anthropic"),
        ("gpt-5.5", "openai"),
        ("o3-mini", "openai"),
        ("openai:gpt-4o", "openai"),
        ("groq:llama-3.1", "groq"),
    ],
)
def test_infer_provider_kind(model, kind):
    assert infer_provider_kind(model) == kind


def test_infer_provider_kind_unknown_raises():
    with pytest.raises(KeyError):
        infer_provider_kind("totally-unknown-model")


def test_resolver_prefers_org_secret_over_env():
    org = uuid.uuid4()
    st = SimpleNamespace(anthropic_api_key="env-key", openai_api_key="", openai_api_base="")
    secrets = {(str(org), "anthropic"): "org-secret"}
    r = ProviderResolver(
        settings=st,
        load_org_secret=lambda o, p: secrets.get((str(o), p)),
    )
    adapter = r.resolve(org_id=org, model="claude-opus-4-8")
    assert isinstance(adapter, AnthropicProvider)
    assert adapter._api_key == "org-secret"


def test_resolver_falls_back_to_env_when_no_org_secret():
    org = uuid.uuid4()
    st = SimpleNamespace(anthropic_api_key="env-ant", openai_api_key="", openai_api_base="")
    r = ProviderResolver(settings=st, load_org_secret=lambda o, p: None)
    adapter = r.resolve(org_id=org, model="claude-opus-4-8")
    assert adapter._api_key == "env-ant"


def test_resolver_no_credential_raises():
    org = uuid.uuid4()
    st = SimpleNamespace(anthropic_api_key="", openai_api_key="", openai_api_base="")
    r = ProviderResolver(settings=st, load_org_secret=lambda o, p: None)
    with pytest.raises(NoProviderCredential):
        r.resolve(org_id=org, model="claude-opus-4-8")


def test_resolver_caches_adapter_per_fingerprint():
    org = uuid.uuid4()
    st = SimpleNamespace(anthropic_api_key="", openai_api_key="", openai_api_base="")
    calls = {"n": 0}

    def _load(o, p):
        calls["n"] += 1
        return "stable-secret"

    r = ProviderResolver(settings=st, load_org_secret=_load)
    a1 = r.resolve(org_id=org, model="claude-opus-4-8")
    a2 = r.resolve(org_id=org, model="claude-sonnet-4-6")
    assert a1 is a2  # same fingerprint → cached instance


def test_resolver_rotates_on_secret_change():
    org = uuid.uuid4()
    st = SimpleNamespace(anthropic_api_key="", openai_api_key="", openai_api_base="")
    secret = {"v": "old"}
    r = ProviderResolver(settings=st, load_org_secret=lambda o, p: secret["v"])
    a1 = r.resolve(org_id=org, model="claude-opus-4-8")
    secret["v"] = "new"
    a2 = r.resolve(org_id=org, model="claude-opus-4-8")
    assert a1 is not a2
    assert a2._api_key == "new"
