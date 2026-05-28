"""Plan-and-Execute — distinct planner pass then per-step executor."""

from __future__ import annotations

import pytest

from ai_portal.workers.agent_loops.providers.plan_and_execute import (
    PlanAndExecuteLoop,
)
from ai_portal.workers.tools.protocol import ToolResult
from ai_portal.workers.types import EventKind

from tests.workers.agent_loops.conftest import FakeTool


@pytest.mark.asyncio
async def test_plan_then_execute_each_step(make_ctx, fake_gateway):
    shell = FakeTool("shell", result=ToolResult(ok=True, output={"stdout": "ok"}))
    # First response = plan (final text). Subsequent = act → done.
    fake_gateway.queue(
        [
            {
                "thought": "plan",
                "tool": None,
                "final": "plan:\n- step 1: write\n- step 2: test",
            },
            {"thought": "do step 1", "tool": "shell", "tool_args": {"cmd": ["true"]}},
            {"thought": "do step 2", "tool": "shell", "tool_args": {"cmd": ["true"]}},
            {"thought": "done", "tool": None, "final": "all done"},
        ]
    )
    loop = PlanAndExecuteLoop()
    ctx = await make_ctx(tools=[shell], max_iterations=10)
    events = [ev async for ev in loop.run(ctx)]
    kinds = [e.kind for e in events]

    # First event must be the plan thought / phase change.
    assert any(
        e.kind == EventKind.agent_thought
        and "step 1" in (e.payload.get("text") or "")
        for e in events
    )
    # Plan phase_changed emitted.
    phase_changes = [e for e in events if e.kind == EventKind.phase_changed]
    assert any(p.payload.get("phase") == "planning" for p in phase_changes)
    assert any(p.payload.get("phase") == "executing" for p in phase_changes)
    assert kinds.count(EventKind.tool_call) == 2


@pytest.mark.asyncio
async def test_plan_and_execute_stops_when_no_plan(make_ctx, fake_gateway):
    # Planner returns empty; loop must terminate cleanly.
    fake_gateway.queue([{"thought": "", "tool": None, "final": ""}])
    loop = PlanAndExecuteLoop()
    ctx = await make_ctx(tools=[], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    assert any(e.kind == EventKind.error for e in events)
