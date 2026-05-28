"""Shell tool — run a command in the sandbox, stream output, audit hashes.

Streams chunks via ``ctx.emit_event(EventKind.shell_output, ...)``. Redacts
known secret values before streaming. Emits a final audit row with sha256s
of cmd, stdout, stderr.
"""

from __future__ import annotations

import hashlib

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


class ShellTool:
    """Run a shell command inside the sandbox."""

    name = "shell"
    schema = {
        "type": "object",
        "properties": {
            "cmd": {"type": "array", "items": {"type": "string"}},
            "cwd": {"type": "string"},
            "timeout_sec": {"type": "integer", "default": 600},
        },
        "required": ["cmd"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        cmd = list(args["cmd"])
        cwd = args.get("cwd")
        timeout = int(args.get("timeout_sec", 600))

        await ctx.emit_event(EventKind.tool_call, {"tool": "shell", "cmd": cmd})

        out_buf: list[str] = []
        err_buf: list[str] = []

        def _redact(s: str) -> str:
            if ctx.secrets_proxy is not None and hasattr(ctx.secrets_proxy, "redact"):
                return ctx.secrets_proxy.redact(s)
            return s

        async for stream, chunk in ctx.sandbox_provider.stream_exec(
            ctx.sandbox, cmd, cwd=cwd, timeout_sec=timeout
        ):
            chunk = _redact(chunk)
            if stream == "stdout":
                out_buf.append(chunk)
            else:
                err_buf.append(chunk)
            await ctx.emit_event(
                EventKind.shell_output, {"stream": stream, "chunk": chunk}
            )

        stdout = "".join(out_buf)
        stderr = "".join(err_buf)

        # Final exec to obtain exit code (stream_exec on most providers doesn't
        # expose it). Fake/Docker streamers replay last result.
        result = await ctx.sandbox_provider.exec(
            ctx.sandbox, cmd, cwd=cwd, timeout_sec=timeout
        )

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.shell",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "cmd_sha256": _sha256(" ".join(cmd)),
                        "stdout_sha256": _sha256(stdout),
                        "stderr_sha256": _sha256(stderr),
                        "exit_code": result.exit_code,
                    },
                }
            )

        return ToolResult(
            ok=result.exit_code == 0,
            output={
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": result.exit_code,
            },
        )
