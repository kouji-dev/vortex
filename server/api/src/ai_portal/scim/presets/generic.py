"""Generic SCIM 2.0 attribute mapper — uses the core schema verbatim."""

from __future__ import annotations

from ai_portal.scim.presets.base import (
    MappedGroup,
    MappedGroupMember,
    MappedUser,
)


def _primary_or_first_email(emails: list[dict] | None) -> str | None:
    if not emails:
        return None
    primary = next((e for e in emails if e.get("primary")), None)
    candidate = primary or emails[0]
    val = candidate.get("value") or candidate.get("Value")
    return str(val).strip() if val else None


def _format_name(name: dict | None) -> str | None:
    if not name:
        return None
    if name.get("formatted"):
        return str(name["formatted"]).strip()
    given = (name.get("givenName") or "").strip()
    family = (name.get("familyName") or "").strip()
    full = f"{given} {family}".strip()
    return full or None


class GenericPreset:
    name = "generic"

    def map_user(self, payload: dict) -> MappedUser:
        email = _primary_or_first_email(payload.get("emails"))
        user_name = payload.get("userName") or email or ""
        if not email:
            # Some clients only send userName when it's the email itself.
            email = user_name
        active = payload.get("active")
        # SCIM default: active = True if absent.
        active_bool = True if active is None else bool(active)
        return MappedUser(
            external_id=payload.get("externalId"),
            user_name=str(user_name),
            email=str(email),
            name=_format_name(payload.get("name")),
            active=active_bool,
            locale=payload.get("locale"),
        )

    def map_group(self, payload: dict) -> MappedGroup:
        raw_members = payload.get("members") or []
        members: list[MappedGroupMember] = []
        for m in raw_members:
            value = m.get("value") or m.get("Value")
            if not value:
                continue
            members.append(
                MappedGroupMember(
                    external_user_id=str(value),
                    email=m.get("display") or None,
                )
            )
        return MappedGroup(
            external_id=payload.get("externalId"),
            display_name=str(payload.get("displayName") or "").strip(),
            members=members,
        )
