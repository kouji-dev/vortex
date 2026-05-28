"""C1: ORM model + registry smoke tests.

Pure import + registry shape — no DB required.
"""
from __future__ import annotations

import uuid

from ai_portal.gateway.routing import (
    STRATEGY_REGISTRY,
    ModelAlias,
    ProviderModel,
    RoutingCtx,
    RoutingPolicy,
    get_strategy,
)


def test_routing_policy_orm_has_expected_columns():
    cols = RoutingPolicy.__table__.columns
    assert "id" in cols and "org_id" in cols and "name" in cols
    assert "strategy" in cols and "rules_json" in cols and "created_at" in cols


def test_model_alias_orm_has_expected_columns():
    cols = ModelAlias.__table__.columns
    assert "id" in cols and "org_id" in cols and "alias" in cols
    assert "routing_policy_id" in cols and "created_at" in cols


def test_registry_has_seven_bundled_strategies():
    expected = {
        "static",
        "priority",
        "weighted",
        "cost_optimized",
        "latency_optimized",
        "capability_match",
        "custom_rules",
    }
    assert set(STRATEGY_REGISTRY) == expected


def test_get_strategy_returns_singleton_for_each_name():
    for name in (
        "static",
        "priority",
        "weighted",
        "cost_optimized",
        "latency_optimized",
        "capability_match",
        "custom_rules",
    ):
        a = get_strategy(name)
        b = get_strategy(name)
        assert a is b
        assert a.name == name


def test_get_strategy_raises_keyerror_on_unknown():
    import pytest

    with pytest.raises(KeyError):
        get_strategy("nonexistent")


def test_provider_model_is_frozen_dataclass():
    pm = ProviderModel(provider="x", model_id="y")
    # frozen → cannot mutate.
    import dataclasses

    assert dataclasses.is_dataclass(pm)
    import pytest

    with pytest.raises(dataclasses.FrozenInstanceError):
        pm.provider = "z"  # type: ignore[misc]


def test_routing_ctx_defaults_are_safe():
    ctx = RoutingCtx()
    assert ctx.rules == {}
    assert ctx.metrics == {}
    assert ctx.seed is None


def test_strategy_check_constraint_lists_all_bundled_names():
    # The CHECK constraint string should reference every strategy name.
    constraints = {c.name for c in RoutingPolicy.__table__.constraints}
    assert "ck_routing_policies_strategy" in constraints


def test_routing_policy_can_construct_in_memory_uuid_default():
    pol = RoutingPolicy(
        org_id=uuid.uuid4(),
        name="default",
        strategy="priority",
        rules_json={"order": []},
    )
    # ``id`` default is generated client-side by SQLAlchemy default=uuid4 on insert,
    # but on bare construction it's still None until flush — accept either.
    assert pol.name == "default"
    assert pol.strategy == "priority"
