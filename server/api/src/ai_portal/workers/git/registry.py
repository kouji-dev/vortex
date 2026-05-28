"""Git provider registry — name → provider lookup."""

from __future__ import annotations

from ai_portal.workers.git.protocol import GitProvider


class GitProviderNotRegistered(KeyError):
    """Raised when ``get(name)`` finds no provider."""


_REG: dict[str, GitProvider] = {}


def register(provider: GitProvider) -> None:
    """Register a provider under ``provider.name``."""
    _REG[provider.name] = provider


def get(name: str) -> GitProvider:
    """Lookup a provider by name."""
    try:
        return _REG[name]
    except KeyError as e:
        raise GitProviderNotRegistered(name) from e


def all_providers() -> list[str]:
    """Return all registered provider names."""
    return list(_REG.keys())


def clear() -> None:
    """Test helper — empty the registry."""
    _REG.clear()
