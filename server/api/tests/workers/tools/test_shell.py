"""Tests for the shell tool — streaming, redaction, audit hashes."""

from __future__ import annotations

import hashlib

import pytest

from ai_portal.workers.tools.providers.shell import ShellTool


@pytest.mark.asyncio
async def test_shell_runs_and_streams_output(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    t = ShellTool()
    r = await t.invoke({"cmd": ["echo", "hello"]}, ctx)
    assert r.ok is True
    assert r.output["exit_code"] == 0
    assert "hello" in r.output["stdout"]

    kinds = [k for k, _ in rec.events]
    assert "tool_call" in kinds
    assert "shell_output" in kinds


@pytest.mark.asyncio
async def test_shell_audit_records_hashes(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    await ShellTool().invoke({"cmd": ["echo", "hi"]}, ctx)
    assert rec.audited
    audit = rec.audited[-1]
    assert audit["action"] == "worker.shell"
    assert "cmd_sha256" in audit["payload"]
    assert "stdout_sha256" in audit["payload"]
    # cmd hash matches what we computed.
    expected = hashlib.sha256("echo hi".encode()).hexdigest()
    assert audit["payload"]["cmd_sha256"] == expected


@pytest.mark.asyncio
async def test_shell_redacts_secret_values(harness) -> None:
    from ai_portal.workers.sandboxes.providers.fake import FakeSandbox

    sb = FakeSandbox(
        scripts={
            ("printenv",): (0, "TOKEN=npm_super-secret-XYZ\n", ""),
        },
    )
    _sb, _h, ctx, rec = await harness(
        sandbox=sb, secrets={"NPM_TOKEN": "npm_super-secret-XYZ"}
    )
    r = await ShellTool().invoke({"cmd": ["printenv"]}, ctx)
    assert "npm_super-secret-XYZ" not in r.output["stdout"]
    assert "***" in r.output["stdout"]
    # Audit also sees redacted hash, not the secret.
    audited_payload = rec.audited[-1]["payload"]
    assert "stdout_sha256" in audited_payload


@pytest.mark.asyncio
async def test_shell_nonzero_exit_marks_failure(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await ShellTool().invoke({"cmd": ["false"]}, ctx)
    assert r.ok is False
    assert r.output["exit_code"] == 1
