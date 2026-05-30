"""api_keys — per-key rate limits set on create, edited via update, kept on rotate."""

from __future__ import annotations

import uuid

from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401
import ai_portal.api_keys.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'RlOrg') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_create_persists_rate_limits():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-create")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id,
                name="limited",
                rate_limits={"rpm": 60, "tpm": 100000, "concurrency": 4},
            )
            assert created.key.rate_limits_json == {
                "rpm": 60,
                "tpm": 100000,
                "concurrency": 4,
            }
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_update_edits_and_clears_rate_limits():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-edit")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id, name="k", rate_limits={"rpm": 10}
            )
            kid = created.key.id

            # Edit limits.
            row = svc.update(
                org_id=org_id,
                key_id=kid,
                rate_limits={"rpm": 30, "tpm": 5000},
                rate_limits_set=True,
            )
            assert row.rate_limits_json == {"rpm": 30, "tpm": 5000}

            # Clear limits (provided as empty/None).
            row = svc.update(
                org_id=org_id, key_id=kid, rate_limits=None, rate_limits_set=True
            )
            assert row.rate_limits_json is None

            # Name-only edit leaves limits untouched.
            svc.update(
                org_id=org_id,
                key_id=kid,
                rate_limits={"rpm": 7},
                rate_limits_set=True,
            )
            row = svc.update(org_id=org_id, key_id=kid, name="renamed")
            assert row.name == "renamed"
            assert row.rate_limits_json == {"rpm": 7}
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_rotate_carries_rate_limits():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "rl-rotate")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id, name="k", rate_limits={"rpm": 25, "concurrency": 2}
            )
            new_created, _revoked = svc.rotate(org_id=org_id, key_id=created.key.id)
            assert new_created.key.rate_limits_json == {"rpm": 25, "concurrency": 2}
            db.commit()
    finally:
        db.rollback()
        db.close()
