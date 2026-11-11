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
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from ui.popups import install_combo
from PyQt6.QtGui import QFont

from ui.widgets.theme_designer import ThemePropertyEditor
from ui.widgets.theme_designer.document import ThemeDocument
from ui.theme_kit import SampleInjector, SampleState
from ui.theme_kit.preview_manager import PreviewManager
from ui.widgets.theme_preview import ThemePreview
from ui.widgets.theme_designer.animation_panel import AnimationPanel
from ui.widgets.theme_designer.container_workspace import ContainerWorkspace
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, TEXT_FAINT, SLATE_300, BG_RAISED,
    ACCENT, ACCENT_HOVER, SELECTION_BG, CHROME_SOFT, TEXT_SELECTION,
    ACCENT_TEXT,
)
import core.theme_loader


# ─── Styles ──────────────────────────────────────────────────────────────────

_PANEL_BG = CHROME_SOFT
_BORDER_SUBTLE = "rgba(255, 255, 255, 0.06)"

_JSON_EDITOR_STYLE = (
    "QTextEdit {"
    "  background: rgba(0, 0, 0, 0.4);"
    "  border: 1px solid rgba(255, 255, 255, 0.06);"
    "  border-radius: 8px;"
    "  color: " + SLATE_300 + ";"
    "  font-family: 'Consolas', 'Courier New', monospace;"
    "  font-size: 12px;"
    "  padding: 8px;"
    "  selection-background-color: " + TEXT_SELECTION + ";"
    "}"
)

_TOOLBAR_BTN_STYLE = (
    "QPushButton {"
    "  background: transparent;"
    "  color: " + TEXT_MUTED + ";"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 6px;"
    "  padding: 5px 12px;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  color: " + TEXT_PRIMARY + ";"
    "}"
)

_TOOLBAR_BTN_PRIMARY = (
    "QPushButton {"
    "  background: " + ACCENT + ";"
    "  color: " + TEXT_PRIMARY + ";"
    "  border: none;"
    "  border-radius: 6px;"
    "  padding: 5px 14px;"
    "  font-size: 12px;"
    "  font-weight: 700;"
    "}"
    "QPushButton:hover {"
    "  background: " + ACCENT_HOVER + ";"
    "}"
    "QPushButton:pressed {"
    "  background: " + ACCENT + ";"
    "}"
)

_TOOLBAR_BTN_SECONDARY = (
    "QPushButton {"
    "  background: rgba(255, 255, 255, 0.06);"
    "  color: " + SLATE_300 + ";"
    "  border: 1px solid rgba(255, 255, 255, 0.1);"
    "  border-radius: 6px;"
    "  padding: 5px 12px;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.1);"
    "  color: " + TEXT_PRIMARY + ";"
    "}"
)

_TOOLBAR_BTN_GHOST = (
    "QPushButton {"
    "  background: transparent;"
    "  color: " + TEXT_FAINT + ";"
    "  border: none;"
    "  border-radius: 6px;"
    "  padding: 5px 10px;"
    "  font-size: 12px;"
    "  font-weight: 600;"
    "}"
    "QPushButton:hover {"
    "  background: rgba(255, 255, 255, 0.05);"
    "  color: " + TEXT_MUTED + ";"
    "}"
)

_TAB_BTN_ACTIVE = (
    "QPushButton {"
    "  background: " + SELECTION_BG + ";"
    "  color: " + ACCENT_TEXT + ";"
    "  border: none;"
    "  border-radius: 4px;"
    "  font-size: 12px;"
    "  font-weight: 700;"
    "  padding: 0 12px;"
    "}"
)

_TAB_BTN_INACTIVE = (
    "QPushButton {"
    "  background: transparent;"
    "  color: " + TEXT_FAINT + ";"
    "  border: none;"
    "  border-radius: 4px;"
    "  font-size: 12px;"
    "  font-weight: 700;"
    "  padding: 0 12px;"
    "}"
    "QPushButton:hover { color: " + TEXT_MUTED + "; }"
)

