"""GDPR cascade for the memory module.

Registers a deleter + exporter with ``control_plane.register_*`` so the
GDPR worker fans out user-delete / user-export jobs to this module.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_portal.memory.model import Memory, MemoryScope, MemoryUse

logger = logging.getLogger(__name__)


async def delete_for_user(
    session: AsyncSession, org_id: _uuid.UUID, user_id: int | str
) -> int:
    """Hard-delete all memories owned by ``user_id`` within ``org_id``."""
    ids = (
        await session.execute(
            select(Memory.id).where(
                Memory.org_id == org_id,
                Memory.actor_owner_json["id"].astext == str(user_id),
            )
        )
    ).scalars().all()
    if not ids:
        return 0
    await session.execute(delete(MemoryUse).where(MemoryUse.memory_id.in_(ids)))
    await session.execute(delete(MemoryScope).where(MemoryScope.memory_id.in_(ids)))
    res = await session.execute(delete(Memory).where(Memory.id.in_(ids)))
    await session.flush()
    count = int(res.rowcount or len(ids))
    try:
        from ai_portal.control_plane import emit_audit

        emit_audit(
            org_id=org_id,
            event_type="memory.gdpr.deleted",
            resource={"user_id": str(user_id), "count": count},
        )
    except Exception:
        pass
    return count


async def export_for_user(
    session: AsyncSession, org_id: _uuid.UUID, user_id: int | str
) -> dict[str, Any]:
    rows = (
        await session.execute(
            select(Memory).where(
                Memory.org_id == org_id,
                Memory.actor_owner_json["id"].astext == str(user_id),
            )
        )
    ).scalars().all()
    return {
        "memories": [
            {
                "id": str(m.id),
                "type": m.type.value,
                "text": m.text,
                "scope_kind": m.scope_kind.value,
                "scope_ids": m.scope_ids_json,
                "source_conversation_id": m.source_conversation_id,
                "source_turn_ids": m.source_turn_ids_json,
                "extractor_model": m.extractor_model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in rows
        ]
    }


# ── control-plane adapters (org-scoped signatures) ─────────────────────


async def _delete_adapter(org_id: _uuid.UUID, scope: dict) -> None:
    """Adapter matching ``Deleter`` protocol ``(org_id, scope) -> None``.

    Scope may contain ``user_id`` to target one actor. Opens its own session.
    """
    user_id = (scope or {}).get("user_id") or (scope or {}).get("actor_id")
    if user_id is None:
        return
    from ai_portal.core.db.session import AsyncSessionLocal  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as session:  # type: ignore[misc]
        try:
            await delete_for_user(session, org_id, user_id)
            await session.commit()
        except Exception:
            logger.exception("memory.gdpr.delete_adapter_failed")
            await session.rollback()


async def _export_adapter(org_id: _uuid.UUID) -> dict[str, Any]:
    """Adapter matching ``Exporter`` protocol ``(org_id) -> dict``.

    Exports every memory in the org (not user-scoped) since exporters are
    invoked per org by the GDPR worker.
    """
    from ai_portal.core.db.session import AsyncSessionLocal  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as session:  # type: ignore[misc]
        rows = (
            await session.execute(
                select(Memory).where(Memory.org_id == org_id)
            )
        ).scalars().all()
        return {
            "memories": [
                {
                    "id": str(m.id),
                    "actor": m.actor_owner_json,
                    "type": m.type.value,
                    "text": m.text,
                    "scope_kind": m.scope_kind.value,
                    "scope_ids": m.scope_ids_json,
                    "created_at": m.created_at.isoformat() if m.created_at else None,
                }
                for m in rows
            ]
        }


def register() -> None:
    """Register adapters with control_plane GDPR registry."""
    try:
        from ai_portal.control_plane import register_deleter, register_exporter

        register_deleter("memory", _delete_adapter)
        register_exporter("memory", _export_adapter)
    except Exception:
        logger.debug("memory.gdpr.register_skipped")
