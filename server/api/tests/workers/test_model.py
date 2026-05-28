"""Smoke tests for the workers SQLAlchemy models.

These run without a DB — we only assert ``__tablename__``, columns, indexes
and constraints are wired up so the migration matches expectations.
"""

from __future__ import annotations

from ai_portal.workers.model import (
    GitIntegration,
    IssueTrackerIntegration,
    WorkerApproval,
    WorkerArtifact,
    WorkerBranchLock,
    WorkerEgressRule,
    WorkerEvent,
    WorkerPool,
    WorkerRun,
    WorkerSandboxRow,
    WorkerSecretGrant,
    WorkerTask,
)


def test_table_names() -> None:
    assert WorkerPool.__tablename__ == "worker_pools"
    assert WorkerTask.__tablename__ == "worker_tasks"
    assert WorkerRun.__tablename__ == "worker_runs"
    assert WorkerEvent.__tablename__ == "worker_events"
    assert WorkerArtifact.__tablename__ == "worker_artifacts"
    assert WorkerApproval.__tablename__ == "worker_approvals"
    assert WorkerSandboxRow.__tablename__ == "worker_sandboxes"
    assert WorkerSecretGrant.__tablename__ == "worker_secrets_grants"
    assert WorkerEgressRule.__tablename__ == "worker_egress_rules"
    assert WorkerBranchLock.__tablename__ == "worker_branch_locks"
    assert GitIntegration.__tablename__ == "git_integrations"
    assert IssueTrackerIntegration.__tablename__ == "issue_tracker_integrations"


def test_pool_columns() -> None:
    cols = {c.name for c in WorkerPool.__table__.columns}
    assert {
        "id",
        "org_id",
        "name",
        "template",
        "sandbox_provider",
        "repo_allow_list_json",
        "budget_cents_per_task",
        "default_model",
        "settings_json",
        "enabled",
        "created_at",
    } <= cols


def test_task_columns() -> None:
    cols = {c.name for c in WorkerTask.__table__.columns}
    assert {
        "id",
        "org_id",
        "pool_id",
        "trigger_source",
        "trigger_payload_json",
        "title",
        "description",
        "repo",
        "base_branch",
        "status",
        "created_by",
        "created_at",
        "completed_at",
    } <= cols


def test_run_columns() -> None:
    cols = {c.name for c in WorkerRun.__table__.columns}
    assert {
        "id",
        "task_id",
        "attempt_no",
        "status",
        "started_at",
        "ended_at",
        "sandbox_id",
        "cost_cents",
        "error",
    } <= cols


def test_event_has_composite_index() -> None:
    idx_names = {ix.name for ix in WorkerEvent.__table__.indexes}
    assert "ix_worker_events_run_ts" in idx_names


def test_branch_lock_unique_triple() -> None:
    names = {
        c.name
        for c in WorkerBranchLock.__table__.constraints
        if c.name is not None
    }
    assert "uq_worker_branch_locks_triple" in names


def test_pool_unique_org_name() -> None:
    names = {
        c.name
        for c in WorkerPool.__table__.constraints
        if c.name is not None
    }
    assert "uq_worker_pools_org_name" in names


def test_models_registered_with_metadata() -> None:
    from ai_portal.core.db.base import Base

    md_tables = set(Base.metadata.tables.keys())
    for t in (
        "worker_pools",
        "worker_tasks",
        "worker_runs",
        "worker_events",
        "worker_artifacts",
        "worker_approvals",
        "worker_sandboxes",
        "worker_secrets_grants",
        "worker_egress_rules",
        "worker_branch_locks",
        "git_integrations",
        "issue_tracker_integrations",
    ):
        assert t in md_tables, f"{t} missing from Base.metadata"


def test_models_re_exported_from_models_pkg() -> None:
    """Ensure central models __init__ re-exports new tables for alembic."""
    from ai_portal import models as m

    for name in (
        "WorkerPool",
        "WorkerTask",
        "WorkerRun",
        "WorkerEvent",
        "WorkerArtifact",
        "WorkerApproval",
        "WorkerSandboxRow",
        "WorkerSecretGrant",
        "WorkerEgressRule",
        "WorkerBranchLock",
        "GitIntegration",
        "IssueTrackerIntegration",
    ):
        assert hasattr(m, name)
