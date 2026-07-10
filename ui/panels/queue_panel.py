"""
ui/panels/queue_panel.py

Operator review queue: shows auto-detected verse matches from Thread 3.
Show → fires broadcast_display() + Stage 3 DB log.
Reject → discards and frees memory.
Limited to 50 visible items (virtual scrolling).
"""

import asyncio
import logging
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QStackedWidget, QToolTip
)
from PyQt6.QtCore import Qt, pyqtSignal, QPoint

from ui.styles import (
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    QUEUE_ITEM_STYLE, SHOW_BTN_STYLE, REJECT_BTN_STYLE,
    CYAN_400, SLATE_300, SLATE_500, SLATE_600, WHITE, BORDER_SUBTLE
)
from core.queues import db_write_queue
from core.bible_service import get_display_name

logger = logging.getLogger(__name__)

MAX_VISIBLE_ITEMS = 50


class _TabButton(QPushButton):
    """QPushButton that shows a tooltip on hover via QToolTip.showText."""

    def __init__(self, icon: str, tooltip: str, parent=None):
        super().__init__(icon, parent)
        self._tooltip_text = tooltip
        self.setMouseTracking(True)

    def enterEvent(self, event):
        pos = self.mapToGlobal(QPoint(self.width() // 2, self.height()))
        QToolTip.showText(pos, self._tooltip_text, self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)


class QueueItemWidget(QFrame):
    """A single verse match in the operator review queue."""

    show_clicked = pyqtSignal(dict)
    reject_clicked = pyqtSignal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self.setStyleSheet(QUEUE_ITEM_STYLE)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(8)

        # Confidence dot
        conf = data.get("confidence", 0)
        dot_color = CYAN_400 if conf >= 85 else SLATE_600
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {dot_color}; font-size: 8px;")
        dot.setFixedWidth(12)
        layout.addWidget(dot)

        # Verse ref
        ref_text = f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}"
        ref_label = QLabel(ref_text)
        ref_label.setStyleSheet(f"color: {SLATE_300}; font-size: 11px; font-weight: 700;")
        ref_label.setToolTip(data.get("text", ""))
        layout.addWidget(ref_label)

        layout.addStretch()

        # Confidence %
        conf_label = QLabel(f"{conf:.0f}%")
        conf_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; font-weight: 600;")
        conf_label.setToolTip("Confidence threshold: verses above this go to the review queue")
        layout.addWidget(conf_label)

        # Show
        show_btn = QPushButton("Show")
        show_btn.setStyleSheet(SHOW_BTN_STYLE)
        show_btn.setToolTip("Broadcast this verse to the live display output")
        show_btn.setFixedWidth(50)
        show_btn.clicked.connect(lambda: self.show_clicked.emit(self.data))
        layout.addWidget(show_btn)

        # Reject
        reject_btn = QPushButton("✕")
        reject_btn.setStyleSheet(REJECT_BTN_STYLE)
        reject_btn.setToolTip("Discard this suggestion from the queue")
        reject_btn.setFixedWidth(28)
        reject_btn.clicked.connect(lambda: self.reject_clicked.emit(self.data))
        layout.addWidget(reject_btn)


class QueuePanel(QWidget):
    """Operator review queue panel with sub-tab switching (QUEUE | THEMES | SEARCH)."""

    # Emitted when the operator clicks "Show" on a verse
    display_requested = pyqtSignal(dict)
    # Emitted when operator selects a display theme (single-click)
    theme_changed = pyqtSignal(str)
    # Emitted when operator double-clicks a theme
    theme_double_clicked = pyqtSignal(str)
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

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        # ── Vertical tab bar (left side) ──
        tab_bar = QWidget()
        tab_bar.setFixedWidth(48)
        tab_bar.setStyleSheet(PANEL_HEADER_STYLE)
        tab_layout = QVBoxLayout(tab_bar)
        tab_layout.setContentsMargins(4, 8, 4, 8)
        tab_layout.setSpacing(4)

        self._tab_buttons: dict[str, QPushButton] = {}
        self._active_tab = "queue"

        for tab_name, icon, tooltip in [
            ("queue", "\u2261", "Queue"),
            ("themes", "\u25C9", "Themes"),
            ("search", "\u2315", "Search"),
        ]:
            btn = _TabButton(icon, tooltip)
            btn.setCheckable(True)
            btn.setChecked(tab_name == "queue")
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(self._tab_style(tab_name == "queue"))
            btn.clicked.connect(lambda checked, n=tab_name: self._switch_tab(n))
            tab_layout.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self._tab_buttons[tab_name] = btn

        tab_layout.addStretch()

        # Item count
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px; font-weight: 600;")
        tab_layout.addWidget(self.count_label, 0, Qt.AlignmentFlag.AlignHCenter)

        body.addWidget(tab_bar)

        # ── Stacked content (right side) ──
        self._stack = QStackedWidget()

        # Queue list (index 0)
        self.list_widget = QListWidget()
        self.list_widget.setSpacing(4)
        self.list_widget.setStyleSheet("QListWidget { padding: 6px; }")
        self._stack.addWidget(self.list_widget)

        # Themes panel (index 1) — lazy loaded
        self._themes_panel = None
        self._themes_index = -1

        # Search panel (index 2) — lazy loaded
        self._search_panel = None
        self._search_index = -1

        body.addWidget(self._stack, 1)

        layout.addLayout(body, 1)

    def _tab_style(self, active: bool) -> str:
        if active:
            return f"""
                QPushButton {{
                    color: {CYAN_400};
                    font-size: 11px; font-weight: 700;
                    background: rgba(34, 211, 238, 0.1);
                    border-radius: 6px;
                    border: none;
                }}
            """
        return f"""
            QPushButton {{
                color: {SLATE_500};
                font-size: 11px; font-weight: 700;
                background: transparent;
                border-radius: 6px;
                border: none;
            }}
            QPushButton:hover {{
                color: {WHITE};
                background: rgba(255, 255, 255, 5);
            }}
        """

    def _switch_tab(self, name: str):
        if name == self._active_tab:
            return

        # Update button styles
        for tab_name, btn in self._tab_buttons.items():
            btn.setChecked(tab_name == name)
            btn.setStyleSheet(self._tab_style(tab_name == name))

        self._active_tab = name

        if name == "queue":
            self._stack.setCurrentIndex(0)
            self.count_label.setVisible(True)
        elif name == "themes":
            self._ensure_themes_loaded()
            self._stack.setCurrentIndex(self._themes_index)
            self.count_label.setVisible(False)
        elif name == "search":
            self._ensure_search_loaded()
            self._stack.setCurrentIndex(self._search_index)
            self.count_label.setVisible(False)

    def _ensure_themes_loaded(self):
        if self._themes_panel is None:
            from ui.panels.themes_panel import ThemesPanel
            self._themes_panel = ThemesPanel()
            self._themes_panel.theme_changed.connect(self.theme_changed)
            self._themes_panel.theme_double_clicked.connect(self.theme_double_clicked)
            self._themes_index = self._stack.addWidget(self._themes_panel)

    def _ensure_search_loaded(self):
        if self._search_panel is None:
            from ui.panels.search_panel import SearchPanel
            self._search_panel = SearchPanel()
            self._search_panel.verse_to_schedule.connect(self.verse_to_schedule)
            self._search_panel.verse_to_navigator.connect(self.verse_to_navigator)
            self._search_panel.verse_to_live.connect(self.verse_to_live)
            self._search_panel.trans_badge_to_navigator.connect(self.trans_badge_to_navigator)
            self._search_panel.trans_badge_to_live.connect(self.trans_badge_to_live)
            self._search_index = self._stack.addWidget(self._search_panel)

    def switch_to_search(self):
        """Programmatically switch to the search tab and focus the query input."""
        self._switch_tab("search")
        if self._search_panel:
            self._search_panel.focus_query()

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
