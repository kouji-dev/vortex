"""Tests for secret injection into sandbox env."""

from __future__ import annotations

import pytest

from ai_portal.workers.secrets.bindings import SecretRef
from ai_portal.workers.secrets.injection import (
    InMemorySecretResolver,
    SecretNotFound,
    inject_env,
)


@pytest.mark.asyncio
async def test_inject_env_default_name_mapping() -> None:
    resolver = InMemorySecretResolver(values={"aws/staging/access_key": "AKIA-fake"})
    out = await inject_env(
        {"PATH": "/usr/bin"},
        refs=[SecretRef("aws/staging/access_key")],
        resolver=resolver,
    )
    assert out["PATH"] == "/usr/bin"
    assert out["AWS_STAGING_ACCESS_KEY"] == "AKIA-fake"


@pytest.mark.asyncio
async def test_inject_env_uses_override_name() -> None:
    resolver = InMemorySecretResolver(values={"npm/token": "npm-fake"})
    out = await inject_env(
        {},
        refs=[SecretRef("npm/token")],
        resolver=resolver,
        env_name_overrides={"npm/token": "NPM_TOKEN"},
    )
    assert out == {"NPM_TOKEN": "npm-fake"}


@pytest.mark.asyncio
async def test_inject_env_secret_overrides_base() -> None:
    resolver = InMemorySecretResolver(values={"my_secret": "real"})
    out = await inject_env(
        {"MY_SECRET": "placeholder"},
        refs=[SecretRef("my_secret")],
        resolver=resolver,
    )
    assert out["MY_SECRET"] == "real"


@pytest.mark.asyncio
async def test_inject_env_unknown_ref_raises() -> None:
    resolver = InMemorySecretResolver(values={})
    with pytest.raises(SecretNotFound):
        await inject_env({}, refs=[SecretRef("missing")], resolver=resolver)


@pytest.mark.asyncio
async def test_inject_env_does_not_mutate_inputs() -> None:
    resolver = InMemorySecretResolver(values={"k": "v"})
    base = {"A": "1"}
    out = await inject_env(base, refs=[SecretRef("k")], resolver=resolver)
    assert base == {"A": "1"}
    assert out is not base
