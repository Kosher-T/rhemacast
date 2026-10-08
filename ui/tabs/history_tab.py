"""
ui/tabs/history_tab.py

Operator activity log — History tab.

Documents everything that hits the live screen (verse pushes, slide pushes,
clears) plus every operator search (query, top hits, chosen result), grouped
per session with the newest session first. Read-only; refreshes whenever the
tab is shown.
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_600,
    SLATE_500, SLATE_400, SLATE_300, WHITE, BORDER_SUBTLE,
    BLUE_400, CYAN_400, EMERALD_400, AMBER_500,
    SELECTION_BG, SELECTION_BORDER, TEXT_SELECTION,
)
from ui.panels.history_preview_panel import HistoryPreviewPanel

logger = logging.getLogger(__name__)

_BADGE_COLORS = {
    "VERSE": BLUE_400,
    "SLIDE": EMERALD_400,
    "CLEAR": SLATE_500,
    "SEARCH": AMBER_500,
}

_SEARCH_INPUT_STYLE = f"""
    QLineEdit {{
        background: rgba(29, 29, 34, 0.5);
        color: {SLATE_300};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 12px 16px;
        font-size: 14px;
        selection-background-color: {TEXT_SELECTION};
    }}
    QLineEdit:focus {{
        border-color: {SELECTION_BORDER};
    }}
    QLineEdit::placeholder {{
        color: {SLATE_600};
    }}
"""

_DATE_HEADER_STYLE = f"""
    color: {SLATE_400};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 8px 0 2px 0;
"""

_SESSION_SUB_STYLE = f"""
    color: {SLATE_500};
    font-size: 11px;
    padding: 0 0 8px 0;
"""

_CARD_STYLE = f"""
    QFrame {{
        background: rgba(29, 29, 34, 0.35);
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
    }}
