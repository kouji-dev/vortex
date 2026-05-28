"""C1: api_keys.service — verify + revoke + rotate semantics."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401
import ai_portal.api_keys.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ApV') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_verify_returns_key_for_valid_plaintext_and_bumps_last_used():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-verify")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id, name="probe", scopes=["gateway:complete"]
            )
            assert created.key.last_used_at is None
            row = svc.verify(created.plaintext)
            assert row is not None
            assert row.id == created.key.id
            assert row.last_used_at is not None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_verify_rejects_bad_or_revoked_or_expired_key():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-reject")
            svc = ApiKeyService(db)
            # Unknown plaintext.
            assert svc.verify("ap_unknown_secret") is None
            # Plaintext that doesn't have the ap_ prefix is rejected immediately.
            assert svc.verify("not-an-ap-key") is None

            created = svc.create(org_id=org_id, name="r1")
            svc.revoke(org_id=org_id, key_id=created.key.id)
            assert svc.verify(created.plaintext) is None

            expired = svc.create(
                org_id=org_id,
                name="ex",
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
            assert svc.verify(expired.plaintext) is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_rotate_creates_new_key_and_revokes_old():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-rotate")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id, name="rotate-me", scopes=["gateway:complete"]
            )
            new_created, revoked_id = svc.rotate(
                org_id=org_id, key_id=created.key.id
            )
            # New key holds the same scopes + name + has fresh plaintext.
            assert new_created.plaintext != created.plaintext
            assert new_created.key.scopes_json == ["gateway:complete"]
            assert new_created.key.name == "rotate-me"
            # Old key revoked → verify fails.
            assert revoked_id == created.key.id
            assert svc.verify(created.plaintext) is None
            # New key valid.
            new_verified = svc.verify(new_created.plaintext)
            assert new_verified is not None
            assert new_verified.id == new_created.key.id
            db.commit()
    finally:
        db.rollback()
        db.close()
