"""Control-plane API keys.

Personal / service / scoped API keys minted per-org. Plaintext is shown once at
creation time. We persist the SHA-256 hash plus a short prefix for recognition.

Contract (Phase C of the Control Plane plan):

- ``ApiKey.plaintext_prefix`` is ``ap_`` and the secret body is base62(32 bytes).
- ``ApiKey.scopes_json`` is a flat list of permission keys taken from the
  RBAC catalog (:mod:`ai_portal.rbac.catalog`).
- ``ApiKey.actor_user_id`` may be ``NULL`` for service keys.
- ``service.ApiKeyService.create`` returns a :class:`CreatedApiKey` tuple
  carrying the plaintext exactly once; subsequent reads return the model only.
"""

from __future__ import annotations
