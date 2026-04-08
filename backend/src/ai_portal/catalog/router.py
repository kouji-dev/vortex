"""Read-only model catalog for chat UI (REQ-CAT, REQ-META)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.catalog import repository as repo
from ai_portal.catalog.schemas import CatalogModelRead
from ai_portal.catalog.model import CatalogModel
from ai_portal.auth.model import User
from ai_portal.catalog.model_settings import model_settings_from_metadata
from ai_portal.catalog.service import resolve_default_conversation_stored_model

router = APIRouter(prefix="/api", tags=["model-catalog"])


def _default_catalog_row_id(rows: list[CatalogModel], db: Session) -> int | None:
    """Single catalog row matching the server default (slug or API model id fallback)."""
    key = resolve_default_conversation_stored_model(db)
    by_slug = next((m for m in rows if m.slug == key), None)
    if by_slug is not None:
        return by_slug.id
    matches = [m for m in rows if m.api_model_id == key]
    if not matches:
        return None
    return min(matches, key=lambda m: (m.sort_order, m.id)).id


def _row_to_read(m: CatalogModel, *, is_default: bool) -> CatalogModelRead:
    # Stub until WS-ENT: "granted" = not requires_entitlement
    accessible = not m.requires_entitlement
    can_request_access = not accessible
    return CatalogModelRead(
        id=m.id,
        slug=m.slug,
        display_name=m.display_name,
        description=m.description,
        api_model_id=m.api_model_id,
        effort=m.effort,
        sort_order=m.sort_order,
        catalog_metadata=m.catalog_metadata,
        model_settings=model_settings_from_metadata(m.catalog_metadata),
        accessible=accessible,
        can_request_access=can_request_access,
        request_access_url=m.request_access_url,
        is_default=is_default,
    )


@router.get(
    "/models",
    response_model=list[CatalogModelRead],
    response_model_by_alias=True,
)
def list_catalog_models(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[CatalogModelRead]:
    # catalog_models.org_id is set but not yet used for per-org visibility
    rows = repo.get_all_active_catalog_models(db)
    default_id = _default_catalog_row_id(rows, db)
    return [_row_to_read(m, is_default=(m.id == default_id)) for m in rows]
