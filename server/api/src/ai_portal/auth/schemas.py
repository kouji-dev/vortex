from __future__ import annotations

from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: str
    password: str


class SessionRead(BaseModel):
    id: str
    ip: str | None
    user_agent: str | None
    created_at: str
    expires_at: str
    revoked_at: str | None
    current: bool = False


class SessionsList(BaseModel):
    sessions: list[SessionRead]


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserRead(BaseModel):
    id: int
    email: str
    role: str
    is_verified: bool
    is_superuser: bool
    org_id: str | None

    model_config = {"from_attributes": True}


class AcceptInviteRequest(BaseModel):
    token: str
    password: str = Field(min_length=8, max_length=128)
