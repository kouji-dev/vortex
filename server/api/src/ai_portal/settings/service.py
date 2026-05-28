"""Settings + module flags service.

Default semantics:
- Every module is enabled by default; a row with ``enabled=false`` disables it.
- Feature gates default to ``False`` (opt-in). The caller passes the gate key.
- ``get_org_setting`` returns ``None`` when no row exists; caller supplies a
  default if needed.

All upserts are RLS-bypassing on writes (admin path); reads respect RLS but
the helpers expect callers to have already set org context where required.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ai_portal.core.db.rls import bypass_rls
from ai_portal.settings.model import ModuleFlag, OrgSetting


KNOWN_MODULES: tuple[str, ...] = (
    "gateway",
    "rag",
    "memories",
    "workers",
    "assistants",
    "chat",
    "knowledge_base",
)


# ── KV settings ─────────────────────────────────────────────────────────────


def get_org_setting(
    db: Session, *, org_id: _uuid.UUID, key: str, default: Any | None = None
) -> Any | None:
    """Return ``value_json`` for (org, key) or ``default`` if missing."""
    with bypass_rls(db):
        row = db.scalars(
            select(OrgSetting).where(
                OrgSetting.org_id == org_id, OrgSetting.key == key
            )
        ).first()
    if row is None:
        return default
    return row.value_json


def set_org_setting(
    db: Session, *, org_id: _uuid.UUID, key: str, value: Any
) -> None:
    """Upsert a setting row. Commits the transaction."""
    with bypass_rls(db):
        stmt = (
            pg_insert(OrgSetting)
            .values(org_id=org_id, key=key, value_json=value)
            .on_conflict_do_update(
                index_elements=["org_id", "key"],
                set_={"value_json": value},
            )
        )
        db.execute(stmt)
        db.commit()


def list_org_settings(db: Session, *, org_id: _uuid.UUID) -> dict[str, Any]:
    """Return all settings for the org as a flat ``{key: value}`` dict."""
    with bypass_rls(db):
        rows = db.scalars(
            select(OrgSetting).where(OrgSetting.org_id == org_id)
        ).all()
    return {r.key: r.value_json for r in rows}


# ── Module flags ────────────────────────────────────────────────────────────


def is_module_enabled(
    db: Session, *, org_id: _uuid.UUID, module: str
) -> bool:
    """Return True unless an explicit ``enabled=false`` row exists for the org."""
    with bypass_rls(db):
        row = db.scalars(
            select(ModuleFlag).where(
                ModuleFlag.org_id == org_id, ModuleFlag.module == module
            )
        ).first()
    if row is None:
        return True
    return bool(row.enabled)


def set_module_flag(
    db: Session,
    *,
    org_id: _uuid.UUID,
    module: str,
    enabled: bool,
    gates: dict | None = None,
) -> None:
    """Upsert a module flag. ``gates`` replaces the existing JSON blob."""
    payload: dict[str, Any] = {"enabled": enabled}
    if gates is not None:
        payload["gates_json"] = gates
    with bypass_rls(db):
        stmt = (
            pg_insert(ModuleFlag)
            .values(
                org_id=org_id,
                module=module,
                enabled=enabled,
                gates_json=gates or {},
            )
            .on_conflict_do_update(
                index_elements=["org_id", "module"],
                set_=payload,
            )
        )
        db.execute(stmt)
        db.commit()


def list_module_flags(
    db: Session, *, org_id: _uuid.UUID
) -> dict[str, dict[str, Any]]:
    """Return ``{module: {enabled, gates}}`` for every module.

    Known modules with no row appear as ``enabled=True`` with empty gates.
    Rows for unknown modules are still returned (forward-compat).
    """
    with bypass_rls(db):
        rows = db.scalars(
            select(ModuleFlag).where(ModuleFlag.org_id == org_id)
        ).all()
    by_module = {r.module: r for r in rows}
    out: dict[str, dict[str, Any]] = {}
    for m in KNOWN_MODULES:
        r = by_module.get(m)
        out[m] = {
            "enabled": True if r is None else bool(r.enabled),
            "gates": (r.gates_json if r is not None else {}) or {},
        }
    # Surface any unknown modules persisted by older code paths.
    for m, r in by_module.items():
        if m in out:
            continue
        out[m] = {"enabled": bool(r.enabled), "gates": r.gates_json or {}}
    return out


# ── Feature gates ───────────────────────────────────────────────────────────


def get_feature_gate(
    db: Session, *, org_id: _uuid.UUID, module: str, gate_key: str
) -> bool:
    """Return the gate's boolean value. Default ``False``."""
    with bypass_rls(db):
        row = db.scalars(
            select(ModuleFlag).where(
                ModuleFlag.org_id == org_id, ModuleFlag.module == module
            )
        ).first()
    if row is None:
        return False
    return bool((row.gates_json or {}).get(gate_key, False))


def set_feature_gate(
    db: Session,
    *,
    org_id: _uuid.UUID,
    module: str,
    gate_key: str,
    value: bool,
) -> None:
    """Set a single gate inside a module flag. Creates the row if missing."""
    with bypass_rls(db):
        existing = db.scalars(
            select(ModuleFlag).where(
                ModuleFlag.org_id == org_id, ModuleFlag.module == module
            )
        ).first()
        if existing is None:
            db.add(
                ModuleFlag(
                    org_id=org_id,
                    module=module,
                    enabled=True,
                    gates_json={gate_key: bool(value)},
                )
            )
        else:
            gates = dict(existing.gates_json or {})
            gates[gate_key] = bool(value)
            existing.gates_json = gates
        db.commit()
