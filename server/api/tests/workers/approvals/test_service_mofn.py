"""Service-level M-of-N tests for ``svc.decide_approval``.

Drives the service via a stub :class:`Session` so we cover the
persistence wiring (votes_json + approvers_decided_json + state) without
touching Postgres.
"""

from __future__ import annotations

import uuid as _uuid

import pytest

from ai_portal.workers import service as svc
from ai_portal.workers.model import WorkerApproval, WorkerTask


class _StubExecResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _StubSession:
    """Minimal Session stand-in that returns prebuilt rows by table."""

    def __init__(self, approval: WorkerApproval | None, task: WorkerTask | None):
        self._approval = approval
        self._task = task

    def execute(self, stmt):  # noqa: ANN001
        # We can't introspect the SQL Statement cheaply — use call order.
        # decide_approval calls execute(WorkerApproval) FIRST, then
        # get_task calls execute(WorkerTask). Use a flag to switch.
        if not getattr(self, "_approval_returned", False):
            self._approval_returned = True
            return _StubExecResult(self._approval)
        return _StubExecResult(self._task)

    def flush(self):
        return None


def _make_approval(
    *,
    required_approvers: int = 1,
    approver_ids: list[str] | None = None,
    state: str = "pending",
    votes: dict[str, str] | None = None,
) -> WorkerApproval:
    a = WorkerApproval()
    a.id = _uuid.uuid4()
    a.task_id = _uuid.uuid4()
    a.kind = "plan"
    a.required_approvers = required_approvers
    a.approver_ids_json = list(approver_ids or [])
    a.state = state
    a.votes_json = dict(votes or {})
    a.approvers_decided_json = []
    a.decision = None
    a.decided_at = None
    a.decided_by = None
    a.reason = None
    return a


def _make_task(org_id: _uuid.UUID) -> WorkerTask:
    t = WorkerTask()
    t.id = _uuid.uuid4()
    t.org_id = org_id
    return t


def _decide(approval, *, decision, decided_by, reason=None, org_id=None):
    org = org_id or _uuid.uuid4()
    task = _make_task(org)
    approval.task_id = task.id
    sess = _StubSession(approval=approval, task=task)
    return svc.decide_approval(
        sess,
        org_id=org,
        approval_id=approval.id,
        decision=decision,
        decided_by=decided_by,
        reason=reason,
    )


def test_1_of_1_first_approve_flips_to_approved() -> None:
    a = _make_approval(required_approvers=1)
    out = _decide(a, decision="approve", decided_by="alice")
    assert out.state == "approved"
    assert out.decision == "approve"
    assert out.decided_by == "alice"
    assert out.votes_json == {"alice": "approve"}
    trail = list(out.approvers_decided_json)
    assert len(trail) == 1
    assert trail[0]["user_id"] == "alice"
    assert trail[0]["decision"] == "approve"
    assert trail[0]["ts"]


def test_2_of_3_two_approvals_flip_state() -> None:
    a = _make_approval(
        required_approvers=2,
        approver_ids=["alice", "bob", "carol"],
    )
    out = _decide(a, decision="approve", decided_by="alice")
    assert out.state == "pending"
    assert out.votes_json == {"alice": "approve"}
    assert out.decision is None  # not yet terminal
    out = _decide(out, decision="approve", decided_by="bob")
    assert out.state == "approved"
    assert out.votes_json == {"alice": "approve", "bob": "approve"}
    assert out.decision == "approve"
    assert len(out.approvers_decided_json) == 2


def test_2_of_3_reject_short_circuits_to_rejected() -> None:
    a = _make_approval(
        required_approvers=2,
        approver_ids=["alice", "bob", "carol"],
    )
    out = _decide(a, decision="approve", decided_by="alice")
    assert out.state == "pending"
    out = _decide(out, decision="reject", decided_by="bob", reason="bad plan")
    assert out.state == "rejected"
    assert out.decision == "reject"
    assert out.reason == "bad plan"
    trail = list(out.approvers_decided_json)
    assert [v["decision"] for v in trail] == ["approve", "reject"]


def test_unauthorized_approver_raises_conflict() -> None:
    a = _make_approval(
        required_approvers=2,
        approver_ids=["alice", "bob"],
    )
    with pytest.raises(svc.ApprovalConflict):
        _decide(a, decision="approve", decided_by="eve")


def test_vote_on_terminal_raises_conflict() -> None:
    a = _make_approval(
        required_approvers=1,
        approver_ids=["alice"],
        state="approved",
        votes={"alice": "approve"},
    )
    with pytest.raises(svc.ApprovalConflict):
        _decide(a, decision="approve", decided_by="alice")


def test_legacy_null_required_approvers_acts_as_single_approver() -> None:
    """Backward compat: required_approvers=NULL behaves like 1-of-1."""
    a = _make_approval(required_approvers=0)
    out = _decide(a, decision="approve", decided_by="alice")
    assert out.state == "approved"


def test_missing_decided_by_raises_conflict() -> None:
    a = _make_approval(required_approvers=1)
    with pytest.raises(svc.ApprovalConflict):
        _decide(a, decision="approve", decided_by=None)
