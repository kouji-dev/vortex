"""Agent loop protocol — pluggable agentic strategy.

Concrete loops (ReAct, Plan-and-Execute, OpenHands-style) implement this
contract. The orchestrator drives the loop and streams the events it yields.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ai_portal.workers.types import WorkerEvent


@dataclass
class AgentRunCtx:
    """Per-run context handed to the agent loop."""

    task: Any
    run: Any
    tools: list
    gateway: Any
    sandbox: Any
    sandbox_provider: Any
    repo: Any
    model: str
    max_iterations: int = 40


@runtime_checkable
class AgentLoop(Protocol):
    """Contract every agent loop must satisfy."""

    name: str

    def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]: ...
