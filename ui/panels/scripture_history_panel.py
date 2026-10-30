"""
ui/panels/scripture_history_panel.py

Scripture history panel — the minimal log of scriptures pushed live.

One vertically minimal entry per displayed scripture: the reference plus
the Bible version that was displayed (no Schedule-style [NIV] prefix).
Deck slides, clears and searches never arrive here — scriptures only.

Rows append at the bottom like the STT transcript: a running log where
the very last row is the scripture currently on the live screen.
Single click navigates the browser to the scripture in the translation
it was displayed in; double click pushes it live again and records it
again — unless that row is already the newest one, so the log never
shows the same scripture twice back to back.

The log is session-scoped: it only holds scriptures displayed in the
current session — one app run, plus the live transcription session
inside it. When a session ends — STT session ending, service restart,
or the app closing — the panel wipes and the next session starts
empty. Backfill never resurrects rows stamped before this run booted.
The raw display log is never rewritten; scoping is how this panel
reads it.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_400, SLATE_500, SLATE_600, WHITE,
    ACCENT_SOFT, BG_PANEL, PANEL_BODY_STYLE,
    TEXT_FAINT,
)

logger = logging.getLogger(__name__)

_ROW_QSS = f"""
    QFrame {{
        background: transparent;
        border-radius: 4px;
    }}
    QFrame:hover {{
        background: {ACCENT_SOFT};
    }}
"""

_EMPTY_QSS = f"""
    color: {TEXT_FAINT};
    font-size: 12px;
    padding: 10px 4px;
