"""Branch-level lock — one worker per (org, repo, branch) at a time.

Uses the ``worker_branch_locks`` table with a unique (org_id, repo, branch)
constraint as the serialization point. Two concurrent workers on the same
branch will see :class:`BranchBusy` raised on the loser.

Synchronous helpers for in-memory tests live in :class:`InMemoryBranchLocks`.
The async DB helpers operate on ``WorkerBranchLock`` rows and rely on the
unique constraint for atomicity.
"""

from __future__ import annotations

import uuid as _uuid
from dataclasses import dataclass, field


class BranchBusy(Exception):
    """Raised when the requested (org, repo, branch) is already locked."""

    def __init__(self, org_id: str, repo: str, branch: str) -> None:
        super().__init__(f"branch busy: {org_id}/{repo}#{branch}")
        self.org_id = org_id
        self.repo = repo
        self.branch = branch


def _key(org_id: str, repo: str, branch: str) -> tuple[str, str, str]:
    return (str(org_id), repo, branch)


@dataclass
class InMemoryBranchLocks:
    """Thread-unsafe in-memory implementation — for unit tests."""

    _held: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def acquire(
        self,
        *,
        org_id: str,
        repo: str,
        branch: str,
        run_id: str | None = None,
    ) -> str:
        """Acquire the lock. Returns a lock id. Raises :class:`BranchBusy`."""
        k = _key(org_id, repo, branch)
        if k in self._held:
            raise BranchBusy(org_id, repo, branch)
        lock_id = run_id or _uuid.uuid4().hex
        self._held[k] = lock_id
        return lock_id

    def release(self, *, org_id: str, repo: str, branch: str) -> None:
        """Release the lock. No-op if not held."""
        self._held.pop(_key(org_id, repo, branch), None)

    def is_held(self, *, org_id: str, repo: str, branch: str) -> bool:
        return _key(org_id, repo, branch) in self._held


async def acquire_branch_db(
    session,
    *,
    org_id: str,
    repo: str,
    branch: str,
    run_id: str | None = None,
):
    """Acquire a branch lock by inserting a ``worker_branch_locks`` row.

    Relies on the ``uq_worker_branch_locks_triple`` unique constraint to
    serialize concurrent acquirers. Raises :class:`BranchBusy` on conflict.
    """
    from sqlalchemy.exc import IntegrityError

    from ai_portal.workers.model import WorkerBranchLock

    row = WorkerBranchLock(
        org_id=org_id,
        repo=repo,
        branch=branch,
        run_id=run_id,
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError as e:
        await session.rollback()
        raise BranchBusy(str(org_id), repo, branch) from e
    return row


async def release_branch_db(
    session,
    *,
    org_id: str,
    repo: str,
    branch: str,
) -> None:
    """Release the branch lock by deleting the row (no-op if missing)."""
    from sqlalchemy import delete

    from ai_portal.workers.model import WorkerBranchLock

    await session.execute(
        delete(WorkerBranchLock).where(
            WorkerBranchLock.org_id == org_id,
            WorkerBranchLock.repo == repo,
            WorkerBranchLock.branch == branch,
        )
    )
    await session.flush()
