"""Okta SCIM attribute mapper.

Differences from generic SCIM:

- Okta sends ``userName`` in lowercase. We keep it as-is but lowercase the email
  comparator.
- Group member refs carry the Okta user id in ``value`` and the userName in
  ``display`` (we surface ``display`` as ``email`` for unresolved lookups).
- ``externalId`` is sent for both Users and Groups — already standard.
"""

from __future__ import annotations

from ai_portal.scim.presets.base import (
    MappedGroup,
    MappedGroupMember,
    MappedUser,
)
from ai_portal.scim.presets.generic import GenericPreset


class OktaPreset:
    name = "okta"

    def __init__(self) -> None:
        self._generic = GenericPreset()

    def map_user(self, payload: dict) -> MappedUser:
        base = self._generic.map_user(payload)
        # Okta lowercases userName by convention. Treat email lookups
        # case-insensitively.
        return MappedUser(
            external_id=base.external_id,
            user_name=base.user_name.lower(),
            email=base.email.lower(),
            name=base.name,
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
            display = m.get("display")
            members.append(
                MappedGroupMember(
                    external_user_id=str(value),
                    email=(str(display).lower() if display else None),
                )
            )
        return MappedGroup(
            external_id=payload.get("externalId"),
            display_name=str(payload.get("displayName") or "").strip(),
            members=members,
        )
