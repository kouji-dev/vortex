"""Each agent loop must emit at least one Phase.REFLECT event per run."""

from __future__ import annotations

import pytest

from ai_portal.workers.agent_loops.protocol import Phase, ReflectDecision
from ai_portal.workers.agent_loops.providers.openhands_style import (
    OpenHandsStyleLoop,
)
from ai_portal.workers.agent_loops.providers.plan_and_execute import (
    PlanAndExecuteLoop,
)
from ai_portal.workers.agent_loops.providers.react import ReactLoop
from ai_portal.workers.tools.protocol import ToolResult
from ai_portal.workers.types import EventKind


def _reflects(events) -> list:
    return [
        e for e in events
        if e.kind == EventKind.phase_changed
        and e.payload.get("phase") == Phase.REFLECT.value
    ]


@pytest.mark.asyncio
async def test_react_emits_reflect_after_tool(make_ctx, fake_gateway) -> None:
    from tests.workers.agent_loops.conftest import FakeTool

    tool = FakeTool("shell", result=ToolResult(ok=True, output={"out": "ok"}))
    ctx = await make_ctx(tools=[tool])
    fake_gateway.queue(
        [
            {"thought": "run", "tool": "shell", "tool_args": {"cmd": ["ls"]}},
            {"final": "final answer done"},
        ]
    )

    events = [ev async for ev in ReactLoop().run(ctx)]
    reflects = _reflects(events)
    assert reflects, "react must emit a REFLECT event"
    decisions = {r.payload.get("decision") for r in reflects}
    assert ReflectDecision.RETRY.value in decisions or ReflectDecision.DONE.value in decisions


@pytest.mark.asyncio
async def test_react_reflect_decision_escalate_on_tool_failure(
    make_ctx, fake_gateway
) -> None:
    from tests.workers.agent_loops.conftest import FakeTool

    tool = FakeTool(
        "shell", result=ToolResult(ok=False, output=None, error="boom")
    )
    ctx = await make_ctx(tools=[tool])
    fake_gateway.queue(
        [
            {"thought": "run", "tool": "shell", "tool_args": {"cmd": ["x"]}},
            {"final": "final"},
        ]
    )
    events = [ev async for ev in ReactLoop().run(ctx)]
    reflects = _reflects(events)
    decisions = [r.payload.get("decision") for r in reflects]
    assert ReflectDecision.ESCALATE.value in decisions


@pytest.mark.asyncio
async def test_plan_and_execute_emits_reflect(make_ctx, fake_gateway) -> None:
    from tests.workers.agent_loops.conftest import FakeTool

    tool = FakeTool("shell", result=ToolResult(ok=True, output={"o": 1}))
    ctx = await make_ctx(tools=[tool])
    # Plan response → exec tool → final.
    fake_gateway.queue(
        [
            {"final": "1. ls\n2. cat README"},
            {"thought": "ls", "tool": "shell", "tool_args": {"cmd": ["ls"]}},
            {"final": "done"},
        ]
    )
    events = [ev async for ev in PlanAndExecuteLoop().run(ctx)]
    reflects = _reflects(events)
    assert reflects, "plan_and_execute must emit a REFLECT event"


@pytest.mark.asyncio
async def test_openhands_style_emits_reflect(make_ctx, fake_gateway) -> None:
    from tests.workers.agent_loops.conftest import FakeTool

    shell_tool = FakeTool("shell", result=ToolResult(ok=True, output={"o": 0}))
    ctx = await make_ctx(tools=[shell_tool])
    # Native tool call → finish.
    fake_gateway.queue(
        [
            {
                "thought": "run shell",
                "tool": "shell",
                "tool_args": {"cmd": ["ls"]},
            },
            {"final": "<finish>"},
        ]
    )
    events = [ev async for ev in OpenHandsStyleLoop().run(ctx)]
    reflects = _reflects(events)
    assert reflects, "openhands_style must emit a REFLECT event"
    # Either retry after the ok tool, or done at finish.
    decisions = {r.payload.get("decision") for r in reflects}
    assert decisions & {
        ReflectDecision.RETRY.value,
        ReflectDecision.DONE.value,
    }
