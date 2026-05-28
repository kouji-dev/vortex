"""OpenHands-style CodeAct loop — code execution as the action.

Inspired by the OpenHands / CodeAct pattern: the model expresses every
action as an executable code block (``python`` / ``bash``) which the loop
extracts and dispatches to the matching tool.

Action dispatch priority per turn:
1. Native ``tool_calls`` on the response (same path as ReAct).
2. First fenced ``python`` block → ``python_exec`` tool (args: ``{code}``).
3. First fenced ``bash`` / ``sh`` / ``shell`` block →
   ``shell`` tool (args: ``{cmd: ["bash", "-lc", <code>]}``).
4. ``<finish>`` marker or ``stop_reason == "end_turn"`` → stop.
5. Otherwise emit thought and continue.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import AsyncIterator

from ai_portal.workers.agent_loops.protocol import (
    AgentRunCtx,
    Phase,
    ReflectDecision,
)
from ai_portal.workers.agent_loops.providers.react import _build_tool_ctx
from ai_portal.workers.types import EventKind, WorkerEvent


_SYSTEM = (
    "CodeAct agent.\n"
    "- Express every action as a fenced code block.\n"
    "- Use ```python``` for compute / file edits via python.\n"
    "- Use ```bash``` for shell commands.\n"
    "- Emit `<finish>` when done. One action per turn.\n"
    "- Never push to main. Never write secrets.\n"
)

_PY_RE = re.compile(r"```python\s*\n(.*?)```", re.DOTALL)
_SH_RE = re.compile(r"```(?:bash|sh|shell)\s*\n(.*?)```", re.DOTALL)


def _now() -> datetime:
    return datetime.now()


def _extract_action(text: str) -> tuple[str, dict] | None:
    """Return ``(tool_name, args)`` for the first action block found."""
    m = _PY_RE.search(text)
    if m:
        return "python_exec", {"code": m.group(1).rstrip()}
    m = _SH_RE.search(text)
    if m:
        code = m.group(1).strip()
        return "shell", {"cmd": ["bash", "-lc", code]}
    return None


class OpenHandsStyleLoop:
    """CodeAct-style loop — code blocks are actions."""

    name = "openhands_style"

    def __init__(self, *, repo_instructions: str = "") -> None:
        self._repo_instructions = repo_instructions

    def _system(self) -> str:
        if self._repo_instructions:
            return _SYSTEM + "\nRepo conventions:\n" + self._repo_instructions.strip()
        return _SYSTEM

    async def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]:
        tools_by_name = {t.name: t for t in ctx.tools}
        messages: list[dict] = [
            {"role": "system", "content": self._system()},
            {
                "role": "user",
                "content": f"{getattr(ctx.task, 'title', '')}\n\n"
                f"{getattr(ctx.task, 'description', '')}",
            },
        ]
        tool_specs = [{"name": t.name, "schema": t.schema} for t in ctx.tools]

        for _ in range(ctx.max_iterations):
            resp = await ctx.gateway.complete(
                {"model": ctx.model, "messages": messages, "tools": tool_specs}
            )
            tool_calls = list(getattr(resp, "tool_calls", []) or [])
            content = getattr(resp, "content", "") or ""
            stop_reason = getattr(resp, "stop_reason", "")

            # 1. Native tool call wins.
            if tool_calls:
                tc = tool_calls[0]
                tc_name = getattr(tc, "name", None) or tc["name"]
                tc_args = getattr(tc, "arguments", None) or tc.get("arguments", {})
                tc_reason = getattr(tc, "reasoning", "") or ""
                async for ev in self._dispatch(
                    ctx, tools_by_name, tc_name, tc_args, tc_reason, messages
                ):
                    yield ev
                continue

            # 2. Code-block action.
            action = _extract_action(content)
            if action is not None:
                tool_name, args = action
                # Emit thought = the surrounding prose minus the block.
                prose = (
                    _PY_RE.sub("", _SH_RE.sub("", content)).strip()
                    or "(action)"
                )
                yield WorkerEvent(
                    run_id=ctx.run.id,
                    kind=EventKind.agent_thought,
                    payload={"text": prose},
                    ts=_now(),
                )
                async for ev in self._dispatch(
                    ctx, tools_by_name, tool_name, args, prose, messages
                ):
                    yield ev
                continue

            # 3. Finish.
            yield WorkerEvent(
                run_id=ctx.run.id,
                kind=EventKind.agent_thought,
                payload={"text": content},
                ts=_now(),
            )
            if "<finish>" in content or stop_reason == "end_turn":
                yield WorkerEvent(
                    run_id=ctx.run.id,
                    kind=EventKind.phase_changed,
                    payload={
                        "phase": Phase.REFLECT.value,
                        "decision": ReflectDecision.DONE.value,
                    },
                    ts=_now(),
                )
                return
            messages.append({"role": "assistant", "content": content})

    async def _dispatch(
        self,
        ctx: AgentRunCtx,
        tools_by_name: dict,
        tc_name: str,
        tc_args: dict,
        reasoning: str,
        messages: list[dict],
    ) -> AsyncIterator[WorkerEvent]:
        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.tool_call,
            payload={"tool": tc_name, "args": tc_args},
            ts=_now(),
        )
        tool = tools_by_name.get(tc_name)
        if tool is None:
            yield WorkerEvent(
                run_id=ctx.run.id,
                kind=EventKind.error,
                payload={"error": f"unknown tool {tc_name}"},
                ts=_now(),
            )
            messages.append(
                {
                    "role": "tool",
                    "name": tc_name,
                    "content": json.dumps({"error": "unknown tool"}),
                }
            )
            return
        inner: list[WorkerEvent] = []
        result = await tool.invoke(tc_args, _build_tool_ctx(ctx, inner))
        for ev in inner:
            yield ev
        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.tool_result,
            payload={
                "tool": tc_name,
                "ok": result.ok,
                "output": result.output,
                "error": result.error,
            },
            ts=_now(),
        )
        decision = ReflectDecision.RETRY if result.ok else ReflectDecision.ESCALATE
        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.phase_changed,
            payload={
                "phase": Phase.REFLECT.value,
                "decision": decision.value,
                "tool": tc_name,
                "ok": result.ok,
            },
            ts=_now(),
        )
        messages.append(
            {
                "role": "assistant",
                "content": reasoning,
                "tool_calls": [{"name": tc_name, "args": tc_args}],
            }
        )
        messages.append(
            {
                "role": "tool",
                "name": tc_name,
                "content": json.dumps(
                    {
                        "ok": result.ok,
                        "output": result.output,
                        "error": result.error,
                    },
                    default=str,
                ),
            }
        )