"""

_BACKFILL_LIMIT = 200


class ScriptureHistoryRow(QFrame):
    """One recorded scripture: `John 3:16 · NIV` on a single row."""

    clicked = pyqtSignal(dict)
    double_clicked = pyqtSignal(dict)

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self._entry = dict(entry)
        self._key = entry.get("key")
        self.setStyleSheet(_ROW_QSS)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(self._entry.get("tooltip", ""))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(6)

        ref = self._entry.get("display_ref") or "—"
        ref_label = QLabel(ref)
        ref_label.setStyleSheet(
            f"color: {WHITE}; font-size: 12px; font-weight: 600;")
        layout.addWidget(ref_label)

        layout.addStretch()

        version = self._entry.get("display_translation") or ""
        if version:
            version_label = QLabel(version)
            version_label.setStyleSheet(
                f"color: {SLATE_500}; font-size: 12px; font-weight: 600;")
            layout.addWidget(version_label)

    @property
    def key(self):
        return self._key

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._entry)
        else:
            super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit(self._entry)


class ScriptureHistoryPanel(QWidget):
    """Scriptures that hit live, recorded one row per display."""

    verse_selected = pyqtSignal(dict)        # single click → navigate in browser
    verse_double_clicked = pyqtSignal(dict)  # double click → push live again

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._rows: list = []  # chronological (oldest first); rows[-1] = newest
        self._session_id: str | None = None  # which session rows==None → unknown

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: {BG_PANEL};
                border: none;
            }}
        """)
        # Every new row lands where the operator is already looking: the
        # end of the log like the STT transcript. Range changes are the
        # late finisher — a row inserted before the panel has been laid
        # out (boot backfill, hidden tab) fires this the moment there is
        # something to scroll to.
        self._scroll.verticalScrollBar().rangeChanged.connect(
            self._on_range_changed)
        self._pending_scroll = False

        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._list = QVBoxLayout(self._container)
        self._list.setContentsMargins(0, 2, 0, 2)
        self._list.setSpacing(2)
        self._list.addStretch()
        self._scroll.setWidget(self._container)

        self._empty = QLabel("No scriptures displayed yet.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self._empty.setStyleSheet(_EMPTY_QSS)

        layout.addWidget(self._scroll, 1)
        layout.addWidget(self._empty)

        self._empty.setVisible(True)
        self._scroll.setVisible(False)

        self._hydrate()

    # ── Display hooks (called by PresentationTab) ────────────────────────

    def record_display(self, verse: dict) -> bool:
        """Record a scripture that reached the live screen.

        Session-scoped: a scripture recorded in a session that already
        ended would resurrect a dead log, so the panel wipes first when
        the operator session id has changed since the last row. Returns
        True when a row was added. A scripture identical to the newest
        entry is never recorded again — pushing the same verse twice in
        a row (queue Show, live double-click, recall) stays one line,
        and a double-click on the very last row cannot duplicate it.
        """
        self._enforce_session()
        entry = self._entry_from_verse(verse)
        if entry is None:
            return False
        return self._append(entry)

    # ── Internals ─────────────────────────────────────────────────────────

    def _wipe(self):
        """Drop every row (session ended). The raw display log keeps its
        rows; this view rule means a finished session never leaks across."""
        while self._list.count() > 1:  # the last item is the layout stretch
            item = self._list.itemAt(0)
            widget = item.widget()
            self._list.removeItem(item)
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()
        self._empty.setVisible(True)
        self._scroll.setVisible(False)

    def _current_session(self) -> str | None:
        try:
            from core.database import current_operator_session
            return current_operator_session()
        except Exception as e:
            logger.debug(f"Session lookup failed: {e}")
            return None

    def _enforce_session(self):
        """Wipe the log when the operator session id has changed."""
        sid = self._current_session()
        if sid is None or sid == self._session_id:
            return
        self._wipe()
        self._session_id = sid

    def _append(self, entry: dict) -> bool:
        if self._rows and self._rows[-1]["key"] == entry["key"]:
            return False
        self._rows.append(entry)
        row = ScriptureHistoryRow(entry)
        row.clicked.connect(self.verse_selected.emit)
        row.double_clicked.connect(self.verse_double_clicked.emit)
        self._list.insertWidget(self._list.count() - 1, row)
        self._empty.setVisible(False)
        self._scroll.setVisible(True)
        self._request_scroll_to_end()
        return True

    def _request_scroll_to_end(self):
        """Follow the new row: try now, finish via rangeChanged later."""
        self._pending_scroll = True
        self._scroll_to_end()

    def _scroll_to_end(self):
        bar = self._scroll.verticalScrollBar()
        if bar.maximum() == 0:
            return  # nothing laid out yet — rangeChanged picks this up
        bar.setValue(bar.maximum())
        self._pending_scroll = False

    def _on_range_changed(self, minimum: int, maximum: int):
        if self._pending_scroll and maximum > 0:
            self._scroll_to_end()

    @staticmethod
    def _entry_from_verse(verse: dict) -> dict | None:
        if not isinstance(verse, dict):
            return None
        book = verse.get("book", "")
        chapter = str(verse.get("chapter", ""))
        verse_num = str(verse.get("verse_num", ""))
        code = verse.get("version", "")
        if not (book and chapter and verse_num):
            return None
        display_name = code
        if code:
            from core.bible_service import get_display_name
            display_name = get_display_name(code)
        key = (book.lower(), chapter, verse_num.lower(), code.lower())
        return {
            "key": key,
            "book": book,
            "chapter": chapter,
            "verse_num": verse_num,
            "version": code,
            "display_ref": f"{book} {chapter}:{verse_num}",
            "display_translation": display_name,
            "text": verse.get("text", ""),
        }

    @staticmethod
    def _entry_from_db_row(row: dict) -> dict | None:
        ref = row.get("ref") or ""
        ref = ref.split("] ", 1)[1] if "] " in ref else ref
        parts = ref.rsplit(":", 1)
        book_chapter = parts[0] if len(parts) == 2 else ref
        verse_num = parts[1] if len(parts) == 2 else ""
        book = book_chapter.rsplit(" ", 1)[0] if " " in book_chapter else book_chapter
        chapter = book_chapter.rsplit(" ", 1)[1] if " " in book_chapter else ""
        if not (book and chapter and verse_num):
            return None
        display_name = row.get("translation") or ""
        code = ""
        if display_name:
            code = ScriptureHistoryPanel._code_for_display(display_name)
        key = (book.lower(), chapter, verse_num.lower(),
               (code or display_name).lower())
        return {
            "key": key,
            "book": book,
            "chapter": chapter,
            "verse_num": verse_num,
            "version": code,
            "display_ref": ref,
            "display_translation": display_name,
            "text": row.get("text") or "",
        }

    @staticmethod
    def _code_for_display(display_name: str) -> str:
        """Canonical translation code for a display name ('' when unknown)."""
        try:
            from core.bible_service import (get_available_translations,
                                            get_display_name)
            for code in get_available_translations():
                if get_display_name(code) == display_name:
                    return code
        except Exception as e:
            logger.debug(f"Display-name lookup failed: {e}")
        return ""

    def _hydrate(self):
        """Load the current session's past scripture displays.

        Newest first, collapsed to the "no consecutive duplicates" view:
        the DB keeps every raw push, the panel shows one line per distinct
        consecutive display so dedupes survive app restarts identically.
        The SQL helper scopes to this run's boot — a previous run's rows
        are already out — and the session check below adds the live
        transcription boundary on top.
        """
        sid = self._current_session()
        if sid is not None:
            self._session_id = sid
        from core.database import get_scripture_display_history
        try:
            rows = get_scripture_display_history(limit=_BACKFILL_LIMIT)
        except Exception as e:
            logger.error(f"Failed to load scripture history: {e}")
            rows = []
        entries = []
        for row in rows:
            entry = self._entry_from_db_row(row)
            if entry is None:
                continue
            if entries and entries[-1]["key"] == entry["key"]:
                continue
            entries.append(entry)
        for entry in reversed(entries):  # oldest first, append order
            self._append(entry)

    def showEvent(self, event):
        """On reveal: catch a session change and (re)fill an empty log.

        The check on record_display covers the common flow; this covers
        the session that started while the panel was hidden — the
        operator lands on the tab after service start and sees the
        session's own backfill, nothing from the session before it.
        """
        super().showEvent(event)
        self._on_revealed()

    def _on_revealed(self):
        sid = self._current_session()
        if sid is not None and sid != self._session_id:
            self._wipe()
            self._session_id = sid
        if not self._rows:
            self._hydrate()
