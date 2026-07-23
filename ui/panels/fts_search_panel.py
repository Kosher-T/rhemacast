"""
ui/panels/fts_search_panel.py

Compact FTS5 + BM25 hybrid search across 6 translations.
Results ordered by relevance. Translation badges + Send button.
Single-click → navigator, double-click → push to live.
"""

import logging
import re
import time
from typing import List, Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QPushButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QWheelEvent

from ui.styles import (
    PANEL_BODY_STYLE, SHOW_BTN_STYLE,
    CYAN_400, SLATE_300, SLATE_400, SLATE_500, SLATE_600, SLATE_800,
    WHITE, BORDER_SUBTLE
)
from core.bible_service import hybrid_search

logger = logging.getLogger(__name__)

FTS_TRANSLATIONS = ["KJV", "NKJV", "ESV", "NLT", "AMP", "BSB"]

_CLICK_DELAY = 250
_ROW_HEIGHT = 48


class _FtsResultsList(QListWidget):
    """QListWidget that scrolls exactly one row per wheel notch."""

    def wheelEvent(self, event: QWheelEvent):
        vbar = self.verticalScrollBar()
        if not vbar or vbar.maximum() == vbar.minimum():
            super().wheelEvent(event)
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            return
        direction = -1 if delta > 0 else 1
        vbar.setValue(max(0, vbar.value() + direction))


class _TransBadge(QLabel):
    """Compact translation badge with single/double click."""

    single_clicked = pyqtSignal(str, dict)
    double_clicked = pyqtSignal(str, dict)

    def __init__(self, version: str, verse_data: dict, parent=None):
        super().__init__(version, parent)
        self._version = version
        self._verse_data = verse_data
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(_CLICK_DELAY)
        self._click_timer.timeout.connect(self._on_single)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QLabel {{
                color: {SLATE_400};
                font-size: 8px;
                font-weight: 700;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 3px;
                padding: 1px 4px;
            }}
            QLabel:hover {{
                color: {WHITE};
                background: rgba(34, 211, 238, 0.15);
            }}
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
                self.double_clicked.emit(self._version, self._verse_data)
            else:
                self._click_timer.start()
        super().mousePressEvent(event)

    def _on_single(self):
        self.single_clicked.emit(self._version, self._verse_data)


class _ResultRow(QFrame):
    """Compact result row: ref + text + translation badges + Send."""

    send_to_schedule = pyqtSignal(dict)
    navigate_requested = pyqtSignal(dict)
    live_requested = pyqtSignal(dict)
    trans_single = pyqtSignal(str, dict)
    trans_double = pyqtSignal(str, dict)

    def __init__(self, data: dict, query: str, parent=None):
        super().__init__(parent)
        self._data = data
        self.setFixedHeight(_ROW_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 0 4px;
            }}
            QFrame:hover {{
                background: rgba(255, 255, 255, 0.03);
                border-color: {BORDER_SUBTLE};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)

        # Reference
        ref = f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}"
        ref_label = QLabel(ref)
        ref_label.setFixedWidth(65)
        ref_label.setStyleSheet(f"color: {CYAN_400}; font-size: 9px; font-weight: 700;")
        layout.addWidget(ref_label)

        # Scripture text with keyword highlighting
        text_label = QLabel()
        text_label.setStyleSheet(f"color: {SLATE_300}; font-size: 10px; background: transparent;")
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setWordWrap(False)
        layout.addWidget(text_label, 1)

        text = data.get("text", "")
        if query and text:
            safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            words = query.split()
            if words:
                pattern = "|".join(r"\b" + re.escape(w) + r"\b" for w in words)
                try:
                    highlighted = re.sub(
                        pattern,
                        lambda m: f'<span style="background:rgba(34,211,238,0.25);color:{WHITE};border-radius:2px;">{m.group()}</span>',
                        safe,
                        flags=re.IGNORECASE
                    )
                except re.error:
                    highlighted = safe
                text_label.setText(highlighted)
            else:
                text_label.setText(safe)
        else:
            text_label.setText(text)

        # Translation badge (only the one whose text is displayed)
        translations = data.get("translations", [])
        if translations:
            t = translations[0]
            badge = _TransBadge(t["version"], t)
            badge.single_clicked.connect(self.trans_single.emit)
            badge.double_clicked.connect(self.trans_double.emit)
            layout.addWidget(badge)

        # Send button
        send_btn = QPushButton("Send")
        send_btn.setStyleSheet(f"""
            QPushButton {{
                color: {WHITE};
                font-size: 9px;
                font-weight: 600;
                background: rgba(34, 211, 238, 0.15);
                border: none;
                border-radius: 3px;
                padding: 2px 8px;
            }}
            QPushButton:hover {{
                background: rgba(34, 211, 238, 0.3);
            }}
        """)
        send_btn.setFixedWidth(40)
        send_btn.setFixedHeight(20)
        send_btn.setToolTip("Add this verse to the schedule")
        send_btn.clicked.connect(lambda: self.send_to_schedule.emit(self._data))
        layout.addWidget(send_btn)

        # Click handlers — timer-based single/double click
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(_CLICK_DELAY)
        self._click_timer.timeout.connect(self._on_single_click)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
                self.live_requested.emit(self._data)
            else:
                self._click_timer.start()
        super().mousePressEvent(event)

    def _on_single_click(self):
        self.navigate_requested.emit(self._data)


