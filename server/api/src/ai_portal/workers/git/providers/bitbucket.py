"""Bitbucket Cloud git provider — REST API 2.0 over httpx."""

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


class BitbucketProvider:
    """Bitbucket Cloud (v2) provider."""

    name = "bitbucket"
    base = "https://api.bitbucket.org/2.0"

    def __init__(
        self,
        *,
        username: str,
        app_password: str,
        webhook_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._user = username
        self._pw = app_password
        self._secret = webhook_secret
        self._client = client

    def _headers(self) -> dict[str, str]:
        auth = base64.b64encode(
            f"{self._user}:{self._pw}".encode()
        ).decode()
        return {
            "Authorization": f"Basic {auth}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    async def clone(self, repo: RepoRef, *, into: str, sandbox: Any) -> None:
        sp, sh = _sandbox_handle(sandbox)
        creds = f"{self._user}:{self._pw}"
        url = repo.clone_url.replace("https://", f"https://{creds}@")
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
                f"{self.base}/repositories/{repo.full_name}/pullrequests",
                headers=self._headers(),
                json={
                    "title": ("DRAFT: " + title) if draft else title,
                    "description": body,
                    "source": {"branch": {"name": head}},
                    "destination": {"branch": {"name": base}},
                },
            )
            r.raise_for_status()
            d = r.json()
        return self._to_pr(d, base_default=base)

    async def comment_pr(self, repo: RepoRef, pr_number: int, body: str) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self.base}/repositories/{repo.full_name}"
                f"/pullrequests/{pr_number}/comments",
                headers=self._headers(),
                json={"content": {"raw": body}},
            )
            r.raise_for_status()

    async def read_pr(self, repo: RepoRef, pr_number: int) -> PullRequest:
        async with self._ctx() as c:
            r = await c.get(
                f"{self.base}/repositories/{repo.full_name}"
                f"/pullrequests/{pr_number}",
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
        async with self._ctx() as c:
            r = await c.put(
                f"{self.base}/repositories/{repo.full_name}"
                f"/pullrequests/{pr_number}",
                headers=self._headers(),
                json=patch,
            )
            r.raise_for_status()
        return await self.read_pr(repo, pr_number)

    def parse_pr_event(
        self, payload: dict, headers: dict
    ) -> PrEventParsed | None:
        if self._secret is not None:
            # Bitbucket uses ``X-Hub-Signature`` with HMAC-SHA256 of the body.
            if headers.get("X-Hook-UUID") is None and headers.get(
                "X-Hub-Signature"
            ) is None:
                return None
        pr = payload.get("pullrequest")
        if not pr:
            return None
        repo_d = payload.get("repository", {})
        full = repo_d.get("full_name", "")
        clone_url = ""
        for link in (repo_d.get("links", {}).get("clone", []) or []):
            if link.get("name") == "https":
                clone_url = link.get("href", "")
                break
        repo = RepoRef(full, "main", clone_url)
        event_key = headers.get("X-Event-Key", "")
        kind = (
            "opened"
            if event_key.endswith(":created")
            else "synchronized"
            if event_key.endswith(":updated")
            else "closed"
            if event_key.endswith(":fulfilled") or event_key.endswith(":rejected")
            else "comment"
        )
        return PrEventParsed(
            kind=kind,
            repo=repo,
            pr_number=int(pr.get("id", 0)),
            actor=payload.get("actor", {}).get("username")
            or payload.get("actor", {}).get("display_name", ""),
            body=payload.get("comment", {}).get("content", {}).get("raw"),
        )

    def _to_pr(self, d: dict, *, base_default: str = "main") -> PullRequest:
        return PullRequest(
            id=str(d.get("id", "")),
            number=int(d.get("id", 0)),
            url=d.get("links", {}).get("html", {}).get("href", ""),
            state=str(d.get("state", "OPEN")).lower(),
            head_branch=d.get("source", {}).get("branch", {}).get("name", ""),
            base_branch=d.get("destination", {})
            .get("branch", {})
            .get("name", base_default),
            title=d.get("title", ""),
            body=d.get("description") or "",
        )
