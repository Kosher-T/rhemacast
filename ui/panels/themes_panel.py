"""
ui/panels/themes_panel.py

Vertical theme selector panel.
Dynamically loads theme JSON files from themes/ directory.
Clicking a theme applies it to the live display.
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_BODY_STYLE,
    CYAN_400, SLATE_300, SLATE_500, WHITE, BORDER_SUBTLE
)

logger = logging.getLogger(__name__)


class ThemeCard(QFrame):
    """A single theme card in the vertical list."""

    theme_selected = pyqtSignal(str)  # single-click
    theme_double_clicked = pyqtSignal(str)  # double-click

    def __init__(self, theme: dict, parent=None):
        super().__init__(parent)
        self.theme_name = theme["name"]
        self._active = False

        # Extract accent color from container border or use a default
        accent = "#3b82f6"
        container = theme.get("container", {})
        border = container.get("border", "")
        if "rgba(" in border:
            # Pull the color from the border definition
            try:
                parts = border.split("solid")[1].strip().rstrip(")")
                accent = parts
            except (IndexError, ValueError):
                pass

        bg = container.get("background", "rgba(15, 23, 42, 0.6)")

        self.setStyleSheet(f"""
            QFrame {{
                background: rgba(255, 255, 255, 3);
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: rgba(255, 255, 255, 8);
                border-color: rgba(255, 255, 255, 20);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # Color swatch
        swatch = QLabel()
        swatch.setFixedSize(28, 28)
        swatch.setStyleSheet(f"""
            background: {bg};
            border: 2px solid {accent};
            border-radius: 6px;
        """)
        layout.addWidget(swatch)

        # Text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(2)

        name_label = QLabel(theme.get("label", theme["name"]))
        name_label.setStyleSheet(f"color: {WHITE}; font-size: 11px; font-weight: 700; background: transparent;")
        text_layout.addWidget(name_label)

        desc_label = QLabel(theme.get("description", ""))
        desc_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; background: transparent;")
        text_layout.addWidget(desc_label)

        layout.addLayout(text_layout)
        layout.addStretch()

    def set_active(self, active: bool):
        self._active = active
        if active:
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba(34, 211, 238, 8);
                    border: 1px solid rgba(34, 211, 238, 30);
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba(255, 255, 255, 3);
                    border: 1px solid {BORDER_SUBTLE};
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    background: rgba(255, 255, 255, 8);
                    border-color: rgba(255, 255, 255, 20);
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.theme_selected.emit(self.theme_name)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.theme_double_clicked.emit(self.theme_name)
        super().mouseDoubleClickEvent(event)


class ThemesPanel(QWidget):
    """Vertical theme selector panel — loads themes dynamically from themes/ directory."""

    # Emitted when operator selects a theme (theme name)
    theme_changed = pyqtSignal(str)
    theme_double_clicked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._current_theme = "default"
        self._cards: dict[str, ThemeCard] = {}

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(6)

        self._load_themes()

        self._layout.addStretch()

    def _load_themes(self):
        """Load all themes from the theme loader and create cards."""
        from core.theme_loader import get_all_themes

        themes = get_all_themes()
        for name, theme in themes.items():
            card = ThemeCard(theme)
            card.theme_selected.connect(self._on_theme_selected)
            card.theme_double_clicked.connect(self._on_theme_double_clicked)
            self._layout.addWidget(card)
            self._cards[name] = card

        # Load saved theme from settings
        from core.database import get_setting
        saved_theme = get_setting("display.last_theme", "default")
        if saved_theme in self._cards:
            self._cards[saved_theme].set_active(True)
            self._current_theme = saved_theme

    def _on_theme_selected(self, name: str):
        if name == self._current_theme:
            return

        # Update active states
        if self._current_theme in self._cards:
            self._cards[self._current_theme].set_active(False)
        self._cards[name].set_active(True)
        self._current_theme = name

        # Save theme to settings
        from core.database import set_setting
        set_setting("display.last_theme", name)

        self.theme_changed.emit(name)
        logger.info(f"Theme changed to: {name}")

    def _on_theme_double_clicked(self, name: str):
        # Ensure the theme is selected (set active)
        if name != self._current_theme:
            if self._current_theme in self._cards:
                self._cards[self._current_theme].set_active(False)
            self._cards[name].set_active(True)
            self._current_theme = name

            # Save theme to settings
            from core.database import set_setting
            set_setting("display.last_theme", name)

            self.theme_changed.emit(name)

        self.theme_double_clicked.emit(name)
        logger.info(f"Theme double-clicked: {name}")

    @property
    def current_theme(self) -> str:
        return self._current_theme
