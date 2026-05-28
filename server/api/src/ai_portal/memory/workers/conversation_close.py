"""Conversation-close summarization worker.

Drains queued ``MemoryJob`` rows of kind=``conversation_close`` and runs the
batched extractor over the full transcript captured in the payload. Mirrors
``scheduled_extractor.run_once`` so the two triggers behave identically once
on the worker side.
"""
from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory import jobs as _jobs
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn
from ai_portal.memory.service import MemoryService

logger = logging.getLogger(__name__)


async def run_once(session: AsyncSession, *, max_jobs: int = 50) -> int:
    """Drain up to ``max_jobs`` queued conversation_close jobs.

    Returns the number of jobs processed (success + failure).
    """
    processed = 0
    for _ in range(max_jobs):
        job = await _jobs.claim_next(session, kind="conversation_close")
        if job is None:
            break
        try:
            payload = job.payload_json or {}
            turns_raw = payload.get("turns") or []
            turns = [
                Turn(
                    role=t.get("role", "user"),
                    content=t.get("content", ""),
                    turn_id=t.get("turn_id") or str(t.get("id") or ""),
                    ts=float(t.get("ts") or 0.0),
                )
                for t in turns_raw
            ]
            scope = ExtractScope(
                org_id=str(job.org_id),
                actor_user_id=str(payload.get("actor_user_id") or ""),
                scope_kind=job.scope_kind.value,
                scope_id=str(payload.get("scope_id") or ""),
                conversation_id=payload.get("conversation_id"),
                assistant_id=payload.get("assistant_id"),
            )
            opts = ExtractOpts(model=payload.get("model") or "claude-sonnet-4-6")
            svc = MemoryService(session)
            await svc.extract(turns, scope, opts)
            await _jobs.finish(session, job.id, status="done")
        except Exception as e:  # pragma: no cover - exercised via mocks
            logger.exception("memory.conversation_close.failed")
            await _jobs.finish(session, job.id, status="error", error=str(e)[:2000])
        processed += 1
    return processed


__all__ = ["run_once"]
