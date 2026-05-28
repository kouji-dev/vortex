"""Tests for the decide_handler — DI'd I/O so no DB required."""

from __future__ import annotations

import pytest

from ai_portal.workers.approvals.decision import AlreadyDecided, NotAuthorized
from ai_portal.workers.approvals.router import (
    DecideRequest,
    decide_handler,
)


class _Row:
    def __init__(self, **kw):
        self.id = kw.get("id", "approval-1")
        self.state = kw.get("state", "pending")
        self.required_approvers = kw.get("required_approvers", 1)
        self.approver_ids_json = kw.get("approver_ids_json", [])
        self.votes_json = kw.get("votes_json", {})
        self.task_id = kw.get("task_id", "task-1")
        self.kind = kw.get("kind", "plan")
        self.org_id = kw.get("org_id", "org-1")


@pytest.mark.asyncio
async def test_decide_approve_path_emits_audit() -> None:
    row = _Row(required_approvers=1)
    saved = {}
    audited = []

    def load(_id):
        return row

    def save(r, result):
        saved["r"] = r
        saved["result"] = result
        r.state = result.state
        r.votes_json = result.votes
        return r

    async def audit(**kw):
        audited.append(kw)

    resp = await decide_handler(
        approval_id="approval-1",
        actor_id="alice",
        body=DecideRequest(decision="approve"),
        load_approval=load,
        save_approval=save,
        emit_audit=audit,
    )
    assert resp.state == "approved"
    assert resp.approve_count == 1
    assert saved["result"].state == "approved"
    assert audited and audited[0]["event_type"] == "workers.approval.decided"
    assert audited[0]["payload"]["decision"] == "approve"


@pytest.mark.asyncio
async def test_decide_reject_short_circuits() -> None:
    row = _Row(required_approvers=3, approver_ids_json=["alice", "bob", "carol"])

    def load(_):
        return row

    def save(r, result):
        r.state = result.state
        return r

    resp = await decide_handler(
        approval_id="x",
        actor_id="alice",
        body=DecideRequest(decision="reject", reason="bad plan"),
        load_approval=load,
        save_approval=save,
    )
    assert resp.state == "rejected"


@pytest.mark.asyncio
async def test_decide_unknown_id_raises() -> None:
    def load(_):
        return None

    with pytest.raises(LookupError):
        await decide_handler(
            approval_id="missing",
            actor_id="a",
            body=DecideRequest(decision="approve"),
            load_approval=load,
            save_approval=lambda r, result: r,
        )


@pytest.mark.asyncio
async def test_decide_already_decided_propagates() -> None:
    row = _Row(state="approved", votes_json={"a": "approve"})
    with pytest.raises(AlreadyDecided):
        await decide_handler(
            approval_id="x",
            actor_id="b",
            body=DecideRequest(decision="approve"),
            load_approval=lambda _: row,
            save_approval=lambda r, result: r,
        )


@pytest.mark.asyncio
async def test_decide_unauthorized_propagates() -> None:
    row = _Row(approver_ids_json=["only-allowed"])
    with pytest.raises(NotAuthorized):
        await decide_handler(
            approval_id="x",
            actor_id="someone-else",
            body=DecideRequest(decision="approve"),
            load_approval=lambda _: row,
            save_approval=lambda r, result: r,
        )
