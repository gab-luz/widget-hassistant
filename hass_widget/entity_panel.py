"""Panel UI for browsing and toggling Home Assistant entities."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from PyQt6 import QtCore, QtGui, QtWidgets


@dataclass(slots=True)
class PanelEntity:
    """Representation of an entity shown inside the panel."""

    entity_id: str
    friendly_name: str
    icon: QtGui.QIcon | None = None


class _EntityRow(QtWidgets.QFrame):
    """Single entity row that emits a toggle request when activated."""

    toggle_requested = QtCore.pyqtSignal(str)

    def __init__(self, entity: PanelEntity, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self._entity = entity
        self.setObjectName("entityRow")
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        self._icon_label = QtWidgets.QLabel()
        self._icon_label.setFixedSize(32, 32)
        self._icon_label.setScaledContents(True)
        layout.addWidget(self._icon_label)

        text = f"{entity.friendly_name} ({entity.entity_id})"
        self._name_label = QtWidgets.QLabel(text)
        self._name_label.setWordWrap(True)
        layout.addWidget(self._name_label, 1)

        self._toggle_button = QtWidgets.QPushButton("Toggle")
        self._toggle_button.setObjectName("toggleButton")
        self._toggle_button.clicked.connect(self._emit_toggle)
        layout.addWidget(self._toggle_button)

        self._refresh_icon()

    def _refresh_icon(self) -> None:
        icon = self._entity.icon
        if icon is None or icon.isNull():
            self._icon_label.clear()
            self._icon_label.setPixmap(QtGui.QPixmap())
            return
        pixmap = icon.pixmap(32, 32)
        self._icon_label.setPixmap(pixmap)

    def _emit_toggle(self) -> None:
        self.toggle_requested.emit(self._entity.entity_id)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:  # type: ignore[override]
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._emit_toggle()
        super().mouseReleaseEvent(event)


class EntitiesPanel(QtWidgets.QDialog):
    """Floating panel that lists cached entities with search and fade animation."""

    toggle_requested = QtCore.pyqtSignal(str)

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Home Assistant Entities")
        self.setWindowFlag(QtCore.Qt.WindowType.Tool)
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setModal(False)

        self._all_entities: List[PanelEntity] = []

        self._opacity_effect = QtWidgets.QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity_effect)
        self._fade_animation = QtCore.QPropertyAnimation(self._opacity_effect, b"opacity", self)
        self._fade_animation.setDuration(200)
        self._fade_animation.finished.connect(self._on_fade_finished)
        self._fade_target: float = 1.0

        outer_layout = QtWidgets.QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        self._panel = QtWidgets.QFrame()
        self._panel.setObjectName("panelFrame")
        outer_layout.addWidget(self._panel)

        layout = QtWidgets.QVBoxLayout(self._panel)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setSpacing(12)

        self._search_input = QtWidgets.QLineEdit()
        self._search_input.setPlaceholderText("Search entities…")
        header_layout.addWidget(self._search_input, 1)

        self._close_button = QtWidgets.QPushButton("✕")
        self._close_button.setObjectName("closeButton")
        self._close_button.setFixedSize(28, 28)
        self._close_button.clicked.connect(self.hide_panel)
        header_layout.addWidget(self._close_button)

        layout.addLayout(header_layout)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._scroll, 1)

        self._entries_container = QtWidgets.QWidget()
        self._entries_layout = QtWidgets.QVBoxLayout(self._entries_container)
        self._entries_layout.setContentsMargins(0, 0, 0, 0)
        self._entries_layout.setSpacing(8)
        self._entries_layout.addStretch()
        self._scroll.setWidget(self._entries_container)

        self._placeholder = QtWidgets.QLabel("No entities configured.")
        self._placeholder.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self._placeholder.setObjectName("placeholderLabel")
        self._entries_layout.insertWidget(0, self._placeholder)

        self._search_input.textChanged.connect(self._apply_filter)

        self._apply_stylesheet()
        self.resize(420, 520)

    # ----- Public API -----------------------------------------------------

    def update_entities(self, entities: Iterable[PanelEntity]) -> None:
        """Update the cached entity list displayed in the panel."""

        self._all_entities = list(entities)
        self._apply_filter()

    def show_panel(self) -> None:
        """Show the panel with a fade-in animation."""

        if self.isVisible():
            return
        self._fade_animation.stop()
        self._fade_target = 1.0
        self._opacity_effect.setOpacity(0.0)
        self._fade_animation.setStartValue(0.0)
        self._fade_animation.setEndValue(1.0)
        super().show()
        self.raise_()
        self._fade_animation.start()
        self._search_input.setFocus(QtCore.Qt.FocusReason.ActiveWindowFocusReason)

    def hide_panel(self) -> None:
        """Hide the panel with a fade-out animation."""

        if not self.isVisible():
            return
        self._fade_animation.stop()
        self._fade_target = 0.0
        self._fade_animation.setStartValue(self._opacity_effect.opacity())
        self._fade_animation.setEndValue(0.0)
        self._fade_animation.start()

    # ----- Internal helpers ----------------------------------------------

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not self._all_entities:
            self._show_placeholder("No entities configured.")
            return

        if not query:
            filtered = list(self._all_entities)
        else:
            filtered = [
                entity
                for entity in self._all_entities
                if query in entity.friendly_name.lower() or query in entity.entity_id.lower()
            ]

        if not filtered:
            self._show_placeholder("No matching entities.")
            return

        self._clear_entries()
        for entity in filtered:
            row = _EntityRow(entity)
            row.toggle_requested.connect(self.toggle_requested.emit)
            self._entries_layout.addWidget(row)
        self._entries_layout.addStretch()

    def _show_placeholder(self, text: str) -> None:
        self._clear_entries()
        self._placeholder.setText(text)
        self._placeholder.show()
        self._entries_layout.addWidget(self._placeholder)
        self._entries_layout.addStretch()

    def _clear_entries(self) -> None:
        while self._entries_layout.count():
            item = self._entries_layout.takeAt(0)
            widget = item.widget()
            if widget is not None and widget is not self._placeholder:
                widget.deleteLater()
        self._placeholder.hide()

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            #panelFrame {
                background-color: rgba(36, 38, 45, 230);
                border-radius: 14px;
                color: white;
            }
            #panelFrame QLineEdit {
                padding: 6px 10px;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 50);
                background: rgba(255, 255, 255, 30);
                color: white;
            }
            #panelFrame QLineEdit:focus {
                border-color: rgba(255, 255, 255, 90);
            }
            #closeButton {
                border: none;
                background: transparent;
                font-size: 16px;
                color: white;
            }
            #closeButton:hover {
                color: #ffb3b3;
            }
            #entityRow {
                background-color: rgba(255, 255, 255, 30);
                border-radius: 10px;
            }
            #entityRow:hover {
                background-color: rgba(255, 255, 255, 45);
            }
            #toggleButton {
                padding: 6px 12px;
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 60);
                background: rgba(0, 0, 0, 60);
                color: white;
            }
            #toggleButton:hover {
                background: rgba(0, 0, 0, 90);
            }
            #toggleButton:pressed {
                background: rgba(0, 0, 0, 120);
            }
            #placeholderLabel {
                color: rgba(255, 255, 255, 120);
                padding: 24px 12px;
            }
        """
        )

    def _on_fade_finished(self) -> None:
        if self._fade_target == 0.0:
            super().hide()

    # ----- Qt overrides ---------------------------------------------------

    def closeEvent(self, event: QtGui.QCloseEvent) -> None:  # type: ignore[override]
        self.hide_panel()
        event.ignore()

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:  # type: ignore[override]
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.hide_panel()
            event.accept()
            return
        super().keyPressEvent(event)


__all__ = ["EntitiesPanel", "PanelEntity"]