_THEME_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0, 0, 0, 0.3);"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 6px;"
    "  padding: 4px 10px;"
    "  color: " + TEXT_PRIMARY + ";"
    "  font-size: 13px;"
    "  font-weight: 600;"
    "  min-width: 120px;"
    "}"
    "QComboBox::drop-down {"
    "  border: none;"
    "  width: 20px;"
    "}"
    "QComboBox QAbstractItemView {"
    "  background: " + BG_RAISED + ";"
    "  color: " + TEXT_PRIMARY + ";"
    "  border: 1px solid rgba(255, 255, 255, 0.1);"
    "  selection-background-color: " + TEXT_SELECTION + ";"
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
        # Single document owner: every panel is a view over this object.
        self._document = ThemeDocument({}, self)
        self._document.changed.connect(self._on_document_changed)
        self._document.replaced.connect(self._on_document_replaced)
        self._preview_pending: dict | None = None
        self._preview_paths: tuple = ()
        self._preview_reload = False
        # Single selection model for every container view (Stage 4).
        self._selected_container_id: str = ""

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
        left_col.setFixedWidth(260)
        left_col.setStyleSheet(f"background: {_PANEL_BG};")
        left_layout = QVBoxLayout(left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._properties_panel = ThemePropertyEditor()
        self._properties_panel.container_selected.connect(
            self._on_container_selected)
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

        self._btn_multi = QPushButton("Preview")
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

        # Page 0: one preview, driven by the Stage 1 sample injector.
        preview_page = QWidget()
        preview_page.setStyleSheet("background: transparent;")
        preview_layout = QVBoxLayout(preview_page)
        preview_layout.setContentsMargins(16, 12, 16, 12)
        preview_layout.setSpacing(8)
        self._preview = ThemePreview(
            verse_key="medium", label="Preview",
            min_width=320, max_width=820
        )
        preview_layout.addWidget(self._preview, 1)
        self._samples = SampleInjector(
            [SampleState("shortest", "Shortest"),
             SampleState("medium", "Medium"),
             SampleState("longest", "Longest"),
             SampleState("freeform", "Freeform")], "medium")
        self._samples.changed.connect(self._on_sample_changed)
        preview_layout.addWidget(self._samples, 0)
        self._center_stack.addWidget(preview_page)

        # Page 1: container canvas + layer strip + exact geometry
        self._workspace = ContainerWorkspace()
        self._workspace.preview_changed.connect(self._on_workspace_preview)
        self._workspace.container_selected.connect(self._on_container_selected)
        self._center_stack.addWidget(self._workspace)

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

        # Every panel reads the same document; none owns a second copy.
        self._properties_panel.bind_document(self._document)
        self._animations_panel.bind_document(self._document)
        self._workspace.bind_document(self._document)

        # One preview, one replay policy.  The manager never writes the
        # document; it only decides which page-side phase to ask for.
        self._preview_manager = PreviewManager(
            self._preview, self._animations_panel, self)
        self._animations_panel.replay_requested.connect(
            self._preview_manager.request_replay)

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
        install_combo(self._theme_combo)
        self._theme_combo.setStyleSheet(_THEME_COMBO_STYLE)
        self._theme_combo.currentTextChanged.connect(self._on_combo_changed)
        layout.addWidget(self._theme_combo)

        # Name badge
        self._name_badge = QLabel("")
        self._name_badge.setStyleSheet(
            "color: " + TEXT_PRIMARY + "; font-size: 13px; font-weight: 700; "
            "background: transparent; padding: 0 4px;"
        )
        layout.addWidget(self._name_badge)

        # Description
        self._desc_label = QLabel("")
        self._desc_label.setStyleSheet(
            "color: " + TEXT_FAINT + "; font-size: 12px; background: transparent; "
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
        self._animations_panel = AnimationPanel()
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
            "color: " + TEXT_MUTED + "; font-size: 12px; font-weight: 700; "
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

        self._btn_apply = QPushButton("Apply")
        self._btn_apply.setStyleSheet(_TOOLBAR_BTN_SECONDARY)
        self._btn_apply.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_apply.setFixedHeight(22)
        self._btn_apply.clicked.connect(self._on_apply_json)
        json_header.addWidget(self._btn_apply)

        json_layout.addLayout(json_header)

        # JSON text editor
        self._json_editor = QTextEdit()
        self._json_editor.setReadOnly(False)
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
            self._workspace.set_selected(self._selected_container_id)



    # ─── Public API ───────────────────────────────────────────────────────────

    def set_theme(self, name: str):
        """Load a theme by name into the one document every panel renders."""
        theme = core.theme_loader.get_theme(name)
        if theme is None:
            return
        self._theme_name = name
        self._original_theme = copy.deepcopy(theme)
        self._preview_pending = None
        self._selected_container_id = ""
        self._refresh_theme_combo()
        self._document.replace(copy.deepcopy(theme), source=self)

    @property
    def _working_theme(self) -> dict:
        """Read-only snapshot of the tab-owned document (legacy readers)."""
        return self._document.snapshot()

    @_working_theme.setter
    def _working_theme(self, theme: dict) -> None:
        """Compatibility assignment used by dev harnesses; not a second copy."""
        self._preview_pending = None
        self._selected_container_id = ""
        self._document.replace(theme if isinstance(theme, dict) else {},
                               source=self)

    # ── Unload contract (see MainWindow._unload_tab) ─────────────────────

    def is_dirty(self) -> bool:
        """True when the document differs from the last loaded/saved one."""
        working = self._document.snapshot()
        return bool(working) and working != self._original_theme

    def can_unload(self):
        if self.is_dirty():
            return False, (
                "Theme Designer has unsaved changes. Save or discard them "
                "before unloading the tab.")
        return True, ""

    def current_state(self) -> dict:
        return {"theme": self._theme_name}

    def restore_state(self, state: dict) -> None:
        name = state.get("theme")
        if name:
            self.set_theme(name)

    # ─── Signal handlers ──────────────────────────────────────────────────────

    def _on_document_changed(self, paths, _source):
        """The tab owns the document; panels already refreshed themselves."""
        ids = self._container_ids()
        if self._selected_container_id not in ids:
            self._selected_container_id = ids[0] if ids else ""
        self._preview_pending = None
        self._preview_paths = tuple(paths or ())
        self._preview_reload = False
        self._refresh_toolbar_identity()
        self._apply_to_previews()
        self._update_json_display()

    def _on_document_replaced(self, _source):
        ids = self._container_ids()
        self._selected_container_id = (
            self._selected_container_id
            if self._selected_container_id in ids else (ids[0] if ids else ""))
        if self._selected_container_id:
            self._on_container_selected(self._selected_container_id)
        self._preview_pending = None
        self._preview_paths = ()
        self._preview_reload = True
        self._refresh_toolbar_identity()
        self._apply_to_previews()
        self._update_json_display()

    def _on_workspace_preview(self, theme_dict: dict):
        """Canvas drag preview only; the document changes on release."""
        if not isinstance(theme_dict, dict):
            return
        self._preview_pending = copy.deepcopy(theme_dict)
        self._preview_paths = ()
        self._preview_reload = False
        self._apply_to_previews()

    def _on_container_selected(self, container_id: str):
        ids = self._container_ids()
        if container_id not in ids:
            return
        self._selected_container_id = container_id
        self._properties_panel.set_selected_container(container_id)
        self._workspace.set_selected(container_id)
        self._animations_panel.set_container(container_id)

    def _refresh_toolbar_identity(self):
        theme = self._working_theme
        label = theme.get("label", self._theme_name.title())
        self._name_badge.setText(str(label))
        self._desc_label.setText(str(theme.get("description", "")))

    def _on_save(self):
        """Save the document to disk and emit theme_saved."""
        self._document.set(("name",), self._theme_name, source=self)
        working = self._document.snapshot()
        core.theme_loader.save_theme(self._theme_name, working)
        self._original_theme = copy.deepcopy(working)
        self.theme_saved.emit(self._theme_name)

    def _on_cancel(self):
        """Restore the original theme without saving."""
        self._selected_container_id = ""
        self._preview_pending = None
        self._document.replace(copy.deepcopy(self._original_theme), source=self)

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
        self._selected_container_id = ""
        self._preview_pending = None
        self._document.replace(theme, source=self)

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _apply_to_previews(self):
        """Push the working theme into the single preview (debounced)."""
        if not hasattr(self, "_preview_timer"):
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(80)
            self._preview_timer.timeout.connect(self._flush_preview)
        self._preview_timer.start()

    def _flush_preview(self):
        theme = (self._preview_pending if self._preview_pending is not None
                 else self._working_theme)
        self._preview_pending = None
        if self._preview_reload:
            self._preview_manager.load_theme(theme, self._samples.current())
        else:
            self._preview_manager.update_theme(theme, self._preview_paths)
        self._preview_reload = False
        self._preview_paths = ()

    def _on_sample_changed(self, sample_id: str, _reroll: bool = False):
        self._preview_manager.set_sample(sample_id, self._working_theme)

    def _container_ids(self) -> list[str]:
        containers = self._working_theme.get("containers")
        if not isinstance(containers, list):
            return []
        return [str(c.get("id", "")) for c in containers
                if isinstance(c, dict)]

    def _first_container_id(self) -> str:
        ids = self._container_ids()
        return ids[0] if ids else ""

    def _ensure_selection(self) -> None:
        ids = self._container_ids()
        if self._selected_container_id not in ids:
            self._selected_container_id = ids[0] if ids else ""

    def _active_container(self) -> dict:
        containers = self._working_theme.get("containers")
        if isinstance(containers, list):
            for container in containers:
                if isinstance(container, dict) and str(
                        container.get("id", "")) == self._selected_container_id:
                    return container
        container = self._working_theme.get("container")
        return container if isinstance(container, dict) else {}

    def _update_json_display(self):
        """Refresh the JSON editor with the current working theme."""
        text = json.dumps(self._working_theme, indent=4, ensure_ascii=False)
        self._json_editor.setPlainText(text)

    def showEvent(self, event):
        super().showEvent(event)
        if hasattr(self, "_preview_manager"):
            self._preview_manager.set_visible(True)

    def hideEvent(self, event):
        if hasattr(self, "_preview_manager"):
            self._preview_manager.set_visible(False)
        super().hideEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "_preview_manager"):
            self._preview_manager.shutdown()
        super().closeEvent(event)

    def _on_apply_json(self):
        """Apply raw JSON edits; unknown keys are kept because the text is
        the whole document, not a resolved projection."""
        try:
            parsed = json.loads(self._json_editor.toPlainText())
        except (json.JSONDecodeError, ValueError):
            return
        if not isinstance(parsed, dict):
            return
        self._selected_container_id = ""
        self._preview_pending = None
        self._document.replace(parsed, source=self)

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
