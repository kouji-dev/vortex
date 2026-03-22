from celery import Celery

from ai_portal.config import get_settings

settings = get_settings()

app = Celery(
    "ai_portal",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
