"""User identity service — signup, email verification, password reset, profile.

This is the consolidated entry-point for control-plane identity operations.
The legacy :class:`UserManager` in ``auth/strategies/dev.py`` remains for
existing login/register/refresh routes; new flows funnel through this service.

Notifications are emitted via an injectable ``notifier`` (defaults to a
no-op). Tests inject :class:`CapturingNotifier` to assert emails.
"""
from __future__ import annotations

import hashlib
import re
import secrets
import uuid as _uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import (
    EmailVerification,
    Org,
    PasswordReset,
    User,
)
from ai_portal.auth.password import hash_password, verify_password
from ai_portal.auth.users_schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    UpdateProfileRequest,
    VerifyEmailRequest,
)

EMAIL_VERIFY_EXPIRY_HOURS = 24
PASSWORD_RESET_EXPIRY_HOURS = 1


# ── Errors ───────────────────────────────────────────────────────────────────


class EmailAlreadyRegistered(Exception):
    pass


class EmailNotVerified(Exception):
    pass


class InvalidToken(Exception):
    pass


class TokenExpired(Exception):
    pass


class UserNotFound(Exception):
    pass


# ── Notifier protocol ────────────────────────────────────────────────────────


class Notifier(Protocol):
    """Tiny in-process notify surface. Real implementation lives under
    ``ai_portal.notify`` once Phase I lands; for now we keep a stub."""

    def send(self, *, template: str, to: str, payload: dict[str, Any]) -> None: ...


class _NullNotifier:
    def send(self, *, template: str, to: str, payload: dict[str, Any]) -> None:
        return None


@dataclass
class _SentMessage:
    template: str
    to: str
    payload: dict[str, Any]


@dataclass
class CapturingNotifier:
    """Test helper: records each ``send`` call. ``has`` answers "did we send …?"."""

    messages: list[_SentMessage] = field(default_factory=list)

    def send(self, *, template: str, to: str, payload: dict[str, Any]) -> None:
        self.messages.append(_SentMessage(template=template, to=to, payload=payload))

    def has(self, template: str, to: str) -> bool:
        return any(
            m.template == template and m.to == to.lower().strip()
            for m in self.messages
        )

    def last(self, template: str | None = None) -> _SentMessage | None:
        if template is None:
            return self.messages[-1] if self.messages else None
        for m in reversed(self.messages):
            if m.template == template:
                return m
        return None


# ── Helpers ──────────────────────────────────────────────────────────────────


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _slugify(email: str) -> str:
    local = email.split("@")[0]
    slug = re.sub(r"[^a-z0-9]", "-", local.lower())[:48]
    return f"{slug}-{secrets.token_hex(4)}"


