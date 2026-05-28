"""Approval-policy evaluation.

A pool has one or more :class:`PolicyRule` entries per gate kind
(``plan``, ``pr``, ``budget``). Each rule is evaluated against a
:class:`PolicyContext`; if *any* rule fires, an approval is required
and the matching :class:`ApprovalRequired` describes why.

Rules supported (mirrors :class:`ai_portal.workers.types.ApprovalPolicy`):

- ``always``               — always require approval.
- ``never``                — explicitly do not require approval.
- ``on_cost_above``        — fire if est_cost_cents > threshold_cents.
- ``on_files_matching``    — fire if any changed file matches one of the
                              ``patterns`` (fnmatch).
- ``on_first_run_for_repo``— fire if this is the first task targeting
                              ``ctx.repo`` (callers pass ``prior_runs_for_repo``).

The ``never`` rule short-circuits: a policy set with ``never`` always
returns *no approval required* (its presence is an admin override).
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class PolicyRule:
    """One rule. ``kind`` selects the predicate; other fields are params."""

    kind: str  # "always" | "never" | "on_cost_above" | "on_files_matching" | "on_first_run_for_repo"
    threshold_cents: int | None = None
    patterns: tuple[str, ...] = ()


@dataclass
class PolicyContext:
    """Context the rules read from.

    ``changed_files`` is a list of paths the worker plans to modify.
    ``est_cost_cents`` is the estimate at evaluation time (planner output
    or current accumulated cost for the budget gate).
    ``prior_runs_for_repo`` is the count of completed runs the pool has
    on this repo before this one.
    """

    repo: str | None = None
    changed_files: tuple[str, ...] = ()
    est_cost_cents: int = 0
    prior_runs_for_repo: int = 0
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ApprovalRequired:
    """Result row when at least one rule fires."""

    rule_kind: str
    reason: str


def _rule_fires(rule: PolicyRule, ctx: PolicyContext) -> ApprovalRequired | None:
    if rule.kind == "always":
        return ApprovalRequired("always", "policy: always")
    if rule.kind == "never":
        return None
    if rule.kind == "on_cost_above":
        thr = rule.threshold_cents or 0
        if ctx.est_cost_cents > thr:
            return ApprovalRequired(
                "on_cost_above", f"cost {ctx.est_cost_cents}c > threshold {thr}c"
            )
        return None
    if rule.kind == "on_files_matching":
        for path in ctx.changed_files:
            for pat in rule.patterns:
                if fnmatch.fnmatch(path, pat):
                    return ApprovalRequired(
                        "on_files_matching", f"file {path} matches {pat}"
                    )
        return None
    if rule.kind == "on_first_run_for_repo":
        if ctx.prior_runs_for_repo == 0:
            return ApprovalRequired(
                "on_first_run_for_repo", f"first run for repo {ctx.repo}"
            )
        return None
    # Unknown rule kind: fail-open with no firing — the catalog gates names.
    return None


def evaluate_policies(
    rules: Iterable[PolicyRule], ctx: PolicyContext
) -> ApprovalRequired | None:
    """Return the first :class:`ApprovalRequired` that fires, or ``None``.

    ``never`` rules disable approval entirely — if any ``never`` is in the
    list, the function short-circuits to ``None``.
    """
    rules_list = list(rules)
    if any(r.kind == "never" for r in rules_list):
        return None
    for rule in rules_list:
        hit = _rule_fires(rule, ctx)
        if hit is not None:
            return hit
    return None
