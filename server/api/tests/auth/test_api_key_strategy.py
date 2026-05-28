"""C2: ap_ bearer auth strategy resolves Actor(kind="api_key").

Covers:
- A valid ``ap_`` plaintext → ``Actor(kind="api_key", org_id=..., user_id=...)``.
- A revoked / expired / unknown token → ``None`` (strategy declines; resolver
  caller turns this into 401).
- A non-``ap_`` token short-circuits to ``None`` so the resolver chain can
  fall through.
"""

from __future__ import annotations

import uuid

from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401
import ai_portal.api_keys.model  # noqa: F401

from tests.conftest import requires_postgres


def _mk_org(db, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text("INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ApS') ON CONFLICT DO NOTHING"),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def test_looks_like_api_key_token_discriminator():
    from ai_portal.auth.strategies.api_key import looks_like_api_key_token

    assert looks_like_api_key_token("ap_abc")
    assert not looks_like_api_key_token("aip_abc")
    assert not looks_like_api_key_token("Bearer foo")
    assert not looks_like_api_key_token("")


def test_non_ap_token_returns_none_without_db_hit():
    # The strategy short-circuits on the prefix check, so it must not require
    # a live DB to reject a non-ap_ token. We pass ``db=None`` to assert that
    # no DB call is made for non-matching tokens.
    from ai_portal.auth.strategies.api_key import actor_for_api_key_token

    assert actor_for_api_key_token(None, "aip_legacy_token") is None  # type: ignore[arg-type]
    assert actor_for_api_key_token(None, "") is None  # type: ignore[arg-type]


@requires_postgres
def test_ap_bearer_resolves_actor_with_org_and_user_id():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.auth.strategies.api_key import actor_for_api_key_token
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-strat")
            svc = ApiKeyService(db)
            created = svc.create(
                org_id=org_id,
                name="bearer-test",
                scopes=["gateway:complete"],
                actor_user_id=None,  # service key
            )
            actor = actor_for_api_key_token(db, created.plaintext)
            assert actor is not None
            assert actor.kind == "api_key"
            assert actor.org_id == org_id
            assert actor.user_id is None
            assert actor.api_key_id is not None
            db.commit()
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_ap_bearer_rejects_revoked_token():
    from ai_portal.api_keys.service import ApiKeyService
    from ai_portal.auth.strategies.api_key import actor_for_api_key_token
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "apk-strat-revoke")
            svc = ApiKeyService(db)
            created = svc.create(org_id=org_id, name="will-be-revoked")
            svc.revoke(org_id=org_id, key_id=created.key.id)
            assert actor_for_api_key_token(db, created.plaintext) is None
            db.commit()
    finally:
        db.rollback()
        db.close()
