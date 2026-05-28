"""Plan-and-Execute agent loop.

Two-stage variant of ReAct:
1. Planner: single gateway call asks the model to produce a numbered plan
   (no tool calls). Plan is emitted as ``agent_thought`` and stored in
   message history.
2. Executor: reuses ReAct-style tool dispatch over the remaining
   iterations.

Cleaner separation than pure ReAct when a task benefits from up-front
decomposition (e.g. multi-file refactor). Falls back to executor-only
behaviour if the planner returns nothing useful.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import AsyncIterator

from ai_portal.workers.agent_loops.protocol import (
    AgentRunCtx,
    Phase,
    ReflectDecision,
)
from ai_portal.workers.agent_loops.providers.react import _build_tool_ctx
from ai_portal.workers.types import EventKind, WorkerEvent


_PLANNER_SYSTEM = (
    "Planner.\n"
    "- Produce numbered plan. One step per line. No tool calls.\n"
    "- Steps must be executable by an engineer agent with shell + edit tools.\n"
    "- Stop after listing steps.\n"
)

_EXECUTOR_SYSTEM = (
    "Executor.\n"
    "- Follow the plan. One tool per step.\n"
    "- Verify with tests/lint at end.\n"
    "- Stop when plan complete.\n"
)


def _now() -> datetime:
    return datetime.now()


class PlanAndExecuteLoop:
    """Planner → Executor."""

    name = "plan_and_execute"

    def __init__(
        self,
        *,
        repo_instructions: str = "",
    ) -> None:
        self._repo_instructions = repo_instructions

    def _planner_prompt(self) -> str:
        if self._repo_instructions:
            return (
                _PLANNER_SYSTEM
                + "\nRepo conventions:\n"
                + self._repo_instructions.strip()
            )
        return _PLANNER_SYSTEM

    def _executor_prompt(self) -> str:
        if self._repo_instructions:
            return (
                _EXECUTOR_SYSTEM
                + "\nRepo conventions:\n"
                + self._repo_instructions.strip()
            )
        return _EXECUTOR_SYSTEM

    async def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]:
        tools_by_name = {t.name: t for t in ctx.tools}
        tool_specs = [{"name": t.name, "schema": t.schema} for t in ctx.tools]

        # ── PLAN ─────────────────────────────────────────────────────────
        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.phase_changed,
            payload={"phase": "planning"},
            ts=_now(),
        )
        plan_req = {
            "model": ctx.model,
            "messages": [
                {"role": "system", "content": self._planner_prompt()},
                {
                    "role": "user",
                    "content": f"{getattr(ctx.task, 'title', '')}\n\n"
                    f"{getattr(ctx.task, 'description', '')}",
                },
            ],
            "tools": [],
        }
        plan_resp = await ctx.gateway.complete(plan_req)
        plan_text = (getattr(plan_resp, "content", "") or "").strip()

        if not plan_text:
            yield WorkerEvent(
                run_id=ctx.run.id,
                kind=EventKind.error,
                payload={"error": "planner returned empty plan"},
                ts=_now(),
            )
            return

        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.agent_thought,
            payload={"text": plan_text},
            ts=_now(),
        )

        # ── EXECUTE ──────────────────────────────────────────────────────
        yield WorkerEvent(
            run_id=ctx.run.id,
            kind=EventKind.phase_changed,
            payload={"phase": "executing"},
            ts=_now(),
        )

        messages: list[dict] = [
            {"role": "system", "content": self._executor_prompt()},
            {
                "role": "user",
                "content": f"Task: {getattr(ctx.task, 'title', '')}\n\n"
                f"Plan:\n{plan_text}\n\nExecute step by step.",
            },
        ]

        remaining = max(1, ctx.max_iterations - 1)
        for _ in range(remaining):
            resp = await ctx.gateway.complete(
                {"model": ctx.model, "messages": messages, "tools": tool_specs}
            )
            tool_calls = list(getattr(resp, "tool_calls", []) or [])
            content = getattr(resp, "content", "") or ""
            stop_reason = getattr(resp, "stop_reason", "")

            if tool_calls:
                tc = tool_calls[0]
                tc_name = getattr(tc, "name", None) or tc["name"]
                tc_args = getattr(tc, "arguments", None) or tc.get("arguments", {})
                tc_reason = getattr(tc, "reasoning", "") or ""

                if tc_reason:
                    yield WorkerEvent(
                        run_id=ctx.run.id,
                        kind=EventKind.agent_thought,
                        payload={"text": tc_reason},
                        ts=_now(),
                    )
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
                    continue

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
                decision = (
                    ReflectDecision.RETRY if result.ok else ReflectDecision.ESCALATE
                )
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
                        "content": tc_reason,
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
                continue

            yield WorkerEvent(
                run_id=ctx.run.id,
                kind=EventKind.agent_thought,
                payload={"text": content},
                ts=_now(),
            )
            if stop_reason == "end_turn" or "done" in content.lower():
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
