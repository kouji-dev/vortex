"""RQ entrypoint for ingest."""

from unittest.mock import patch

from ai_portal.knowledge_base.workers.ingest.job import run_ingest_job


def test_run_ingest_job_delegates_to_worker():
    with patch("ai_portal.knowledge_base.workers.ingest.job.ingest_document_worker") as w:
        run_ingest_job(99)
        w.assert_called_once_with(99)
