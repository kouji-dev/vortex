from __future__ import annotations
import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from ai_portal.auth.idp.protocol import UserClaims
from ai_portal.auth.model import User

def jit_provision(db: Session, *, claims: UserClaims, org_id: uuid.UUID, role: str) -> User:
    user = db.scalars(select(User).where(User.email == claims.email)).first()
    if user is None:
        user = User(uuid=uuid.uuid4(), email=claims.email, name=claims.name,
                    org_id=org_id, role=role, is_active=True, is_verified=True,
                    idp_groups=list(claims.groups))
        db.add(user)
    else:
        user.org_id, user.role, user.is_active = org_id, role, True
        user.idp_groups = list(claims.groups)
    db.flush(); return user
