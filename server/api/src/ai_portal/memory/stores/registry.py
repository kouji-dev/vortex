"""Process-local registry of memory stores.

Stores may need a SQLAlchemy session to construct, so this registry stores
factories rather than singletons.
"""
from __future__ import annotations

from typing import Any, Callable

_REG: dict[str, Callable[..., Any]] = {}


def register(name: str, factory: Callable[..., Any]) -> None:
    if not name:
        raise ValueError("store registration requires a name")
    _REG[name] = factory


def get(name: str) -> Callable[..., Any]:
    if name not in _REG:
        raise KeyError(f"unknown store: {name}")
    return _REG[name]


def list_names() -> list[str]:
    return sorted(_REG)


def clear() -> None:
    _REG.clear()
