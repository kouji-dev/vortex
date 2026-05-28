"""Tests for the Kubernetes sandbox provider — fake CoreV1/NetworkingV1 APIs."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from ai_portal.workers.sandboxes.protocol import SandboxHandle
from ai_portal.workers.sandboxes.providers.kubernetes import KubernetesSandbox
from ai_portal.workers.types import ResourceLimits


def _apis():
    core = MagicMock()
    net = MagicMock()
    return core, net


@pytest.mark.asyncio
async def test_provision_creates_pod_with_runtime_class_and_limits() -> None:
    core, net = _apis()
    sb = KubernetesSandbox(
        core_api=core, networking_api=net, runtime_class="gvisor"
    )
    h = await sb.provision(
        image="python:3.12",
        limits=ResourceLimits(cpu_cores=1, ram_mb=1024, disk_mb=2048),
        env={"X": "1"},
        egress_allow_list=["pypi.org"],
    )
    args, kwargs = core.create_namespaced_pod.call_args
    pod = kwargs["body"]
    assert pod["spec"]["runtimeClassName"] == "gvisor"
    c = pod["spec"]["containers"][0]
    assert c["image"] == "python:3.12"
    assert c["resources"]["limits"]["memory"] == "1024Mi"
    assert c["resources"]["limits"]["cpu"] == "1"
    assert c["securityContext"]["allowPrivilegeEscalation"] is False
    assert h.provider == "kubernetes"
    assert h.workdir == "/work"


@pytest.mark.asyncio
async def test_provision_creates_network_policy_with_allow_list() -> None:
    core, net = _apis()
    sb = KubernetesSandbox(core_api=core, networking_api=net)
    await sb.provision(
        image="x",
        limits=ResourceLimits(),
        env={},
        egress_allow_list=["pypi.org", "github.com"],
    )
    args, kwargs = net.create_namespaced_network_policy.call_args
    np = kwargs["body"]
    assert np["kind"] == "NetworkPolicy"
    assert "Egress" in np["spec"]["policyTypes"]
    annot = np["metadata"]["annotations"]["ai_portal_worker/egress_hosts"]
    assert "pypi.org" in annot and "github.com" in annot


@pytest.mark.asyncio
async def test_kill_deletes_pod_and_policy() -> None:
    core, net = _apis()
    sb = KubernetesSandbox(core_api=core, networking_api=net)
    h = SandboxHandle(
        id="worker-x", provider="kubernetes", provider_resource_id="worker-x",
        workdir="/work", meta={},
    )
    await sb.kill(h)
    core.delete_namespaced_pod.assert_called_once()
    net.delete_namespaced_network_policy.assert_called_once()


@pytest.mark.asyncio
async def test_exec_returns_decoded_result() -> None:
    core, net = _apis()
    resp = MagicMock()
    resp.stdout = "hello\n"
    resp.stderr = ""
    resp.returncode = 0
    core.connect_get_namespaced_pod_exec.return_value = resp
    sb = KubernetesSandbox(core_api=core, networking_api=net)
    h = SandboxHandle(
        id="x", provider="kubernetes", provider_resource_id="worker-x",
        workdir="/work", meta={},
    )
    r = await sb.exec(h, ["echo", "hello"])
    assert r.exit_code == 0
    assert "hello" in r.stdout


@pytest.mark.asyncio
async def test_snapshot_returns_ref() -> None:
    core, net = _apis()
    sb = KubernetesSandbox(core_api=core, networking_api=net)
    h = SandboxHandle(
        id="x", provider="kubernetes", provider_resource_id="worker-x",
        workdir="/work", meta={},
    )
    snap = await sb.snapshot(h)
    assert snap.provider == "kubernetes"
    assert snap.id.startswith("k8s-snap-")
