from __future__ import annotations

import uuid
from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.core.db.base import Base

T = TypeVar("T", bound=Base)


class TenantRepository(Generic[T]):
    """Base repository that enforces org_id on all queries.

    Usage:
        repo = TenantRepository(db=db, model=Assistant)
        assistants = repo.all(org_id=user.org_id)
    """

    def __init__(self, *, db: Session, model: type[T]) -> None:
        self._db = db
        self._model = model

    def all(self, org_id: uuid.UUID) -> list[T]:
        return list(
            self._db.scalars(
                select(self._model).where(self._model.org_id == org_id)
            ).all()
        )

    def get(self, *, id: Any, org_id: uuid.UUID) -> T | None:
        return self._db.scalars(
            select(self._model).where(
                self._model.id == id,
                self._model.org_id == org_id,
            )
        ).first()

    def create(self, *, data: dict, org_id: uuid.UUID) -> T:
        obj = self._model(**data, org_id=org_id)
        self._db.add(obj)
        self._db.commit()
        self._db.refresh(obj)
        return obj

    def update(self, *, id: Any, data: dict, org_id: uuid.UUID) -> T:
        obj = self.get(id=id, org_id=org_id)
        if obj is None:
            raise ValueError(f"{self._model.__tablename__} {id} not found in org {org_id}")
        for k, v in data.items():
            setattr(obj, k, v)
        self._db.commit()
        self._db.refresh(obj)
        return obj

    def delete(self, *, id: Any, org_id: uuid.UUID) -> None:
        obj = self.get(id=id, org_id=org_id)
        if obj is None:
            raise ValueError(f"{self._model.__tablename__} {id} not found in org {org_id}")
        self._db.delete(obj)
        self._db.commit()
