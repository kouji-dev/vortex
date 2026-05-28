from __future__ import annotations

import asyncio
import logging
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop is the default)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from ai_portal.api.admin.consumption import router as consumption_router
from ai_portal.api_keys.router import router as api_keys_router
from ai_portal.assistant.router import router as assistants_router
from ai_portal.audit.router import router as audit_router
from ai_portal.auth.router import router as auth_router
from ai_portal.auth.routes_control_plane import router as control_plane_router
from ai_portal.auth.routes_me import router as me_router
from ai_portal.auth.routes_mfa import router as auth_mfa_router
from ai_portal.auth.routes_sso import router as auth_sso_router
import ai_portal.auth.idp.providers  # noqa: F401 — register IdP factories on startup
from ai_portal.catalog.router import router as catalog_router
from ai_portal.chat.router import router as chat_router
from ai_portal.knowledge_base.router import router as knowledge_base_router
from ai_portal.assistant.router import router as assistants_router
from ai_portal.auth.routes_orgs import router as orgs_router
from ai_portal.auth.routes_setup import router as setup_router
from ai_portal.memory.router import router as memories_router
from ai_portal.usage.router import router as usage_router, v1_router as usage_v1_router
from ai_portal.budgets.router import router as budgets_router
from ai_portal.rbac.router import router as rbac_router
from ai_portal.retention.router import router as retention_router
from ai_portal.api.admin.consumption import router as consumption_router
from ai_portal.realtime.router import router as realtime_router
from ai_portal.webhooks.router import router as webhooks_router
from ai_portal.billing.router import router as billing_router
from ai_portal.api_keys.router import router as api_keys_router
from ai_portal.scim.router import admin_router as scim_admin_router
from ai_portal.scim.router import scim_router
from ai_portal.settings.router import router as settings_router
from ai_portal.core.config import get_settings, settings_log_snapshot
from ai_portal.core.logging import configure_logging
from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware
from ai_portal.gateway.playground.router import router as gateway_playground_router
from ai_portal.gateway.rate_limits.router import router as gateway_limits_router
from ai_portal.gdpr.router import router as gdpr_router
from ai_portal.knowledge_base.router import router as knowledge_base_router
from ai_portal.memory.router import router as memories_router
from ai_portal.rbac.router import router as rbac_router
from ai_portal.realtime.router import router as realtime_router
from ai_portal.retention.router import router as retention_router
from ai_portal.settings.router import router as settings_router
from ai_portal.usage.router import router as usage_router
from ai_portal.usage.router import v1_router as usage_v1_router
from ai_portal.webhooks.router import router as webhooks_router

logger = logging.getLogger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    st = get_settings()
    logger.info("app_startup %s", settings_log_snapshot(st))

    # OTEL — install only when OTEL_ENABLED is truthy.
    from ai_portal.gateway.traces import otel as _otel  # noqa: PLC0415
    if _otel.is_enabled():
        _otel.install()
        logger.info("otel_installed")

    # Start TraceWriter background drain.
    from ai_portal.gateway.traces import get_writer as _get_writer  # noqa: PLC0415
    _writer = _get_writer()
    try:
        await _writer.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("trace_writer_start_failed: %s", exc)

    yield

    try:
        await _writer.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("trace_writer_stop_failed: %s", exc)
    logger.info("app_shutdown")


app = FastAPI(title="AI Portal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.deployment_mode == "dev" else settings.cors_origin_list,
    allow_credentials=False if settings.deployment_mode == "dev" else True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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


app.include_router(auth_router)
app.include_router(auth_mfa_router)
app.include_router(auth_sso_router)
app.include_router(catalog_router)
app.include_router(me_router)
app.include_router(assistants_router)
app.include_router(chat_router)
app.include_router(memories_router)
app.include_router(knowledge_base_router)
app.include_router(setup_router)
app.include_router(orgs_router)
app.include_router(control_plane_router)
app.include_router(usage_router)
app.include_router(usage_v1_router)
app.include_router(budgets_router)
app.include_router(audit_router)
app.include_router(rbac_router)
app.include_router(retention_router)
app.include_router(consumption_router)
app.include_router(realtime_router)
app.include_router(webhooks_router)
app.include_router(billing_router)
app.include_router(api_keys_router)
app.include_router(scim_admin_router)
app.include_router(scim_router)
app.include_router(settings_router)
app.include_router(gdpr_router)
app.include_router(gateway_limits_router)
app.include_router(gateway_playground_router)

