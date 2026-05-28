"""M-of-N approval decision tracking.

A :class:`WorkerApproval` row carries ``required_approvers`` (the M) and
an ``approver_ids_json`` list (allowed N). Each approver may submit one
decision; the approval is *resolved* when:

- a single ``reject`` arrives → state = ``rejected``
- M distinct ``approve`` votes arrive → state = ``approved``

This file holds the pure decision math (DB-free) so it can be unit-tested
without a session. Caller persists the resulting :class:`DecisionResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class AlreadyDecided(Exception):
    """The approval is in a terminal state — no more votes accepted."""


class NotAuthorized(Exception):
    """Approver id is not in the allow list for this approval."""


@dataclass
class DecisionResult:
    """Materialized state after applying a vote."""

    state: str  # "pending" | "approved" | "rejected"
    votes: dict[str, str] = field(default_factory=dict)  # approver_id -> "approve"|"reject"
    reason: str | None = None

    @property
    def approve_count(self) -> int:
        return sum(1 for v in self.votes.values() if v == "approve")

    @property
    def reject_count(self) -> int:
        return sum(1 for v in self.votes.values() if v == "reject")


def record_decision(
    *,
    current: DecisionResult,
    approver_id: str,
    decision: str,
    required_approvers: int,
    allowed_approver_ids: list[str] | tuple[str, ...] | None,
    reason: str | None = None,
) -> DecisionResult:
    """Apply one vote and return the new :class:`DecisionResult`.

    - Empty / ``None`` allow list = any approver allowed (open gate).
    - Same approver voting twice replaces their previous vote *only* if
      the approval is still pending — raises :class:`AlreadyDecided`
      otherwise.
    - ``decision`` must be ``approve`` or ``reject``.
    """
    if decision not in ("approve", "reject"):
        raise ValueError(f"invalid decision: {decision}")
    if current.state != "pending":
        raise AlreadyDecided(f"approval already {current.state}")
    if allowed_approver_ids and approver_id not in allowed_approver_ids:
        raise NotAuthorized(f"approver {approver_id} not in allow list")
    new_votes = dict(current.votes)
    new_votes[approver_id] = decision
    if decision == "reject":
        return DecisionResult(state="rejected", votes=new_votes, reason=reason)
    approve_count = sum(1 for v in new_votes.values() if v == "approve")
    if approve_count >= max(1, required_approvers):
        return DecisionResult(state="approved", votes=new_votes, reason=reason)
    return DecisionResult(state="pending", votes=new_votes, reason=reason)
