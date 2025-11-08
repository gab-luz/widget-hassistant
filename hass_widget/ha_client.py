"""HTTP client for interacting with Home Assistant."""
from __future__ import annotations

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


def format_entities(entities: Iterable[Tuple[str, str]]) -> List[str]:
    """Return entity IDs sorted by friendly name."""
    return [entity_id for entity_id, _ in sorted(entities, key=lambda pair: pair[1].lower())]


__all__ = [
    "HomeAssistantClient",
    "HomeAssistantError",
    "format_entities",
]
