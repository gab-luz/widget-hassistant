"""HTTP client for interacting with Home Assistant."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

import requests


class HomeAssistantError(RuntimeError):
    """Raised when an API call to Home Assistant fails."""


@dataclass(frozen=True)
class EntityState:
    """Container describing a Home Assistant entity."""

    entity_id: str
    friendly_name: str
    icon: str | None = None


class HomeAssistantClient:
    """Minimal client to interact with the Home Assistant REST API."""

    def __init__(self, base_url: str, token: str, *, proxies: dict[str, str] | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token.strip()
        self._proxies = proxies

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def validate(self) -> None:
        """Ensure the configuration is usable by pinging the API."""
        try:
            response = requests.get(
                f"{self.base_url}/api/config",
                headers=self._headers,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError("Failed to connect to Home Assistant") from exc
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Failed to connect to Home Assistant: {response.status_code} {response.text}"
            )

    def list_entities(self) -> List[EntityState]:
        """Return available entities with metadata."""
        try:
            response = requests.get(
                f"{self.base_url}/api/states",
                headers=self._headers,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError("Unable to list entities") from exc
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Unable to list entities: {response.status_code} {response.text}"
            )
        data = response.json()
        entities: List[EntityState] = []
        for item in data:
            entity_id = item.get("entity_id")
            if not entity_id:
                continue
            attributes = item.get("attributes", {})
            friendly_name = attributes.get("friendly_name", entity_id)
            icon = attributes.get("icon")
            entities.append(EntityState(entity_id, friendly_name, icon))
        entities.sort(key=lambda state: state.friendly_name.lower())
        return entities

    def get_entity_states(self, entity_ids: Iterable[str]) -> Dict[str, EntityState]:
        """Return metadata for a subset of entities."""

        ids = {entity_id for entity_id in entity_ids if entity_id}
        if not ids:
            return {}

        try:
            response = requests.get(
                f"{self.base_url}/api/states",
                headers=self._headers,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError("Unable to load entity metadata") from exc
        if response.status_code != 200:
            raise HomeAssistantError(
                f"Unable to load entity metadata: {response.status_code} {response.text}"
            )

        results: Dict[str, EntityState] = {}
        for item in response.json():
            entity_id = item.get("entity_id")
            if entity_id not in ids:
                continue
            attributes = item.get("attributes", {})
            friendly_name = attributes.get("friendly_name", entity_id)
            icon = attributes.get("icon")
            results[entity_id] = EntityState(entity_id, friendly_name, icon)

        for missing in ids - results.keys():
            results[missing] = EntityState(missing, missing, None)

        return results

    def toggle_entity(self, entity_id: str) -> None:
        """Trigger the toggle service for the provided entity."""
        domain = entity_id.split(".", 1)[0]
        try:
            response = requests.post(
                f"{self.base_url}/api/services/{domain}/toggle",
                headers=self._headers,
                json={"entity_id": entity_id},
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError(f"Failed to toggle {entity_id}") from exc
        if response.status_code not in (200, 201):
            raise HomeAssistantError(
                f"Failed to toggle {entity_id}: {response.status_code} {response.text}"
            )

    def call_service(self, domain: str, service: str, **data) -> None:
        try:
            response = requests.post(
                f"{self.base_url}/api/services/{domain}/{service}",
                headers=self._headers,
                json=data,
                timeout=10,
                proxies=self._proxies,
            )
        except requests.RequestException as exc:
            raise HomeAssistantError(f"Failed to call {domain}.{service}") from exc
        if response.status_code not in (200, 201):
            raise HomeAssistantError(
                f"Failed to call {domain}.{service}: {response.status_code} {response.text}"
            )


def format_entities(entities: Iterable[EntityState]) -> List[str]:
    """Return entity IDs sorted by friendly name."""
    return [state.entity_id for state in sorted(entities, key=lambda state: state.friendly_name.lower())]


__all__ = [
    "HomeAssistantClient",
    "HomeAssistantError",
    "EntityState",
    "format_entities",
]
