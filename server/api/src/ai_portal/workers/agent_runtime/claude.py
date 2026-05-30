"""Claude Agent SDK runtime — interface only (real exec STUBBED).

Drives the Claude Agent SDK / `claude` CLI inside the worker sandbox in
**streaming input mode**:

- Feed an async generator of user messages; consume the assistant / tool_use /
  tool_result / result stream.
- ``canUseTool`` callback → surfaced as a :class:`PermissionRequest`; the host
  answers allow/deny (the inline per-step prompt in worker chat).
- Skills loaded from the sandbox filesystem (``setting_sources`` + ``Skill``
  tool); convention files (``CLAUDE.md``) loaded as context.
- LLM calls routed through our gateway via ``ANTHROPIC_BASE_URL`` in the VM.

NOTHING here fabricates agent output. Every method that would touch the real
CLI raises ``NotImplementedError`` at the TODO boundary.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ai_portal.workers.agent_runtime.protocol import (
    AgentEvent,
    AgentRuntimeConfig,
    PermissionResponder,
)


class ClaudeAgentRuntime:
    """Claude Agent SDK runtime adapter (interface only)."""

    name = "claude"
    # provider env var the gateway base_url is injected into inside the sandbox
    base_url_env = "ANTHROPIC_BASE_URL"

    def __init__(self) -> None:
        self._config: AgentRuntimeConfig | None = None
        self._on_permission: PermissionResponder | None = None
        self._started = False

    def build_launch_env(self, config: AgentRuntimeConfig) -> dict[str, str]:
        """Compose the sandbox env that points the CLI at our gateway.

        Pure + testable: no process side effects. This is the concrete wiring
        of the no-fake-providers directive — the agent's Anthropic calls hit
        the gateway base_url, never a raw provider endpoint.
        """
        env = dict(config.env)
        env[self.base_url_env] = config.gateway_base_url
        # The agent authenticates to the gateway, not Anthropic directly; the
        # gateway holds real provider credentials. A per-worker gateway token
        # is injected by the secrets layer as ANTHROPIC_API_KEY in the VM.
        return env

    def build_cli_args(self, config: AgentRuntimeConfig) -> list[str]:
        """Compose the headless `claude` CLI invocation (pure)."""
        args = ["claude", "--model", config.model, "--permission-mode", config.permission_mode]
        for skill in config.skills:
            args += ["--skill", skill]
        return args

    async def start(
        self,
        sandbox: Any,
        config: AgentRuntimeConfig,
        *,
        on_permission: PermissionResponder | None = None,
    ) -> None:
        self._config = config
        self._on_permission = on_permission
        # TODO(agent-sdk-boundary): install + launch the Claude Agent SDK / CLI
        # inside `sandbox` (via the in-sandbox runner), wiring build_launch_env
        # + build_cli_args. Establish the bidirectional control channel. Until
        # real sandbox provisioning + the runner exist this cannot run.
        raise NotImplementedError(
            "Claude Agent SDK exec is stubbed — needs real sandbox + in-sandbox "
            "runner. See agent_runtime/in_sandbox_runner.py."
        )

    def send_message(self, text: str) -> AsyncIterator[AgentEvent]:
        # TODO(agent-sdk-boundary): yield text via the streaming-input async
        # generator; translate the SDK message stream (assistant / tool_use /
        # tool_result / result) + canUseTool prompts into AgentEvent.
        raise NotImplementedError("Claude runtime streaming is stubbed.")

    async def interrupt(self) -> None:
        # TODO(agent-sdk-boundary): call the SDK interrupt on the live query.
        raise NotImplementedError("Claude runtime interrupt is stubbed.")

    async def stop(self) -> None:
        self._started = False
        # TODO(agent-sdk-boundary): close the streaming session / kill the CLI.
        raise NotImplementedError("Claude runtime stop is stubbed.")
