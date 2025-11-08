"""Settings dialog for configuring the Home Assistant tray widget."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List

from PyQt6 import QtCore, QtGui, QtWidgets

from .config import WidgetConfig, save_config
from .ha_client import HomeAssistantClient, HomeAssistantError
from .icons import icon_from_bytes, load_domain_icon


@dataclass(slots=True)
class EntityListItem:
    """Representation of an entity shown in the settings dialog."""

    entity_id: str
    friendly_name: str
    icon_name: str
    entity_picture: str
    icon: QtGui.QIcon | None


class SettingsDialog(QtWidgets.QDialog):
    """Dialog that allows managing Home Assistant connection and entities."""

    configuration_changed = QtCore.pyqtSignal(WidgetConfig)

    _ICON_THEME_OPTIONS: list[tuple[str, str]] = [
        ("auto", "Auto detect"),
        ("light", "Light icon"),
        ("dark", "Dark icon"),
    ]

    def __init__(self, config: WidgetConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Home Assistant Widget Settings")
        self.resize(600, 400)

        self._config = config
        self._available_entities: List[EntityListItem] = []
        self._entity_display_map: dict[str, str] = {}
        self._entity_icon_map: dict[str, QtGui.QIcon] = {}
        self._icon_cache: dict[str, QtGui.QIcon] = {}

        self._url_input = QtWidgets.QLineEdit(self._config.base_url)
        self._token_input = QtWidgets.QLineEdit(self._config.api_token)
        self._token_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("Long-lived access token")

        self._http_proxy_input = QtWidgets.QLineEdit(self._config.http_proxy)
        self._https_proxy_input = QtWidgets.QLineEdit(self._config.https_proxy)
        self._icon_theme_select = QtWidgets.QComboBox()
        for value, label in self._ICON_THEME_OPTIONS:
            self._icon_theme_select.addItem(label, value)
        current_theme = self._config.tray_icon_theme or "auto"
        index = self._icon_theme_select.findData(current_theme)
        if index < 0:
            index = 0
        self._icon_theme_select.setCurrentIndex(index)
        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText("Search entities…")
        self._available_list = QtWidgets.QListWidget()
        self._selected_list = QtWidgets.QListWidget()

        self._add_button = QtWidgets.QPushButton("Add →")
        self._remove_button = QtWidgets.QPushButton("← Remove")
        self._refresh_button = QtWidgets.QPushButton("Refresh from Home Assistant")

        self._button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Save
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )

        self._build_layout()
        self._bind_events()
        self._populate_selected()

    # ----- UI Construction -------------------------------------------------

    def _build_layout(self) -> None:
        form = QtWidgets.QFormLayout()
        form.addRow("Instance URL", self._url_input)
        form.addRow("API Token", self._token_input)
        form.addRow("HTTP Proxy", self._http_proxy_input)
        form.addRow("HTTPS Proxy", self._https_proxy_input)
        form.addRow("Tray icon theme", self._icon_theme_select)

        lists_layout = QtWidgets.QHBoxLayout()
        lists_layout.addWidget(self._available_list)

        buttons_layout = QtWidgets.QVBoxLayout()
        buttons_layout.addStretch()
        buttons_layout.addWidget(self._add_button)
        buttons_layout.addWidget(self._remove_button)
        buttons_layout.addStretch()
        lists_layout.addLayout(buttons_layout)

        lists_layout.addWidget(self._selected_list)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self._refresh_button)
        layout.addWidget(self._search_input)
        layout.addLayout(lists_layout)
        layout.addWidget(self._button_box)

        self._available_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self._selected_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)

    # ----- Event Handling --------------------------------------------------

    def _bind_events(self) -> None:
        self._add_button.clicked.connect(self._add_entities)
        self._remove_button.clicked.connect(self._remove_entities)
        self._refresh_button.clicked.connect(self._refresh_entities)
        self._search_input.textChanged.connect(self._apply_search_filter)
        self._button_box.accepted.connect(self._save)
        self._button_box.rejected.connect(self.reject)

    def _populate_selected(self) -> None:
        self._selected_list.clear()
        for entity_id in self._config.entities:
            display_text = self._entity_display_map.get(entity_id, entity_id)
            item = QtWidgets.QListWidgetItem(display_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entity_id)
            icon = self._entity_icon_map.get(entity_id)
            if icon is not None and not icon.isNull():
                item.setIcon(icon)
            self._selected_list.addItem(item)

    def _add_entities(self) -> None:
        for item in self._available_list.selectedItems():
            entity_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if entity_id not in self._config.entities:
                self._config.entities.append(entity_id)
        self._populate_selected()

    def _remove_entities(self) -> None:
        for item in self._selected_list.selectedItems():
            data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            entity_id = str(data) if data else item.text()
            if entity_id in self._config.entities:
                self._config.entities.remove(entity_id)
        self._populate_selected()

    def _refresh_entities(self) -> None:
        client = HomeAssistantClient(
            self._url_input.text(),
            self._token_input.text(),
            proxies=self._current_proxies() or None,
        )
        try:
            states = client.list_entity_states()
        except HomeAssistantError as exc:
            QtWidgets.QMessageBox.critical(self, "Home Assistant", str(exc))
            return

        self._available_entities = []
        self._entity_display_map.clear()
        self._entity_icon_map.clear()

        for state in states:
            entity_id = str(state.get("entity_id") or "").strip()
            if not entity_id:
                continue
            attributes = state.get("attributes") or {}
            friendly_name = str(attributes.get("friendly_name") or entity_id)
            icon_name = str(attributes.get("icon") or "").strip()
            entity_picture = str(attributes.get("entity_picture") or "").strip()
            icon = self._entity_icon(entity_id, entity_picture, icon_name, client)
            entry = EntityListItem(
                entity_id=entity_id,
                friendly_name=friendly_name,
                icon_name=icon_name,
                entity_picture=entity_picture,
                icon=icon,
            )
            self._available_entities.append(entry)
            display_text = f"{friendly_name} ({entity_id})"
            self._entity_display_map[entity_id] = display_text
            if icon is not None and not icon.isNull():
                self._entity_icon_map[entity_id] = icon

        self._apply_search_filter()
        self._populate_selected()

    def _save(self) -> None:
        self._config.base_url = self._url_input.text().strip()
        self._config.api_token = self._token_input.text().strip()
        self._config.http_proxy = self._http_proxy_input.text().strip()
        self._config.https_proxy = self._https_proxy_input.text().strip()
        theme_data = self._icon_theme_select.currentData()
        self._config.tray_icon_theme = str(theme_data) if theme_data else "auto"
        entities: list[str] = []
        for i in range(self._selected_list.count()):
            item = self._selected_list.item(i)
            data = item.data(QtCore.Qt.ItemDataRole.UserRole)
            entity_id = str(data) if data else item.text()
            entities.append(entity_id)
        self._config.entities = entities
        save_config(self._config)
        self.configuration_changed.emit(self._config)
        self.accept()

    def _current_proxies(self) -> dict[str, str]:
        proxies: dict[str, str] = {}
        http_proxy = self._http_proxy_input.text().strip()
        https_proxy = self._https_proxy_input.text().strip()
        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        return proxies

    def _apply_search_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        self._available_list.clear()
        for entity in self._available_entities:
            friendly_lower = entity.friendly_name.lower()
            entity_lower = entity.entity_id.lower()
            if query and query not in friendly_lower and query not in entity_lower:
                continue
            display_text = f"{entity.friendly_name} ({entity.entity_id})"
            item = QtWidgets.QListWidgetItem(display_text)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entity.entity_id)
            if entity.icon is not None and not entity.icon.isNull():
                item.setIcon(entity.icon)
            self._available_list.addItem(item)

    def _entity_icon(
        self,
        entity_id: str,
        entity_picture: str,
        icon_name: str,
        client: HomeAssistantClient,
    ) -> QtGui.QIcon | None:
        if entity_picture:
            cache_key = f"api:{client.base_url}:{entity_picture}"
            icon = self._cached_icon(
                cache_key, lambda: icon_from_bytes(client.fetch_entity_picture(entity_picture))
            )
            if icon is not None:
                return icon
        if icon_name:
            cache_key = f"api:{client.base_url}:{icon_name}"
            icon = self._cached_icon(
                cache_key, lambda: icon_from_bytes(client.fetch_icon(icon_name))
            )
            if icon is not None:
                return icon
        return self._resource_icon(entity_id)

    def _resource_icon(self, entity_id: str) -> QtGui.QIcon | None:
        domain, _, _ = entity_id.partition(".")
        cache_key = f"resource:{domain}" if domain else f"resource:{entity_id}"
        icon = self._icon_cache.get(cache_key)
        if icon is None:
            icon = load_domain_icon(entity_id)
            self._icon_cache[cache_key] = icon
        if icon.isNull():
            return None
        return icon

    def _cached_icon(
        self, cache_key: str, loader: Callable[[], QtGui.QIcon | None]
    ) -> QtGui.QIcon | None:
        icon = self._icon_cache.get(cache_key)
        if icon is not None:
            return None if icon.isNull() else icon
        try:
            icon = loader()
        except HomeAssistantError:
            icon = None
        if icon is None:
            icon = QtGui.QIcon()
        self._icon_cache[cache_key] = icon
        return None if icon.isNull() else icon


__all__ = ["SettingsDialog"]
