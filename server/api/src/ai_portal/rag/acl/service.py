"""ACL mirroring service.

Captures source-system ACLs during ingest and writes a denormalised allow
set into ``kb_acls`` — one row per (kb_id, document_id|chunk_id,
subject_kind, subject_id) entry. Retrieval is then filtered by joining
chunks to ``kb_acls`` for the requesting actor.

Workflow during ingest:

1. Connector emits :class:`AclSet` with **source-native** ids.
2. :func:`capture_acls` resolves them via an :class:`AclProvider`
   (defaults to :class:`DefaultIdpAclProvider`) and returns a
   :class:`ResolvedAcl` for the document.
3. :func:`store_document_acl` writes one row per principal into
   ``kb_acls`` with ``document_id`` set.
4. :func:`fanout_to_chunks` denormalises the doc-level ACL across every
   chunk id of the document — one row per chunk per principal — so the
   chunk-level retrieval filter can join in O(1) without walking back
   up to the document.

The store is intentionally **deny-by-default**:

- A document with ``public=True`` writes a single row with
  ``subject_kind="public"`` and ``subject_id=NULL``.
- A document with no allowed principals writes **no rows** — retrieval
  returns nothing for it.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Iterable, Sequence

from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbAcl
from ai_portal.rag.acl.protocol import AclProvider, ResolvedAcl
from ai_portal.rag.connectors.protocol import AclSet


SubjectKind = str  # "user" | "group" | "public"


@dataclass(slots=True)
class StoredAclRow:
    """Subset of an inserted ``kb_acls`` row, returned to callers."""

    id: _uuid.UUID
    subject_kind: SubjectKind
    subject_id: str | None


# ────────────────────────────────────────────────────────────── capture ──


async def capture_acls(
    *,
    provider: AclProvider,
    source_acls: AclSet,
    org_id: str,
) -> ResolvedAcl:
    """Resolve a connector ``AclSet`` to a :class:`ResolvedAcl`.

    Pure wrapper around the provider — kept here so the ingest stage
    imports a single symbol regardless of which provider is wired in.
    """

    return await provider.map(source_acls=source_acls, org_id=org_id)


# ─────────────────────────────────────────────────────────────── store ──


def _doc_uuid(document_id: str | _uuid.UUID) -> _uuid.UUID:
    return document_id if isinstance(document_id, _uuid.UUID) else _uuid.UUID(str(document_id))


def _chunk_uuid(chunk_id: str | _uuid.UUID) -> _uuid.UUID:
    return chunk_id if isinstance(chunk_id, _uuid.UUID) else _uuid.UUID(str(chunk_id))


def _rows_from_resolved(
    *,
    kb_id: int,
    document_id: _uuid.UUID | None,
    chunk_id: _uuid.UUID | None,
    acl: ResolvedAcl,
) -> list[dict]:
    rows: list[dict] = []
    if acl.public:
        rows.append({
            "kb_id": kb_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "subject_kind": "public",
            "subject_id": None,
        })
    for uid in sorted(acl.user_ids):
        rows.append({
            "kb_id": kb_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "subject_kind": "user",
            "subject_id": uid,
        })
    for gid in sorted(acl.group_ids):
        rows.append({
            "kb_id": kb_id,
            "document_id": document_id,
            "chunk_id": chunk_id,
            "subject_kind": "group",
            "subject_id": gid,
        })
    return rows


def store_document_acl(
    db: Session,
    *,
    kb_id: int,
    document_id: str | _uuid.UUID,
    acl: ResolvedAcl,
    replace: bool = True,
) -> int:
    """Persist doc-level allow set.

    Returns the number of rows inserted. When ``replace`` is True (default)
    any existing doc-level rows for this document are removed first — used
    for re-syncs after source ACL changes.
    """

    doc_uuid = _doc_uuid(document_id)
    if replace:
        db.execute(
            delete(KbAcl).where(
                KbAcl.document_id == doc_uuid,
                KbAcl.chunk_id.is_(None),
            )
        )
    rows = _rows_from_resolved(
        kb_id=kb_id, document_id=doc_uuid, chunk_id=None, acl=acl,
    )
    if not rows:
        return 0
    db.execute(insert(KbAcl), rows)
    return len(rows)


def fanout_to_chunks(
    db: Session,
    *,
    kb_id: int,
    document_id: str | _uuid.UUID,
    chunk_ids: Sequence[str | _uuid.UUID],
    acl: ResolvedAcl,
    replace: bool = True,
) -> int:
    """Write per-chunk allow rows for every chunk under ``document_id``.

    The retrieval filter joins ``kb_chunks`` ↔ ``kb_acls`` on
    ``chunk_id`` so this fan-out is what makes filtering O(1) per hit.
    """

    if not chunk_ids:
        return 0
    chunk_uuids = [_chunk_uuid(c) for c in chunk_ids]
    if replace:
        db.execute(
            delete(KbAcl).where(
                KbAcl.chunk_id.in_(chunk_uuids),
            )
        )
    doc_uuid = _doc_uuid(document_id)
    rows: list[dict] = []
    for cu in chunk_uuids:
        rows.extend(
            _rows_from_resolved(
                kb_id=kb_id, document_id=doc_uuid, chunk_id=cu, acl=acl,
            )
        )
    if not rows:
        return 0
    db.execute(insert(KbAcl), rows)
    return len(rows)


def delete_acl_for_document(
    db: Session, *, document_id: str | _uuid.UUID
) -> None:
    """Drop both doc-level + chunk-level rows for a document.

    Used on tombstone / deletion.
    """

    doc_uuid = _doc_uuid(document_id)
    db.execute(delete(KbAcl).where(KbAcl.document_id == doc_uuid))


# ─────────────────────────────────────────────────────── retrieval filter ──


def visible_document_ids(
    db: Session,
    *,
    kb_id: int,
    user_id: str | None,
    group_ids: Iterable[str] = (),
) -> set[_uuid.UUID]:
    """Return the set of documents the actor is allowed to retrieve.

    Used by the permission-test endpoint and by retrieval to pre-filter
    candidate documents before vector search. Public-ACL docs are always
    included.
    """

    group_list = list(group_ids)
    conditions = [
        KbAcl.subject_kind == "public",
    ]
    if user_id is not None:
        conditions.append(
            (KbAcl.subject_kind == "user")
            & (KbAcl.subject_id == str(user_id))
        )
    if group_list:
        conditions.append(
            (KbAcl.subject_kind == "group")
            & (KbAcl.subject_id.in_([str(g) for g in group_list]))
        )

    # OR the conditions together.
    from sqlalchemy import or_
    stmt = (
        select(KbAcl.document_id)
        .where(
            KbAcl.kb_id == kb_id,
            KbAcl.document_id.is_not(None),
            or_(*conditions),
        )
        .distinct()
    )
    return {row[0] for row in db.execute(stmt) if row[0] is not None}


def visible_chunk_ids(
    db: Session,
    *,
    kb_id: int,
    user_id: str | None,
    group_ids: Iterable[str] = (),
) -> set[_uuid.UUID]:
    """Return the chunk IDs the actor can retrieve.

    The retrieval pipeline ANDs this set with the candidate chunk list
    produced by dense + lexical retrieval.
    """

    group_list = list(group_ids)
    from sqlalchemy import or_
    conditions = [KbAcl.subject_kind == "public"]
    if user_id is not None:
        conditions.append(
            (KbAcl.subject_kind == "user")
            & (KbAcl.subject_id == str(user_id))
        )
    if group_list:
        conditions.append(
            (KbAcl.subject_kind == "group")
            & (KbAcl.subject_id.in_([str(g) for g in group_list]))
        )

    stmt = (
        select(KbAcl.chunk_id)
        .where(
            KbAcl.kb_id == kb_id,
            KbAcl.chunk_id.is_not(None),
            or_(*conditions),
        )
        .distinct()
    )
    return {row[0] for row in db.execute(stmt) if row[0] is not None}


__all__ = [
    "StoredAclRow",
    "capture_acls",
    "delete_acl_for_document",
    "fanout_to_chunks",
    "store_document_acl",
    "visible_chunk_ids",
    "visible_document_ids",
]
