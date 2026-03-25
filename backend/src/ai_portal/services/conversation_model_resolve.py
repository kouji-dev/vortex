"""Map ``conversations.model`` (slug or bare API id) to the vendor model string for chat.

Legacy rows may store a bare vendor model id string matching ``catalog_models.api_model_id``;
when several catalog rows share one API id, the lowest ``(sort_order, id)`` wins.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import CatalogModel


def resolve_stored_model_to_chat_model(db: Session, stored: str) -> str:
    """Return the vendor model id string used for LangChain chat."""
    s = (stored or "").strip()
    if not s:
        return s
    slug_row = db.scalars(
        select(CatalogModel)
        .where(CatalogModel.slug == s)
        .where(CatalogModel.is_active.is_(True))
        .limit(1)
    ).first()
    if slug_row is not None:
        return slug_row.api_model_id
    api_rows = list(
        db.scalars(
            select(CatalogModel)
            .where(CatalogModel.api_model_id == s)
            .where(CatalogModel.is_active.is_(True))
        ).all()
    )
    if len(api_rows) == 1:
        return api_rows[0].api_model_id
    if len(api_rows) > 1:
        api_rows.sort(key=lambda r: (r.sort_order, r.id))
        return api_rows[0].api_model_id
    return s
