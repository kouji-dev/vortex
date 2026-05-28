"""Provider-compatible HTTP surfaces.

Each module in this package translates one vendor's wire format into the
canonical :class:`ai_portal.gateway.LLMRequest` on the way in and back out
to the vendor's response shape on the way out. The actual completion call
goes through the gateway service (DI-overridable for tests).
"""
