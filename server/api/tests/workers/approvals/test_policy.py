"""Tests for approval policy evaluation."""

from __future__ import annotations

from ai_portal.workers.approvals.policy import (
    PolicyContext,
    PolicyRule,
    evaluate_policies,
)


def test_always_fires() -> None:
    res = evaluate_policies([PolicyRule("always")], PolicyContext())
    assert res is not None and res.rule_kind == "always"


def test_never_short_circuits_other_rules() -> None:
    rules = [PolicyRule("always"), PolicyRule("never")]
    assert evaluate_policies(rules, PolicyContext()) is None


def test_cost_above_threshold() -> None:
    rule = PolicyRule("on_cost_above", threshold_cents=500)
    assert evaluate_policies([rule], PolicyContext(est_cost_cents=600)) is not None
    assert evaluate_policies([rule], PolicyContext(est_cost_cents=400)) is None
    # boundary: > not >=
    assert evaluate_policies([rule], PolicyContext(est_cost_cents=500)) is None


def test_files_matching_glob() -> None:
    rule = PolicyRule("on_files_matching", patterns=("infra/**", "*.lock"))
    ctx = PolicyContext(changed_files=("src/app.py", "infra/main.tf"))
    res = evaluate_policies([rule], ctx)
    assert res is not None
    assert "main.tf" in res.reason


def test_files_matching_no_match() -> None:
    rule = PolicyRule("on_files_matching", patterns=("infra/**",))
    ctx = PolicyContext(changed_files=("src/app.py", "README.md"))
    assert evaluate_policies([rule], ctx) is None


def test_first_run_for_repo() -> None:
    rule = PolicyRule("on_first_run_for_repo")
    assert evaluate_policies(
        [rule], PolicyContext(repo="acme/api", prior_runs_for_repo=0)
    ) is not None
    assert evaluate_policies(
        [rule], PolicyContext(repo="acme/api", prior_runs_for_repo=1)
    ) is None


def test_unknown_rule_does_not_fire() -> None:
    rule = PolicyRule("not_a_real_rule")
    assert evaluate_policies([rule], PolicyContext()) is None


def test_empty_policy_list_no_approval_needed() -> None:
    assert evaluate_policies([], PolicyContext()) is None


def test_first_matching_rule_wins() -> None:
    rules = [
        PolicyRule("on_cost_above", threshold_cents=100),
        PolicyRule("always"),
    ]
    res = evaluate_policies(rules, PolicyContext(est_cost_cents=200))
    assert res is not None
    assert res.rule_kind == "on_cost_above"
