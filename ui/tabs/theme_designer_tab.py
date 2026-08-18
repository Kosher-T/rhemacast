"""
ui/tabs/theme_designer_tab.py

Three-column theme designer tab:
  Left  (280px) — ThemePropertiesPanel (elements + container tabs)
  Center (flex) — Three ThemePreview widgets in triangle layout
  Right (300px) — Animations panel + JSON editor

Top toolbar: theme selector combo, name badge, Import/Export/Save/Cancel/Reset.
"""

import copy
import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTextEdit, QComboBox, QStackedWidget, QApplication, QSizePolicy,
    QSplitter,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

from ui.widgets.theme_properties_panel import ThemePropertiesPanel
from ui.widgets.theme_preview import ThemePreview
from ui.widgets.theme_animations_panel import ThemeAnimationsPanel
from ui.widgets.container_editor import ContainerEditor
import core.theme_loader


# ─── Styles ──────────────────────────────────────────────────────────────────

_PANEL_BG = "rgba(15, 23, 42, 0.6)"
_BORDER_SUBTLE = "rgba(255, 255, 255, 0.06)"

_JSON_EDITOR_STYLE = (
    "QTextEdit {"
    "  background: rgba(0, 0, 0, 0.4);"
    "  border: 1px solid rgba(255, 255, 255, 0.06);"
    "  border-radius: 8px;"
    "  color: #e2e8f0;"
    "  font-family: 'Consolas', 'Courier New', monospace;"
    "  font-size: 11px;"
    "  padding: 8px;"
    "  selection-background-color: rgba(59, 130, 246, 0.3);"
    "}"
)

_TOOLBAR_BTN_STYLE = (
    "QPushButton {"
    "  background: transparent;"
    "  color: #94a3b8;"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 6px;"
    "  padding: 5px 12px;"
    "  font-size: 11px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  color: #f8fafc;"
    "}"
)

_TOOLBAR_BTN_PRIMARY = (
    "QPushButton {"
    "  background: #3b82f6;"
    "  color: #ffffff;"
    "  border: none;"
    "  border-radius: 6px;"
    "  padding: 5px 14px;"
    "  font-size: 11px;"
    "  font-weight: 700;"
    "}"
    "QPushButton:hover {"
    "  background: #2563eb;"
    "}"
    "QPushButton:pressed {"
    "  background: #1d4ed8;"
    "}"
)

_TOOLBAR_BTN_SECONDARY = (
    "QPushButton {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  color: #cbd5e1;"
    "  border: 1px solid rgba(255, 255, 255, 0.1);"
    "  border-radius: 6px;"
    "  padding: 5px 12px;"
    "  font-size: 11px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.1);"
    "  color: #f8fafc;"
    "}"
)

_TOOLBAR_BTN_GHOST = (
    "QPushButton {"
    "  background: transparent;"
    "  color: #64748b;"
    "  border: none;"
    "  border-radius: 6px;"
    "  padding: 5px 10px;"
    "  font-size: 11px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.05);"
    "  color: #94a3b8;"
    "}"
)

_TAB_BTN_ACTIVE = (
    "QPushButton {"
    "  background: rgba(59, 130, 246, 0.2);"
    "  color: #60a5fa;"
    "  border: none;"
    "  border-radius: 4px;"
    "  font-size: 10px;"
    "  font-weight: 700;"
    "  padding: 0 12px;"
    "}"
)

_TAB_BTN_INACTIVE = (
    "QPushButton {"
    "  background: transparent;"
    "  color: #64748b;"
    "  border: none;"
    "  border-radius: 4px;"
    "  font-size: 10px;"
    "  font-weight: 700;"
    "  padding: 0 12px;"
    "}"
    "QPushButton:hover { color: #94a3b8; }"
)

_THEME_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0, 0, 0, 0.3);"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 6px;"
    "  padding: 4px 10px;"
    "  color: #f8fafc;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "  min-width: 120px;"
    "}"
    "QComboBox::drop-down {"
    "  border: none;"
    "  width: 20px;"
    "}"
    "QComboBox QAbstractItemView {"
    "  background: #1e293b;"
    "  color: #f8fafc;"
    "  border: 1px solid rgba(255, 255, 255, 0.1);"
    "  selection-background-color: rgba(59, 130, 246, 0.3);"
    "  padding: 4px;"
    "}"
)


