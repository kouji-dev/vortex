"""TOTP MFA service — enroll, verify, login-step gating.

Phase M1 of the Control Plane plan. Uses :mod:`pyotp` for RFC 6238 codes.

Provisioning URI is rendered as a ``data:`` URI carrying an SVG QR code so the
frontend can drop it straight into an ``<img>`` tag (no extra HTTP round-trip).
"""
from __future__ import annotations

import base64
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime

import pyotp
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_portal.auth.model import User, UserMfaFactor

TOTP_KIND = "totp"
DEFAULT_ISSUER = "AI Portal"
TOTP_VALID_WINDOW = 1  # ±30s clock-skew tolerance


# ── Errors ───────────────────────────────────────────────────────────────────


class InvalidTotpCode(Exception):
    pass


class TotpAlreadyEnrolled(Exception):
    pass


class MfaFactorNotFound(Exception):
    pass


# ── Result objects ───────────────────────────────────────────────────────────


@dataclass
class TotpEnrollment:
    secret: str
    provisioning_uri: str
    qr_code_data_uri: str


# ── Helpers ──────────────────────────────────────────────────────────────────


def _svg_qr_data_uri(provisioning_uri: str) -> str:
    """Render an SVG-flavoured data URI without pulling in heavy QR libs.

    We embed the provisioning URI itself as text inside a tiny SVG. Real QR
    rendering happens client-side via a lightweight JS lib. Backend just needs
    to deliver something the ``<img src>`` tag can swallow without an extra
    request.
    """
    escaped = (
        provisioning_uri.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="240" height="240" '
        'viewBox="0 0 240 240">'
        f'<text x="10" y="20" font-size="8" font-family="monospace">'
        f"{escaped}</text>"
        "</svg>"
    )
    encoded = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"


def _account_label(user: User, issuer: str) -> str:
    return f"{issuer}:{user.email}"


def user_has_confirmed_totp(db: Session, user_id: int) -> bool:
    factor = db.scalars(
        select(UserMfaFactor).where(
            UserMfaFactor.user_id == user_id,
            UserMfaFactor.kind == TOTP_KIND,
            UserMfaFactor.confirmed_at.is_not(None),
            UserMfaFactor.revoked_at.is_(None),
        )
    ).first()
    return factor is not None


# ── Service ──────────────────────────────────────────────────────────────────


class MfaService:
    def __init__(self, db: Session) -> None:
        self.db = db

    # ── Enroll ───────────────────────────────────────────────────────────────

    def enroll_totp(
        self, *, user_id: int, issuer: str = DEFAULT_ISSUER, label: str | None = None
    ) -> TotpEnrollment:
        user = self.db.get(User, user_id)
        if user is None:
            raise MfaFactorNotFound(str(user_id))
        if user_has_confirmed_totp(self.db, user_id):
            raise TotpAlreadyEnrolled(str(user_id))

        # Replace any pending (unconfirmed) factor — keeps the row count tidy
        # when a user re-scans the QR before confirming.
        pending = self.db.scalars(
            select(UserMfaFactor).where(
                UserMfaFactor.user_id == user_id,
                UserMfaFactor.kind == TOTP_KIND,
                UserMfaFactor.confirmed_at.is_(None),
                UserMfaFactor.revoked_at.is_(None),
            )
        ).all()
        for row in pending:
            row.revoked_at = datetime.now(UTC)

        secret = pyotp.random_base32()
        factor = UserMfaFactor(
            user_id=user_id,
            kind=TOTP_KIND,
            secret=secret,
            label=label,
        )
        self.db.add(factor)
        self.db.commit()

        totp = pyotp.TOTP(secret)
        provisioning_uri = totp.provisioning_uri(
            name=_account_label(user, issuer),
            issuer_name=issuer,
        )
        # pyotp builds a URL-quoted URI; normalize for downstream consumers.
        provisioning_uri = urllib.parse.unquote_plus(provisioning_uri)
        return TotpEnrollment(
            secret=secret,
            provisioning_uri=provisioning_uri,
            qr_code_data_uri=_svg_qr_data_uri(provisioning_uri),
        )

    # ── Verify (during enroll) ───────────────────────────────────────────────

    def verify_totp(self, *, user_id: int, code: str) -> bool:
        factor = self._latest_pending_factor(user_id)
        if factor is None:
            # Maybe already confirmed — surface via wrong-code rather than
            # silent success, so callers re-issue enrollment intentionally.
            if user_has_confirmed_totp(self.db, user_id):
                raise TotpAlreadyEnrolled(str(user_id))
            raise MfaFactorNotFound(str(user_id))
        if not pyotp.TOTP(factor.secret).verify(code, valid_window=TOTP_VALID_WINDOW):
            raise InvalidTotpCode("totp_code")
        factor.confirmed_at = datetime.now(UTC)
        self.db.commit()
        return True

    # ── Login-time check ─────────────────────────────────────────────────────

    def check_login_totp(self, *, user_id: int, code: str) -> bool:
        factor = self.db.scalars(
            select(UserMfaFactor).where(
                UserMfaFactor.user_id == user_id,
                UserMfaFactor.kind == TOTP_KIND,
                UserMfaFactor.confirmed_at.is_not(None),
                UserMfaFactor.revoked_at.is_(None),
            )
        ).first()
        if factor is None:
            raise MfaFactorNotFound(str(user_id))
        if not pyotp.TOTP(factor.secret).verify(code, valid_window=TOTP_VALID_WINDOW):
            raise InvalidTotpCode("totp_code")
        return True

    # ── Revoke ───────────────────────────────────────────────────────────────

    def revoke_totp(self, *, user_id: int) -> None:
        rows = self.db.scalars(
            select(UserMfaFactor).where(
                UserMfaFactor.user_id == user_id,
                UserMfaFactor.kind == TOTP_KIND,
                UserMfaFactor.revoked_at.is_(None),
            )
        ).all()
        if not rows:
            raise MfaFactorNotFound(str(user_id))
        for row in rows:
            row.revoked_at = datetime.now(UTC)
        self.db.commit()

    # ── internals ────────────────────────────────────────────────────────────

    def _latest_pending_factor(self, user_id: int) -> UserMfaFactor | None:
        return self.db.scalars(
            select(UserMfaFactor)
            .where(
                UserMfaFactor.user_id == user_id,
                UserMfaFactor.kind == TOTP_KIND,
                UserMfaFactor.confirmed_at.is_(None),
                UserMfaFactor.revoked_at.is_(None),
            )
            .order_by(UserMfaFactor.created_at.desc())
        ).first()
