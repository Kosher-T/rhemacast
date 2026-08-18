"""
ui/widgets/theme_quick_editor.py

Popup widget for quickly editing a theme without opening the full designer.
Two-column layout: properties panel on the left, live preview on the right.
"""

import copy

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.widgets.theme_properties_panel import ThemePropertiesPanel
from ui.widgets.theme_preview import ThemePreview
from ui.styles import BLUE_500
import core.theme_loader


# ─── Styles ──────────────────────────────────────────────────────────────────

_POPUP_STYLE = (
    "QWidget {"
    "  background: rgba(15, 23, 42, 0.97);"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 16px;"
    "  color: #f8fafc;"
    "  font-family: 'Nunito', sans-serif;"
    "  font-size: 11px;"
    "}"
)

_TITLE_BAR_STYLE = (
    "QFrame {"
    "  background: transparent;"
    "  border-bottom: 1px solid rgba(255, 255, 255, 0.06);"
    "}"
)

_TITLE_LABEL_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #f8fafc;"
    "font-size: 12px;"
    "font-weight: 700;"
)

_BADGE_STYLE = (
    "background: rgba(6, 182, 212, 0.15);"
    "color: #22d3ee;"
    "border: 1px solid rgba(6, 182, 212, 0.3);"
    "border-radius: 4px;"
    "padding: 1px 8px;"
    "font-size: 10px;"
    "font-weight: 700;"
)

_ICON_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #22d3ee;"
    "font-size: 14px;"
)

_BTN_GHOST = (
    "QPushButton {"
    "  background: transparent;"
    "  color: #94a3b8;"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 4px;"
    "  padding: 4px 12px;"
    "  font-size: 10px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  color: #f8fafc;"
    "}"
)

_BTN_PRIMARY = (
    "QPushButton {"
    f"  background: {BLUE_500};"
    "  color: #ffffff;"
    "  border: none;"
    "  border-radius: 4px;"
    "  padding: 4px 16px;"
    "  font-size: 10px;"
    "  font-weight: 700;"
    "}"
    "QPushButton:hover {"
    "  background: #2563eb;"
    "}"
    "QPushButton:pressed {"
    "  background: #1d4ed8;"
    "}"
)

_BTN_EXPAND = (
    "QPushButton {"
    "  background: rgba(6, 182, 212, 0.15);"
    "  color: #22d3ee;"
    "  border: 1px solid rgba(6, 182, 212, 0.3);"
    "  border-radius: 4px;"
    "  padding: 4px 14px;"
    "  font-size: 10px;"
    "  font-weight: 700;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(6, 182, 212, 0.25);"
    "}"
    "QPushButton:pressed {"
    "  background: rgba(6, 182, 212, 0.35);"
    "}"
)

_BTN_CLOSE = (
    "QPushButton {"
    "  background: transparent;"
    "  color: #64748b;"
    "  border: none;"
    "  border-radius: 4px;"
    "  padding: 4px 8px;"
    "  font-size: 13px;"
    "  font-weight: 700;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(239, 68, 68, 0.15);"
    "  color: #ef4444;"
    "}"
)

_DIVIDER_STYLE = (
    "background: rgba(255, 255, 255, 0.06);"
    "border: none;"
)


# ─── Widget ──────────────────────────────────────────────────────────────────


class ThemeQuickEditor(QWidget):
    """Popup editor for quick theme adjustments with live preview."""

    edit_full_requested = pyqtSignal(str)
    theme_saved = pyqtSignal(str)

    def __init__(self, theme_name: str, parent=None):
        super().__init__(parent)
        self._theme_name = theme_name
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
        )
        self.setFixedSize(1280, 720)
        self.setStyleSheet(_POPUP_STYLE)

        theme_data = core.theme_loader.get_theme(theme_name)
        self._original_theme = copy.deepcopy(theme_data) if theme_data else {}
        self._working_theme = copy.deepcopy(self._original_theme)

        # ── Root layout ──
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Title bar ──
        title_bar = QFrame()
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet(_TITLE_BAR_STYLE)
        title_bar.setCursor(Qt.CursorShape.SizeAllCursor)

        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(14, 0, 10, 0)
        tb_layout.setSpacing(8)

        # Left: icon + title + badge
        icon_lbl = QLabel("\u2728")
        icon_lbl.setStyleSheet(_ICON_STYLE)
        icon_lbl.setFixedWidth(20)
        tb_layout.addWidget(icon_lbl)

        title_lbl = QLabel("Quick Theme Editor")
        title_lbl.setStyleSheet(_TITLE_LABEL_STYLE)
        tb_layout.addWidget(title_lbl)

        badge = QLabel(theme_name)
        badge.setStyleSheet(_BADGE_STYLE)
        tb_layout.addWidget(badge)

        tb_layout.addStretch()

        # Right: buttons
        btn_edit_full = QPushButton("Edit in Full Designer")
        btn_edit_full.setStyleSheet(_BTN_EXPAND)
        btn_edit_full.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_edit_full.clicked.connect(self._on_edit_full)
        tb_layout.addWidget(btn_edit_full)

        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(_BTN_GHOST)
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._on_reset)
        tb_layout.addWidget(btn_reset)

        btn_save = QPushButton("Save")
        btn_save.setStyleSheet(_BTN_PRIMARY)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._on_save)
        tb_layout.addWidget(btn_save)

        btn_close = QPushButton("\u00d7")
        btn_close.setStyleSheet(_BTN_CLOSE)
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self._on_cancel)
        tb_layout.addWidget(btn_close)

        root.addWidget(title_bar)

        # ── Body: two columns ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left column — properties panel
        left_container = QFrame()
        left_container.setFixedWidth(380)
        left_container.setStyleSheet(
            "QFrame {"
            "  background: transparent;"
            "  border-right: 1px solid rgba(255, 255, 255, 0.06);"
            "}"
        )
        left_layout = QVBoxLayout(left_container)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._props = ThemePropertiesPanel()
        self._props.theme_changed.connect(self._on_theme_changed)
        left_layout.addWidget(self._props)

        body.addWidget(left_container)

        # Right column — preview
        right_container = QFrame()
        right_container.setStyleSheet("QFrame { background: transparent; }")
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(16, 12, 16, 12)
        right_layout.setSpacing(0)

        self._preview = ThemePreview(
            verse_key="popup",
            label="Preview",
            min_width=160,
            max_width=800,
        )
        right_layout.addWidget(self._preview, 1)

        body.addWidget(right_container, 1)

        root.addLayout(body, 1)

        # ── Load theme into panels ──
        self._props.load_theme(self._working_theme)
        self._preview.apply_theme(self._working_theme)

    # ── Slots ──────────────────────────────────────────────────────────────

    def _on_theme_changed(self, theme_dict: dict):
        self._working_theme = theme_dict
        self._preview.apply_theme(theme_dict)

    def _on_save(self):
        core.theme_loader.save_theme(self._theme_name, self._working_theme)
        self.theme_saved.emit(self._theme_name)
        self.close()

    def _on_cancel(self):
        self._working_theme = copy.deepcopy(self._original_theme)
        self._props.load_theme(self._working_theme)
        self._preview.apply_theme(self._working_theme)
        self.close()

    def _on_reset(self):
        fresh = core.theme_loader.get_theme(self._theme_name)
        if fresh is not None:
            self._original_theme = copy.deepcopy(fresh)
            self._working_theme = copy.deepcopy(fresh)
            self._props.load_theme(self._working_theme)
            self._preview.apply_theme(self._working_theme)

    def _on_edit_full(self):
        self.edit_full_requested.emit(self._theme_name)
