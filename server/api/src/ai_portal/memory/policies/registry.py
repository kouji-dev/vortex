"""Process-local registry of memory policies."""
from __future__ import annotations

from .protocol import MemoryPolicy

_REG: dict[str, MemoryPolicy] = {}


def register(p: MemoryPolicy) -> None:
    if not getattr(p, "name", None):
        raise ValueError("policy must expose a 'name' attribute")
    _REG[p.name] = p


def get(name: str) -> MemoryPolicy:
    if name not in _REG:
        raise KeyError(f"unknown policy: {name}")
    return _REG[name]


def list_names() -> list[str]:
    return sorted(_REG)


def clear() -> None:
    _REG.clear()
