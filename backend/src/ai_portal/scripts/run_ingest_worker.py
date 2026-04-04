"""Run RQ worker for the ``ingest`` queue (requires ``REDIS_URL``)."""
from __future__ import annotations

import logging
import sys

from redis import Redis
from rq import Connection, Worker
from rq.timeouts import TimerDeathPenalty
from rq.worker import SimpleWorker

from ai_portal.config import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.redis_url.strip():
        raise SystemExit("REDIS_URL must be set to run the ingest worker.")
    redis = Redis.from_url(settings.redis_url)
    logger.info("ingest_worker_starting", extra={"redis": settings.redis_url.split("@")[-1]})
    with Connection(redis):
        # Default RQ Worker uses os.fork(); UnixSignalDeathPenalty uses SIGALRM — neither works on Windows.
        if sys.platform == "win32":
            w: Worker = SimpleWorker(["ingest"])
            w.death_penalty_class = TimerDeathPenalty
        else:
            w = Worker(["ingest"])
        w.work()


if __name__ == "__main__":
    main()
