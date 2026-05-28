"""SCIM preset attribute mappers.

A preset translates an inbound SCIM payload (dict, already validated by
scim2-models) into a flat :class:`MappedUser` or :class:`MappedGroup` carrying
the fields the control plane needs to write.

Generic = raw SCIM core attrs. Okta / Entra override the bits where those
vendors put data in non-standard places (Entra emits ``externalId`` from
``objectId``; Okta passes group memberships under different array shapes).
"""

from __future__ import annotations

from ai_portal.scim.presets.base import (
    MappedGroup,
    MappedGroupMember,
    MappedUser,
    Preset,
)
from ai_portal.scim.presets.entra import EntraPreset
from ai_portal.scim.presets.generic import GenericPreset
from ai_portal.scim.presets.okta import OktaPreset

_REGISTRY: dict[str, Preset] = {
    "generic": GenericPreset(),
    "okta": OktaPreset(),
    "entra": EntraPreset(),
}


def get_preset(name: str) -> Preset:
    """Lookup a preset by name. Falls back to ``generic`` when unknown."""
    return _REGISTRY.get(name) or _REGISTRY["generic"]


__all__ = [
    "EntraPreset",
    "GenericPreset",
    "MappedGroup",
    "MappedGroupMember",
    "MappedUser",
    "OktaPreset",
    "Preset",
    "get_preset",
]
