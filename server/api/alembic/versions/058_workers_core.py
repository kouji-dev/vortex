"""workers: core tables.

Adds the foundation of the workers domain:

- ``worker_pools``                — sandbox template + scope per org.
- ``worker_tasks``                — one row per submitted task.
- ``worker_runs``                 — one row per execution attempt.
- ``worker_events``               — append-only stream (indexed by run_id, ts).
- ``worker_artifacts``            — PR url / log blob / screenshot / diff.
- ``worker_approvals``            — plan / pr / budget gates.
- ``worker_sandboxes``            — running sandbox lifecycle rows.
- ``worker_secrets_grants``       — per-pool secret bindings.
- ``worker_egress_rules``         — per-pool egress allow-list.
- ``worker_branch_locks``         — one worker per (org, repo, branch).
- ``git_integrations``            — per-org git provider config (encrypted).
- ``issue_tracker_integrations``  — per-org issue tracker config (encrypted).

Every org-scoped table is protected by the standard RLS isolation policy.

``worker_events`` is created as a regular table here. Daily partitioning
should be applied in a follow-up migration once event volume warrants it.

Revision ID: 058_workers_core
Revises: 057_memory_pluggable
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "058_workers_core"
down_revision = "057_memory_pluggable"
branch_labels = None
depends_on = None


_ORG_SCOPED = (
    "worker_pools",
    "worker_tasks",
    "worker_branch_locks",
    "git_integrations",
    "issue_tracker_integrations",
)


def _enable_rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY {table}_org_isolation ON {table}
        USING (org_id = app.current_org_id() OR app.is_rls_bypassed())
        WITH CHECK (org_id = app.current_org_id() OR app.is_rls_bypassed())
        """
    )


def _drop_rls(table: str) -> None:
    op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table}")


