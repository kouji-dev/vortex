"""Memory policy protocol, registry, and bundled implementations."""
from __future__ import annotations

from .protocol import MemoryPolicy
from .registry import get, list_names, register

from . import default  # noqa: F401
from . import strict_eu  # noqa: F401

__all__ = ["MemoryPolicy", "get", "list_names", "register"]
