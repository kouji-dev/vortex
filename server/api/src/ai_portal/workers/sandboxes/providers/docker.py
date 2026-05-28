"""Docker sandbox provider — local-dev exemplar.

Provisions a long-running container per task. Resource limits applied via
docker SDK ``mem_limit``, ``nano_cpus``, ``pids_limit``. Egress restricted
by binding the container to a pre-created bridge network at deploy time
(``wp-egress-<pool_id>``); the allow-list is recorded as a container label
so iptables/CoreDNS sidecars can read it.

Security defaults:
- ``cap_drop=["ALL"]``
- ``security_opt=["no-new-privileges"]``
- ``read_only=False`` (workdir writeable; root fs hardening left to image)
- ``/tmp`` mounted as tmpfs

Exec is dispatched via the docker SDK in a thread (the sync SDK can't be
awaited natively).
"""

from __future__ import annotations

import asyncio
import io
import tarfile
import uuid
from typing import Any, AsyncIterator

try:
    import docker  # type: ignore[import-not-found]
    from docker import errors as docker_errors  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover — exercised when docker not installed
    docker = None  # type: ignore[assignment]
    docker_errors = None  # type: ignore[assignment]

from ai_portal.workers.sandboxes.protocol import (
    ExecResult,
    SandboxHandle,
    SnapshotRef,
)
from ai_portal.workers.types import ResourceLimits


class DockerNotAvailable(RuntimeError):
    """Raised when the docker python SDK isn't installed."""


class DockerSandbox:
    """Sandbox provider backed by a local Docker daemon."""

    name = "docker"

    def __init__(self, client: Any | None = None) -> None:
        if client is not None:
            self._client = client
            return
        if docker is None:
            raise DockerNotAvailable(
                "docker python SDK not installed; pip install docker"
            )
        self._client = docker.from_env()

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle:
        loop = asyncio.get_event_loop()

        def _run() -> Any:
            return self._client.containers.run(
                image=image,
                command="sleep infinity",
                detach=True,
                mem_limit=f"{limits.ram_mb}m",
                nano_cpus=int(limits.cpu_cores * 1e9),
                pids_limit=limits.max_processes,
                network_mode="bridge",
                environment=dict(env),
                working_dir="/work",
                tmpfs={"/tmp": "rw,size=512m"},
                cap_drop=["ALL"],
                security_opt=["no-new-privileges"],
                read_only=False,
                labels={
                    "ai_portal_worker": "1",
                    "egress_acl": ",".join(egress_allow_list),
                },
            )

        container = await loop.run_in_executor(None, _run)
        return SandboxHandle(
            id=f"docker-{uuid.uuid4().hex[:8]}",
            provider="docker",
            provider_resource_id=container.id,
            workdir="/work",
            meta={
                "image": image,
                "egress_allow_list": list(egress_allow_list),
                "limits": limits,
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
        loop = asyncio.get_event_loop()

        def _do() -> ExecResult:
            c = self._client.containers.get(h.provider_resource_id)
            res = c.exec_run(
                cmd=cmd,
                workdir=cwd or h.workdir,
                environment=env or {},
                demux=True,
            )
            ec = res.exit_code
            out, err = res.output if isinstance(res.output, tuple) else (res.output, b"")
            return ExecResult(
                exit_code=ec if ec is not None else -1,
                stdout=(out or b"").decode("utf-8", errors="replace"),
                stderr=(err or b"").decode("utf-8", errors="replace"),
                duration_ms=0,
                truncated=False,
            )

        return await asyncio.wait_for(
            loop.run_in_executor(None, _do), timeout=timeout_sec
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
        loop = asyncio.get_event_loop()

        def _start() -> Any:
            c = self._client.containers.get(h.provider_resource_id)
            _, gen = c.exec_run(
                cmd=cmd,
                workdir=cwd or h.workdir,
                environment=env or {},
                stream=True,
                demux=True,
            )
            return gen

        gen = await loop.run_in_executor(None, _start)
        for stdout_chunk, stderr_chunk in gen:
            if stdout_chunk:
                yield ("stdout", stdout_chunk.decode("utf-8", errors="replace"))
            if stderr_chunk:
                yield ("stderr", stderr_chunk.decode("utf-8", errors="replace"))

    async def read_file(self, h: SandboxHandle, path: str) -> bytes:
        loop = asyncio.get_event_loop()

        def _do() -> bytes:
            c = self._client.containers.get(h.provider_resource_id)
            stream, _ = c.get_archive(path)
            buf = b"".join(stream)
            with tarfile.open(fileobj=io.BytesIO(buf)) as tf:
                m = tf.next()
                if m is None:
                    return b""
                f = tf.extractfile(m)
                return f.read() if f else b""

        return await loop.run_in_executor(None, _do)

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None:
        loop = asyncio.get_event_loop()

        def _do() -> None:
            c = self._client.containers.get(h.provider_resource_id)
            tar_buf = io.BytesIO()
            name = path.rsplit("/", 1)[-1]
            parent = path.rsplit("/", 1)[0] or "/"
            with tarfile.open(fileobj=tar_buf, mode="w") as tf:
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mode = 0o644
                tf.addfile(info, io.BytesIO(data))
            tar_buf.seek(0)
            c.put_archive(parent, tar_buf.getvalue())

        await loop.run_in_executor(None, _do)

    async def kill(self, h: SandboxHandle) -> None:
        loop = asyncio.get_event_loop()

        def _do() -> None:
            try:
                c = self._client.containers.get(h.provider_resource_id)
                c.kill()
                c.remove(force=True)
            except Exception:  # noqa: BLE001 — best-effort cleanup
                pass

        await loop.run_in_executor(None, _do)

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        loop = asyncio.get_event_loop()

        def _do() -> SnapshotRef:
            c = self._client.containers.get(h.provider_resource_id)
            img = c.commit(repository="ai_portal_snap", tag=h.id)
            size = 0
            attrs = getattr(img, "attrs", None) or {}
            size = int(attrs.get("Size", 0))
            return SnapshotRef(
                id=img.id,
                provider="docker",
                size_bytes=size,
            )

        return await loop.run_in_executor(None, _do)

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle:
        return await self.provision(
            image=snap.id,
            limits=limits,
            env=env,
            egress_allow_list=[],
        )