def upgrade() -> None:
    op.create_table(
        "worker_pools",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("sandbox_provider", sa.String(32), nullable=False),
        sa.Column(
            "repo_allow_list_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "budget_cents_per_task",
            sa.Integer(),
            nullable=False,
            server_default="10000",
        ),
        sa.Column("default_model", sa.String(128), nullable=False),
        sa.Column(
            "settings_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("org_id", "name", name="uq_worker_pools_org_name"),
    )
    op.create_index("ix_worker_pools_org_id", "worker_pools", ["org_id"])

    op.create_table(
        "worker_tasks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "pool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trigger_source", sa.String(32), nullable=False),
        sa.Column(
            "trigger_payload_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("repo", sa.String(255), nullable=True),
        sa.Column(
            "base_branch", sa.String(128), nullable=False, server_default="main"
        ),
        sa.Column(
            "status",
            sa.String(32),
            nullable=False,
            server_default="queued",
        ),
        sa.Column("created_by", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_worker_tasks_org_id", "worker_tasks", ["org_id"])
    op.create_index("ix_worker_tasks_pool_id", "worker_tasks", ["pool_id"])
    op.create_index("ix_worker_tasks_status", "worker_tasks", ["status"])

    op.create_table(
        "worker_runs",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "attempt_no", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="planning"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sandbox_id", UUID(as_uuid=True), nullable=True),
        sa.Column("cost_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error", sa.String(2048), nullable=True),
    )
    op.create_index("ix_worker_runs_task_id", "worker_runs", ["task_id"])

    op.create_table(
        "worker_events",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "payload_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "ts",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_worker_events_run_id", "worker_events", ["run_id"])
    op.create_index(
        "ix_worker_events_run_ts", "worker_events", ["run_id", "ts"]
    )

    op.create_table(
        "worker_artifacts",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("ref", sa.String(1024), nullable=False),
        sa.Column(
            "meta_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_worker_artifacts_run_id", "worker_artifacts", ["run_id"])

    op.create_table(
        "worker_approvals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "task_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.String(64), nullable=True),
        sa.Column("decision", sa.String(16), nullable=True),
        sa.Column("reason", sa.String(2048), nullable=True),
        sa.Column(
            "required_approvers",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "approver_ids_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.create_index("ix_worker_approvals_task_id", "worker_approvals", ["task_id"])

    op.create_table(
        "worker_sandboxes",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("run_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_resource_id", sa.String(255), nullable=False),
        sa.Column(
            "state", sa.String(16), nullable=False, server_default="allocated"
        ),
        sa.Column(
            "allocated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_worker_sandboxes_run_id", "worker_sandboxes", ["run_id"])

    op.create_table(
        "worker_secrets_grants",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "pool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("secret_ref", sa.String(255), nullable=False),
        sa.Column(
            "allow_repos_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_worker_secrets_grants_pool_id", "worker_secrets_grants", ["pool_id"]
    )

    op.create_table(
        "worker_egress_rules",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "pool_id",
            UUID(as_uuid=True),
            sa.ForeignKey("worker_pools.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "allow_list_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_worker_egress_rules_pool_id", "worker_egress_rules", ["pool_id"]
    )

    op.create_table(
        "worker_branch_locks",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo", sa.String(255), nullable=False),
        sa.Column("branch", sa.String(255), nullable=False),
        sa.Column("run_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "acquired_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id", "repo", "branch", name="uq_worker_branch_locks_triple"
        ),
    )

    op.create_table(
        "git_integrations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "config_encrypted",
            sa.LargeBinary(),
            nullable=False,
            server_default=sa.text("''::bytea"),
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_git_integrations_org_id", "git_integrations", ["org_id"])

    op.create_table(
        "issue_tracker_integrations",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("orgs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "config_encrypted",
            sa.LargeBinary(),
            nullable=False,
            server_default=sa.text("''::bytea"),
        ),
        sa.Column(
            "project_mapping_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_issue_tracker_integrations_org_id",
        "issue_tracker_integrations",
        ["org_id"],
    )

    for table in _ORG_SCOPED:
        _enable_rls(table)


def downgrade() -> None:
    for table in reversed(_ORG_SCOPED):
        _drop_rls(table)

    op.drop_index(
        "ix_issue_tracker_integrations_org_id", table_name="issue_tracker_integrations"
    )
    op.drop_table("issue_tracker_integrations")

    op.drop_index("ix_git_integrations_org_id", table_name="git_integrations")
    op.drop_table("git_integrations")

    op.drop_table("worker_branch_locks")

    op.drop_index(
        "ix_worker_egress_rules_pool_id", table_name="worker_egress_rules"
    )
    op.drop_table("worker_egress_rules")

    op.drop_index(
        "ix_worker_secrets_grants_pool_id", table_name="worker_secrets_grants"
    )
    op.drop_table("worker_secrets_grants")

    op.drop_index("ix_worker_sandboxes_run_id", table_name="worker_sandboxes")
    op.drop_table("worker_sandboxes")

    op.drop_index("ix_worker_approvals_task_id", table_name="worker_approvals")
    op.drop_table("worker_approvals")

    op.drop_index("ix_worker_artifacts_run_id", table_name="worker_artifacts")
    op.drop_table("worker_artifacts")

    op.drop_index("ix_worker_events_run_ts", table_name="worker_events")
    op.drop_index("ix_worker_events_run_id", table_name="worker_events")
    op.drop_table("worker_events")

    op.drop_index("ix_worker_runs_task_id", table_name="worker_runs")
    op.drop_table("worker_runs")

    op.drop_index("ix_worker_tasks_status", table_name="worker_tasks")
    op.drop_index("ix_worker_tasks_pool_id", table_name="worker_tasks")
    op.drop_index("ix_worker_tasks_org_id", table_name="worker_tasks")
    op.drop_table("worker_tasks")

    op.drop_index("ix_worker_pools_org_id", table_name="worker_pools")
    op.drop_table("worker_pools")
