"""Helpers for loading icons used throughout the widget."""
from __future__ import annotations

from pathlib import Path

from PyQt6 import QtGui


_RESOURCE_DIR = Path(__file__).parent / "resources"


DOMAIN_ICON_FILES: dict[str, str] = {
    "automation": "entity-script.svg",
    "binary_sensor": "entity-sensor.svg",
    "button": "entity-button.svg",
    "climate": "entity-climate.svg",
    "cover": "entity-cover.svg",
    "fan": "entity-fan.svg",
    "input_boolean": "entity-switch.svg",
    "light": "entity-light.svg",
    "lock": "entity-lock.svg",
    "media_player": "entity-media-player.svg",
    "scene": "entity-scene.svg",
    "script": "entity-script.svg",
    "sensor": "entity-sensor.svg",
    "switch": "entity-switch.svg",
}

DEFAULT_ENTITY_ICON = "entity-generic.svg"


def get_resource_path(name: str) -> str:
    """Return the absolute path for a named resource."""

    return str(_RESOURCE_DIR / name)


def load_resource_icon(name: str) -> QtGui.QIcon:
    """Load a QIcon from the resources directory."""

    icon = QtGui.QIcon(get_resource_path(name))
    if icon.isNull():
        return QtGui.QIcon()
    return icon


def domain_icon_name(entity_id: str) -> str:
    """Return the icon file name for a given entity ID domain."""

    domain, _, _ = entity_id.partition(".")
    return DOMAIN_ICON_FILES.get(domain, DEFAULT_ENTITY_ICON)


def load_domain_icon(entity_id: str) -> QtGui.QIcon:
    """Load a default icon for the provided entity ID."""

    return load_resource_icon(domain_icon_name(entity_id))


def icon_from_bytes(data: bytes) -> QtGui.QIcon | None:
    """Build a QIcon from raw image bytes."""

    pixmap = QtGui.QPixmap()
    if not pixmap.loadFromData(data):
        return None
    return QtGui.QIcon(pixmap)


__all__ = [
    "DEFAULT_ENTITY_ICON",
    "DOMAIN_ICON_FILES",
    "domain_icon_name",
    "get_resource_path",
    "icon_from_bytes",
    "load_domain_icon",
    "load_resource_icon",
]

