"""GitHub connector.

Walks repos under an org or a single repo. For each repo it yields:

- README and ``docs/`` tree (code + docs)
- Issues + pull requests
- Wiki pages (if enabled)

SDK (PyGithub) is hidden behind ``_GithubClient`` so tests inject a fake.

ACL: repo collaborators (login set). Delta: updated_at timestamps.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from ai_portal.rag.connectors import register
from ai_portal.rag.connectors.manifest import ConnectorManifest
from ai_portal.rag.connectors.protocol import (
    AclSet,
    FetchedDoc,
    SourceDoc,
)

_MANIFEST = ConnectorManifest(
    name="github",
    auth_kinds=("token", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["scope_type", "scope_id"],
        "properties": {
            "scope_type": {"enum": ["org", "repo"]},
            "scope_id": {"type": "string"},
            "include_issues": {"type": "boolean", "default": True},
            "include_pulls": {"type": "boolean", "default": True},
            "include_wiki": {"type": "boolean", "default": False},
        },
    },
)


class _GithubClient:
    """Lazy wrapper around ``github.Github``."""

    def __init__(self, token: str | None) -> None:
        self._token = token
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            from github import Github  # type: ignore

            self._svc = Github(login_or_token=self._token)
        return self._svc

    async def list_repos(self, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        if scope_type == "org":
            org = svc.get_organization(scope_id)
            return [{"full_name": r.full_name, "name": r.name} for r in org.get_repos()]
        return [{"full_name": scope_id, "name": scope_id.split("/")[-1]}]

    async def list_docs(self, repo_full_name: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        repo = svc.get_repo(repo_full_name)
        out = [{"path": "README.md", "sha": repo.get_readme().sha, "updated_at": None}]
        for c in repo.get_contents("docs"):
            out.append({"path": c.path, "sha": c.sha, "updated_at": None})
        return out

    async def list_issues(self, repo_full_name: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        repo = svc.get_repo(repo_full_name)
        return [
            {
                "number": i.number,
                "title": i.title,
                "body": i.body or "",
                "updated_at": i.updated_at.isoformat() if i.updated_at else None,
                "is_pull": i.pull_request is not None,
            }
            for i in repo.get_issues(state="all")
        ]

    async def get_blob(self, repo_full_name: str, path: str) -> bytes:
        svc = self._resolve()
        repo = svc.get_repo(repo_full_name)
        return repo.get_contents(path).decoded_content

    async def list_collaborators(self, repo_full_name: str) -> list[str]:
        svc = self._resolve()
        repo = svc.get_repo(repo_full_name)
        return [c.login for c in repo.get_collaborators()]


class GithubConnector:
    """GitHub repo walker — docs + issues + PRs + collaborators."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "GithubConnector":
        client = (
            getattr(secret_store, "github_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            token = (
                getattr(secret_store, "github_token", lambda: None)()
                if secret_store is not None
                else None
            )
            client = _GithubClient(token)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        repos = await self._client.list_repos(
            self._config["scope_type"], self._config["scope_id"]
        )
        max_ts = cursor
        for r in repos:
            full = r["full_name"]
            for doc in await self._client.list_docs(full):
                yield SourceDoc(
                    source_uri=f"github://{full}/blob/{doc['path']}",
                    title=doc["path"],
                    mime="text/markdown" if doc["path"].endswith(".md") else "text/plain",
                    size=None,
                    modified_at=None,
                    cursor_token=doc.get("sha"),
                    raw={"repo": full, "path": doc["path"]},
                )
            if self._config.get("include_issues", True) or self._config.get(
                "include_pulls", True
            ):
                for i in await self._client.list_issues(full):
                    if i["is_pull"] and not self._config.get("include_pulls", True):
                        continue
                    if not i["is_pull"] and not self._config.get(
                        "include_issues", True
                    ):
                        continue
                    updated = i.get("updated_at")
                    if cursor and updated and updated <= cursor:
                        continue
                    if updated and (max_ts is None or updated > max_ts):
                        max_ts = updated
                    kind = "pull" if i["is_pull"] else "issue"
                    yield SourceDoc(
                        source_uri=f"github://{full}/{kind}s/{i['number']}",
                        title=i["title"],
                        mime="text/markdown",
                        size=len(i["body"]) or None,
                        modified_at=None,
                        cursor_token=updated,
                        raw={"repo": full, **i},
                    )
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        if "/blob/" in sd.source_uri:
            repo = sd.raw["repo"]
            path = sd.raw["path"]
            data = await self._client.get_blob(repo, path)
            return FetchedDoc(data=data, mime=sd.mime or "text/plain", meta={"path": path})
        return FetchedDoc(
            data=(sd.raw.get("body") or "").encode("utf-8"),
            mime="text/markdown",
            meta={k: v for k, v in sd.raw.items() if k != "body"},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        repo = sd.raw.get("repo", "")
        try:
            logins = await self._client.list_collaborators(repo)
        except Exception:
            return AclSet()
        return AclSet(user_ids=set(logins))

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(GithubConnector)
