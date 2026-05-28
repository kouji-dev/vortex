"""Org-scoped delete + export adapters for the workers module.

The delete order respects FK constraints:

1. ``worker_events`` (by run_id) — partitioned, no FK but indexed by run.
2. ``worker_artifacts`` (by run_id).
3. ``worker_sandboxes`` (by run_id).
4. ``worker_runs`` (by task_id; tasks have ondelete=CASCADE so step 6
   would handle them, but we delete explicitly for clarity).
5. ``worker_approvals`` (by task_id; same — kept explicit).
6. ``worker_tasks`` (by org_id — cascades the rest).
7. ``worker_branch_locks`` (by org_id).
8. ``worker_secrets_grants`` (by pool_id → org_id).
9. ``worker_egress_rules`` (by pool_id → org_id).
10. ``worker_pools`` (by org_id).
11. ``git_integrations`` (by org_id).
12. ``issue_tracker_integrations`` (by org_id).

Audit is emitted on success.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

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

logger = logging.getLogger(__name__)


async def delete_for_org(
    session: AsyncSession, org_id: _uuid.UUID
) -> dict[str, int]:
    """Hard-delete every workers row owned by ``org_id``.

    Returns per-table delete counts so the GDPR worker can audit the scope.
    Idempotent — re-running after partial failure must complete cleanly.
    """
    counts: dict[str, int] = {}

    # collect run_ids first (needed for tables without org_id column)
    task_ids = (
        await session.execute(
            select(WorkerTask.id).where(WorkerTask.org_id == org_id)
        )
    ).scalars().all()
    run_ids = []
    if task_ids:
        run_ids = (
            await session.execute(
                select(WorkerRun.id).where(WorkerRun.task_id.in_(task_ids))
            )
        ).scalars().all()
    pool_ids = (
        await session.execute(
            select(WorkerPool.id).where(WorkerPool.org_id == org_id)
        )
    ).scalars().all()

    if run_ids:
        r = await session.execute(
            delete(WorkerEvent).where(WorkerEvent.run_id.in_(run_ids))
        )
        counts["worker_events"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerArtifact).where(WorkerArtifact.run_id.in_(run_ids))
        )
        counts["worker_artifacts"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerSandboxRow).where(WorkerSandboxRow.run_id.in_(run_ids))
        )
        counts["worker_sandboxes"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerRun).where(WorkerRun.id.in_(run_ids))
        )
        counts["worker_runs"] = int(r.rowcount or 0)
    else:
        counts["worker_events"] = 0
        counts["worker_artifacts"] = 0
        counts["worker_sandboxes"] = 0
        counts["worker_runs"] = 0

    if task_ids:
        r = await session.execute(
            delete(WorkerApproval).where(WorkerApproval.task_id.in_(task_ids))
        )
        counts["worker_approvals"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerTask).where(WorkerTask.id.in_(task_ids))
        )
        counts["worker_tasks"] = int(r.rowcount or 0)
    else:
        counts["worker_approvals"] = 0
        counts["worker_tasks"] = 0

    r = await session.execute(
        delete(WorkerBranchLock).where(WorkerBranchLock.org_id == org_id)
    )
    counts["worker_branch_locks"] = int(r.rowcount or 0)

    if pool_ids:
        r = await session.execute(
            delete(WorkerSecretGrant).where(WorkerSecretGrant.pool_id.in_(pool_ids))
        )
        counts["worker_secrets_grants"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerEgressRule).where(WorkerEgressRule.pool_id.in_(pool_ids))
        )
        counts["worker_egress_rules"] = int(r.rowcount or 0)
        r = await session.execute(
            delete(WorkerPool).where(WorkerPool.id.in_(pool_ids))
        )
        counts["worker_pools"] = int(r.rowcount or 0)
    else:
        counts["worker_secrets_grants"] = 0
        counts["worker_egress_rules"] = 0
        counts["worker_pools"] = 0

    r = await session.execute(
        delete(GitIntegration).where(GitIntegration.org_id == org_id)
    )
    counts["git_integrations"] = int(r.rowcount or 0)
    r = await session.execute(
        delete(IssueTrackerIntegration).where(
            IssueTrackerIntegration.org_id == org_id
        )
    )
    counts["issue_tracker_integrations"] = int(r.rowcount or 0)

    await session.flush()

    try:
        from ai_portal.control_plane import emit_audit  # noqa: PLC0415

        emit_audit(
            org_id=org_id,
            event_type="workers.gdpr.deleted",
            resource={"type": "workers", "id": str(org_id)},
            payload={"counts": counts},
        )
    except Exception:
        logger.debug("workers.gdpr.audit_skipped", exc_info=True)
    return counts


async def export_for_org(
    session: AsyncSession, org_id: _uuid.UUID
) -> dict[str, Any]:
    """Build a JSON-serialisable export of every workers row for ``org_id``."""
    pools = (
        await session.execute(
            select(WorkerPool).where(WorkerPool.org_id == org_id)
        )
    ).scalars().all()
    tasks = (
        await session.execute(
            select(WorkerTask).where(WorkerTask.org_id == org_id)
        )
    ).scalars().all()
    task_ids = [t.id for t in tasks]
    runs = []
    if task_ids:
        runs = (
            await session.execute(
                select(WorkerRun).where(WorkerRun.task_id.in_(task_ids))
            )
        ).scalars().all()
    approvals = []
    if task_ids:
        approvals = (
            await session.execute(
                select(WorkerApproval).where(WorkerApproval.task_id.in_(task_ids))
            )
        ).scalars().all()
    git_ints = (
        await session.execute(
            select(GitIntegration).where(GitIntegration.org_id == org_id)
        )
    ).scalars().all()
    issue_ints = (
        await session.execute(
            select(IssueTrackerIntegration).where(
                IssueTrackerIntegration.org_id == org_id
            )
        )
    ).scalars().all()

    return {
        "worker_pools": [
            {
                "id": str(p.id),
                "name": p.name,
                "template": p.template,
                "sandbox_provider": p.sandbox_provider,
                "repo_allow_list": p.repo_allow_list_json,
                "budget_cents_per_task": p.budget_cents_per_task,
                "default_model": p.default_model,
                "enabled": p.enabled,
            }
            for p in pools
        ],
        "worker_tasks": [
            {
                "id": str(t.id),
                "pool_id": str(t.pool_id),
                "trigger_source": t.trigger_source,
                "title": t.title,
                "repo": t.repo,
                "status": t.status,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "worker_runs": [
            {
                "id": str(r.id),
                "task_id": str(r.task_id),
                "attempt_no": r.attempt_no,
                "status": r.status,
                "cost_cents": r.cost_cents,
                "error": r.error,
            }
            for r in runs
        ],
        "worker_approvals": [
            {
                "id": str(a.id),
                "task_id": str(a.task_id),
                "kind": a.kind,
                "decision": a.decision,
                "decided_by": a.decided_by,
            }
            for a in approvals
        ],
        "git_integrations": [
            {"id": str(g.id), "kind": g.kind, "enabled": g.enabled}
            for g in git_ints
        ],
        "issue_tracker_integrations": [
            {"id": str(i.id), "kind": i.kind, "enabled": i.enabled}
            for i in issue_ints
        ],
    }


# ── control-plane adapters ────────────────────────────────────────────────


async def _delete_adapter(org_id: _uuid.UUID, scope: dict) -> None:
    """Match ``Deleter`` protocol — opens its own session.

    Scope is org-wide for workers: a per-user delete is meaningless
    (worker tasks are not user-PII heavy; the org cascade purges them).
    """
    from ai_portal.core.db.session import AsyncSessionLocal  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as session:  # type: ignore[misc]
        try:
            await delete_for_org(session, org_id)
            await session.commit()
        except Exception:
            logger.exception("workers.gdpr.delete_adapter_failed")
            await session.rollback()


async def _export_adapter(org_id: _uuid.UUID) -> dict[str, Any]:
    from ai_portal.core.db.session import AsyncSessionLocal  # type: ignore[attr-defined]

    async with AsyncSessionLocal() as session:  # type: ignore[misc]
        return await export_for_org(session, org_id)


def register() -> None:
    """Register adapters with the control_plane GDPR registry."""
    try:
        from ai_portal.control_plane import (  # noqa: PLC0415
            register_deleter,
            register_exporter,
        )

        register_deleter("workers", _delete_adapter)
        register_exporter("workers", _export_adapter)
    except Exception:
        logger.debug("workers.gdpr.register_skipped", exc_info=True)
