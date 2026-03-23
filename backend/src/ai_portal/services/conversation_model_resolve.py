"""Map stored ``ChatConversation.model`` to a LiteLLM / API model id.

The UI stores **catalog slugs** for catalog rows (unique per entitlement variant). Legacy rows
may still store a bare ``litellm_model_id``; when several catalog rows share one API id, the
first active row by ``sort_order`` then ``id`` is used.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import CatalogModel


def resolve_stored_model_to_litellm(db: Session, stored: str) -> str:
    s = stored.strip()
    if not s:
        return ""

    slug_row = db.scalars(
        select(CatalogModel)
        .where(CatalogModel.slug == s)
        .where(CatalogModel.is_active.is_(True))
        .limit(1)
    ).first()
    if slug_row is not None:
        return slug_row.litellm_model_id

    litellm_rows = list(
        db.scalars(
            select(CatalogModel)
            .where(CatalogModel.litellm_model_id == s)
            .where(CatalogModel.is_active.is_(True))
        ).all()
    )
    if len(litellm_rows) == 1:
        return litellm_rows[0].litellm_model_id
    if len(litellm_rows) > 1:
        litellm_rows.sort(key=lambda r: (r.sort_order, r.id))
        return litellm_rows[0].litellm_model_id

    return s
