"""Tests for the E2B sandbox provider — respx mocks the HTTP layer."""

from __future__ import annotations

import httpx
import pytest
import respx

from ai_portal.workers.sandboxes.protocol import SandboxHandle
from ai_portal.workers.sandboxes.providers.e2b import E2BSandbox
from ai_portal.workers.types import ResourceLimits


@pytest.mark.asyncio
async def test_provision_posts_to_sandboxes_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.e2b.dev/sandboxes").mock(
            return_value=httpx.Response(
                200,
                json={"sandboxID": "sb-1", "workdir": "/home/user"},
            )
        )
        sb = E2BSandbox(api_key="k")
        h = await sb.provision(
            image="python-3.12",
            limits=ResourceLimits(),
            env={"X": "1"},
            egress_allow_list=["pypi.org"],
        )
    assert h.provider == "e2b"
    assert h.provider_resource_id == "sb-1"
    assert h.workdir == "/home/user"


@pytest.mark.asyncio
async def test_exec_posts_to_exec_endpoint() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.e2b.dev/sandboxes/sb-1/exec").mock(
            return_value=httpx.Response(
                200,
                json={
                    "exitCode": 0,
                    "stdout": "ok\n",
                    "stderr": "",
                    "durationMs": 5,
                },
            )
        )
        sb = E2BSandbox(api_key="k")
        h = SandboxHandle(
            id="x", provider="e2b", provider_resource_id="sb-1",
            workdir="/home/user", meta={},
        )
        r = await sb.exec(h, ["echo", "ok"])
    assert r.exit_code == 0
    assert r.stdout == "ok\n"
    assert r.duration_ms == 5


@pytest.mark.asyncio
async def test_kill_deletes_sandbox() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.delete("https://api.e2b.dev/sandboxes/sb-1").mock(
            return_value=httpx.Response(204)
        )
        sb = E2BSandbox(api_key="k")
        h = SandboxHandle(
            id="x", provider="e2b", provider_resource_id="sb-1",
            workdir="/home/user", meta={},
        )
        await sb.kill(h)


@pytest.mark.asyncio
async def test_snapshot_returns_ref() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.e2b.dev/sandboxes/sb-1/snapshots").mock(
            return_value=httpx.Response(
                200, json={"snapshotID": "snap-99", "sizeBytes": 1234}
            )
        )
        sb = E2BSandbox(api_key="k")
        h = SandboxHandle(
            id="x", provider="e2b", provider_resource_id="sb-1",
            workdir="/home/user", meta={},
        )
        snap = await sb.snapshot(h)
    assert snap.id == "snap-99"
    assert snap.size_bytes == 1234


@pytest.mark.asyncio
async def test_write_and_read_file() -> None:
    async with respx.mock(assert_all_called=True) as mock:
        mock.post("https://api.e2b.dev/sandboxes/sb-1/files").mock(
            return_value=httpx.Response(200)
        )
        mock.get("https://api.e2b.dev/sandboxes/sb-1/files").mock(
            return_value=httpx.Response(200, content=b"hello")
        )
        sb = E2BSandbox(api_key="k")
        h = SandboxHandle(
            id="x", provider="e2b", provider_resource_id="sb-1",
            workdir="/home/user", meta={},
        )
        await sb.write_file(h, "/work/foo.txt", b"hello")
        data = await sb.read_file(h, "/work/foo.txt")
    assert data == b"hello"
