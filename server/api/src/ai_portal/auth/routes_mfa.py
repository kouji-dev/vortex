"""MFA + session-management routes.

Phase M1+M2 of the Control Plane plan. Mounted under ``/auth`` next to the
login/register endpoints so the frontend can reuse the same fetch client.
"""
from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.mfa_totp import (
    InvalidTotpCode,
    MfaFactorNotFound,
    MfaService,
    TotpAlreadyEnrolled,
)
from ai_portal.auth.model import User
from ai_portal.auth.schemas import (
    SessionRead,
    SessionsList,
    TotpEnrollResponse,
    TotpVerifyRequest,
)
from ai_portal.auth.sessions import (
    SessionNotFound,
    list_sessions,
    revoke_all_except,
    revoke_session,
)

router = APIRouter(prefix="/auth", tags=["auth"])


# ── MFA / TOTP ───────────────────────────────────────────────────────────────


@router.post("/mfa/totp/enroll", response_model=TotpEnrollResponse)
def enroll_totp(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TotpEnrollResponse:
    svc = MfaService(db)
    try:
        enrol = svc.enroll_totp(user_id=user.id)
    except TotpAlreadyEnrolled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="totp_already_enrolled")
    return TotpEnrollResponse(
        secret=enrol.secret,
        provisioning_uri=enrol.provisioning_uri,
        qr_code_data_uri=enrol.qr_code_data_uri,
    )


@router.post("/mfa/totp/verify", status_code=status.HTTP_200_OK)
def verify_totp(
    body: TotpVerifyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    svc = MfaService(db)
    try:
        svc.verify_totp(user_id=user.id, code=body.code)
    except InvalidTotpCode:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="invalid_totp_code")
    except MfaFactorNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="totp_not_enrolled")
    except TotpAlreadyEnrolled:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="totp_already_enrolled")
    return {"confirmed": True}


@router.delete("/mfa/totp", status_code=status.HTTP_204_NO_CONTENT)
def revoke_totp(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    svc = MfaService(db)
    try:
        svc.revoke_totp(user_id=user.id)
    except MfaFactorNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="totp_not_enrolled")


# ── Sessions ─────────────────────────────────────────────────────────────────


def _current_session_id(request: Request) -> _uuid.UUID | None:
    sid = getattr(request.state, "session_id", None)
    if isinstance(sid, _uuid.UUID):
        return sid
    if isinstance(sid, str) and sid:
        try:
            return _uuid.UUID(sid)
        except ValueError:
            return None
    return None


def _serialize(session, current_sid: _uuid.UUID | None) -> SessionRead:
    return SessionRead(
        id=str(session.id),
        ip=session.ip,
        user_agent=session.user_agent,
        created_at=session.created_at.isoformat() if session.created_at else "",
        expires_at=session.expires_at.isoformat() if session.expires_at else "",
        revoked_at=session.revoked_at.isoformat() if session.revoked_at else None,
        current=(current_sid is not None and session.id == current_sid),
    )


@router.get("/sessions", response_model=SessionsList)
def list_user_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionsList:
    rows = list_sessions(db, user_id=user.id)
    current_sid = _current_session_id(request)
    return SessionsList(sessions=[_serialize(r, current_sid) for r in rows])


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_one_session(
    session_id: _uuid.UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        revoke_session(db, user_id=user.id, session_id=session_id)
    except SessionNotFound:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="session_not_found")


@router.delete("/sessions", status_code=status.HTTP_204_NO_CONTENT)
def revoke_all_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    keep = _current_session_id(request)
    revoke_all_except(db, user_id=user.id, keep_session_id=keep)
