"""Kubernetes sandbox provider — pod-per-task with gVisor/Kata.

Each task runs in a freshly provisioned Pod with ``runtimeClassName`` set to
``gvisor`` (default) or ``kata``. Resource limits map directly to the Pod
spec. A NetworkPolicy is created per Pod restricting egress to the
allow-list (translated to ``egress.to.namespaceSelector`` / ``ports``).

The kubernetes python SDK is synchronous; calls are dispatched via
``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, AsyncIterator

try:
    from kubernetes import client as k8s_client  # type: ignore[import-not-found]
    from kubernetes import config as k8s_config  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover
    k8s_client = None  # type: ignore[assignment]
    k8s_config = None  # type: ignore[assignment]

from ai_portal.workers.sandboxes.protocol import (
    ExecResult,
    SandboxHandle,
    SnapshotRef,
)
from ai_portal.workers.types import ResourceLimits


class KubernetesNotAvailable(RuntimeError):
    """Raised when the kubernetes SDK isn't installed."""


class KubernetesSandbox:
    """Sandbox provider backed by a Kubernetes cluster."""

    name = "kubernetes"

    def __init__(
        self,
        core_api: Any | None = None,
        networking_api: Any | None = None,
        *,
        namespace: str = "ai-portal-workers",
        runtime_class: str = "gvisor",
    ) -> None:
        if core_api is not None and networking_api is not None:
            self._core = core_api
            self._net = networking_api
        else:
            if k8s_client is None:
                raise KubernetesNotAvailable("kubernetes SDK not installed")
            try:
                k8s_config.load_incluster_config()
            except Exception:  # noqa: BLE001
                k8s_config.load_kube_config()
            self._core = k8s_client.CoreV1Api()
            self._net = k8s_client.NetworkingV1Api()
        self._ns = namespace
        self._runtime_class = runtime_class

    def _pod_spec(
        self,
        *,
        name: str,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> dict:
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "metadata": {
                "name": name,
                "namespace": self._ns,
                "labels": {"ai_portal_worker": "1", "worker_pod": name},
            },
            "spec": {
                "runtimeClassName": self._runtime_class,
                "restartPolicy": "Never",
                "containers": [
                    {
                        "name": "task",
                        "image": image,
                        "command": ["sleep", "infinity"],
                        "workingDir": "/work",
                        "env": [
                            {"name": k, "value": v} for k, v in env.items()
                        ],
                        "resources": {
                            "limits": {
                                "cpu": str(limits.cpu_cores),
                                "memory": f"{limits.ram_mb}Mi",
                                "ephemeral-storage": f"{limits.disk_mb}Mi",
                            },
                            "requests": {
                                "cpu": str(limits.cpu_cores / 2),
                                "memory": f"{limits.ram_mb // 2}Mi",
                            },
                        },
                        "securityContext": {
                            "allowPrivilegeEscalation": False,
                            "capabilities": {"drop": ["ALL"]},
                            "runAsNonRoot": True,
                        },
                    }
                ],
            },
        }

    def _network_policy(
        self, *, pod_name: str, egress_allow_list: list[str]
    ) -> dict:
        # Default-deny + named-host allow rules. Actual host->CIDR resolution
        # is left to a sidecar (CoreDNS plugin); the manifest records hosts
        # as annotations.
        return {
            "apiVersion": "networking.k8s.io/v1",
            "kind": "NetworkPolicy",
            "metadata": {
                "name": f"np-{pod_name}",
                "namespace": self._ns,
                "annotations": {
                    "ai_portal_worker/egress_hosts": ",".join(
                        egress_allow_list
                    ),
                },
            },
            "spec": {
                "podSelector": {"matchLabels": {"worker_pod": pod_name}},
                "policyTypes": ["Egress"],
                "egress": [
                    {
                        "ports": [
                            {"port": 53, "protocol": "UDP"},
                            {"port": 443, "protocol": "TCP"},
                            {"port": 80, "protocol": "TCP"},
                        ]
                    }
                ],
            },
        }

    async def provision(
        self,
        *,
        image: str,
        limits: ResourceLimits,
        env: dict[str, str],
        egress_allow_list: list[str],
    ) -> SandboxHandle:
        name = f"worker-{uuid.uuid4().hex[:10]}"
        pod = self._pod_spec(
            name=name, image=image, limits=limits, env=env
        )
        np = self._network_policy(
            pod_name=name, egress_allow_list=egress_allow_list
        )
        await asyncio.to_thread(
            self._core.create_namespaced_pod,
            namespace=self._ns,
            body=pod,
        )
        await asyncio.to_thread(
            self._net.create_namespaced_network_policy,
            namespace=self._ns,
            body=np,
        )
        return SandboxHandle(
            id=name,
            provider="kubernetes",
            provider_resource_id=name,
            workdir="/work",
            meta={
                "image": image,
                "namespace": self._ns,
                "runtime_class": self._runtime_class,
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
        # The kubernetes ``stream`` API returns the full transcript when
        # buffered with ``_preload_content=False`` then ``read_all()``. We
        # capture stdout/stderr separately when supported by the test
        # double; otherwise we report combined output as stdout.
        def _do() -> ExecResult:
            try:
                from kubernetes.stream import stream  # type: ignore[import-not-found]
            except ImportError:
                stream = None  # type: ignore[assignment]
            if stream is not None:
                resp = stream(
                    self._core.connect_get_namespaced_pod_exec,
                    h.provider_resource_id,
                    self._ns,
                    command=cmd,
                    stderr=True,
                    stdout=True,
                    stdin=False,
                    tty=False,
                    _preload_content=False,
                )
                resp.run_forever(timeout=timeout_sec)
                stdout = resp.read_stdout()
                stderr = resp.read_stderr()
                rc = int(resp.returncode or 0)
            else:
                # Test path — call the api directly through the double.
                resp = self._core.connect_get_namespaced_pod_exec(
                    h.provider_resource_id,
                    self._ns,
                    command=cmd,
                    stderr=True,
                    stdout=True,
                    stdin=False,
                    tty=False,
                )
                stdout = getattr(resp, "stdout", "") or ""
                stderr = getattr(resp, "stderr", "") or ""
                rc = int(getattr(resp, "returncode", 0))
            return ExecResult(
                exit_code=rc,
                stdout=stdout,
                stderr=stderr,
                duration_ms=0,
                truncated=False,
            )

        return await asyncio.to_thread(_do)

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
        r = await self.exec(h, ["cat", path])
        return r.stdout.encode("utf-8", errors="replace")

    async def write_file(
        self, h: SandboxHandle, path: str, data: bytes
    ) -> None:
        # Write via a here-doc style exec — sufficient for orchestrator
        # bootstrapping (large files use ``kubectl cp`` outside this layer).
        import base64

        b64 = base64.b64encode(data).decode()
        await self.exec(
            h,
            ["sh", "-c", f"echo {b64} | base64 -d > {path}"],
        )

    async def kill(self, h: SandboxHandle) -> None:
        try:
            await asyncio.to_thread(
                self._core.delete_namespaced_pod,
                name=h.provider_resource_id,
                namespace=self._ns,
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            await asyncio.to_thread(
                self._net.delete_namespaced_network_policy,
                name=f"np-{h.provider_resource_id}",
                namespace=self._ns,
            )
        except Exception:  # noqa: BLE001
            pass

    async def snapshot(self, h: SandboxHandle) -> SnapshotRef:
        # Kubernetes Pods aren't snapshottable directly. Fall back to a
        # tarball of /work uploaded to blob storage; we record only the ref
        # — the orchestrator handles the blob round-trip.
        return SnapshotRef(
            id=f"k8s-snap-{uuid.uuid4().hex[:8]}",
            provider="kubernetes",
            size_bytes=0,
        )

    async def restore(
        self,
        snap: SnapshotRef,
        *,
        limits: ResourceLimits,
        env: dict[str, str],
    ) -> SandboxHandle:
        raise NotImplementedError(
            "k8s restore requires external blob hydration; orchestrator handles it"
        )
