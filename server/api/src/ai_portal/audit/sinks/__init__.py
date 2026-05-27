"""Bundled audit sinks.

- :mod:`postgres`     — primary store, queryable
- :mod:`s3_jsonl`     — newline-delimited JSON to S3-compatible object storage
- :mod:`splunk_hec`   — Splunk HTTP Event Collector
- :mod:`datadog_logs` — Datadog Logs intake
- :mod:`syslog`       — RFC 5424 over UDP/TCP
"""

from __future__ import annotations
