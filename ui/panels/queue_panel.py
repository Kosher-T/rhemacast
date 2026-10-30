"""
ui/panels/queue_panel.py

Operator review queue: shows auto-detected verse matches from Thread 3.
Show → fires broadcast_display() + Stage 3 DB log.
Reject → discards and frees memory.
Limited to 50 visible items (virtual scrolling).
"""

import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QStackedWidget
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    PANEL_BODY_STYLE, QUEUE_ITEM_STYLE, SHOW_BTN_STYLE, REJECT_BTN_STYLE,
    SLATE_300, SLATE_600,
)
from ui.tokens import (
    TEXT_MUTED, TYPE_CAPTION, WEIGHT_SEMIBOLD,
)
from core.queues import db_write_queue
from core.bible_service import get_display_name

logger = logging.getLogger(__name__)

MAX_VISIBLE_ITEMS = 50


class QueueItemWidget(QFrame):
    """A single verse match in the operator review queue."""

    show_clicked = pyqtSignal(dict)
    reject_clicked = pyqtSignal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setStyleSheet(QUEUE_ITEM_STYLE)
        self.setAccessibleName(f"Queue item: {data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}")
        self.setAccessibleDescription(f"Confidence {data.get('confidence', 0):.0f}%. Press Enter to show, Delete to reject.")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Confidence dot
        conf = data.get("confidence", 0)
        dot_color = CYAN_400 if conf >= 85 else SLATE_600
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 12px;")
        dot.setFixedWidth(12)
        layout.addWidget(dot)

        # Verse ref
        ref_text = f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}"
        ref_label = QLabel(ref_text)
        ref_label.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; font-weight: 700;")
        ref_label.setToolTip(data.get("text", ""))
        layout.addWidget(ref_label)

        layout.addStretch()

        # Confidence %
        conf_label = QLabel(f"{conf:.0f}%")
        conf_label.setStyleSheet(f"color: {SLATE_500}; font-size: 12px; font-weight: 600;")
        conf_label.setToolTip("Confidence threshold: verses above this go to the review queue")
        layout.addWidget(conf_label)

        # Show
        show_btn = QPushButton("Show")
        show_btn.setAccessibleName("Show verse")
        show_btn.setAccessibleDescription("Broadcast this verse to the live display output")
        show_btn.setStyleSheet(SHOW_BTN_STYLE)
        show_btn.setToolTip("Broadcast this verse to the live display output (Enter)")
        show_btn.setFixedWidth(50)
        show_btn.clicked.connect(lambda: self.show_clicked.emit(self.data))
        layout.addWidget(show_btn)

        # Reject
        reject_btn = QPushButton()
        reject_btn.setAccessibleName("Reject verse")
        reject_btn.setAccessibleDescription("Discard this suggestion from the queue")
        from ui.icons import apply_button
        apply_button(reject_btn, "close")
        reject_btn.setStyleSheet(REJECT_BTN_STYLE)
        reject_btn.setToolTip("Discard this suggestion from the queue (Delete)")
        reject_btn.setFixedWidth(28)
        reject_btn.clicked.connect(lambda: self.reject_clicked.emit(self.data))
        layout.addWidget(reject_btn)

    def keyPressEvent(self, event):
        """Handle keyboard navigation for accessibility."""
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            self.show_clicked.emit(self.data)
            event.accept()
        elif event.key() == Qt.Key.Key_Delete:
            self.reject_clicked.emit(self.data)
            event.accept()
        else:
            super().keyPressEvent(event)


