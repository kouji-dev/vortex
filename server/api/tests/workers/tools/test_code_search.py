"""Tests for code_search tool (ripgrep + ast-grep)."""

from __future__ import annotations

import json

import pytest

from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.tools.providers.code_search import CodeSearchTool


def _rg_match(path: str, line: int, text: str) -> str:
    """Build a single ripgrep --json 'match' record."""
    return json.dumps(
        {
            "type": "match",
            "data": {
                "path": {"text": path},
                "line_number": line,
                "lines": {"text": text + "\n"},
            },
        }
    )


@pytest.mark.asyncio
async def test_code_search_ripgrep_parses_matches(harness) -> None:
    out = (
        _rg_match("src/a.py", 12, "def foo(): pass")
        + "\n"
        + _rg_match("src/b.py", 3, "foo = 1")
        + "\n"
    )
    sb = FakeSandbox(
        scripts={
            ("rg", "--json", "foo", "."): (0, out, ""),
        }
    )
    _sb, _h, ctx, _rec = await harness(sandbox=sb)
    r = await CodeSearchTool().invoke({"pattern": "foo"}, ctx)
    assert r.ok
    assert r.output["count"] == 2
    assert r.output["matches"][0]["path"] == "src/a.py"
    assert r.output["matches"][0]["line"] == 12


@pytest.mark.asyncio
async def test_code_search_ripgrep_no_match_is_ok(harness) -> None:
    # rg exits 1 when there are no matches — we treat that as OK.
    sb = FakeSandbox(
        scripts={
            ("rg", "--json", "missing", "."): (1, "", ""),
        }
    )
    _sb, _h, ctx, _rec = await harness(sandbox=sb)
    r = await CodeSearchTool().invoke({"pattern": "missing"}, ctx)
    assert r.ok
    assert r.output["count"] == 0


@pytest.mark.asyncio
async def test_code_search_ast_grep_engine(harness) -> None:
    out = json.dumps({"file": "src/a.py", "range": [1, 2]}) + "\n"
    sb = FakeSandbox(
        scripts={
            ("ast-grep", "--json", "--pattern", "def $X():", "."): (
                0,
                out,
                "",
            ),
        }
    )
    _sb, _h, ctx, _rec = await harness(sandbox=sb)
    r = await CodeSearchTool().invoke(
        {"pattern": "def $X():", "engine": "ast-grep"}, ctx
    )
    assert r.ok
    assert r.output["engine"] == "ast-grep"
    assert r.output["count"] == 1


@pytest.mark.asyncio
async def test_code_search_unknown_engine(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await CodeSearchTool().invoke(
        {"pattern": "x", "engine": "bogus"}, ctx
    )
    assert not r.ok
