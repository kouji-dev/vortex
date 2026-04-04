from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ai_portal.api import (
    auth,
    assistants,
    conversations,
    e2e,
    knowledge_bases,
    me,
    memories,
    model_catalog,
    orgs as orgs_api,
    setup as setup_api,
)
from ai_portal.config import get_settings, settings_log_snapshot
from ai_portal.logging_config import configure_logging

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    st = get_settings()
    logger.info("app_startup %s", settings_log_snapshot(st))
    yield
    logger.info("app_shutdown")


app = FastAPI(title="AI Portal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from ai_portal.middleware.setup_guard import SetupGuardMiddleware

app.add_middleware(SetupGuardMiddleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


def _app_has_post_knowledge_bases_create() -> bool:
    for route in app.routes:
        if getattr(route, "path", None) != "/api/knowledge-bases":
            continue
        methods = getattr(route, "methods", None) or set()
        if "POST" in methods:
            return True
    return False


@app.get("/health")
def health() -> dict[str, Any]:
    st = get_settings()
    return {
        "status": "ok",
        "auth_mode": st.auth_mode,
        "api": {"post_knowledge_bases": _app_has_post_knowledge_bases_create()},
    }


app.include_router(auth.router)
app.include_router(model_catalog.router)
app.include_router(me.router)
app.include_router(assistants.router)
app.include_router(conversations.router)
app.include_router(memories.router)
app.include_router(knowledge_bases.router)
app.include_router(setup_api.router)
app.include_router(orgs_api.router)

if settings.auth_mode == "dev":
    app.include_router(e2e.router)
