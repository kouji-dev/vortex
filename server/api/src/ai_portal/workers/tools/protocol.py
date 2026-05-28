"""Tool protocol — worker-callable capabilities.

A ``Tool`` is anything the agent loop can invoke with structured args inside
a sandboxed context. Bundled tools include shell, file I/O, code search,
test/build/lint runners, git, PR ops, web fetch, KB/web search, memory ops,
and an MCP bridge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


@dataclass
class ToolResult:
    """Uniform return shape for every tool invocation."""

    ok: bool
    output: Any = None
    error: str | None = None
    artifacts: list[dict] = field(default_factory=list)


@dataclass
class ToolContext:
    """Per-invocation context handed to every tool.

    Slots are typed loosely (``Any``) because tools may run with a fake
    sandbox, a real provider, or a stub gateway — concrete shapes live in
    the orchestrator/test fixtures.
    """

    sandbox: Any
    sandbox_provider: Any
    task_id: str
    run_id: str
    actor_id: str
    org_id: str
    emit_event: Callable[..., Awaitable[None]]
    egress: Any = None
    gateway: Any = None
    repo: Any = None
    secrets_proxy: Any = None
    audit: Callable[..., Awaitable[None]] | None = None
    pool_settings: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Tool(Protocol):
    """Contract every tool must satisfy."""

    name: str
    schema: dict

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult: ...
