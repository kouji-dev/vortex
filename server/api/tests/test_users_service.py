"""Tests for UserService — signup, email verify, password reset, profile."""
from __future__ import annotations

import secrets

import pytest

from ai_portal.auth.users_schemas import (
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from ai_portal.auth.users_service import (
    CapturingNotifier,
    EmailAlreadyRegistered,
    EmailNotVerified,
    InvalidToken,
    TokenExpired,
    UserNotFound,
    UserService,
)
from ai_portal.core.db.session import SessionLocal
from tests.conftest import requires_postgres


def _email() -> str:
    return f"u-{secrets.token_hex(6)}@control.test"


# ── Signup ───────────────────────────────────────────────────────────────────


@requires_postgres
def test_signup_creates_user_personal_org_and_emits_verify():
    db = SessionLocal()
    notifier = CapturingNotifier()
    try:
        svc = UserService(db, notifier=notifier)
        email = _email()
        user = svc.signup(SignupRequest(email=email, password="Strong-pass-123"))
        assert user.email == email
        assert user.is_verified is False
        assert user.org_id is not None
        assert user.role == "owner"
        assert notifier.has(template="verify_email", to=email)
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_signup_duplicate_email_raises():
    db = SessionLocal()
    try:
        svc = UserService(db)
        email = _email()
        svc.signup(SignupRequest(email=email, password="Strong-pass-123"))
        with pytest.raises(EmailAlreadyRegistered):
            svc.signup(SignupRequest(email=email, password="Strong-pass-456"))
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_assert_can_login_blocks_unverified():
    db = SessionLocal()
    try:
        svc = UserService(db)
        email = _email()
        svc.signup(SignupRequest(email=email, password="Strong-pass-123"))
        with pytest.raises(EmailNotVerified):
            svc.assert_can_login(email)
    finally:
        db.rollback()
        db.close()


# ── Email verification ───────────────────────────────────────────────────────


@requires_postgres
def test_verify_email_flow_marks_user_verified():
    db = SessionLocal()
    notifier = CapturingNotifier()
    try:
        svc = UserService(db, notifier=notifier)
        email = _email()
        user = svc.signup(SignupRequest(email=email, password="Strong-pass-123"))
        msg = notifier.last("verify_email")
        assert msg is not None
        token = msg.payload["token"]

        verified = svc.verify_email(VerifyEmailRequest(token=token))
        assert verified.is_verified is True
        assert verified.email_verified_at is not None
        # Second use must fail (consumed).
        with pytest.raises(InvalidToken):
            svc.verify_email(VerifyEmailRequest(token=token))
        # And login now works.
        ok = svc.assert_can_login(email)
        assert ok.id == user.id
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_verify_email_unknown_token_raises():
    db = SessionLocal()
    try:
        svc = UserService(db)
        with pytest.raises(InvalidToken):
            svc.verify_email(VerifyEmailRequest(token="not-a-real-token"))
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_verify_email_expired_token_raises():
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from ai_portal.auth.model import EmailVerification

    db = SessionLocal()
    notifier = CapturingNotifier()
    try:
        svc = UserService(db, notifier=notifier)
        svc.signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        token = notifier.last("verify_email").payload["token"]
        from ai_portal.auth.users_service import _hash_token

        rec = db.scalars(
            select(EmailVerification).where(
                EmailVerification.token_hash == _hash_token(token)
            )
        ).first()
        rec.expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
        with pytest.raises(TokenExpired):
            svc.verify_email(VerifyEmailRequest(token=token))
    finally:
        db.rollback()
        db.close()


# ── Password reset ───────────────────────────────────────────────────────────


@requires_postgres
def test_password_reset_happy_path():
    db = SessionLocal()
    notifier = CapturingNotifier()
    try:
        svc = UserService(db, notifier=notifier)
        email = _email()
        svc.signup(SignupRequest(email=email, password="Old-pass-123"))

        token = svc.request_password_reset(PasswordResetRequest(email=email))
        assert token is not None
        assert notifier.has(template="password_reset", to=email)

        new_user = svc.reset_password(
            PasswordResetConfirm(token=token, new_password="New-pass-456")
        )
        from ai_portal.auth.password import verify_password

        assert verify_password("New-pass-456", new_user.hashed_password)
        assert not verify_password("Old-pass-123", new_user.hashed_password)

        # Token cannot be reused.
        with pytest.raises(InvalidToken):
            svc.reset_password(
                PasswordResetConfirm(token=token, new_password="Yet-another-789")
            )
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_password_reset_unknown_email_silently_returns_none():
    db = SessionLocal()
    try:
        svc = UserService(db)
        token = svc.request_password_reset(
            PasswordResetRequest(email="nope-" + secrets.token_hex(4) + "@x.test")
        )
        assert token is None
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_change_password_requires_current():
    db = SessionLocal()
    try:
        svc = UserService(db)
        email = _email()
        user = svc.signup(SignupRequest(email=email, password="Old-pass-123"))
        with pytest.raises(InvalidToken):
            svc.change_password(user.id, "WRONG", "New-pass-456")
        svc.change_password(user.id, "Old-pass-123", "New-pass-456")
        from ai_portal.auth.password import verify_password

        db.refresh(user)
        assert verify_password("New-pass-456", user.hashed_password)
    finally:
        db.rollback()
        db.close()


# ── Profile ──────────────────────────────────────────────────────────────────


@requires_postgres
def test_update_profile_sets_name_and_locale():
    db = SessionLocal()
    try:
        svc = UserService(db)
        user = svc.signup(SignupRequest(email=_email(), password="Strong-pass-123"))
        updated = svc.update_profile(
            user.id, UpdateProfileRequest(name="Alice", locale="en-GB")
        )
        assert updated.name == "Alice"
        assert updated.locale == "en-GB"
    finally:
        db.rollback()
        db.close()


@requires_postgres
def test_update_profile_unknown_user_raises():
    db = SessionLocal()
    try:
        svc = UserService(db)
        with pytest.raises(UserNotFound):
            svc.update_profile(999_999_999, UpdateProfileRequest(name="X"))
    finally:
        db.rollback()
        db.close()
