"""Code search tool — ripgrep + ast-grep front-end.

Both engines are expected to be preinstalled in the sandbox image (see
``workers/sandboxes/templates.py``). This tool just shells out and parses
the JSON output. For tests we stub the exec result with the fake sandbox's
``scripts`` map.
"""

from __future__ import annotations

import json

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


class CodeSearchTool:
    """Search the sandbox workspace for a pattern."""

    name = "code_search"
    schema = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "engine": {
                "type": "string",
                "enum": ["ripgrep", "ast-grep"],
                "default": "ripgrep",
            },
            "path": {"type": "string", "default": "."},
            "globs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["pattern"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        pattern = args["pattern"]
        engine = args.get("engine", "ripgrep")
        path = args.get("path", ".")
        globs = args.get("globs") or []

        if engine == "ripgrep":
            cmd: list[str] = ["rg", "--json", pattern, path]
            for g in globs:
                cmd.extend(["-g", g])
        elif engine == "ast-grep":
            cmd = ["ast-grep", "--json", "--pattern", pattern, path]
        else:
            return ToolResult(ok=False, error=f"unknown engine: {engine}")

        await ctx.emit_event(
            EventKind.tool_call,
            {"tool": "code_search", "engine": engine, "pattern": pattern},
        )

        r = await ctx.sandbox_provider.exec(ctx.sandbox, cmd, timeout_sec=120)
        if r.exit_code not in (0, 1):
            # rg returns 1 on no-match; treat that as ok with empty matches.
            return ToolResult(
                ok=False,
                error=r.stderr or f"exit {r.exit_code}",
                output={"exit_code": r.exit_code},
            )

        matches: list[dict] = []
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if engine == "ripgrep" and rec.get("type") == "match":
                d = rec.get("data", {})
                matches.append(
                    {
                        "path": d.get("path", {}).get("text"),
                        "line": d.get("line_number"),
                        "text": d.get("lines", {}).get("text", "").rstrip("\n"),
                    }
                )
            elif engine == "ast-grep":
                matches.append(rec)

        return ToolResult(
            ok=True,
            output={
                "engine": engine,
                "pattern": pattern,
                "count": len(matches),
                "matches": matches,
            },
        )
