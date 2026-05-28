"""Verify tool — run the repo's test/lint/typecheck/build commands in order.

Reads ``ctx.pool_settings["verify"]`` for the per-check command map::

    pool_settings = {
        "verify": {
            "test": ["pnpm", "test"],
            "lint": ["pnpm", "lint"],
            "typecheck": ["pnpm", "tsc", "--noEmit"],
            "build": ["pnpm", "build"],
        }
    }

Run order is fixed: ``test → lint → typecheck → build``. If a check has
no command it is skipped. By default the tool stops at the first
failure; pass ``{"continue_on_error": true}`` to run every step. Pass
``{"only": ["test", "lint"]}`` to subset.

This is the agent's "verify phase" — call it after edits and before
opening a PR.
"""

from __future__ import annotations

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


_VERIFY_ORDER: tuple[str, ...] = ("test", "lint", "typecheck", "build")


class VerifyTool:
    """Run the repo's verify pipeline."""

    name = "verify"
    schema = {
        "type": "object",
        "properties": {
            "only": {"type": "array", "items": {"type": "string"}},
            "continue_on_error": {"type": "boolean", "default": False},
            "timeout_sec": {"type": "integer", "default": 1800},
        },
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        verify_cfg: dict[str, list[str]] = (
            ctx.pool_settings.get("verify", {}) or {}
        )
        only: list[str] | None = args.get("only")
        continue_on_error = bool(args.get("continue_on_error", False))
        timeout = int(args.get("timeout_sec", 1800))

        steps_to_run = [
            s for s in _VERIFY_ORDER if (only is None or s in only)
        ]

        await ctx.emit_event(
            EventKind.tool_call,
            {"tool": "verify", "steps": steps_to_run},
        )

        steps_report: list[dict] = []
        all_ok = True

        for step in steps_to_run:
            cmd = verify_cfg.get(step)
            if not cmd:
                continue

            r = await ctx.sandbox_provider.exec(
                ctx.sandbox, list(cmd), timeout_sec=timeout
            )
            step_ok = r.exit_code == 0
            steps_report.append(
                {
                    "name": step,
                    "cmd": list(cmd),
                    "ok": step_ok,
                    "exit_code": r.exit_code,
                    "stdout": r.stdout,
                    "stderr": r.stderr,
                }
            )
            if not step_ok:
                all_ok = False
                if not continue_on_error:
                    break

        return ToolResult(
            ok=all_ok,
            output={"steps": steps_report},
        )
