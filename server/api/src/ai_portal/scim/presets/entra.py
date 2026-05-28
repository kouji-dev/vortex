"""Microsoft Entra (Azure AD) SCIM attribute mapper.

Differences from generic SCIM:

- Entra sometimes omits ``externalId`` and uses the Entra-specific extension
  ``urn:ietf:params:scim:schemas:extension:enterprise:2.0:User`` with
  ``employeeNumber``. We prefer ``externalId`` when set, otherwise fall back to
  the enterprise extension's ``employeeNumber`` and finally to the request's
  ``id`` (the Entra ``objectId``).
- Group member refs carry the user's Entra ``objectId`` in ``value``.
- ``displayName`` on User is sometimes the only name field Entra sends.
"""

from __future__ import annotations

from ai_portal.scim.presets.base import (
    MappedGroup,
    MappedGroupMember,
    MappedUser,
)
from ai_portal.scim.presets.generic import GenericPreset

ENTERPRISE_USER_URN = (
    "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
)


def _entra_external_id(payload: dict) -> str | None:
    """Resolve Entra's stable user id.

    Order:
    1. ``externalId`` if present (Entra emits this when configured).
    2. ``id`` (the Entra ``objectId`` sent by SCIM clients on PUT/PATCH).
    3. enterprise extension's ``employeeNumber``.
    """
    if payload.get("externalId"):
        return str(payload["externalId"])
    if payload.get("id"):
        return str(payload["id"])
    ext = payload.get(ENTERPRISE_USER_URN) or {}
    emp = ext.get("employeeNumber") if isinstance(ext, dict) else None
    if emp:
        return str(emp)
    return None


class EntraPreset:
    name = "entra"

    def __init__(self) -> None:
        self._generic = GenericPreset()

    def map_user(self, payload: dict) -> MappedUser:
        base = self._generic.map_user(payload)
        external = _entra_external_id(payload)
        # Entra's User.displayName is sometimes the full name when ``name`` is
        # missing entirely.
        name = base.name or payload.get("displayName")
        return MappedUser(
            external_id=external,
            user_name=base.user_name,
            email=base.email,
            name=name,
            active=base.active,
            locale=base.locale,
        )

    def map_group(self, payload: dict) -> MappedGroup:
        raw_members = payload.get("members") or []
        members: list[MappedGroupMember] = []
        for m in raw_members:
            value = m.get("value")
            if not value:
                continue
            members.append(
                MappedGroupMember(
                    external_user_id=str(value),
                    email=m.get("display") or None,
                )
            )
        external = payload.get("externalId") or payload.get("id")
        return MappedGroup(
            external_id=(str(external) if external else None),
            display_name=str(payload.get("displayName") or "").strip(),
            members=members,
        )
