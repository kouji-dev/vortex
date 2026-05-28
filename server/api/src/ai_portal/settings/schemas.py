"""Pydantic schemas for the settings API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsPatch(BaseModel):
    """PATCH /v1/settings — upsert N KV entries in one call."""

    settings: dict[str, Any] = Field(default_factory=dict)


class SettingsOut(BaseModel):
    settings: dict[str, Any]


class ModuleFlagPatchItem(BaseModel):
    enabled: bool | None = None
    gates: dict[str, Any] | None = None


class ModuleFlagsPatch(BaseModel):
    """PATCH /v1/module-flags — upsert N modules in one call.

    Body: ``{"modules": {"gateway": {"enabled": false}, "rag": {"gates": {"hybrid": true}}}}``
    """

    modules: dict[str, ModuleFlagPatchItem] = Field(default_factory=dict)


class ModuleFlagOut(BaseModel):
    enabled: bool
    gates: dict[str, Any]


class ModuleFlagsOut(BaseModel):
    modules: dict[str, ModuleFlagOut]
