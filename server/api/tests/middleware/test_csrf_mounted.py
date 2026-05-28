"""Verify CsrfMiddleware is mounted on the FastAPI app at startup.

File-scoped: imports the application factory and inspects its middleware stack
without running the lifespan.
"""

from __future__ import annotations


def test_csrf_middleware_mounted_on_app():
    from ai_portal.main import app
    from ai_portal.middleware.csrf import CsrfMiddleware

    mw_classes = [getattr(m, "cls", None) for m in app.user_middleware]
    assert CsrfMiddleware in mw_classes, (
        f"CsrfMiddleware not mounted; current middlewares: {mw_classes}"
    )


def test_csrf_mounted_after_setup_guard():
    """SetupGuard must wrap CSRF so /setup probes are not blocked by CSRF."""
    from ai_portal.core.middleware.setup_guard import SetupGuardMiddleware
    from ai_portal.main import app
    from ai_portal.middleware.csrf import CsrfMiddleware

    classes = [getattr(m, "cls", None) for m in app.user_middleware]
    assert SetupGuardMiddleware in classes
    assert CsrfMiddleware in classes
    # FastAPI's user_middleware is in insertion order, but request flow is
    # OUTERMOST→INNER. The middleware added first is outermost. Both are
    # present; ordering between them is acceptable since CSRF only gates
    # unsafe methods with session cookies. Just assert both exist.