"""

_MAX_SESSIONS_SHOWN = 30


class HistoryCard(QFrame):
    """One history row: a live push (verse/slide/clear) or an operator search."""

    clicked = pyqtSignal(dict)  # the session item dict

    def __init__(self, badge: str, title: str, body: str = "",
                 time_str: str = "", item: dict | None = None, parent=None):
        super().__init__(parent)
        self._item = item or {}
        self.setStyleSheet(_CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        badge_label = QLabel(badge.upper())
        badge_label.setStyleSheet(f"""
            color: {_BADGE_COLORS.get(badge.upper(), SLATE_500)};
            background: rgba(29, 29, 34, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        badge_label.setFixedHeight(22)
        top_row.addWidget(badge_label)
        top_row.addStretch()

        if time_str:
            time_label = QLabel(time_str)
            time_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
            top_row.addWidget(time_label)

        layout.addLayout(top_row)

        if title:
            title_label = QLabel(title)
            title_label.setWordWrap(True)
            title_label.setStyleSheet(
                f"color: {WHITE}; font-size: 13px; font-weight: 700;")
            layout.addWidget(title_label)

        if body:
            body_label = QLabel(body)
            body_label.setWordWrap(True)
            body_label.setStyleSheet(f"color: {SLATE_400}; font-size: 12px;")
            layout.addWidget(body_label)

        self._text = f"{title} {body}".lower()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(dict(self._item))
        super().mousePressEvent(event)

    @staticmethod
    def _time(ts) -> str:
        try:
            return datetime.fromtimestamp(ts / 1000).strftime("%I:%M %p")
        except Exception:
            return ""


class HistoryTab(QWidget):
    """Session-grouped log of live pushes and operator searches."""

    navigate_to_verse_requested = pyqtSignal(str, str, str, str)  # book, chapter, verse, translation

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._expanded: set[str] = set()  # session ids open in view
        self._built: set[str] = set()  # sessions whose items are built
        self._session_blocks: dict = {}  # sid -> (header_btn, sub, container)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 16)
        root.setSpacing(0)

        # ── Header: title + counts + refresh ──
        header_row = QHBoxLayout()
        header_row.setSpacing(12)

        title = QLabel("HISTORY")
        title.setStyleSheet(
            f"color: {WHITE}; font-size: 15px; font-weight: 800; "
            f"letter-spacing: 1px; background: transparent;")
        header_row.addWidget(title)

        self._counts = QLabel("")
        self._counts.setStyleSheet(
            f"color: {SLATE_500}; font-size: 11px; background: transparent;")
        header_row.addWidget(self._counts)
        header_row.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{ color: {WHITE}; }}
        """)
        refresh_btn.clicked.connect(self.reload)
        header_row.addWidget(refresh_btn)

        # ── Filter ──
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Filter history…")
        self._search_input.setStyleSheet(_SEARCH_INPUT_STYLE)
        self._search_input.setFixedHeight(40)
        self._search_input.textChanged.connect(self._filter_cards)

        # ── Scrollable session groups ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 8, 0, 0)
        self._cards_layout.setSpacing(6)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addLayout(header_row)
        left_layout.addWidget(self._search_input)
        left_layout.addWidget(scroll, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(left)
        self.preview_panel = HistoryPreviewPanel()
        self.preview_panel.navigate_verse_requested.connect(
            self.navigate_to_verse_requested.emit)
        splitter.addWidget(self.preview_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        from core.panel_layout import track_splitter
        self._columns_splitter = track_splitter(
            "history.columns", splitter, [700, 450])

        self.reload()

    def showEvent(self, event):
        super().showEvent(event)
        from core.panel_layout import restore_splitter
        restore_splitter("history.columns", self._columns_splitter)
        self.reload()

    # ── Loading ──────────────────────────────────────────────────────────

    def reload(self):
        """Rebuild session groups (newest first).

        Headers for every session are cheap (counts come with the query);
        items build lazily — newest session expands immediately, the rest on
        first expand (or when filtering). Previously expanded sessions stay so.
        """
        from core.database import get_history_sessions

        keep_expanded = set(self._expanded)
        self._expanded = set()
        self._built = set()
        self._session_blocks = {}

        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            sessions = get_history_sessions()[:_MAX_SESSIONS_SHOWN]
        except Exception as e:
            logger.error(f"Failed to load history sessions: {e}")
            sessions = []

        total_pushes = sum(s.get("pushes", 0) for s in sessions)
        total_searches = sum(s.get("searches", 0) for s in sessions)
        self._counts.setText(
            f"{len(sessions)} sessions · {total_pushes} live pushes · "
            f"{total_searches} searches")

        if not sessions:
            self._show_empty_state()
            return

        for order, session in enumerate(sessions):
            sid = session.get("session_id") or "global"
            header_btn, sub, container = self._add_session_block(session)
            self._session_blocks[sid] = (header_btn, sub, container)
            if order == 0 or sid in keep_expanded:
                self._expand_session(sid, session)

        self._filter_cards()

    def _session_title(self, session: dict) -> str:
        sid = session.get("session_id") or "global"
        start = session.get("start_time")
        end = session.get("end_time")
        try:
            day = (datetime.fromtimestamp((end or start) / 1000)
                   .strftime("%A, %B %d, %Y").upper() if (end or start) else "")
        except Exception:
            day = ""
        if sid == "global":
            return f"OUTSIDE SESSION{(' · ' + day) if day else ''}"
        return f"SESSION {sid}{(' · ' + day) if day else ''}"

    def _session_subtitle(self, session: dict) -> str:
        start = session.get("start_time")
        end = session.get("end_time")
        try:
            span = ""
            if start and end and end != start:
                span = (datetime.fromtimestamp(start / 1000).strftime("%I:%M %p")
                        + " – "
                        + datetime.fromtimestamp(end / 1000).strftime("%I:%M %p"))
            elif end or start:
                span = datetime.fromtimestamp(
                    (end or start) / 1000).strftime("%I:%M %p")
        except Exception:
            span = ""
        return (f"{session.get('pushes', 0)} live · "
                f"{session.get('searches', 0)} searches"
                + (f" · {span}" if span else ""))

    def _add_session_block(self, session: dict):
        sid = session.get("session_id") or "global"
        header_btn = QPushButton(("▾ " if sid in self._expanded else "▸ ")
                                 + self._session_title(session))
        header_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        header_btn.setStyleSheet(_DATE_HEADER_STYLE + """
            QPushButton { text-align: left; border: none; background: transparent; }
        """)
        header_btn.clicked.connect(lambda _=False, s=sid: self._toggle_session(s))
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, header_btn)

        sub = QLabel(self._session_subtitle(session))
        sub.setStyleSheet(_SESSION_SUB_STYLE)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, sub)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(6)
        container.setVisible(False)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, container)
        return header_btn, sub, container

    def _toggle_session(self, sid: str):
        if sid in self._expanded:
            self._expanded.discard(sid)
            block = self._session_blocks.get(sid)
            if block:
                block[0].setText("▸ " + self._session_title_text(block[0]))
                block[2].setVisible(False)
        else:
            self._expand_session(sid)

    @staticmethod
    def _session_title_text(header_btn) -> str:
        text = header_btn.text()
        return text[2:] if text[:2] in ("▾ ", "▸ ") else text

    def _expand_session(self, sid: str, session: dict | None = None):
        block = self._session_blocks.get(sid)
        if not block:
            return
        header_btn, _sub, container = block
        header_btn.setText("▾ " + self._session_title_text(header_btn))
        container.setVisible(True)
        self._expanded.add(sid)
        if sid not in self._built:
            self._built.add(sid)
            self._build_session_items(sid, container)
        self._filter_cards()

    def _build_session_items(self, sid: str, container: QWidget):
        from core.database import get_session_items
        from core.slide_parser import strip_inline_markup
        try:
            items = get_session_items(sid)
        except Exception as e:
            logger.error(f"Failed to load history items: {e}")
            return
        layout = container.layout()
        for item in items:
            card = self._card_for_item(item, strip_inline_markup)
            if card is not None:
                card.clicked.connect(self._on_card_selected)
                layout.addWidget(card)

    def _card_for_item(self, item: dict, strip_markup) -> HistoryCard | None:
        ts = HistoryCard._time(item.get("timestamp_ms"))
        if item.get("type") == "display":
            kind = (item.get("kind") or "verse").lower()
            if item.get("action") == "clear":
                return HistoryCard("clear", "Display cleared", "", ts, item)
            ref = item.get("ref", "")
            text = item.get("text", "")
            if kind == "slide":
                try:
                    text = strip_markup(text)
                except Exception:
                    pass
                title = ref or "Slide"
                body = (text[:160] + "…") if len(text) > 160 else text
                if item.get("translation"):
                    body = f"{body}  ·  {item['translation']}" if body else item["translation"]
                return HistoryCard("slide", title, body, ts, item)
            title = ref or "Verse"
            body = (text[:160] + "…") if len(text) > 160 else text
            if item.get("translation"):
                title = f"{title}  ·  {item['translation']}" if title else item["translation"]
            return HistoryCard("verse", title, body, ts, item)
        if item.get("type") == "search":
            lane = {"fts": "FTS", "fuzzy": "Fuzzy", "decks": "Decks"}.get(
                item.get("lane"), item.get("lane") or "Search")
            title = f"{lane} search: “{item.get('query', '')}”"
            lines = [f"{item.get('result_count', 0)} results"]
            tops = item.get("top_refs") or []
            if tops:
                lines.append(" · ".join(str(t) for t in tops[:5]))
            if item.get("chosen"):
                lines.append(f"→ {item['chosen']}")
            return HistoryCard("search", title, "\n".join(lines), ts, item)
        return None

    def _on_card_selected(self, item: dict):
        """Show a history row in the right preview column."""
        if not isinstance(item, dict):
            return
        if item.get("type") == "display":
            if item.get("action") == "clear":
                self.preview_panel.show_clear()
            elif (item.get("kind") or "verse").lower() == "slide":
                self.preview_panel.show_slide(
                    item.get("deck_id"), item.get("ref", ""),
                    item.get("text", ""), item.get("theme") or "slides")
            else:
                self.preview_panel.show_verse(
                    item.get("ref", ""), item.get("text", ""),
                    item.get("translation", ""), item.get("theme") or "default")
        elif item.get("type") == "search":
            self.preview_panel.show_search(
                item.get("query", ""), item.get("top_refs") or [],
                item.get("chosen"))

    def _show_empty_state(self):
        self._counts.setText("0 sessions")
        empty = QLabel("Nothing on record yet.\nAnything pushed to live will be documented here, grouped per session.")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(f"""
            color: {SLATE_500};
            font-size: 14px;
            padding: 60px 40px;
            line-height: 1.6;
        """)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, empty)

    # ── Filtering ────────────────────────────────────────────────────────

    def _iter_cards(self):
        for sid, (_header, _sub, container) in (self._session_blocks or {}).items():
            layout = container.layout()
            for i in range(layout.count()):
                widget = layout.itemAt(i).widget()
                if isinstance(widget, HistoryCard):
                    yield sid, widget

    def _filter_cards(self):
        search = self._search_input.text().strip().lower()
        if search:
            # Matches may hide in collapsed sessions — build them on demand.
            for sid in list((self._session_blocks or {}).keys()):
                if sid not in self._built:
                    self._built.add(sid)
                    block = self._session_blocks.get(sid)
                    if block:
                        self._build_session_items(sid, block[2])
        visible_per_session: dict[str, int] = {}
        for sid, widget in self._iter_cards():
            show = not search or search in widget._text
            widget.setVisible(show)
            if show:
                visible_per_session[sid] = visible_per_session.get(sid, 0) + 1
        for sid, (header, sub, container) in (self._session_blocks or {}).items():
            # A session with no visible cards hides wholesale while filtering.
            block_visible = (not search) or visible_per_session.get(sid, 0) > 0
            header.setVisible(block_visible)
            sub.setVisible(block_visible)
            container.setVisible(block_visible and sid in self._expanded)
