"""Agent loop protocol — pluggable agentic strategy.

Concrete loops (ReAct, Plan-and-Execute, OpenHands-style) implement this
contract. The orchestrator drives the loop and streams the events it yields.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ai_portal.workers.types import WorkerEvent


class Phase(str, enum.Enum):
    """Lifecycle phase emitted on ``phase_changed`` events.

    REFLECT is the per-iteration decision point: after every observation
    the loop classifies the next move as ``retry`` / ``escalate`` /
    ``done`` and continues, surfaces an approval, or stops.
    """

    PLANNING = "planning"
    EXECUTING = "executing"
    REFLECT = "reflect"
    DONE = "done"


class ReflectDecision(str, enum.Enum):
    """Outcome of a single reflection step."""

    RETRY = "retry"
    ESCALATE = "escalate"
    DONE = "done"


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