def _hash_token(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


def _new_token() -> tuple[str, str]:
    """Return (plaintext, hash). Plaintext is shown once."""
    plain = secrets.token_urlsafe(32)
    return plain, _hash_token(plain)


# ── Service ──────────────────────────────────────────────────────────────────


class UserService:
    """Identity operations: signup / verify_email / password_reset / profile."""

    def __init__(self, db: Session, notifier: Notifier | None = None) -> None:
        self.db = db
        self.notifier: Notifier = notifier or _NullNotifier()

    # ── signup ───────────────────────────────────────────────────────────────

    def signup(self, dto: SignupRequest) -> User:
        """Create a user + personal org + queue email-verification token."""
        email = _normalize_email(dto.email)
        existing = self.db.scalars(
            select(User).where(User.email == email)
        ).first()
        if existing is not None:
            raise EmailAlreadyRegistered(email)

        personal_org = Org(
            slug=_slugify(email),
            name=email.split("@")[0],
            region="eu-west-1",
            status="active",
        )
        self.db.add(personal_org)
        self.db.flush()

        user = User(
            email=email,
            uuid=_uuid.uuid4(),
            hashed_password=hash_password(dto.password),
            org_id=personal_org.id,
            role="owner",
            is_active=True,
            is_verified=False,
            name=dto.name,
            locale=dto.locale,
        )
        self.db.add(user)
        self.db.flush()

        self._issue_email_verification(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def signup_via_invite(
        self, invite_token: str, password: str, name: str | None = None
    ) -> User:
        """Signup path triggered by an invite. Caller's :class:`OrgService`
        is expected to consume the invite right after this returns."""
        from ai_portal.auth.model import OrgInvite

        invite = self.db.scalars(
            select(OrgInvite).where(
                OrgInvite.token == invite_token,
                OrgInvite.accepted_at.is_(None),
                OrgInvite.revoked_at.is_(None),
            )
        ).first()
        if invite is None:
            raise InvalidToken(invite_token)
        expires_at = invite.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise TokenExpired(invite_token)

        email = _normalize_email(invite.invited_email)
        existing = self.db.scalars(
            select(User).where(User.email == email)
        ).first()
        if existing is not None:
            raise EmailAlreadyRegistered(email)

        user = User(
            email=email,
            uuid=_uuid.uuid4(),
            hashed_password=hash_password(password),
            org_id=invite.org_id,
            role=invite.role,
            is_active=True,
            is_verified=False,
            name=name,
        )
        self.db.add(user)
        self.db.flush()
        self.db.commit()
        self.db.refresh(user)
        return user

    # ── email verification ───────────────────────────────────────────────────

    def _issue_email_verification(self, user: User) -> str:
        plain, hashed = _new_token()
        record = EmailVerification(
            user_id=user.id,
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(hours=EMAIL_VERIFY_EXPIRY_HOURS),
        )
        self.db.add(record)
        self.db.flush()
        self.notifier.send(
            template="verify_email",
            to=user.email,
            payload={"token": plain, "user_id": user.id},
        )
        return plain

    def request_email_verification(self, user_id: int) -> str:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(str(user_id))
        token = self._issue_email_verification(user)
        self.db.commit()
        return token

    def verify_email(self, dto: VerifyEmailRequest) -> User:
        hashed = _hash_token(dto.token)
        record = self.db.scalars(
            select(EmailVerification).where(
                EmailVerification.token_hash == hashed,
                EmailVerification.consumed_at.is_(None),
            )
        ).first()
        if record is None:
            raise InvalidToken("email_verify")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise TokenExpired("email_verify")

        user = self.db.get(User, record.user_id)
        if user is None:
            raise UserNotFound(str(record.user_id))
        user.is_verified = True
        user.email_verified_at = datetime.now(UTC)
        record.consumed_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)
        return user

    def assert_can_login(self, email: str) -> User:
        """Raises if the account is missing or email not verified."""
        norm = _normalize_email(email)
        user = self.db.scalars(
            select(User).where(User.email == norm)
        ).first()
        if user is None:
            raise UserNotFound(norm)
        if not user.is_verified:
            raise EmailNotVerified(norm)
        return user

    # ── password reset ───────────────────────────────────────────────────────

    def request_password_reset(self, dto: PasswordResetRequest) -> str | None:
        """Issue a one-shot reset token. Returns the plaintext token in tests;
        callers should send it via the notifier, never expose it via API."""
        norm = _normalize_email(dto.email)
        user = self.db.scalars(
            select(User).where(User.email == norm)
        ).first()
        if user is None:
            # Don't leak account existence — return None silently.
            return None
        plain, hashed = _new_token()
        record = PasswordReset(
            user_id=user.id,
            token_hash=hashed,
            expires_at=datetime.now(UTC) + timedelta(hours=PASSWORD_RESET_EXPIRY_HOURS),
        )
        self.db.add(record)
        self.db.flush()
        self.notifier.send(
            template="password_reset",
            to=user.email,
            payload={"token": plain, "user_id": user.id},
        )
        self.db.commit()
        return plain

    def reset_password(self, dto: PasswordResetConfirm) -> User:
        hashed = _hash_token(dto.token)
        record = self.db.scalars(
            select(PasswordReset).where(
                PasswordReset.token_hash == hashed,
                PasswordReset.consumed_at.is_(None),
            )
        ).first()
        if record is None:
            raise InvalidToken("password_reset")
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at < datetime.now(UTC):
            raise TokenExpired("password_reset")
        user = self.db.get(User, record.user_id)
        if user is None:
            raise UserNotFound(str(record.user_id))
        user.hashed_password = hash_password(dto.new_password)
        record.consumed_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(user)
        return user

    def change_password(
        self, user_id: int, current_password: str, new_password: str
    ) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(str(user_id))
        if not user.hashed_password or not verify_password(
            current_password, user.hashed_password
        ):
            raise InvalidToken("current_password")
        user.hashed_password = hash_password(new_password)
        self.db.commit()
        self.db.refresh(user)
        return user

    # ── profile ──────────────────────────────────────────────────────────────

    def update_profile(self, user_id: int, dto: UpdateProfileRequest) -> User:
        user = self.db.get(User, user_id)
        if user is None:
            raise UserNotFound(str(user_id))
        if dto.name is not None:
            user.name = dto.name
        if dto.locale is not None:
            user.locale = dto.locale
        self.db.commit()
        self.db.refresh(user)
        return user
