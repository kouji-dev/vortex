from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any

# psycopg async requires SelectorEventLoop on Windows (ProactorEventLoop is the default)
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

import ai_portal.auth.idp.providers  # noqa: F401 — register IdP factories on startup
from ai_portal.api.admin.consumption import router as consumption_router
from ai_portal.api_keys.router import router as api_keys_router
from ai_portal.assistant.router import router as assistants_router
from ai_portal.audit.router import router as audit_router
from ai_portal.audit.sinks_router import router as audit_sinks_router
from ai_portal.auth.router import router as auth_router
from ai_portal.auth.routes_control_plane import router as control_plane_router
from ai_portal.auth.routes_me import router as me_router
from ai_portal.auth.routes_members import router as members_router
from ai_portal.auth.routes_orgs import router as orgs_router
from ai_portal.auth.routes_sso import router as auth_sso_router
from ai_portal.billing.router import router as billing_router
from ai_portal.budgets.router import router as budgets_router
from ai_portal.catalog.router import router as catalog_router
from ai_portal.chat.router import router as chat_router
from ai_portal.core.config import get_settings, settings_log_snapshot
from ai_portal.gateway.compat.openai import router as gateway_openai_compat_router
from ai_portal.core.logging import configure_logging
from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware
from ai_portal.gateway.admin_routes import router as gateway_admin_router
from ai_portal.gateway.evals.router import router as gateway_evals_router
from ai_portal.gateway.traces.router import router as gateway_traces_router
from ai_portal.gateway.playground.router import router as gateway_playground_router
from ai_portal.gateway.rate_limits.router import router as gateway_limits_router
from ai_portal.gateway.traces.metrics_router import router as gateway_metrics_router
from ai_portal.gdpr.router import router as gdpr_router
from ai_portal.guardrails.router import router as guardrail_policies_router
from ai_portal.knowledge_base.router import router as knowledge_base_router
from ai_portal.memory.router import router as memories_router
from ai_portal.memory.v1_router import router as memories_v1_router
from ai_portal.middleware.csrf import CsrfMiddleware
from ai_portal.rag.management.router import router as rag_management_router
from ai_portal.rag.router import router as rag_router
from ai_portal.rbac.router import router as rbac_router
from ai_portal.realtime.router import router as realtime_router
from ai_portal.retention.router import router as retention_router
from ai_portal.settings.router import router as settings_router
from ai_portal.usage.router import router as usage_router
from ai_portal.usage.router import v1_router as usage_v1_router
from ai_portal.webhooks.router import router as webhooks_router
from ai_portal.workers.router import router as workers_router
from ai_portal.workers.instances_router import router as workers_instances_router
from ai_portal.workers.triggers.webhook_router import router as workers_webhook_router
from ai_portal.workers.git.router import router as workers_git_router
from ai_portal.auth.routes_social import router as auth_social_router
from ai_portal.auth.routes_auth_config import router as auth_config_router
from ai_portal.control_plane.teams.router import router as teams_router

logger = logging.getLogger(__name__)
settings = get_settings()


