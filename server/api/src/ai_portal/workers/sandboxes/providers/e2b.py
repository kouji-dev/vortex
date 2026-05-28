"""E2B sandbox provider — managed micro-VM sandboxes over HTTP.

Thin httpx adapter against E2B's sandbox REST API. The actual host/path
layout is encapsulated so tests can mock with respx.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx

from ai_portal.workers.sandboxes.protocol import (
    ExecResult,
    SandboxHandle,
    SnapshotRef,
)
from ai_portal.workers.types import ResourceLimits


class E2BSandbox:
    """Sandbox provider backed by the E2B service."""

    name = "e2b"
    default_base = "https://api.e2b.dev"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._key = api_key
        self._base = (base_url or self.default_base).rstrip("/")
        self._client = client

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ctx(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(headers=self._headers())

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle:
        body = {
            "template": image,
            "metadata": {
                "egress_allow_list": egress_allow_list,
                "cpu_cores": limits.cpu_cores,
                "ram_mb": limits.ram_mb,
            },
            "envVars": env,
        }
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/sandboxes", json=body, headers=self._headers()
            )
            r.raise_for_status()
            data = r.json()
        return SandboxHandle(
            id=f"e2b-{uuid.uuid4().hex[:8]}",
            provider="e2b",
            provider_resource_id=str(data["sandboxID"]),
            workdir=data.get("workdir", "/home/user"),
            meta={
                "image": image,
                "limits": limits,
                "egress_allow_list": list(egress_allow_list),
            },
        )

    async def exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout_sec: int = 600,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        body = {
            "cmd": cmd,
            "cwd": cwd or h.workdir,
            "envVars": env or {},
            "timeoutMs": timeout_sec * 1000,
        }
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/sandboxes/{h.provider_resource_id}/exec",
                json=body,
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return ExecResult(
            exit_code=int(data.get("exitCode", 0)),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            duration_ms=int(data.get("durationMs", 0)),
            truncated=bool(data.get("truncated", False)),
        )

    async def stream_exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
    ) -> AsyncIterator[tuple[str, str]]:
        r = await self.exec(h, cmd, cwd=cwd, env=env, timeout_sec=timeout_sec)
        if r.stdout:
            yield ("stdout", r.stdout)
        if r.stderr:
            yield ("stderr", r.stderr)

    async def read_file(self, h: SandboxHandle, path: str) -> bytes:
        async with self._ctx() as c:
            r = await c.get(
                f"{self._base}/sandboxes/{h.provider_resource_id}/files",
                params={"path": path},
                headers=self._headers(),
            )
            r.raise_for_status()
        return r.content

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/sandboxes/{h.provider_resource_id}/files",
                params={"path": path},
                content=data,
                headers={**self._headers(), "Content-Type": "application/octet-stream"},
            )
            r.raise_for_status()

    async def kill(self, h: SandboxHandle) -> None:
        async with self._ctx() as c:
            r = await c.delete(
                f"{self._base}/sandboxes/{h.provider_resource_id}",
                headers=self._headers(),
            )
            if r.status_code not in (200, 202, 204, 404):
                r.raise_for_status()

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/sandboxes/{h.provider_resource_id}/snapshots",
                headers=self._headers(),
            )
            r.raise_for_status()
            data = r.json()
        return SnapshotRef(
            id=str(data["snapshotID"]),
            provider="e2b",
            size_bytes=int(data.get("sizeBytes", 0)),
        )

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle:
        body = {
            "snapshotID": snap.id,
            "envVars": env,
            "metadata": {"cpu_cores": limits.cpu_cores, "ram_mb": limits.ram_mb},
        }
        async with self._ctx() as c:
            r = await c.post(
                f"{self._base}/sandboxes", json=body, headers=self._headers()
            )
            r.raise_for_status()
            data = r.json()
        return SandboxHandle(
            id=f"e2b-{uuid.uuid4().hex[:8]}",
            provider="e2b",
            provider_resource_id=str(data["sandboxID"]),
            workdir=data.get("workdir", "/home/user"),
            meta={"limits": limits, "restored_from": snap.id},
        )