class QueuePanel(QWidget):
    """Operator review queue panel.

    Sub-pages: Outputs | Keyword | Semantic (plus the internal "queue"
    list, kept for backward compatibility).
    """

    # Emitted when the operator clicks "Show" on a verse
    display_requested = pyqtSignal(dict)
    # Emitted when operator selects a display theme (single-click)
    theme_changed = pyqtSignal(str, str)   # (output_id, theme_name)
    # Emitted when operator double-clicks a theme
    theme_double_clicked = pyqtSignal(str, str)  # (output_id, theme_name)
    # Emitted when operator right-clicks a theme → Quick Edit
    theme_edit_requested = pyqtSignal(str)  # theme_name
    # Emitted when the operator adds/removes an output in the Outputs page
    outputs_changed = pyqtSignal(list)  # active output ids
    # Emitted when operator sends a search result to schedule
    verse_to_schedule = pyqtSignal(dict)
    # Single-click search result → navigate in current browser translation
    verse_to_navigator = pyqtSignal(dict)
    # Double-click search result → send to live in current browser translation
    verse_to_live = pyqtSignal(dict)
    # Single-click translation badge → navigate in result's translation
    trans_badge_to_navigator = pyqtSignal(dict)
    # Double-click translation badge → send to live in result's translation
    trans_badge_to_live = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sub-page tabs (top): Outputs | Keyword | Semantic ──
        # Text buttons, same row style as the Decks panel — the old icon
        # rail read as glyphs and gave no hint what the pages were.
        from ui.panels.text_tabs import build_text_tab_row
        self._active_tab = "outputs"
        # Group id order — the row is exclusive and checkable, so it
        # highlights on its own; WITHOUT this connection the button lights
        # up and nothing else happens (no page switch).
        self._tab_keys = ("outputs", "keyword", "semantic")
        tab_row, self._page_tabs, self._tab_buttons = build_text_tab_row(
            [("outputs", "Outputs", "Per-output display themes"),
             ("keyword", "Keyword", "Keyword search — FTS5, stemmed, "
                                     "across every translation"),
             ("semantic", "Semantic", "Semantic search — describe it in "
                                      "your own words")],
            checked_key="outputs")
        self._page_tabs.idClicked.connect(
            lambda index: self._switch_tab(self._tab_keys[index]))

        # Item count rides the row's right edge (queue page only).
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: {TYPE_CAPTION}px;"
            f" font-weight: {WEIGHT_SEMIBOLD};")
        tab_row.layout().addWidget(self.count_label)
        layout.addWidget(tab_row)

        # ── Stacked content (the open sub-page) ──
        self._stack = QStackedWidget()

        # Queue list (index 0) — hidden, kept for backward compatibility
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("QListWidget { padding: 6px; }")
        self._stack.addWidget(self.list_widget)

        # Outputs (themes) panel — lazy loaded
        self._themes_panel = None
        self._themes_index = -1

        # Keyword (FTS) panel — lazy loaded
        self._fts_search_panel = None
        self._fts_search_index = -1

        # Semantic (fuzzy/FAISS) panel — lazy loaded
        self._fuzzy_search_panel = None
        self._fuzzy_search_index = -1

        # Start on the Outputs page
        self._ensure_themes_loaded()
        self._stack.setCurrentIndex(self._themes_index)
        self.count_label.setVisible(False)

        layout.addWidget(self._stack, 1)

    def _switch_tab(self, name: str):
        """Flip sub-pages: Outputs | Keyword | Semantic (or "queue")."""
        if name == self._active_tab:
            return

        self._active_tab = name
        # The row's buttons drive themselves (exclusive QButtonGroup +
        # :checked QSS); set the checked one for programmatic switches.
        btn = self._tab_buttons.get(name)
        if btn is not None:
            btn.setChecked(True)

        if name == "queue":
            self._stack.setCurrentIndex(0)
            self.count_label.setVisible(True)
        elif name == "outputs":
            self._ensure_themes_loaded()
            self._stack.setCurrentIndex(self._themes_index)
            self.count_label.setVisible(False)
        elif name == "keyword":
            self._ensure_fts_search_loaded()
            self._stack.setCurrentIndex(self._fts_search_index)
            self.count_label.setVisible(False)
            # Clicking the tab is as much "go search" as the hotkey is:
            # hand the operator the box with its text already selected.
            self._fts_search_panel.focus_query()
        elif name == "semantic":
            self._ensure_fuzzy_search_loaded()
            self._stack.setCurrentIndex(self._fuzzy_search_index)
            self.count_label.setVisible(False)
            self._fuzzy_search_panel.focus_query()

    def _ensure_themes_loaded(self):
        if self._themes_panel is None:
            from ui.panels.themes_panel import ThemesPanel
            from core.outputs import active_outputs
            self._themes_panel = ThemesPanel(
                output_ids=active_outputs("SCRIPTURE"), tab_key="SCRIPTURE",
                allow_add_remove=True)
            self._themes_panel.theme_changed.connect(self.theme_changed)
            self._themes_panel.theme_double_clicked.connect(self.theme_double_clicked)
            self._themes_panel.theme_edit_requested.connect(self.theme_edit_requested)
            self._themes_panel.outputs_changed.connect(self.outputs_changed)
            from ui.widgets.scrollable import scrollable
            self._themes_index = self._stack.addWidget(
                scrollable(self._themes_panel))

    def _ensure_fts_search_loaded(self):
        if self._fts_search_panel is None:
            from ui.panels.fts_search_panel import FtsSearchPanel
            self._fts_search_panel = FtsSearchPanel()
            self._fts_search_panel.verse_to_schedule.connect(self.verse_to_schedule)
            self._fts_search_panel.verse_to_navigator.connect(self.verse_to_navigator)
            self._fts_search_panel.verse_to_live.connect(self.verse_to_live)
            self._fts_search_panel.trans_badge_to_navigator.connect(self.trans_badge_to_navigator)
            self._fts_search_panel.trans_badge_to_live.connect(self.trans_badge_to_live)
            self._fts_search_index = self._stack.addWidget(self._fts_search_panel)

    def _ensure_fuzzy_search_loaded(self):
        if self._fuzzy_search_panel is None:
            from ui.panels.search_panel import SearchPanel
            self._fuzzy_search_panel = SearchPanel()
            self._fuzzy_search_panel.verse_to_schedule.connect(self.verse_to_schedule)
            self._fuzzy_search_panel.verse_to_navigator.connect(self.verse_to_navigator)
            self._fuzzy_search_panel.verse_to_live.connect(self.verse_to_live)
            self._fuzzy_search_panel.trans_badge_to_navigator.connect(self.trans_badge_to_navigator)
            self._fuzzy_search_panel.trans_badge_to_live.connect(self.trans_badge_to_live)
            self._fuzzy_search_index = self._stack.addWidget(self._fuzzy_search_panel)

    def switch_to_fts_search(self):
        """Switch to the Keyword search page and focus the query input."""
        self._switch_tab("keyword")
        if self._fts_search_panel:
            self._fts_search_panel.focus_query()

    def switch_to_fuzzy_search(self):
        """Switch to the Semantic search page and focus the query input."""
        self._switch_tab("semantic")
        if self._fuzzy_search_panel:
            self._fuzzy_search_panel.focus_query()

    def set_translation(self, version: str):
        """Forward translation change to the FTS search panel."""
        if self._fts_search_panel:
            self._fts_search_panel.set_translation(version)

    def add_item(self, data: dict):
        """Add a verse match to the review queue."""
        # Enforce 50-item cap
        while self.list_widget.count() >= MAX_VISIBLE_ITEMS:
            self.list_widget.takeItem(self.list_widget.count() - 1)

        widget = QueueItemWidget(data)
        widget.show_clicked.connect(self._on_show)
        widget.reject_clicked.connect(self._on_reject)

        item = QListWidgetItem()
        item.setSizeHint(widget.sizeHint())
        item.setData(Qt.ItemDataRole.UserRole, data)

        # High priority items go to the top
        if data.get("priority") == "high":
            self.list_widget.insertItem(0, item)
        else:
            self.list_widget.addItem(item)
        self.list_widget.setItemWidget(item, widget)

        self.count_label.setText(str(self.list_widget.count()))

    def _on_show(self, data: dict):
        """Operator approved the verse for broadcast."""
        import time

        # Emit display signal
        self.display_requested.emit(data)

        # Stage 3 DB log
        db_write_queue.put({
            "type": "display_event",
            "payload": {
                "action": "operator_approved",
                "ref": f"[{get_display_name(data.get('version',''))}] {data.get('book','')} {data.get('chapter','')}:{data.get('verse_num','')}",
                "confidence": data.get("confidence", 0),
                "timestamp_ms": int(time.time() * 1000)
            }
        })

        # Remove from list
        self._remove_item_by_data(data)

    def _on_reject(self, data: dict):
        """Operator rejected the verse."""
        self._remove_item_by_data(data)

    def _remove_item_by_data(self, data: dict):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == data:
                widget = self.list_widget.itemWidget(item)
                self.list_widget.takeItem(i)
                if widget:
                    widget.deleteLater()
                break
        self.count_label.setText(str(self.list_widget.count()))
