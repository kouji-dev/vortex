"""Codex CLI runtime — interface only (real exec STUBBED).

Drives ``codex exec`` headless inside the worker sandbox:

- ``codex exec`` runs a single session to completion, non-interactive.
- ``--json`` → stdout is a JSONL event stream (``thread.started`` /
  ``turn.started`` / ``turn.completed`` / ``turn.failed`` / ``item.*`` /
  ``error``). Item types: agent messages, reasoning, command exec, file
  changes, MCP tool calls, web searches, plan updates.
- LLM calls routed through our gateway via ``OPENAI_BASE_URL`` in the VM.

Interactive steering maps each user message to a fresh ``codex exec`` (one run).
NOTHING here fabricates agent output — real exec raises at the TODO boundary.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ai_portal.workers.agent_runtime.protocol import (
    AgentEvent,
    AgentEventKind,
    AgentRuntimeConfig,
    PermissionResponder,
)


# Codex JSONL event-type → normalized AgentEventKind. Pure mapping table;
# unit-tested without invoking the CLI.
CODEX_EVENT_MAP: dict[str, AgentEventKind] = {
    "thread.started": AgentEventKind.run_started,
    "turn.started": AgentEventKind.run_started,
    "turn.completed": AgentEventKind.run_finished,
    "turn.failed": AgentEventKind.error,
    "item.agent_message": AgentEventKind.agent_message,
    "item.reasoning": AgentEventKind.agent_thought,
    "item.command_execution": AgentEventKind.shell_output,
    "item.file_change": AgentEventKind.file_changed,
    "item.mcp_tool_call": AgentEventKind.tool_call,
    "item.web_search": AgentEventKind.tool_call,
    "item.plan_update": AgentEventKind.agent_thought,
    "error": AgentEventKind.error,
}


def map_codex_event(event_type: str) -> AgentEventKind:
    """Normalize a Codex JSONL event type (pure)."""
    return CODEX_EVENT_MAP.get(event_type, AgentEventKind.agent_stdio)


class CodexAgentRuntime:
    """Codex CLI runtime adapter (interface only)."""

    name = "codex"
    base_url_env = "OPENAI_BASE_URL"

    def __init__(self) -> None:
        self._config: AgentRuntimeConfig | None = None
        self._on_permission: PermissionResponder | None = None

    def build_launch_env(self, config: AgentRuntimeConfig) -> dict[str, str]:
        """Point the Codex CLI at our gateway (pure)."""
        env = dict(config.env)
        env[self.base_url_env] = config.gateway_base_url
        return env

    def build_cli_args(self, config: AgentRuntimeConfig, message: str) -> list[str]:
        """Compose a headless ``codex exec --json`` invocation (pure)."""
        return ["codex", "exec", "--json", "--model", config.model, message]

    async def start(
        self,
        sandbox: Any,
        config: AgentRuntimeConfig,
        *,
        on_permission: PermissionResponder | None = None,
    ) -> None:
        self._config = config
        self._on_permission = on_permission
        # TODO(agent-sdk-boundary): install the Codex CLI in `sandbox` and
        # verify auth against the gateway base_url. No persistent process —
        # Codex is per-run via `codex exec`.
        raise NotImplementedError(
            "Codex CLI exec is stubbed — needs real sandbox + in-sandbox runner."
        )

    def send_message(self, text: str) -> AsyncIterator[AgentEvent]:
        # TODO(agent-sdk-boundary): run `codex exec --json <text>` in the
        # sandbox, parse the JSONL stream via map_codex_event into AgentEvent.
        raise NotImplementedError("Codex runtime streaming is stubbed.")

    async def interrupt(self) -> None:
        # TODO(agent-sdk-boundary): signal the running `codex exec` process.
        raise NotImplementedError("Codex runtime interrupt is stubbed.")

    async def stop(self) -> None:
        # TODO(agent-sdk-boundary): kill any running `codex exec` process.
        raise NotImplementedError("Codex runtime stop is stubbed.")
