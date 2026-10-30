"""
ui/panels/schedule_panel.py

Ordered verse list for the service schedule.
Programmatic add via Alt+click in the browser panel.

Interactions:
  - Single-click → preview verse
  - Double-click → push verse to live
  - Right-click → context menu (Rename / Themes / Delete)
  - Alt+Right-click → themes-only picker
  - Delete key → delete selected item(s)
  - Internal reorder via drag-and-drop
  - Multi-select via Ctrl/Shift click for batch operations
"""

import logging
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QFrame, QAbstractItemView, QMenu, QLineEdit, QSizePolicy, QApplication,
    QFileDialog, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent

from ui import dialogs
from ui.popups import menu_qss
from ui.styles import (
    PANEL_HEADER_STYLE, panel_header_label_style,
    PANEL_BODY_STYLE, WHITE,
    SELECTION_BG, SELECTION_BORDER, MENU_BG,
    apply_minimal_scrollbar,
)
from ui.tokens import (
    BG_CARD, CARD_OBJECT_NAME, SPACE_4, SPACE_8, SPACE_12,
    SELECTED_BAR_WIDTH, BADGE_BORDER_WIDTH, BADGE_PAD_Y, TEXT_PRIMARY,
    TRANSLATION_COLORS, TRANSLATION_FALLBACK, TRANSLATION_LABELS,
    BUTTON_HEIGHT, badge_qss, button_qss, card_qss,
)

logger = logging.getLogger(__name__)

_DOUBLE_CLICK_THRESHOLD_MS = 400

# Schedule card type: one group (family/weight/size) for the row's
# reference, translation badge and rename field. Per-label defaults keep
# the existing hierarchy (ref 600, badge 400) until the operator overrides
# it.
_SCHEDULE_CARD_SIZE_MIN = 8
_SCHEDULE_CARD_SIZE_MAX = 24


def _schedule_card_font(size_default: int, weight_default: int) -> dict:
    from ui.app_theme import area_font
    return area_font("schedule.cards", size_default, weight_default,
                     size_min=_SCHEDULE_CARD_SIZE_MIN,
                     size_max=_SCHEDULE_CARD_SIZE_MAX)


def _grouped_themes():
    """Yield (section_label, [(name, theme_data)]) grouped by theme kind.

    Schedule items mix verses and slide decks, so both kinds are offered —
    but grouped under Scripture / Freeform headers, never mashed together.
    """
    from core.theme_loader import get_all_themes, get_theme_kind, SCRIPTURE, FREEFORM
    themes = get_all_themes()
    for kind, label in ((SCRIPTURE, "Scripture"), (FREEFORM, "Freeform")):
        names = sorted(n for n in themes if get_theme_kind(n) == kind)
        if names:
            yield label, [(n, themes[n]) for n in names]

# Schedules directory
_SCHEDULES_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "schedules"

# Small button style for schedule header — ghost variant of the shared
# button language (text until hovered, same height/radius as every button).
_header_btn_style = button_qss("ghost", padding=f"0 {SPACE_8}px")

# ─── Color coding for schedule items ──────────────────────────────────────────
# 8 base colors, one per book group. Different chapters get different shades.

_BOOK_COLORS = [
    ("#1e3a5f", "#2d5a8a", "#152c4a"),  # 0: steel blue — base, bright, dark
    ("#3b2d4a", "#5a4270", "#2d2238"),  # 1: plum
    ("#2d4a3b", "#42705a", "#22382d"),  # 2: forest
    ("#4a3b2d", "#705a42", "#382d22"),  # 3: amber-brown
    ("#4a2d3b", "#704260", "#382230"),  # 4: mauve
    ("#2d3b4a", "#425a70", "#223038"),  # 5: slate blue
    ("#3b4a2d", "#5a7042", "#303822"),  # 6: olive
    ("#4a3030", "#705050", "#382424"),  # 7: wine
]

_DEFAULT_BG = BG_CARD


