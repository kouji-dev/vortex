"""ReAct loop — Plan → Act → Observe → Reflect; one tool per step."""

from __future__ import annotations

import pytest

from ai_portal.workers.agent_loops.providers.react import ReactLoop
from ai_portal.workers.tools.protocol import ToolResult
from ai_portal.workers.types import EventKind

from tests.workers.agent_loops.conftest import FakeTool


@pytest.mark.asyncio
async def test_react_iterates_until_final(make_ctx, fake_gateway):
    shell = FakeTool("shell", result=ToolResult(ok=True, output={"stdout": "x\n"}))
    fake_gateway.queue(
        [
            {"thought": "use shell", "tool": "shell", "tool_args": {"cmd": ["echo", "x"]}},
            {"thought": "done", "tool": None, "final": "done"},
        ]
    )
    loop = ReactLoop()
    ctx = await make_ctx(tools=[shell], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    kinds = [e.kind for e in events]
    assert EventKind.agent_thought in kinds
    assert EventKind.tool_call in kinds
    assert EventKind.tool_result in kinds
    assert len(shell.calls) == 1
    assert shell.calls[0]["cmd"] == ["echo", "x"]


@pytest.mark.asyncio
async def test_react_emits_error_on_unknown_tool(make_ctx, fake_gateway):
    fake_gateway.queue(
        [
            {"thought": "use", "tool": "ghost_tool", "tool_args": {}},
            {"thought": "done", "tool": None, "final": "done"},
        ]
    )
    loop = ReactLoop()
    ctx = await make_ctx(tools=[], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    kinds = [e.kind for e in events]
    assert EventKind.error in kinds


@pytest.mark.asyncio
async def test_react_stops_at_max_iterations(make_ctx, fake_gateway):
    shell = FakeTool("shell")
    # Always queue tool_use response; loop must stop at max_iterations.
    for _ in range(20):
        fake_gateway.queue(
            [{"thought": "loop", "tool": "shell", "tool_args": {"cmd": ["true"]}}]
        )
    loop = ReactLoop()
    ctx = await make_ctx(tools=[shell], max_iterations=3)
    events = [ev async for ev in loop.run(ctx)]
    tool_calls = [e for e in events if e.kind == EventKind.tool_call]
    assert len(tool_calls) == 3


@pytest.mark.asyncio
async def test_react_injects_repo_instructions(make_ctx, fake_gateway):
    fake_gateway.queue([{"thought": "done", "tool": None, "final": "done"}])
    loop = ReactLoop(repo_instructions="caveman: dont push to main")
    ctx = await make_ctx(tools=[], max_iterations=2)
    _ = [ev async for ev in loop.run(ctx)]
    sys_msg = fake_gateway.requests[0]["messages"][0]
    assert sys_msg["role"] == "system"
    assert "caveman" in sys_msg["content"]


@pytest.mark.asyncio
async def test_react_appends_tool_result_to_messages(make_ctx, fake_gateway):
    shell = FakeTool("shell", result=ToolResult(ok=True, output={"stdout": "ok"}))
    fake_gateway.queue(
        [
            {"thought": "go", "tool": "shell", "tool_args": {"cmd": ["true"]}},
            {"thought": "done", "tool": None, "final": "done"},
        ]
    )
    loop = ReactLoop()
    ctx = await make_ctx(tools=[shell], max_iterations=5)
    _ = [ev async for ev in loop.run(ctx)]
    # Second request should carry assistant tool_call + tool result.
    msgs = fake_gateway.requests[1]["messages"]
    roles = [m["role"] for m in msgs]
    assert "tool" in roles
