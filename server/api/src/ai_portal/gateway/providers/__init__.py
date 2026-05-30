"""Real provider adapters for the gateway — anthropic + openai over httpx.

These are the runtime path. The :class:`~ai_portal.gateway.fake_provider.FakeProvider`
is test-only (behind ``GATEWAY_USE_FAKE_PROVIDER``).

Adapters implement the canonical
:class:`~ai_portal.catalog.providers.protocol.LLMProvider` protocol so the
gateway facade + compat surfaces stay vendor-neutral. The :mod:`registry`
maps a provider *kind* to a factory and builds an adapter from a per-org
:class:`~ai_portal.gateway.provider_credentials.model.ProviderCredential`
secret (or an env-config fallback).
"""

from __future__ import annotations

from ai_portal.gateway.providers.anthropic import AnthropicProvider
from ai_portal.gateway.providers.openai import OpenAIProvider
from ai_portal.gateway.providers.registry import (
    ProviderNotRegistered,
    build_from_secret,
    build_from_settings,
    register_provider,
    supported_provider_kinds,
)

__all__ = [
    "AnthropicProvider",
    "OpenAIProvider",
    "ProviderNotRegistered",
    "build_from_secret",
    "build_from_settings",
    "register_provider",
    "supported_provider_kinds",
]
