"""ACL re-sync.

When a source system signals an ACL change (Slack channel membership
update, GDrive share change, Confluence space restriction tweak, ...)
we re-resolve the document's ACL and overwrite the rows in ``kb_acls``.

Two entry points:

- :func:`resync_document` — re-resolve + re-write the ACL for a single
  document. Called from connector webhooks where the affected doc id is
  known cheaply.
- :func:`resync_kb` — fall back to walking every doc in a KB. Used by
  scheduled re-syncs for connectors without webhook support.

The function does **not** re-fetch the document bytes. It only re-runs
``connector.acls(sd)`` for the source-doc reference reconstructed from
the stored ``source_uri``, then stores the result.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.knowledge_base.model import KbChunk, KbDocument
from ai_portal.rag.acl.protocol import AclProvider, ResolvedAcl
from ai_portal.rag.acl.service import (
    capture_acls,
    fanout_to_chunks,
    store_document_acl,
)
from ai_portal.rag.connectors.protocol import AclSet, SourceDoc


@dataclass(slots=True)
class ResyncResult:
    """Outcome of a single doc re-sync."""

    document_id: _uuid.UUID
    chunk_count: int
    doc_rows: int
    chunk_rows: int
    resolved: ResolvedAcl


# Callable shape: given a source_uri + connector raw meta, return AclSet.
AclFetcher = Callable[[SourceDoc], Awaitable[AclSet]]


def _doc_to_source_doc(doc: KbDocument) -> SourceDoc:
    """Reconstruct the minimal SourceDoc needed for ``connector.acls()``.

    We only need ``source_uri``; the connector treats this as the key
    and looks up ACLs from its own backing store. Other fields are
    populated best-effort from the persisted document row.
    """

    return SourceDoc(
        source_uri=doc.source_uri,
        title=doc.title or doc.source_uri,
        mime=doc.mime or None,
        size=None,
        modified_at=doc.updated_at,
        cursor_token=None,
        raw=dict(doc.meta_json or {}),
    )


def _chunk_ids_for_doc(
    db: Session, document_id: _uuid.UUID
) -> list[_uuid.UUID]:
    rows = db.execute(
        select(KbChunk.id).where(KbChunk.document_id == document_id)
    ).all()
    return [r[0] for r in rows]


async def resync_document(
    db: Session,
    *,
    document_id: str | _uuid.UUID,
    org_id: str,
    fetcher: AclFetcher,
    provider: AclProvider,
) -> ResyncResult:
    """Re-resolve + re-write the ACL for one document.

    Steps:

    1. Load the document row.
    2. Call ``fetcher(source_doc)`` to get the *current* source ACL.
    3. Resolve via the provider.
    4. Replace doc-level rows in ``kb_acls``.
    5. Fan out to every chunk under the document.
    """

    did = (
        document_id
        if isinstance(document_id, _uuid.UUID)
        else _uuid.UUID(str(document_id))
    )
    doc = db.execute(
        select(KbDocument).where(KbDocument.id == did)
    ).scalar_one()
    sd = _doc_to_source_doc(doc)
    source_acl = await fetcher(sd)
    resolved = await capture_acls(
        provider=provider, source_acls=source_acl, org_id=org_id,
    )
    doc_rows = store_document_acl(
        db, kb_id=doc.kb_id, document_id=did, acl=resolved,
    )
    chunk_ids = _chunk_ids_for_doc(db, did)
    chunk_rows = fanout_to_chunks(
        db, kb_id=doc.kb_id, document_id=did,
        chunk_ids=chunk_ids, acl=resolved,
    )
    return ResyncResult(
        document_id=did,
        chunk_count=len(chunk_ids),
        doc_rows=doc_rows,
        chunk_rows=chunk_rows,
        resolved=resolved,
    )


async def resync_kb(
    db: Session,
    *,
    kb_id: int,
    org_id: str,
    fetcher: AclFetcher,
    provider: AclProvider,
    doc_ids: Sequence[str | _uuid.UUID] | None = None,
) -> list[ResyncResult]:
    """Re-sync every doc in a KB (or a subset).

    Failure of one doc does NOT block the rest — its failure is captured
    by returning a :class:`ResyncResult` with ``doc_rows=0`` and
    ``chunk_rows=0`` and an empty :attr:`ResyncResult.resolved`. Callers
    can inspect ``resolved.unresolved`` for the unresolved-ids set.
    """

    if doc_ids is None:
        rows = db.execute(
            select(KbDocument.id).where(KbDocument.kb_id == kb_id)
        ).all()
        ids: list[_uuid.UUID] = [r[0] for r in rows]
    else:
        ids = [
            d if isinstance(d, _uuid.UUID) else _uuid.UUID(str(d))
            for d in doc_ids
        ]

    out: list[ResyncResult] = []
    for did in ids:
        try:
            res = await resync_document(
                db,
                document_id=did,
                org_id=org_id,
                fetcher=fetcher,
                provider=provider,
            )
            out.append(res)
        except Exception:
            # Failure-isolated: record an empty result so callers can
            # surface failures via audit / webhooks without aborting the
            # KB-wide re-sync.
            out.append(
                ResyncResult(
                    document_id=did,
                    chunk_count=0,
                    doc_rows=0,
                    chunk_rows=0,
                    resolved=ResolvedAcl(),
                )
            )
    return out


__all__ = [
    "AclFetcher",
    "ResyncResult",
    "resync_document",
    "resync_kb",
]
