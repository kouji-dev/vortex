"""Tool registry with per-pool allow-list enforcement.

Tools are registered globally by name. The orchestrator builds a per-run
tool list by calling :func:`for_pool` with the pool's allow-list.
"""

from __future__ import annotations

from ai_portal.workers.tools.protocol import Tool


class ToolNotRegistered(KeyError):
    """Raised when ``get(name)`` finds no tool."""


class ToolNotAllowed(PermissionError):
    """Raised when a tool is requested but not on the pool's allow-list."""


_REG: dict[str, Tool] = {}


def register(tool: Tool) -> None:
    """Register a tool under ``tool.name``."""
    _REG[tool.name] = tool


def get(name: str) -> Tool:
    """Lookup a tool by name. Raises :class:`ToolNotRegistered`."""
    try:
        return _REG[name]
    except KeyError as e:
        raise ToolNotRegistered(name) from e


def all_tools() -> list[str]:
    """All registered tool names."""
    return list(_REG.keys())


def clear() -> None:
    """Test helper — empty the registry."""
    _REG.clear()


def for_pool(allow_list: list[str]) -> list[Tool]:
    """Return tools allowed for a pool.

    Empty ``allow_list`` means **no** tools (default-deny). Pass ``["*"]``
    to allow everything registered. Unknown names raise
    :class:`ToolNotRegistered`.
    """
    if "*" in allow_list:
        return list(_REG.values())
    out: list[Tool] = []
    for name in allow_list:
        out.append(get(name))
    return out


def resolve(name: str, allow_list: list[str]) -> Tool:
    """Resolve a tool by name, enforcing the pool's allow-list."""
    if "*" not in allow_list and name not in allow_list:
        raise ToolNotAllowed(name)
    return get(name)
