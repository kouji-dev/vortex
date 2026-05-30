"""Name → factory registry for :class:`SocialProvider` implementations.

Providers register themselves at import time::

    from ai_portal.auth.social.registry import register_social_provider
    register_social_provider("google", GoogleSocialProvider.from_env)

Factories take no arguments and read their config from env (client id/secret),
so a provider only appears in :func:`available_social_providers` when it is both
imported and configured.
"""

from __future__ import annotations

from collections.abc import Callable

from ai_portal.auth.social.protocol import SocialProvider

SocialProviderFactory = Callable[[], SocialProvider]


class SocialProviderNotFound(Exception):
    """Raised when a provider name has no registered factory."""


class SocialProviderNotConfigured(Exception):
    """Raised when a provider is registered but missing required env config."""


_REGISTRY: dict[str, SocialProviderFactory] = {}


def register_social_provider(name: str, factory: SocialProviderFactory) -> None:
    """Register or replace the factory for a social provider."""
    _REGISTRY[name] = factory


def get_social_provider(name: str) -> SocialProvider:
    """Build a configured provider instance for ``name``.

    Raises :class:`SocialProviderNotFound` if unknown, or
    :class:`SocialProviderNotConfigured` if the factory reports missing config.
    """
    try:
        factory = _REGISTRY[name]
    except KeyError as exc:
        raise SocialProviderNotFound(name) from exc
    return factory()


def available_social_providers() -> tuple[str, ...]:
    """Return registered provider names that are also configured (have creds)."""
    out: list[str] = []
    for name, factory in sorted(_REGISTRY.items()):
        try:
            factory()
        except SocialProviderNotConfigured:
            continue
        out.append(name)
    return tuple(out)


def registered_names() -> tuple[str, ...]:
    """All registered names regardless of config (for diagnostics / tests)."""
    return tuple(sorted(_REGISTRY))


def _clear_for_tests() -> None:
    _REGISTRY.clear()
