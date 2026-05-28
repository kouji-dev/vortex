"""Azure DevOps git provider — REST 7.x.

Repos in Azure DevOps live under ``{org}/{project}/_git/{repo}``. The
``RepoRef.full_name`` is expected as ``{org}/{project}/{repo}``.
"""

from __future__ import annotations

import base64
from typing import Any

import httpx

from ai_portal.workers.git.protocol import (
    PrEventParsed,
    PullRequest,
    RepoRef,
)
from ai_portal.workers.git.providers.github import (
    DefaultBranchPushBlocked,
    _sandbox_handle,
)

_DEFAULT_BRANCHES = {"main", "master", "trunk", "develop"}


class AzureDevOpsProvider:
    """Azure DevOps Services git provider."""

    name = "azure_devops"

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

    def _path(self, repo: RepoRef) -> str:
        org, project, name = repo.full_name.split("/", 2)
        return (
            f"{self._base}/{org}/{project}/_apis/git/repositories/{name}"
        )

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None:
        sp, sh = _sandbox_handle(sandbox)
        url = repo.clone_url.replace(
            "https://", f"https://x-access-token:{self._pat}@"
        )
        r = await sp.exec(sh, ["git", "clone", url, into])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def branch(
        self, sandbox: Any, *, name: str, base: str | None = None
    ) -> None:
        sp, sh = _sandbox_handle(sandbox)
        if base:
            await sp.exec(sh, ["git", "checkout", base])
        r = await sp.exec(sh, ["git", "checkout", "-b", name])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def commit(
        self, sandbox: Any, *, message: str, author: tuple[str, str]
    ) -> str:
        sp, sh = _sandbox_handle(sandbox)
        name, email = author
        await sp.exec(sh, ["git", "config", "user.name", name])
        await sp.exec(sh, ["git", "config", "user.email", email])
        await sp.exec(sh, ["git", "add", "-A"])
        r = await sp.exec(sh, ["git", "commit", "-m", message])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)
        return (await sp.exec(sh, ["git", "rev-parse", "HEAD"])).stdout.strip()

    async def push(self, sandbox: Any, *, branch: str) -> None:
        if branch in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(branch)
        sp, sh = _sandbox_handle(sandbox)
        r = await sp.exec(sh, ["git", "push", "-u", "origin", branch])
        if r.exit_code != 0:
            raise RuntimeError(r.stderr)

    async def create_pr(
        self,
        repo: RepoRef,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
        draft: bool = True,
    ) -> PullRequest:
        if head in _DEFAULT_BRANCHES:
            raise DefaultBranchPushBlocked(head)
        async with self._ctx() as c:
            r = await c.post(
                f"{self._path(repo)}/pullrequests?api-version=7.1",
                headers=self._headers(),
                json={
                    "sourceRefName": f"refs/heads/{head}",
                    "targetRefName": f"refs/heads/{base}",
                    "title": title,
                    "description": body,
                    "isDraft": draft,
                },
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d)

    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._path(repo)}/pullRequests/{pr_number}/threads?api-version=7.1",
                headers=self._headers(),
                json={
                    "comments": [{"parentCommentId": 0, "content": body, "commentType": 1}],
                    "status": 1,
                },
            )
            r.raise_for_status()

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._path(repo)}/pullrequests/{pr_number}?api-version=7.1",
                headers=self._headers(),
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d)

    async def update_pr(
        self,
        repo: RepoRef,
        pr_number: int,
        *,
        title: str | None = None,
        body: str | None = None,
        state: str | None = None,
        draft: bool | None = None,
    ) -> PullRequest:
        patch: dict[str, Any] = {}
        if title is not None:
            patch["title"] = title
        if body is not None:
            patch["description"] = body
        if state is not None:
            patch["status"] = state
        if draft is not None:
            patch["isDraft"] = draft
        async with self._ctx() as c:
            r = await c.patch(
                f"{self._path(repo)}/pullrequests/{pr_number}?api-version=7.1",
                headers=self._headers(),
                json=patch,
            )
            r.raise_for_status()
        return await self.read_pr(repo, pr_number)

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None:
        if payload.get("eventType", "").startswith("git.pullrequest"):
            pr = payload.get("resource", {})
            repo_d = pr.get("repository", {})
            project = repo_d.get("project", {})
            full = (
                f"{project.get('organization', '')}/"
                f"{project.get('name', '')}/{repo_d.get('name', '')}"
            )
            repo = RepoRef(
                full,
                repo_d.get("defaultBranch", "refs/heads/main").replace(
                    "refs/heads/", ""
                ),
                repo_d.get("remoteUrl", ""),
            )
            event = payload.get("eventType", "")
            kind = (
                "opened"
                if event.endswith("created")
                else "synchronized"
                if event.endswith("updated")
                else "closed"
                if event.endswith("merged") or pr.get("status") == "completed"
                else "comment"
            )
            return PrEventParsed(
                kind=kind,
                repo=repo,
                pr_number=int(pr.get("pullRequestId", 0)),
                actor=pr.get("createdBy", {}).get("uniqueName", ""),
                body=None,
            )
        return None

    def _to_pr(self, d: dict) -> PullRequest:
        return PullRequest(
            id=str(d.get("pullRequestId", "")),
            number=int(d.get("pullRequestId", 0)),
            url=d.get("url", ""),
            state="draft" if d.get("isDraft") else d.get("status", "active"),
            head_branch=str(d.get("sourceRefName", "")).replace(
                "refs/heads/", ""
            ),
            base_branch=str(d.get("targetRefName", "")).replace(
                "refs/heads/", ""
            ),
            title=d.get("title", ""),
            body=d.get("description") or "",
        )
