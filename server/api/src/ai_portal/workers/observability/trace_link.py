"""Helpers to correlate Gateway request traces with worker tasks/runs.

The Gateway's ``request_traces`` table stores the actor as a JSON blob.
Workers stash ``task_id`` and ``run_id`` in that actor blob so trace
queries can filter by task without a schema migration.

The query helper :func:`task_id_filter` returns a SQLAlchemy ``where``
fragment that callers can compose with their own session.
"""

from __future__ import annotations

from typing import Any


def build_trace_actor(
    *,
    org_id: str,
    user_id: str | None,
    task_id: str,
    run_id: str | None = None,
    actor_type: str = "worker",
) -> dict[str, Any]:
    """Build the actor dict passed to Gateway ``LLMRequest.actor`` field.

    The ``kind`` field is set to ``worker`` (or override via ``actor_type``)
    so the gateway dashboards can split workers from interactive chat.
    """
    actor: dict[str, Any] = {
        "kind": actor_type,
        "org_id": org_id,
        "task_id": task_id,
    }
    if user_id is not None:
        actor["user_id"] = user_id
    if run_id is not None:
        actor["run_id"] = run_id
    return actor


def extract_task_id(actor_json: dict | None) -> str | None:
    """Pull the task_id back out of a stored actor blob (if any)."""
    if not actor_json:
        return None
    val = actor_json.get("task_id")
    return str(val) if val else None


def task_id_filter(model_cls, task_id: str):
    """Return a SQLAlchemy filter expression: ``actor_json->>'task_id' = task_id``.

    Caller passes ``RequestTrace`` (or a stub with an ``actor_json`` JSONB
    column) so this module need not import the gateway namespace at import
    time.
    """
    return model_cls.actor_json["task_id"].astext == task_id


def metric_tags(
    *,
    org_id: str,
    pool_id: str | None,
    template: str | None,
    repo: str | None,
) -> dict[str, str]:
    """Canonical label set for worker metrics (tasks_completed, etc.)."""
    tags: dict[str, str] = {"org_id": org_id}
    if pool_id:
        tags["pool_id"] = pool_id
    if template:
        tags["template"] = template
    if repo:
        tags["repo"] = repo
    return tags
