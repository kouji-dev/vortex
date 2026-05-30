"""Agent runtime registry — name → runtime factory.

Bundled: ``claude`` (Claude Agent SDK / CLI), ``codex`` (Codex CLI). Mirrors
the sandbox/git/issues/tools registry pattern in this module.
"""

from __future__ import annotations

from typing import Callable

from ai_portal.workers.agent_runtime.claude import ClaudeAgentRuntime
from ai_portal.workers.agent_runtime.codex import CodexAgentRuntime
from ai_portal.workers.agent_runtime.protocol import AgentRuntime

_FACTORIES: dict[str, Callable[[], AgentRuntime]] = {
    "claude": ClaudeAgentRuntime,
    "codex": CodexAgentRuntime,
}


class UnknownRuntime(KeyError):
    """Requested runtime name is not registered."""


def get_runtime(name: str) -> AgentRuntime:
    """Instantiate the runtime registered under ``name``."""
    factory = _FACTORIES.get(name)
    if factory is None:
        raise UnknownRuntime(name)
    return factory()


def list_runtimes() -> list[str]:
    """Names of registered runtimes."""
    return sorted(_FACTORIES)
