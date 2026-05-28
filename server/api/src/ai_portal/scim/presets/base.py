"""Preset base — shared dataclasses + protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class MappedUser:
    """Vendor-neutral User payload extracted from a SCIM resource."""

    external_id: str | None
    user_name: str
    email: str
    name: str | None = None
    active: bool = True
    locale: str | None = None


@dataclass(frozen=True)
class MappedGroupMember:
    """One member ref inside a SCIM Group payload."""

    # Stable IdP identifier — Entra ``objectId``, Okta user id, generic ``value``.
    external_user_id: str
    email: str | None = None


@dataclass(frozen=True)
class MappedGroup:
    """Vendor-neutral Group payload extracted from a SCIM resource."""

    external_id: str | None
    display_name: str
    members: list[MappedGroupMember] = field(default_factory=list)


class Preset(Protocol):
    """Translate raw SCIM dicts into :class:`MappedUser` / :class:`MappedGroup`."""

    name: str

    def map_user(self, payload: dict) -> MappedUser: ...
    def map_group(self, payload: dict) -> MappedGroup: ...
