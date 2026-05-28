"""OpenHands-style CodeAct — model emits code blocks as actions."""

from __future__ import annotations

import pytest

from ai_portal.workers.agent_loops.providers.openhands_style import (
    OpenHandsStyleLoop,
)
from ai_portal.workers.tools.protocol import ToolResult
from ai_portal.workers.types import EventKind

from tests.workers.agent_loops.conftest import FakeTool


@pytest.mark.asyncio
async def test_codeact_extracts_python_block(make_ctx, fake_gateway):
    py = FakeTool("python_exec", result=ToolResult(ok=True, output={"stdout": "42\n"}))
    fake_gateway.queue(
        [
            {
                "thought": "compute",
                "tool": None,
                "final": "```python\nprint(40+2)\n```",
            },
            {"thought": "done", "tool": None, "final": "<finish>"},
        ]
    )
    loop = OpenHandsStyleLoop()
    ctx = await make_ctx(tools=[py], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    tool_calls = [e for e in events if e.kind == EventKind.tool_call]
    assert tool_calls
    assert tool_calls[0].payload["tool"] == "python_exec"
    assert "print(40+2)" in tool_calls[0].payload["args"]["code"]


@pytest.mark.asyncio
async def test_codeact_extracts_bash_block(make_ctx, fake_gateway):
    sh = FakeTool("shell", result=ToolResult(ok=True, output={"stdout": "ok"}))
    fake_gateway.queue(
        [
            {"thought": "run", "tool": None, "final": "```bash\nls -la\n```"},
            {"thought": "done", "tool": None, "final": "<finish>"},
        ]
    )
    loop = OpenHandsStyleLoop()
    ctx = await make_ctx(tools=[sh], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    tool_calls = [e for e in events if e.kind == EventKind.tool_call]
    assert tool_calls[0].payload["tool"] == "shell"
    assert tool_calls[0].payload["args"]["cmd"] == ["bash", "-lc", "ls -la"]


@pytest.mark.asyncio
async def test_codeact_native_tool_call_overrides_block(make_ctx, fake_gateway):
    sh = FakeTool("shell", result=ToolResult(ok=True, output={"stdout": "ok"}))
    fake_gateway.queue(
        [
            {
                "thought": "act",
                "tool": "shell",
                "tool_args": {"cmd": ["echo", "hi"]},
            },
            {"thought": "done", "tool": None, "final": "<finish>"},
        ]
    )
    loop = OpenHandsStyleLoop()
    ctx = await make_ctx(tools=[sh], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    tool_calls = [e for e in events if e.kind == EventKind.tool_call]
    assert tool_calls[0].payload["args"]["cmd"] == ["echo", "hi"]


@pytest.mark.asyncio
async def test_codeact_finishes_on_finish_marker(make_ctx, fake_gateway):
    fake_gateway.queue([{"thought": "all good", "tool": None, "final": "<finish>"}])
    loop = OpenHandsStyleLoop()
    ctx = await make_ctx(tools=[], max_iterations=5)
    events = [ev async for ev in loop.run(ctx)]
    # No tool calls but should finish cleanly.
    assert any(e.kind == EventKind.agent_thought for e in events)
