"""Tests for the Docker sandbox provider — uses a fake docker client."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from ai_portal.workers.sandboxes.protocol import SandboxHandle
from ai_portal.workers.sandboxes.providers.docker import DockerSandbox
from ai_portal.workers.types import ResourceLimits


def _fake_client() -> Any:
    client = MagicMock()
    container = MagicMock()
    container.id = "c0ffee"
    client.containers.run.return_value = container
    client.containers.get.return_value = container
    return client, container


@pytest.mark.asyncio
async def test_provision_applies_resource_limits_and_security() -> None:
    client, _ = _fake_client()
    sb = DockerSandbox(client=client)
    h = await sb.provision(
        image="python:3.12",
        limits=ResourceLimits(cpu_cores=2, ram_mb=2048, max_processes=128),
        env={"FOO": "1"},
        egress_allow_list=["pypi.org", "github.com"],
    )
    args, kwargs = client.containers.run.call_args
    assert kwargs["image"] == "python:3.12"
    assert kwargs["mem_limit"] == "2048m"
    assert kwargs["nano_cpus"] == int(2 * 1e9)
    assert kwargs["pids_limit"] == 128
    assert kwargs["environment"] == {"FOO": "1"}
    assert kwargs["detach"] is True
    assert kwargs["working_dir"] == "/work"
    assert kwargs["cap_drop"] == ["ALL"]
    assert "no-new-privileges" in kwargs["security_opt"]
    assert kwargs["labels"]["ai_portal_worker"] == "1"
    assert "pypi.org" in kwargs["labels"]["egress_acl"]
    assert h.provider == "docker"
    assert h.provider_resource_id == "c0ffee"
    assert h.workdir == "/work"


@pytest.mark.asyncio
async def test_exec_returns_decoded_result() -> None:
    client, container = _fake_client()
    res = MagicMock()
    res.exit_code = 0
    res.output = (b"hello\n", b"")
    container.exec_run.return_value = res
    sb = DockerSandbox(client=client)
    h = SandboxHandle(
        id="x",
        provider="docker",
        provider_resource_id="c0ffee",
        workdir="/work",
        meta={},
    )
    r = await sb.exec(h, ["echo", "hello"])
    assert r.exit_code == 0
    assert "hello" in r.stdout
    assert r.stderr == ""


@pytest.mark.asyncio
async def test_exec_decodes_stderr() -> None:
    client, container = _fake_client()
    res = MagicMock()
    res.exit_code = 2
    res.output = (b"", b"boom\n")
    container.exec_run.return_value = res
    sb = DockerSandbox(client=client)
    h = SandboxHandle(
        id="x", provider="docker", provider_resource_id="c0ffee",
        workdir="/work", meta={},
    )
    r = await sb.exec(h, ["false"])
    assert r.exit_code == 2
    assert "boom" in r.stderr


@pytest.mark.asyncio
async def test_kill_calls_remove_force() -> None:
    client, container = _fake_client()
    sb = DockerSandbox(client=client)
    h = SandboxHandle(
        id="x", provider="docker", provider_resource_id="c0ffee",
        workdir="/work", meta={},
    )
    await sb.kill(h)
    container.kill.assert_called_once()
    container.remove.assert_called_once_with(force=True)


@pytest.mark.asyncio
async def test_snapshot_commits_to_image() -> None:
    client, container = _fake_client()
    img = MagicMock()
    img.id = "sha256:deadbeef"
    img.attrs = {"Size": 42}
    container.commit.return_value = img
    sb = DockerSandbox(client=client)
    h = SandboxHandle(
        id="x", provider="docker", provider_resource_id="c0ffee",
        workdir="/work", meta={},
    )
    snap = await sb.snapshot(h)
    assert snap.id == "sha256:deadbeef"
    assert snap.size_bytes == 42
    assert snap.provider == "docker"


@pytest.mark.asyncio
async def test_write_then_read_file_roundtrips_through_tar() -> None:
    client, container = _fake_client()

    captured: dict[str, bytes] = {}

    def fake_put_archive(parent: str, data: bytes) -> None:
        captured["data"] = data
        captured["parent"] = parent.encode()

    container.put_archive.side_effect = fake_put_archive

    def fake_get_archive(path: str) -> tuple[Any, dict]:
        import io as _io
        import tarfile as _tar

        buf = _io.BytesIO()
        with _tar.open(fileobj=buf, mode="w") as tf:
            info = _tar.TarInfo(name="hello.txt")
            info.size = 5
            tf.addfile(info, _io.BytesIO(b"hello"))
        buf.seek(0)
        return iter([buf.getvalue()]), {}

    container.get_archive.side_effect = fake_get_archive

    sb = DockerSandbox(client=client)
    h = SandboxHandle(
        id="x", provider="docker", provider_resource_id="c0ffee",
        workdir="/work", meta={},
    )
    await sb.write_file(h, "/work/hello.txt", b"hello")
    assert captured["parent"] == b"/work"
    data = await sb.read_file(h, "/work/hello.txt")
    assert data == b"hello"
