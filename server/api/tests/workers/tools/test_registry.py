"""Tests for the tool registry + bundled registration."""

from __future__ import annotations

import pytest

from ai_portal.workers.tools import bundled, registry
from ai_portal.workers.tools.protocol import ToolResult
from ai_portal.workers.tools.registry import ToolNotAllowed, ToolNotRegistered


class _Stub:
    name = "stub"
    schema: dict = {"type": "object"}

    async def invoke(self, args, ctx):
        return ToolResult(ok=True, output=args)


def _reset() -> None:
    registry.clear()


def test_register_and_get() -> None:
    _reset()
    s = _Stub()
    registry.register(s)
    assert registry.get("stub") is s
    assert "stub" in registry.all_tools()


def test_get_missing_raises() -> None:
    _reset()
    with pytest.raises(ToolNotRegistered):
        registry.get("missing")


def test_for_pool_filters_by_allow_list() -> None:
    _reset()
    bundled.register_bundled()
    subset = registry.for_pool(["shell", "read_file"])
    names = sorted(t.name for t in subset)
    assert names == ["read_file", "shell"]


def test_for_pool_star_returns_everything() -> None:
    _reset()
    bundled.register_bundled()
    subset = registry.for_pool(["*"])
    assert {t.name for t in subset} == set(bundled.BUNDLED_TOOL_NAMES)


def test_for_pool_empty_means_nothing() -> None:
    _reset()
    bundled.register_bundled()
    assert registry.for_pool([]) == []


def test_resolve_respects_allow_list() -> None:
    _reset()
    bundled.register_bundled()
    assert registry.resolve("shell", ["shell"]).name == "shell"
    with pytest.raises(ToolNotAllowed):
        registry.resolve("shell", ["read_file"])


def test_bundled_registers_nine_tools() -> None:
    _reset()
    bundled.register_bundled()
    assert sorted(registry.all_tools()) == sorted(bundled.BUNDLED_TOOL_NAMES)
    assert len(bundled.BUNDLED_TOOL_NAMES) == 9
