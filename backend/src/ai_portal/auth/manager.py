from __future__ import annotations

import re
import secrets
import uuid as _uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.jwt import create_access_token, create_refresh_token
from ai_portal.auth.password import hash_password, verify_password
from ai_portal.models.org import Org
from ai_portal.models.user import User


class RegistrationError(ValueError):
    pass


class AuthenticationError(ValueError):
    pass


def _slugify(email: str) -> str:
    local = email.split("@")[0]
    slug = re.sub(r"[^a-z0-9]", "-", local.lower())[:48]
    return f"{slug}-{secrets.token_hex(4)}"


class UserManager:
    def __init__(self, db: Session, secret: str) -> None:
        self._db = db
        self._secret = secret

    def register(
        self,
        *,
        email: str,
        password: str,
        org_id: _uuid.UUID | None = None,
        role: str = "owner",
    ) -> User:
        """Register a new user.

        If org_id is None (SaaS open signup), a personal org is created automatically.
        If org_id is provided (invite flow), the user joins that org as a member.
        """
        existing = self._db.scalars(
            select(User).where(User.email == email.lower().strip())
        ).first()
        if existing is not None:
            raise RegistrationError("Email already registered")

        if org_id is None:
            # Create personal org
            personal_org = Org(slug=_slugify(email), name=email.split("@")[0])
            self._db.add(personal_org)
            self._db.flush()  # populate personal_org.id
            effective_org_id = personal_org.id
        else:
            effective_org_id = org_id

        user = User(
            email=email.lower().strip(),
            hashed_password=hash_password(password),
            uuid=_uuid.uuid4(),
            org_id=effective_org_id,
            role=role,
            is_active=True,
            is_verified=False,
        )
        self._db.add(user)
        self._db.commit()
        self._db.refresh(user)
        return user

    def authenticate(self, *, email: str, password: str) -> User:
        """Return user if credentials valid. Raises AuthenticationError otherwise."""
        user = self._db.scalars(
            select(User).where(User.email == email.lower().strip())
        ).first()
        if user is None or not user.hashed_password:
            raise AuthenticationError("Invalid email or password")
        if not verify_password(password, user.hashed_password):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("Account is disabled")
        return user

    def create_tokens(self, user: User) -> dict[str, str]:
        """Return {access_token, refresh_token, token_type} for a user."""
        return {
            "access_token": create_access_token(
                user_uuid=user.uuid,
                org_id=user.org_id,
                role=user.role,
                secret=self._secret,
            ),
            "refresh_token": create_refresh_token(
                user_uuid=user.uuid,
                org_id=user.org_id,
                role=user.role,
                secret=self._secret,
            ),
            "token_type": "bearer",
        }

    def get_by_uuid(self, user_uuid: _uuid.UUID) -> User | None:
        return self._db.scalars(
            select(User).where(User.uuid == user_uuid)
        ).first()
