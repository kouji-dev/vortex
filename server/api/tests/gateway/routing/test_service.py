"""C3: service-level alias resolution + header override.

End-to-end through :class:`RoutingService.resolve` (the pure-Python wiring;
no provider invocation here — that's exercised in compat-endpoint tests).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

import ai_portal.auth.model  # noqa: F401 — register Org for FK
import ai_portal.gateway.routing.model  # noqa: F401 — register tables
from ai_portal.gateway.routing.protocol import ProviderModel, RoutingError
from ai_portal.gateway.routing.service import (
    RoutingResolution,
    RoutingService,
)
from ai_portal.gateway.types import LLMRequest, Message, TextBlock
from tests.conftest import requires_postgres


def _req(model: str = "smart") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[Message(role="user", content=[TextBlock(text="hi")])],
    )


def _cands() -> list[ProviderModel]:
    return [
        ProviderModel(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            price_input_per_1k_cents=0.3,
            price_output_per_1k_cents=1.5,
        ),
        ProviderModel(
            provider="openai",
            model_id="gpt-4o",
            price_input_per_1k_cents=0.5,
            price_output_per_1k_cents=1.5,
        ),
        ProviderModel(
            provider="gemini",
            model_id="gemini-2.5-flash",
            price_input_per_1k_cents=0.075,
            price_output_per_1k_cents=0.3,
        ),
    ]


def _mk_org(db, slug: str) -> uuid.UUID:
    org_id = uuid.uuid4()
    db.execute(
        text(
            "INSERT INTO orgs (id, slug, name) VALUES (:id, :slug, 'GW-Route') "
            "ON CONFLICT DO NOTHING"
        ),
        {"id": str(org_id), "slug": f"{slug}-{org_id.hex[:8]}"},
    )
    return org_id


# ── concrete model id passes through ────────────────────────────────────────


def test_concrete_model_id_resolves_directly_no_db_needed():
    """No DB lookup needed when ``model`` is a concrete provider+model match."""
    svc = RoutingService(db=None)  # type: ignore[arg-type]
    res = svc.resolve(
        req=_req(model="claude-sonnet-4-6"),
        org_id=uuid.uuid4(),
        candidates=_cands(),
    )
    assert isinstance(res, RoutingResolution)
    assert res.candidate.model_id == "claude-sonnet-4-6"
    assert res.policy_id is None
    assert res.alias is None


# ── DB-backed: alias + policy resolution ────────────────────────────────────


@requires_postgres
def test_alias_resolves_to_policy_and_strategy_picks_concrete():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gw-route-alias")
            policy = RoutingPolicy(
                org_id=org_id,
                name="smart-default",
                strategy="cost_optimized",
                rules_json={},
            )
            db.add(policy)
            db.flush()
            db.add(
                ModelAlias(
                    org_id=org_id,
                    alias="smart",
                    routing_policy_id=policy.id,
                )
            )
            db.commit()

            svc = RoutingService(db=db)
            res = svc.resolve(
                req=_req(model="smart"),
                org_id=org_id,
                candidates=_cands(),
            )
            # cost_optimized → gemini (cheapest)
            assert res.candidate.provider == "gemini"
            assert res.alias == "smart"
            assert res.policy_id == policy.id
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_header_override_picks_alternative_policy():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal
    from ai_portal.gateway.routing.model import ModelAlias, RoutingPolicy

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gw-route-override")
            cost_policy = RoutingPolicy(
                org_id=org_id,
                name="cheapest",
                strategy="cost_optimized",
                rules_json={},
            )
            priority_policy = RoutingPolicy(
                org_id=org_id,
                name="anthropic-first",
                strategy="priority",
                rules_json={
                    "order": [
                        {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
                    ]
                },
            )
            db.add_all([cost_policy, priority_policy])
            db.flush()
            db.add(
                ModelAlias(
                    org_id=org_id,
                    alias="smart",
                    routing_policy_id=cost_policy.id,
                )
            )
            db.commit()

            svc = RoutingService(db=db)
            # No override → cost_optimized → gemini
            res_default = svc.resolve(
                req=_req(model="smart"), org_id=org_id, candidates=_cands()
            )
            assert res_default.candidate.provider == "gemini"

            # With override → priority_policy → anthropic
            res_override = svc.resolve(
                req=_req(model="smart"),
                org_id=org_id,
                candidates=_cands(),
                policy_override="anthropic-first",
            )
            assert res_override.candidate.provider == "anthropic"
            assert res_override.policy_id == priority_policy.id
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_unknown_alias_falls_through_to_concrete_match_or_raises():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gw-route-unknown")
            svc = RoutingService(db=db)

            # "claude-sonnet-4-6" is a concrete candidate → resolves directly.
            res = svc.resolve(
                req=_req(model="claude-sonnet-4-6"),
                org_id=org_id,
                candidates=_cands(),
            )
            assert res.candidate.model_id == "claude-sonnet-4-6"

            # "unknown-model" has no alias and no candidate → RoutingError.
            with pytest.raises(RoutingError):
                svc.resolve(
                    req=_req(model="unknown-model"),
                    org_id=org_id,
                    candidates=_cands(),
                )
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_policy_override_to_nonexistent_policy_raises():
    from ai_portal.core.db.rls import bypass_rls
    from ai_portal.core.db.session import SessionLocal

    db = SessionLocal()
    try:
        with bypass_rls(db):
            org_id = _mk_org(db, "gw-route-bad-override")
            svc = RoutingService(db=db)
            with pytest.raises(RoutingError):
                svc.resolve(
                    req=_req(model="claude-sonnet-4-6"),
                    org_id=org_id,
                    candidates=_cands(),
                    policy_override="does-not-exist",
                )
    finally:
        db.rollback()
        db.close()
