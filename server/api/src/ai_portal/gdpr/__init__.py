"""GDPR data lifecycle — Article 15 (export) + Article 17 (delete).

Public surface re-exported via :mod:`ai_portal.control_plane`. Module
exporters and deleters register at import time so the workers can fan out
across every module that opted in.
"""

from ai_portal.gdpr.registry import register_exporter

__all__ = ["register_exporter"]
