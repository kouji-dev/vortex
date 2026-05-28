"""Firecracker sandbox provider — future microVM slot.

Stubbed out: implements the protocol surface but ``provision`` raises
``NotImplementedError`` until a real Firecracker control socket is wired
up. The slot exists so production deploys can drop in an adapter without
re-shaping the registry.
"""

from __future__ import annotations

from typing import AsyncIterator

from ai_portal.workers.sandboxes.protocol import (
    ExecResult,
    SandboxHandle,
    SnapshotRef,
)
from ai_portal.workers.types import ResourceLimits


class FirecrackerNotConfigured(NotImplementedError):
    """Raised until a control-socket path is provided."""


class FirecrackerSandbox:
    """Slot for a Firecracker microVM adapter."""

    name = "firecracker"

    def __init__(self, *, firecracker_socket_path: str | None = None) -> None:
        self._socket = firecracker_socket_path

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle:
        if not self._socket:
            raise FirecrackerNotConfigured(
                "requires firecracker socket — pass firecracker_socket_path"
            )
        # Real provisioning would PUT /machine-config, PUT /boot-source,
        # PUT /drives/rootfs, then POST /actions InstanceStart.
        raise FirecrackerNotConfigured("firecracker adapter not yet implemented")

    async def exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout_sec: int = 600,
        env: dict[str, str] | None = None,
    ) -> ExecResult:
        raise FirecrackerNotConfigured("firecracker exec not implemented")

    async def stream_exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
    ) -> AsyncIterator[tuple[str, str]]:
        raise FirecrackerNotConfigured("firecracker stream_exec not implemented")
        yield  # pragma: no cover — keeps mypy happy as async generator

    async def read_file(self, h: SandboxHandle, path: str) -> bytes:
        raise FirecrackerNotConfigured("firecracker read_file not implemented")

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None:
        raise FirecrackerNotConfigured("firecracker write_file not implemented")

    async def kill(self, h: SandboxHandle) -> None:
        # Idempotent best-effort — no-op so orchestrator cleanup never raises.
        return None

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        raise FirecrackerNotConfigured("firecracker snapshot not implemented")

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle:
        raise FirecrackerNotConfigured("firecracker restore not implemented")
