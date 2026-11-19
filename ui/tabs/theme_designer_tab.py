"""
ui/tabs/theme_designer_tab.py

Three-column theme designer tab:
  Left  (default 260px, draggable) - ThemePropertiesPanel
  Center (flex, min 360px)         - preview / container workspace
  Right (default 300px, draggable) - Animations panel + JSON editor

The side columns resize by dragging the painted handles between them. Widths
are clamped, persisted in the app settings store, and reset by double-clicking
a handle. When the window is too small the side columns give way first; the
preview keeps its minimum width.

Top toolbar: theme selector combo, name badge, Import/Export/Save/Cancel/Reset.
"""

import copy
import json
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QTextEdit, QStackedWidget, QApplication, QSizePolicy,
    QLineEdit,
)
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPalette

from core.constants import (
    DESIGNER_HANDLE_WIDTH,
    DESIGNER_LEFT_DEFAULT_WIDTH,
    DESIGNER_LEFT_MAX_WIDTH,
    DESIGNER_LEFT_MIN_WIDTH,
    DESIGNER_PREVIEW_MIN_WIDTH,
    DESIGNER_RIGHT_DEFAULT_WIDTH,
    DESIGNER_RIGHT_MAX_WIDTH,
    DESIGNER_RIGHT_MIN_WIDTH,
    THEME_PREVIEW_FRAME_MS,
)
from core.theme_catalog import (
    ThemeCatalog, build_entry, clean_description, clean_label, prettify_id,
)
from ui.widgets.theme_designer import ThemePropertyEditor
from ui.widgets.theme_designer.column_handle import ColumnHandle
from ui.widgets.theme_designer.document import ThemeDocument
from ui.widgets.theme_designer.notice_bar import NoticeBar
from ui.widgets.theme_designer.theme_combo import ThemeSelector
from ui.widgets.theme_designer.theme_watcher import ThemeFolderWatcher
from ui.theme_kit import SampleInjector, SampleState
from ui.theme_kit.preview_manager import PreviewManager
from ui.widgets.theme_preview import ThemePreview
from ui.widgets.theme_designer.animation_panel import AnimationPanel
from ui.widgets.theme_designer.container_workspace import ContainerWorkspace
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, TEXT_FAINT, SLATE_300, BG_RAISED,
    ACCENT, ACCENT_HOVER, SELECTION_BG, CHROME_SOFT, TEXT_SELECTION,
    ACCENT_TEXT, BORDER_LIGHT,
)
import core.theme_loader

logger = logging.getLogger(__name__)

# Settings keys live beside the splitter keys (layout.splitter.*) so every
# persisted layout value is found in the same place.
_LEFT_WIDTH_KEY = "layout.designer.left_width"
_RIGHT_WIDTH_KEY = "layout.designer.right_width"

#: Width of one side column after a double-click on its handle.
_DEFAULT_WIDTHS = {
    "left": DESIGNER_LEFT_DEFAULT_WIDTH,
    "right": DESIGNER_RIGHT_DEFAULT_WIDTH,
}


def clamp_column_width(value: int, minimum: int, maximum: int) -> int:
    """Clamp a column width into its allowed range."""
    return max(minimum, min(maximum, int(value)))


