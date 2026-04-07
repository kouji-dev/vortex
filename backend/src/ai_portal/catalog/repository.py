# src/ai_portal/catalog/repository.py
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.models import CatalogModel


def get_active_catalog_model_by_slug(db: Session, slug: str) -> CatalogModel | None:
    return db.scalars(
        select(CatalogModel)
        .where(CatalogModel.slug == slug)
        .where(CatalogModel.is_active.is_(True))
        .limit(1)
    ).first()


def get_active_catalog_models_by_api_model_id(
    db: Session, api_model_id: str
) -> list[CatalogModel]:
    return list(
        db.scalars(
            select(CatalogModel)
            .where(CatalogModel.api_model_id == api_model_id)
            .where(CatalogModel.is_active.is_(True))
        ).all()
    )


def get_all_active_catalog_models(db: Session) -> list[CatalogModel]:
    return list(
        db.scalars(
            select(CatalogModel)
            .where(CatalogModel.is_active.is_(True))
            .order_by(CatalogModel.sort_order, CatalogModel.id)
        ).all()
    )
