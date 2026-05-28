"""workers: M-of-N approval state.

Adds three columns to ``worker_approvals`` (all additive, backward
compatible):

- ``state``                     — pending | approved | rejected
- ``votes_json``                — {approver_id -> "approve"|"reject"}
- ``approvers_decided_json``    — append-only audit trail of votes

Existing single-approver rows keep working: ``required_approvers``
NULL/1 with ``decision`` set behaves as before.

Revision ID: 062_workers_approvals_mn
Revises: 061_gateway_files
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "062_workers_approvals_mn"
down_revision = "061_gateway_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_approvals",
        sa.Column(
            "state",
            sa.String(16),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "worker_approvals",
        sa.Column(
            "votes_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "worker_approvals",
        sa.Column(
            "approvers_decided_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Backfill state from legacy ``decision`` column so previously
    # single-shot approvals show the right terminal state.
    op.execute(
        """
        UPDATE worker_approvals
           SET state = CASE
             WHEN decision IN ('approve','approved') THEN 'approved'
             WHEN decision IN ('reject','rejected') THEN 'rejected'
             ELSE 'pending'
           END
        """
    )


def downgrade() -> None:
    op.drop_column("worker_approvals", "approvers_decided_json")
    op.drop_column("worker_approvals", "votes_json")
    op.drop_column("worker_approvals", "state")
