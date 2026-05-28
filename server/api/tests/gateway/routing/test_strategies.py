"""C1: one test per bundled routing strategy.

Pure-Python — no DB. Each strategy is exercised against a small candidate
list to verify it picks the expected route given a representative
``rules_json`` payload.
"""

from __future__ import annotations

import pytest

from ai_portal.gateway.routing.protocol import (
    ProviderModel,
    RoutingCtx,
    RoutingError,
)
from ai_portal.gateway.routing.strategies import (
    CapabilityMatchStrategy,
    CostOptimizedStrategy,
    CustomRulesStrategy,
    LatencyOptimizedStrategy,
    PriorityStrategy,
    StaticStrategy,
    WeightedStrategy,
)
from ai_portal.gateway.types import LLMRequest, Message, TextBlock


def _req(model: str = "smart", text: str = "hi") -> LLMRequest:
    return LLMRequest(
        model=model,
        messages=[Message(role="user", content=[TextBlock(text=text)])],
    )


def _candidates() -> list[ProviderModel]:
    return [
        ProviderModel(
            provider="anthropic",
            model_id="claude-sonnet-4-6",
            capabilities=frozenset({"chat", "tools", "vision"}),
            price_input_per_1k_cents=0.3,
            price_output_per_1k_cents=1.5,
            weight=3.0,
            p95_latency_ms=900.0,
        ),
        ProviderModel(
            provider="openai",
            model_id="gpt-4o",
            capabilities=frozenset({"chat", "tools", "vision", "json_schema"}),
            price_input_per_1k_cents=0.5,
            price_output_per_1k_cents=1.5,
            weight=1.0,
            p95_latency_ms=600.0,
        ),
        ProviderModel(
            provider="gemini",
            model_id="gemini-2.5-flash",
            capabilities=frozenset({"chat", "tools"}),
            price_input_per_1k_cents=0.075,
            price_output_per_1k_cents=0.3,
            weight=2.0,
            p95_latency_ms=400.0,
        ),
    ]


# ── static ──────────────────────────────────────────────────────────────────


def test_static_picks_configured_target():
    s = StaticStrategy()
    ctx = RoutingCtx(rules={"provider": "openai", "model_id": "gpt-4o"})
    pick = s.pick(_req(), _candidates(), ctx)
    assert pick.provider == "openai"
    assert pick.model_id == "gpt-4o"


def test_static_raises_when_target_missing():
    s = StaticStrategy()
    ctx = RoutingCtx(rules={"provider": "openai", "model_id": "gpt-9000"})
    with pytest.raises(RoutingError):
        s.pick(_req(), _candidates(), ctx)


# ── priority ────────────────────────────────────────────────────────────────


