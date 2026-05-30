"""Agent runtime protocol + normalized wire types.

Designed against the **current** (May 2026) reality of the two agent CLIs,
verified by docs lookup at implementation time:

Claude Agent SDK (``@anthropic-ai/claude-agent-sdk`` / ``claude_agent_sdk``)
  - **Streaming input mode** is the recommended driver: you feed an async
    generator of user messages and consume an async stream of messages
    (``assistant`` / tool_use / tool_result / ``result``).
  - **Permissions**: a ``canUseTool`` callback is invoked when a tool isn't
    pre-approved by ``allowed_tools`` / rules / mode. Modes: ``default`` |
    ``acceptEdits`` | ``plan`` | ``dontAsk`` | ``bypassPermissions``. The host
    app answers allow/deny — this is the per-step prompt the worker surfaces.
  - **Skills**: loaded from the filesystem via ``setting_sources`` with the
    ``Skill`` tool allowed; the agent gets skill descriptions at startup and
    loads full content on demand.
  - **Model / base_url**: model via ``ClaudeAgentOptions``; gateway routing via
    ``ANTHROPIC_BASE_URL`` env in the sandbox (so all LLM calls go through our
    gateway — keys + routing + audit live there).

Codex CLI (``codex exec``)
  - **Headless**: ``codex exec`` runs a single session to completion,
    non-interactive, exits when done.
  - **Streaming**: ``--json`` makes stdout a JSONL event stream
    (``thread.started`` / ``turn.*`` / ``item.*`` / ``error``). Item types
    cover agent messages, reasoning, command exec, file changes, MCP tool
    calls, web searches, plan updates.
  - **Model / base_url**: ``OPENAI_BASE_URL`` env routes through our gateway.

This module normalizes both into one :class:`AgentEvent` taxonomy so the
orchestrator stays runtime-agnostic.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol, runtime_checkable


class AgentEventKind(str, enum.Enum):
    """Normalized event taxonomy across Claude + Codex wires.

    Maps onto the worker chat / run-change surfaces. Both runtimes emit a
    superset of these; the runtime adapter is responsible for the mapping.
    """

    # lifecycle
    run_started = "run_started"
    run_finished = "run_finished"
    # agent output
    agent_message = "agent_message"   # assistant text chunk
    agent_thought = "agent_thought"   # reasoning / thinking block
    agent_stdio = "agent_stdio"       # raw terminal stdio passthrough
    # tools
    tool_call = "tool_call"
    tool_result = "tool_result"
    # filesystem (drives run-change diff pane)
    file_changed = "file_changed"
    shell_output = "shell_output"
    # human-in-the-loop
    permission_request = "permission_request"  # canUseTool / approval prompt
    # terminal
    error = "error"


@dataclass(frozen=True)
class AgentEvent:
    """One normalized event off a runtime's wire."""

    kind: AgentEventKind
    payload: dict[str, Any] = field(default_factory=dict)
    # opaque per-runtime correlation id (e.g. tool_use_id / item id)
    ref: str | None = None


@dataclass
class PermissionRequest:
    """A per-step tool-permission prompt surfaced from the runtime.

    Mirrors the Claude Agent SDK ``canUseTool`` callback input and the
    inline approval the worker chat shows. The orchestrator persists this and
    waits for a :class:`PermissionDecision` answered via the HTTP API.
    """

    prompt_id: str
    tool_name: str
    # tool input the model proposed (path, command, args…)
    tool_input: dict[str, Any] = field(default_factory=dict)
    # human-readable summary for the chat UI
    summary: str = ""


@dataclass
class PermissionDecision:
    """Host answer to a :class:`PermissionRequest`."""

    prompt_id: str
    # "allow" | "deny"
    decision: str
    # optional updated tool_input (SDK allows editing before allow)
    updated_input: dict[str, Any] | None = None
    reason: str | None = None


@dataclass
class AgentRuntimeConfig:
    """Everything a runtime needs to drive the agent in the sandbox.

    ``gateway_base_url`` is the crux of the no-fake-providers directive: the
    in-sandbox agent's LLM calls are pointed at our gateway via the runtime's
    provider env var (``ANTHROPIC_BASE_URL`` / ``OPENAI_BASE_URL``), so keys +
    routing + audit + cost all live at the gateway. The agent never holds a
    raw provider key.
    """

    model: str
    # gateway base_url injected as ANTHROPIC_BASE_URL / OPENAI_BASE_URL in VM
    gateway_base_url: str
    # repo working dir inside the sandbox
    workdir: str = "/workspace/repo"
    # skill names to inject (resolved by workers.skills before launch)
    skills: list[str] = field(default_factory=list)
    # permission mode: default | acceptEdits | plan | dontAsk | bypassPermissions
    permission_mode: str = "default"
    # extra env (secrets injected by workers.secrets; never logged)
    env: dict[str, str] = field(default_factory=dict)
    # repo-convention files to load (CLAUDE.md / AGENTS.md) — paths in workdir
    convention_files: list[str] = field(default_factory=list)


# Callback the runtime invokes to ask the host for a permission decision.
# The host (orchestrator) returns the decision once the user answers in chat.
PermissionResponder = Callable[[PermissionRequest], Awaitable[PermissionDecision]]


@runtime_checkable
class AgentRuntime(Protocol):
    """Contract every agent runtime (claude | codex) must satisfy.

    Pairs with the in-sandbox runner (:mod:`ai_portal.workers.agent_runtime.\
in_sandbox_runner`): this server-side adapter speaks the runner's wire
    protocol; the runner drives the actual CLI in the VM.
    """

    name: str

    async def start(
        self,
        sandbox: Any,
        config: AgentRuntimeConfig,
        *,
        on_permission: PermissionResponder | None = None,
    ) -> None:
        """Bootstrap the agent CLI in the sandbox (install + launch).

        TODO(agent-sdk-boundary): real CLI install + launch lives here.
        """
        ...

    def send_message(self, text: str) -> AsyncIterator[AgentEvent]:
        """Send one user message; stream normalized events for that run.

        One call == one run (user-message → agent-work cycle).
        """
        ...

    async def interrupt(self) -> None:
        """Interrupt the current run (stop & redirect)."""
        ...

    async def stop(self) -> None:
        """Stop the agent process + release the runtime (not the sandbox)."""
        ...
