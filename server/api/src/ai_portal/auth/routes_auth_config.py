"""Public auth-config bootstrap — GET /v1/auth/config.

Unauthenticated. The frontend hits this before rendering login/signup so it
shows only the strategies this deployment enables (password / social buttons /
directory / enterprise SSO). No mode flag involved.

The advertised social list is the intersection of the deployment config and the
social providers actually registered in the backend registry, so we never
surface a button the server can't service.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

import ai_portal.auth.social.providers  # noqa: F401 — register social providers
from ai_portal.auth.config import get_auth_config
from ai_portal.auth.social.registry import available_social_providers

router = APIRouter(prefix="/v1/auth", tags=["auth", "config"])


class AuthConfigResponse(BaseModel):
    password: bool
    social: list[str]
    directory: bool
    enterprise: bool


@router.get("/config", response_model=AuthConfigResponse)
def auth_config() -> AuthConfigResponse:
    cfg = get_auth_config()
    registered = set(available_social_providers())
    # Only advertise providers that are both enabled AND registered.
    social = [p for p in cfg.social_providers if p in registered]
    return AuthConfigResponse(
        password=cfg.password_enabled,
        social=social,
        directory=cfg.directory_enabled,
        enterprise=cfg.enterprise_enabled,
    )
