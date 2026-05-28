"""In-memory fake sandbox provider — used by tests.

Simulates exec/read/write/snapshot/restore without containers or
networking. Behaviour is deterministic so test assertions stay stable.

Scripted exec: pass ``scripts={("python", "-V"): (0, "Python 3.12\\n", "")}``
to the constructor to override default exec behaviour for specific commands.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

from ai_portal.workers.sandboxes.protocol import (
    ExecResult,
    SandboxHandle,
    SnapshotRef,
)
from ai_portal.workers.types import ResourceLimits


class FakeSandbox:
    """Test double satisfying :class:`SandboxProvider`."""

    name = "fake"

    def __init__(
        self,
        scripts: dict[tuple[str, ...], tuple[int, str, str]] | None = None,
    ) -> None:
        self._fs: dict[str, dict[str, bytes]] = {}
        self._scripts: dict[tuple[str, ...], tuple[int, str, str]] = (
            dict(scripts) if scripts else {}
        )
        self._snapshots: dict[str, dict[str, bytes]] = {}
        self._killed: set[str] = set()
        # Audit-style records (tests can inspect).
        self.exec_log: list[list[str]] = []

    def script(self, cmd: tuple[str, ...], result: tuple[int, str, str]) -> None:
        """Register a scripted exec result for ``cmd``."""
        self._scripts[cmd] = result

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle:
        sid = f"fake-{uuid.uuid4().hex[:8]}"
        self._fs[sid] = {}
        return SandboxHandle(
            id=sid,
            provider="fake",
            provider_resource_id=sid,
            workdir="/work",
            meta={
                "image": image,
                "env": dict(env),
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
        self.exec_log.append(list(cmd))
        if h.id in self._killed:
            return ExecResult(
                exit_code=137,
                stdout="",
                stderr="killed",
                duration_ms=0,
                truncated=False,
            )
        key = tuple(cmd)
        if key in self._scripts:
            ec, out, err = self._scripts[key]
            return ExecResult(
                exit_code=ec,
                stdout=out,
                stderr=err,
                duration_ms=1,
                truncated=False,
            )
        if cmd and cmd[0] == "echo":
            return ExecResult(
                exit_code=0,
                stdout=" ".join(cmd[1:]) + "\n",
                stderr="",
                duration_ms=1,
                truncated=False,
            )
        if cmd and cmd[0] == "true":
            return ExecResult(
                exit_code=0,
                stdout="",
                stderr="",
                duration_ms=1,
                truncated=False,
            )
        if cmd and cmd[0] == "false":
            return ExecResult(
                exit_code=1,
                stdout="",
                stderr="",
                duration_ms=1,
                truncated=False,
            )
        # Default: ok with empty output.
        return ExecResult(
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1,
            truncated=False,
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
        r = await self.exec(
            h, cmd, cwd=cwd, env=env, timeout_sec=timeout_sec
        )
        if r.stdout:
            yield ("stdout", r.stdout)
        if r.stderr:
            yield ("stderr", r.stderr)

    async def read_file(self, h: SandboxHandle, path: str) -> bytes:
        return self._fs[h.id][path]

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None:
        self._fs.setdefault(h.id, {})[path] = data

    async def kill(self, h: SandboxHandle) -> None:
        self._killed.add(h.id)

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        sid = f"snap-{uuid.uuid4().hex[:8]}"
        snap = dict(self._fs.get(h.id, {}))
        self._snapshots[sid] = snap
        return SnapshotRef(
            id=sid,
            provider="fake",
            size_bytes=sum(len(v) for v in snap.values()),
        )

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle:
        sid = f"fake-{uuid.uuid4().hex[:8]}"
        self._fs[sid] = dict(self._snapshots[snap.id])
        return SandboxHandle(
            id=sid,
            provider="fake",
            provider_resource_id=sid,
            workdir="/work",
            meta={
                "env": dict(env),
                "limits": limits,
                "egress_allow_list": [],
            },
        )
