"""Permission catalog — single source of truth across all modules.

Every gated action in every module declares its permission key here. The
:mod:`alembic` seed pours this list into the ``permissions`` table on upgrade.

Key shape: ``<namespace>:<action>`` (optionally ``<namespace>:<action>:<scope>``)
- namespace identifies the module / resource class
- action is the verb (``read``, ``write``, ``create``, ``delete``, ...)
- lowercase, hyphens permitted in namespace
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Permission:
    key: str
    description: str
    module: str  # control_plane | gateway | rag | memories | workers


# fmt: off
PERMISSIONS: list[Permission] = [
    # ── control plane ────────────────────────────────────────────────────────
    Permission("org:read", "Read org metadata", "control_plane"),
    Permission("org:update", "Update org metadata", "control_plane"),
    Permission("org:delete", "Delete / archive org", "control_plane"),
    Permission("members:read", "List org members", "control_plane"),
    Permission("members:invite", "Invite a new member", "control_plane"),
    Permission("members:remove", "Remove a member", "control_plane"),
    Permission("members:role:assign", "Assign roles to members", "control_plane"),
    Permission("teams:read", "List teams + members + per-team key/usage stats", "control_plane"),
    Permission("teams:write", "Create / update / delete teams + memberships", "control_plane"),
    Permission("api-keys:create", "Mint API keys", "control_plane"),
    Permission("api-keys:read", "List API keys (no secrets)", "control_plane"),
    Permission("api-keys:revoke", "Revoke API keys", "control_plane"),
    Permission("audit:read", "Search audit events", "control_plane"),
    Permission("audit:export", "Export audit events", "control_plane"),
    Permission("usage:read", "Read usage dashboard", "control_plane"),
    Permission("usage:export", "Export usage data", "control_plane"),
    Permission("budgets:read", "Read budgets + quotas", "control_plane"),
    Permission("budgets:write", "Create / update budgets + quotas", "control_plane"),
    Permission("webhooks:read", "List webhooks", "control_plane"),
    Permission("webhooks:write", "Create / update / delete webhooks", "control_plane"),
    Permission("settings:read", "Read org settings", "control_plane"),
    Permission("settings:write", "Update org settings + module flags", "control_plane"),
    Permission("rbac:read", "Read roles and permissions", "control_plane"),
    Permission("rbac:write", "Create / update roles", "control_plane"),
    Permission("idp:read", "Read SSO connections", "control_plane"),
    Permission("idp:write", "Configure SSO connections", "control_plane"),
    Permission("scim:read", "Read SCIM endpoints", "control_plane"),
    Permission("scim:write", "Configure SCIM endpoints", "control_plane"),
    Permission("billing:read", "Read billing + invoices", "control_plane"),
    Permission("billing:write", "Manage subscription + payment methods", "control_plane"),
    Permission("data:export", "Request GDPR data export", "control_plane"),
    Permission("data:delete", "Request GDPR data delete", "control_plane"),

    # ── gateway ──────────────────────────────────────────────────────────────
    Permission("gateway:complete", "Call LLMs through gateway", "gateway"),
    Permission("gateway:embed", "Call embedding models", "gateway"),
    Permission("gateway:admin", "Manage routing / rate-limits / policies", "gateway"),
    Permission("gateway:traces:read", "View gateway traces", "gateway"),
    Permission("gateway:replay", "Replay historic gateway requests", "gateway"),

    # ── rag (knowledge bases) ────────────────────────────────────────────────
    Permission("kb:create", "Create a knowledge base", "rag"),
    Permission("kb:read", "Read a knowledge base", "rag"),
    Permission("kb:write", "Ingest / update content in a KB", "rag"),
    Permission("kb:delete", "Delete a knowledge base", "rag"),
    Permission("kb:answer", "Run RAG answer queries", "rag"),
    Permission("kb:eval", "Run evaluation runs against a KB", "rag"),

    # ── memories ─────────────────────────────────────────────────────────────
    Permission("memory:read", "Read user / org memories", "memories"),
    Permission("memory:write", "Write user / org memories", "memories"),
    Permission("memory:admin", "Administer memory store", "memories"),

    # ── workers (agentic tasks) ──────────────────────────────────────────────
    Permission("workers:submit", "Submit worker tasks", "workers"),
    Permission("workers:approve", "Approve worker outputs", "workers"),
    Permission("workers:admin", "Manage worker fleet + queues", "workers"),
]
# fmt: on


_BY_KEY: dict[str, Permission] = {p.key: p for p in PERMISSIONS}


def permission_by_key(key: str) -> Permission | None:
    """Return the catalog entry for *key* or ``None`` if unknown."""
    return _BY_KEY.get(key)


def all_keys() -> list[str]:
    return [p.key for p in PERMISSIONS]
