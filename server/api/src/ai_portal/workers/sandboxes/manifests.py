"""Sandbox provider manifests — metadata for UI + admin pages.

Each entry describes one bundled provider so the admin UI can render a
picker without importing the provider class.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxManifest:
    name: str
    label: str
    description: str
    requires: list[str]
    supports_snapshot: bool
    supports_egress_acl: bool
    deployment: str  # "local" | "self-hosted" | "managed"


MANIFESTS: dict[str, SandboxManifest] = {
    "fake": SandboxManifest(
        name="fake",
        label="In-memory (tests)",
        description="Simulated sandbox — used by tests, never in production.",
        requires=[],
        supports_snapshot=True,
        supports_egress_acl=False,
        deployment="local",
    ),
    "docker": SandboxManifest(
        name="docker",
        label="Docker",
        description="Local-dev sandbox via the Docker daemon.",
        requires=["docker>=7.1"],
        supports_snapshot=True,
        supports_egress_acl=True,
        deployment="local",
    ),
    "kubernetes": SandboxManifest(
        name="kubernetes",
        label="Kubernetes",
        description="Pod-per-task with gVisor/Kata runtime + NetworkPolicy egress.",
        requires=["kubernetes>=31"],
        supports_snapshot=False,
        supports_egress_acl=True,
        deployment="self-hosted",
    ),
    "e2b": SandboxManifest(
        name="e2b",
        label="E2B",
        description="Managed micro-VM sandboxes from e2b.dev.",
        requires=[],
        supports_snapshot=True,
        supports_egress_acl=True,
        deployment="managed",
    ),
    "daytona": SandboxManifest(
        name="daytona",
        label="Daytona",
        description="Managed dev environments from daytona.io.",
        requires=[],
        supports_snapshot=True,
        supports_egress_acl=True,
        deployment="managed",
    ),
    "firecracker": SandboxManifest(
        name="firecracker",
        label="Firecracker (slot)",
        description="MicroVM slot — not yet implemented.",
        requires=["firecracker-microvm socket"],
        supports_snapshot=False,
        supports_egress_acl=True,
        deployment="self-hosted",
    ),
}


def get(name: str) -> SandboxManifest:
    return MANIFESTS[name]


def all_manifests() -> list[SandboxManifest]:
    return list(MANIFESTS.values())
