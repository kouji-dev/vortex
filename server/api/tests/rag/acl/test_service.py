"""ACL service: capture → store → fan-out → filter.

Postgres-backed: hits ``kb_acls`` directly.

Covers:
- ``capture_acls`` defers to provider.
- ``store_document_acl`` inserts one row per principal.
- ``store_document_acl`` writes a ``public`` row for public ACLs.
- ``store_document_acl`` writes zero rows for empty allow set.
- ``store_document_acl`` replaces existing doc-level rows on re-sync.
- ``fanout_to_chunks`` writes one row per (chunk × principal).
- ``visible_document_ids`` returns only docs the actor can see.
- ``visible_chunk_ids`` returns only chunks the actor can see.
- Public docs are visible to all actors.
- Group membership grants access.
- ``delete_acl_for_document`` clears both doc + chunk rows.
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.knowledge_base.model  # noqa: F401
from ai_portal.knowledge_base.model import KbAcl
from ai_portal.rag.acl.protocol import ResolvedAcl
from ai_portal.rag.acl.service import (
    capture_acls,
    delete_acl_for_document,
    fanout_to_chunks,
    store_document_acl,
    visible_chunk_ids,
    visible_document_ids,
)
from ai_portal.rag.connectors.protocol import AclSet
from tests.conftest import requires_postgres


def _mk_org(db) -> _uuid.UUID:
    oid = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ACL') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(oid), "slug": f"acl-svc-{oid.hex[:8]}"},
    )
    return oid


def _mk_user(db) -> int:
    uid_uuid = _uuid.uuid4()
    row = db.execute(
        text(
            "INSERT INTO users (uuid, email, role) "
            "VALUES (:uuid, :em, 'member') RETURNING id"
        ),
        {"uuid": str(uid_uuid), "em": f"u-{uid_uuid.hex[:6]}@x.test"},
    ).first()
    return int(row[0])


def _mk_kb(db, org_id: _uuid.UUID, owner_id: int) -> int:
    row = db.execute(
        text(
            "INSERT INTO knowledge_bases "
            "(org_id, name, description, owner_user_id) "
            "VALUES (:org, :n, '', :ow) RETURNING id"
        ),
        {
            "org": str(org_id),
            "n": f"kb-acl-{_uuid.uuid4().hex[:6]}",
            "ow": owner_id,
        },
    ).first()
    return int(row[0])


def _mk_doc(db, kb_id: int, source_uri: str = "file:///x") -> _uuid.UUID:
    did = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO kb_documents (id, kb_id, source_uri) "
            "VALUES (:id, :kb, :su)"
        ),
        {"id": str(did), "kb": kb_id, "su": f"{source_uri}-{did.hex[:6]}"},
    )
    return did


def _count_acls(db, **where) -> int:
    q = "SELECT count(*) FROM kb_acls"
    parts = []
    params: dict = {}
    for k, v in where.items():
        parts.append(f"{k} = :{k}")
        params[k] = v
    if parts:
        q += " WHERE " + " AND ".join(parts)
    return db.execute(text(q), params).scalar() or 0


# ─────────────────────────────────────────────────────── capture_acls ──


class _StubProvider:
    connector_kind = "stub"

    def __init__(self, mapped: ResolvedAcl):
        self._mapped = mapped
        self.calls: list[tuple[AclSet, str]] = []

    async def map(self, source_acls: AclSet, org_id: str) -> ResolvedAcl:
        self.calls.append((source_acls, org_id))
        return self._mapped


@pytest.mark.asyncio
async def test_capture_acls_defers_to_provider():
    mapped = ResolvedAcl(user_ids={"42"}, public=False)
    provider = _StubProvider(mapped)
    src = AclSet(user_ids={"alice@x.test"})
    out = await capture_acls(
        provider=provider, source_acls=src, org_id="org-1"
    )
    assert out is mapped
    assert provider.calls == [(src, "org-1")]


# ─────────────────────────────────────────────────────── store_document ──


@requires_postgres
def test_store_document_acl_one_row_per_principal():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            n = store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(
                    user_ids={"u-1", "u-2"},
                    group_ids={"g-1"},
                    public=False,
                ),
            )
            assert n == 3
            assert _count_acls(
                db, document_id=str(doc), subject_kind="user"
            ) == 2
            assert _count_acls(
                db, document_id=str(doc), subject_kind="group"
            ) == 1
            assert _count_acls(
                db, document_id=str(doc), subject_kind="public"
            ) == 0
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_store_document_acl_public_writes_single_row():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            n = store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(public=True),
            )
            assert n == 1
            assert _count_acls(
                db, document_id=str(doc), subject_kind="public"
            ) == 1
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_store_document_acl_empty_writes_zero_rows():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            n = store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(),
            )
            assert n == 0
            assert _count_acls(db, document_id=str(doc)) == 0
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_store_document_acl_replaces_on_resync():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(user_ids={"u-1", "u-2"}),
            )
            assert _count_acls(db, document_id=str(doc)) == 2
            store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(user_ids={"u-3"}),
            )
            assert _count_acls(db, document_id=str(doc)) == 1
            db.commit()
    finally:
        db.rollback()
        db.close()


# ─────────────────────────────────────────────────────── fan-out chunks ──


@requires_postgres
def test_fanout_to_chunks_writes_per_chunk_rows():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            chunks = [_uuid.uuid4(), _uuid.uuid4(), _uuid.uuid4()]
            n = fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=chunks,
                acl=ResolvedAcl(user_ids={"u-a"}, group_ids={"g-a"}),
            )
            # 3 chunks × 2 principals = 6 rows
            assert n == 6
            for c in chunks:
                assert _count_acls(db, chunk_id=str(c)) == 2
            db.commit()
    finally:
        db.rollback()
        db.close()


# ─────────────────────────────────────────────────────── visibility ──


@requires_postgres
def test_visible_document_ids_only_includes_allowed():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            d_alice = _mk_doc(db, kb_id)
            d_bob = _mk_doc(db, kb_id)
            d_public = _mk_doc(db, kb_id)
            store_document_acl(
                db, kb_id=kb_id, document_id=d_alice,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            store_document_acl(
                db, kb_id=kb_id, document_id=d_bob,
                acl=ResolvedAcl(user_ids={"bob"}),
            )
            store_document_acl(
                db, kb_id=kb_id, document_id=d_public,
                acl=ResolvedAcl(public=True),
            )

            # Alice sees her doc + public.
            seen = visible_document_ids(db, kb_id=kb_id, user_id="alice")
            assert seen == {d_alice, d_public}
            # Bob sees his doc + public.
            seen_b = visible_document_ids(db, kb_id=kb_id, user_id="bob")
            assert seen_b == {d_bob, d_public}
            # Stranger sees only public.
            seen_s = visible_document_ids(
                db, kb_id=kb_id, user_id="stranger"
            )
            assert seen_s == {d_public}
            # Anonymous (no user) still sees public.
            seen_a = visible_document_ids(db, kb_id=kb_id, user_id=None)
            assert seen_a == {d_public}
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_visible_document_ids_group_membership_grants_access():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            d = _mk_doc(db, kb_id)
            store_document_acl(
                db, kb_id=kb_id, document_id=d,
                acl=ResolvedAcl(group_ids={"engineering"}),
            )
            # Wrong groups → not visible.
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="x",
                group_ids=["marketing"],
            ) == set()
            # Correct group → visible.
            assert visible_document_ids(
                db, kb_id=kb_id, user_id="x",
                group_ids=["engineering"],
            ) == {d}
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_visible_chunk_ids_after_fanout():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            chunks = [_uuid.uuid4(), _uuid.uuid4()]
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=chunks,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            seen = visible_chunk_ids(db, kb_id=kb_id, user_id="alice")
            assert seen == set(chunks)
            seen_other = visible_chunk_ids(
                db, kb_id=kb_id, user_id="bob"
            )
            assert seen_other == set()
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_delete_acl_for_document_clears_doc_and_chunks():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            uid = _mk_user(db)
            kb_id = _mk_kb(db, org, uid)
            doc = _mk_doc(db, kb_id)
            chunks = [_uuid.uuid4()]
            store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            fanout_to_chunks(
                db, kb_id=kb_id, document_id=doc, chunk_ids=chunks,
                acl=ResolvedAcl(user_ids={"alice"}),
            )
            assert _count_acls(db, document_id=str(doc)) == 2
            delete_acl_for_document(db, document_id=doc)
            assert _count_acls(db, document_id=str(doc)) == 0
            db.commit()
    finally:
        db.rollback()
        db.close()
