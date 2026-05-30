"""SQLAlchemy ORM models for the workers domain.

Tables:
- ``worker_pools``            — sandbox template + scope per org.
- ``worker_tasks``            — one row per assigned task.
- ``worker_runs``             — one row per execution attempt.
- ``worker_events``           — append-only stream (partitioned daily by ts).
- ``worker_artifacts``        — PR url / log blob / screenshot / diff.
- ``worker_approvals``        — plan / pr / budget gates.
- ``worker_sandboxes``        — running sandbox lifecycle rows.
- ``worker_secrets_grants``   — per-pool secret bindings.
- ``worker_egress_rules``     — per-pool egress allow-list.
- ``worker_branch_locks``     — one-worker-per-branch lock.
- ``git_integrations``        — per-org git provider config (encrypted).
- ``issue_tracker_integrations`` — per-org issue tracker config (encrypted).
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ai_portal.core.db.base import Base

_EMPTY_LIST = text("'[]'::jsonb")
_EMPTY_OBJ = text("'{}'::jsonb")
_EMPTY_BYTEA = text("''::bytea")


class WorkerPool(Base):
    """A pool: sandbox template + scope (repos, budget, sandbox provider)."""

    __tablename__ = "worker_pools"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)
    sandbox_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    repo_allow_list_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_LIST
    )
    budget_cents_per_task: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="10000"
    )
    default_model: Mapped[str] = mapped_column(String(128), nullable=False)
    settings_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_worker_pools_org_name"),
    )


class WorkerTask(Base):
    """One row per submitted task."""

    __tablename__ = "worker_tasks"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pool_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False)
    trigger_payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=""
    )
    repo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_branch: Mapped[str] = mapped_column(
        String(128), nullable=False, server_default="main"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="queued",
        server_default="queued",
        index=True,
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkerRun(Base):
    """One row per execution attempt of a task."""

    __tablename__ = "worker_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    task_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_no: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="planning",
        server_default="planning",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sandbox_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)


class WorkerEvent(Base):
    """Append-only event stream — partitioned daily by ``ts`` in production."""

    __tablename__ = "worker_events"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    run_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_worker_events_run_ts", "run_id", "ts"),)


class WorkerArtifact(Base):
    """Output artifacts for a run: PR url, log blob, screenshot, diff."""

    __tablename__ = "worker_artifacts"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    run_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    ref: Mapped[str] = mapped_column(String(1024), nullable=False)
    meta_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkerApproval(Base):
    """Approval row — plan / pr / budget gate."""

    __tablename__ = "worker_approvals"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    task_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    required_approvers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    approver_ids_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_LIST
    )
    # M-of-N runtime state.
    # ``state`` mirrors ``decision`` for the M-of-N flow: "pending"
    # | "approved" | "rejected". ``decision`` stays for single-approver
    # backwards-compat readers.
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    # ``votes_json`` = {approver_id -> "approve"|"reject"} — fast lookup
    # used by the decision math (idempotent re-vote).
    votes_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    # ``approvers_decided_json`` = ordered audit trail of every vote:
    # [{"user_id": str, "decision": "approve"|"reject", "ts": iso8601,
    # "reason": str|None}, ...]
    approvers_decided_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_LIST
    )


class WorkerSandboxRow(Base):
    """Lifecycle row for a running sandbox."""

    __tablename__ = "worker_sandboxes"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    run_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_resource_id: Mapped[str] = mapped_column(String(255), nullable=False)
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="allocated", server_default="allocated"
    )
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkerSecretGrant(Base):
    """Per-pool secret binding."""

    __tablename__ = "worker_secrets_grants"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    pool_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    secret_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    allow_repos_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_LIST
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkerEgressRule(Base):
    """Per-pool egress allow-list."""

    __tablename__ = "worker_egress_rules"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    pool_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_pools.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    allow_list_json: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_LIST
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkerBranchLock(Base):
    """Branch-level lock — one worker per (org, repo, branch) at a time."""

    __tablename__ = "worker_branch_locks"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo: Mapped[str] = mapped_column(String(255), nullable=False)
    branch: Mapped[str] = mapped_column(String(255), nullable=False)
    run_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "org_id", "repo", "branch", name="uq_worker_branch_locks_triple"
        ),
    )


class GitIntegration(Base):
    """Per-org git provider config (cipher text)."""

    __tablename__ = "git_integrations"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, server_default=_EMPTY_BYTEA
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IssueTrackerIntegration(Base):
    """Per-org issue tracker config (cipher text) + project→pool mapping."""

    __tablename__ = "issue_tracker_integrations"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    config_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, server_default=_EMPTY_BYTEA
    )
    project_mapping_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── worker-centric model (v1 direction: "a worker IS a task") ──────────────
#
# The tables above are the legacy *task-centric* framing (worker_tasks +
# task-scoped worker_runs). The tables below are the new *worker-centric*
# direction from the suite spec: a first-class persistent ``Worker`` bound 1:1
# to a sandbox, driven message-by-message (interactive) or by a trigger
# (autonomous). Each user message spawns a ``WorkerInstanceRun`` that tracks
# its own file changes. ``WorkerMessage`` is the worker's own agent-SDK chat
# thread (distinct from the LLM-provider chat module).
#
# These coexist with the legacy tables for now — the task-centric path is not
# yet removed (see spec "Worker Model & Runtime"). New surfaces use these.


class Worker(Base):
    """First-class spawned worker = the task (interactive | autonomous).

    Bound 1:1 to a sandbox/VM for v1. The sandbox stays allocated while the
    worker is ``idle``; released only when the worker is ``stopped``.
    """

    __tablename__ = "workers"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    org_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    pool_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_pools.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    # state: idle | provisioning | running | error | stopped
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="provisioning",
        server_default="provisioning", index=True,
    )
    # mode: interactive | autonomous
    mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="interactive",
        server_default="interactive",
    )
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    # runtime: claude | codex (which agent SDK/CLI drives the sandbox)
    runtime: Mapped[str] = mapped_column(
        String(16), nullable=False, default="claude", server_default="claude"
    )
    # connector_json: GitLab connector config (project id, branch, token ref…)
    connector_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    repo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    sandbox_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    trigger_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    trigger_payload_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=_EMPTY_OBJ
    )
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WorkerInstanceRun(Base):
    """One run = one user-message → agent-work cycle for a :class:`Worker`.

    Distinct from the legacy task-scoped ``worker_runs`` (``WorkerRun``).
    """

    __tablename__ = "worker_instance_runs"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    worker_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seq_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    user_message: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # status: running | error | finished | success
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="running", server_default="running"
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sandbox_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    cost_cents: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    error: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    __table_args__ = (
        UniqueConstraint("worker_id", "seq_no", name="uq_worker_instance_runs_seq"),
        Index("ix_worker_instance_runs_worker", "worker_id", "seq_no"),
    )


class WorkerRunChange(Base):
    """A file changed during a run — drives the right-pane diff + file list."""

    __tablename__ = "worker_run_changes"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    run_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_instance_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    # change_kind: added | modified | deleted | renamed
    change_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    additions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    deletions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # diff_ref: blob-store ref or inline unified diff (small diffs inline)
    diff_ref: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class WorkerMessage(Base):
    """The worker's own agent-SDK chat thread (separate from the chat module).

    ``role``: user | agent | system. Persists across the worker's life.
    """

    __tablename__ = "worker_messages"

    id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=_uuid.uuid4
    )
    worker_id: Mapped[_uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("workers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[_uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("worker_instance_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_worker_messages_worker_ts", "worker_id", "ts"),)
