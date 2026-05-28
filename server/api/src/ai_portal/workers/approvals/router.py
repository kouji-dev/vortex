"""HTTP entry point: ``POST /v1/workers/approvals/{id}/decide``.

The router itself is a thin shell — it parses the request, resolves the
``WorkerApproval`` row, applies :func:`record_decision`, persists, and
emits an audit row. The decision math is in
:mod:`ai_portal.workers.approvals.decision`.

This module avoids importing FastAPI at import time so unit tests can
exercise the handler via :func:`decide_handler` without spinning up the
ASGI app.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from ai_portal.workers.approvals.decision import (
    AlreadyDecided,
    DecisionResult,
    NotAuthorized,
    record_decision,
)


@dataclass
class DecideRequest:
    decision: str  # "approve" | "reject"
    reason: str | None = None


@dataclass
class DecideResponse:
    approval_id: str
    state: str
    approve_count: int
    reject_count: int
    reason: str | None = None


AuditFn = Callable[..., Awaitable[None]] | Callable[..., None]


async def decide_handler(
    *,
    approval_id: str | _uuid.UUID,
    actor_id: str,
    body: DecideRequest,
    load_approval: Callable[[str], Any],
    save_approval: Callable[[Any, DecisionResult], Any],
    emit_audit: AuditFn | None = None,
) -> DecideResponse:
    """Pure handler — DI'd I/O.

    ``load_approval(id)`` returns a row-like object with attributes:
    ``required_approvers``, ``approver_ids_json``, ``votes_json``,
    ``state`` ("pending"|"approved"|"rejected"), ``task_id``, ``kind``.

    ``save_approval(row, result)`` persists and returns the row.
    """
    row = load_approval(str(approval_id))
    if row is None:
        raise LookupError(f"approval not found: {approval_id}")

    current = DecisionResult(
        state=row.state or "pending",
        votes=dict(row.votes_json or {}),
    )
    try:
        new = record_decision(
            current=current,
            approver_id=actor_id,
            decision=body.decision,
            required_approvers=int(row.required_approvers or 1),
            allowed_approver_ids=list(row.approver_ids_json or []) or None,
            reason=body.reason,
        )
    except (AlreadyDecided, NotAuthorized):
        raise

    save_approval(row, new)

    if emit_audit is not None:
        payload = {
            "approval_id": str(approval_id),
            "task_id": str(getattr(row, "task_id", "")),
            "kind": getattr(row, "kind", None),
            "decision": body.decision,
            "state": new.state,
            "actor_id": actor_id,
        }
        result = emit_audit(  # type: ignore[misc]
            org_id=getattr(row, "org_id", None),
            event_type="workers.approval.decided",
            actor={"id": actor_id, "type": "user"},
            resource={"type": "worker_approval", "id": str(approval_id)},
            payload=payload,
        )
        # If the audit hook is async, await it.
        if hasattr(result, "__await__"):
            await result  # type: ignore[func-returns-value]

    return DecideResponse(
        approval_id=str(approval_id),
        state=new.state,
        approve_count=new.approve_count,
        reject_count=new.reject_count,
        reason=new.reason,
    )
