"""Tests for read_file / write_file / edit_file tools."""

from __future__ import annotations

import hashlib

import pytest

from ai_portal.workers.tools.providers.files import (
    EditFileTool,
    ReadFileTool,
    WriteFileTool,
)


@pytest.mark.asyncio
async def test_write_then_read_roundtrip(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    w = await WriteFileTool().invoke(
        {"path": "/work/a.txt", "content": "hello"}, ctx
    )
    assert w.ok
    expected = hashlib.sha256(b"hello").hexdigest()
    assert w.output["after_sha256"] == expected
    assert w.output["before_sha256"] is None

    r = await ReadFileTool().invoke({"path": "/work/a.txt"}, ctx)
    assert r.ok
    assert r.output["content"] == "hello"
    assert r.output["sha256"] == expected

    # file_changed event emitted.
    kinds = [k for k, _ in rec.events]
    assert "file_changed" in kinds


@pytest.mark.asyncio
async def test_write_overwrites_emits_before_hash(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    await WriteFileTool().invoke(
        {"path": "/work/a.txt", "content": "v1"}, ctx
    )
    w = await WriteFileTool().invoke(
        {"path": "/work/a.txt", "content": "v2"}, ctx
    )
    assert w.output["before_sha256"] == hashlib.sha256(b"v1").hexdigest()
    assert w.output["after_sha256"] == hashlib.sha256(b"v2").hexdigest()


@pytest.mark.asyncio
async def test_edit_file_find_replace(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    await WriteFileTool().invoke(
        {"path": "/work/code.py", "content": "x = 1\ny = 2\n"}, ctx
    )
    e = await EditFileTool().invoke(
        {"path": "/work/code.py", "find": "x = 1", "replace": "x = 99"}, ctx
    )
    assert e.ok
    assert "x = 99" in e.output["diff"]
    # File on disk actually changed.
    r = await ReadFileTool().invoke({"path": "/work/code.py"}, ctx)
    assert "x = 99" in r.output["content"]


@pytest.mark.asyncio
async def test_edit_file_missing_find_fails(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    await WriteFileTool().invoke(
        {"path": "/work/code.py", "content": "y = 1\n"}, ctx
    )
    e = await EditFileTool().invoke(
        {"path": "/work/code.py", "find": "not present", "replace": "x"}, ctx
    )
    assert not e.ok
    assert "find string" in e.error


@pytest.mark.asyncio
async def test_read_missing_file_fails(harness) -> None:
    _sb, _h, ctx, _rec = await harness()
    r = await ReadFileTool().invoke({"path": "/work/missing.txt"}, ctx)
    assert not r.ok


@pytest.mark.asyncio
async def test_write_emits_audit(harness) -> None:
    _sb, _h, ctx, rec = await harness()
    await WriteFileTool().invoke(
        {"path": "/work/a.txt", "content": "hi"}, ctx
    )
    assert any(a["action"] == "worker.write_file" for a in rec.audited)