def _install_default_gateway_facade(
    fastapi_app: FastAPI, st: Any, trace_writer: Any
) -> None:
    """Wire the process-wide :class:`GatewayFacade` for compat surfaces.

    - emit_trace → :class:`TraceWriter` submit (async drain to ``request_traces``)
    - emit_audit → :func:`ai_portal.audit.service.emit_audit`
    - emit_usage → :func:`ai_portal.usage.emit.emit_usage` (own DB session)
    - resolve_provider → real httpx adapter (anthropic/openai) built from the
      org's :class:`ProviderCredential` (or env-config fallback) via
      :class:`ProviderResolver`; :class:`FakeProvider` only when
      ``GATEWAY_USE_FAKE_PROVIDER`` is set
    """
    from ai_portal.audit.service import emit_audit as _emit_audit  # noqa: PLC0415
    from ai_portal.gateway import service as gw_service  # noqa: PLC0415
    from ai_portal.gateway.facade import (  # noqa: PLC0415
        FacadeConfig,
        GatewayFacade,
        set_default_facade,
    )
    from ai_portal.gateway.providers.resolution import (  # noqa: PLC0415
        NoProviderCredential,
        ProviderResolver,
    )
    from ai_portal.gateway.traces.writer import TraceRecord  # noqa: PLC0415
    from ai_portal.usage.emit import emit_usage as _emit_usage  # noqa: PLC0415

    use_fake = os.environ.get("GATEWAY_USE_FAKE_PROVIDER", "").lower() in (
        "1", "true", "yes",
    )

    # ── Provider resolution ─────────────────────────────────────────────────
    # Real HTTP adapters (anthropic/openai) are the runtime path. FakeProvider
    # is a deliberate test-only hook gated behind GATEWAY_USE_FAKE_PROVIDER.

    provider_singleton: Any = None
    if use_fake:
        from ai_portal.gateway.fake_provider import FakeProvider  # noqa: PLC0415
        provider_singleton = FakeProvider()
        logger.info("gateway_fake_provider_bound")

    def _load_org_secret(org_id: Any, provider: str) -> str | None:
        """Decrypt the org's ProviderCredential for ``provider`` (or None)."""
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415
        from ai_portal.gateway.provider_credentials.service import (  # noqa: PLC0415
            CredentialNotFound,
            ProviderCredentialService,
        )

        try:
            with SessionLocal() as db:
                with bypass_rls(db):
                    svc = ProviderCredentialService(db)
                    try:
                        return svc.get_decrypted(org_id=org_id, provider=provider)
                    except CredentialNotFound:
                        return None
        except Exception:  # noqa: BLE001
            logger.debug("provider credential lookup failed", exc_info=True)
            return None

    resolver = ProviderResolver(settings=st, load_org_secret=_load_org_secret)

    def _resolve_provider(req: Any, actor: Any) -> Any:
        # Fake provider wins only when explicitly enabled (tests / smoke).
        if provider_singleton is not None:
            return provider_singleton
        org_id = getattr(actor, "org_id", None)
        model = getattr(req, "model", "") or ""
        return resolver.resolve(org_id=org_id, model=model)

    # Override the compat FastAPI dep so OpenAI/Anthropic/Bedrock surfaces
    # resolve a real adapter from the authenticated org's credentials.
    # The dep reads the model off the (cached) JSON body and the org off the
    # authenticated user, then builds/caches the matching adapter.
    async def _resolve_for_request_dep(request: Request) -> Any:
        if provider_singleton is not None:
            return provider_singleton
        user = getattr(request.state, "current_user", None)
        if user is None:
            # Compat routes set current_user inside the handler (after deps),
            # so resolve the actor here too — best-effort, no auth requirement.
            from ai_portal.gateway.compat.openai import (  # noqa: PLC0415
                _try_resolve_actor_user,
            )

            user = _try_resolve_actor_user(request)
        org_id = getattr(user, "org_id", None)
        model = ""
        try:
            body = await request.json()
            model = (body or {}).get("model", "") or ""
        except Exception:  # noqa: BLE001
            model = ""
        try:
            return resolver.resolve(org_id=org_id, model=model)
        except NoProviderCredential as exc:
            from fastapi import HTTPException  # noqa: PLC0415

            raise HTTPException(status_code=503, detail=str(exc)) from exc

    fastapi_app.dependency_overrides[gw_service.get_llm_provider] = (
        _resolve_for_request_dep
    )

    def _emit_trace(record: TraceRecord) -> None:
        trace_writer.submit(record)

    def _emit_audit_hook(**kw: Any) -> None:
        try:
            _emit_audit(**kw)
        except Exception:  # noqa: BLE001
            logger.exception("gateway facade audit emit failed")

    def _emit_usage_hook(**kw: Any) -> None:
        from ai_portal.core.db.rls import bypass_rls  # noqa: PLC0415
        from ai_portal.core.db.session import SessionLocal  # noqa: PLC0415

        try:
            with SessionLocal() as db:
                with bypass_rls(db):
                    _emit_usage(db, **kw)
                    db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("gateway facade usage emit failed")

    facade = GatewayFacade(
        FacadeConfig(
            resolve_provider=_resolve_provider,
            emit_trace=_emit_trace,
            emit_audit=_emit_audit_hook,
            emit_usage=_emit_usage_hook,
            route_name="POST /v1/chat/completions",
        )
    )
    set_default_facade(facade)


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

    # Install the default GatewayFacade so internal callers + compat routes
    # share one trace/audit/usage emit pipeline.
    try:
        _install_default_gateway_facade(_app, st, _writer)
        logger.info("gateway_facade_installed")
    except Exception as exc:  # noqa: BLE001
        logger.warning("gateway_facade_install_failed: %s", exc)

    # Wire the new-device login alert through NotifyService — skip cleanly
    # when no notification transport is configured.
    try:
        from ai_portal.auth.new_device_notify import (  # noqa: PLC0415
            install_new_device_notifier,
        )
        from ai_portal.notify.bootstrap import build_notify_service  # noqa: PLC0415

        notify_svc = build_notify_service(st)
        if notify_svc is not None:
            install_new_device_notifier(notify_svc)
            logger.info("new_device_notifier_installed")
        else:
            logger.info("new_device_notifier_skipped notify_not_configured")
    except Exception as exc:  # noqa: BLE001
        logger.warning("new_device_notifier_install_failed: %s", exc)

    # Start catalog refresh + health-probe scheduler.
    from ai_portal.catalog import sync as _catalog_sync  # noqa: PLC0415
    _catalog_tasks: list = []
    try:
        _catalog_tasks = _catalog_sync.start_background_scheduler()
        logger.info("catalog_scheduler_started")
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog_scheduler_start_failed: %s", exc)

    yield

    try:
        await _catalog_sync.stop_background_scheduler(_catalog_tasks)
    except Exception as exc:  # noqa: BLE001
        logger.warning("catalog_scheduler_stop_failed: %s", exc)

    try:
        await _writer.stop()
    except Exception as exc:  # noqa: BLE001
        logger.warning("trace_writer_stop_failed: %s", exc)
    logger.info("app_shutdown")


