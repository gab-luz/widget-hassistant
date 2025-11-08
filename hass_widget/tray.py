"""System tray widget for controlling Home Assistant entities."""
from __future__ import annotations

from typing import Any, Callable

import darkdetect
from PyQt6 import QtCore, QtGui, QtWidgets

from .config import WidgetConfig
from .ha_client import HomeAssistantClient, HomeAssistantError
from .icons import get_resource_path, icon_from_bytes, load_domain_icon
from .settings import SettingsDialog


class TrayIcon(QtWidgets.QSystemTrayIcon):
    """Tray icon that exposes Home Assistant entities as menu actions."""

    def __init__(self, config: WidgetConfig, app: QtWidgets.QApplication) -> None:
        if darkdetect.isDark():
            icon = QtGui.QIcon(get_resource_path("home-assistant-dark.svg"))
        else:
            icon = QtGui.QIcon(get_resource_path("home-assistant-light.svg"))

        super().__init__(icon, parent=app)
        self._app = app
        self._config = config
        self._menu = QtWidgets.QMenu()
        self.setContextMenu(self._menu)
        self.setToolTip("Home Assistant")
        self.activated.connect(self._on_activated)

        self._settings_dialog: SettingsDialog | None = None

        self._settings_action = self._menu.addAction("Settings…")
        self._settings_action.triggered.connect(self._open_settings)
        self._menu.addSeparator()
        self._exit_action = self._menu.addAction("Quit")
        self._exit_action.triggered.connect(self._quit)

        self._known_notifications: set[str] = set()
        self._notification_timer = QtCore.QTimer(self)
        self._notification_timer.setInterval(30_000)
        self._notification_timer.timeout.connect(self._check_notifications)
        self._notification_timer.start()

        self._icon_cache: dict[str, QtGui.QIcon] = {}
        self._entity_states: dict[str, dict[str, Any]] = {}

        self.update_entities()
        self._initialize_notifications()
        QtCore.QTimer.singleShot(0, self._check_notifications)

    # ----- Menu construction ------------------------------------------------

    def update_entities(self) -> None:
        """Rebuild the context menu with the configured entities."""
        # Remove previous entity actions (everything above Settings)
        for action in list(self._menu.actions()):
            if action not in (self._settings_action, self._exit_action):
                self._menu.removeAction(action)

        if self._config.entities:
            client: HomeAssistantClient | None = None
            try:
                client = self._create_client()
                all_states = client.list_entity_states()
            except HomeAssistantError:
                entity_map = {}
                self._entity_states = {}
                client = None
            else:
                entity_map = {}
                state_map: dict[str, dict[str, Any]] = {}
                for state in all_states:
                    entity_id = state.get("entity_id")
                    if not entity_id:
                        continue
                    attributes = state.get("attributes") or {}
                    friendly_name = attributes.get("friendly_name") or entity_id
                    entity_map[entity_id] = str(friendly_name)
                    state_map[entity_id] = state
                self._entity_states = state_map

            for entity_id in self._config.entities:
                friendly_name = entity_map.get(entity_id, entity_id)
                icon = self._entity_icon(entity_id, client)
                if icon is not None:
                    action = QtGui.QAction(icon, friendly_name, self._menu)
                else:
                    action = QtGui.QAction(friendly_name, self._menu)
                action.triggered.connect(lambda checked=False, e=entity_id: self._toggle_entity(e))
                self._menu.insertAction(self._settings_action, action)
            self._menu.insertSeparator(self._settings_action)
        else:
            self._entity_states = {}
            placeholder = QtGui.QAction("No entities configured", self._menu)
            placeholder.setEnabled(False)
            self._menu.insertAction(self._settings_action, placeholder)
            self._menu.insertSeparator(self._settings_action)

    # ----- Slots ------------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, None)
        dialog.configuration_changed.connect(self._on_configuration_changed)
        dialog.exec()

    def _on_configuration_changed(self, config: WidgetConfig) -> None:
        self._config = config
        self._icon_cache.clear()
        self.update_entities()
        self._initialize_notifications()
        self._check_notifications()

    def _toggle_entity(self, entity_id: str) -> None:
        try:
            client = self._create_client()
        except HomeAssistantError as exc:
            self.showMessage("Home Assistant", str(exc), QtWidgets.QSystemTrayIcon.MessageIcon.Warning)
            return
        try:
            client.toggle_entity(entity_id)
            self.showMessage("Home Assistant", f"Toggled {entity_id}", QtWidgets.QSystemTrayIcon.MessageIcon.Information)
        except HomeAssistantError as exc:
            self.showMessage("Home Assistant", str(exc), QtWidgets.QSystemTrayIcon.MessageIcon.Warning)

    def _on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.contextMenu().popup(QtGui.QCursor.pos())

    def _quit(self) -> None:
        self.hide()
        self._app.quit()

    def _create_client(self) -> HomeAssistantClient:
        if not self._config.base_url or not self._config.api_token:
            raise HomeAssistantError("Home Assistant URL or token is not configured.")
        proxies = self._config.build_proxies()
        return HomeAssistantClient(
            self._config.base_url,
            self._config.api_token,
            proxies=proxies or None,
        )

    def _initialize_notifications(self) -> None:
        self._known_notifications.clear()
        if not self._config.base_url or not self._config.api_token:
            return
        try:
            client = self._create_client()
            notifications = client.list_notifications()
        except HomeAssistantError:
            return
        for notification in notifications:
            notification_id = str(notification.get("notification_id", "")).strip()
            if notification_id:
                self._known_notifications.add(notification_id)

    def _check_notifications(self) -> None:
        if not self._config.base_url or not self._config.api_token:
            return
        try:
            client = self._create_client()
            notifications = client.list_notifications()
        except HomeAssistantError:
            return

        current_ids: set[str] = set()
        for notification in notifications:
            notification_id = str(notification.get("notification_id", "")).strip()
            if not notification_id:
                continue
            current_ids.add(notification_id)
            if notification_id in self._known_notifications:
                continue
            title = str(notification.get("title") or "Home Assistant")
            message = str(notification.get("message") or "")
            self.showMessage(title, message, QtWidgets.QSystemTrayIcon.MessageIcon.Information)
            self._known_notifications.add(notification_id)

        if current_ids:
            self._known_notifications.intersection_update(current_ids)
        else:
            self._known_notifications.clear()

    def _entity_icon(self, entity_id: str, client: HomeAssistantClient | None) -> QtGui.QIcon | None:
        icon = None
        if client is not None:
            icon = self._entity_icon_from_api(entity_id, client)
        if icon is None:
            icon = self._entity_icon_from_resources(entity_id)
        return icon

    def _entity_icon_from_api(
        self, entity_id: str, client: HomeAssistantClient
    ) -> QtGui.QIcon | None:
        state = self._entity_states.get(entity_id)
        if not state:
            return None
        attributes = state.get("attributes") or {}
        entity_picture = str(attributes.get("entity_picture") or "").strip()
        icon_name = str(attributes.get("icon") or "").strip()

        if entity_picture:
            cache_key = f"api:{self._config.base_url}:{entity_picture}"
            return self._cached_icon(
                cache_key,
                lambda: icon_from_bytes(client.fetch_entity_picture(entity_picture)),
            )
        if icon_name:
            cache_key = f"api:{self._config.base_url}:{icon_name}"
            return self._cached_icon(
                cache_key, lambda: icon_from_bytes(client.fetch_icon(icon_name))
            )
        return None

    def _entity_icon_from_resources(self, entity_id: str) -> QtGui.QIcon | None:
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



__all__ = ["TrayIcon"]
