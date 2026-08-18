"""
ui/panels/search_panel.py

Advanced semantic search panel for vague natural language queries.
Uses existing FAISS + BM25 hybrid search infrastructure.
"""

import logging
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QListWidget, QListWidgetItem, QFrame, QApplication
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtGui import QWheelEvent

from ui.styles import (
    PANEL_BODY_STYLE, SHOW_BTN_STYLE,
    CYAN_400, SLATE_300, SLATE_400, SLATE_500, SLATE_600,
    SLATE_800, WHITE, BORDER_SUBTLE
)

logger = logging.getLogger(__name__)

# Delay (ms) to distinguish single-click from double-click
_CLICK_DELAY = 250


class _SearchResultsList(QListWidget):
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
        new_row = max(0, vbar.value() + direction)
        vbar.setValue(new_row)


class _TabButton(QPushButton):
    """Small toggle-style tab button for switching result views."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self._update_style(False)
        self.toggled.connect(lambda checked: self._update_style(checked))

    def _update_style(self, checked: bool):
        if checked:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(34, 211, 238, 0.15);
                    color: {CYAN_400};
                    border: 1px solid rgba(34, 211, 238, 0.3);
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 9px;
                    font-weight: 600;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {SLATE_500};
                    border: 1px solid transparent;
                    border-radius: 4px;
                    padding: 3px 8px;
                    font-size: 9px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    color: {SLATE_300};
                    border: 1px solid {BORDER_SUBTLE};
                }}
            """)


class _TransBadge(QLabel):
    """Translation badge that emits separate signals for single and double clicks."""

    single_clicked = pyqtSignal(str, dict)   # version, verse_data
    double_clicked = pyqtSignal(str, dict)   # version, verse_data

    def __init__(self, version: str, display: str, verse_data: dict, parent=None):
        super().__init__(display, parent)
        self._version = version
        self._verse_data = verse_data
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(_CLICK_DELAY)
        self._click_timer.timeout.connect(self._on_single_click)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._click_timer.isActive():
                self._click_timer.stop()
                self.double_clicked.emit(self._version, self._verse_data)
            else:
                self._click_timer.start()

    def _on_single_click(self):
        self.single_clicked.emit(self._version, self._verse_data)


