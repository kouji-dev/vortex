"""Audit hook helpers — fire-and-forget wrappers over ``emit_audit``.

Every helper accepts an ``emit`` callable (defaults to
``ai_portal.control_plane.emit_audit``) so unit tests can capture the
payload without touching the DB.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable

from ai_portal.workers.audit_hooks.hashing import excerpt, sha256_hex

EmitFn = Callable[..., Any]


def _default_emit() -> EmitFn:
    from ai_portal.control_plane import emit_audit  # noqa: PLC0415

    return emit_audit


def audit_shell(
    *,
    org_id: str,
    task_id: str,
    run_id: str,
    cmd: list[str],
    exit_code: int,
    stdout: str,
    stderr: str,
    duration_ms: int,
    actor_id: str | None = None,
    cwd: str | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Record one shell exec. Returns the payload that was emitted."""
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "cmd": cmd,
        "cwd": cwd,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_sha256": sha256_hex(stdout),
        "stderr_sha256": sha256_hex(stderr),
        "stdout_excerpt": excerpt(stdout),
        "stderr_excerpt": excerpt(stderr),
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type="workers.shell.exec",
        actor={"id": actor_id or "worker", "type": "worker"},
        resource={"type": "worker_run", "id": run_id},
        payload=payload,
    )
    return payload


def audit_file_write(
    *,
    org_id: str,
    task_id: str,
    run_id: str,
    path: str,
    before: bytes | str,
    after: bytes | str,
    actor_id: str | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Record one file write with before/after hashes."""
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "path": path,
        "before_sha256": sha256_hex(before),
        "after_sha256": sha256_hex(after),
        "before_size": len(before),
        "after_size": len(after),
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type="workers.file.write",
        actor={"id": actor_id or "worker", "type": "worker"},
        resource={"type": "worker_run", "id": run_id},
        payload=payload,
    )
    return payload


def audit_pr_created(
    *,
    org_id: str,
    task_id: str,
    run_id: str,
    repo: str,
    pr_number: int,
    pr_url: str,
    diff_text: str,
    head_branch: str,
    base_branch: str,
    actor_id: str | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Record a PR creation with the diff hash + url."""
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "repo": repo,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "head_branch": head_branch,
        "base_branch": base_branch,
        "diff_sha256": sha256_hex(diff_text),
        "diff_size": len(diff_text),
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type="workers.pr.created",
        actor={"id": actor_id or "worker", "type": "worker"},
        resource={"type": "worker_pr", "id": f"{repo}#{pr_number}"},
        payload=payload,
    )
    return payload


def audit_approval_decided(
    *,
    org_id: str,
    task_id: str,
    approval_id: str,
    kind: str,
    decision: str,
    decided_by: str,
    reason: str | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Record one approval decision."""
    payload = {
        "task_id": task_id,
        "approval_id": approval_id,
        "kind": kind,
        "decision": decision,
        "decided_by": decided_by,
        "reason": reason,
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type="workers.approval.decided",
        actor={"id": decided_by, "type": "user"},
        resource={"type": "worker_approval", "id": approval_id},
        payload=payload,
    )
    return payload


def audit_egress_blocked(
    *,
    org_id: str,
    task_id: str,
    run_id: str,
    host: str,
    reason: str,
    actor_id: str | None = None,
    emit: EmitFn | None = None,
) -> dict:
    """Record one blocked outbound attempt."""
    payload = {
        "task_id": task_id,
        "run_id": run_id,
        "host": host,
        "reason": reason,
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type="workers.egress.blocked",
        actor={"id": actor_id or "worker", "type": "worker"},
        resource={"type": "worker_run", "id": run_id},
        payload=payload,
    )
    return payload


def audit_secret_grant(
    *,
    org_id: str,
    pool_id: str,
    secret_ref: str,
    allow_repos: Iterable[str],
    actor_id: str,
    action: str = "grant",
    emit: EmitFn | None = None,
) -> dict:
    """Record a secret grant / revoke action."""
    payload = {
        "pool_id": pool_id,
        "secret_ref": secret_ref,
        "allow_repos": list(allow_repos),
        "action": action,
    }
    e = emit or _default_emit()
    e(
        org_id=org_id,
        event_type=f"workers.secret.{action}",
        actor={"id": actor_id, "type": "user"},
        resource={"type": "worker_secret_grant", "id": secret_ref},
        payload=payload,
    )
    return payload
