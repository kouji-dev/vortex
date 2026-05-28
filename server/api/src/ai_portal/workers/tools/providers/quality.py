"""Quality tools — run_tests, run_build, lint, format.

Each tool consults ``ctx.pool_settings`` for the repo-specific command and
falls back to a template default if missing. Captures exit code + truncated
stdout/stderr.
"""

from __future__ import annotations

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


_DEFAULT_COMMANDS: dict[str, dict[str, list[str]]] = {
    "run_tests": {
        "python": ["pytest", "-x"],
        "node": ["pnpm", "test"],
        "go": ["go", "test", "./..."],
        "rust": ["cargo", "test"],
    },
    "run_build": {
        "python": ["python", "-m", "build"],
        "node": ["pnpm", "build"],
        "go": ["go", "build", "./..."],
        "rust": ["cargo", "build"],
    },
    "lint": {
        "python": ["ruff", "check", "."],
        "node": ["pnpm", "lint"],
        "go": ["golangci-lint", "run"],
        "rust": ["cargo", "clippy", "--", "-D", "warnings"],
    },
    "format": {
        "python": ["ruff", "format", "."],
        "node": ["pnpm", "format"],
        "go": ["gofmt", "-w", "."],
        "rust": ["cargo", "fmt"],
    },
}


def _resolve_cmd(
    tool_name: str, pool_settings: dict, template: str | None
) -> list[str] | None:
    """Look up the command for ``tool_name``.

    Priority: pool_settings["commands"][tool_name] > template default > None.
    """
    cmd = pool_settings.get("commands", {}).get(tool_name)
    if cmd:
        return list(cmd)
    if template and tool_name in _DEFAULT_COMMANDS:
        return list(_DEFAULT_COMMANDS[tool_name].get(template, []) or []) or None
    return None


class _QualityRunner:
    """Base class for run_tests / run_build / lint / format."""

    name: str = ""
    schema: dict = {}

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        template = ctx.pool_settings.get("template")
        cmd = args.get("cmd")
        if not cmd:
            cmd = _resolve_cmd(self.name, ctx.pool_settings, template)
        if not cmd:
            return ToolResult(
                ok=False,
                error=f"no command configured for {self.name}",
            )

        await ctx.emit_event(
            EventKind.tool_call, {"tool": self.name, "cmd": list(cmd)}
        )

        timeout = int(args.get("timeout_sec", 1800))
        r = await ctx.sandbox_provider.exec(
            ctx.sandbox, list(cmd), timeout_sec=timeout
        )
        return ToolResult(
            ok=r.exit_code == 0,
            output={
                "cmd": list(cmd),
                "exit_code": r.exit_code,
                "stdout": r.stdout,
                "stderr": r.stderr,
            },
        )


class RunTestsTool(_QualityRunner):
    name = "run_tests"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "timeout_sec": {"type": "integer", "default": 1800},
        },
    }


class RunBuildTool(_QualityRunner):
    name = "run_build"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "timeout_sec": {"type": "integer", "default": 1800},
        },
    }


class LintTool(_QualityRunner):
    name = "lint"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "timeout_sec": {"type": "integer", "default": 600},
        },
    }


class FormatTool(_QualityRunner):
    name = "format"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "timeout_sec": {"type": "integer", "default": 600},
        },
    }
