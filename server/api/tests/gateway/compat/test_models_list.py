"""B5: GET /v1/models — unified OpenAI-shaped listing.

Returns models from ``gateway_models`` filtered to providers the requesting
org has credentials for.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

import ai_portal.auth.model  # noqa: F401  — register Org
import ai_portal.catalog.model  # noqa: F401  — register GatewayModel
import ai_portal.gateway.provider_credentials.model  # noqa: F401
from tests.conftest import requires_postgres


# ── helpers ──────────────────────────────────────────────────────────────


def _mk_org(db: Session, slug_prefix: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'ML') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug_prefix}-{org_id.hex[:8]}"},
    )
    return org_id


def _seed_gateway_model(
    db: Session,
    *,
    provider: str,
    model_id: str,
    display_name: str | None = None,
    capabilities: list[str] | None = None,
) -> None:
    """Upsert one ``gateway_models`` row — idempotent across reruns."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from ai_portal.catalog.model import GatewayModel

    db.execute(
        pg_insert(GatewayModel)
        .values(
            provider=provider,
            model_id=model_id,
            display_name=display_name or model_id,
            capabilities_json=capabilities or ["chat", "streaming"],
            price_input_per_1k_cents=300,
            price_output_per_1k_cents=1500,
            price_cache_read_per_1k_cents=30,
        )
        .on_conflict_do_nothing(
            constraint="uq_gateway_models_provider_model"
        )
    )


def _build_app(*, actor) -> FastAPI:
    from ai_portal.auth.deps import get_db
    from ai_portal.control_plane.deps import require_actor
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.compat.models_list import router

    app = FastAPI()
    app.include_router(router)

    def _db_override():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db_override
    app.dependency_overrides[require_actor] = lambda: actor
    return app


# ── tests ────────────────────────────────────────────────────────────────


@requires_postgres
def test_models_list_returns_openai_shape_for_org_providers():
    """Catalog has 2 fakeanthropic + 1 fakeopenai models. Org has only
    fakeanthropic creds. /v1/models returns the 2 fakeanthropic models in
    OpenAI list shape.

    Uses fake provider names so the catalog rows do not collide with
    real models added by sibling tests.
    """
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.provider_credentials.service import (
        ProviderCredentialService,
    )
    from ai_portal.rbac.service import Actor

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "ml-shape")
            _seed_gateway_model(
                db,
                provider="ml-shape-anthropic",
                model_id="claude-sonnet-4-6",
                capabilities=["chat", "streaming", "vision", "tools"],
            )
            _seed_gateway_model(
                db,
                provider="ml-shape-anthropic",
                model_id="claude-opus-4-7",
            )
            _seed_gateway_model(
                db,
                provider="ml-shape-openai",
                model_id="gpt-4o",
            )
            ProviderCredentialService(db).upsert(
                org_id=org_id, provider="ml-shape-anthropic", plaintext="sk-ant-xxx"
            )
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor))
    res = client.get("/v1/models")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["object"] == "list"
    ids = {m["id"] for m in body["data"]}
    assert ids == {"claude-sonnet-4-6", "claude-opus-4-7"}
    # OpenAI list shape.
    for m in body["data"]:
        assert m["object"] == "model"
        assert m["owned_by"] == "ml-shape-anthropic"
        assert isinstance(m["created"], int)


@requires_postgres
def test_models_list_empty_when_org_has_no_creds():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.rbac.service import Actor

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "ml-empty")
            _seed_gateway_model(db, provider="ml-empty-anthropic", model_id="claude-x")
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor))
    res = client.get("/v1/models")
    assert res.status_code == 200
    body = res.json()
    assert body["object"] == "list"
    assert body["data"] == []


@requires_postgres
def test_models_list_excludes_deprecated_models():
    """Models with ``deprecated_at`` set in the past must not appear."""
    from datetime import UTC, datetime, timedelta

    from ai_portal.catalog.model import GatewayModel
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.provider_credentials.service import (
        ProviderCredentialService,
    )
    from ai_portal.rbac.service import Actor

    from sqlalchemy.dialects.postgresql import insert as pg_insert

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "ml-dep")
            db.execute(
                pg_insert(GatewayModel)
                .values(
                    provider="ml-dep-openai",
                    model_id="gpt-3.5-turbo-dep",
                    display_name="gpt-3.5-turbo",
                    capabilities_json=["chat"],
                    price_input_per_1k_cents=50,
                    price_output_per_1k_cents=150,
                    price_cache_read_per_1k_cents=0,
                    deprecated_at=datetime.now(UTC) - timedelta(days=30),
                )
                .on_conflict_do_nothing(
                    constraint="uq_gateway_models_provider_model"
                )
            )
            _seed_gateway_model(db, provider="ml-dep-openai", model_id="gpt-4o-current")
            ProviderCredentialService(db).upsert(
                org_id=org_id, provider="ml-dep-openai", plaintext="sk-xxx"
            )
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor))
    res = client.get("/v1/models")
    assert res.status_code == 200
    ids = {m["id"] for m in res.json()["data"]}
    assert ids == {"gpt-4o-current"}


@requires_postgres
def test_models_list_filter_by_provider_query():
    """``?provider=openai`` returns only openai models, even if both have creds."""
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.provider_credentials.service import (
        ProviderCredentialService,
    )
    from ai_portal.rbac.service import Actor

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "ml-filter")
            _seed_gateway_model(db, provider="ml-filter-anthropic", model_id="claude-y")
            _seed_gateway_model(
                db, provider="ml-filter-openai", model_id="gpt-4o-mini-x"
            )
            svc = ProviderCredentialService(db)
            svc.upsert(org_id=org_id, provider="ml-filter-anthropic", plaintext="x")
            svc.upsert(org_id=org_id, provider="ml-filter-openai", plaintext="y")
            db.commit()
    finally:
        db.close()

    actor = Actor(org_id=org_id, kind="user", user_id=1)
    client = TestClient(_build_app(actor=actor))
    res = client.get("/v1/models?provider=ml-filter-openai")
    assert res.status_code == 200
    ids = {m["id"] for m in res.json()["data"]}
    assert ids == {"gpt-4o-mini-x"}
