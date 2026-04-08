from __future__ import annotations

import uuid as _uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_db
from ai_portal.auth.strategies.dev import RegistrationError, UserManager
from ai_portal.core.config import get_settings
from ai_portal.models.org import Org

router = APIRouter(tags=["setup"])


class SetupRequest(BaseModel):
    org_name: str = Field(min_length=1, max_length=255)
    admin_email: str = Field(min_length=3, max_length=255)
    admin_password: str = Field(min_length=8, max_length=128)


class SetupResponse(BaseModel):
    message: str
    org_id: str


@router.post("/setup", response_model=SetupResponse, status_code=status.HTTP_201_CREATED)
def first_run_setup(body: SetupRequest, db: Session = Depends(get_db)) -> SetupResponse:
    settings = get_settings()

    if settings.deployment_mode != "selfhosted":
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Setup endpoint is only available in selfhosted mode.",
        )

    # Check if already set up
    count = db.scalar(select(func.count()).select_from(Org))
    if count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail="Instance is already set up.",
        )

    # Create the instance org
    org = Org(
        slug="instance",
        name=body.org_name,
        instance_mode=True,
    )
    db.add(org)
    db.flush()

    # Create admin user (owner + superuser)
    manager = UserManager(db=db, secret=settings.secret_key)
    try:
        user = manager.register(
            email=body.admin_email,
            password=body.admin_password,
            org_id=org.id,
            role="owner",
        )
    except RegistrationError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, detail=str(e))

    # Make them superuser
    user.is_superuser = True
    user.is_verified = True
    db.commit()

    return SetupResponse(
        message="Instance setup complete. You can now log in.",
        org_id=str(org.id),
    )
