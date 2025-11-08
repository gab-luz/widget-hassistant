"""Configuration management for the Home Assistant tray widget."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "hassistant-widget"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class WidgetConfig:
    """Dataclass representing persisted configuration values."""

    base_url: str = ""
    api_token: str = ""
    entities: List[str] = field(default_factory=list)
    http_proxy: str = ""
    https_proxy: str = ""
    tray_icon_theme: str = "auto"
    panel_refresh_minutes: int = 5

    def to_dict(self) -> dict:
        return {
            "base_url": self.base_url,
            "api_token": self.api_token,
            "entities": self.entities,
            "http_proxy": self.http_proxy,
            "https_proxy": self.https_proxy,
            "tray_icon_theme": self.tray_icon_theme,
            "panel_refresh_minutes": self.panel_refresh_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "WidgetConfig":
        if not data:
            return cls()
        return cls(
            base_url=data.get("base_url", ""),
            api_token=data.get("api_token", ""),
            entities=list(dict.fromkeys(data.get("entities", []))),
            http_proxy=data.get("http_proxy", ""),
            https_proxy=data.get("https_proxy", ""),
            tray_icon_theme=data.get("tray_icon_theme", "auto") or "auto",
            panel_refresh_minutes=int(data.get("panel_refresh_minutes", 5) or 5),
        )

    def build_proxies(self) -> dict[str, str]:
        """Return a requests-compatible proxies mapping."""

        proxies: dict[str, str] = {}
        if self.http_proxy:
            proxies["http"] = self.http_proxy
        if self.https_proxy:
            proxies["https"] = self.https_proxy
        return proxies


def load_config() -> WidgetConfig:
    """Load configuration from disk."""

    if not CONFIG_FILE.exists():
        return WidgetConfig()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (OSError, json.JSONDecodeError):
        return WidgetConfig()
    return WidgetConfig.from_dict(data)


def save_config(config: WidgetConfig) -> None:
    """Persist configuration to disk."""

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    with CONFIG_FILE.open("w", encoding="utf-8") as fp:
        json.dump(config.to_dict(), fp, indent=2)


__all__ = ["WidgetConfig", "load_config", "save_config", "CONFIG_FILE"]
