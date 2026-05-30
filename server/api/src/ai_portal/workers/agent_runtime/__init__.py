"""Agent runtime abstraction — drives a real coding-agent CLI/SDK in a sandbox.

v1 primary path (see spec "Agent Runtime"). A runtime drives a real agent CLI
(Claude Agent SDK / Codex) **inside the worker's sandbox** and brokers its
streaming stdio + structured events back to the orchestrator.

Public surface:

- :class:`AgentRuntime`        — the protocol every runtime implements.
- :class:`AgentRuntimeConfig`  — model + gateway base_url + skills + repo dir.
- :class:`AgentEvent`          — one normalized event off the runtime wire.
- :data:`AgentEventKind`       — Claude/Codex events normalized to one taxonomy.
- :func:`get_runtime`          — registry lookup by name (``claude`` | ``codex``).

The concrete runtimes (:mod:`.claude`, :mod:`.codex`) are **interface only** —
the real CLI exec is stubbed with an explicit ``NotImplementedError`` and a
``TODO`` marking the VM/agent-SDK boundary. No fabricated agent output.
"""

from __future__ import annotations

from ai_portal.workers.agent_runtime.protocol import (
    AgentEvent,
    AgentEventKind,
    AgentRuntime,
    AgentRuntimeConfig,
    PermissionRequest,
    PermissionDecision,
)
from ai_portal.workers.agent_runtime.registry import get_runtime, list_runtimes

__all__ = [
    "AgentEvent",
    "AgentEventKind",
    "AgentRuntime",
    "AgentRuntimeConfig",
    "PermissionRequest",
    "PermissionDecision",
    "get_runtime",
    "list_runtimes",
]
