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
from ui.widgets.text_nav import install_line_edit_nav
from ui.widgets.predictive_input import (
    BookFilterInput, OLD_TESTAMENT_BOOKS, NEW_TESTAMENT_BOOKS,
    GOSPELS_BOOKS)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QWheelEvent, QFontMetrics

from ui.styles import (
    PANEL_BODY_STYLE, SHOW_BTN_STYLE,
    ACCENT, ACCENT_SOFT, ACCENT_BORDER, SELECTION_BG,
    SLATE_300, SLATE_400, SLATE_500, SLATE_600, SLATE_800,
    WHITE, BORDER_SUBTLE
)
from core.bible_service import fts_search, keyword_search
from core.bible_service import fts_translations

logger = logging.getLogger(__name__)

_CLICK_DELAY = 250


def _book_predicate(term: str | None):
    """Match a result book against a verified filter term.

    The term always comes from BookFilterInput.current_filter(), so it
    is canonical; book comparison is exact (case-insensitive), testament
    comparison is set membership.
    """
    if not term:
        return None
    if term == "Old Testament":
        return lambda book: book in OLD_TESTAMENT_BOOKS
    if term == "New Testament":
        return lambda book: book in NEW_TESTAMENT_BOOKS
    if term == "Gospels":
        return lambda book: book in GOSPELS_BOOKS
    lowered = term.lower()
    return lambda book: (book or "").lower() == lowered


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

    def __init__(self, data: dict, query: str, parent=None,
                 highlight_words: list | None = None):
        super().__init__(parent)
        self._data = data
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
        ref_label.setStyleSheet(f"color: {WHITE}; font-size: 10px; font-weight: 700;")
        text_layout.addWidget(ref_label)

        verse_text = data.get("text", "")
        text_label = QLabel()
        text_label.setStyleSheet(f"color: {SLATE_400}; font-size: 9px;")
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setWordWrap(True)
        fm = QFontMetrics(text_label.font())
        text_label.setMaximumHeight(fm.height() * 2)

        if query and verse_text:
            safe = verse_text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            # Highlight query words PLUS matched surfaces (stem expansions,
            # typo-rescued forms) so indirect hits show their evidence.
            glow = list(dict.fromkeys(
                list(query.split())
                + list(highlight_words or [])))
            words = [w for w in glow if w]
            if words:
                pattern = "|".join(r"\b" + re.escape(w) + r"\b" for w in words)
                try:
                    highlighted = re.sub(
                        pattern,
                        lambda m: f'<span style="background:{ACCENT_SOFT};color:{WHITE};border-radius:2px;">{m.group()}</span>',
                        safe,
                        flags=re.IGNORECASE
                    )
                except re.error:
                    highlighted = safe
                text_label.setText(highlighted)
            else:
                text_label.setText(safe)
        else:
            text_label.setText(verse_text)

        text_layout.addWidget(text_label)

        layout.addLayout(text_layout, 1)

        # Translation badge
        translations = data.get("translations", [])
        if translations:
            t = translations[0]
            from core.bible_service import get_display_name
            badge = _TransBadge(t["version"], t)
            badge.setStyleSheet(f"""
                color: {SLATE_500};
                font-size: 8px;
                font-weight: 600;
                background: rgba(255, 255, 255, 0.05);
                border-radius: 2px;
                padding: 1px 4px;
            """)
            badge.single_clicked.connect(self.trans_single.emit)
            badge.double_clicked.connect(self.trans_double.emit)
            layout.addWidget(badge)

        # Send to Schedule button
        send_btn = QPushButton("Send")
        send_btn.setStyleSheet(SHOW_BTN_STYLE)
        send_btn.setFixedWidth(44)
        send_btn.setFixedHeight(18)
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

    def set_selected(self, selected: bool):
        """Reflect QListWidget selection with the theme highlight."""
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)