class FtsSearchPanel(QWidget):
    """Compact FTS search across 6 translations, ordered by relevance."""

    verse_to_schedule = pyqtSignal(dict)
    verse_to_navigator = pyqtSignal(dict)
    verse_to_live = pyqtSignal(dict)
    trans_badge_to_navigator = pyqtSignal(dict)
    trans_badge_to_live = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self.setAccessibleName("FTS Search Panel")
        self.setAccessibleDescription("Search Bible verses across 6 translations using FTS5 full-text search")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        header.setSpacing(6)
        icon = QLabel("\u2315")
        icon.setStyleSheet(f"color: {CYAN_400}; font-size: 16px; font-weight: 700;")
        header.addWidget(icon)
        title = QLabel("FTS")
        title.setStyleSheet(f"color: {WHITE}; font-size: 12px; font-weight: 700;")
        header.addWidget(title)
        header.addStretch()
        self.trans_label = QLabel("6 translations")
        self.trans_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px;")
        header.addWidget(self.trans_label)
        layout.addLayout(header)

        # Search input
        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("Search all translations...")
        self.query_input.setAccessibleName("FTS search query")
        self.query_input.setAccessibleDescription("Type a Bible verse reference or text to search across all translations")
        self.query_input.setStyleSheet(f"""
            QLineEdit {{
                background: {SLATE_800};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 4px;
                padding: 4px 8px;
                color: {WHITE};
                font-size: 11px;
            }}
            QLineEdit:focus {{
                border-color: {CYAN_400};
            }}
        """)
        self.query_input.returnPressed.connect(self._on_search)
        layout.addWidget(self.query_input)

        # Results list
        self.results_list = _FtsResultsList()
        self.results_list.setAccessibleName("FTS search results")
        self.results_list.setAccessibleDescription("List of Bible verse search results ordered by relevance")
        self.results_list.setSpacing(2)
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                padding: 0;
            }}
            QListWidget::item:focus {{
                outline: 2px solid {CYAN_400};
                outline-offset: -2px;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {SLATE_600};
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)
        layout.addWidget(self.results_list, 1)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setAccessibleName("Search status")
        self.status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px;")
        layout.addWidget(self.status_label)

        # Debounce timer
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(200)
        self._debounce_timer.timeout.connect(self._execute_search)
        self.query_input.textChanged.connect(lambda: self._debounce_timer.start())

    def set_translation(self, version: str):
        pass

    def focus_query(self):
        self.query_input.setFocus()
        self.query_input.selectAll()

    def _on_search(self):
        self._debounce_timer.stop()
        self._execute_search()

    def _execute_search(self):
        query = self.query_input.text().strip()
        if not query:
            self.results_list.clear()
            self.status_label.setText("")
            return

        t0 = time.monotonic()

        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = {pool.submit(hybrid_search, query, trans, 30): trans for trans in FTS_TRANSLATIONS}
            all_results = []
            for future in as_completed(futures):
                trans = futures[future]
                try:
                    for r in future.result():
                        r["version"] = trans
                        all_results.append(r)
                except Exception as e:
                    logger.warning(f"FTS search failed for {trans}: {e}")

        elapsed_ms = (time.monotonic() - t0) * 1000

        # Group by verse reference
        grouped = {}
        for r in all_results:
            ref = f"{r['book']} {r['chapter']}:{r['verse']}"
            if ref not in grouped:
                grouped[ref] = {
                    "book": r["book"],
                    "chapter": str(r["chapter"]),
                    "verse_num": str(r["verse"]),
                    "text": r["text"],
                    "confidence": r.get("confidence", 0),
                    "translations": [],
                }
            grouped[ref]["translations"].append({
                "version": r["version"],
                "text": r["text"],
                "book": r["book"],
                "chapter": str(r["chapter"]),
                "verse_num": str(r["verse"]),
            })
            grouped[ref]["confidence"] = max(
                grouped[ref]["confidence"],
                r.get("confidence", 0)
            )

        # Sort by relevance (confidence descending)
        sorted_verses = sorted(grouped.values(), key=lambda v: v["confidence"], reverse=True)

        self.results_list.clear()
        for v in sorted_verses:
            item = QListWidgetItem()
            widget = _ResultRow(v, query)
            widget.send_to_schedule.connect(self.verse_to_schedule.emit)
            widget.navigate_requested.connect(self.verse_to_navigator.emit)
            widget.live_requested.connect(self.verse_to_live.emit)
            widget.trans_single.connect(self._on_trans_single)
            widget.trans_double.connect(self._on_trans_double)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)
            item.setSizeHint(QSize(200, _ROW_HEIGHT))

        self.status_label.setText(
            f"{len(sorted_verses)} verses across {len(FTS_TRANSLATIONS)} translations ({elapsed_ms:.0f}ms)"
        )

    def _on_trans_single(self, version: str, data: dict):
        """Single-click on translation badge → navigate in that translation."""
        self.trans_badge_to_navigator.emit(data)

    def _on_trans_double(self, version: str, data: dict):
        """Double-click on translation badge → push to live in that translation."""
        self.trans_badge_to_live.emit(data)

    def clear_results(self):
        self.results_list.clear()
        self.query_input.clear()
        self.status_label.setText("")