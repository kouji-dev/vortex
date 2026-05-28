"""FastAPI deps — resolve the configured BillingProvider.

Selection rules:
- ``BILLING_PROVIDER=stripe`` -> Stripe (requires ``STRIPE_API_KEY``).
- anything else (or unset) -> manual no-op.

The provider is process-scoped (cached). Tests override via
``app.dependency_overrides[get_billing_provider]``.
"""

from __future__ import annotations

import os
from functools import lru_cache

from ai_portal.billing.protocol import BillingProvider
from ai_portal.billing.providers.manual import ManualBillingProvider


@lru_cache(maxsize=1)
def get_billing_provider() -> BillingProvider:
    kind = (os.environ.get("BILLING_PROVIDER") or "manual").strip().lower()
    if kind == "stripe":
        try:
            from ai_portal.billing.providers.stripe import StripeBillingProvider

            return StripeBillingProvider(
                api_key=os.environ.get("STRIPE_API_KEY"),
                webhook_secret=os.environ.get("STRIPE_WEBHOOK_SECRET"),
            )
        except Exception:  # noqa: BLE001 -- fail safe to manual
            pass
    return ManualBillingProvider()


def reset_billing_provider_cache() -> None:
    """Drop the cached provider — used by tests after env overrides."""
    get_billing_provider.cache_clear()
