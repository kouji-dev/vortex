"""File tools — read_file, write_file, edit_file.

Each tool emits ``file_changed`` events with before/after sha256 so downstream
listeners (audit, UI diff viewer) can correlate without holding plaintext.
"""

from __future__ import annotations

import difflib
import hashlib

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def _try_read(ctx: ToolContext, path: str) -> bytes | None:
    try:
        return await ctx.sandbox_provider.read_file(ctx.sandbox, path)
    except Exception:
        return None


class ReadFileTool:
    name = "read_file"
    schema = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args["path"]
        await ctx.emit_event(
            EventKind.tool_call, {"tool": "read_file", "path": path}
        )
        try:
            data = await ctx.sandbox_provider.read_file(ctx.sandbox, path)
        except Exception as e:
            return ToolResult(ok=False, error=str(e))
        return ToolResult(
            ok=True,
            output={
                "path": path,
                "size": len(data),
                "content": data.decode("utf-8", errors="replace"),
                "sha256": _sha256(data),
            },
        )


class WriteFileTool:
    name = "write_file"
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args["path"]
        new_data = args["content"].encode("utf-8")

        await ctx.emit_event(
            EventKind.tool_call, {"tool": "write_file", "path": path}
        )

        before = await _try_read(ctx, path)
        before_sha = _sha256(before) if before is not None else None
        after_sha = _sha256(new_data)

        await ctx.sandbox_provider.write_file(ctx.sandbox, path, new_data)

        await ctx.emit_event(
            EventKind.file_changed,
            {
                "path": path,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "size": len(new_data),
            },
        )

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.write_file",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "path": path,
                        "before_sha256": before_sha,
                        "after_sha256": after_sha,
                    },
                }
            )

        return ToolResult(
            ok=True,
            output={
                "path": path,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
            },
        )


def _apply_unified_diff(original: str, diff_text: str) -> str:
    """Naive unified-diff applier — supports add/remove of contiguous lines.

    We do not bring a full patch engine in here; for v1 the agent uses
    ``find_replace`` semantics (see ``find``/``replace`` args). Falls back to
    treating the diff as a full replacement when ``find`` is given.
    """
    # If find/replace mode was used by the caller, just do a literal replace.
    raise NotImplementedError("unified diff not supported in v1")


class EditFileTool:
    """Find/replace edit. Pass ``find`` + ``replace`` strings."""

    name = "edit_file"
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "find": {"type": "string"},
            "replace": {"type": "string"},
        },
        "required": ["path", "find", "replace"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        path = args["path"]
        find_s = args["find"]
        repl_s = args["replace"]

        await ctx.emit_event(
            EventKind.tool_call, {"tool": "edit_file", "path": path}
        )

        try:
            before = await ctx.sandbox_provider.read_file(ctx.sandbox, path)
        except Exception as e:
            return ToolResult(ok=False, error=f"read failed: {e}")

        before_text = before.decode("utf-8", errors="replace")
        if find_s not in before_text:
            return ToolResult(
                ok=False, error="find string not present in file"
            )

        after_text = before_text.replace(find_s, repl_s, 1)
        after_data = after_text.encode("utf-8")

        before_sha = _sha256(before)
        after_sha = _sha256(after_data)

        await ctx.sandbox_provider.write_file(ctx.sandbox, path, after_data)

        diff_lines = list(
            difflib.unified_diff(
                before_text.splitlines(keepends=True),
                after_text.splitlines(keepends=True),
                fromfile=path,
                tofile=path,
                n=2,
            )
        )

        await ctx.emit_event(
            EventKind.file_changed,
            {
                "path": path,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "diff": "".join(diff_lines),
            },
        )

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.edit_file",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "path": path,
                        "before_sha256": before_sha,
                        "after_sha256": after_sha,
                    },
                }
            )

        return ToolResult(
            ok=True,
            output={
                "path": path,
                "before_sha256": before_sha,
                "after_sha256": after_sha,
                "diff": "".join(diff_lines),
            },
        )
