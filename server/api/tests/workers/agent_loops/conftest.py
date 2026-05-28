"""Shared fixtures for agent-loop tests.

Provides:
- ``FakeGateway`` — queue-driven LLM stub returning scripted responses
  with ``tool_calls`` or final ``content``.
- ``FakeTool`` — captures every invocation; ``ToolResult`` configurable.
- ``make_ctx`` factory — builds a minimal :class:`AgentRunCtx`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from ai_portal.workers.agent_loops.protocol import AgentRunCtx
from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.tools.protocol import ToolContext, ToolResult
from ai_portal.workers.types import ResourceLimits


@dataclass
class _ToolCall:
    name: str
    arguments: dict
    reasoning: str = ""


@dataclass
class _GwResponse:
    """Minimal response shape consumed by agent loops."""

    content: str = ""
    tool_calls: list[_ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"
    cost_cents: int = 0


class FakeGateway:
    """Returns scripted responses in FIFO order."""

    def __init__(self) -> None:
        self._queue: list[_GwResponse] = []
        self.requests: list[dict] = []

    def queue(self, items: list[dict]) -> None:
        """Queue scripted responses.

        Each item shape:
          {"thought": str, "tool": str|None, "tool_args": dict, "final": str?}
        """
        for it in items:
            tool = it.get("tool")
            tcs: list[_ToolCall] = []
            if tool:
                tcs.append(
                    _ToolCall(
                        name=tool,
                        arguments=it.get("tool_args", {}),
                        reasoning=it.get("thought", ""),
                    )
                )
            self._queue.append(
                _GwResponse(
                    content=it.get("final", "") or it.get("thought", ""),
                    tool_calls=tcs,
                    stop_reason=(
                        "end_turn" if it.get("final") or not tool else "tool_use"
                    ),
                )
            )

    async def complete(self, req: dict) -> _GwResponse:
        self.requests.append(req)
        if not self._queue:
            return _GwResponse(content="(no more responses)", stop_reason="end_turn")
        return self._queue.pop(0)


class FakeTool:
    """Tool stub that returns a fixed result and records calls."""

    def __init__(
        self,
        name: str,
        *,
        result: ToolResult | None = None,
        schema: dict | None = None,
    ) -> None:
        self.name = name
        self.schema = schema or {"type": "object", "properties": {}}
        self._result = result or ToolResult(ok=True, output={"ran": name})
        self.calls: list[dict] = []

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        self.calls.append(dict(args))
        return self._result


@dataclass
class _FakeTask:
    id: str = "task-1"
    title: str = "do thing"
    description: str = "details"
    org_id: str = "org-1"


@dataclass
class _FakeRun:
    id: str = "run-1"
    task_id: str = "task-1"


@pytest.fixture
def fake_gateway() -> FakeGateway:
    return FakeGateway()


@pytest.fixture
def fake_sandbox():
    """Returns ``(provider, handle)`` for a fresh fake sandbox."""

    async def _make():
        sb = FakeSandbox()
        h = await sb.provision(
            image="x",
            limits=ResourceLimits(),
            env={},
            egress_allow_list=[],
        )
        return sb, h

    return _make


@pytest.fixture
def make_ctx(fake_sandbox, fake_gateway):
    """Builds an ``AgentRunCtx`` with fakes."""

    async def _make(
        *,
        tools: list[Any],
        model: str = "claude-sonnet-4-6",
        max_iterations: int = 10,
        task: _FakeTask | None = None,
        run: _FakeRun | None = None,
    ) -> AgentRunCtx:
        sb, h = await fake_sandbox()
        return AgentRunCtx(
            task=task or _FakeTask(),
            run=run or _FakeRun(),
            tools=tools,
            gateway=fake_gateway,
            sandbox=h,
            sandbox_provider=sb,
            repo=None,
            model=model,
            max_iterations=max_iterations,
        )

    return _make


@pytest.fixture
def fake_task():
    return _FakeTask()


@pytest.fixture
def fake_run():
    return _FakeRun()