# ─── Theme Designer Tab ──────────────────────────────────────────────────────


class ThemeDesignerTab(QWidget):
    """Three-column theme designer with live previews and JSON editor."""

    theme_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_name: str = "default"
        self._original_theme: dict = {}
        self._working_theme: dict = {}

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Top toolbar ──
        toolbar = self._build_toolbar()
        root_layout.addWidget(toolbar)

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORDER_SUBTLE};")
        root_layout.addWidget(sep)

        # ── Three-column body ──
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # Left column: Properties panel (280px)
        left_col = QWidget()
        left_col.setFixedWidth(280)
        left_col.setStyleSheet(f"background: {_PANEL_BG};")
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._properties_panel = ThemePropertiesPanel()
        self._properties_panel.theme_changed.connect(self._on_theme_changed)
        left_layout.addWidget(self._properties_panel)
        body.addWidget(left_col)

        # Vertical separator
        vsep1 = QFrame()
        vsep1.setFixedWidth(1)
        vsep1.setStyleSheet(f"background: {_BORDER_SUBTLE};")
        body.addWidget(vsep1)

        # Center column: stacked (multi-preview | editor)
        center_col = QWidget()
        center_col.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(center_col)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        # View toggle bar
        toggle_bar = QWidget()
        toggle_bar.setFixedHeight(32)
        toggle_bar.setStyleSheet(
            "background: rgba(15,23,42,0.6); "
            "border-bottom: 1px solid rgba(255,255,255,0.06);"
        )
        toggle_layout = QHBoxLayout(toggle_bar)
        toggle_layout.setContentsMargins(8, 4, 8, 4)
        toggle_layout.setSpacing(4)

        self._btn_multi = QPushButton("Multi Preview")
        self._btn_multi.setCheckable(True)
        self._btn_multi.setChecked(True)
        self._btn_multi.setFixedHeight(24)
        self._btn_multi.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_multi.clicked.connect(lambda: self._switch_center_view("multi"))
        toggle_layout.addWidget(self._btn_multi)

        self._btn_editor = QPushButton("Editor")
        self._btn_editor.setCheckable(True)
        self._btn_editor.setChecked(False)
        self._btn_editor.setFixedHeight(24)
        self._btn_editor.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_editor.clicked.connect(lambda: self._switch_center_view("editor"))
        toggle_layout.addWidget(self._btn_editor)

        toggle_layout.addStretch()
        center_layout.addWidget(toggle_bar)

        # Stacked: page 0 = multi-preview, page 1 = editor
        self._center_stack = QStackedWidget()

        # Page 0: Multi-preview (three ThemePreviews in triangle)
        multi_page = QWidget()
        multi_page.setStyleSheet("background: transparent;")
        multi_layout = QVBoxLayout(multi_page)
        multi_layout.setContentsMargins(16, 12, 16, 12)
        multi_layout.setSpacing(0)

        preview_splitter = QSplitter(Qt.Orientation.Vertical)
        preview_splitter.setStyleSheet(
            "QSplitter::handle { background: rgba(255,255,255,0.06); height: 1px; }"
        )
        preview_splitter.setChildrenCollapsible(False)

        top_container = QWidget()
        top_container.setStyleSheet("background: transparent;")
        top_row = QHBoxLayout(top_container)
        top_row.setContentsMargins(0, 0, 0, 0)
        self._preview_medium = ThemePreview(
            verse_key="medium", label="Medium Verse",
            min_width=320, max_width=720
        )
        top_row.addStretch()
        top_row.addWidget(self._preview_medium)
        top_row.addStretch()
        preview_splitter.addWidget(top_container)

        bottom_container = QWidget()
        bottom_container.setStyleSheet("background: transparent;")
        bottom_row = QHBoxLayout(bottom_container)
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(12)
        self._preview_shortest = ThemePreview(
            verse_key="shortest", label="Shortest Verse",
            min_width=320, max_width=600
        )
        bottom_row.addWidget(self._preview_shortest)
        self._preview_longest = ThemePreview(
            verse_key="longest", label="Longest Verse",
            min_width=320, max_width=600
        )
        bottom_row.addWidget(self._preview_longest)
        preview_splitter.addWidget(bottom_container)

        multi_layout.addWidget(preview_splitter, 1)
        self._center_stack.addWidget(multi_page)

        # Page 1: Container editor
        self._editor = ContainerEditor()
        self._editor.container_changed.connect(self._on_container_changed)
        self._center_stack.addWidget(self._editor)

        self._center_stack.setCurrentIndex(0)
        center_layout.addWidget(self._center_stack, 1)
        body.addWidget(center_col, 1)

        # Vertical separator
        vsep2 = QFrame()
        vsep2.setFixedWidth(1)
        vsep2.setStyleSheet(f"background: {_BORDER_SUBTLE};")
        body.addWidget(vsep2)

        # Right column: Animations + JSON tabs (300px)
        right_col = QWidget()
        right_col.setFixedWidth(300)
        right_col.setStyleSheet(f"background: {_PANEL_BG};")
        right_layout = QVBoxLayout(right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._build_right_panel(right_layout)
        body.addWidget(right_col)

        root_layout.addLayout(body, 1)

        # ── Load default theme ──
        self.set_theme("default")

    # ─── Toolbar ──────────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QFrame:
        toolbar = QFrame()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet(
            f"QFrame {{ background: {_PANEL_BG}; "
            f"border-bottom: 1px solid {_BORDER_SUBTLE}; }}"
        )
        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        # Theme selector combo
        self._theme_combo = QComboBox()
        self._theme_combo.setStyleSheet(_THEME_COMBO_STYLE)
        self._theme_combo.currentTextChanged.connect(self._on_combo_changed)
        layout.addWidget(self._theme_combo)

        # Name badge
        self._name_badge = QLabel("")
        self._name_badge.setStyleSheet(
            "color: #f8fafc; font-size: 13px; font-weight: 700; "
            "background: transparent; padding: 0 4px;"
        )
        layout.addWidget(self._name_badge)

        # Description
        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet(
            "color: #64748b; font-size: 10px; background: transparent; "
            "padding: 0 4px;"
        )
        self._desc_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        layout.addWidget(self._desc_label, 1)

        layout.addSpacing(8)

        # Import button
        self._btn_import = QPushButton("Import")
        self._btn_import.setStyleSheet(_TOOLBAR_BTN_SECONDARY)
        self._btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_import.clicked.connect(self._on_import)
        layout.addWidget(self._btn_import)

        # Export button
        self._btn_export = QPushButton("Export")
        self._btn_export.setStyleSheet(_TOOLBAR_BTN_SECONDARY)
        self._btn_export.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_export.clicked.connect(self._on_export)
        layout.addWidget(self._btn_export)

        layout.addSpacing(4)

        # Save button
        self._btn_save = QPushButton("Save")
        self._btn_save.setStyleSheet(_TOOLBAR_BTN_PRIMARY)
        self._btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save)
        layout.addWidget(self._btn_save)

        # Cancel button
        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.setStyleSheet(_TOOLBAR_BTN_GHOST)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.clicked.connect(self._on_cancel)
        layout.addWidget(self._btn_cancel)

        # Reset button
        self._btn_reset = QPushButton("Reset")
        self._btn_reset.setStyleSheet(_TOOLBAR_BTN_GHOST)
        self._btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_reset.clicked.connect(self._on_reset)
        layout.addWidget(self._btn_reset)

        return toolbar

    def _refresh_theme_combo(self):
        """Repopulate the combo box with all available themes."""
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        names = core.theme_loader.get_theme_names()
        self._theme_combo.addItems(names)
        idx = self._theme_combo.findText(self._theme_name)
        if idx >= 0:
            self._theme_combo.setCurrentIndex(idx)
        self._theme_combo.blockSignals(False)

    def _on_combo_changed(self, name: str):
        if name and name != self._theme_name:
            self.set_theme(name)

    # ─── Right panel (Animations + JSON) ──────────────────────────────────────

    def _build_right_panel(self, parent_layout: QVBoxLayout):
        # Tab bar
        tab_bar = QFrame()
        tab_bar.setFixedHeight(32)
        tab_bar.setStyleSheet(
            f"QFrame {{ background: {_PANEL_BG}; "
            f"border-bottom: 1px solid {_BORDER_SUBTLE}; }}"
        )
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(4, 4, 4, 4)
        tab_layout.setSpacing(2)

        self._tab_anim = QPushButton("Animations")
        self._tab_anim.setCheckable(True)
        self._tab_anim.setChecked(True)
        self._tab_anim.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_anim.setFixedHeight(24)
        self._tab_anim.clicked.connect(lambda: self._switch_right_tab("animations"))
        self._tab_anim.setStyleSheet(_TAB_BTN_ACTIVE)
        tab_layout.addWidget(self._tab_anim)

        self._tab_json = QPushButton("JSON")
        self._tab_json.setCheckable(True)
        self._tab_json.setChecked(False)
        self._tab_json.setCursor(Qt.CursorShape.PointingHandCursor)
        self._tab_json.setFixedHeight(24)
        self._tab_json.clicked.connect(lambda: self._switch_right_tab("json"))
        self._tab_json.setStyleSheet(_TAB_BTN_INACTIVE)
        tab_layout.addWidget(self._tab_json)

        tab_layout.addStretch()
        parent_layout.addWidget(tab_bar)

        # Stacked content
        self._right_stack = QStackedWidget()

        # Animations page
        self._animations_panel = ThemeAnimationsPanel()
        self._right_stack.addWidget(self._animations_panel)

        # JSON page
        json_page = QWidget()
        json_page.setStyleSheet("background: transparent;")
        json_layout = QVBoxLayout(json_page)
        json_layout.setContentsMargins(8, 8, 8, 8)
        json_layout.setSpacing(6)

        # JSON header buttons
        json_header = QHBoxLayout()
        json_header.setSpacing(4)
        lbl = QLabel("Theme JSON")
        lbl.setStyleSheet(
            "color: #94a3b8; font-size: 10px; font-weight: 700; "
            "text-transform: uppercase; letter-spacing: 1px; background: transparent;"
        )
        json_header.addWidget(lbl)
        json_header.addStretch()

        self._btn_format = QPushButton("Format")
        self._btn_format.setStyleSheet(_TOOLBAR_BTN_GHOST)
        self._btn_format.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_format.setFixedHeight(22)
        self._btn_format.clicked.connect(self._on_format_json)
        json_header.addWidget(self._btn_format)

        self._btn_copy = QPushButton("Copy")
        self._btn_copy.setStyleSheet(_TOOLBAR_BTN_GHOST)
        self._btn_copy.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_copy.setFixedHeight(22)
        self._btn_copy.clicked.connect(self._on_copy_json)
        json_header.addWidget(self._btn_copy)

        json_layout.addLayout(json_header)

        # JSON text editor
        self._json_editor = QTextEdit()
        self._json_editor.setReadOnly(True)
        self._json_editor.setStyleSheet(_JSON_EDITOR_STYLE)
        mono = QFont("Consolas", 11)
        mono.setStyleHint(QFont.StyleHint.Monospace)
        self._json_editor.setFont(mono)
        json_layout.addWidget(self._json_editor, 1)

        self._right_stack.addWidget(json_page)
        parent_layout.addWidget(self._right_stack, 1)

    def _switch_right_tab(self, tab: str):
        is_anim = tab == "animations"
        self._tab_anim.setChecked(is_anim)
        self._tab_json.setChecked(not is_anim)
        self._tab_anim.setStyleSheet(
            _TAB_BTN_ACTIVE if is_anim else _TAB_BTN_INACTIVE
        )
        self._tab_json.setStyleSheet(
            _TAB_BTN_ACTIVE if not is_anim else _TAB_BTN_INACTIVE
        )
        self._right_stack.setCurrentIndex(0 if is_anim else 1)

    def _switch_center_view(self, view: str):
        """Toggle between multi-preview and editor views."""
        is_multi = view == "multi"
        self._btn_multi.setChecked(is_multi)
        self._btn_editor.setChecked(not is_multi)
        self._btn_multi.setStyleSheet(
            _TAB_BTN_ACTIVE if is_multi else _TAB_BTN_INACTIVE
        )
        self._btn_editor.setStyleSheet(
            _TAB_BTN_ACTIVE if not is_multi else _TAB_BTN_INACTIVE
        )
        self._center_stack.setCurrentIndex(0 if is_multi else 1)
        if not is_multi:
            self._editor.load_container(self._working_theme.get("container", {}))

    def _on_container_changed(self, container: dict):
        """Called when the container editor updates container properties."""
        self._working_theme["container"] = container
        self._properties_panel.load_theme(self._working_theme)
        self._apply_to_previews()
        self._update_json_display()

    # ─── Public API ───────────────────────────────────────────────────────────

    def set_theme(self, name: str):
        """Load a theme by name and update all panels and previews."""
        theme = core.theme_loader.get_theme(name)
        if theme is None:
            return
        self._theme_name = name
        self._original_theme = copy.deepcopy(theme)
        self._working_theme = copy.deepcopy(theme)

        # Update combo
        self._refresh_theme_combo()

        # Update toolbar labels
        display_label = theme.get("label", name.title())
        self._name_badge.setText(display_label)
        self._desc_label.setText(theme.get("description", ""))

        # Load into properties panel (blocks signals internally)
        self._properties_panel.load_theme(self._working_theme)

        # Load into editor
        self._editor.load_container(self._working_theme.get("container", {}))

        # Apply to all previews
        self._apply_to_previews()

        # Update JSON display
        self._update_json_display()

    # ─── Signal handlers ──────────────────────────────────────────────────────

    def _on_theme_changed(self, theme_dict: dict):
        """Called when ThemePropertiesPanel emits an edit."""
        self._working_theme = copy.deepcopy(theme_dict)
        self._working_theme["name"] = self._theme_name
        label = self._original_theme.get("label", self._theme_name.title())
        self._working_theme["label"] = label
        self._editor.load_container(self._working_theme.get("container", {}))
        self._apply_to_previews()
        self._update_json_display()

    def _on_save(self):
        """Save the working theme to disk and emit theme_saved."""
        self._working_theme["name"] = self._theme_name
        core.theme_loader.save_theme(self._theme_name, self._working_theme)
        self._original_theme = copy.deepcopy(self._working_theme)
        self.theme_saved.emit(self._theme_name)

    def _on_cancel(self):
        """Restore the original theme without saving."""
        self._working_theme = copy.deepcopy(self._original_theme)
        self._properties_panel.load_theme(self._working_theme)
        self._editor.load_container(self._working_theme.get("container", {}))
        self._apply_to_previews()
        self._update_json_display()

    def _on_reset(self):
        """Reload the theme from disk (discard unsaved changes)."""
        core.theme_loader.reload_themes()
        self.set_theme(self._theme_name)

    def _on_export(self):
        """Copy the current working theme JSON to the system clipboard."""
        text = json.dumps(self._working_theme, indent=4, ensure_ascii=False)
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)

    def _on_import(self):
        """Paste JSON from the system clipboard and load it into the panels."""
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text()
        if not text or not text.strip():
            return
        try:
            theme = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(theme, dict):
            return
        # Preserve our current name/label
        theme["name"] = self._theme_name
        if "label" not in theme:
            theme["label"] = self._original_theme.get(
                "label", self._theme_name.title()
            )
        self._working_theme = theme
        self._properties_panel.load_theme(self._working_theme)
        self._apply_to_previews()
        self._update_json_display()

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _apply_to_previews(self):
        """Push the working theme dict into all three preview widgets."""
        self._preview_medium.apply_theme(self._working_theme)
        self._preview_shortest.apply_theme(self._working_theme)
        self._preview_longest.apply_theme(self._working_theme)

    def _update_json_display(self):
        """Refresh the JSON editor with the current working theme."""
        text = json.dumps(self._working_theme, indent=4, ensure_ascii=False)
        self._json_editor.setPlainText(text)

    def _on_format_json(self):
        """Re-format the JSON display (pretty-print with 4-space indent)."""
        try:
            parsed = json.loads(self._json_editor.toPlainText())
            formatted = json.dumps(parsed, indent=4, ensure_ascii=False)
            self._json_editor.setPlainText(formatted)
        except (json.JSONDecodeError, ValueError):
            pass

    def _on_copy_json(self):
        """Copy the JSON editor content to the clipboard."""
        text = self._json_editor.toPlainText()
        clipboard = QApplication.clipboard()
        if clipboard is not None and text:
            clipboard.setText(text)
