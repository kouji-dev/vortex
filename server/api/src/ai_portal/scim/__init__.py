"""SCIM 2.0 provisioning for the control plane.

Phase H. One SCIM endpoint per org. Bearer token (sha256) authenticates inbound
requests from Okta / Entra / generic SCIM clients. The router accepts the RFC
7644 shape; the service translates payloads via a preset attribute mapper into
control-plane User + Group + role-assignment writes.

Deactivation (``active=false`` on User) revokes all sessions and scopes the
user's API keys. Group membership maps to a system role via
``scim_groups.role_name``.
"""

from __future__ import annotations
