"""GitLab connector.

Walks projects under a group or a single project. Yields README + docs/ tree
+ issues. SDK (``python-gitlab``) hidden behind ``_GitlabClient`` so tests
inject a fake.

ACL: project member usernames. Delta: issue ``updated_at``.
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
    name="gitlab",
    auth_kinds=("token", "oauth"),
    schedulable=True,
    supports_delta=True,
    supports_acl=True,
    supports_webhook=True,
    config_schema={
        "type": "object",
        "required": ["scope_type", "scope_id"],
        "properties": {
            "scope_type": {"enum": ["group", "project"]},
            "scope_id": {"type": "string"},
            "base_url": {"type": "string", "default": "https://gitlab.com"},
            "include_issues": {"type": "boolean", "default": True},
        },
    },
)


class _GitlabClient:
    """Lazy wrapper around ``gitlab.Gitlab``."""

    def __init__(self, base_url: str, token: str | None) -> None:
        self._base_url = base_url
        self._token = token
        self._svc: Any | None = None

    def _resolve(self) -> Any:
        if self._svc is None:
            import gitlab  # type: ignore

            self._svc = gitlab.Gitlab(self._base_url, private_token=self._token)
        return self._svc

    async def list_projects(self, scope_type: str, scope_id: str) -> list[dict[str, Any]]:
        svc = self._resolve()
        if scope_type == "group":
            grp = svc.groups.get(scope_id)
            return [{"id": p.id, "path_with_namespace": p.path_with_namespace}
                    for p in grp.projects.list(all=True)]
        proj = svc.projects.get(scope_id)
        return [{"id": proj.id, "path_with_namespace": proj.path_with_namespace}]

    async def list_docs(self, project_id: Any) -> list[dict[str, Any]]:
        svc = self._resolve()
        proj = svc.projects.get(project_id)
        tree = proj.repository_tree(path="docs", recursive=True, all=True)
        return [{"path": "README.md"}] + [
            {"path": item["path"]} for item in tree if item["type"] == "blob"
        ]

    async def get_blob(self, project_id: Any, path: str) -> bytes:
        svc = self._resolve()
        proj = svc.projects.get(project_id)
        return proj.files.raw(file_path=path, ref="HEAD")

    async def list_issues(self, project_id: Any) -> list[dict[str, Any]]:
        svc = self._resolve()
        proj = svc.projects.get(project_id)
        return [
            {
                "iid": i.iid,
                "title": i.title,
                "description": i.description or "",
                "updated_at": i.updated_at,
            }
            for i in proj.issues.list(all=True)
        ]

    async def list_members(self, project_id: Any) -> list[str]:
        svc = self._resolve()
        proj = svc.projects.get(project_id)
        return [m.username for m in proj.members_all.list(all=True)]


class GitlabConnector:
    """GitLab project walker — docs + issues + members."""

    manifest = _MANIFEST

    def __init__(self, config: dict[str, Any], client: Any) -> None:
        self._config = config
        self._client = client
        self._cursor: str | None = None

    @classmethod
    async def setup(
        cls, config: dict[str, Any], secret_store: Any
    ) -> "GitlabConnector":
        client = (
            getattr(secret_store, "gitlab_client", None)
            if secret_store is not None
            else None
        )
        if client is None:
            base_url = config.get("base_url", "https://gitlab.com")
            token = (
                getattr(secret_store, "gitlab_token", lambda: None)()
                if secret_store is not None
                else None
            )
            client = _GitlabClient(base_url, token)
        return cls(config, client)

    async def discover(
        self, cursor: str | None
    ) -> AsyncIterator[SourceDoc]:
        projects = await self._client.list_projects(
            self._config["scope_type"], self._config["scope_id"]
        )
        max_ts = cursor
        for p in projects:
            slug = p["path_with_namespace"]
            pid = p["id"]
            for doc in await self._client.list_docs(pid):
                yield SourceDoc(
                    source_uri=f"gitlab://{slug}/blob/{doc['path']}",
                    title=doc["path"],
                    mime="text/markdown" if doc["path"].endswith(".md") else "text/plain",
                    size=None,
                    modified_at=None,
                    cursor_token=None,
                    raw={"project_id": pid, "slug": slug, "path": doc["path"]},
                )
            if self._config.get("include_issues", True):
                for i in await self._client.list_issues(pid):
                    upd = i.get("updated_at")
                    if cursor and upd and upd <= cursor:
                        continue
                    if upd and (max_ts is None or upd > max_ts):
                        max_ts = upd
                    yield SourceDoc(
                        source_uri=f"gitlab://{slug}/issues/{i['iid']}",
                        title=i["title"],
                        mime="text/markdown",
                        size=len(i["description"]) or None,
                        modified_at=None,
                        cursor_token=upd,
                        raw={"project_id": pid, "slug": slug, **i},
                    )
        if max_ts:
            self._cursor = max_ts

    async def fetch(self, sd: SourceDoc) -> FetchedDoc:
        if "/blob/" in sd.source_uri:
            data = await self._client.get_blob(sd.raw["project_id"], sd.raw["path"])
            return FetchedDoc(
                data=data,
                mime=sd.mime or "text/plain",
                meta={"path": sd.raw["path"]},
            )
        return FetchedDoc(
            data=(sd.raw.get("description") or "").encode("utf-8"),
            mime="text/markdown",
            meta={k: v for k, v in sd.raw.items() if k != "description"},
        )

    async def acls(self, sd: SourceDoc) -> AclSet:
        pid = sd.raw.get("project_id")
        if pid is None:
            return AclSet()
        try:
            members = await self._client.list_members(pid)
        except Exception:
            return AclSet()
        return AclSet(user_ids=set(members))

    async def delta_cursor(self) -> str | None:
        return self._cursor

    async def apply_delta_cursor(self, cursor: str) -> None:
        self._cursor = cursor


register(GitlabConnector)
