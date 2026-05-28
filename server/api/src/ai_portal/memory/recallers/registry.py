"""Process-local registry of memory recallers."""
from __future__ import annotations

from .protocol import Recaller

_REG: dict[str, Recaller] = {}


def register(r: Recaller) -> None:
    if not getattr(r, "name", None):
        raise ValueError("recaller must expose a 'name' attribute")
    _REG[r.name] = r


def get(name: str) -> Recaller:
    if name not in _REG:
        raise KeyError(f"unknown recaller: {name}")
    return _REG[name]


def list_names() -> list[str]:
    return sorted(_REG)


def clear() -> None:
    _REG.clear()
