"""Sandbox provider registry — name → provider lookup."""

from __future__ import annotations

from ai_portal.workers.sandboxes.protocol import SandboxProvider


class SandboxNotRegistered(KeyError):
    """Raised when ``get(name)`` finds no provider."""


_REG: dict[str, SandboxProvider] = {}


def register(provider: SandboxProvider) -> None:
    """Register a provider under ``provider.name``."""
    _REG[provider.name] = provider


def get(name: str) -> SandboxProvider:
    """Lookup a provider by name. Raises :class:`SandboxNotRegistered`."""
    try:
        return _REG[name]
    except KeyError as e:
        raise SandboxNotRegistered(name) from e


def all_providers() -> list[str]:
    """Return all registered provider names."""
    return list(_REG.keys())


def clear() -> None:
    """Test helper — empty the registry."""
    _REG.clear()
