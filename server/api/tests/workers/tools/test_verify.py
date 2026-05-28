"""Verify tool — run repo-defined test/lint/typecheck/build sequence."""

from __future__ import annotations

import pytest

from ai_portal.workers.tools.providers.verify import VerifyTool


@pytest.mark.asyncio
async def test_verify_runs_all_checks_in_order(harness):
    sb, h, ctx, rec = await harness(
        pool_settings={
            "verify": {
                "test": ["echo", "tests"],
                "lint": ["echo", "lint"],
                "typecheck": ["echo", "types"],
                "build": ["echo", "build"],
            }
        }
    )
    r = await VerifyTool().invoke({}, ctx)
    assert r.ok is True
    # Each check is its own entry in the report.
    steps = r.output["steps"]
    assert [s["name"] for s in steps] == ["test", "lint", "typecheck", "build"]
    assert all(s["ok"] for s in steps)


@pytest.mark.asyncio
async def test_verify_stops_at_first_failure_by_default(harness):
    sb, h, ctx, rec = await harness(
        pool_settings={
            "verify": {
                "test": ["false"],
                "lint": ["echo", "lint"],
            }
        }
    )
    r = await VerifyTool().invoke({}, ctx)
    assert r.ok is False
    names = [s["name"] for s in r.output["steps"]]
    # Stopped after first failure → lint not run.
    assert names == ["test"]


@pytest.mark.asyncio
async def test_verify_continue_on_error(harness):
    sb, h, ctx, rec = await harness(
        pool_settings={
            "verify": {
                "test": ["false"],
                "lint": ["echo", "lint"],
            }
        }
    )
    r = await VerifyTool().invoke({"continue_on_error": True}, ctx)
    assert r.ok is False
    names = [s["name"] for s in r.output["steps"]]
    assert names == ["test", "lint"]


@pytest.mark.asyncio
async def test_verify_skips_when_no_commands_configured(harness):
    sb, h, ctx, rec = await harness(pool_settings={})
    r = await VerifyTool().invoke({}, ctx)
    assert r.ok is True
    assert r.output["steps"] == []


@pytest.mark.asyncio
async def test_verify_only_runs_requested_steps(harness):
    sb, h, ctx, rec = await harness(
        pool_settings={
            "verify": {
                "test": ["echo", "t"],
                "lint": ["echo", "l"],
                "build": ["echo", "b"],
            }
        }
    )
    r = await VerifyTool().invoke({"only": ["test", "build"]}, ctx)
    names = [s["name"] for s in r.output["steps"]]
    assert names == ["test", "build"]


@pytest.mark.asyncio
async def test_verify_emits_tool_call_events(harness):
    sb, h, ctx, rec = await harness(
        pool_settings={"verify": {"test": ["echo", "t"]}}
    )
    await VerifyTool().invoke({}, ctx)
    kinds = [e[0] for e in rec.events]
    assert "tool_call" in kinds
