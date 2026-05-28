"""HTTP receiver for issue-tracker webhooks.

``POST /v1/workers/webhooks/{provider}`` — signature-verified webhook
receiver that auto-submits a worker task when the project mapping for the
sender's org carries a matching trigger label.

Provider names match :mod:`workers.issues.registry`:
``jira_cloud``, ``linear``, ``github_issues``, ``gitlab_issues``,
``azure_boards``.

Auth: webhook payloads carry no user session — instead a per-integration
secret signs the request. The router pulls the secret from
:class:`IssueTrackerIntegration` (decrypted) and asks the tracker
provider to verify via :meth:`parse_webhook_event` (each provider already
returns ``None`` on bad signature).

Routing: webhooks are *org-scoped* via the ``X-Org-Id`` header. In
production this is set by the deployment-layer ingress that strips a
per-org subdomain or a webhook secret prefix.
"""

from __future__ import annotations

import logging
import uuid as _uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.workers import service as svc
from ai_portal.workers.issues import registry as issues_registry
from ai_portal.workers.model import IssueTrackerIntegration
from ai_portal.workers.triggers.webhooks import resolve_match

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/workers/webhooks", tags=["workers", "webhooks"])


_ALLOWED_PROVIDERS = {
    "jira_cloud",
    "linear",
    "github_issues",
    "gitlab_issues",
    "azure_boards",
}


@router.post("/{provider}", status_code=status.HTTP_202_ACCEPTED)
async def receive_webhook(
    provider: str,
    request: Request,
    db: Session = Depends(get_db),
    x_org_id: str | None = Header(default=None, alias="X-Org-Id"),
) -> dict:
    """Receive a webhook, parse, match, submit."""
    if provider not in _ALLOWED_PROVIDERS:
        raise HTTPException(404, f"unknown provider {provider}")
    if not x_org_id:
        raise HTTPException(400, "missing X-Org-Id header")
    try:
        org_id = _uuid.UUID(x_org_id)
    except ValueError as e:
        raise HTTPException(400, "invalid org id") from e

    integ = (
        db.query(IssueTrackerIntegration)
        .filter(
            IssueTrackerIntegration.org_id == org_id,
            IssueTrackerIntegration.kind == provider,
            IssueTrackerIntegration.enabled.is_(True),
        )
        .first()
    )
    if integ is None:
        raise HTTPException(404, "no integration for provider")

    try:
        tracker = issues_registry.get(provider)
    except KeyError as e:
        raise HTTPException(404, "tracker not registered") from e

    payload = await request.json()
    headers = dict(request.headers)
    ev = tracker.parse_webhook_event(payload, headers)
    if ev is None:
        # signature bad or event irrelevant — both → 204 no-op
        return {"status": "ignored", "reason": "no_event"}

    match = resolve_match(
        ev, project_mapping=integ.project_mapping_json or {}
    )
    if match is None:
        return {"status": "ignored", "reason": "no_match"}

    task = svc.submit_task(
        db,
        org_id=org_id,
        pool_id=_uuid.UUID(match.pool_id),
        title=match.title,
        description=match.description,
        repo=match.repo,
        base_branch=match.base_branch,
        trigger_source=f"{provider}_webhook",
        trigger_payload=match.trigger_payload,
        created_by=None,
    )
    db.commit()
    return {"status": "submitted", "task_id": str(task.id)}
