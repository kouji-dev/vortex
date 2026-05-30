"""Provider adapter registry — kind → factory, build from credential or env.

The registry maps a provider *kind* (``"anthropic"``, ``"openai"``, plus the
OpenAI-wire-compatible backends ``"together"`` / ``"groq"`` / ``"fireworks"``
/ ``"vllm"``) to a factory that constructs a canonical
:class:`~ai_portal.catalog.providers.protocol.LLMProvider` adapter.

Two build entry points:

- :func:`build_from_secret` — given a decrypted API key (typically pulled from
  a per-org :class:`ProviderCredential` via
  :meth:`ProviderCredentialService.get_decrypted`).
- :func:`build_from_settings` — env-config fallback (``OPENAI_API_KEY`` /
  ``ANTHROPIC_API_KEY``) used by internal callers / dev when no per-org
  credential row exists.

The provider *set* is declared here (deployment config), not in the UI. The UI
only enables/disables per-org credentials — it never adds new provider kinds.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

from ai_portal.gateway.providers.anthropic import AnthropicProvider
from ai_portal.gateway.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class ProviderFactory(Protocol):
    def __call__(self, *, api_key: str, base_url: str | None = None) -> Any: ...


# OpenAI-wire-compatible backends → default base URLs. Same adapter, different
# host. (Anthropic is wire-unique, registered separately below.)
_OPENAI_COMPATIBLE_BASES: dict[str, str] = {
    "openai": "https://api.openai.com/v1",
    "together": "https://api.together.xyz/v1",
    "groq": "https://api.groq.com/openai/v1",
    "fireworks": "https://api.fireworks.ai/inference/v1",
    "mistral": "https://api.mistral.ai/v1",
}


def _openai_factory(kind: str) -> ProviderFactory:
    base_default = _OPENAI_COMPATIBLE_BASES[kind]

    def _factory(*, api_key: str, base_url: str | None = None) -> OpenAIProvider:
        return OpenAIProvider(
            api_key=api_key,
            base_url=base_url or base_default,
            name=kind,
        )

    return _factory


def _anthropic_factory(*, api_key: str, base_url: str | None = None) -> AnthropicProvider:
    kwargs: dict[str, Any] = {"api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return AnthropicProvider(**kwargs)


# kind → factory. This is the deployment-config provider SET.
_REGISTRY: dict[str, ProviderFactory] = {
    "anthropic": _anthropic_factory,
    **{kind: _openai_factory(kind) for kind in _OPENAI_COMPATIBLE_BASES},
}


class ProviderNotRegistered(KeyError):
    """Raised when a provider kind has no adapter factory."""


def supported_provider_kinds() -> list[str]:
    """Provider kinds with a real adapter available (deployment config)."""
    return sorted(_REGISTRY)


def register_provider(kind: str, factory: ProviderFactory) -> None:
    """Register or override an adapter factory for ``kind``."""
    _REGISTRY[kind] = factory


def build_from_secret(
    *, provider: str, api_key: str, base_url: str | None = None
) -> Any:
    """Construct an adapter for ``provider`` from a decrypted secret.

    Raises :class:`ProviderNotRegistered` for unknown kinds and ``ValueError``
    when the key is empty (adapters reject empty keys).
    """
    factory = _REGISTRY.get(provider)
    if factory is None:
        raise ProviderNotRegistered(
            f"no adapter registered for provider {provider!r} — "
            f"supported: {supported_provider_kinds()}"
        )
    return factory(api_key=api_key, base_url=base_url)


def build_from_settings(*, provider: str, settings: Any) -> Any:
    """Env-config fallback — build an adapter from ``Settings`` API keys.

    Reads ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY`` (and ``OPENAI_API_BASE``)
    off the settings object. Raises ``ValueError`` when the relevant key is
    unset so the caller can surface a clear "no credential" error.
    """
    if provider == "anthropic":
        key = (getattr(settings, "anthropic_api_key", "") or "").strip()
        return build_from_secret(provider="anthropic", api_key=key)
    if provider == "openai":
        key = (getattr(settings, "openai_api_key", "") or "").strip()
        base = (getattr(settings, "openai_api_base", "") or "").strip() or None
        return build_from_secret(provider="openai", api_key=key, base_url=base)
    raise ProviderNotRegistered(
        f"no env-config fallback for provider {provider!r}"
    )


__all__ = [
    "ProviderNotRegistered",
    "build_from_secret",
    "build_from_settings",
    "register_provider",
    "supported_provider_kinds",
]
