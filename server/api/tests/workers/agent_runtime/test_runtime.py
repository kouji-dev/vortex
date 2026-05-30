"""Pure-logic tests for the agent_runtime abstraction.

Covers the registry, the gateway base_url env wiring (the no-fake-providers
crux), CLI-arg builders, and the Codex event-map normalization. Confirms the
real exec boundary stays an explicit ``NotImplementedError`` (no fabricated
agent output).
"""

from __future__ import annotations

import asyncio

import pytest

from ai_portal.workers.agent_runtime import (
    AgentEventKind,
    AgentRuntimeConfig,
    get_runtime,
    list_runtimes,
)
from ai_portal.workers.agent_runtime.claude import ClaudeAgentRuntime
from ai_portal.workers.agent_runtime.codex import (
    CODEX_EVENT_MAP,
    CodexAgentRuntime,
    map_codex_event,
)
from ai_portal.workers.agent_runtime.in_sandbox_runner import (
    InSandboxRunner,
    RunnerBootSpec,
    WireFrame,
    WireMsgKind,
)
from ai_portal.workers.agent_runtime.registry import UnknownRuntime


def _cfg(**kw) -> AgentRuntimeConfig:
    base = dict(model="claude-sonnet-4-6", gateway_base_url="http://gw/v1")
    base.update(kw)
    return AgentRuntimeConfig(**base)


# ── registry ─────────────────────────────────────────────────────


def test_registry_lists_bundled_runtimes() -> None:
    assert list_runtimes() == ["claude", "codex"]


def test_get_runtime_returns_instances() -> None:
    assert isinstance(get_runtime("claude"), ClaudeAgentRuntime)
    assert isinstance(get_runtime("codex"), CodexAgentRuntime)


def test_get_unknown_runtime_raises() -> None:
    with pytest.raises(UnknownRuntime):
        get_runtime("gemini-cli")


# ── gateway base_url wiring (no-fake-providers) ──────────────────


def test_claude_injects_anthropic_base_url() -> None:
    env = ClaudeAgentRuntime().build_launch_env(_cfg())
    assert env["ANTHROPIC_BASE_URL"] == "http://gw/v1"


def test_codex_injects_openai_base_url() -> None:
    env = CodexAgentRuntime().build_launch_env(_cfg())
    assert env["OPENAI_BASE_URL"] == "http://gw/v1"


def test_launch_env_preserves_extra_env() -> None:
    env = ClaudeAgentRuntime().build_launch_env(_cfg(env={"FOO": "bar"}))
    assert env["FOO"] == "bar"
    assert env["ANTHROPIC_BASE_URL"] == "http://gw/v1"


# ── cli arg builders ─────────────────────────────────────────────


def test_claude_cli_args_include_model_and_skills() -> None:
    args = ClaudeAgentRuntime().build_cli_args(
        _cfg(skills=["fix-bug", "write-tests"], permission_mode="acceptEdits")
    )
    assert args[0] == "claude"
    assert "--model" in args and "claude-sonnet-4-6" in args
    assert "--permission-mode" in args and "acceptEdits" in args
    assert args.count("--skill") == 2


def test_codex_cli_args_are_headless_json() -> None:
    args = CodexAgentRuntime().build_cli_args(_cfg(), "fix the bug")
    assert args[:3] == ["codex", "exec", "--json"]
    assert args[-1] == "fix the bug"


# ── codex event normalization ────────────────────────────────────


def test_map_codex_known_events() -> None:
    assert map_codex_event("turn.completed") is AgentEventKind.run_finished
    assert map_codex_event("item.file_change") is AgentEventKind.file_changed
    assert map_codex_event("item.agent_message") is AgentEventKind.agent_message
    assert map_codex_event("error") is AgentEventKind.error


def test_map_codex_unknown_falls_back_to_stdio() -> None:
    assert map_codex_event("item.totally_new") is AgentEventKind.agent_stdio


def test_codex_event_map_values_are_known_kinds() -> None:
    for kind in CODEX_EVENT_MAP.values():
        assert isinstance(kind, AgentEventKind)


# ── exec boundary stays stubbed (no fabricated output) ───────────


def test_claude_start_is_stubbed() -> None:
    with pytest.raises(NotImplementedError):
        asyncio.run(ClaudeAgentRuntime().start(object(), _cfg()))


def test_codex_start_is_stubbed() -> None:
    with pytest.raises(NotImplementedError):
        asyncio.run(CodexAgentRuntime().start(object(), _cfg()))


def test_in_sandbox_runner_boot_is_stubbed() -> None:
    spec = RunnerBootSpec(
        runtime="claude",
        model="claude-sonnet-4-6",
        gateway_base_url="http://gw/v1",
        repo_url="https://gitlab.com/acme/api.git",
    )
    runner = InSandboxRunner(spec)
    with pytest.raises(NotImplementedError):
        asyncio.run(runner.boot())


# ── wire protocol round-trip ─────────────────────────────────────


def test_wire_frame_encode_decode_roundtrip() -> None:
    f = WireFrame(WireMsgKind.user_message, {"text": "hi"})
    again = WireFrame.decode(f.encode())
    assert again.kind is WireMsgKind.user_message
    assert again.payload == {"text": "hi"}


def test_runner_boot_spec_serializes() -> None:
    spec = RunnerBootSpec(
        runtime="codex",
        model="gpt-x",
        gateway_base_url="http://gw/v1",
        repo_url="r",
        skills=["fix-bug"],
    )
    import json

    obj = json.loads(spec.to_json())
    assert obj["runtime"] == "codex"
    assert obj["skills"] == ["fix-bug"]