class FtsSearchPanel(QWidget):
    """Compact FTS search across 6 translations, ordered by relevance."""

    verse_to_schedule = pyqtSignal(dict)
    verse_to_navigator = pyqtSignal(dict)
    verse_to_live = pyqtSignal(dict)
    trans_badge_to_navigator = pyqtSignal(dict)
    trans_badge_to_live = pyqtSignal(dict)
    # Sweep completion hops worker→GUI thread (always queued across
    # threads): generation, {translation: [results]}, elapsed ms, done,
    # keyword-lane [results], keyword ms, keyword display translation.
    _sweep_done = pyqtSignal(int, object, float, bool, object, float, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        # Search generations: only the latest generation may paint.
        # Single-flight background sweep (max 1 worker); newer queries
        # coalesce into _search_pending and supersede in-flight work.
        self._search_gen = 0
        self._search_executor = None
        self._search_future = None
        self._search_pending = None
        self._gen_queries = {}
        # Last submitted query (popularity pick logging context).
        self._last_query = ""
        # Progressive paint state (orphaned silently by newer searches).
        self._paint = None
        self._paint_per_frame = 25
        # Book/testament filter (verified term from the filter box, or None).
        # Filtering is hide/show over painted rows — no rebuild per keystroke.
        self._book_filter: str | None = None
        # Full sorted results of the latest search (filter source of truth).
        self._all_verses: list | None = None
        self._last_elapsed_ms: float = 0.0
        # Initial paint cap: full 129-row paints block ~300ms even
        # batched; a "show all" affordance reveals the rest on demand.
        self._paint_max_initial = 40
        self._sweep_done.connect(self._on_sweep_done)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self.setAccessibleName("FTS Search Panel")
        self.setAccessibleDescription("Search Bible verses across 6 translations using FTS5 full-text search")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header
        header = QLabel("FTS Search")
        header.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; font-weight: 700;")
        layout.addWidget(header)

        # Search input
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.query_input = QLineEdit()
        # Word gestures + focus-select-all + triple-click-select-all.
        # A plain QLineEdit on purpose: emulating a single-line field on
        # QTextEdit is what produced the selection and caret bugs.
        install_line_edit_nav(self.query_input)
        self.query_input.setPlaceholderText("e.g., rich man threw a party for his son...")
        self.query_input.setAccessibleName("FTS search query")
        self.query_input.setAccessibleDescription("Type a Bible verse reference or text to search across all translations")
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
        self.search_btn.setAccessibleDescription("Execute FTS search across all translations")
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

        layout.addLayout(input_row)

        # Book/testament filter row (verified-inputs-only, mirrors the
        # navigator book box: highlighted autofill, x to clear).
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self.filter_input = BookFilterInput()
        self.filter_input.setAccessibleName("Book filter")
        self.filter_input.setAccessibleDescription(
            "Filter results by book or testament. Only verified book names accepted.")
        self.filter_input.setStyleSheet(f"""
            QLineEdit {{
                background: {SLATE_800};
                color: {WHITE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {ACCENT};
            }}
        """)
        self.filter_input.textChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self.filter_input)

        self.filter_clear_btn = QPushButton("×")
        self.filter_clear_btn.setAccessibleName("Clear book filter")
        self.filter_clear_btn.setAccessibleDescription("Clear the book filter and show all results")
        self.filter_clear_btn.setFixedWidth(28)
        self.filter_clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.filter_clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_500};
                border: none;
                border-radius: 6px;
                font-size: 14px;
                font-weight: 700;
                padding: 4px;
            }}
            QPushButton:hover {{
                color: {WHITE};
                background: rgba(255, 255, 255, 0.08);
            }}
        """)
        self.filter_clear_btn.clicked.connect(self._clear_filter)
        filter_row.addWidget(self.filter_clear_btn)
        filter_row.addStretch(1)

        layout.addLayout(filter_row)

        # Results list
        self.results_list = _FtsResultsList()
        self.results_list.itemSelectionChanged.connect(
            self._sync_row_selection)
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

        # Status / latency label
        self.status_label = QLabel("")
        self.status_label.setAccessibleName("Search status")
        self.status_label.setStyleSheet(f"color: {SLATE_500}; font-size: 10px;")
        layout.addWidget(self.status_label)

        # Debounce timer (100ms: searches run ~15ms, coalesced)
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(100)
        self._debounce_timer.timeout.connect(self._execute_search)
        self.query_input.textChanged.connect(lambda: self._debounce_timer.start())

        # Session-only search history (Up/Down recall). Qualifying a query:
        # 2s idle, or the operator clicks a hit / scrolls the results.
        from core.constants import SEARCH_HISTORY_IDLE_MS, SEARCH_HISTORY_MAX_ENTRIES
        from ui.widgets.search_history import SearchHistory
        self._search_history = SearchHistory(
            self.query_input, idle_ms=SEARCH_HISTORY_IDLE_MS,
            max_entries=SEARCH_HISTORY_MAX_ENTRIES)
        self._search_history.bind_scroll(
            self.results_list.verticalScrollBar())

    def set_translation(self, version: str):
        pass

    def focus_query(self):
        """Focus the query input. Selecting its contents is the app-wide
        focus watcher's job (text_nav._FocusSelectAll), so nothing to add
        here — and nothing here that could disagree with it."""
        self.query_input.setFocus()

    def _on_search(self):
        self._debounce_timer.stop()
        self._execute_search()

    def _execute_search(self):
        query = self.query_input.text().strip()
        if not query:
            self._search_gen += 1  # invalidate any in-flight sweep
            self._search_pending = None
            self._paint = None  # orphan any in-flight paint chain
            self._all_verses = None
            self.results_list.clear()
            self.status_label.setText("")
            self._last_search_row = None
            return

        self._search_gen += 1
        gen = self._search_gen
        self._gen_queries[gen] = query
        self._last_query = query
        # Prune old query records (latest few suffice for stragglers).
        for old in [g for g in self._gen_queries if g < gen - 3]:
            del self._gen_queries[old]
        if self._search_future is not None and not self._search_future.done():
            # Worker busy: coalesce — latest query wins, supersedes.
            self._search_pending = (gen, query)
            self.status_label.setText("Searching…")
            return
        self._submit_sweep(gen, query)

    def _submit_sweep(self, gen: int, query: str):
        """Run one 6-translation sweep on the background worker."""
        from concurrent.futures import ThreadPoolExecutor
        if self._search_executor is None:
            self._search_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="scripture-search")
        self._search_future = self._search_executor.submit(
            self._run_sweep, gen, query)
        self._search_future.add_done_callback(self._sweep_finished)
        self.status_label.setText("Searching…")

    def _run_sweep(self, gen: int, query: str):
        """Worker thread: per-translation two-stage search in parallel,
        plus the keyword lane once per query (translation-independent).

        Checks each completion whether a newer generation superseded
        this sweep (cancels the rest); returns (gen, {trans: results},
        elapsed_ms, done, kw_results, kw_ms, kw_display). Never touches
        widgets — results hop back via _sweep_done.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        bucket: dict = {}
        t0 = time.monotonic()
        done = True
        pool = ThreadPoolExecutor(max_workers=3,
                                  thread_name_prefix="scripture-trans")
        futures: dict = {}
        try:
            # Read live: the operator chooses this in Settings, and
            # narrowing the fan-out is the biggest speed lever available.
            for trans in fts_translations():
                futures[pool.submit(fts_search, query, trans, 30)] = trans
            for future in as_completed(futures):
                if gen != self._search_gen:
                    done = False
                    for f in futures:
                        f.cancel()
                    break
                trans = futures[future]
                try:
                    bucket[trans] = future.result()
                except Exception as e:
                    logger.warning(f"FTS search failed for {trans}: {e}")
                    bucket[trans] = []
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
        kw_results, kw_ms, kw_display = keyword_search(query, 30)
        return (gen, bucket, (time.monotonic() - t0) * 1000, done,
                kw_results, kw_ms, kw_display)

    def _sweep_finished(self, future):
        """Worker-thread callback: forward to the GUI thread."""
        try:
            (gen, bucket, elapsed_ms, done,
             kw_results, kw_ms, kw_display) = future.result()
        except Exception as e:
            logger.warning(f"Scripture sweep crashed: {e}")
            return
        self._sweep_done.emit(gen, bucket, elapsed_ms, done,
                              kw_results, kw_ms, kw_display)

    def _on_sweep_done(self, gen: int, bucket: dict, elapsed_ms: float,
                       done: bool, kw_results: list, kw_ms: float,
                       kw_display: str):
        """GUI thread: render the sweep iff still current, then drain
        any coalesced pending query (a superseded sweep still drains —
        otherwise the waiting query strands).

        Keyword-lane hits merge as display-translation results; a
        (reference, translation) pair already present from the sweep wins
        (no duplicate badges), genuinely new verses join the list."""
        pending = self._search_pending
        self._search_pending = None
        if gen == self._search_gen:
            query = self._gen_queries.get(gen, "")
            all_results = []
            seen = set()

            def _refkey(r: dict, version: str) -> tuple:
                verse = r.get("verse", r.get("verse_num", ""))
                return (f"{r.get('book', '')} {r.get('chapter', '')}:"
                        f"{verse}", version)

            for trans, results in bucket.items():
                for r in results:
                    r["version"] = trans
                    all_results.append(r)
                    seen.add(_refkey(r, trans))
            for r in kw_results or []:
                r["version"] = kw_display
                key = _refkey(r, kw_display)
                if key not in seen:
                    seen.add(key)
                    all_results.append(r)
            # Operator learning: previously picked verses for similar
            # prompts ride near the top (weight, not verdict).
            from core.bible_service import (
                apply_popularity, popularity_boosts)
            all_results = apply_popularity(
                all_results, popularity_boosts(query))
            self._render_results(query, all_results, elapsed_ms)
        if pending is not None and pending[0] == self._search_gen:
            # Still the latest keystroke run: sweep it now.
            self._submit_sweep(*pending)
        # Else: a newer generation already runs or ran — drop the stale.

    def cleanup(self):
        """Stop background work (tests / teardown)."""
        self._search_gen += 1
        self._search_pending = None
        if self._search_executor is not None:
            try:
                self._search_executor.shutdown(wait=False,
                                               cancel_futures=True)
            except Exception:
                pass
            self._search_executor = None
            self._search_future = None

    def _render_results(self, query: str, all_results: list,
                        elapsed_ms: float):
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
                    # Uncapped score when popularity supplied one: the
                    # badge is capped at 100% but ordering must not be,
                    # or two saturated verses tie on display alone.
                    "confidence_rank": r.get("confidence_rank"),
                    "boosted": bool(r.get("boosted")),
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
            prev = grouped[ref].get("confidence_rank")
            rank = r.get("confidence_rank")
            if rank is not None:
                grouped[ref]["confidence_rank"] = (
                    rank if prev is None else max(prev, rank))
            grouped[ref]["boosted"] = grouped[ref].get("boosted") or bool(
                r.get("boosted"))

        # Sort by relevance (rank score descending, falling back to the
        # displayed confidence where no popularity boost applied)
        sorted_verses = sorted(
            grouped.values(),
            key=lambda v: (v["confidence_rank"]
                           if v.get("confidence_rank") is not None
                           else v["confidence"]),
            reverse=True)

        # Paint progressively (a full 129-row paint blocks ~300ms):
        # first frame now, the rest cooperatively. A newer search
        # replaces the paint state, orphaning this chain mid-flight.
        # The chain always paints the FULL list; the book filter is
        # hide/show over painted rows (no rebuild per keystroke).
        self.results_list.clear()
        self._all_verses = sorted_verses
        self._last_elapsed_ms = elapsed_ms
        # Rendering scrolls the list on its own; re-arm so only the
        # operator's own scrolling counts as qualifying the query.
        self._search_history.arm_scroll()
        self._paint = {"verses": sorted_verses, "query": query,
                       "pos": 0, "elapsed_ms": elapsed_ms,
                       "capped": len(sorted_verses) > self._paint_max_initial,
                       "expanded": False,
                       "awaiting_expand": False}
        self._paint_chunk()
        if self._book_filter is not None:
            self._apply_book_filter(self._book_filter)

        # History: document the search (query + top hits). Keystroke runs
        # coalesce in log_search_event — no debounce needed here.
        from core.database import (current_operator_session, log_search_event)
        top = [f"{v['book']} {v['chapter']}:{v['verse_num']}"
               for v in sorted_verses[:5]]
        self._last_search_row = log_search_event(
            current_operator_session(), "fts", query,
            len(sorted_verses), top)

    def _paint_chunk(self):
        """Paint the next frame of rows; reschedule while rows remain.

        The initial paint stops at _paint_max_initial with a "show all"
        affordance instead of the full list (large paints block hundreds
        of ms); expanding resumes the same chain.
        """
        from PyQt6.QtCore import QTimer
        state = self._paint
        if state is None or self._paint is not state:
            return  # superseded by a newer search: stop silently
        verses = state["verses"]
        pos = state["pos"]
        filter_active = self._book_filter is not None
        # While filtered, the cap/button are bypassed: the chain paints
        # everything (chunked) so matches beyond the cap still surface.
        cap = len(verses) if (
            state.get("expanded") or filter_active) else min(
            len(verses), self._paint_max_initial)
        end = min(pos + self._paint_per_frame, cap)
        self.results_list.setUpdatesEnabled(False)
        try:
            for v in verses[pos:end]:
                item = QListWidgetItem()
                widget = _ResultRow(
                    v, state["query"],
                    highlight_words=v.get("matched"))
                widget.send_to_schedule.connect(self.verse_to_schedule.emit)
                widget.navigate_requested.connect(self.verse_to_navigator.emit)
                widget.live_requested.connect(self.verse_to_live.emit)
                widget.trans_single.connect(self._on_trans_single)
                widget.trans_double.connect(self._on_trans_double)
                self.results_list.addItem(item)
                self.results_list.setItemWidget(item, widget)
                item.setSizeHint(widget.sizeHint())
        finally:
            self.results_list.setUpdatesEnabled(True)
        state["pos"] = end
        if filter_active:
            self._sweep_range(pos, end)
        capped = not state.get("expanded") and end >= cap
        if capped and end < len(verses):
            if filter_active:
                # No button while filtered: keep painting to the end.
                state["expanded"] = True
                self.status_label.setText(
                    f"showing {end}/{len(verses)} verses…")
                QTimer.singleShot(0, self._paint_chunk)
            else:
                self._paint_show_more(state)
        elif end < len(verses):
            self.status_label.setText(
                f"showing {end}/{len(verses)} verses…")
            QTimer.singleShot(0, self._paint_chunk)
        else:
            self._paint = None
            self._update_done_status(
                len(verses), state["elapsed_ms"])

    def _paint_show_more(self, state):
        """Cap affordance row: click resumes painting the full list."""
        from PyQt6.QtWidgets import QPushButton
        item = QListWidgetItem()
        btn = QPushButton(
            f"Show all {len(state['verses'])} verses "
            f"({len(state['verses']) - state['pos']} more)")
        btn.setObjectName("ShowMoreButton")
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: {ACCENT_SOFT};"
            f"  color: {ACCENT}; border: 1px solid {ACCENT_BORDER};"
            "  border-radius: 6px; padding: 6px; font-size: 11px;"
            "  font-weight: 700; }"
            f"QPushButton:hover {{ background: {SELECTION_BG}; }}")

        def _expand():
            if self._paint is not state:
                return  # superseded meanwhile: ignore the tap
            # Drop the button row itself, then continue painting.
            for i in range(self.results_list.count()):
                if self.results_list.itemWidget(
                        self.results_list.item(i)) is btn:
                    self.results_list.takeItem(i)
                    break
            btn.deleteLater()
            state["expanded"] = True
            state["awaiting_expand"] = False
            self._paint_chunk()

        btn.clicked.connect(_expand)
        self.results_list.addItem(item)
        self.results_list.setItemWidget(item, btn)
        item.setSizeHint(btn.sizeHint())
        state["awaiting_expand"] = True
        self.status_label.setText(
            f"showing {state['pos']}/{len(state['verses'])} verses…")

    def _update_done_status(self, total: int, elapsed_ms: float):
        """Final status line; notes the active book filter, if any."""
        if self._book_filter is not None:
            visible = self._visible_count()
            self.status_label.setText(
                f"{visible} of {total} verses "
                f"(filter: {self._book_filter})")
        else:
            self.status_label.setText(
                f"{total} verses across {len(fts_translations())} "
                f"translations ({elapsed_ms:.0f}ms)"
            )

    def _visible_count(self) -> int:
        """Painted verse rows currently not hidden."""
        n = 0
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            if not item.isHidden() and isinstance(
                    self.results_list.itemWidget(item), _ResultRow):
                n += 1
        return n

    def _sweep_range(self, start: int, end: int):
        """Hide/show freshly painted rows [start, end) per the filter."""
        pred = _book_predicate(self._book_filter)
        if pred is None:
            return
        for i in range(start, min(end, self.results_list.count())):
            item = self.results_list.item(i)
            widget = self.results_list.itemWidget(item)
            if isinstance(widget, _ResultRow):
                item.setHidden(not pred(widget._data.get("book", "")))

    def _sweep_all(self) -> int:
        """Hide/show every painted row per the filter; hide the
        show-more button while filtered. Returns visible verse count."""
        pred = _book_predicate(self._book_filter)
        visible = 0
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            widget = self.results_list.itemWidget(item)
            if isinstance(widget, _ResultRow):
                show = pred is None or pred(widget._data.get("book", ""))
                item.setHidden(not show)
                visible += show
            elif isinstance(widget, QPushButton):
                item.setHidden(self._book_filter is not None)
        return visible

    def _drop_button_row(self):
        """Remove the show-more affordance row, if present."""
        for i in range(self.results_list.count()):
            if isinstance(self.results_list.itemWidget(
                    self.results_list.item(i)), QPushButton):
                self.results_list.takeItem(i)
                break

    def _on_filter_changed(self):
        """Every keystroke re-resolves the verified term and filters."""
        self._apply_book_filter(self.filter_input.current_filter())

    def _clear_filter(self):
        self.filter_input.clear_filter()
        self.filter_input.setFocus()

    def _apply_book_filter(self, term: str | None):
        """Filter painted rows by verified term; ensure the chain
        paints any matches beyond the cap (no rebuild per keystroke)."""
        self._book_filter = term
        if not self._all_verses:
            return  # nothing painted yet; later searches respect the term
        visible = self._sweep_all()
        total = len(self._all_verses)
        state = self._paint
        if term is not None and state is not None:
            if state.get("awaiting_expand"):
                # Chain paused at the button: drop it and paint through.
                self._drop_button_row()
                state["expanded"] = True
                state["awaiting_expand"] = False
                self._paint_chunk()
                visible = self._visible_count()
            # Else the chain is in flight (or done) — _paint_chunk
            # already sweeps new rows and bypasses the cap while filtered.
        if state is None:
            self._update_done_status(total, self._last_elapsed_ms)
        else:
            if term is not None:
                self.status_label.setText(
                    f"{visible} of {total} verses (filter: {term})")
            else:
                self.status_label.setText(
                    f"showing {state['pos']}/{total} verses…")

    def _sync_row_selection(self):
        """Mirror QListWidget selection onto row widgets (theme highlight)."""
        for i in range(self.results_list.count()):
            item = self.results_list.item(i)
            widget = self.results_list.itemWidget(item)
            if isinstance(widget, _ResultRow):
                widget.set_selected(item.isSelected())

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

    def _on_trans_single(self, version: str, data: dict):
        """Single-click on translation badge → navigate in that translation."""
        self.trans_badge_to_navigator.emit(data)

    def _on_trans_double(self, version: str, data: dict):
        """Double-click on translation badge → push to live in that translation."""
        self.trans_badge_to_live.emit(data)

    def clear_results(self):
        self._paint = None
        self._all_verses = None
        self.results_list.clear()
        self.query_input.clear()
        self.status_label.setText("")