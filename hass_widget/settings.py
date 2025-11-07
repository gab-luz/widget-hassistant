"""Settings dialog for configuring the Home Assistant tray widget."""
from __future__ import annotations

from typing import Dict, List

from PyQt6 import QtCore, QtWidgets

from .config import WidgetConfig, build_proxy_map, save_config
from .ha_client import EntityState, HomeAssistantClient, HomeAssistantError


class SettingsDialog(QtWidgets.QDialog):
    """Dialog that allows managing Home Assistant connection and entities."""

    configuration_changed = QtCore.pyqtSignal(WidgetConfig)

    def __init__(self, config: WidgetConfig, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Home Assistant Widget Settings")
        self.resize(600, 400)

        self._config = config
        self._available_entities: List[EntityState] = []
        self._entity_lookup: Dict[str, EntityState] = {}

        self._url_input = QtWidgets.QLineEdit(self._config.base_url)
        self._token_input = QtWidgets.QLineEdit(self._config.api_token)
        self._token_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self._token_input.setPlaceholderText("Long-lived access token")

        self._proxy_host_input = QtWidgets.QLineEdit(self._config.proxy_host)
        self._proxy_port_input = QtWidgets.QLineEdit(self._config.proxy_port)
        self._proxy_username_input = QtWidgets.QLineEdit(self._config.proxy_username)
        self._proxy_password_input = QtWidgets.QLineEdit(self._config.proxy_password)
        self._proxy_password_input.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)

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
        form.addRow("Proxy Host", self._proxy_host_input)
        form.addRow("Proxy Port", self._proxy_port_input)
        form.addRow("Proxy Username", self._proxy_username_input)
        form.addRow("Proxy Password", self._proxy_password_input)

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
        layout.addLayout(lists_layout)
        layout.addWidget(self._button_box)

        self._available_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self._selected_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)

    # ----- Event Handling --------------------------------------------------

    def _bind_events(self) -> None:
        self._add_button.clicked.connect(self._add_entities)
        self._remove_button.clicked.connect(self._remove_entities)
        self._refresh_button.clicked.connect(self._refresh_entities)
        self._button_box.accepted.connect(self._save)
        self._button_box.rejected.connect(self.reject)

    def _populate_selected(self) -> None:
        self._selected_list.clear()
        for entity_id in self._config.entities:
            display = self._entity_lookup.get(entity_id)
            item = QtWidgets.QListWidgetItem(display.friendly_name if display else entity_id)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, entity_id)
            item.setToolTip(entity_id)
            self._selected_list.addItem(item)

    def _add_entities(self) -> None:
        for item in self._available_list.selectedItems():
            entity_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if entity_id not in self._config.entities:
                self._config.entities.append(entity_id)
        self._populate_selected()

    def _remove_entities(self) -> None:
        for item in self._selected_list.selectedItems():
            entity_id = item.data(QtCore.Qt.ItemDataRole.UserRole)
            if entity_id in self._config.entities:
                self._config.entities.remove(entity_id)
        self._populate_selected()

    def _refresh_entities(self) -> None:
        client = HomeAssistantClient(
            self._url_input.text(),
            self._token_input.text(),
            proxies=build_proxy_map(
                self._proxy_host_input.text(),
                self._proxy_port_input.text(),
                self._proxy_username_input.text(),
                self._proxy_password_input.text(),
            ),
        )
        try:
            self._available_entities = client.list_entities()
        except HomeAssistantError as exc:
            QtWidgets.QMessageBox.critical(self, "Home Assistant", str(exc))
            return

        self._available_list.clear()
        for state in self._available_entities:
            item = QtWidgets.QListWidgetItem(state.friendly_name)
            item.setData(QtCore.Qt.ItemDataRole.UserRole, state.entity_id)
            item.setToolTip(state.entity_id)
            self._available_list.addItem(item)

        self._entity_lookup = {state.entity_id: state for state in self._available_entities}
        self._populate_selected()

    def _save(self) -> None:
        self._config.base_url = self._url_input.text().strip()
        self._config.api_token = self._token_input.text().strip()
        self._config.proxy_host = self._proxy_host_input.text().strip()
        self._config.proxy_port = self._proxy_port_input.text().strip()
        self._config.proxy_username = self._proxy_username_input.text().strip()
        self._config.proxy_password = self._proxy_password_input.text().strip()
        self._config.entities = [
            self._selected_list.item(i).data(QtCore.Qt.ItemDataRole.UserRole)
            for i in range(self._selected_list.count())
        ]
        save_config(self._config)
        self.configuration_changed.emit(self._config)
        self.accept()


__all__ = ["SettingsDialog"]
