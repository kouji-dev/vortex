"""Object storage abstraction (BlobStore) for the Control Plane.

Bundled providers live under ``ai_portal.storage.providers``. The
:class:`BlobStore` protocol is the only stable surface — services depend on
the protocol, not the concrete provider.
"""

from ai_portal.storage.protocol import BlobStore

__all__ = ["BlobStore"]