class SearchResultWidget(QFrame):
    """A single search result item."""

    send_to_schedule = pyqtSignal(dict)
    # Single-click anywhere on the result (except badge) → navigator in current translation
    navigate_requested = pyqtSignal(dict)
    # Double-click anywhere on the result (except badge) → live in current translation
    live_requested = pyqtSignal(dict)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self.data = data
        self._click_timer = QTimer(self)
        self._click_timer.setSingleShot(True)
        self._click_timer.setInterval(_CLICK_DELAY)
        self._click_timer.timeout.connect(self._on_single_click)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: none;
            }}
            QFrame:hover {{
                background: rgba(255, 255, 255, 0.03);
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        # Confidence badge
        conf = data.get("confidence", 0)
        conf_label = QLabel(f"{conf:.0f}%")
        conf_label.setFixedWidth(32)
        conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if conf >= 70:
            badge_color = CYAN_400
        elif conf >= 40:
            badge_color = SLATE_400
        else:
            badge_color = SLATE_600
        conf_label.setStyleSheet(f"""
            color: {badge_color};
            font-size: 9px;
            font-weight: 700;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 3px;
            padding: 1px 0;
        """)
        layout.addWidget(conf_label)

        # Verse reference + text
        text_layout = QVBoxLayout()
        text_layout.setSpacing(1)

        ref = f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}"
        ref_label = QLabel(ref)
        ref_label.setStyleSheet(f"color: {WHITE}; font-size: 10px; font-weight: 700;")
        text_layout.addWidget(ref_label)

        verse_text = data.get("text", "")
        text_label = QLabel(verse_text)
        text_label.setStyleSheet(f"color: {SLATE_400}; font-size: 9px;")
        text_label.setWordWrap(True)
        fm = QFontMetrics(text_label.font())
        text_label.setMaximumHeight(fm.height() * 2)
        text_layout.addWidget(text_label)

        layout.addLayout(text_layout, 1)

        # Translation badge (clickable — separate from result clicks)
        self._trans_badge = None
        version = data.get("version", "")
        if version:
            from core.bible_service import get_display_name
            self._trans_badge = _TransBadge(version, get_display_name(version), data)
            self._trans_badge.setStyleSheet(f"""
                color: {SLATE_500};
                font-size: 8px;
                font-weight: 600;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 2px;
                padding: 1px 4px;
            """)
            layout.addWidget(self._trans_badge)

        # Send to Schedule button
        send_btn = QPushButton("Send")
        send_btn.setStyleSheet(SHOW_BTN_STYLE)
        send_btn.setFixedWidth(44)
        send_btn.setFixedHeight(18)
        send_btn.setToolTip("Add this verse to the schedule")
        send_btn.clicked.connect(lambda: self.send_to_schedule.emit(self.data))
        layout.addWidget(send_btn)

    def mousePressEvent(self, event):
        """Handle single/double click on the result row (excluding badge area)."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Ignore clicks on the translation badge — it has its own handler
            if self._trans_badge and self._trans_badge.underMouse():
                return
            if self._click_timer.isActive():
                self._click_timer.stop()
                self.live_requested.emit(self.data)
            else:
                self._click_timer.start()

    def _on_single_click(self):
        self.navigate_requested.emit(self.data)


class SearchPanel(QWidget):
    """Advanced semantic search panel for the operator review area."""

    verse_to_schedule = pyqtSignal(dict)
    # Single-click result → navigate to reference in current browser translation
    verse_to_navigator = pyqtSignal(dict)
    # Double-click result → send to live in current browser translation
    verse_to_live = pyqtSignal(dict)
    # Single-click translation badge → navigate to reference in result's translation
    trans_badge_to_navigator = pyqtSignal(dict)
    # Double-click translation badge → send to live in result's translation
    trans_badge_to_live = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self.setAccessibleName("Fuzzy Search Panel")
        self.setAccessibleDescription("Semantic search using FAISS and BM25 for natural language Bible verse queries")
        self._searching = False
        self._verse_results = []
        self._topical_results = []
        self._active_tab = "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # ── Header ──
        header = QLabel("Fuzzy Search")
        header.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; font-weight: 700;")
        layout.addWidget(header)

        # ── Query input ──
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.query_input = QLineEdit()
        self.query_input.setPlaceholderText("e.g., prodigal son, David and Goliath...")
        self.query_input.setAccessibleName("Fuzzy search query")
        self.query_input.setAccessibleDescription("Type a natural language description to find Bible verses")
        self.query_input.setStyleSheet(f"""
            QLineEdit {{
                background: {SLATE_800};
                color: {WHITE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {CYAN_400};
            }}
        """)
        self.query_input.returnPressed.connect(self._on_search)
        input_row.addWidget(self.query_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.setAccessibleName("Search")
        self.search_btn.setAccessibleDescription("Execute semantic search for Bible verses")
        self.search_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(34, 211, 238, 0.15);
                color: {CYAN_400};
                border: 1px solid rgba(34, 211, 238, 0.3);
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: rgba(34, 211, 238, 0.25);
            }}
        """)
        self.search_btn.setFixedWidth(70)
        self.search_btn.clicked.connect(self._on_search)
        input_row.addWidget(self.search_btn)

        layout.addLayout(input_row)

        # ── Tab bar ──
        tab_row = QHBoxLayout()
        tab_row.setSpacing(4)

        self.tab_all = _TabButton("All")
        self.tab_verses = _TabButton("Verses")
        self.tab_topics = _TabButton("Topics")
        self.tab_all.setChecked(True)

        self.tab_all.clicked.connect(lambda: self._switch_tab("all"))
        self.tab_verses.clicked.connect(lambda: self._switch_tab("verses"))
        self.tab_topics.clicked.connect(lambda: self._switch_tab("topics"))

        tab_row.addWidget(self.tab_all)
        tab_row.addWidget(self.tab_verses)
        tab_row.addWidget(self.tab_topics)
        tab_row.addStretch()

        # Result count labels
        self.verse_count_label = QLabel("")
        self.verse_count_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px;")
        tab_row.addWidget(self.verse_count_label)

        self.topic_count_label = QLabel("")
        self.topic_count_label.setStyleSheet(f"color: {SLATE_500}; font-size: 9px;")
        tab_row.addWidget(self.topic_count_label)

        layout.addLayout(tab_row)

        # ── Results list ──
        self.results_list = _SearchResultsList()
        self.results_list.setAccessibleName("Fuzzy search results")
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

        # ── Status / latency label ──
        self.status_label = QLabel("")
        self.status_label.setAccessibleName("Search status")
        self.status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        layout.addWidget(self.status_label)

    def _switch_tab(self, tab: str):
        """Switch between All / Verses / Topics views."""
        self._active_tab = tab

        # Update tab button states
        self.tab_all.setChecked(tab == "all")
        self.tab_verses.setChecked(tab == "verses")
        self.tab_topics.setChecked(tab == "topics")

        self._repopulate_results()

    def _repopulate_results(self):
        """Re-populate the results list based on the active tab."""
        self.results_list.clear()

        if self._active_tab == "all":
            items = self._verse_results + self._topical_results
        elif self._active_tab == "verses":
            items = self._verse_results
        elif self._active_tab == "topics":
            items = self._topical_results
        else:
            items = []

        for r in items:
            widget = SearchResultWidget(r)
            widget.send_to_schedule.connect(self._on_send_to_schedule)
            widget.navigate_requested.connect(self._on_navigate_requested)
            widget.live_requested.connect(self._on_live_requested)
            if widget._trans_badge:
                widget._trans_badge.single_clicked.connect(self._on_trans_badge_single)
                widget._trans_badge.double_clicked.connect(self._on_trans_badge_double)

            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            item.setData(Qt.ItemDataRole.UserRole, r)
            self.results_list.addItem(item)
            self.results_list.setItemWidget(item, widget)

    def _ensure_indexes_loaded(self) -> bool:
        """Ensure search indexes are loaded. Returns True if ready."""
        from core.model_manager import model_manager

        # Fuzzy BM25 is optional — FAISS-only degradation if missing
        if (model_manager.faiss_index is not None
                and model_manager.embedding_model is not None):
            return True

        # Models are being loaded in background — wait
        if model_manager.embedding_model is None or model_manager.faiss_index is None:
            self.status_label.setText("Search model still loading, please wait...")
            QApplication.processEvents()
            import time
            for _ in range(80):  # up to 8 seconds
                if (model_manager.faiss_index is not None
                        and model_manager.embedding_model is not None):
                    return True
                time.sleep(0.1)
            # If still not loaded, try loading on main thread as fallback
            logger.warning("Background preload did not finish in time, loading on main thread")

        self.status_label.setText("Loading search indexes...")
        QApplication.processEvents()

        try:
            model_manager._load_indexes()
            model_manager._load_embedding()
            logger.info("Lazy-loaded search indexes: FuzzyBM25=%s, FAISS=%s",
                        model_manager.fuzzy_bm25_index is not None,
                        model_manager.faiss_index is not None)
            return True
        except Exception as e:
            logger.error("Failed to load search indexes: %s", e, exc_info=True)
            self.status_label.setText(f"Error loading indexes: {e}")
            return False

    def _on_search(self):
        query = self.query_input.text().strip()
        if not query or self._searching:
            return

        self._searching = True
        self.search_btn.setEnabled(False)
        self.query_input.setEnabled(False)
        self.status_label.setText("Searching...")
        self.results_list.clear()
        QApplication.processEvents()

        try:
            if not self._ensure_indexes_loaded():
                return

            from core.search_engine import fuzzy_bm25_search, faiss_search, rrf_fuse, topical_search

            t0 = time.perf_counter()
            bm25_res = fuzzy_bm25_search(query, top_k=10)
            faiss_res = faiss_search(query, top_k=10)
            fused = rrf_fuse(bm25_res, faiss_res, word_count=len(query.split()))
            topical_res = topical_search(query, top_k=3)
            latency_ms = (time.perf_counter() - t0) * 1000

            logger.info("Search '%s': bm25=%d, faiss=%d, fused=%d, topical=%d (%.0fms)",
                        query, len(bm25_res), len(faiss_res), len(fused),
                        len(topical_res), latency_ms)

            # Store results for tab switching
            self._verse_results = []
            for r in fused:
                r["latency_ms"] = latency_ms
                self._verse_results.append(r)

            self._topical_results = []
            for t in topical_res:
                for v in t["verses"]:
                    self._topical_results.append({
                        "confidence": t["confidence"],
                        "topic": t["topic"],
                        "description": t["description"],
                        "book": v["book"],
                        "chapter": v["chapter"],
                        "verse_num": v["verse"],
                        "text": f"[{t['topic']}] {t['description'][:80]}...",
                        "latency_ms": latency_ms,
                        "is_topical": True,
                    })

            # Update counts
            n_v = len(self._verse_results)
            n_t = len(self._topical_results)
            self.verse_count_label.setText(f"{n_v} verse{'s' if n_v != 1 else ''}")
            self.topic_count_label.setText(f"{n_t} topic{'s' if n_t != 1 else ''}")

            if not self._verse_results and not self._topical_results:
                self.status_label.setText("No results found")
                return

            total = n_v + n_t
            self.status_label.setText(f"{total} results ({latency_ms:.0f}ms)")

            self._repopulate_results()

        except Exception as e:
            logger.error("Search error: %s", e, exc_info=True)
            self.status_label.setText(f"Error: {e}")
        finally:
            self._searching = False
            self.search_btn.setEnabled(True)
            self.query_input.setEnabled(True)

    def _on_send_to_schedule(self, data: dict):
        self.verse_to_schedule.emit(data)

    def _on_navigate_requested(self, data: dict):
        """Single-click on result row → navigate to reference in current browser translation."""
        self.verse_to_navigator.emit(data)

    def _on_live_requested(self, data: dict):
        """Double-click on result row → send to live in current browser translation."""
        self.verse_to_live.emit(data)

    def _on_trans_badge_single(self, version: str, data: dict):
        """Single-click on translation badge → navigate to reference in that translation."""
        self.trans_badge_to_navigator.emit(data)

    def _on_trans_badge_double(self, version: str, data: dict):
        """Double-click on translation badge → send to live in that translation."""
        self.trans_badge_to_live.emit(data)

    def focus_query(self):
        """Programmatically focus the query input (for Ctrl+Shift+S)."""
        self.query_input.setFocus()
        self.query_input.selectAll()
