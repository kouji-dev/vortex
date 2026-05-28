"""Dev launcher — forces SelectorEventLoop on Windows.

psycopg's async driver cannot use ProactorEventLoop. Python 3.14 deprecated
``set_event_loop_policy`` and the default factory still picks Proactor.
We monkey-patch ``asyncio.new_event_loop`` before importing uvicorn so the
loop uvicorn constructs is always Selector-based.

Usage:
    python run_dev.py
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    if sys.platform == "win32":
        import asyncio
        import selectors

        # Force SelectorEventLoop everywhere — psycopg async requires it.
        _orig = asyncio.new_event_loop

        def _new_selector_loop():
            return asyncio.SelectorEventLoop(selectors.SelectSelector())

        asyncio.new_event_loop = _new_selector_loop  # type: ignore[assignment]
        # Also set the deprecated policy for any code path that still consults it.
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass

    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "ai_portal.main:app",
        host="127.0.0.1",
        port=int(os.environ.get("API_PORT", "8000")),
        log_level="info",
        loop="asyncio",
        app_dir="src",
    )


if __name__ == "__main__":
    main()
