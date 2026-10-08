"""
ui/widgets/search_history.py

Terminal-style search history for the search textboxes (FTS, Fuzzy, deck
search). Up/Down walk the entries and overwrite the box, exactly like a
shell.

SESSION-ONLY BY CONSTRUCTION: entries live in a Python list on this object
and are never written to the settings DB, history tables, or disk. Closing
the app drops them, which is the requested behavior — nothing to clean up,
nothing to migrate.

A query only qualifies for the history when the operator shows they meant
it. Every keystroke is technically a search (these boxes search live), so
raw keystrokes would flood the list. Three signals qualify a query:

  1. IDLE — typing stopped for `idle_ms` (default 2s). The box settles on
     one query and nothing else happens: that is a real search.
  2. RESULT CLICKED — the operator navigated to / displayed / scheduled a
     hit. Unambiguously the query they wanted.
  3. RESULTS SCROLLED — the operator read past the first screen, so they
     were reading hits, not typing.

(1) is automatic. (2) and (3) call `note_used()` from the panels.

Scrolling needs care: rendering results scrolls the list programmatically,
and that must NOT count. `bind_scroll()` therefore waits for the scroll
position to settle before treating any movement as a user scroll.
"""

import logging

from PyQt6.QtCore import QEvent, QObject, QTimer, Qt

logger = logging.getLogger(__name__)

# Settle window after a render before scroll movement counts as the
# operator's own. Progressive paint chains can scroll the list after the
# first frame, so this cannot be zero.
SCROLL_SETTLE_MS = 300


