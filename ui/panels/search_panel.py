"""
ui/panels/search_panel.py

Advanced semantic search panel for vague natural language queries.
Uses existing FAISS + BM25 hybrid search infrastructure.
"""

import logging
import time

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QListWidget, QListWidgetItem, QFrame, QApplication
)
from ui.widgets.text_nav import install_line_edit_nav
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtGui import QWheelEvent

from ui.styles import (
    PANEL_BODY_STYLE, SHOW_BTN_STYLE,
    ACCENT, ACCENT_SOFT, ACCENT_BORDER, SELECTION_BG,
    SLATE_300, SLATE_400, SLATE_500, SLATE_600,
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
                    background: {ACCENT_SOFT};
                    color: {ACCENT};
                    border: 1px solid {ACCENT_BORDER};
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
        self.setProperty("selected", False)
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: none;
            }}
            QFrame:hover {{
                background: rgba(255, 255, 255, 0.03);
            }}
            QFrame[selected="true"] {{
                background: {SELECTION_BG};
            }}
            QFrame[selected="true"]:hover {{
                background: {SELECTION_BG};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(6)

        # Confidence badge (★ when lifted by the operator's own picks)
        # Belt and braces: nothing should produce >100%, but a badge is
        # the last place that can guarantee it.
        conf = min(100.0, data.get("confidence", 0) or 0)
        star = "★" if data.get("boosted") else ""
        conf_label = QLabel(f"{star}{conf:.0f}%")
        conf_label.setFixedWidth(40 if star else 32)
        if star:
            conf_label.setToolTip("Boosted by your picks")
        conf_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if conf >= 70:
            badge_color = ACCENT
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
        from ui.app_theme import area_font, font_qss
        ref_font = area_font("search.ref", 10, 700,
                                  family_key="search.ref_font_family",
                                  weight_key="search.ref_font_weight",
                                  size_key="search.ref_font_size")
        ref_label.setStyleSheet(f"color: {WHITE}; " + font_qss(ref_font))
        text_layout.addWidget(ref_label)

        verse_text = data.get("text", "")
        text_label = QLabel(verse_text)
        text_font = area_font("search.result", 9,
                                    family_key="search.result_font_family",
                                    weight_key="search.result_font_weight",
                                    size_key="search.result_font_size")
        text_label.setStyleSheet(f"color: {SLATE_400}; " + font_qss(text_font))
        text_label.setWordWrap(True)
        from PyQt6.QtGui import QFont, QFontMetrics
        probe = QFont()
        if text_font["family"]:
            probe.setFamily(text_font["family"])
        probe.setPixelSize(text_font["size"])
        probe.setWeight(text_font["weight"])
        fm = QFontMetrics(probe)
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
        super().mousePressEvent(event)

    def _on_single_click(self):
        self.navigate_requested.emit(self.data)

    def set_selected(self, selected: bool):
        """Reflect QListWidget selection with the theme highlight."""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)


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
        self.setAccessibleName("Semantic Search Panel")
        self.setAccessibleDescription("Semantic search using FAISS and BM25 for natural language Bible verse queries")
        self._searching = False
        self._verse_results = []
        self._topical_results = []
        self._active_tab = "all"
        # Last submitted query (popularity pick logging context).
        self._last_query = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # No in-panel title: the page's text tab already names it.

        # ── Query input ──
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.query_input = QLineEdit()
        # Native × affordance: clears the query in one click (shows only
        # while text is present; clearing fires textChanged like typing).
        self.query_input.setClearButtonEnabled(True)
        # Word gestures + focus-select-all + triple-click-select-all.
        # A plain QLineEdit on purpose: emulating a single-line field on
        # QTextEdit is what produced the selection and caret bugs.
        install_line_edit_nav(self.query_input)
        self.query_input.setPlaceholderText("e.g., describe it: jesus walks on water...")
        self.query_input.setAccessibleName("Semantic search query")
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
                border-color: {ACCENT};
            }}
        """)
        self.query_input.returnPressed.connect(self._on_search)
        input_row.addWidget(self.query_input)

        self.search_btn = QPushButton("Search")
        self.search_btn.setAccessibleName("Search")
        self.search_btn.setAccessibleDescription("Execute semantic search for Bible verses")
        self.search_btn.setStyleSheet(f"""
            QPushButton {{
                background: {ACCENT_SOFT};
                color: {ACCENT};
                border: 1px solid {ACCENT_BORDER};
                border-radius: 6px;
                padding: 8px 16px;
                font-size: 11px;
                font-weight: 700;
            }}
            QPushButton:hover {{
                background: {SELECTION_BG};
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
        self.results_list.itemSelectionChanged.connect(
            self._sync_row_selection)
        self.results_list.setAccessibleName("Semantic search results")
        self.results_list.setAccessibleDescription("List of Bible verse search results ordered by relevance")
        self.results_list.setSpacing(2)
        self.results_list.setStyleSheet(f"""
            QListWidget {{
                background: transparent;
                border: none;
                padding: 0;
            }}
            QListWidget::item:focus {{
                outline: 2px solid {ACCENT};
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

        # ── Session-only search history (Up/Down recall) ──
        # Qualifying a query: 2s idle, or the operator clicks a hit /
        # scrolls the results.
        from core.constants import SEARCH_HISTORY_IDLE_MS, SEARCH_HISTORY_MAX_ENTRIES
        from ui.widgets.search_history import SearchHistory
        self._search_history = SearchHistory(
            self.query_input, idle_ms=SEARCH_HISTORY_IDLE_MS,
            max_entries=SEARCH_HISTORY_MAX_ENTRIES)
        self._search_history.bind_scroll(
            self.results_list.verticalScrollBar())

        # ── Status / latency label ──
        self.status_label = QLabel("")
        self.status_label.setAccessibleName("Search status")
        self.status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        layout.addWidget(self.status_label)

        # History: record which result the operator picks (self-connection).
        self._last_search_row: int | None = None
        self.verse_to_navigator.connect(self._on_result_chosen)
        self.verse_to_live.connect(self._on_result_chosen)
        self.trans_badge_to_navigator.connect(self._on_result_chosen)
        self.trans_badge_to_live.connect(self._on_result_chosen)
        # Popularity: weighted pick logging (private, debug-logged).
        self.verse_to_navigator.connect(self._on_pop_navigate)
        self.trans_badge_to_navigator.connect(self._on_pop_navigate)
        self.verse_to_schedule.connect(self._on_pop_schedule)
        self.verse_to_live.connect(self._on_pop_live)
        self.trans_badge_to_live.connect(self._on_pop_live)

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

    def _sync_row_selection(self):
        """Mirror QListWidget selection onto row widgets (theme highlight)."""
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            widget = self.results_list.itemWidget(item)
            if isinstance(widget, SearchResultWidget):
                widget.set_selected(item.isSelected())

    def _on_search(self):
        query = self.query_input.text().strip()
        if not query or self._searching:
            if not query:
                self._last_search_row = None
            return

        self._searching = True
        self.search_btn.setEnabled(False)
        self.query_input.setEnabled(False)
        self.status_label.setText("Searching...")
        self.results_list.clear()
        # Rendering scrolls the list on its own; re-arm so only the
        # operator's own scrolling counts as qualifying the query.
        self._search_history.arm_scroll()
        QApplication.processEvents()
        self._last_query = query

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

            # Operator learning: previously picked verses for similar
            # prompts ride near the top (weight, not verdict).
            from core.bible_service import apply_popularity, popularity_boosts
            fused = apply_popularity(fused, popularity_boosts(query))

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

            # History: document the search (query + top verse hits).
            from core.database import (current_operator_session, log_search_event)
            top = [f"{r.get('book', '')} {r.get('chapter', '')}:"
                   f"{r.get('verse_num', r.get('verse', ''))}".strip()
                   for r in self._verse_results[:5]]
            self._last_search_row = log_search_event(
                current_operator_session(), "fuzzy", query, total, top)

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

    @staticmethod
    def _verse_ref(data: dict) -> str:
        return (f"{data.get('book', '')} {data.get('chapter', '')}:"
                f"{data.get('verse_num', data.get('verse', ''))}".strip())

    def _on_result_chosen(self, data: dict):
        """Record which search result the operator picked."""
        if not isinstance(data, dict):
            return
        # Clicking a hit qualifies the query outright (no idle wait).
        self._search_history.note_used()
        from core.database import mark_search_chosen
        mark_search_chosen(self._last_search_row, self._verse_ref(data))

    def _log_pick(self, data: dict, points: float, action: str):
        """Popularity pick (private): prompt + verse + action weight."""
        if not isinstance(data, dict) or not self._last_query:
            return
        from core.database import log_verse_pick
        log_verse_pick(self._last_query, data.get("book"),
                       data.get("chapter"),
                       data.get("verse_num", data.get("verse")), points)
        logger.debug("Popularity %s: %r -> %s", action, self._last_query,
                     self._verse_ref(data))

    def _on_pop_navigate(self, data: dict):
        from core.constants import POPULARITY_POINTS_NAVIGATE
        self._log_pick(data, POPULARITY_POINTS_NAVIGATE, "navigate")

    def _on_pop_schedule(self, data: dict):
        from core.constants import POPULARITY_POINTS_SCHEDULE
        self._log_pick(data, POPULARITY_POINTS_SCHEDULE, "schedule")

    def _on_pop_live(self, data: dict):
        from core.constants import POPULARITY_POINTS_LIVE
        self._log_pick(data, POPULARITY_POINTS_LIVE, "live")

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
        """Programmatically focus the query input (for Ctrl+Shift+S).
        Contents are selected by the app-wide focus watcher."""
        self.query_input.setFocus()