def fit_side_widths(available: int, left: int, right: int) -> tuple[int, int]:
    """Trim both side columns when the preview's space is at risk.

    ``available`` is the body width minus the two handles and the preview
    minimum. Trim is proportional to each column's slack over its own
    minimum, so the wider column gives up more but neither can take the
    other under its minimum. The preview is never part of this function: it
    is the space this calculation protects.
    """
    if left + right <= available:
        return left, right
    excess = left + right - available
    left_slack = max(0, left - DESIGNER_LEFT_MIN_WIDTH)
    right_slack = max(0, right - DESIGNER_RIGHT_MIN_WIDTH)
    total_slack = left_slack + right_slack
    if total_slack <= 0 or excess >= total_slack:
        return DESIGNER_LEFT_MIN_WIDTH, DESIGNER_RIGHT_MIN_WIDTH
    left_take = min(left_slack, excess * left_slack // total_slack)
    right_take = min(right_slack, excess - left_take)
    left_take = min(left_slack, excess - right_take)
    return left - left_take, right - right_take


def _saved_width(key: str, default: int, minimum: int, maximum: int) -> int:
    """Read one saved width, falling back to the default on bad data."""
    try:
        from core.database import get_setting
        raw = get_setting(key, "")
        return clamp_column_width(int(str(raw)), minimum, maximum)
    except (TypeError, ValueError):
        return default
    except Exception as exc:
        logger.warning("Could not read Theme Designer width %r: %s", key, exc)
        return default


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

# The theme label reads as a heading until the pointer or focus lands on it.
# The file name stays the ID, so this field can be renamed freely.
_LABEL_FIELD_STYLE = (
    "QLineEdit {"
    "  background: transparent;"
    "  border: none;"
    "  border-bottom: 1px solid transparent;"
    "  border-radius: 0;"
    "  color: " + TEXT_PRIMARY + ";"
    "  font-size: 13px;"
    "  font-weight: 700;"
    "  padding: 0 4px;"
    "}"
    "QLineEdit:hover {"
    "  border-bottom: 1px solid " + BORDER_LIGHT + ";"
    "}"
    "QLineEdit:focus {"
    "  border-bottom: 1px solid " + ACCENT + ";"
    "}"
)


# ─── Theme Designer Tab ──────────────────────────────────────────────────────


class ThemeDesignerTab(QWidget):
    """Three-column theme designer with live previews and JSON editor."""

    theme_saved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # ID = permanent theme identity (file name stem). The label is display
        # text only and may change at any time without moving the file.
        self._theme_id: str = "default"
        self._theme_name: str = "default"
        self._catalog = ThemeCatalog()
        self._original_theme: dict = {}
        # A disk change that arrived while the open theme had unsaved edits.
        self._disk_conflict: dict | None = None
        # Single document owner: every panel is a view over this object.
        self._document = ThemeDocument({}, self)
        self._document.changed.connect(self._on_document_changed)
        self._document.previewed.connect(self._on_document_previewed)
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

        # ── Disk-change notice (hidden until the watcher has something to say) ──
        self._notice = NoticeBar(self)
        root_layout.addWidget(self._notice)
        # Document-level messages (a deleted tie target, say) share the bar.
        self._document.noticed.connect(
            lambda text: self._notice.show_notice(
                text, [("Dismiss", self._notice.dismiss)]))

        # ── Separator ──
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_BORDER_SUBTLE};")
        root_layout.addWidget(sep)

        # ── Three-column body ──
        # The body is laid out by _layout_columns(), not by a QHBoxLayout.
        # A layout folds the current side widths into the tab's minimum size,
        # so a wide drag would stop the window from shrinking at all. Each
        # column keeps its own layout; only this outer geometry is manual.
        self._body = QWidget(self)
        self._body.setObjectName("rcDesignerBody")
        self._body.setStyleSheet("background: transparent;")
        root_layout.addWidget(self._body, 1)

        self._left_width = DESIGNER_LEFT_DEFAULT_WIDTH
        self._right_width = DESIGNER_RIGHT_DEFAULT_WIDTH
        self._drag_dirty = False
        self._applying_columns = False

        # The preview owns this floor; the side columns may never take it.
        self.setMinimumWidth(
            DESIGNER_LEFT_MIN_WIDTH + DESIGNER_RIGHT_MIN_WIDTH
            + DESIGNER_PREVIEW_MIN_WIDTH + 2 * DESIGNER_HANDLE_WIDTH)

        # Left column: properties panel.
        self._left_col = QWidget(self._body)
        self._left_col.setStyleSheet(f"background: {_PANEL_BG};")
        left_layout = QVBoxLayout(self._left_col)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        self._properties_panel = ThemePropertyEditor()
        self._properties_panel.container_selected.connect(
            self._on_container_selected)
        self._properties_panel.block_selected.connect(
            self._on_block_selected)
        left_layout.addWidget(self._properties_panel)

        self._left_handle = ColumnHandle("left", self._body)
        self._left_handle.drag_started.connect(self._on_handle_drag_started)
        self._left_handle.dragged.connect(
            lambda delta: self._on_handle_dragged("left", delta))
        self._left_handle.drag_finished.connect(self._on_handle_drag_finished)
        self._left_handle.reset_requested.connect(
            lambda: self._reset_column("left"))

        # Center column: stacked (multi-preview | editor).
        self._center_col = QWidget(self._body)
        self._center_col.setStyleSheet("background: transparent;")
        center_layout = QVBoxLayout(self._center_col)
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

        self._right_handle = ColumnHandle("right", self._body)
        self._right_handle.drag_started.connect(self._on_handle_drag_started)
        self._right_handle.dragged.connect(
            lambda delta: self._on_handle_dragged("right", delta))
        self._right_handle.drag_finished.connect(self._on_handle_drag_finished)
        self._right_handle.reset_requested.connect(
            lambda: self._reset_column("right"))

        # Right column: animations + JSON tabs.
        self._right_col = QWidget(self._body)
        self._right_col.setStyleSheet(f"background: {_PANEL_BG};")
        right_layout = QVBoxLayout(self._right_col)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        self._build_right_panel(right_layout)

        # Every panel reads the same document; none owns a second copy.
        self._properties_panel.bind_document(self._document)
        self._animations_panel.bind_document(self._document)
        self._workspace.bind_document(self._document)
        # A committed left-panel edit paints now, not on the next frame.
        self._properties_panel.theme_changed.connect(
            self._on_property_committed)

        # One preview, one replay policy.  The manager never writes the
        # document; it only decides which page-side phase to ask for.
        self._preview_manager = PreviewManager(
            self._preview, self._animations_panel, self)
        self._animations_panel.replay_requested.connect(
            self._preview_manager.request_replay)
        self._animations_panel.block_selected.connect(
            self._on_animation_block_selected)

        # ── Load default theme ──
        # The catalog is the one in-memory store the selector reads, keyed by
        # ID; the file watcher keeps it current from disk.
        self._catalog.load()
        self.set_theme("default")

        # ── Watch the themes folder for edits made outside the app ──
        self._watcher = ThemeFolderWatcher(self)
        self._watcher.changed.connect(self._on_theme_files_changed)
        self._watcher.start()

        # Saved widths are read once per tab instance; the layout pass then
        # clamps them to the window it actually opened in.
        self._load_column_widths()
        self._layout_columns()

    # ─── Column layout ────────────────────────────────────────────────────────

    def _load_column_widths(self) -> None:
        self._left_width = _saved_width(
            _LEFT_WIDTH_KEY, DESIGNER_LEFT_DEFAULT_WIDTH,
            DESIGNER_LEFT_MIN_WIDTH, DESIGNER_LEFT_MAX_WIDTH)
        self._right_width = _saved_width(
            _RIGHT_WIDTH_KEY, DESIGNER_RIGHT_DEFAULT_WIDTH,
            DESIGNER_RIGHT_MIN_WIDTH, DESIGNER_RIGHT_MAX_WIDTH)

    def _save_column_widths(self) -> None:
        try:
            from core.database import set_setting
            set_setting(_LEFT_WIDTH_KEY, str(int(self._left_width)))
            set_setting(_RIGHT_WIDTH_KEY, str(int(self._right_width)))
        except Exception as exc:
            logger.warning(
                "Could not save Theme Designer column widths: %s", exc)

    def _column_widths(self, body_width: int) -> tuple[int, int, int]:
        """Effective (left, right, preview) widths for one body width."""
        left = clamp_column_width(
            self._left_width, DESIGNER_LEFT_MIN_WIDTH, DESIGNER_LEFT_MAX_WIDTH)
        right = clamp_column_width(
            self._right_width, DESIGNER_RIGHT_MIN_WIDTH,
            DESIGNER_RIGHT_MAX_WIDTH)
        handles = 2 * DESIGNER_HANDLE_WIDTH
        available = body_width - handles - DESIGNER_PREVIEW_MIN_WIDTH
        left, right = fit_side_widths(available, left, right)
        preview = body_width - handles - left - right
        return left, right, max(DESIGNER_PREVIEW_MIN_WIDTH, preview)

    def _reflow_right_header(self, right_width: int) -> None:
        """Let the JSON header label step aside before its text is clipped."""
        label = getattr(self, "_json_header_label", None)
        if label is None:
            return
        label.setVisible(right_width >= self._json_header_min_width)

    def _layout_columns(self) -> None:
        if self._applying_columns or not hasattr(self, "_body"):
            return
        body_width = self._body.width()
        body_height = self._body.height()
        if body_width <= 0 or body_height <= 0:
            return
        self._applying_columns = True
        try:
            left, right, preview = self._column_widths(body_width)
            self._reflow_right_header(right)
            x = 0
            self._left_col.setGeometry(x, 0, left, body_height)
            x += left
            self._left_handle.setGeometry(
                x, 0, DESIGNER_HANDLE_WIDTH, body_height)
            x += DESIGNER_HANDLE_WIDTH
            self._center_col.setGeometry(x, 0, preview, body_height)
            x += preview
            self._right_handle.setGeometry(
                x, 0, DESIGNER_HANDLE_WIDTH, body_height)
            x += DESIGNER_HANDLE_WIDTH
            self._right_col.setGeometry(x, 0, right, body_height)
        finally:
            self._applying_columns = False

    def _on_handle_drag_started(self) -> None:
        # A press with no motion must not rewrite a width the window is
        # currently trimming. Effective widths are committed on the first
        # real delta instead.
        self._drag_dirty = False

    def _on_handle_dragged(self, side: str, delta: int) -> None:
        if not delta:
            return
        if not self._drag_dirty:
            self._left_width = self._left_col.width()
            self._right_width = self._right_col.width()
            self._drag_dirty = True
        body_width = self._body.width()
        handles = 2 * DESIGNER_HANDLE_WIDTH
        if side == "left":
            upper = (body_width - handles - DESIGNER_PREVIEW_MIN_WIDTH
                     - self._right_width)
            upper = max(DESIGNER_LEFT_MIN_WIDTH,
                        min(DESIGNER_LEFT_MAX_WIDTH, upper))
            self._left_width = clamp_column_width(
                self._left_col.width() + delta,
                DESIGNER_LEFT_MIN_WIDTH, upper)
        else:
            upper = (body_width - handles - DESIGNER_PREVIEW_MIN_WIDTH
                     - self._left_width)
            upper = max(DESIGNER_RIGHT_MIN_WIDTH,
                        min(DESIGNER_RIGHT_MAX_WIDTH, upper))
            # The right column's left edge moves with the pointer, so the
            # same pointer delta subtracts from its width.
            self._right_width = clamp_column_width(
                self._right_col.width() - delta,
                DESIGNER_RIGHT_MIN_WIDTH, upper)
        self._layout_columns()

    def _on_handle_drag_finished(self) -> None:
        if self._drag_dirty:
            self._drag_dirty = False
            self._save_column_widths()

    def _reset_column(self, side: str) -> None:
        """Double-clicked handle: restore that column's shipped width."""
        self._left_width = (
            _DEFAULT_WIDTHS["left"] if side == "left" else self._left_width)
        self._right_width = (
            _DEFAULT_WIDTHS["right"] if side == "right" else self._right_width)
        self._layout_columns()
        self._save_column_widths()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_columns()

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

        # Theme selector: option text is the label, value is the permanent ID.
        self._theme_combo = ThemeSelector()
        self._theme_combo.setStyleSheet(_THEME_COMBO_STYLE)
        self._theme_combo.currentIndexChanged.connect(self._on_combo_changed)
        layout.addWidget(self._theme_combo)

        # Label (rename in place). The placeholder is the prettified ID, so an
        # empty field still tells the operator what the selector falls back to.
        self._label_field = QLineEdit()
        self._label_field.setStyleSheet(_LABEL_FIELD_STYLE)
        self._label_field.setMaxLength(120)
        self._label_field.setFixedHeight(24)
        self._label_field.setMinimumWidth(120)
        self._label_field.setMaximumWidth(320)
        self._label_field.setAccessibleName("Theme label")
        self._label_field.setToolTip(
            "Display name for this theme. The file name stays its ID.")
        palette = self._label_field.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText,
                         QColor(TEXT_FAINT))
        self._label_field.setPalette(palette)
        self._label_field.textEdited.connect(self._on_label_edited)
        layout.addWidget(self._label_field)

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
        """Repopulate the selector from the catalog, keeping the same ID.

        Selection is restored by ID (the option value), never by text or
        index, so a label edit or a re-sort cannot move the operator to a
        different theme.
        """
        self._theme_combo.set_entries(self._catalog.entries(), self._theme_id)

    def _on_combo_changed(self, _index: int):
        theme_id = self._theme_combo.current_id()
        if theme_id and theme_id != self._theme_id:
            self.set_theme(theme_id)

    def _on_label_edited(self, text: str):
        """Typing a label updates the catalog and the dropdown per keystroke.

        The document keeps exactly what was typed (an empty string stays
        empty so the operator can keep typing); the save path is what refuses
        to write an empty label to disk.
        """
        if not self._theme_id:
            return
        if self._catalog.set_label(self._theme_id, text):
            # Store the trimmed label so the document and the one store never
            # disagree about trailing whitespace.
            self._document.set(("label",), clean_label(text), source=self)
            self._refresh_theme_combo()

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
        # Decorative: the tab bar already says JSON. It is hidden when the
        # column is too narrow for it, so the three action buttons never clip.
        lbl = QLabel("Theme JSON")
        lbl.setStyleSheet(
            "color: " + TEXT_MUTED + "; font-size: 12px; font-weight: 700; "
            "text-transform: uppercase; letter-spacing: 1px; background: transparent;"
        )
        self._json_header_label = lbl
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
        # Natural width of the header row: label, three buttons, spacing and
        # the page margins. Below this the label steps aside (see
        # _reflow_right_header) instead of clipping its text.
        self._json_header_min_width = (
            self._json_header_label.sizeHint().width()
            + self._btn_format.sizeHint().width()
            + self._btn_copy.sizeHint().width()
            + self._btn_apply.sizeHint().width()
            + 3 * json_header.spacing()
            + json_layout.contentsMargins().left()
            + json_layout.contentsMargins().right())

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
        """Load a theme by ID into the one document every panel renders.

        ``name`` may also be a legacy loader key; the selector always passes
        the permanent ID (file name stem). The label is display text only.
        """
        entry = self._entry_for(name)
        theme = core.theme_loader.get_theme(entry.name if entry else name)
        if theme is None:
            return
        self._theme_id = entry.id if entry is not None else name
        self._theme_name = entry.name if entry is not None else name
        self._original_theme = copy.deepcopy(theme)
        self._preview_pending = None
        self._selected_container_id = ""
        self._disk_conflict = None
        self._notice.dismiss()
        self._refresh_theme_combo()
        self._document.replace(copy.deepcopy(theme), source=self)

    def _entry_for(self, theme_id_or_name: str):
        """Catalog entry for an ID or loader key, registering it on demand."""
        entry = self._catalog.resolve(theme_id_or_name)
        if entry is not None:
            return entry
        for ref in core.theme_loader.get_theme_refs().values():
            if theme_id_or_name in (ref.id, ref.name):
                theme = core.theme_loader.get_theme(ref.name)
                if not isinstance(theme, dict):
                    return None
                entry = build_entry(
                    ref.id, ref.name, ref.path, ref.kind, theme)
                self._catalog.upsert(entry)
                return entry
        return None

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
        self._sync_catalog_label()
        self._refresh_toolbar_identity()
        self._apply_to_previews()
        self._update_json_display()

    def _on_document_previewed(self, _paths, _source):
        """A live left-panel value landed in the document: publish it now."""
        self._preview_pending = None
        self._preview_paths = ()
        self._apply_to_previews()

    def _on_property_committed(self, _theme=None) -> None:
        """Pointer release / commit: refresh the panes and paint at once."""
        self._update_json_display()
        self._preview_pending = None
        self._flush_preview(flush=True)

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

    def _on_block_selected(self, block: str) -> None:
        """Left Blocks tab chose an element; the panel follows it."""
        self._animations_panel.set_block(block)

    def _on_animation_block_selected(self, block: str) -> None:
        """Right panel target chose an element; the Blocks section follows."""
        self._properties_panel.set_selected_block(block)

    def _refresh_toolbar_identity(self):
        theme = self._working_theme
        raw_label = theme.get("label")
        raw_label = raw_label if isinstance(raw_label, str) else ""
        if (not self._label_field.hasFocus()
                and self._label_field.text() != raw_label):
            self._label_field.setText(raw_label)
        self._label_field.setPlaceholderText(
            prettify_id(self._theme_id or self._theme_name))
        entry = self._catalog.get(self._theme_id)
        stale = bool(entry is not None and entry.stale)
        base_tip = "Display name for this theme. The file name stays its ID."
        self._label_field.setToolTip(
            base_tip + ("\nThis file is not valid JSON right now; showing "
                        "the last good version." if stale else ""))
        description = theme.get("description")
        self._desc_label.setText(clean_description(description))
        self._desc_label.setToolTip(
            clean_description(description) if description else "")

    def _sync_catalog_label(self):
        """Mirror the open document's label into the one catalog store."""
        raw = self._working_theme.get("label")
        raw = raw if isinstance(raw, str) else ""
        if self._catalog.set_label(self._theme_id, raw):
            self._refresh_theme_combo()

    def _on_save(self):
        """Save the document to disk and emit theme_saved.

        Label changes never rename or move the file (the ID is the file name).
        An empty label is dropped instead of written as `"label": ""`, so the
        selector keeps showing the prettified ID after a reload.
        """
        self._document.set(("name",), self._theme_name, source=self)
        label = self._document.get(("label",))
        if isinstance(label, str) and not label.strip():
            self._document.set(("label",), None, source=self)
        working = self._document.snapshot()
        path = core.theme_loader.save_theme(self._theme_name, working)
        # Mark our own bytes so the file watcher ignores this save's echo.
        self._catalog.note_written(
            path, working, core.theme_loader.dump_theme(working))
        self._original_theme = copy.deepcopy(working)
        self._refresh_theme_combo()
        self._refresh_toolbar_identity()
        self.theme_saved.emit(self._theme_name)

    def _on_cancel(self):
        """Restore the original theme without saving."""
        self._selected_container_id = ""
        self._preview_pending = None
        self._document.replace(copy.deepcopy(self._original_theme), source=self)

    def _on_reset(self):
        """Reload the theme from disk (discard unsaved changes)."""
        core.theme_loader.reload_themes()
        self._catalog.load()
        self.set_theme(self._theme_id)

    # ─── External file changes (watcher) ─────────────────────────────────────

    def _on_theme_files_changed(self):
        """One debounced disk event: reconcile the store and the open theme."""
        changes = self._catalog.sync_from_disk(
            core.theme_loader.iter_theme_files())
        if not changes:
            return

        selected = self._theme_id
        removed = next(
            (c for c in changes
             if c.action == "removed" and c.theme_id == selected), None)
        changed = next(
            (c for c in changes
             if c.theme_id == selected and c.action != "removed"), None)

        if removed is not None:
            self._handle_deleted_theme(removed)
            return
        if changed is not None:
            if changed.action == "invalid":
                self._handle_invalid_theme(changed)
            elif self.is_dirty():
                self._handle_disk_conflict(changed)
            else:
                # Same ID, new content: reload the document quietly.
                self.set_theme(selected)
                return
        self._refresh_theme_combo()

    def _handle_deleted_theme(self, change) -> None:
        """The selected theme's file disappeared: fall back and say so."""
        was_dirty = self.is_dirty()
        label = (clean_label(self._original_theme.get("label"))
                 or prettify_id(change.theme_id))
        fallback = "default" if self._catalog.get("default") else (
            self._catalog.entries()[0].id if len(self._catalog) else "")
        if fallback:
            self.set_theme(fallback)
            fallback_label = self._catalog.get(fallback).label
            text = (f'"{label}" was deleted on disk. Switched to '
                    f'"{fallback_label}".')
            if was_dirty:
                text += " Its unsaved edits were discarded."
        else:
            self._refresh_theme_combo()
            text = (f'"{label}" was deleted on disk and no themes remain. '
                    "Saving will recreate it.")
        self._notice.show_notice(
            text, [("Dismiss", self._notice.dismiss)])

    def _handle_invalid_theme(self, change) -> None:
        """Mid-edit JSON on disk: keep the last good version, warn quietly."""
        entry = self._catalog.get(change.theme_id)
        label = entry.label if entry is not None else prettify_id(
            change.theme_id)
        # The open document is the operator's truth; keep its label in the
        # one store so the selector does not contradict the field.
        self._sync_catalog_label()
        self._refresh_theme_combo()
        self._notice.show_notice(
            f'"{label}" is not valid JSON right now. Showing the last good '
            "version.", [("Dismiss", self._notice.dismiss)])

    def _handle_disk_conflict(self, change) -> None:
        """Externally edited while dirty: never overwrite the operator's work."""
        self._disk_conflict = {"id": change.theme_id, "path": str(change.path)}
        entry = self._catalog.get(change.theme_id)
        label = entry.label if entry is not None else prettify_id(
            change.theme_id)
        # The open document wins until the operator chooses to reload.
        self._sync_catalog_label()
        self._refresh_theme_combo()
        self._notice.show_notice(
            f'"{label}" changed on disk while you have unsaved edits.',
            [("Reload from disk", self._reload_disk_theme),
             ("Keep editing", self._dismiss_disk_conflict)])

    def _reload_disk_theme(self) -> None:
        """Conflict action: replace the document with the file on disk."""
        theme_id = (self._disk_conflict or {}).get("id") or self._theme_id
        self._disk_conflict = None
        self.set_theme(theme_id)

    def _dismiss_disk_conflict(self) -> None:
        """Conflict action: keep the operator's unsaved edits."""
        self._disk_conflict = None
        self._notice.dismiss()

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
        # Retired keys (canvas.fit) are tolerated on import but never stored.
        core.theme_loader.strip_obsolete_keys(theme)
        # Preserve our current name/label
        theme["name"] = self._theme_name
        if "label" not in theme:
            current = self._working_theme.get("label")
            theme["label"] = (
                current if isinstance(current, str) and current.strip()
                else prettify_id(self._theme_id))
        self._selected_container_id = ""
        self._preview_pending = None
        self._document.replace(theme, source=self)

    # ─── Internal helpers ─────────────────────────────────────────────────────

    def _apply_to_previews(self):
        """Arm one frame for the newest theme — never a debounce.

        The timer is started by the first change and is not restarted by
        later ones, so a burst of drag events costs one publish and always
        publishes the latest value. `_flush_preview(flush=True)` paints a
        commit synchronously instead of waiting for the frame.
        """
        if not hasattr(self, "_preview_timer"):
            self._preview_timer = QTimer(self)
            self._preview_timer.setSingleShot(True)
            self._preview_timer.setInterval(THEME_PREVIEW_FRAME_MS)
            self._preview_timer.timeout.connect(self._flush_preview)
        if not self._preview_timer.isActive():
            self._preview_timer.start()

    def _flush_preview(self, flush: bool = False):
        timer = getattr(self, "_preview_timer", None)
        if timer is not None:
            timer.stop()
        theme = (self._preview_pending if self._preview_pending is not None
                 else self._working_theme)
        self._preview_pending = None
        if self._preview_reload:
            self._preview_manager.load_theme(theme, self._samples.current())
        else:
            self._preview_manager.update_theme(theme, self._preview_paths,
                                               flush=flush)
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
        # First show is when the body finally has a real width; the saved
        # widths are clamped against that width here, not at construction.
        self._layout_columns()
        if hasattr(self, "_preview_manager"):
            self._preview_manager.set_visible(True)

    def hideEvent(self, event):
        if hasattr(self, "_preview_manager"):
            self._preview_manager.set_visible(False)
        super().hideEvent(event)

    def closeEvent(self, event):
        if hasattr(self, "_watcher"):
            self._watcher.stop()
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
        # Retired keys (canvas.fit) are tolerated in pasted JSON but never
        # stored, so the next save cannot write them back.
        core.theme_loader.strip_obsolete_keys(parsed)
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
