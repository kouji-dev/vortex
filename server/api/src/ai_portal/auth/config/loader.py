"""Auth-config loader — reads enabled strategies from env / YAML.

Strategy kinds: ``password``, ``social`` (consumer OAuth), ``directory``
(LDAP/AD bind), ``enterprise`` (SSO). Any combination per deployment.

Resolution order (highest precedence first):
1. Environment variables (``AUTH_PASSWORD_ENABLED``, ``AUTH_SOCIAL_PROVIDERS``,
   ``AUTH_DIRECTORY_ENABLED``, ``AUTH_ENTERPRISE_ENABLED``).
2. The ``auth`` section of ``config.yaml`` (``auth.strategies``).
3. Defaults: password on, no social, directory off, enterprise on.

The result is read-only and surfaced to the frontend via the public
``GET /v1/auth/config`` bootstrap endpoint. The social provider list is
intersected with the actually-registered social providers so we never
advertise a button the backend can't service.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_SOCIAL_KNOWN = ("google", "github", "gitlab")


@dataclass(frozen=True, slots=True)
class AuthConfig:
    """Enabled auth strategies for this deployment."""

    password_enabled: bool = True
    social_providers: tuple[str, ...] = ()
    directory_enabled: bool = False
    enterprise_enabled: bool = True
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def social_enabled(self) -> bool:
        return bool(self.social_providers)

    def to_public_dict(self) -> dict[str, Any]:
        """Shape returned by the public bootstrap endpoint."""
        return {
            "password": self.password_enabled,
            "social": list(self.social_providers),
            "directory": self.directory_enabled,
            "enterprise": self.enterprise_enabled,
        }


# ── env / yaml parsing ──────────────────────────────────────────────────────


def _truthy(val: str | None, *, default: bool) -> bool:
    if val is None or val.strip() == "":
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _parse_social(val: str | None) -> tuple[str, ...] | None:
    """Parse a comma/space-separated provider list. ``None`` if unset."""
    if val is None:
        return None
    items = [p.strip().lower() for p in val.replace(",", " ").split() if p.strip()]
    # Keep only known providers, dedup, preserve declared order.
    seen: list[str] = []
    for p in items:
        if p in _SOCIAL_KNOWN and p not in seen:
            seen.append(p)
    return tuple(seen)


def _config_yaml_path() -> Path:
    env_path = os.environ.get("AI_PORTAL_CONFIG")
    if env_path:
        return Path(env_path)
    # server/api/config.yaml — same location core.config uses.
    return Path(__file__).resolve().parents[4] / "config.yaml"


def _yaml_auth_section() -> dict[str, Any]:
    path = _config_yaml_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
    except (yaml.YAMLError, OSError):
        return {}
    auth = data.get("auth")
    if not isinstance(auth, dict):
        return {}
    strategies = auth.get("strategies")
    return strategies if isinstance(strategies, dict) else {}


def _load() -> AuthConfig:
    yaml_cfg = _yaml_auth_section()

    # YAML provides the base; env overrides per-key.
    y_password = yaml_cfg.get("password")
    y_social = yaml_cfg.get("social")
    y_directory = yaml_cfg.get("directory")
    y_enterprise = yaml_cfg.get("enterprise")

    password = _truthy(
        os.environ.get("AUTH_PASSWORD_ENABLED"),
        default=bool(y_password) if y_password is not None else True,
    )
    directory = _truthy(
        os.environ.get("AUTH_DIRECTORY_ENABLED"),
        default=bool(y_directory) if y_directory is not None else False,
    )
    enterprise = _truthy(
        os.environ.get("AUTH_ENTERPRISE_ENABLED"),
        default=bool(y_enterprise) if y_enterprise is not None else True,
    )

    social = _parse_social(os.environ.get("AUTH_SOCIAL_PROVIDERS"))
    if social is None:
        # Fall back to YAML list.
        if isinstance(y_social, (list, tuple)):
            social = tuple(
                p for p in (str(x).strip().lower() for x in y_social)
                if p in _SOCIAL_KNOWN
            )
        elif isinstance(y_social, str):
            social = _parse_social(y_social) or ()
        else:
            social = ()

    return AuthConfig(
        password_enabled=password,
        social_providers=tuple(social),
        directory_enabled=directory,
        enterprise_enabled=enterprise,
    )


@lru_cache(maxsize=1)
def _cached() -> AuthConfig:
    return _load()


def get_auth_config() -> AuthConfig:
    """Return the deployment :class:`AuthConfig` (cached)."""
    return _cached()


def get_enabled_auth_strategies() -> AuthConfig:
    """Module-boundary alias — same as :func:`get_auth_config`."""
    return get_auth_config()


def reset_cache() -> None:
    """Test hook — drop the cached config so env changes are observed."""
    _cached.cache_clear()
