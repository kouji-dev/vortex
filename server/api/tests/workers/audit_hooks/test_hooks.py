"""Tests for the audit hook helpers (DI emit so no DB required)."""

from __future__ import annotations

from ai_portal.workers.audit_hooks.hashing import sha256_hex
from ai_portal.workers.audit_hooks.hooks import (
    audit_approval_decided,
    audit_egress_blocked,
    audit_file_write,
    audit_pr_created,
    audit_secret_grant,
    audit_shell,
)


class _Capture:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kw):
        self.calls.append(kw)


def test_audit_shell_hashes_stdout_and_stderr() -> None:
    cap = _Capture()
    payload = audit_shell(
        org_id="org-1",
        task_id="t-1",
        run_id="r-1",
        cmd=["echo", "ok"],
        exit_code=0,
        stdout="hello",
        stderr="",
        duration_ms=42,
        emit=cap,
    )
    assert payload["stdout_sha256"] == sha256_hex("hello")
    assert payload["stderr_sha256"] == sha256_hex("")
    assert payload["duration_ms"] == 42
    assert payload["cmd"] == ["echo", "ok"]
    assert cap.calls[0]["event_type"] == "workers.shell.exec"


def test_audit_shell_truncates_excerpts() -> None:
    cap = _Capture()
    huge = "x" * 50_000
    payload = audit_shell(
        org_id="o", task_id="t", run_id="r", cmd=["x"], exit_code=0,
        stdout=huge, stderr=huge, duration_ms=0, emit=cap,
    )
    assert len(payload["stdout_excerpt"]) < 1000
    assert len(payload["stderr_excerpt"]) < 1000


def test_audit_file_write_records_before_after() -> None:
    cap = _Capture()
    payload = audit_file_write(
        org_id="o", task_id="t", run_id="r",
        path="src/app.py", before="old", after="new", emit=cap,
    )
    assert payload["before_sha256"] == sha256_hex("old")
    assert payload["after_sha256"] == sha256_hex("new")
    assert payload["before_size"] == 3
    assert payload["after_size"] == 3


def test_audit_file_write_works_with_bytes() -> None:
    cap = _Capture()
    payload = audit_file_write(
        org_id="o", task_id="t", run_id="r",
        path="bin/x", before=b"\x00\x01", after=b"\x00\x02", emit=cap,
    )
    assert payload["before_size"] == 2
    assert payload["after_sha256"] != payload["before_sha256"]


def test_audit_pr_created_hashes_diff() -> None:
    cap = _Capture()
    diff = "diff --git a b\n@@\n+new line"
    payload = audit_pr_created(
        org_id="o", task_id="t", run_id="r",
        repo="acme/api", pr_number=42, pr_url="https://x/42",
        diff_text=diff, head_branch="worker/t-1", base_branch="main",
        emit=cap,
    )
    assert payload["diff_sha256"] == sha256_hex(diff)
    assert payload["pr_number"] == 42
    assert cap.calls[0]["event_type"] == "workers.pr.created"


def test_audit_approval_decided_shape() -> None:
    cap = _Capture()
    audit_approval_decided(
        org_id="o", task_id="t", approval_id="a-1",
        kind="plan", decision="approve", decided_by="alice", emit=cap,
    )
    kw = cap.calls[0]
    assert kw["event_type"] == "workers.approval.decided"
    assert kw["payload"]["decision"] == "approve"
    assert kw["actor"]["id"] == "alice"


def test_audit_egress_blocked_shape() -> None:
    cap = _Capture()
    audit_egress_blocked(
        org_id="o", task_id="t", run_id="r",
        host="evil.tld", reason="not in allow list", emit=cap,
    )
    kw = cap.calls[0]
    assert kw["event_type"] == "workers.egress.blocked"
    assert kw["payload"]["host"] == "evil.tld"


def test_audit_secret_grant_shape() -> None:
    cap = _Capture()
    audit_secret_grant(
        org_id="o", pool_id="p", secret_ref="aws/key",
        allow_repos=["acme/api"], actor_id="alice", emit=cap,
    )
    kw = cap.calls[0]
    assert kw["event_type"] == "workers.secret.grant"
    assert kw["payload"]["allow_repos"] == ["acme/api"]
