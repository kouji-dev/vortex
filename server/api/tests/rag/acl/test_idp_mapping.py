"""IdP mapping: source IDs → org user / group IDs (best-effort).

Postgres-backed because resolution hits ``users`` + ``scim_groups`` with an
``org_id`` filter.

Covers:
- Email resolves to ``users.id``.
- Unknown email → in ``unresolved``.
- Entra OID resolves to ``users.id``.
- UUID matches ``users.uuid`` when not bound to an Entra oid.
- Group external_id resolves to ``scim_groups.id``.
- Group display_name resolves as fallback.
- Public source ACL preserved.
- Cross-org users are NOT resolved (tenant isolation).
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy import text

import ai_portal.api_keys.model  # noqa: F401
import ai_portal.auth.model  # noqa: F401
import ai_portal.scim.model  # noqa: F401
from ai_portal.rag.acl.idp_mapping import (
    DefaultIdpAclProvider,
    IdpMapper,
)
from ai_portal.rag.connectors.protocol import AclSet
from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> _uuid.UUID:
    org_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ACL') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def _mk_user(
    db, org_id: _uuid.UUID, email: str,
    entra_oid: str | None = None,
    user_uuid: _uuid.UUID | None = None,
) -> int:
    u = user_uuid or _uuid.uuid4()
    row = db.execute(
        text(
            "INSERT INTO users (uuid, email, entra_object_id, org_id, role) "
            "VALUES (:uuid, :email, :oid, :org, 'member') RETURNING id"
        ),
        {
            "uuid": str(u),
            "email": email,
            "oid": entra_oid,
            "org": str(org_id),
        },
    ).first()
    return int(row[0])


def _mk_scim_group(
    db, org_id: _uuid.UUID, display_name: str,
    external_id: str | None = None,
) -> _uuid.UUID:
    ep_id = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO scim_endpoints "
            "(id, org_id, name, preset, token_hash, enabled) "
            "VALUES (:id, :org, :name, 'generic', :h, true)"
        ),
        {
            "id": str(ep_id),
            "org": str(org_id),
            "name": f"ep-{ep_id.hex[:6]}",
            "h": ep_id.hex,
        },
    )
    gid = _uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO scim_groups "
            "(id, endpoint_id, org_id, external_id, display_name) "
            "VALUES (:id, :ep, :org, :ext, :dn)"
        ),
        {
            "id": str(gid),
            "ep": str(ep_id),
            "org": str(org_id),
            "ext": external_id,
            "dn": display_name,
        },
    )
    return gid


@requires_postgres
def test_resolve_user_by_email():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-em")
            uid = _mk_user(db, org, email="alice@acme.test")
            mapper = IdpMapper(db=db, org_id=org)
            assert mapper.resolve_user("alice@acme.test") == str(uid)
            assert mapper.resolve_user("ghost@acme.test") is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_resolve_user_by_entra_oid():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-oid")
            oid = str(_uuid.uuid4())
            uid = _mk_user(
                db, org, email=f"u-{oid[:6]}@acme.test", entra_oid=oid
            )
            mapper = IdpMapper(db=db, org_id=org)
            assert mapper.resolve_user(oid) == str(uid)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_resolve_user_by_internal_uuid_fallback():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-uuid")
            user_uuid = _uuid.uuid4()
            uid = _mk_user(
                db, org,
                email=f"u-{user_uuid.hex[:6]}@acme.test",
                user_uuid=user_uuid,
            )
            mapper = IdpMapper(db=db, org_id=org)
            assert mapper.resolve_user(str(user_uuid)) == str(uid)
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_resolve_group_by_external_id_then_display_name():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-grp")
            ext = f"ext-{_uuid.uuid4().hex[:8]}"
            gid_ext = _mk_scim_group(
                db, org, display_name="Engineering", external_id=ext
            )
            gid_dn = _mk_scim_group(
                db, org, display_name="Marketing", external_id=None
            )
            mapper = IdpMapper(db=db, org_id=org)
            assert mapper.resolve_group(ext) == str(gid_ext)
            assert mapper.resolve_group("Marketing") == str(gid_dn)
            assert mapper.resolve_group("Nope") is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_cross_org_isolation():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_a = _mk_org(db, "acl-tA")
            org_b = _mk_org(db, "acl-tB")
            _mk_user(db, org_a, email="bob@acme.test")
            mapper_b = IdpMapper(db=db, org_id=org_b)
            assert mapper_b.resolve_user("bob@acme.test") is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_map_acls_collects_unresolved():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-set")
            uid = _mk_user(db, org, email="carol@acme.test")
            gid = _mk_scim_group(
                db, org, display_name="Sales",
                external_id="grp-ext-sales",
            )
            mapper = IdpMapper(db=db, org_id=org)
            acl = mapper.map_acls(
                AclSet(
                    user_ids={"carol@acme.test", "ghost@acme.test"},
                    group_ids={"grp-ext-sales", "grp-ext-unknown"},
                    public=False,
                )
            )
            assert acl.user_ids == {str(uid)}
            assert acl.group_ids == {str(gid)}
            assert acl.unresolved == {
                "user:ghost@acme.test",
                "group:grp-ext-unknown",
            }
            assert acl.public is False
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_public_acl_preserved():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-pub")
            mapper = IdpMapper(db=db, org_id=org)
            acl = mapper.map_acls(AclSet(public=True))
            assert acl.public is True
            assert acl.is_empty() is False
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
@pytest.mark.asyncio
async def test_default_provider_wraps_idp_mapper():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org = _mk_org(db, "acl-def")
            uid = _mk_user(db, org, email="dave@acme.test")
            provider = DefaultIdpAclProvider(db=db)
            assert provider.connector_kind == "default"
            acl = await provider.map(
                AclSet(user_ids={"dave@acme.test"}),
                org_id=str(org),
            )
            assert acl.user_ids == {str(uid)}
            db.commit()
    finally:
        db.rollback()
        db.close()
