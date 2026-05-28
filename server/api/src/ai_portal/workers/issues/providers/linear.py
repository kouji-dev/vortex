"""Linear issue tracker — GraphQL over httpx."""

from __future__ import annotations

import httpx

from ai_portal.workers.issues.protocol import Issue, IssueWebhookEvent


_LIST_Q = """
query Issues($team: String!, $filter: String) {
  issues(filter: { team: { key: { eq: $team } } }, first: 50) {
    nodes { id identifier title description url labels { nodes { name } } state { name } }
  }
}
"""

_READ_Q = """
query Issue($id: String!) {
  issue(id: $id) {
    id identifier title description url labels { nodes { name } } state { name }
  }
}
"""

_COMMENT_M = """
mutation Comment($issueId: String!, $body: String!) {
  commentCreate(input: { issueId: $issueId, body: $body }) { success }
}
"""

_UPDATE_M = """
mutation Update($id: String!, $stateId: String!) {
  issueUpdate(id: $id, input: { stateId: $stateId }) { success }
}
"""

_STATES_Q = """
query States($team: String!) {
  workflowStates(filter: { team: { key: { eq: $team } } }) { nodes { id name } }
}
"""


class LinearTracker:
    """Linear tracker via GraphQL ``https://api.linear.app/graphql``."""

    name = "linear"
    endpoint = "https://api.linear.app/graphql"

    def __init__(
        self,
        api_key: str,
        *,
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key = api_key
        self._secret = webhook_secret
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._key,
            "Content-Type": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    async def _gql(self, query: str, variables: dict) -> dict:
        async with self._ctx() as c:
            r = await c.post(
                self.endpoint,
                headers=self._headers(),
                json={"query": query, "variables": variables},
            )
            r.raise_for_status()
            data = r.json()
        if "errors" in data:
            raise RuntimeError(str(data["errors"]))
        return data["data"]

    async def list_issues(
        self, *, project: str, query: str | None = None
    ) -> list[Issue]:
        d = await self._gql(_LIST_Q, {"team": project, "filter": query})
        return [self._to_issue(x) for x in d["issues"]["nodes"]]

    async def read_issue(self, *, project: str, external_id: str) -> Issue:
        d = await self._gql(_READ_Q, {"id": external_id})
        return self._to_issue(d["issue"])

    async def comment_issue(
        self, *, project: str, external_id: str, body: str
    ) -> None:
        await self._gql(_COMMENT_M, {"issueId": external_id, "body": body})

    async def set_status(
        self, *, project: str, external_id: str, status: str
    ) -> None:
        d = await self._gql(_STATES_Q, {"team": project})
        state = next(
            (
                s
                for s in d["workflowStates"]["nodes"]
                if s["name"].lower() == status.lower()
            ),
            None,
        )
        if not state:
            raise ValueError(f"no state {status} on team {project}")
        await self._gql(
            _UPDATE_M, {"id": external_id, "stateId": state["id"]}
        )

    def parse_webhook_event(
        self, payload: dict, headers: dict
    ) -> IssueWebhookEvent | None:
        if self._secret is not None:
            if headers.get("Linear-Signature") is None:
                return None
        if payload.get("type") != "Issue":
            return None
        data = payload.get("data") or {}
        if not data:
            return None
        action = payload.get("action", "create")
        kind = (
            "created"
            if action == "create"
            else "status_changed"
            if action == "update"
            and any("state" in c for c in payload.get("updatedFrom", {}))
            else "labeled"
            if action == "update"
            and any("label" in c for c in payload.get("updatedFrom", {}))
            else "commented"
            if action == "create" and payload.get("type") == "Comment"
            else "status_changed"
        )
        return IssueWebhookEvent(
            kind=kind,
            issue=self._to_issue(data),
            actor=payload.get("actor", {}).get("name", "")
            or data.get("creator", {}).get("name", ""),
            raw=payload,
        )

    def _to_issue(self, raw: dict) -> Issue:
        labels = []
        node = raw.get("labels", {})
        if isinstance(node, dict):
            labels = [n["name"] for n in node.get("nodes", []) or []]
        elif isinstance(node, list):
            labels = [
                n.get("name", "") if isinstance(n, dict) else str(n)
                for n in node
            ]
        state = raw.get("state") or {}
        if not isinstance(state, dict):
            state = {}
        return Issue(
            id=str(raw.get("id", "")),
            external_id=raw.get("identifier") or raw.get("id", ""),
            title=raw.get("title", ""),
            body=raw.get("description", "") or "",
            url=raw.get("url", ""),
            labels=labels,
            status=state.get("name", ""),
            repo_hint=None,
        )
