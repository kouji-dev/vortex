"""Admin settings + module flags API.

- ``GET    /v1/settings``         — all KV entries for the org.
- ``PATCH  /v1/settings``         — bulk upsert KV entries.
- ``GET    /v1/module-flags``     — module on/off + gates view.
- ``PATCH  /v1/module-flags``     — bulk upsert module flags + gates.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_portal.auth.deps import get_current_user, get_db
from ai_portal.auth.model import User
from ai_portal.auth.routes_orgs import _require_role
from ai_portal.settings.schemas import (
    ModuleFlagOut,
    ModuleFlagsOut,
    ModuleFlagsPatch,
    SettingsOut,
    SettingsPatch,
)
from ai_portal.settings.service import (
    list_module_flags,
    list_org_settings,
    set_module_flag,
    set_org_setting,
)


router = APIRouter(prefix="/v1", tags=["settings"])


def _require_admin(user: User = Depends(get_current_user)) -> User:
    _require_role(user, "owner", "admin")
    if user.org_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="No org context")
    return user


# ── Settings KV ─────────────────────────────────────────────────────────────


@router.get("/settings", response_model=SettingsOut)
def get_settings(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> SettingsOut:
    assert user.org_id is not None  # _require_admin enforces
    return SettingsOut(settings=list_org_settings(db, org_id=user.org_id))


@router.patch("/settings", response_model=SettingsOut)
def patch_settings(
    body: SettingsPatch,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> SettingsOut:
    assert user.org_id is not None
    for key, value in body.settings.items():
        set_org_setting(db, org_id=user.org_id, key=key, value=value)
    return SettingsOut(settings=list_org_settings(db, org_id=user.org_id))


# ── Module flags ────────────────────────────────────────────────────────────


def _flags_out(db: Session, org_id) -> ModuleFlagsOut:
    raw = list_module_flags(db, org_id=org_id)
    return ModuleFlagsOut(
        modules={m: ModuleFlagOut(**v) for m, v in raw.items()}
    )


@router.get("/module-flags", response_model=ModuleFlagsOut)
def get_module_flags(
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ModuleFlagsOut:
    assert user.org_id is not None
    return _flags_out(db, user.org_id)


@router.patch("/module-flags", response_model=ModuleFlagsOut)
def patch_module_flags(
    body: ModuleFlagsPatch,
    db: Session = Depends(get_db),
    user: User = Depends(_require_admin),
) -> ModuleFlagsOut:
    assert user.org_id is not None
    for module, item in body.modules.items():
        # Default to enabled=True when caller only supplies gates.
        enabled = True if item.enabled is None else bool(item.enabled)
        set_module_flag(
            db,
            org_id=user.org_id,
            module=module,
            enabled=enabled,
            gates=item.gates,
        )
    return _flags_out(db, user.org_id)
