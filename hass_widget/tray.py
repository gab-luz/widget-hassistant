"""System tray widget for controlling Home Assistant entities."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

from PyQt6 import QtGui, QtWidgets

from .config import WidgetConfig
from .ha_client import EntityState, HomeAssistantClient, HomeAssistantError
from .settings import SettingsDialog


ICON_DIR = Path(__file__).resolve().parent / "resources"
LIGHT_ICON = ICON_DIR / "home-assistant-light.svg"
DARK_ICON = ICON_DIR / "home-assistant-dark.svg"


class TrayIcon(QtWidgets.QSystemTrayIcon):
    """Tray icon that exposes Home Assistant entities as menu actions."""

    def __init__(self, config: WidgetConfig, app: QtWidgets.QApplication) -> None:
        super().__init__(QtGui.QIcon(), parent=app)
        self._app = app
        self._config = config
        self._menu = QtWidgets.QMenu()
        self.setContextMenu(self._menu)
        self.setToolTip("Home Assistant")
        self.activated.connect(self._on_activated)
        self._entity_labels: Dict[str, str] = {}

        self._light_icon = QtGui.QIcon(str(LIGHT_ICON)) if LIGHT_ICON.exists() else QtGui.QIcon()
        self._dark_icon = QtGui.QIcon(str(DARK_ICON)) if DARK_ICON.exists() else QtGui.QIcon()
        self._apply_theme_icon()

        palette_changed = getattr(self._app, "paletteChanged", None)
        if palette_changed is not None:
            palette_changed.connect(self._apply_theme_icon)  # type: ignore[attr-defined]

        self._settings_action = self._menu.addAction("Settings…")
        self._settings_action.triggered.connect(self._open_settings)
        self._menu.addSeparator()
        self._exit_action = self._menu.addAction("Quit")
        self._exit_action.triggered.connect(self._quit)

        self.update_entities()

    # ----- Menu construction ------------------------------------------------

    def update_entities(self) -> None:
        """Rebuild the context menu with the configured entities."""
        # Remove previous entity actions (everything above Settings)
        for action in list(self._menu.actions()):
            if action not in (self._settings_action, self._exit_action):
                self._menu.removeAction(action)

        self._entity_labels.clear()

        if not self._config.entities:
            self._insert_placeholder("No entities configured")
            return

        if not self._config.base_url or not self._config.api_token:
            self._insert_placeholder("Configure Home Assistant in Settings")
            return

        client = HomeAssistantClient(
            self._config.base_url,
            self._config.api_token,
            proxies=self._config.build_proxies(),
        )
        try:
            metadata = client.get_entity_states(self._config.entities)
        except HomeAssistantError as exc:
            self._insert_placeholder("Failed to load entities")
            self.showMessage(
                "Home Assistant",
                str(exc),
                QtWidgets.QSystemTrayIcon.MessageIcon.Warning,
            )
            return

        inserted = False
        for entity_id in self._config.entities:
            info: EntityState | None = metadata.get(entity_id)
            label = info.friendly_name if info else entity_id
            action = QtGui.QAction(label, self._menu)
            action.setToolTip(entity_id)
            icon = self._resolve_entity_icon(info.icon if info else None)
            if icon is not None and not icon.isNull():
                action.setIcon(icon)
            action.triggered.connect(lambda checked=False, e=entity_id: self._toggle_entity(e))
            self._menu.insertAction(self._settings_action, action)
            self._entity_labels[entity_id] = label
            inserted = True

        if inserted:
            self._menu.insertSeparator(self._settings_action)

    # ----- Slots ------------------------------------------------------------

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._config, None)
        dialog.configuration_changed.connect(self._on_configuration_changed)
        dialog.exec()

    def _on_configuration_changed(self, config: WidgetConfig) -> None:
        self._config = config
        self.update_entities()

    def _toggle_entity(self, entity_id: str) -> None:
        client = HomeAssistantClient(
            self._config.base_url,
            self._config.api_token,
            proxies=self._config.build_proxies(),
        )
        try:
            client.toggle_entity(entity_id)
            label = self._entity_labels.get(entity_id, entity_id)
            self.showMessage(
                "Home Assistant",
                f"Toggled {label}",
                QtWidgets.QSystemTrayIcon.MessageIcon.Information,
            )
        except HomeAssistantError as exc:
            self.showMessage("Home Assistant", str(exc), QtWidgets.QSystemTrayIcon.MessageIcon.Warning)

    def _on_activated(self, reason: QtWidgets.QSystemTrayIcon.ActivationReason) -> None:
        if reason == QtWidgets.QSystemTrayIcon.ActivationReason.Trigger:
            self.contextMenu().popup(QtGui.QCursor.pos())

    def _quit(self) -> None:
        self.hide()
        self._app.quit()

    # ----- Helpers ---------------------------------------------------------

    def _insert_placeholder(self, text: str) -> None:
        placeholder = QtGui.QAction(text, self._menu)
        placeholder.setEnabled(False)
        self._menu.insertAction(self._settings_action, placeholder)
        self._menu.insertSeparator(self._settings_action)

    def _apply_theme_icon(self) -> None:
        palette = self._app.palette()
        window_color = palette.color(QtGui.QPalette.ColorRole.Window)
        icon = self._light_icon if window_color.lightness() > 128 else self._dark_icon
        if icon.isNull():
            icon = QtGui.QIcon.fromTheme("home")
        self.setIcon(icon)

    def _resolve_entity_icon(self, icon_name: str | None) -> QtGui.QIcon | None:
        if not icon_name:
            return None

        candidates = [icon_name]
        if ":" in icon_name:
            prefix, name = icon_name.split(":", 1)
            candidates.extend(
                filter(
                    None,
                    {
                        name,
                        name.replace("_", "-"),
                        f"{prefix}-{name}",
                        f"{prefix}-{name.replace('_', '-')}",
                    },
                )
            )
        else:
            candidates.append(icon_name.replace("_", "-"))

        for candidate in candidates:
            icon = QtGui.QIcon.fromTheme(candidate)
            if not icon.isNull():
                return icon

        return None


__all__ = ["TrayIcon"]
