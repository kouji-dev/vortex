"""Tests for the in-memory fake sandbox provider + registry."""

from __future__ import annotations

import pytest

from ai_portal.workers.sandboxes import registry
from ai_portal.workers.sandboxes.protocol import SandboxProvider
from ai_portal.workers.sandboxes.providers.fake import FakeSandbox
from ai_portal.workers.types import ResourceLimits


@pytest.mark.asyncio
async def test_fake_full_lifecycle() -> None:
    sb = FakeSandbox()
    h = await sb.provision(
        image="python:3.12",
        limits=ResourceLimits(),
        env={"X": "1"},
        egress_allow_list=["pypi.org"],
    )
    assert h.provider == "fake"
    assert h.workdir == "/work"
    assert h.meta["egress_allow_list"] == ["pypi.org"]
    assert h.meta["env"] == {"X": "1"}

    await sb.write_file(h, "/work/hello.txt", b"hi")
    assert await sb.read_file(h, "/work/hello.txt") == b"hi"

    r = await sb.exec(h, ["echo", "ok"])
    assert r.exit_code == 0
    assert "ok" in r.stdout

    snap = await sb.snapshot(h)
    assert snap.size_bytes >= 2

    h2 = await sb.restore(snap, limits=ResourceLimits(), env={})
    assert await sb.read_file(h2, "/work/hello.txt") == b"hi"

    await sb.kill(h)
    r2 = await sb.exec(h, ["echo", "after-kill"])
    assert r2.exit_code == 137
    assert r2.stderr == "killed"


@pytest.mark.asyncio
async def test_fake_scripted_exec() -> None:
    sb = FakeSandbox(
        scripts={("python", "-V"): (0, "Python 3.12.0\n", "")},
    )
    h = await sb.provision(
        image="python:3.12",
        limits=ResourceLimits(),
        env={},
        egress_allow_list=[],
    )
    r = await sb.exec(h, ["python", "-V"])
    assert "3.12" in r.stdout
    assert r.exit_code == 0


@pytest.mark.asyncio
async def test_fake_stream_exec_yields_chunks() -> None:
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    chunks: list[tuple[str, str]] = []
    async for stream, chunk in sb.stream_exec(h, ["echo", "x", "y"]):
        chunks.append((stream, chunk))
    assert chunks == [("stdout", "x y\n")]


@pytest.mark.asyncio
async def test_fake_exec_log_records_commands() -> None:
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    await sb.exec(h, ["true"])
    await sb.exec(h, ["false"])
    assert sb.exec_log == [["true"], ["false"]]


@pytest.mark.asyncio
async def test_fake_default_exec_returns_zero() -> None:
    sb = FakeSandbox()
    h = await sb.provision(
        image="x", limits=ResourceLimits(), env={}, egress_allow_list=[]
    )
    r = await sb.exec(h, ["pytest", "-x"])
    assert r.exit_code == 0


def test_fake_satisfies_protocol() -> None:
    assert isinstance(FakeSandbox(), SandboxProvider)


def test_registry_roundtrip() -> None:
    registry.clear()
    sb = FakeSandbox()
    registry.register(sb)
    assert registry.get("fake") is sb
    assert "fake" in registry.all_providers()
    registry.clear()
    with pytest.raises(KeyError):
        registry.get("fake")
