"""Pydantic schemas for the model catalog API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from ai_portal.catalog import model_settings as catalog_model_settings


class CatalogModelRead(BaseModel):
    id: int
    slug: str
    display_name: str
    description: str
    api_model_id: str
    effort: str
    sort_order: int
    catalog_metadata: dict[str, Any] | None = Field(
        default=None,
        serialization_alias="metadata",
    )
    model_settings: catalog_model_settings.ModelSettingsPublic
    accessible: bool
    usable_in_worker: bool = False
    can_request_access: bool
    request_access_url: str | None = None
    is_default: bool = False

    model_config = {"populate_by_name": True}
