from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from ai_portal.config import get_settings
from ai_portal.db.session import SessionLocal
from ai_portal.models.org import Org
from sqlalchemy import select, func


EXEMPT_PATHS = {"/health", "/setup", "/auth/login"}


class SetupGuardMiddleware(BaseHTTPMiddleware):
    """Block all routes with 503 when DEPLOYMENT_MODE=selfhosted and no orgs exist."""

    async def dispatch(self, request: Request, call_next):
        settings = get_settings()
        if settings.deployment_mode != "selfhosted":
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        db = SessionLocal()
        try:
            count = db.scalar(select(func.count()).select_from(Org))
        finally:
            db.close()

        if count == 0:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Setup required. POST /setup to initialize this instance."
                },
            )

        return await call_next(request)
