"""Trigger source registry — kind → trigger lookup."""

from __future__ import annotations

from ai_portal.workers.triggers.protocol import TriggerSource
from ai_portal.workers.types import TriggerSourceKind


class TriggerNotRegistered(KeyError):
    """Raised when ``get(kind)`` finds no trigger."""


_REG: dict[TriggerSourceKind, TriggerSource] = {}


def register(trigger: TriggerSource) -> None:
    _REG[trigger.kind] = trigger


def get(kind: TriggerSourceKind) -> TriggerSource:
    try:
        return _REG[kind]
    except KeyError as e:
        raise TriggerNotRegistered(str(kind)) from e


def all_triggers() -> list[TriggerSourceKind]:
    return list(_REG.keys())


def clear() -> None:
    _REG.clear()
