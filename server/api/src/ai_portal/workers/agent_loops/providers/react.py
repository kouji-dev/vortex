"""ReAct agent loop — Plan → Act → Observe → Reflect.

Single-tool-per-step loop driven by an LLM through the gateway facade.
Each iteration:
1. Prompt the gateway with the current message stack + available tools.
2. If the response carries a ``tool_call``, invoke that tool, append the
   result to the message stack, emit ``tool_call`` + ``tool_result`` events.
3. Otherwise treat the response as the agent's thought / final answer and
   exit the loop.

Stops on:
- explicit ``final:`` text or ``stop_reason == "end_turn"``
- exhausting ``ctx.max_iterations``

Loop is provider-agnostic: ``ctx.gateway`` only needs an async
``complete(req)`` method returning an object with ``tool_calls`` and
``content`` attributes. Production wires this to
:func:`ai_portal.gateway.facade.complete`.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, AsyncIterator

from ai_portal.workers.agent_loops.protocol import (
    AgentRunCtx,
    Phase,
    ReflectDecision,
)
from ai_portal.workers.tools.protocol import ToolContext
from ai_portal.workers.types import EventKind, WorkerEvent


_SYSTEM_BASE = (
    "Engineer agent.\n"
    "- Plan briefly. Act with tools. Verify (tests/lint).\n"
    "- One tool per step. Reason in <thought>. Stop when task done.\n"
    "- Never push to main. Never write secrets.\n"
    "- Conventional commits: type(scope): subject.\n"
)


def _now() -> datetime:
    return datetime.now()


def _build_tool_ctx(ctx: AgentRunCtx, events: list[WorkerEvent]) -> ToolContext:
    """Construct a ToolContext that pipes events into the loop's queue."""

    async def _emit(kind: Any, payload: dict) -> None:
        events.append(
            WorkerEvent(run_id=ctx.run.id, kind=kind, payload=payload, ts=_now())
        )

    return ToolContext(
        sandbox=ctx.sandbox,
        sandbox_provider=ctx.sandbox_provider,
        task_id=getattr(ctx.task, "id", "task-?"),
        run_id=getattr(ctx.run, "id", "run-?"),
        actor_id=getattr(ctx.task, "created_by", "actor-?"),
        org_id=getattr(ctx.task, "org_id", "org-?"),
        emit_event=_emit,
        repo=ctx.repo,
    )


class ReactLoop:
    """Plan → Act → Observe → Reflect loop."""

    name = "react"

    def __init__(
        self,
        *,
        repo_instructions: str = "",
        system_extra: str = "",
    ) -> None:
        self._repo_instructions = repo_instructions
        self._system_extra = system_extra

    def _system_prompt(self) -> str:
        parts = [_SYSTEM_BASE.rstrip()]
        if self._system_extra:
            parts.append(self._system_extra.strip())
        if self._repo_instructions:
            parts.append("Repo conventions:\n" + self._repo_instructions.strip())
        return "\n\n".join(parts)

    async def run(self, ctx: AgentRunCtx) -> AsyncIterator[WorkerEvent]:
        tools_by_name = {t.name: t for t in ctx.tools}
        messages: list[dict] = [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": f"{getattr(ctx.task, 'title', '')}\n\n"
                f"{getattr(ctx.task, 'description', '')}",
            },
        ]
        tool_specs = [{"name": t.name, "schema": t.schema} for t in ctx.tools]

        for _ in range(ctx.max_iterations):
            req = {
                "model": ctx.model,
                "messages": messages,
                "tools": tool_specs,
            }
            resp = await ctx.gateway.complete(req)

            tool_calls = list(getattr(resp, "tool_calls", []) or [])
            content = getattr(resp, "content", "") or ""
            stop_reason = getattr(resp, "stop_reason", "")

            if tool_calls:
                tc = tool_calls[0]
                tc_name = getattr(tc, "name", None) or tc["name"]
                tc_args = getattr(tc, "arguments", None)
                if tc_args is None:
                    tc_args = tc.get("arguments", {})
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
                            "content": json.dumps(
                                {"error": f"unknown tool {tc_name}"}
                            ),
                        }
                    )
                    continue

                inner_events: list[WorkerEvent] = []
                tool_ctx = _build_tool_ctx(ctx, inner_events)
                result = await tool.invoke(tc_args, tool_ctx)
                for ev in inner_events:
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

                # Reflect: decide retry / escalate / done before next iter.
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

            # No tool call → treat as thought / final
            yield WorkerEvent(
                run_id=ctx.run.id,
                kind=EventKind.agent_thought,
                payload={"text": content},
                ts=_now(),
            )
            if stop_reason == "end_turn" or "final" in content.lower():
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
