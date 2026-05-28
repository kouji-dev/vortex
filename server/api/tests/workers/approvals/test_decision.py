"""Tests for the M-of-N decision tracker."""

from __future__ import annotations

import pytest

from ai_portal.workers.approvals.decision import (
    AlreadyDecided,
    DecisionResult,
    NotAuthorized,
    record_decision,
)


def _empty() -> DecisionResult:
    return DecisionResult(state="pending")


def test_single_approve_resolves_when_m_is_1() -> None:
    out = record_decision(
        current=_empty(),
        approver_id="alice",
        decision="approve",
        required_approvers=1,
        allowed_approver_ids=None,
    )
    assert out.state == "approved"
    assert out.approve_count == 1


def test_single_reject_resolves_immediately() -> None:
    out = record_decision(
        current=_empty(),
        approver_id="alice",
        decision="reject",
        required_approvers=2,
        allowed_approver_ids=("alice", "bob"),
        reason="nope",
    )
    assert out.state == "rejected"
    assert out.reject_count == 1
    assert out.reason == "nope"


def test_two_of_three_approve_resolves() -> None:
    s = _empty()
    s = record_decision(
        current=s, approver_id="a", decision="approve",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.state == "pending"
    s = record_decision(
        current=s, approver_id="b", decision="approve",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.state == "approved"
    assert s.approve_count == 2


def test_same_approver_replaces_own_vote_while_pending() -> None:
    s = _empty()
    s = record_decision(
        current=s, approver_id="a", decision="approve",
        required_approvers=3, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.approve_count == 1
    s = record_decision(
        current=s, approver_id="a", decision="approve",
        required_approvers=3, allowed_approver_ids=("a", "b", "c"),
    )
    # still only one distinct vote
    assert s.approve_count == 1


def test_vote_on_resolved_raises() -> None:
    s = DecisionResult(state="approved", votes={"a": "approve"})
    with pytest.raises(AlreadyDecided):
        record_decision(
            current=s, approver_id="b", decision="approve",
            required_approvers=2, allowed_approver_ids=None,
        )


def test_unauthorized_approver_raises() -> None:
    with pytest.raises(NotAuthorized):
        record_decision(
            current=_empty(), approver_id="eve", decision="approve",
            required_approvers=1, allowed_approver_ids=("alice", "bob"),
        )


def test_open_allow_list_anyone_can_vote() -> None:
    out = record_decision(
        current=_empty(), approver_id="random", decision="approve",
        required_approvers=1, allowed_approver_ids=None,
    )
    assert out.state == "approved"


def test_invalid_decision_string_raises() -> None:
    with pytest.raises(ValueError):
        record_decision(
            current=_empty(), approver_id="a", decision="maybe",
            required_approvers=1, allowed_approver_ids=None,
        )


# ── M-of-N scenarios (spec) ────────────────────────────────────


def test_1_of_1_resolves_on_first_approve() -> None:
    s = record_decision(
        current=_empty(), approver_id="solo", decision="approve",
        required_approvers=1, allowed_approver_ids=None,
    )
    assert s.state == "approved"
    assert s.approve_count == 1
    assert s.reject_count == 0


def test_2_of_3_approve_path_pending_then_approved() -> None:
    s = _empty()
    s = record_decision(
        current=s, approver_id="a", decision="approve",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.state == "pending"
    assert s.approve_count == 1
    s = record_decision(
        current=s, approver_id="b", decision="approve",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.state == "approved"
    assert s.approve_count == 2
    # third vote must be rejected — already terminal
    with pytest.raises(AlreadyDecided):
        record_decision(
            current=s, approver_id="c", decision="approve",
            required_approvers=2, allowed_approver_ids=("a", "b", "c"),
        )


def test_2_of_3_one_reject_short_circuits() -> None:
    s = _empty()
    s = record_decision(
        current=s, approver_id="a", decision="approve",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
    )
    assert s.state == "pending"
    s = record_decision(
        current=s, approver_id="b", decision="reject",
        required_approvers=2, allowed_approver_ids=("a", "b", "c"),
        reason="risk",
    )
    assert s.state == "rejected"
    assert s.reject_count == 1
    assert s.approve_count == 1
    assert s.reason == "risk"
    # further votes blocked
    with pytest.raises(AlreadyDecided):
        record_decision(
            current=s, approver_id="c", decision="approve",
            required_approvers=2, allowed_approver_ids=("a", "b", "c"),
        )


def test_legacy_required_approvers_zero_treated_as_one() -> None:
    """Backward compat: NULL/0 required_approvers behaves as 1-of-1."""
    s = record_decision(
        current=_empty(), approver_id="a", decision="approve",
        required_approvers=0, allowed_approver_ids=None,
    )
    assert s.state == "approved"
