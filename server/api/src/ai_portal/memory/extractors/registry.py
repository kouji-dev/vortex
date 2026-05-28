"""Process-local registry of memory extractors.

Bundled extractors register themselves on import; integration code calls
:func:`get` with the policy-chosen extractor name.
"""
from __future__ import annotations

from .protocol import Extractor

_REG: dict[str, Extractor] = {}


def register(e: Extractor) -> None:
    if not getattr(e, "name", None):
        raise ValueError("extractor must expose a 'name' attribute")
    _REG[e.name] = e


def get(name: str) -> Extractor:
    if name not in _REG:
        raise KeyError(f"unknown extractor: {name}")
    return _REG[name]


def list_names() -> list[str]:
    return sorted(_REG)


def clear() -> None:
    """Test helper — wipe the registry."""
    _REG.clear()
