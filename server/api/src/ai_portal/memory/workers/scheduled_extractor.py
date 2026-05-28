"""Scheduled batch extractor.

Walks queued ``memory_jobs`` of kind=``extract`` + invokes MemoryService.
Designed to run every N hours via the worker scheduler.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory import jobs as _jobs
from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn
from ai_portal.memory.service import MemoryService

logger = logging.getLogger(__name__)


async def run_once(session: AsyncSession, *, max_jobs: int = 50) -> int:
    """Drain up to ``max_jobs`` queued extract jobs. Returns processed count."""
    processed = 0
    for _ in range(max_jobs):
        job = await _jobs.claim_next(session, kind="extract")
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
        except Exception as e:  # pragma: no cover - tested via mocks
            logger.exception("memory.scheduled_extractor.failed")
            await _jobs.finish(session, job.id, status="error", error=str(e)[:2000])
        processed += 1
    return processed
