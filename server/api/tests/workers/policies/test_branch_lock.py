"""Tests for the branch-level lock (in-memory backend)."""

from __future__ import annotations

import pytest

from ai_portal.workers.policies.branch_lock import (
    BranchBusy,
    InMemoryBranchLocks,
)


def test_acquire_then_busy_then_release() -> None:
    locks = InMemoryBranchLocks()
    lid = locks.acquire(org_id="o", repo="acme/api", branch="worker/x")
    assert lid
    assert locks.is_held(org_id="o", repo="acme/api", branch="worker/x")

    with pytest.raises(BranchBusy):
        locks.acquire(org_id="o", repo="acme/api", branch="worker/x")

    locks.release(org_id="o", repo="acme/api", branch="worker/x")
    assert not locks.is_held(org_id="o", repo="acme/api", branch="worker/x")

    # re-acquire OK after release
    locks.acquire(org_id="o", repo="acme/api", branch="worker/x")


def test_different_branches_independent() -> None:
    locks = InMemoryBranchLocks()
    locks.acquire(org_id="o", repo="acme/api", branch="a")
    locks.acquire(org_id="o", repo="acme/api", branch="b")
    assert locks.is_held(org_id="o", repo="acme/api", branch="a")
    assert locks.is_held(org_id="o", repo="acme/api", branch="b")


def test_different_repos_independent() -> None:
    locks = InMemoryBranchLocks()
    locks.acquire(org_id="o", repo="acme/api", branch="main-fix")
    locks.acquire(org_id="o", repo="acme/web", branch="main-fix")
    assert locks.is_held(org_id="o", repo="acme/api", branch="main-fix")
    assert locks.is_held(org_id="o", repo="acme/web", branch="main-fix")


def test_different_orgs_independent() -> None:
    locks = InMemoryBranchLocks()
    locks.acquire(org_id="o1", repo="acme/api", branch="b")
    locks.acquire(org_id="o2", repo="acme/api", branch="b")
    assert locks.is_held(org_id="o1", repo="acme/api", branch="b")
    assert locks.is_held(org_id="o2", repo="acme/api", branch="b")


def test_busy_exception_carries_context() -> None:
    locks = InMemoryBranchLocks()
    locks.acquire(org_id="o", repo="r", branch="b")
    try:
        locks.acquire(org_id="o", repo="r", branch="b")
    except BranchBusy as e:
        assert e.org_id == "o"
        assert e.repo == "r"
        assert e.branch == "b"
    else:
        raise AssertionError("expected BranchBusy")


def test_release_without_acquire_is_noop() -> None:
    locks = InMemoryBranchLocks()
    locks.release(org_id="o", repo="r", branch="b")
    assert not locks.is_held(org_id="o", repo="r", branch="b")
