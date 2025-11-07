"""Configuration management for the Home Assistant tray widget."""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List
from urllib.parse import quote

CONFIG_DIR = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "widget-hassistant"
CONFIG_FILE = CONFIG_DIR / "config.json"


@dataclass
class WidgetConfig:
    """Dataclass representing persisted configuration values."""

    base_url: str = ""
    api_token: str = ""
    entities: List[str] = field(default_factory=list)
    proxy_host: str = ""
    proxy_port: str = ""
    proxy_username: str = ""
    proxy_password: str = ""

    def to_dict(self) -> dict:
        proxy = {
            "host": _encode_value(self.proxy_host),
            "port": _encode_value(self.proxy_port),
            "username": _encode_value(self.proxy_username),
            "password": _encode_value(self.proxy_password),
        }
        return {
            "base_url": self.base_url,
            "api_token": self.api_token,
            "entities": self.entities,
            "proxy": proxy,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "WidgetConfig":
        if not data:
            return cls()
        proxy_data = data.get("proxy", {}) if isinstance(data, dict) else {}
        return cls(
            base_url=data.get("base_url", ""),
            api_token=data.get("api_token", ""),
            entities=list(dict.fromkeys(data.get("entities", []))),
            proxy_host=_decode_value(proxy_data.get("host", "")),
            proxy_port=_decode_value(proxy_data.get("port", "")),
            proxy_username=_decode_value(proxy_data.get("username", "")),
            proxy_password=_decode_value(proxy_data.get("password", "")),
        )

    def build_proxies(self) -> dict[str, str] | None:
        """Return a ``requests``-compatible proxy mapping if configured."""

        return build_proxy_map(
            self.proxy_host,
            self.proxy_port,
            self.proxy_username,
            self.proxy_password,
        )


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


def _encode_value(value: str) -> str:
    if not value:
        return ""
    return base64.b64encode(value.encode("utf-8")).decode("utf-8")


def _decode_value(value: str) -> str:
    if not value:
        return ""
    try:
        return base64.b64decode(value.encode("utf-8")).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return ""


def build_proxy_map(
    host: str, port: str, username: str, password: str
) -> dict[str, str] | None:
    """Construct a ``requests`` proxy mapping from raw proxy settings."""

    host = host.strip()
    port = port.strip()
    username = username.strip()
    password = password.strip()

    if not host:
        return None

    auth = ""
    if username:
        user = quote(username, safe="")
        pwd = quote(password, safe="") if password else ""
        auth = f"{user}:{pwd}@" if password else f"{user}@"

    endpoint = host
    if port:
        endpoint = f"{endpoint}:{port}"

    proxy_url = f"http://{auth}{endpoint}"
    return {"http": proxy_url, "https": proxy_url}


__all__ = [
    "WidgetConfig",
    "load_config",
    "save_config",
    "CONFIG_FILE",
    "build_proxy_map",
]