class ScheduleItem(QFrame):
    """A single schedule row — displays reference and translation."""

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    # One of two routes to the same event; see
    # SchedulePanel._emit_item_double_clicked.
    delete_requested = pyqtSignal()
    rename_requested = pyqtSignal()
    theme_change_requested = pyqtSignal(str)
    renamed = pyqtSignal()  # Emitted when rename is confirmed
    delete_requested = pyqtSignal()

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._data = data
        self._editing = False

        ref = data.get("ref", "")
        translation = data.get("translation", "")

        is_slide = data.get("item_type") == "slide"
        if is_slide:
            # Freeform decks: anything can be in one, so no music note and
            # no slide count — just the title.
            display = data.get("name") or ref or "(untitled)"
        else:
            # The translation now lives in its own badge on the right.
            display = data.get("name") or ref

        # Property-based styling keeps selection/hover in QSS. Object-name
        # scoping matters: QLabel inherits QFrame, so a bare `QFrame {}` rule
        # would pad the child labels too.
        self.setObjectName(CARD_OBJECT_NAME)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setProperty("selected", False)
        self.setStyleSheet(card_qss())

        layout = QHBoxLayout(self)
        layout.setContentsMargins(
            SPACE_12 - SELECTED_BAR_WIDTH, SPACE_8, SPACE_12, SPACE_8)
        layout.setSpacing(SPACE_8)

        self._ref_label = QLabel(display)
        # Let the card own hover/press across its whole surface.
        self._ref_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        layout.addWidget(self._ref_label)
        layout.addStretch()

        # Translation badge replaces the old theme tag: the theme is already
        # visible on every output, while the translation is not.
        self._translation_badge = None
        if not is_slide and translation:
            canonical = str(translation).upper()
            badge_name = TRANSLATION_LABELS.get(canonical, canonical)
            self._translation_badge = QLabel(badge_name)
            self._translation_badge.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(self._translation_badge)

        self._edit = QLineEdit()
        self._edit.setVisible(False)
        self._edit.returnPressed.connect(self._finish_rename)
        self._edit.editingFinished.connect(self._finish_rename)
        layout.addWidget(self._edit)
        self.apply_card_fonts()

    def apply_card_fonts(self):
        """Re-read the "schedule.cards" group (family / weight / size)."""
        from ui.app_theme import font_qss

        ref_font = _schedule_card_font(12, 600)
        badge_font = _schedule_card_font(12, 400)
        edit_font = _schedule_card_font(13, 400)
        self._ref_label.setStyleSheet(
            f"color: {TEXT_PRIMARY};{font_qss(ref_font)} background: transparent;")
        if self._translation_badge is not None:
            translation = str(self._data.get("translation", "")).upper()
            border = TRANSLATION_COLORS.get(translation, TRANSLATION_FALLBACK)
            self._translation_badge.setStyleSheet(
                badge_qss(border, font_qss(badge_font)))
        # Uniform row height: reserve the badge's height even on cards that
        # have no translation (slide decks), so mixed schedules stay aligned.
        self._ref_label.ensurePolished()
        badge_height = (self._ref_label.fontMetrics().height()
                        + 2 * BADGE_PAD_Y + 2 * BADGE_BORDER_WIDTH)
        self.setMinimumHeight(badge_height + 2 * SPACE_8)
        self._edit.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(0, 0, 0, 80);
                color: {WHITE};
                border: 1px solid {SELECTION_BORDER};
                border-radius: 4px;
                padding: 2px 6px;{font_qss(edit_font)}
            }}
        """)

    @property
    def data(self) -> dict:
        return self._data

    def set_name(self, name: str):
        self._data["name"] = name
        self._ref_label.setText(name)

    def set_theme(self, theme: str):
        # The card no longer renders the theme; every output already shows it.
        self._data["theme"] = theme

    def set_selected(self, selected: bool):
        """Update the selected visual state."""
        self.setProperty("selected", selected)
        # Keep the settings-backed type across the property re-polish.
        self.apply_card_fonts()
        self.style().unpolish(self)
        self.style().polish(self)

    def row_size_hint(self):
        """Size hint for the QListWidgetItem: the layout's hint, but never
        shorter than the uniform card minimum."""
        hint = self.sizeHint()
        hint.setHeight(max(hint.height(), self.minimumHeight()))
        return hint

    def set_background(self, color: str):
        """Set the item background color dynamically."""
        self._bg_color = color
        self.setStyleSheet(card_qss(color))

    def start_rename(self):
        self._editing = True
        current = self._data.get("name", self._data.get("ref", ""))
        self._edit.setText(current)
        self._ref_label.setVisible(False)
        self._edit.setVisible(True)
        self._edit.setFocus()
        self._edit.selectAll()

    def _finish_rename(self):
        if not self._editing:
            return
        self._editing = False
        new_name = self._edit.text().strip()
        if new_name:
            self._data["name"] = new_name
            self._ref_label.setText(new_name)
        self._edit.setVisible(False)
        self._ref_label.setVisible(True)
        self.renamed.emit()

    def mousePressEvent(self, event):
        if self._editing:
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            # Don't consume - let QListWidget handle selection naturally
            event.ignore()
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()

    def contextMenuEvent(self, event):
        """Handle right-click: regular menu with Delete. Alt+Right-click handled by SchedulePanel."""
        # Check for Alt modifier — if pressed, forward to SchedulePanel for themes menu
        if event.modifiers() & Qt.KeyboardModifier.AltModifier:
            # Find the parent SchedulePanel
            parent = self.parent()
            while parent and not isinstance(parent, QListWidget):
                parent = parent.parent()
            if parent:
                schedule_panel = parent.parent()
                while schedule_panel and not hasattr(schedule_panel, '_show_themes_menu_for_selection'):
                    schedule_panel = schedule_panel.parent()
                if schedule_panel and hasattr(schedule_panel, '_show_themes_menu_for_selection'):
                    # Select this item if not already selected
                    for i in range(parent.count()):
                        list_item = parent.item(i)
                        if parent.itemWidget(list_item) is self:
                            if not list_item.isSelected():
                                parent.clearSelection()
                                list_item.setSelected(True)
                            break
                    schedule_panel._show_themes_menu_for_selection(event.globalPos())
            return
            
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())

        rename_action = menu.addAction("Rename")
        rename_action.triggered.connect(self.rename_requested.emit)

        self._add_themes_submenu(menu)

        menu.addSeparator()

        delete_action = menu.addAction("Delete")
        delete_action.triggered.connect(self.delete_requested.emit)

        menu.exec(event.globalPos())

    def _add_themes_submenu(self, parent_menu: QMenu):
        """Populate a Themes submenu with human-readable labels."""
        themes_menu = parent_menu.addMenu("Themes")
        current_theme = self._data.get("theme", "default")
        for section, items in _grouped_themes():
            themes_menu.addSection(section)
            for name, theme_data in items:
                label = theme_data.get("label", theme_data.get("name", name))
                action = themes_menu.addAction(label)
                if name == current_theme:
                    action.setCheckable(True)
                    action.setChecked(True)
                action.triggered.connect(lambda checked, n=name: self.theme_change_requested.emit(n))


class SchedulePanel(QWidget):
    """Schedule panel — a VIEW over the shared ScheduleModel.

    All schedule contents live in `core.schedule_model.schedule_model`, so
    every SchedulePanel instance (SCRIPTURE tab, SLIDES tab, ...) renders
    identical items by construction. Selection stays per-instance; the
    color-coding toggle is shared across tabs (one flag, all panels
    converge).
    """

    item_clicked = pyqtSignal(dict)
    item_double_clicked = pyqtSignal(dict)
    item_theme_changed = pyqtSignal(str, str)
    item_renamed = pyqtSignal(str, str)
    items_deleted = pyqtSignal(list)
    schedule_modified = pyqtSignal()  # Emitted when schedule changes
    schedule_loaded = pyqtSignal(str)  # Emitted with file path when loaded

    # Color-coding is shared across tabs: toggling it in SCRIPTURE lights
    # SLIDES too (and vice versa). One class flag + a registry of live
    # panels; instances never diverge.
    _shared_color_enabled = False
    _instances = None  # WeakSet, created on first use (import-time Qt safe)

    def __init__(self, model=None, parent=None):
        super().__init__(parent)
        from core.schedule_model import schedule_model as _default_model
        self._model = model or _default_model
        self._last_double_click_at = 0.0
        self.setStyleSheet(PANEL_BODY_STYLE)
        # Focus ring: drawn by PresentationTab's ring state machine around the
        # schedule wrapper (so it can pair with the work-area ring), not here.

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setStyleSheet(PANEL_HEADER_STYLE)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 6, 12, 6)
        self._title_label = QLabel("Schedule")
        self._title_label.setStyleSheet(panel_header_label_style())
        header_layout.addWidget(self._title_label)
        header_layout.addStretch()

        # Save button
        self._save_btn = QPushButton("Save")
        self._save_btn.setFixedHeight(BUTTON_HEIGHT)
        self._save_btn.setStyleSheet(_header_btn_style)
        self._save_btn.setToolTip("Save schedule to file")
        self._save_btn.clicked.connect(lambda: self.save_schedule())
        header_layout.addWidget(self._save_btn)

        layout.addWidget(header)

        self.list_widget = QListWidget()
        self.list_widget.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget.setDragEnabled(True)
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # QListWidget spacing is per-side: 4 yields the 8 px card gap.
        self.list_widget.setSpacing(SPACE_4)
        self.list_widget.setStyleSheet("QListWidget { padding: 4px; }")
        apply_minimal_scrollbar(self.list_widget)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.model().rowsMoved.connect(self._on_rows_moved)
        self.list_widget.itemSelectionChanged.connect(self._sync_selection_state)
        # Native drop indicator is style/palette-dependent (it rendered in one
        # tab and not the other). We draw our own so every tab looks identical.
        self.list_widget.setDropIndicatorShown(False)
        self._drop_line = QFrame(self.list_widget.viewport())
        self._drop_line.setStyleSheet("background: #ffffff; border: none;")
        self._drop_line.setFixedHeight(2)
        self._drop_line.hide()
        # Event filter for proper multi-select handling + custom drop indicator
        self.list_widget.viewport().installEventFilter(self)
        layout.addWidget(self.list_widget)

        # Color coding toggle (bottom bar) — shared across tabs (see
        # _shared_color_enabled): a new panel opens matching the live state.
        self._color_enabled = SchedulePanel._shared_color_enabled
        bottom_bar = QWidget()
        bottom_bar.setStyleSheet("background: transparent;")
        bottom_layout = QHBoxLayout(bottom_bar)
        bottom_layout.setContentsMargins(8, 4, 8, 4)
        bottom_layout.setSpacing(4)

        self._color_toggle = QPushButton("Color Code")
        self._color_toggle.setCheckable(True)
        self._color_toggle.setChecked(self._color_enabled)
        self._color_toggle.setFixedHeight(BUTTON_HEIGHT)
        self._color_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color_toggle.setStyleSheet(button_qss("secondary"))
        self._color_toggle.clicked.connect(self._toggle_color_coding)
        bottom_layout.addWidget(self._color_toggle)
        bottom_layout.addStretch()

        layout.addWidget(bottom_bar)

        # Ensure schedules directory exists
        _SCHEDULES_DIR.mkdir(parents=True, exist_ok=True)

        # Model subscriptions — every mutation anywhere rebuilds this view
        self._rebuilding = False
        # Qt's own double-click detection on the VIEW: the
        # platform-reliable route. ScheduleItem.mousePressEvent
        # deliberately ignores the left press so the view manages
        # selection, and whether the widget's own mouseDoubleClickEvent is
        # then reached is not something a widget may rely on across
        # platforms. The view emits this one everywhere.
        self.list_widget.itemDoubleClicked.connect(self._on_view_double_clicked)

        self._model.items_changed.connect(self._rebuild)
        self._model.items_changed.connect(lambda: self.schedule_modified.emit())
        self._model.file_changed.connect(self._update_title)
        self._rebuild()
        self._update_title()
        # Join the cross-tab registry (WeakSet: dead panels drop out on
        # their own). Construction already converged on the shared flag,
        # and _rebuild() above painted accordingly.
        import weakref as _weakref
        if SchedulePanel._instances is None:
            SchedulePanel._instances = _weakref.WeakSet()
        SchedulePanel._instances.add(self)
        # Settings → Interface changes land while the app is running.
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    # ── Settings-backed type ──────────────────────────────────────────────

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "panel.labels":
            self._title_label.setStyleSheet(panel_header_label_style())
        elif prefix == "schedule.cards":
            self.apply_card_fonts()

    def apply_card_fonts(self):
        """Push the schedule-card font group onto every live row."""
        for i in range(self.list_widget.count()):
            li = self.list_widget.item(i)
            widget = li.data(Qt.ItemDataRole.UserRole + 1) if li else None
            if widget is not None and hasattr(widget, "apply_card_fonts"):
                widget.apply_card_fonts()
                li.setSizeHint(widget.row_size_hint())

    # ── Model-backed view ──────────────────────────────────────────────────

    def _on_view_double_clicked(self, list_item):
        """QListWidget.itemDoubleClicked — the platform-independent route."""
        widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
        if widget is not None and hasattr(widget, "data"):
            self._emit_item_double_clicked(widget.data)

    def _emit_item_double_clicked(self, data: dict):
        """Emit item_double_clicked exactly once per double-click.

        Two routes deliver this event — the row widget's own
        mouseDoubleClickEvent and the view's itemDoubleClicked — and
        depending on the platform only one of them fires, or on some both
        do. Firing twice would push the verse to live twice; firing zero
        times is the bug being fixed (the stale deck stayed on live, and
        prev/next then walked THAT deck's slides instead of the adjacent
        verse). Collapse both routes here so the outcome is identical
        everywhere.
        """
        now = time.monotonic()
        if (now - self._last_double_click_at) * 1000.0 \
                <= QApplication.doubleClickInterval():
            return
        self._last_double_click_at = now
        self.item_double_clicked.emit(data)

    def _add_widget(self, data: dict):
        """Create row widgets for one model item (no model mutation)."""
        item_widget = ScheduleItem(data)
        item_widget.clicked.connect(lambda: self.item_clicked.emit(item_widget.data))
        item_widget.double_clicked.connect(
            lambda: self._emit_item_double_clicked(item_widget.data))
        item_widget.rename_requested.connect(lambda: self._start_rename(item_widget))
        item_widget.theme_change_requested.connect(lambda theme: self._change_theme(item_widget, theme))
        item_widget.delete_requested.connect(lambda: self._delete_item_widget(item_widget))
        item_widget.renamed.connect(lambda: self._push_rename(item_widget))

        list_item = QListWidgetItem()
        list_item.setFlags(list_item.flags() | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
        list_item.setSizeHint(item_widget.row_size_hint())
        # Uid only — Qt copies UserRole values; the widget holds the live dict
        list_item.setData(Qt.ItemDataRole.UserRole, data.get("_sched_uid"))
        list_item.setData(Qt.ItemDataRole.UserRole + 1, item_widget)
        self.list_widget.addItem(list_item)
        self.list_widget.setItemWidget(list_item, item_widget)

        item_widget.setProperty("selected", list_item.isSelected())
        item_widget.style().unpolish(item_widget)
        item_widget.style().polish(item_widget)

    def _rebuild(self):
        """Re-render all rows from the model, preserving selection by uid
        and the scroll position (adds must not throw the view to top)."""
        if self._rebuilding:
            return
        self._rebuilding = True
        bar = self.list_widget.verticalScrollBar()
        pos = bar.value()
        at_bottom = pos >= bar.maximum()
        try:
            selected = set()
            for item in self.list_widget.selectedItems():
                w = item.data(Qt.ItemDataRole.UserRole + 1)
                if w is not None and hasattr(w, "data"):
                    uid = w.data.get("_sched_uid")
                    if uid:
                        selected.add(uid)
            self.list_widget.clear()
            for data in self._model.get_items():
                self._add_widget(data)
            for i in range(self.list_widget.count()):
                li = self.list_widget.item(i)
                w = li.data(Qt.ItemDataRole.UserRole + 1)
                if w is not None and w.data.get("_sched_uid") in selected:
                    li.setSelected(True)
            if self._color_enabled:
                self._assign_colors()
            self._sync_selection_state()
            # At the bottom: track the new bottom (fresh rows visible).
            # Anywhere else: absolute position (viewpoint preserved).
            bar.setValue(bar.maximum() if at_bottom else min(pos, bar.maximum()))
        finally:
            self._rebuilding = False

    def add_item(self, data: dict):
        """Append an item to the shared schedule (all panels update)."""
        return self._model.add_item(data)

    def get_schedule(self) -> list:
        """Return all schedule items (live model dicts)."""
        return self._model.get_items()

    def _find_list_item_for_widget(self, item_widget: ScheduleItem) -> QListWidgetItem | None:
        """Find the QListWidgetItem that wraps the given ScheduleItem."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            if list_item.data(Qt.ItemDataRole.UserRole + 1) is item_widget:
                return list_item
        return None

    def _start_rename(self, item_widget: ScheduleItem):
        item_widget.start_rename()
        self.item_renamed.emit(
            str(id(item_widget)),
            item_widget.data.get("name", item_widget.data.get("ref", ""))
        )

    def _delete_item_widget(self, item_widget: ScheduleItem):
        """Delete a single schedule item by widget reference."""
        uid = item_widget.data.get("_sched_uid")
        if not uid:
            return
        removed = self._model.remove_uids([uid])
        if removed:
            self.items_deleted.emit(removed)

    def _push_rename(self, item_widget: ScheduleItem):
        """Push a finished inline rename into the shared model."""
        uid = item_widget.data.get("_sched_uid")
        if uid:
            self._model.update_item(uid, item_widget.data)

    def _change_theme(self, item_widget: ScheduleItem, theme: str):
        item_widget.set_theme(theme)
        uid = item_widget.data.get("_sched_uid")
        if uid:
            self._model.patch_item(uid, theme=theme)
        self.item_theme_changed.emit(str(id(item_widget)), theme)

    def _on_rows_moved(self, *args):
        if self._rebuilding:
            return
        uids = []
        for i in range(self.list_widget.count()):
            uid = self.list_widget.item(i).data(Qt.ItemDataRole.UserRole)
            if uid:
                uids.append(uid)
        if len(uids) == len(self._model.get_items()):
            self._model.set_order(uids)

    # ─── Color coding ────────────────────────────────────────────────────────

    def _toggle_color_coding(self, checked: bool):
        """Toggle color coding on/off — shared across tabs: every live
        SchedulePanel converges on the new state (setChecked emits
        toggled, not clicked, so this never recurses)."""
        SchedulePanel._shared_color_enabled = checked
        for panel in list(SchedulePanel._instances or ()):
            try:
                panel._color_enabled = checked
                panel._color_toggle.setChecked(checked)
                if checked:
                    panel._assign_colors()
                else:
                    panel._clear_colors()
            except RuntimeError:
                pass  # panel mid-teardown; the WeakSet drops it

    def _assign_colors(self):
        """Assign background colors to schedule items based on the card above.

        Rules (positional, not identity-based):
        - Same book + same chapter as previous → same shade
        - Same book + different chapter → different shade of same color
        - Different book → next color in sequence
        """
        if not self._color_enabled:
            return

        color_idx = 0
        color_idx_at = 0
        prev_book = None
        prev_chapter = None
        chapter_idx = 0

        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if not item_widget:
                continue
            data = item_widget.data if item_widget else None
            # Decks are exempt from color coding: every freeform deck is
            # its own thing, so grouping colors are meaningless for them.
            if data and data.get("item_type") == "slide":
                item_widget.set_background(_DEFAULT_BG)
                continue
            book = data.get("book") if data else ""
            chapter = (data.get("chapter", "") if data else "") or (data.get("section", "") if data else "")

            if book != prev_book:
                # Different book → next color in sequence
                color_idx_at = color_idx % len(_BOOK_COLORS)
                color_idx += 1
                chapter_idx = 0
                prev_book = book
                prev_chapter = chapter
            elif chapter != prev_chapter:
                # Same book, different chapter → different shade
                chapter_idx += 1
                prev_chapter = chapter
            # else: same book + same chapter → keep same shade

            palette = _BOOK_COLORS[color_idx_at]
            shade = palette[chapter_idx % len(palette)]
            item_widget.set_background(shade)

    def _clear_colors(self):
        """Reset all items to the default background."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if item_widget:
                item_widget.set_background(_DEFAULT_BG)

    def _sync_selection_state(self):
        """Sync ScheduleItem's 'selected' property with QListWidget's selection."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            item_widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if item_widget:
                selected = list_item.isSelected()
                if item_widget.property("selected") != selected:
                    item_widget.setProperty("selected", selected)
                    item_widget.style().unpolish(item_widget)
                    item_widget.style().polish(item_widget)

    def contextMenuEvent(self, event):
        """Handle context menu on the list widget."""
        pos = event.pos()
        self._on_context_menu(pos)

    def _on_context_menu(self, pos):
        """Handle context menu on the list widget."""
        item = self.list_widget.itemAt(pos)
        if item:
            item_widget = item.data(Qt.ItemDataRole.UserRole + 1)
            # Check if Alt is pressed for themes menu
            from PyQt6.QtWidgets import QApplication
            if QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
                if item_widget:
                    # Select this item if not already selected
                    if not item.isSelected():
                        self.list_widget.clearSelection()
                        item.setSelected(True)
                self._show_themes_menu_for_selection(self.list_widget.mapToGlobal(pos))
                return
        # Regular right-click on empty space or item - could add a menu here if needed
        pass
        # If no item or empty space, we could show a menu too (optional)

    def keyPressEvent(self, event):
        """Handle key events: Delete for multi-delete, Ctrl+A for select all."""
        if event.key() == Qt.Key.Key_Delete:
            self._delete_selected_items()
        elif event.key() == Qt.Key.Key_A and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.list_widget.selectAll()
        else:
            super().keyPressEvent(event)

    def _delete_selected_items(self):
        """Delete all currently selected schedule items."""
        uids = []
        for item in self.list_widget.selectedItems():
            widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if widget is not None and hasattr(widget, "data"):
                uid = widget.data.get("_sched_uid")
                if uid:
                    uids.append(uid)
        if not uids:
            return
        removed = self._model.remove_uids(uids)
        if removed:
            self.items_deleted.emit(removed)

    def _sync_selection_state(self):
        """Sync the visual selected state of all schedule item widgets."""
        for i in range(self.list_widget.count()):
            list_item = self.list_widget.item(i)
            widget = list_item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                selected = list_item.isSelected()
                widget.set_selected(selected)

    def eventFilter(self, watched, event):
        """Event filter to handle mouse events for proper selection with custom item widgets."""
        if watched is self.list_widget.viewport() and event.type() == event.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton:
                # Get the item at the click position
                item = self.list_widget.itemAt(event.pos())
                if item:
                    item_widget = item.data(Qt.ItemDataRole.UserRole + 1)
                    if item_widget:
                        # Emit clicked signal for preview update
                        item_widget.clicked.emit()
                        # Let the list widget handle selection natively
                        # (don't return True here - let event propagate to list widget)
                # Don't consume the event - let the list widget handle selection
        if watched is self.list_widget.viewport():
            if event.type() in (event.Type.DragEnter, event.Type.DragMove):
                # Schedule rows are uid-unique: Alt must never flip a
                # move into a copy-drop that clones the item.
                event.setDropAction(Qt.DropAction.MoveAction)
            if event.type() == event.Type.DragMove:
                self._update_drop_indicator(event.position().toPoint())
            elif event.type() in (event.Type.DragLeave, event.Type.Drop):
                self._drop_line.hide()
        return super().eventFilter(watched, event)

    def _update_drop_indicator(self, pos):
        """Position the white drop line at the would-be drop location."""
        viewport = self.list_widget.viewport()
        index = self.list_widget.indexAt(pos)
        if not index.isValid():
            if self.list_widget.count() == 0:
                self._drop_line.hide()
                return
            last = self.list_widget.model().index(self.list_widget.count() - 1, 0)
            y = self.list_widget.visualRect(last).bottom() + 1
        else:
            rect = self.list_widget.visualRect(index)
            indicator = self.list_widget.dropIndicatorPosition()
            if indicator == QAbstractItemView.DropIndicatorPosition.AboveItem:
                y = rect.top() - 1
            elif indicator == QAbstractItemView.DropIndicatorPosition.BelowItem:
                y = rect.bottom() + 1
            elif indicator == QAbstractItemView.DropIndicatorPosition.OnItem:
                y = rect.bottom() + 1
            else:  # OnViewport
                self._drop_line.hide()
                return
        self._drop_line.setGeometry(6, y, viewport.width() - 12, 2)
        self._drop_line.show()
        self._drop_line.raise_()

    def _show_themes_menu_for_selection(self, global_pos):
        """Show themes menu that applies to all selected items."""
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return
        
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())

        # Show current theme of first selected item as checked (for reference)
        first_widget = selected_items[0].data(Qt.ItemDataRole.UserRole + 1)
        current_theme = first_widget.data.get("theme", "default") if first_widget else "default"

        for section, items in _grouped_themes():
            menu.addSection(section)
            for name, theme_data in items:
                label = theme_data.get("label", theme_data.get("name", name))
                action = menu.addAction(label)
                if name == current_theme:
                    action.setCheckable(True)
                    action.setChecked(True)
                action.triggered.connect(lambda checked, n=name: self._apply_theme_to_selection(n))
        
        menu.exec(global_pos)

    def _apply_theme_to_selection(self, theme: str):
        """Apply a theme to all selected schedule items."""
        for item_widget in self._get_selected_item_widgets():
            item_widget.set_theme(theme)
            uid = item_widget.data.get("_sched_uid")
            if uid:
                self._model.patch_item(uid, theme=theme)
            self.item_theme_changed.emit(str(id(item_widget)), theme)

    def _get_selected_item_widgets(self) -> list:
        """Get list of ScheduleItem widgets for currently selected items."""
        widgets = []
        for item in self.list_widget.selectedItems():
            widget = item.data(Qt.ItemDataRole.UserRole + 1)
            if widget:
                widgets.append(widget)
        return widgets

    # ── Schedule Filing (delegates to the shared model) ───────────────────

    def _update_title(self):
        """Update the header title to show current schedule name."""
        current_file = self._model.current_file
        if current_file:
            name = Path(current_file).stem
            if self._model.is_modified:
                name += " *"
        else:
            name = "Schedule"
        self._title_label.setText(name)

    @property
    def is_modified(self) -> bool:
        return self._model.is_modified

    @property
    def current_file(self) -> str | None:
        return self._model.current_file

    def get_schedule_data(self) -> list:
        """Return schedule items as a list of dicts for serialization."""
        return self._model.get_serializable()

    def save_schedule(self, file_path: str = None) -> bool:
        """Save the current schedule to a JSON file. Returns True on success."""
        if file_path is None:
            file_path = self._model.current_file

        if file_path is None:
            # No file yet — prompt user
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Schedule", str(_SCHEDULES_DIR),
                "Schedule Files (*.json);;All Files (*)"
            )
            if not file_path:
                return False  # User cancelled
            if not file_path.endswith(".json"):
                file_path += ".json"

        saved = self._model.save(file_path)
        if saved is None:
            dialogs.critical(self, "Save Error", f"Could not save schedule:\n{file_path}")
            return False
        return True

    def load_schedule(self, file_path: str = None) -> bool:
        """Load a schedule from a JSON file. Returns True on success."""
        if file_path is None:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Open Schedule", str(_SCHEDULES_DIR),
                "Schedule Files (*.json);;All Files (*)"
            )
            if not file_path:
                return False  # User cancelled

        if not self._model.load(file_path):
            dialogs.critical(self, "Load Error", f"Could not load schedule:\n{file_path}")
            return False
        self.schedule_loaded.emit(file_path)
        return True

    def clear_all(self, silent: bool = False):
        """Clear all schedule items."""
        if not silent and self._model.is_modified:
            reply = dialogs.question(
                self, "Unsaved Changes",
                "The current schedule has unsaved changes. Clear anyway?",
                dialogs.Yes | dialogs.No,
                dialogs.No
            )
            if reply == dialogs.No:
                return

        self._model.clear()

    def list_schedules(self) -> list:
        """Return list of available schedule files sorted by last modified (newest first)."""
        return self._model.list_schedules()
