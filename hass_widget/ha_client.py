"""HTTP client for interacting with Home Assistant."""
from __future__ import annotations

from urllib.parse import quote

import requests
from typing import Iterable, List, Tuple, Dict, Any


class HomeAssistantError(RuntimeError):
    """Raised when an API call to Home Assistant fails."""


class HomeAssistantClient:
    """Minimal client to interact with the Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, proxies: Dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self._proxies = proxies or None

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def validate(self) -> None:
        """Ensure the configuration is usable by pinging the API."""
        response = requests.get(
            f"{self.base_url}/api/config",
            headers=self._headers,
            timeout=10,
            proxies=self._proxies,
        )
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Failed to connect to Home Assistant: {response.status_code} {response.text}"
            )

    def list_entity_states(self) -> List[Dict[str, Any]]:
        """Return a list of all entity states."""
        response = requests.get(
            f"{self.base_url}/api/states",
            headers=self._headers,
            timeout=10,
            proxies=self._proxies,
        )
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Unable to list entities: {response.status_code} {response.text}"
            )
        data = response.json()
        return sorted(
            data,
            key=lambda item: item.get("attributes", {}).get("friendly_name", item.get("entity_id")),
        )

    def list_entities(self) -> List[Tuple[str, str]]:
        """Return entity IDs and friendly names sorted alphabetically."""
        entities: List[Tuple[str, str]] = []
        for state in self.list_entity_states():
            entity_id = state.get("entity_id")
            if not entity_id:
                continue
            attributes = state.get("attributes") or {}
            friendly_name = attributes.get("friendly_name") or entity_id
            entities.append((entity_id, str(friendly_name)))
        return entities

    def toggle_entity(self, entity_id: str) -> None:
        """Trigger the toggle service for the provided entity."""
        domain = entity_id.split(".", 1)[0]
        response = requests.post(
            f"{self.base_url}/api/services/{domain}/toggle",
            headers=self._headers,
            json={"entity_id": entity_id},
            timeout=10,
            proxies=self._proxies,
        )
        if response.status_code not in (200, 201):
            raise HomeAssistantError(
                f"Failed to toggle {entity_id}: {response.status_code} {response.text}"
            )

    def call_service(self, domain: str, service: str, **data) -> None:
        response = requests.post(
            f"{self.base_url}/api/services/{domain}/{service}",
            headers=self._headers,
            json=data,
            timeout=10,
            proxies=self._proxies,
        )
        if response.status_code not in (200, 201):
            raise HomeAssistantError(
                f"Failed to call {domain}.{service}: {response.status_code} {response.text}"
            )

    def list_notifications(self) -> List[Dict[str, Any]]:
        """Return the list of persistent notifications."""

        response = requests.get(
            f"{self.base_url}/api/persistent_notification",
            headers=self._headers,
            timeout=10,
            proxies=self._proxies,
        )
        if response.status_code not in (200, 201):
            raise HomeAssistantError(
                f"Failed to fetch notifications: {response.status_code} {response.text}"
            )
        data = response.json() or {}
        if isinstance(data, list):
            notifications = data
        else:
            notifications = data.get("notifications")
        if isinstance(notifications, list):
            return [n for n in notifications if isinstance(n, dict)]
        return []

    def fetch_icon(self, icon: str) -> bytes:
        """Fetch a Material Design icon defined in Home Assistant attributes."""
        icon = icon.strip()
        if not icon:
            raise HomeAssistantError("Icon name is empty.")
        encoded_icon = quote(icon, safe="")
        try:
            response = requests.get(
                f"{self.base_url}/api/icon/{encoded_icon}",
                headers=self._headers,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError(f"Failed to fetch icon {icon!r}: {exc}") from exc
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Failed to fetch icon {icon}: {response.status_code} {response.text}"
            )
        return response.content

    def fetch_entity_picture(self, entity_picture: str) -> bytes:
        """Fetch the binary contents of an entity picture."""
        entity_picture = entity_picture.strip()
        if not entity_picture:
            raise HomeAssistantError("Entity picture path is empty.")
        if entity_picture.startswith("http://") or entity_picture.startswith("https://"):
            url = entity_picture
        else:
            url = f"{self.base_url}{entity_picture}"
        try:
            response = requests.get(
                url,
                headers=self._headers,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError(f"Failed to fetch entity picture {entity_picture!r}: {exc}") from exc
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Failed to fetch entity picture {entity_picture}: {response.status_code} {response.text}"
            )
        return response.content


def format_entities(entities: Iterable[Tuple[str, str]]) -> List[str]:
    """Return entity IDs sorted by friendly name."""
    return [entity_id for entity_id, _ in sorted(entities, key=lambda pair: pair[1].lower())]


__all__ = [
    "HomeAssistantClient",
    "HomeAssistantError",
    "format_entities",
]