def test_priority_picks_first_healthy_in_order():
    s = PriorityStrategy()
    ctx = RoutingCtx(
        rules={
            "order": [
                {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
                {"provider": "openai", "model_id": "gpt-4o"},
            ]
        }
    )
    pick = s.pick(_req(), _candidates(), ctx)
    assert pick.provider == "anthropic"


def test_priority_skips_unhealthy():
    s = PriorityStrategy()
    cands = _candidates()
    cands[0] = ProviderModel(
        provider="anthropic", model_id="claude-sonnet-4-6", healthy=False
    )
    ctx = RoutingCtx(
        rules={
            "order": [
                {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
                {"provider": "openai", "model_id": "gpt-4o"},
            ]
        }
    )
    pick = s.pick(_req(), cands, ctx)
    assert pick.provider == "openai"


# ── weighted ────────────────────────────────────────────────────────────────


def test_weighted_picks_within_candidates_using_weights():
    s = WeightedStrategy()
    # Pinned seed → deterministic distribution check.
    chosen = []
    for seed in range(200):
        ctx = RoutingCtx(rules={}, seed=seed)
        chosen.append(s.pick(_req(), _candidates(), ctx).provider)
    assert {"anthropic", "openai", "gemini"} == set(chosen)
    # Anthropic has weight 3 — should be the modal pick across 200 seeds.
    anthropic_count = chosen.count("anthropic")
    assert anthropic_count >= chosen.count("openai")


def test_weighted_with_explicit_rule_weights_overrides_candidate_weights():
    s = WeightedStrategy()
    # Force pick of openai by giving it 100% weight via rules_json.
    ctx = RoutingCtx(
        rules={
            "weights": {"openai:gpt-4o": 1.0},
        },
        seed=0,
    )
    for seed in range(50):
        ctx = RoutingCtx(rules={"weights": {"openai:gpt-4o": 1.0}}, seed=seed)
        pick = s.pick(_req(), _candidates(), ctx)
        assert pick.provider == "openai"


# ── cost_optimized ──────────────────────────────────────────────────────────


def test_cost_optimized_picks_cheapest():
    s = CostOptimizedStrategy()
    pick = s.pick(_req(), _candidates(), RoutingCtx())
    assert pick.provider == "gemini"  # cheapest by input+output.


def test_cost_optimized_honors_output_weight_ratio():
    s = CostOptimizedStrategy()
    # Tilt ratio so output cost dominates 10:1 — gemini still wins (cheapest output).
    ctx = RoutingCtx(rules={"input_output_ratio": [1.0, 10.0]})
    pick = s.pick(_req(), _candidates(), ctx)
    assert pick.provider == "gemini"


# ── latency_optimized ───────────────────────────────────────────────────────


def test_latency_optimized_prefers_metrics_when_available():
    s = LatencyOptimizedStrategy()
    # Metrics override candidate.p95_latency_ms.
    ctx = RoutingCtx(
        metrics={
            ("anthropic", "claude-sonnet-4-6"): 100.0,
            ("openai", "gpt-4o"): 200.0,
            ("gemini", "gemini-2.5-flash"): 50.0,
        }
    )
    pick = s.pick(_req(), _candidates(), ctx)
    assert pick.provider == "gemini"


def test_latency_optimized_falls_back_to_candidate_p95_when_no_metrics():
    s = LatencyOptimizedStrategy()
    pick = s.pick(_req(), _candidates(), RoutingCtx())
    assert pick.provider == "gemini"  # 400ms p95 — lowest in candidates.


# ── capability_match ────────────────────────────────────────────────────────


def test_capability_match_filters_then_picks_first():
    s = CapabilityMatchStrategy()
    ctx = RoutingCtx(rules={"require": ["vision"]})
    pick = s.pick(_req(), _candidates(), ctx)
    assert pick.provider in {"anthropic", "openai"}  # vision-capable only.
    assert "vision" in pick.capabilities


def test_capability_match_raises_when_none_qualify():
    s = CapabilityMatchStrategy()
    ctx = RoutingCtx(rules={"require": ["pdf"]})
    with pytest.raises(RoutingError):
        s.pick(_req(), _candidates(), ctx)


# ── custom_rules ────────────────────────────────────────────────────────────


def test_custom_rules_first_matching_rule_wins():
    s = CustomRulesStrategy()
    # Rule 1: if model starts with "smart" → openai/gpt-4o.
    rules = {
        "rules": [
            {
                "if": {"model_startswith": "smart"},
                "then": {"provider": "openai", "model_id": "gpt-4o"},
            },
            {
                "if": {"contains_text": "code"},
                "then": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
            },
        ],
        "fallback": {"provider": "gemini", "model_id": "gemini-2.5-flash"},
    }
    ctx = RoutingCtx(rules=rules)
    pick = s.pick(_req(model="smart"), _candidates(), ctx)
    assert pick.provider == "openai"


def test_custom_rules_falls_back_to_default():
    s = CustomRulesStrategy()
    rules = {
        "rules": [
            {
                "if": {"contains_text": "code"},
                "then": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
            }
        ],
        "fallback": {"provider": "gemini", "model_id": "gemini-2.5-flash"},
    }
    ctx = RoutingCtx(rules=rules)
    pick = s.pick(_req(model="x", text="hello"), _candidates(), ctx)
    assert pick.provider == "gemini"


def test_custom_rules_match_on_text_content():
    s = CustomRulesStrategy()
    rules = {
        "rules": [
            {
                "if": {"contains_text": "code"},
                "then": {"provider": "anthropic", "model_id": "claude-sonnet-4-6"},
            }
        ],
        "fallback": {"provider": "gemini", "model_id": "gemini-2.5-flash"},
    }
    ctx = RoutingCtx(rules=rules)
    pick = s.pick(_req(text="write some code please"), _candidates(), ctx)
    assert pick.provider == "anthropic"


# ── empty candidate list ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "strategy",
    [
        StaticStrategy(),
        PriorityStrategy(),
        WeightedStrategy(),
        CostOptimizedStrategy(),
        LatencyOptimizedStrategy(),
        CapabilityMatchStrategy(),
        CustomRulesStrategy(),
    ],
)
def test_every_strategy_raises_on_empty_candidates(strategy):
    with pytest.raises(RoutingError):
        strategy.pick(_req(), [], RoutingCtx())