app = FastAPI(title="AI Portal API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(SetupGuardMiddleware)
app.add_middleware(CsrfMiddleware)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    return response


@app.middleware("http")
async def api_v1_prefix_compat(request: Request, call_next):
    """Frontend's authorizedFetch hits `/api/v1/...`; many backend routers are
    mounted at `/v1/...`. Strip the `/api` prefix so both conventions resolve.
    """
    path = request.scope.get("path", "")
    if path.startswith("/api/v1/") or path == "/api/v1":
        request.scope["path"] = path[4:] or "/"
        raw = request.scope.get("raw_path")
        if isinstance(raw, bytes) and raw.startswith(b"/api/v1"):
            request.scope["raw_path"] = raw[4:] or b"/"
    return await call_next(request)


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
        "deployment_mode": st.deployment_mode,
        "api": {"post_knowledge_bases": _app_has_post_knowledge_bases_create()},
    }


app.include_router(auth_router)
app.include_router(auth_sso_router)
app.include_router(catalog_router)
app.include_router(me_router)
app.include_router(assistants_router)
app.include_router(chat_router)
app.include_router(memories_router)
app.include_router(memories_v1_router)
app.include_router(knowledge_base_router)
app.include_router(rag_router)
app.include_router(rag_management_router)
app.include_router(orgs_router)
app.include_router(members_router)
app.include_router(control_plane_router)
app.include_router(usage_router)
app.include_router(usage_v1_router)
app.include_router(budgets_router)
app.include_router(audit_router)
app.include_router(audit_sinks_router)
app.include_router(rbac_router)
app.include_router(retention_router)
app.include_router(consumption_router)
app.include_router(realtime_router)
app.include_router(webhooks_router)
app.include_router(billing_router)
app.include_router(api_keys_router)
app.include_router(settings_router)
app.include_router(gdpr_router)
app.include_router(gateway_limits_router)
app.include_router(gateway_playground_router)
app.include_router(gateway_evals_router)
app.include_router(gateway_admin_router)
app.include_router(gateway_traces_router)
app.include_router(gateway_metrics_router)
app.include_router(guardrail_policies_router)
app.include_router(workers_router)
app.include_router(workers_instances_router)
app.include_router(workers_webhook_router)
app.include_router(workers_git_router)
app.include_router(auth_social_router)
app.include_router(auth_config_router)
app.include_router(teams_router)
app.include_router(gateway_openai_compat_router)

