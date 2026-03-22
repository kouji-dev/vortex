"""Celery entrypoint: `celery -A ai_portal.worker worker -l info`."""

import ai_portal.tasks.ingest  # noqa: F401
from ai_portal.celery_app import app as celery_app

__all__ = ["celery_app"]
