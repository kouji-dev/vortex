"""GDPR data lifecycle — Article 15 (export) + Article 17 (delete).

Two registries let every module declare how it participates:

- ``register_exporter(module_name, async_fn)``: ``fn(org_id) -> dict`` returns
  a JSON-serialisable dump for that module. The worker fans out, zips the
  output, uploads via BlobStore, and emails the requester a presigned URL.
- ``register_deleter(module_name, async_fn)``: ``fn(org_id, scope) -> None``
  hard-deletes all rows owned by the subject. The worker fans out across
  every registered module and emits an audit event on completion.

Public surface re-exported via :mod:`ai_portal.control_plane`.
"""

from ai_portal.gdpr.registry import register_deleter, register_exporter

__all__ = ["register_deleter", "register_exporter"]