class SearchHistory(QObject):
    """Up/Down recall over qualifying queries for one search textbox."""

    def __init__(self, field, idle_ms: int = 2000, max_entries: int = 50,
                 parent=None):
        super().__init__(parent or field)
        self._field = field
        self._idle_ms = idle_ms
        self._max_entries = max(1, max_entries)
        # Most recent first (terminal order): entries()[0] is the newest.
        self._entries: list[str] = []
        self._nav_index: int | None = None   # None = not navigating
        self._draft = ""                     # text to restore on nav exit
        self._applying = False              # guard for programmatic writes

        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._on_idle)
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._on_scroll_settled)
        self._scrollbar = None
        self._armed_value: int | None = None

        field.installEventFilter(self)
        field.textChanged.connect(self._on_text_changed)

    # ── public API ──────────────────────────────────────────────────────────

    @property
    def entries(self) -> list[str]:
        """Queries, newest first."""
        return list(self._entries)

    def add(self, text: str) -> bool:
        """Record a qualifying query. Returns True if it was added."""
        query = (text or "").strip()
        if not query:
            return False
        if self._entries and self._entries[0] == query:
            self._nav_index = None
            return False
        self._entries.insert(0, query)
        del self._entries[self._max_entries:]
        self._nav_index = None
        logger.debug("Search history += %r (%d entries)", query, len(self._entries))
        return True

    def note_used(self) -> bool:
        """The operator used this query's results (clicked a hit or
        scrolled them) — qualify it now, without waiting for idle."""
        self._idle_timer.stop()
        return self.add(self._current_text())

    def bind_scroll(self, scrollbar) -> None:
        """Treat operator scrolling of a results list as `note_used()`."""
        if scrollbar is None:
            return
        self._scrollbar = scrollbar
        try:
            scrollbar.valueChanged.connect(self._on_scrolled)
        except (RuntimeError, TypeError):
            self._scrollbar = None

    def arm_scroll(self) -> None:
        """Called when results (re)render: scroll position is about to move
        on its own, so re-arm after it settles."""
        self._settle_timer.start(SCROLL_SETTLE_MS)

    def clear(self) -> None:
        """Drop everything (also the session wipe hook, if ever needed)."""
        self._entries.clear()
        self._nav_index = None
        self._draft = ""

    # ── recall ──────────────────────────────────────────────────────────────

    def previous(self) -> str | None:
        """Up: overwrite the box with the previous (older) entry.

        Skips any entry equal to what the box ALREADY holds: the current
        query is in the history (it qualified like any other), so naively
        returning entries[0] would rewrite the box with itself — rerunning
        the same search and wasting the press. The first Up must land on
        the query BEFORE the current one.
        """
        if not self._entries:
            return None
        current = self._current_text().strip()
        if self._nav_index is None:
            self._draft = self._current_text()
            start = 0
            while start < len(self._entries) and self._entries[start] == current:
                start += 1
            if start >= len(self._entries):
                return None      # nothing older than the current query
            self._nav_index = start
        elif self._nav_index < len(self._entries) - 1:
            self._nav_index += 1
        # else: already at the oldest entry — stay (shell clamps here too).
        text = self._entries[self._nav_index]
        self._write(text)
        return text

    def next(self) -> str | None:
        """Down: newer entry, or the text that was there before navigating."""
        if self._nav_index is None or not self._entries:
            return None
        if self._nav_index > 0:
            self._nav_index -= 1
            text = self._entries[self._nav_index]
        else:
            # Past the newest entry: restore what the operator had typed.
            self._nav_index = None
            text = self._draft
        self._write(text)
        return text

    def _current_text(self) -> str:
        try:
            return self._field.text()
        except (RuntimeError, AttributeError):
            return ""

    def _write(self, text: str) -> None:
        """Overwrite the box without that write re-qualifying itself."""
        if text == self._current_text():
            return          # identical: leave the box (and its search) alone
        self._applying = True
        try:
            field = self._field
            # Portable across QLineEdit and QTextEdit: the search boxes are
            # plain QLineEdits, and calling setPlainText on one raises
            # AttributeError — which a bare `except` here swallowed, so
            # recall silently wrote nothing at all.
            if hasattr(field, "setText"):
                field.setText(text)
                field.setCursorPosition(len(text))
            else:
                field.setPlainText(text)
                cursor = field.textCursor()
                cursor.movePosition(cursor.MoveOperation.End)
                field.setTextCursor(cursor)
        except RuntimeError:
            pass  # the box was destroyed mid-recall
        finally:
            self._applying = False

    # ── signals ─────────────────────────────────────────────────────────────

    def _on_text_changed(self, *_args) -> None:
        if self._applying:
            return
        # Any real edit abandons an in-progress recall walk.
        self._nav_index = None
        if self._current_text().strip():
            self._idle_timer.start(self._idle_ms)
        else:
            self._idle_timer.stop()

    def _on_idle(self) -> None:
        self.add(self._current_text())

    def _on_scrolled(self, value: int) -> None:
        if self._settle_timer.isActive():
            return          # render-time scrolling, not the operator's
        if self._armed_value is None or value == self._armed_value:
            return
        self.note_used()

    def _on_scroll_settled(self) -> None:
        # Stop first: this is normally the timeout handler, but it is also
        # called directly (teardown, tests) and the arming must not leave
        # the settle timer running to swallow the next real scroll.
        try:
            if self._settle_timer.isActive():
                self._settle_timer.stop()
        except RuntimeError:
            pass
        if self._scrollbar is None:
            self._armed_value = None
            return
        try:
            self._armed_value = self._scrollbar.value()
        except RuntimeError:
            self._armed_value = None

    # ── keys ────────────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        """Up/Down walk history (single-line boxes: otherwise no-ops)."""
        if obj is not self._field or event.type() != QEvent.Type.KeyPress:
            return False
        if not self._entries:
            return False
        mods = event.modifiers()
        if mods & (Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.AltModifier
                   | Qt.KeyboardModifier.MetaModifier
                   | Qt.KeyboardModifier.ShiftModifier):
            return False
        key = event.key()
        if key == Qt.Key.Key_Up:
            text = self.previous()
        elif key == Qt.Key.Key_Down:
            text = self.next()
        else:
            return False
        # previous()/next() already overwrote the box; None = nothing to
        # recall, so let the key through untouched.
        return text is not None