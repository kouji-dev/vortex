"""User signup / verify / password-reset schemas."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=255)
    locale: str | None = Field(default=None, max_length=16)


class VerifyEmailRequest(BaseModel):
    token: str = Field(min_length=8, max_length=256)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=8, max_length=256)
    new_password: str = Field(min_length=8, max_length=128)


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(default=None, max_length=255)
    locale: str | None = Field(default=None, max_length=16)


class UserProfileOut(BaseModel):
    id: int
    email: str
    name: str | None = None
    locale: str | None = None
    role: str
    is_active: bool
    is_verified: bool
    mfa_required: bool
    email_verified_at: datetime | None = None
    org_id: str | None = None

    model_config = {"from_attributes": True}
