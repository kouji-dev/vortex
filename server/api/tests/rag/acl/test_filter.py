"""Retrieval ACL filter.

The filter is the server-side guard ensuring retrieval never returns
chunks the actor can't see, regardless of the retriever (dense, lexical,
hybrid, federated).

Covers:
- Hits whose chunks are in actor's allow set pass through.
- Hits outside the allow set are dropped.
- Public ACL → all actors see the chunk.
- Group membership → actor in the group sees chunks.
- Multi-KB filter routes per-KB.
- Empty hits short-circuits without DB query.
"""

from __future__ import annotations

import uuid as _uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import text

import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.knowledge_base.model  # noqa: F401
from ai_portal.rag.acl.filter import (
    build_allow_predicate,
    filter_hits,
    filter_hits_multi_kb,
)
from ai_portal.rag.acl.protocol import ResolvedAcl
from ai_portal.rag.acl.service import fanout_to_chunks
from ai_portal.rag.search.types import SearchHit
from tests.conftest import requires_postgres


def _hit(chunk_id: str, kb_id: int = 1) -> SearchHit:
    return SearchHit(
        chunk_id=chunk_id,
        document_id="doc-1",
        kb_id=kb_id,
        text="t",
        score=0.5,
    )


def test_filter_hits_empty_short_circuits():
    # Should not even call into the DB.
    db = MagicMock()
    out = filter_hits(
        db, hits=[], kb_id=1, actor_user_id="alice",
    )
    assert out == []
    db.execute.assert_not_called()


def _mk_org_kb_doc(db) -> tuple[int, _uuid.UUID]:
    oid = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES "
            "(:id, :slug, 'ACL') ON CONFLICT DO NOTHING"
        ),
        {"id": str(oid), "slug": f"acl-flt-{oid.hex[:8]}"},
    )
    uid_uuid = _uuid.uuid4()
    uid = db.execute(
        text(
            "INSERT INTO users (uuid, email, role) "
            "VALUES (:u, :e, 'member') RETURNING id"
        ),
        {"u": str(uid_uuid), "e": f"u-{uid_uuid.hex[:6]}@x.test"},
    ).first()[0]
    kb_row = db.execute(
        text(
            "INSERT INTO knowledge_bases "
            "(org_id, name, description, owner_user_id) "
            "VALUES (:org, :n, '', :ow) RETURNING id"
        ),
        {"org": str(oid), "n": f"flt-{_uuid.uuid4().hex[:6]}", "ow": uid},
    ).first()
    kb_id = int(kb_row[0])
    did = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO kb_documents (id, kb_id, source_uri) "
            "VALUES (:id, :kb, :su)"
        ),
        {"id": str(did), "kb": kb_id, "su": f"file:///{did.hex[:6]}"},
    )
    return kb_id, did


@requires_postgres
def test_filter_hits_drops_unallowed():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc = _mk_org_kb_doc(db)
            c_allow = _uuid.uuid4()
            c_deny = _uuid.uuid4()
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=[c_allow],
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=[c_deny],
                acl=ResolvedAcl(user_ids={"bob"}),
            )
            hits = [_hit(str(c_allow), kb_id), _hit(str(c_deny), kb_id)]
            out = filter_hits(
                db, hits=hits, kb_id=kb_id, actor_user_id="alice",
            )
            assert [h.chunk_id for h in out] == [str(c_allow)]
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_filter_hits_public_allows_anyone():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc = _mk_org_kb_doc(db)
            c = _uuid.uuid4()
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=[c],
                acl=ResolvedAcl(public=True),
            )
            out = filter_hits(
                db, hits=[_hit(str(c), kb_id)], kb_id=kb_id,
                actor_user_id="stranger",
            )
            assert len(out) == 1
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_filter_hits_group_membership_grants():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc = _mk_org_kb_doc(db)
            c = _uuid.uuid4()
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=[c],
                acl=ResolvedAcl(group_ids={"eng"}),
            )
            # No group membership → empty.
            assert filter_hits(
                db, hits=[_hit(str(c), kb_id)], kb_id=kb_id,
                actor_user_id="x",
            ) == []
            # Member of "eng" → visible.
            assert len(
                filter_hits(
                    db, hits=[_hit(str(c), kb_id)], kb_id=kb_id,
                    actor_user_id="x", actor_group_ids=["eng"],
                )
            ) == 1
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_build_allow_predicate_membership():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_id, doc = _mk_org_kb_doc(db)
            c_in = _uuid.uuid4()
            c_out = _uuid.uuid4()
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=[c_in],
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            allows = build_allow_predicate(
                db, kb_id=kb_id, actor_user_id="alice",
            )
            assert allows(str(c_in)) is True
            assert allows(str(c_out)) is False
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_filter_hits_multi_kb_routes_per_kb():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            kb_a, doc_a = _mk_org_kb_doc(db)
            kb_b, doc_b = _mk_org_kb_doc(db)
            c_a = _uuid.uuid4()
            c_b = _uuid.uuid4()
            fanout_to_chunks(
                db, kb_id=kb_a, document_id=doc_a, chunk_ids=[c_a],
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            # In kb_b alice is NOT allowed.
            fanout_to_chunks(
                db, kb_id=kb_b, document_id=doc_b, chunk_ids=[c_b],
                acl=ResolvedAcl(user_ids={"bob"}),
            )
            hits = [_hit(str(c_a), kb_a), _hit(str(c_b), kb_b)]
            out = filter_hits_multi_kb(
                db, hits=hits, actor_user_id="alice",
            )
            assert [h.chunk_id for h in out] == [str(c_a)]
            db.commit()
    finally:
        db.rollback()
        db.close()
