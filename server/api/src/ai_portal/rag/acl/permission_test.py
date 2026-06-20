"""Permission-test service.

Answers: "If user X queried this KB right now, which documents could they
retrieve?" — the admin UI uses this to verify ACL mirroring is wired
correctly without having to impersonate the user.

Reads:

- :data:`kb_acls` via :func:`visible_document_ids`.
- :data:`kb_documents` for the sample titles + URIs.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbDocument
from ai_portal.rag.acl.service import visible_document_ids


@dataclass(slots=True)
class PermissionDocSample:
    document_id: _uuid.UUID
    title: str
    source_uri: str


@dataclass(slots=True)
class PermissionTestOutcome:
    user_id: int
    kb_id: int
    visible_document_count: int
    sample: list[PermissionDocSample]
    resolved_group_ids: list[str]


def _load_user_group_ids(db: Session, user_id: int) -> list[str]:
    """Return group ids the user belongs to (as strings).

    SCIM group membership was removed; returns empty list until a
    replacement group-membership mechanism is wired up.
    """
    return []


def run_permission_test(
    db: Session,
    *,
    kb_id: int,
    user_id: int,
    group_ids_override: Iterable[str] | None = None,
    sample_limit: int = 20,
) -> PermissionTestOutcome:
    """Compute which docs in ``kb_id`` are visible to ``user_id``.

    Uses the user's SCIM group membership unless ``group_ids_override``
    is provided (the admin UI lets operators probe hypothetical groups).
    """

    if group_ids_override is not None:
        group_ids = [str(g) for g in group_ids_override]
    else:
        group_ids = _load_user_group_ids(db, user_id)

    seen = visible_document_ids(
        db,
        kb_id=kb_id,
        user_id=str(user_id),
        group_ids=group_ids,
    )
    count = len(seen)

    sample: list[PermissionDocSample] = []
    if sample_limit > 0 and seen:
        # Stable sample: order by document_id so the same probe returns
        # the same sample on consecutive calls.
        sample_ids = sorted(seen)[: sample_limit]
        rows = db.execute(
            select(
                KbDocument.id,
                KbDocument.title,
                KbDocument.source_uri,
            ).where(KbDocument.id.in_(sample_ids))
        ).all()
        # Maintain the sample_ids order.
        by_id = {r[0]: r for r in rows}
        for sid in sample_ids:
            r = by_id.get(sid)
            if r is None:
                continue
            sample.append(
                PermissionDocSample(
                    document_id=r[0],
                    title=r[1] or "",
                    source_uri=r[2] or "",
                )
            )

    return PermissionTestOutcome(
        user_id=user_id,
        kb_id=kb_id,
        visible_document_count=count,
        sample=sample,
        resolved_group_ids=group_ids,
    )


__all__ = [
    "PermissionDocSample",
    "PermissionTestOutcome",
    "run_permission_test",
]
