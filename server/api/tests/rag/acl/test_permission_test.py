"""Permission-test endpoint + service.

Covers:
- Three users with disjoint ACLs → each sees only their own doc(s).
- Public docs are visible to everyone.
- Group membership loaded from SCIM grants access.
- ``group_ids_override`` lets operators probe hypothetical groups.
- Sample is truncated to ``sample_limit`` and ordered by document id.
- Empty allow set → zero count, empty sample.
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.knowledge_base.model  # noqa: F401
import ai_portal.scim.model  # noqa: F401
from ai_portal.rag.acl.permission_test import run_permission_test
from ai_portal.rag.acl.protocol import ResolvedAcl
from ai_portal.rag.acl.service import store_document_acl
from tests.conftest import requires_postgres


def _mk_org(db) -> _uuid.UUID:
    oid = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES "
            "(:id, :slug, 'PT') ON CONFLICT DO NOTHING"
        ),
        {"id": str(oid), "slug": f"pt-{oid.hex[:8]}"},
    )
    return oid


def _mk_user(db, org_id: _uuid.UUID, email: str) -> int:
    u = _uuid.uuid4()
    row = db.execute(
        text(
            "INSERT INTO users (uuid, email, org_id, role) "
            "VALUES (:u, :e, :o, 'member') RETURNING id"
        ),
        {"u": str(u), "e": email, "o": str(org_id)},
    ).first()
    return int(row[0])


def _mk_kb(db, org_id: _uuid.UUID, owner_id: int) -> int:
    row = db.execute(
        text(
            "INSERT INTO knowledge_bases "
            "(org_id, name, description, owner_user_id) "
            "VALUES (:o, :n, '', :ow) RETURNING id"
        ),
        {
            "o": str(org_id),
            "n": f"pt-kb-{_uuid.uuid4().hex[:6]}",
            "ow": owner_id,
        },
    ).first()
    return int(row[0])


def _mk_doc(db, kb_id: int, title: str) -> _uuid.UUID:
    did = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO kb_documents (id, kb_id, source_uri, title) "
            "VALUES (:id, :kb, :su, :t)"
        ),
        {
            "id": str(did),
            "kb": kb_id,
            "su": f"file:///{did.hex[:8]}",
            "t": title,
        },
    )
    return did


def _mk_scim_group_for_user(
    db, org_id: _uuid.UUID, user_id: int, display: str
) -> _uuid.UUID:
    ep_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO scim_endpoints "
            "(id, org_id, name, preset, token_hash, enabled) "
            "VALUES (:id, :o, :n, 'generic', :h, true)"
        ),
        {
            "id": str(ep_id),
            "o": str(org_id),
            "n": f"ep-{ep_id.hex[:6]}",
            "h": ep_id.hex,
        },
    )
    gid = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO scim_groups "
            "(id, endpoint_id, org_id, external_id, display_name) "
            "VALUES (:id, :ep, :o, :ext, :dn)"
        ),
        {
            "id": str(gid),
            "ep": str(ep_id),
            "o": str(org_id),
            "ext": display,
            "dn": display,
        },
    )
    db.execute(
        text(
            "INSERT INTO scim_group_members (group_id, org_id, user_id) "
            "VALUES (:g, :o, :u)"
        ),
        {"g": str(gid), "o": str(org_id), "u": user_id},
    )
    return gid


@requires_postgres
def test_three_users_see_only_their_own_docs():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            alice = _mk_user(db, org, "alice@x.test")
            bob = _mk_user(db, org, "bob@x.test")
            carol = _mk_user(db, org, "carol@x.test")
            kb_id = _mk_kb(db, org, alice)

            d_a = _mk_doc(db, kb_id, "Alice memo")
            d_b = _mk_doc(db, kb_id, "Bob memo")
            d_c = _mk_doc(db, kb_id, "Carol memo")
            d_pub = _mk_doc(db, kb_id, "Public memo")

            store_document_acl(
                db, kb_id=kb_id, document_id=d_a,
                acl=ResolvedAcl(user_ids={str(alice)}),
            )
            store_document_acl(
                db, kb_id=kb_id, document_id=d_b,
                acl=ResolvedAcl(user_ids={str(bob)}),
            )
            store_document_acl(
                db, kb_id=kb_id, document_id=d_c,
                acl=ResolvedAcl(user_ids={str(carol)}),
            )
            store_document_acl(
                db, kb_id=kb_id, document_id=d_pub,
                acl=ResolvedAcl(public=True),
            )

            r_alice = run_permission_test(
                db, kb_id=kb_id, user_id=alice,
            )
            r_bob = run_permission_test(db, kb_id=kb_id, user_id=bob)
            r_carol = run_permission_test(
                db, kb_id=kb_id, user_id=carol,
            )

            # Each user sees their own doc + the public one.
            assert r_alice.visible_document_count == 2
            assert r_bob.visible_document_count == 2
            assert r_carol.visible_document_count == 2

            alice_titles = {s.title for s in r_alice.sample}
            assert alice_titles == {"Alice memo", "Public memo"}
            bob_titles = {s.title for s in r_bob.sample}
            assert bob_titles == {"Bob memo", "Public memo"}
            carol_titles = {s.title for s in r_carol.sample}
            assert carol_titles == {"Carol memo", "Public memo"}
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_group_membership_loaded_from_scim():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            dave = _mk_user(db, org, "dave@x.test")
            kb_id = _mk_kb(db, org, dave)
            gid = _mk_scim_group_for_user(db, org, dave, "Engineering")
            doc = _mk_doc(db, kb_id, "Eng spec")
            store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(group_ids={str(gid)}),
            )

            outcome = run_permission_test(
                db, kb_id=kb_id, user_id=dave,
            )
            assert outcome.visible_document_count == 1
            assert str(gid) in outcome.resolved_group_ids
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_group_ids_override_replaces_scim_lookup():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            eve = _mk_user(db, org, "eve@x.test")
            kb_id = _mk_kb(db, org, eve)
            doc = _mk_doc(db, kb_id, "Hyp")
            store_document_acl(
                db, kb_id=kb_id, document_id=doc,
                acl=ResolvedAcl(group_ids={"hypothetical-grp"}),
            )

            # Without override → eve is in no groups, doc invisible.
            assert run_permission_test(
                db, kb_id=kb_id, user_id=eve,
            ).visible_document_count == 0

            # With override → matched.
            outcome = run_permission_test(
                db, kb_id=kb_id, user_id=eve,
                group_ids_override=["hypothetical-grp"],
            )
            assert outcome.visible_document_count == 1
            assert outcome.resolved_group_ids == ["hypothetical-grp"]
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_sample_limit_truncates():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            frank = _mk_user(db, org, "frank@x.test")
            kb_id = _mk_kb(db, org, frank)
            # 5 public docs.
            for i in range(5):
                d = _mk_doc(db, kb_id, f"Doc {i}")
                store_document_acl(
                    db, kb_id=kb_id, document_id=d,
                    acl=ResolvedAcl(public=True),
                )

            outcome = run_permission_test(
                db, kb_id=kb_id, user_id=frank, sample_limit=2,
            )
            assert outcome.visible_document_count == 5
            assert len(outcome.sample) == 2
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_empty_allow_set_returns_zero():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db)
            ghost = _mk_user(db, org, "ghost@x.test")
            kb_id = _mk_kb(db, org, ghost)
            d = _mk_doc(db, kb_id, "Private")
            store_document_acl(
                db, kb_id=kb_id, document_id=d,
                acl=ResolvedAcl(user_ids={"some-other-user"}),
            )

            outcome = run_permission_test(
                db, kb_id=kb_id, user_id=ghost,
            )
            assert outcome.visible_document_count == 0
            assert outcome.sample == []
            db.commit()
    finally:
        db.rollback()
        db.close()
