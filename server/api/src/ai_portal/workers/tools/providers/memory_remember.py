"""Memory remember tool — write a repo-scoped fact.

The agent calls this to persist a discovered fact (test command, build
command, repo convention, etc.) for the next worker run in the same
repo. We tag every write with ``worker`` + ``repo:<repo_id>`` so the
provenance is visible in the memories UI.

Worker scope maps to the memory module's existing ``ScopeKind.assistant``
with ``scope_ids = [repo_id]``. This avoids a DB enum change while still
giving repo-level isolation.
"""

from __future__ import annotations

from ai_portal.workers.tools.protocol import Tool, ToolContext, ToolResult
from ai_portal.workers.types import EventKind


def _build_memory_service(session):
    from ai_portal.memory.service import MemoryService  # noqa: PLC0415

    return MemoryService(session)


class MemoryRememberTool:
    """Persist a worker-scoped memory."""

    name = "memory_remember"
    schema = {
        "type": "object",
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 240},
            "type": {
                "type": "string",
                "enum": [
                    "fact",
                    "preference",
                    "intent",
                    "skill",
                    "todo",
                    "entity",
                    "summary",
                ],
                "default": "fact",
            },
            "importance": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.6,
            },
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["text"],
    }

    async def invoke(self, args: dict, ctx: ToolContext) -> ToolResult:
        text = args["text"]
        mem_type = args.get("type", "fact")
        importance = float(args.get("importance", 0.6))
        extra_tags = list(args.get("tags") or [])

        await ctx.emit_event(
            EventKind.tool_call,
            {"tool": "memory_remember", "type": mem_type},
        )

        settings = ctx.pool_settings or {}
        session = settings.get("memory_session")
        if session is None:
            return ToolResult(
                ok=False, error="memory_session not bound on worker context"
            )

        repo_id = settings.get("repo_id") or "unknown"
        org_id = settings.get("memory_org_id") or ctx.org_id
        actor_user_id = settings.get("memory_actor_user_id")
        if actor_user_id is None:
            try:
                actor_user_id = int(ctx.actor_id)
            except (TypeError, ValueError):
                actor_user_id = 0

        tags = list(extra_tags)
        if "worker" not in tags:
            tags.append("worker")
        repo_tag = f"repo:{repo_id}"
        if repo_tag not in tags:
            tags.append(repo_tag)

        svc = _build_memory_service(session)
        try:
            stored = await svc.add_manual(
                org_id=org_id,
                actor_user_id=actor_user_id,
                type=mem_type,
                text=text,
                scope_kind="assistant",
                scope_ids=[str(repo_id)],
                importance=importance,
                confidence=0.85,
                tags=tags,
            )
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"remember failed: {e}")

        mid = str(getattr(stored, "id", ""))

        if ctx.audit is not None:
            await ctx.audit(
                {
                    "action": "worker.memory_remember",
                    "resource_type": "worker_run",
                    "resource_id": ctx.run_id,
                    "payload": {
                        "memory_id": mid,
                        "repo_id": str(repo_id),
                        "type": mem_type,
                    },
                }
            )

        return ToolResult(
            ok=True,
            output={"memory_id": mid, "type": mem_type, "tags": tags},
        )


_: Tool = MemoryRememberTool()
