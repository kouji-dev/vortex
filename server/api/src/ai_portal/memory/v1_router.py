"""``/v1/memories`` admin + user API.

Kept separate from the legacy ``/api/users/me/memories`` router so the new
pluggable subsystem ships side-by-side with the older single-row profile.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.extractors.protocol import ExtractOpts, ExtractScope, Turn
from ai_portal.memory.model import (
    ConflictStrategy,
    MemoryExtractionPolicy,
    MemoryRecallPolicy,
    ScopeKind,
)
from ai_portal.memory.recallers.protocol import RecallOpts, RecallScope
from ai_portal.memory.schemas import (
    BulkDeleteRequest,
    ExtractionPolicyDTO,
    ExtractRequest,
    MemoryCreate,
    MemoryPatch,
    PauseRequest,
    RecallPolicyDTO,
    RecallRequest,
)
from ai_portal.memory.service import MemoryService


router = APIRouter(prefix="/v1/memories", tags=["memories-v1"])


# ── DI ───────────────────────────────────────────────────────────────


async def _get_session() -> AsyncSession:  # pragma: no cover - overridden in app wiring
    from ai_portal.core.db.session import AsyncSessionLocal  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as s:
        yield s


def _get_actor():
    """Resolves the current actor (via control_plane). Falls back to a stub
    for tests that override the dep.
    """
    from ai_portal.control_plane import require_actor  # imported lazily

    return require_actor


# ── list / create ────────────────────────────────────────────────────


@router.get("")
async def list_memories(
    type: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> list[dict[str, Any]]:
    from ai_portal.memory.repository import MemoryRepo

    repo = MemoryRepo(session)
    from ai_portal.memory.model import MemoryType

    rows = await repo.list_for_actor(
        org_id=actor.org_id,
        actor_user_id=str(actor.user_id),
        team_ids=[],
        type=MemoryType(type) if type else None,
        q=q,
        limit=limit,
    )
    return [
        {
            "id": str(m.id),
            "type": m.type.value,
            "scope_kind": m.scope_kind.value,
            "scope_ids": m.scope_ids_json,
            "text": m.text,
            "importance": float(m.importance),
            "confidence": float(m.confidence),
            "tags": m.tags_json,
            "pinned": m.pinned,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_memory(
    body: MemoryCreate,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    svc = MemoryService(session)
    m = await svc.add_manual(
        org_id=actor.org_id,
        actor_user_id=int(actor.user_id) if actor.user_id is not None else 0,
        type=body.type,
        text=body.text,
        scope_kind=body.scope_kind,
        scope_ids=body.scope_ids or [str(actor.user_id)],
        importance=body.importance,
        confidence=body.confidence,
        tags=body.tags,
        pinned=body.pinned,
    )
    await session.commit()
    return {"id": str(m.id), "type": m.type.value, "text": m.text}


@router.patch("/{memory_id}")
async def patch_memory(
    memory_id: _uuid.UUID,
    body: MemoryPatch,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    svc = MemoryService(session)
    m = await svc.patch(
        memory_id,
        text=body.text,
        importance=body.importance,
        pinned=body.pinned,
        tags=body.tags,
        confidence=body.confidence,
    )
    if m is None:
        raise HTTPException(404, "memory not found")
    await session.commit()
    return {"id": str(m.id), "text": m.text, "importance": float(m.importance), "pinned": m.pinned}


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(
    memory_id: _uuid.UUID,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> None:
    svc = MemoryService(session)
    await svc.soft_delete(memory_id)
    await session.commit()


@router.post("/bulk-delete")
async def bulk_delete(
    body: BulkDeleteRequest,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, int]:
    svc = MemoryService(session)
    count = await svc.bulk_delete(
        org_id=actor.org_id,
        actor_user_id=int(actor.user_id) if actor.user_id is not None else 0,
        ids=body.ids,
        type=body.type,
        scope_kind=body.scope_kind,
        time_from=body.time_from,
        time_to=body.time_to,
    )
    await session.commit()
    return {"deleted": count}


@router.post("/extract")
async def extract_endpoint(
    body: ExtractRequest,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    scope = ExtractScope(
        org_id=str(actor.org_id),
        actor_user_id=str(actor.user_id),
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
        conversation_id=str(body.conversation_id) if body.conversation_id else None,
        assistant_id=body.assistant_id,
    )
    opts = ExtractOpts(
        model=body.model,
        allowed_types=list(body.allowed_types),
        block_sensitive_categories=list(body.block_sensitive_categories),
        confidence_floor=body.confidence_floor,
    )
    turns = [
        Turn(role=t.role, content=t.content, turn_id=t.turn_id, ts=t.ts)
        for t in body.turns
    ]
    svc = MemoryService(session, extractor_name=body.extractor)
    result = await svc.extract(turns, scope, opts)
    await session.commit()
    return {
        "created": [str(m.id) for m in result.created],
        "updated": [str(m.id) for m in result.updated],
        "skipped_sensitive": len(result.skipped_sensitive),
        "skipped_dedup": len(result.skipped_dedup),
        "skipped_paused": result.skipped_paused,
        "skipped_module_disabled": result.skipped_module_disabled,
    }


@router.post("/recall")
async def recall_endpoint(
    body: RecallRequest,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> list[dict[str, Any]]:
    scope = RecallScope(
        org_id=str(actor.org_id),
        actor_user_id=str(actor.user_id),
        team_ids=[],
        assistant_id=body.assistant_id,
        conversation_id=str(body.conversation_id) if body.conversation_id else None,
    )
    opts = RecallOpts(
        top_k=body.top_k,
        recency_weight=body.recency_weight,
        importance_weight=body.importance_weight,
    )
    svc = MemoryService(session)
    results = await svc.recall(body.query, scope, opts)
    return [
        {"memory_id": r.memory_id, "text": r.text, "score": float(r.score), "explain": r.explain}
        for r in results
    ]


@router.get("/{memory_id}/uses")
async def list_uses(
    memory_id: _uuid.UUID,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    from ai_portal.memory.repository import MemoryRepo

    repo = MemoryRepo(session)
    m = await repo.get(memory_id)
    if m is None:
        raise HTTPException(404, "memory not found")
    uses = await repo.list_uses(memory_id)
    return {
        "uses": [
            {
                "response_message_id": u.response_message_id,
                "score": float(u.score),
                "ts": u.ts.isoformat() if u.ts else None,
            }
            for u in uses
        ],
        "source": {
            "conversation_id": m.source_conversation_id,
            "turn_ids": m.source_turn_ids_json,
            "extractor_model": m.extractor_model,
        },
    }


# ── policies ────────────────────────────────────────────────────────


@router.get("/policies")
async def get_policies(
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    from sqlalchemy import select

    ext_rows = (
        await session.execute(
            select(MemoryExtractionPolicy).where(
                MemoryExtractionPolicy.org_id == actor.org_id
            )
        )
    ).scalars().all()
    rec_rows = (
        await session.execute(
            select(MemoryRecallPolicy).where(MemoryRecallPolicy.org_id == actor.org_id)
        )
    ).scalars().all()
    return {
        "extraction": [
            {
                "scope_kind": p.scope_kind.value,
                "triggers": p.triggers_json,
                "sensitive_block": p.sensitive_block_json,
                "model_allow": p.model_allow_json,
                "conflict_strategy": p.conflict_strategy.value,
                "retention_days": p.retention_days_json,
            }
            for p in ext_rows
        ],
        "recall": [
            {
                "scope_kind": p.scope_kind.value,
                "top_k": p.top_k,
                "recency_weight": float(p.recency_weight),
                "importance_weight": float(p.importance_weight),
                "filters": p.filters_json,
            }
            for p in rec_rows
        ],
    }


@router.post("/policies/extraction")
async def set_extraction_policy(
    body: ExtractionPolicyDTO,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    from sqlalchemy import select

    existing = (
        await session.execute(
            select(MemoryExtractionPolicy).where(
                MemoryExtractionPolicy.org_id == actor.org_id,
                MemoryExtractionPolicy.scope_kind == ScopeKind(body.scope_kind),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = MemoryExtractionPolicy(
            org_id=actor.org_id,
            scope_kind=ScopeKind(body.scope_kind),
        )
        session.add(existing)
    existing.triggers_json = body.triggers
    existing.sensitive_block_json = body.sensitive_block
    existing.model_allow_json = body.model_allow
    existing.conflict_strategy = ConflictStrategy(body.conflict_strategy)
    existing.retention_days_json = body.retention_days
    await session.flush()
    await session.commit()
    try:
        from ai_portal.control_plane import emit_webhook

        emit_webhook(
            "memory.policy.changed",
            {"scope_kind": body.scope_kind, "kind": "extraction"},
            actor.org_id,
        )
    except Exception:
        pass
    return {"ok": True}


@router.post("/policies/recall")
async def set_recall_policy(
    body: RecallPolicyDTO,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    from sqlalchemy import select

    existing = (
        await session.execute(
            select(MemoryRecallPolicy).where(
                MemoryRecallPolicy.org_id == actor.org_id,
                MemoryRecallPolicy.scope_kind == ScopeKind(body.scope_kind),
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        existing = MemoryRecallPolicy(
            org_id=actor.org_id,
            scope_kind=ScopeKind(body.scope_kind),
        )
        session.add(existing)
    existing.top_k = body.top_k
    existing.recency_weight = body.recency_weight
    existing.importance_weight = body.importance_weight
    existing.filters_json = body.filters
    await session.flush()
    await session.commit()
    try:
        from ai_portal.control_plane import emit_webhook

        emit_webhook(
            "memory.policy.changed",
            {"scope_kind": body.scope_kind, "kind": "recall"},
            actor.org_id,
        )
    except Exception:
        pass
    return {"ok": True}


# ── pause / resume / export ─────────────────────────────────────────


@router.post("/pause")
async def pause_endpoint(
    body: PauseRequest,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    svc = MemoryService(session)
    p = await svc.pause(
        org_id=actor.org_id,
        actor_user_id=int(actor.user_id) if actor.user_id is not None else 0,
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
    )
    await session.commit()
    return {"id": str(p.id), "paused_at": p.paused_at.isoformat() if p.paused_at else None}


@router.post("/resume")
async def resume_endpoint(
    body: PauseRequest,
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, int]:
    svc = MemoryService(session)
    cleared = await svc.resume(
        org_id=actor.org_id,
        actor_user_id=int(actor.user_id) if actor.user_id is not None else 0,
        scope_kind=body.scope_kind,
        scope_id=body.scope_id,
    )
    await session.commit()
    return {"cleared": cleared}


@router.get("/export")
async def export_endpoint(
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    svc = MemoryService(session)
    payload = await svc.export_for_user(
        org_id=actor.org_id,
        user_id=int(actor.user_id) if actor.user_id is not None else 0,
    )
    return payload


# ── analytics ───────────────────────────────────────────────────────


@router.get("/analytics")
async def analytics_endpoint(
    session: AsyncSession = Depends(_get_session),
    actor=Depends(_get_actor()),
) -> dict[str, Any]:
    from ai_portal.memory.analytics import rollup_all

    return await rollup_all(session, actor.org_id)
