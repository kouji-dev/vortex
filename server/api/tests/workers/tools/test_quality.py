"""Tests for run_tests / run_build / lint / format tools."""

from __future__ import annotations

import pytest

from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.tools.providers.quality import (
    FormatTool,
    LintTool,
    RunBuildTool,
    RunTestsTool,
)


@pytest.mark.asyncio
async def test_run_tests_uses_template_default(harness) -> None:
    sb = FakeSandbox(scripts={("pytest", "-x"): (0, "ok", "")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "python"}
    )
    r = await RunTestsTool().invoke({}, ctx)
    assert r.ok
    assert r.output["cmd"] == ["pytest", "-x"]


@pytest.mark.asyncio
async def test_run_tests_pool_override_wins(harness) -> None:
    sb = FakeSandbox(
        scripts={("uv", "run", "pytest", "-x"): (0, "ok", "")}
    )
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb,
        pool_settings={
            "template": "python",
            "commands": {"run_tests": ["uv", "run", "pytest", "-x"]},
        },
    )
    r = await RunTestsTool().invoke({}, ctx)
    assert r.ok
    assert r.output["cmd"][0] == "uv"


@pytest.mark.asyncio
async def test_run_tests_arg_override_wins(harness) -> None:
    sb = FakeSandbox(scripts={("make", "test"): (0, "ok", "")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "python"}
    )
    r = await RunTestsTool().invoke({"cmd": ["make", "test"]}, ctx)
    assert r.ok
    assert r.output["cmd"] == ["make", "test"]


@pytest.mark.asyncio
async def test_no_command_configured_fails(harness) -> None:
    _sb, _h, ctx, _rec = await harness(pool_settings={"template": None})
    r = await RunTestsTool().invoke({}, ctx)
    assert not r.ok
    assert "no command" in r.error


@pytest.mark.asyncio
async def test_run_build_template_default(harness) -> None:
    sb = FakeSandbox(scripts={("go", "build", "./..."): (0, "", "")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "go"}
    )
    r = await RunBuildTool().invoke({}, ctx)
    assert r.ok


@pytest.mark.asyncio
async def test_lint_template_default(harness) -> None:
    sb = FakeSandbox(scripts={("ruff", "check", "."): (0, "", "")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "python"}
    )
    r = await LintTool().invoke({}, ctx)
    assert r.ok


@pytest.mark.asyncio
async def test_format_template_default(harness) -> None:
    sb = FakeSandbox(scripts={("cargo", "fmt"): (0, "", "")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "rust"}
    )
    r = await FormatTool().invoke({}, ctx)
    assert r.ok


@pytest.mark.asyncio
async def test_failing_exit_marks_not_ok(harness) -> None:
    sb = FakeSandbox(scripts={("pytest", "-x"): (1, "", "boom")})
    _sb, _h, ctx, _rec = await harness(
        sandbox=sb, pool_settings={"template": "python"}
    )
    r = await RunTestsTool().invoke({}, ctx)
    assert not r.ok
    assert r.output["exit_code"] == 1
    assert "boom" in r.output["stderr"]
