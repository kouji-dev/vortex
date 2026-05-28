"""Issue-tracker webhook → worker task pipeline.

Flow:
- Receive webhook on ``POST /v1/workers/webhooks/{provider}``.
- Look up the org's :class:`IssueTrackerIntegration` for ``provider``.
- Call ``tracker.parse_webhook_event(payload, headers)``.
- Resolve a pool via ``project_mapping_json``:

  .. code-block:: json

     {
       "<project_key>": {
         "pool_id": "<uuid>",
         "trigger_label": "ai-worker",
         "auto_submit_on": ["created", "labeled"]
       }
     }

- If the issue carries the configured ``trigger_label`` and the event kind
  is in ``auto_submit_on`` (default: ``["labeled"]``), submit the task.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_portal.workers.issues.protocol import IssueWebhookEvent


@dataclass
class WebhookMatch:
    """Resolved mapping: pool to submit to + extracted task fields."""

    pool_id: str
    title: str
    description: str
    repo: str
    base_branch: str
    trigger_payload: dict[str, Any]


# Project key resolution — each tracker stores a hint somewhere. We try a
# small list of candidate fields on the issue.
def _project_key(ev: IssueWebhookEvent) -> str | None:
    issue = ev.issue
    # external_id format varies; we prefer ``repo_hint`` (github_issues
    # sets ``owner/repo``; jira sets None so callers map by labels).
    if issue.repo_hint:
        return issue.repo_hint
    # jira external_id looks like "PROJ-123" — strip the suffix.
    ext = issue.external_id or ""
    if "-" in ext and not ext.startswith("-"):
        return ext.split("-", 1)[0]
    return None


def resolve_match(
    ev: IssueWebhookEvent,
    *,
    project_mapping: dict[str, Any],
    default_base_branch: str = "main",
) -> WebhookMatch | None:
    """Resolve a webhook event to a pool + task fields.

    Returns ``None`` if no project mapping matches, label gate fails, or
    the event kind is not in ``auto_submit_on``.
    """
    key = _project_key(ev)
    if not key:
        return None
    cfg = project_mapping.get(key)
    if not cfg:
        return None

    trigger_label = (cfg.get("trigger_label") or "").strip()
    auto_submit_on = cfg.get("auto_submit_on") or ["labeled"]
    if ev.kind not in auto_submit_on:
        return None

    labels = [str(label).lower() for label in (ev.issue.labels or [])]
    if trigger_label and trigger_label.lower() not in labels:
        return None

    pool_id = cfg.get("pool_id") or ""
    if not pool_id:
        return None

    repo = cfg.get("repo") or ev.issue.repo_hint or ""
    return WebhookMatch(
        pool_id=str(pool_id),
        title=ev.issue.title or ev.issue.external_id,
        description=ev.issue.body or "",
        repo=str(repo),
        base_branch=str(cfg.get("base_branch") or default_base_branch),
        trigger_payload={
            "provider": "issue_webhook",
            "issue_external_id": ev.issue.external_id,
            "issue_url": ev.issue.url,
            "actor": ev.actor,
            "event_kind": ev.kind,
        },
    )
