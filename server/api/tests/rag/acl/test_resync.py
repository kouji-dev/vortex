"""ACL re-sync on source change.

When a connector signals an ACL update we re-run ``connector.acls()``
for the affected doc(s), map via the provider, and replace the rows in
``kb_acls`` (both doc-level and per-chunk).

Covers:
- ``resync_document`` calls fetcher once with the source URI.
- ``resync_document`` replaces existing doc + chunk rows.
- ``resync_kb`` walks every doc in the kb when no subset given.
- ``resync_kb`` survives per-doc fetcher failure (failure-isolation).
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.knowledge_base.model  # noqa: F401
from ai_portal.rag.acl.protocol import ResolvedAcl
from ai_portal.rag.acl.resync import resync_document, resync_kb
from ai_portal.rag.acl.service import (
    fanout_to_chunks,
    store_document_acl,
    visible_chunk_ids,
    visible_document_ids,
)
from ai_portal.rag.connectors.protocol import AclSet, SourceDoc
from tests.conftest import requires_postgres


class _FakeProvider:
    connector_kind = "fake"

    def __init__(self, mapped: ResolvedAcl):
        self.mapped = mapped

    async def map(self, source_acls, org_id):
        # Pass through user/group counts and keep public flag.
        return self.mapped


class _FailingFakeProvider:
    connector_kind = "fake"

    async def map(self, source_acls, org_id):
        raise RuntimeError("idp boom")


def _setup_kb_doc_with_chunks(db, n_chunks: int = 3) -> tuple[int, _uuid.UUID, list[_uuid.UUID]]:
    org = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES "
            "(:id, :slug, 'ACL') ON CONFLICT DO NOTHING"
        ),
        {"id": str(org), "slug": f"acl-rs-{org.hex[:8]}"},
    )
    uid_uuid = _uuid.uuid4()
    uid = db.execute(
        text(
            "INSERT INTO users (uuid, email, role) "
            "VALUES (:u, :e, 'member') RETURNING id"
        ),
        {"u": str(uid_uuid), "e": f"u-{uid_uuid.hex[:6]}@x.test"},
    ).first()[0]
    kb_id = int(
        db.execute(
            text(
                "INSERT INTO knowledge_bases "
                "(org_id, name, description, owner_user_id) "
                "VALUES (:org, :n, '', :ow) RETURNING id"
            ),
            {
                "org": str(org),
                "n": f"rs-{_uuid.uuid4().hex[:6]}",
                "ow": uid,
            },
        ).first()[0]
    )
    doc_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO kb_documents (id, kb_id, source_uri) "
            "VALUES (:id, :kb, :su)"
        ),
        {"id": str(doc_id), "kb": kb_id, "su": f"file:///{doc_id.hex[:6]}"},
    )
    chunks: list[_uuid.UUID] = []
    for i in range(n_chunks):
        cid = _uuid.uuid4()
        db.execute(
            text(
                "INSERT INTO kb_chunks (id, document_id, kb_id, chunk_index) "
                "VALUES (:id, :d, :kb, :i)"
            ),
            {"id": str(cid), "d": str(doc_id), "kb": kb_id, "i": i},
        )
        chunks.append(cid)
    return kb_id, doc_id, chunks


@requires_postgres
@pytest.mark.asyncio
async def test_resync_document_replaces_doc_and_chunk_rows():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc_id, chunks = _setup_kb_doc_with_chunks(db, n_chunks=3)
            # Initial ACL: alice only.
            store_document_acl(
                db, kb_id=kb_id, document_id=doc_id,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc_id, chunk_ids=chunks,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="alice"
            ) == {doc_id}
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="bob"
            ) == set()

            # New ACL from source: bob + carol; alice gone.
            captured_calls: list[SourceDoc] = []

            async def fetcher(sd: SourceDoc) -> AclSet:
                captured_calls.append(sd)
                return AclSet(user_ids={"bob", "carol"})

            provider = _FakeProvider(
                ResolvedAcl(user_ids={"bob", "carol"})
            )
            res = await resync_document(
                db,
                document_id=doc_id,
                org_id=str(_uuid.uuid4()),
                fetcher=fetcher,
                provider=provider,
            )
            assert len(captured_calls) == 1
            assert captured_calls[0].source_uri.startswith("file:///")
            assert res.doc_rows == 2
            assert res.chunk_rows == 6  # 3 chunks × 2 principals
            assert res.chunk_count == 3
            # Visibility flipped.
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="alice"
            ) == set()
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="bob"
            ) == {doc_id}
            assert visible_chunk_ids(
                db, kb_id=kb_id, user_id="carol"
            ) == set(chunks)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
@pytest.mark.asyncio
async def test_resync_kb_walks_all_docs_and_isolates_failures():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc_ok, chunks_ok = _setup_kb_doc_with_chunks(db, 2)
            # Second doc in same KB.
            doc_bad = _uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO kb_documents (id, kb_id, source_uri) "
                    "VALUES (:id, :kb, :su)"
                ),
                {
                    "id": str(doc_bad),
                    "kb": kb_id,
                    "su": f"file:///{doc_bad.hex[:6]}",
                },
            )

            async def fetcher(sd: SourceDoc) -> AclSet:
                if "bad" in sd.source_uri or sd.source_uri.endswith(
                    doc_bad.hex[:6]
                ):
                    raise RuntimeError("fetch failed")
                return AclSet(public=True)

            provider = _FakeProvider(ResolvedAcl(public=True))

            results = await resync_kb(
                db,
                kb_id=kb_id,
                org_id="org-test",
                fetcher=fetcher,
                provider=provider,
            )
            assert len(results) == 2
            # The bad doc has empty rows; the good one has > 0.
            res_by_id = {r.document_id: r for r in results}
            assert res_by_id[doc_ok].doc_rows == 1  # one public row
            assert res_by_id[doc_ok].chunk_rows == 2  # 2 chunks × 1 principal
            assert res_by_id[doc_bad].doc_rows == 0
            assert res_by_id[doc_bad].chunk_rows == 0
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
@pytest.mark.asyncio
async def test_resync_kb_subset_only_touches_given_docs():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc1, _ = _setup_kb_doc_with_chunks(db, 1)
            # Another doc in same KB we should NOT touch.
            doc2 = _uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO kb_documents (id, kb_id, source_uri) "
                    "VALUES (:id, :kb, :su)"
                ),
                {"id": str(doc2), "kb": kb_id, "su": "file:///untouched"},
            )

            calls: list[str] = []

            async def fetcher(sd: SourceDoc) -> AclSet:
                calls.append(sd.source_uri)
                return AclSet(public=True)

            provider = _FakeProvider(ResolvedAcl(public=True))
            results = await resync_kb(
                db,
                kb_id=kb_id,
                org_id="org-test",
                fetcher=fetcher,
                provider=provider,
                doc_ids=[doc1],
            )
            assert len(results) == 1
            assert len(calls) == 1
            db.commit()
    finally:
        db.rollback()
        db.close()
