"""Sandbox provider protocol — pluggable code-execution backend.

Concrete providers (docker, kubernetes, e2b, daytona, firecracker) implement
this contract. The orchestrator only talks to ``SandboxProvider`` — never
provider-specific APIs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol, runtime_checkable

from ai_portal.workers.types import ResourceLimits


@dataclass
class SandboxHandle:
    """Opaque handle for an allocated sandbox."""

    id: str
    provider: str
    provider_resource_id: str
    workdir: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecResult:
    """Result of an exec() invocation inside a sandbox."""

    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    truncated: bool


@dataclass
class SnapshotRef:
    """Reference to a sandbox snapshot."""

    id: str
    provider: str
    size_bytes: int


@runtime_checkable
class SandboxProvider(Protocol):
    """Contract every sandbox backend must satisfy."""

    name: str

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle: ...

    async def exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout_sec: int = 600,
        env: dict[str, str] | None = None,
    ) -> ExecResult: ...

    def stream_exec(
        self,
        h: SandboxHandle,
        cmd: list[str],
        *,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_sec: int = 600,
    ) -> AsyncIterator[tuple[str, str]]: ...

    async def read_file(self, h: SandboxHandle, path: str) -> bytes: ...

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None: ...

    async def kill(self, h: SandboxHandle) -> None: ...

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef: ...

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle: ...
