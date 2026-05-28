"""C1: api_keys.service — create returns plaintext once + stores hash only."""

from __future__ import annotations

import uuid

from sqlalchemy import text

# Ensure all referenced tables are loaded before flush.
import ai_portal.auth.model  # noqa: F401
import ai_portal.api_keys.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ApK') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


@requires_postgres
def test_create_key_returns_plaintext_once_and_hashes_secret():
    from ai_portal.api_keys.service import (
        ApiKeyService,
        PLAINTEXT_PREFIX,
        hash_plaintext,
    )
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-create")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id,
                name="dev",
                scopes=["gateway:complete"],
            )
            assert created.plaintext.startswith(PLAINTEXT_PREFIX)
            # Plaintext is a fresh secret each call.
            other = svc.create(
                org_id=org_id,
                name="dev2",
                scopes=["gateway:complete"],
            )
            assert other.plaintext != created.plaintext

            # Stored row carries the hash, NOT the plaintext anywhere.
            assert created.key.hash == hash_plaintext(created.plaintext)
            assert created.plaintext not in (
                created.key.hash or "",
                created.key.prefix or "",
                created.key.name or "",
            )
            # Prefix is a short identifier.
            assert created.key.prefix.startswith(PLAINTEXT_PREFIX)
            assert len(created.key.prefix) <= 16
            # Scopes round-tripped.
            assert created.key.scopes_json == ["gateway:complete"]
            assert created.key.revoked_at is None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_list_returns_keys_for_org_only():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_a = _mk_org(db, "apk-list-a")
            org_b = _mk_org(db, "apk-list-b")
            svc = ApiKeyService(db)
            svc.create(org_id=org_a, name="a-1")
            svc.create(org_id=org_a, name="a-2")
            svc.create(org_id=org_b, name="b-1")

            a_keys = svc.list_for_org(org_a)
            b_keys = svc.list_for_org(org_b)
            assert {k.name for k in a_keys} == {"a-1", "a-2"}
            assert {k.name for k in b_keys} == {"b-1"}
            db.commit()
    finally:
        db.rollback()
        db.close()
