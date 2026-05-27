"""Org repository — narrow CRUD around the Org table."""
from __future__ import annotations

import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import Org


class OrgRepo:
    def __init__(self, db: Session) -> None:
        self.db = db

    def by_slug(self, slug: str) -> Org | None:
        return self.db.scalars(select(Org).where(Org.slug == slug)).first()

    def by_id(self, org_id: _uuid.UUID) -> Org | None:
        return self.db.scalars(select(Org).where(Org.id == org_id)).first()

    def add(self, org: Org) -> Org:
        self.db.add(org)
        self.db.flush()
        return org
