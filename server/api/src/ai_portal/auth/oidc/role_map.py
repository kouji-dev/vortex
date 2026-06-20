from __future__ import annotations
from collections.abc import Sequence

_ROLE_PRIORITY = ("owner", "admin", "member", "viewer")

def map_groups_to_role(groups: Sequence[str], mapping: dict[str, str], default: str = "member") -> str:
    matched = [mapping[g] for g in groups if g in mapping and mapping[g] in _ROLE_PRIORITY]
    return min(matched, key=_ROLE_PRIORITY.index) if matched else default
