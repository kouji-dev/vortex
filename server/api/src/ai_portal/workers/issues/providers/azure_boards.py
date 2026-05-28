"""Azure Boards tracker — Work Items REST API."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent


class AzureBoardsTracker:
    """Azure Boards work-item tracker.

    ``project`` is expected as ``{org}/{project}``. ``external_id`` is the
    numeric work-item id.
    """

    name = "azure_boards"

    def __init__(
        self,
        pat: str,
        *,
        base_url: str = "https://dev.azure.com",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._pat = pat
        self._base = base_url.rstrip("/")
        self._client = client

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f":{self._pat}".encode()).decode()
        return {
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    def _proj_url(self, project: str) -> str:
        return f"{self._base}/{project}/_apis/wit"

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]:
        wiql = (
            "SELECT [System.Id], [System.Title], [System.State] FROM WorkItems "
            f"WHERE [System.TeamProject] = '{project.split('/')[-1]}'"
        )
        if query:
            wiql += f" AND {query}"
        async with self._ctx() as c:
            r = await c.post(
                f"{self._proj_url(project)}/wiql?api-version=7.1",
                headers=self._headers(),
                json={"query": wiql},
            )
            r.raise_for_status()
            ids = [str(x["id"]) for x in r.json().get("workItems", [])]
        out: list[Issue] = []
        for wid in ids[:50]:
            out.append(await self.read_issue(project=project, external_id=wid))
        return out

    async def read_issue(self, *, project: str, external_id: str) -> Issue:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._proj_url(project)}/workitems/{external_id}?api-version=7.1",
                headers=self._headers(),
            )
            r.raise_for_status()
        return self._to_issue(r.json(), project)

    def _to_issue(self, raw: dict, project: str) -> Issue:
        fields = raw.get("fields", {}) or {}
        tags = fields.get("System.Tags", "") or ""
        labels = [t.strip() for t in tags.split(";") if t.strip()]
        url = (
            raw.get("_links", {}).get("html", {}).get("href")
            or raw.get("url", "")
        )
        return Issue(
            id=str(raw.get("id", "")),
            external_id=str(raw.get("id", "")),
            title=fields.get("System.Title", ""),
            body=fields.get("System.Description", "") or "",
            url=url,
            labels=labels,
            status=fields.get("System.State", ""),
            repo_hint=fields.get("System.TeamProject") or None,
        )

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._proj_url(project)}/workItems/{external_id}/comments?api-version=7.1-preview.3",
                headers=self._headers(),
                json={"text": body},
            )
            r.raise_for_status()

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None:
        patch: list[dict[str, Any]] = [
            {"op": "add", "path": "/fields/System.State", "value": status}
        ]
        async with self._ctx() as c:
            r = await c.patch(
                f"{self._proj_url(project)}/workitems/{external_id}?api-version=7.1",
                headers={
                    **self._headers(),
                    "Content-Type": "application/json-patch+json",
                },
                json=patch,
            )
            r.raise_for_status()

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None:
        if not payload.get("eventType", "").startswith("workitem."):
            return None
        resource = payload.get("resource", {})
        # Azure DevOps wraps work items differently per event-type; normalise.
        wi = resource.get("revision") or resource
        fields = wi.get("fields", {})
        proj = (
            fields.get("System.TeamProject", "")
            or payload.get("resourceContainers", {})
            .get("project", {})
            .get("name", "")
        )
        title = fields.get("System.Title", "")
        state = fields.get("System.State", "")
        tags = fields.get("System.Tags", "") or ""
        labels = [t.strip() for t in tags.split(";") if t.strip()]
        issue = Issue(
            id=str(wi.get("id", "")),
            external_id=str(wi.get("id", "")),
            title=title,
            body=fields.get("System.Description", "") or "",
            url=wi.get("_links", {}).get("html", {}).get("href", "")
            or wi.get("url", ""),
            labels=labels,
            status=state,
            repo_hint=proj or None,
        )
        event = payload.get("eventType", "")
        kind = (
            "created"
            if event.endswith("created")
            else "status_changed"
            if event.endswith("updated")
            else "commented"
            if "comment" in event
            else "status_changed"
        )
        return IssueWebhookEvent(
            kind=kind,
            issue=issue,
            actor=payload.get("createdBy", {}).get("uniqueName", "")
            or fields.get("System.ChangedBy", ""),
            raw=payload,
        )
