"""Tests for the Daytona sandbox provider."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.sandboxes.protocol import SandboxHandle
from ai_portal.workers.sandboxes.providers.daytona import DaytonaSandbox
from ai_portal.workers.types import ResourceLimits


BASE = "https://daytona.example.com"


@pytest.mark.asyncio
async def test_provision_creates_workspace() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE}/api/workspace").mock(
            return_value=httpx.Response(
                200, json={"id": "ws-1", "workspaceDir": "/workspaces/repo"}
            )
        )
        sb = DaytonaSandbox(api_key="k", base_url=BASE)
        h = await sb.provision(
            image="img",
            limits=ResourceLimits(cpu_cores=4, ram_mb=8192),
            env={"X": "1"},
            egress_allow_list=["pypi.org"],
        )
    assert h.provider == "daytona"
    assert h.provider_resource_id == "ws-1"
    assert h.workdir == "/workspaces/repo"


@pytest.mark.asyncio
async def test_exec_calls_exec_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE}/api/workspace/ws-1/exec").mock(
            return_value=httpx.Response(
                200,
                json={"exitCode": 0, "stdout": "ok\n", "stderr": "", "durationMs": 7},
            )
        )
        sb = DaytonaSandbox(api_key="k", base_url=BASE)
        h = SandboxHandle(
            id="x", provider="daytona", provider_resource_id="ws-1",
            workdir="/workspaces", meta={},
        )
        r = await sb.exec(h, ["true"])
    assert r.exit_code == 0


@pytest.mark.asyncio
async def test_kill_deletes_workspace() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.delete(f"{BASE}/api/workspace/ws-1").mock(
            return_value=httpx.Response(204)
        )
        sb = DaytonaSandbox(api_key="k", base_url=BASE)
        h = SandboxHandle(
            id="x", provider="daytona", provider_resource_id="ws-1",
            workdir="/workspaces", meta={},
        )
        await sb.kill(h)


@pytest.mark.asyncio
async def test_snapshot_returns_ref() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post(f"{BASE}/api/workspace/ws-1/snapshot").mock(
            return_value=httpx.Response(
                200, json={"id": "snap-1", "sizeBytes": 9}
            )
        )
        sb = DaytonaSandbox(api_key="k", base_url=BASE)
        h = SandboxHandle(
            id="x", provider="daytona", provider_resource_id="ws-1",
            workdir="/workspaces", meta={},
        )
        snap = await sb.snapshot(h)
    assert snap.id == "snap-1"
    assert snap.size_bytes == 9
