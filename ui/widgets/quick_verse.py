"""
ui/widgets/quick_verse.py

Type-a-verse-number quick push.

The shortcut is APP-WIDE: whenever the caret is not somewhere that
legitimately consumes bare digits — an FTS or Fuzzy search box, any other
text input, a spin box or a combo — bare digit presses are intercepted
out of nowhere and collected into a short-lived buffer:

  * first digit      → recording starts, digit consumed (never reaches the
                       panel, a hotkey, or a shortcut)
  * further digits   → appended while each gap stays under the configured
                       timeout (Settings → ``bible.quick_verse_timeout_ms``)
  * Enter            → buffer is committed (``committed`` fires), consumed
  * Esc              → recording cancelled, consumed — even if Esc is bound
                       to a hotkey, that hotkey does NOT fire
  * timeout / focus leaves the panel → buffer silently discarded

Only ASCII digits are ever accepted; everything else passes through
untouched. The recorder owns no UI — it emits ``buffer_changed`` so the
panel can show (or hide) its little badge.
"""

import logging
import weakref

from PyQt6.QtCore import QObject, QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox,
                             QLineEdit, QPlainTextEdit, QTextEdit)

from core.database import get_setting

logger = logging.getLogger(__name__)

_TEXT_INPUT_TYPES = (QLineEdit, QTextEdit, QPlainTextEdit)

# Widgets that legitimately own bare digits. Search boxes (QLineEdit /
# SearchField / QTextEdit) are the case that matters — the operator must be
# able to type "psalm 23" into FTS or Fuzzy without a verse push firing on
# every keystroke — but spin boxes and combos are included for the same
# reason: a digit typed into one of those is data, not a verse reference.
_DIGIT_CONSUMING_TYPES = _TEXT_INPUT_TYPES + (QAbstractSpinBox, QComboBox)


def _within(widget, ancestor) -> bool:
    """Is `widget` `ancestor` or a descendant of it?"""
    if widget is None or ancestor is None:
        return False
    try:
        w = widget
        while w is not None:
            if w is ancestor:
                return True
            w = w.parentWidget()
    except RuntimeError:
        return False
    return False


def _is_digit_consuming(widget) -> bool:
    """Does this widget want bare digit keystrokes for itself?

    Checks the widget AND its ancestors: a QSpinBox hands focus to an
    internal line edit, and composite inputs can wrap one.
    """
    try:
        w = widget
        while w is not None:
            if isinstance(w, _DIGIT_CONSUMING_TYPES):
                return True
            w = w.parentWidget()
    except RuntimeError:
        return False
    return False


def quick_verse_timeout_ms() -> int:
    """Live-read inter-keystroke budget, clamped to the sane range."""
    from core import constants as _c
    default = int(getattr(_c, "QUICK_VERSE_TIMEOUT_MS_DEFAULT", 500))
    try:
        value = int(get_setting("bible.quick_verse_timeout_ms", str(default)))
    except (TypeError, ValueError):
        return default
    lo = int(getattr(_c, "QUICK_VERSE_TIMEOUT_MS_MIN", 50))
    hi = int(getattr(_c, "QUICK_VERSE_TIMEOUT_MS_MAX", 2000))
    return max(lo, min(hi, value))


class QuickVerseRecorder(QObject):
    """Watches keys for one Bible panel; see module docstring for the dance."""

    committed = pyqtSignal(str)       # digits, on Enter
    buffer_changed = pyqtSignal(str)  # current buffer ("" when cleared)

    def __init__(self, panel, parent=None):
        # Parented to the panel: Qt auto-removes a dead object from the
        # app's event-filter list, so teardown needs no explicit call.
        super().__init__(parent or panel)
        self._panel_ref = weakref.ref(panel)
        self._buffer = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_timeout)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)
            app.focusChanged.connect(self._on_focus_changed)

    # ── state ────────────────────────────────────────────────────────────────

    @property
    def buffer(self) -> str:
        return self._buffer

    @property
    def is_recording(self) -> bool:
        return bool(self._buffer)

    def _panel(self):
        try:
            return self._panel_ref()
        except Exception:
            return None

    def _focus_in_panel(self) -> bool:
        """True while the caret is anywhere inside the Bible panel.

        No longer what gates recording — that is app-wide now — but still
        meaningful for panel-local concerns, and kept because the badge
        lives on this panel.
        """
        panel = self._panel()
        if panel is None:
            return False
        return _within(QApplication.focusWidget(), panel)

    def _focus_consumes_digits(self) -> bool:
        """Does the focused widget legitimately want bare digit presses?

        True for the FTS and Fuzzy search boxes (SearchField is a
        QTextEdit), for every other text input, and for spin boxes and
        combos. None of those may have its keystrokes stolen.
        """
        return _is_digit_consuming(QApplication.focusWidget())

    def _capture_allowed(self) -> bool:
        """May a bare digit start/extend a take right now?

        Deliberately not conditioned on being inside the Bible panel: the
        shortcut works from anywhere except a widget that wants the
        digits itself.
        """
        if self._panel() is None:
            return False
        if not self._window_active():
            return False
        try:
            if QApplication.activeModalWidget() is not None:
                return False  # a dialog owns Esc and every other key
        except RuntimeError:
            return False
        return not self._focus_consumes_digits()

    def _window_active(self) -> bool:
        """Does the application have an active window at all?

        Deliberately NOT "is the Bible panel's window active" any more:
        recording is app-wide, so a different top-level being focused is
        no longer a reason to stand down. What still stands it down is a
        modal dialog, checked separately in _capture_allowed.
        """
        try:
            return QApplication.activeWindow() is not None
        except RuntimeError:
            return False

    @staticmethod
    def _plain_mods(event) -> bool:
        """No real modifiers — bare keys only (keypad modifier is fine)."""
        mods = event.modifiers()
        return not (mods & ~Qt.KeyboardModifier.KeypadModifier)

    @staticmethod
    def _is_digit(event) -> bool:
        text = event.text()
        return len(text) == 1 and text.isascii() and text.isdigit()

    # ── event flow ───────────────────────────────────────────────────────────

    def _suppress_shortcut(self, event) -> bool:
        """Should this press be hidden from QShortcut matching?

        Consuming a KeyPress is NOT enough — the shortcut system fires
        anyway (verified). Accepting ShortcutOverride first is what keeps
        a digit-/Enter-/Esc-bound hotkey silent while we own the key.
        """
        if event.isAutoRepeat() or not self._plain_mods(event):
            return False
        if not self._capture_allowed():
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape:
            return self.is_recording  # Esc hijack lives only while recording
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return self.is_recording  # bare Enter commits; else hands off
        return self._is_digit(event)  # digits always start/extend a take

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent as _QE
        event_type = event.type()
        if event_type == _QE.Type.ShortcutOverride:
            if self._suppress_shortcut(event):
                event.accept()
                return True
            return False
        if event_type != _QE.Type.KeyPress:
            return False
        if self._handle_key(event):
            event.accept()
            return True
        return False

    def _handle_key(self, event) -> bool:
        """Consume (True) or pass through (False) a key press."""
        if event.isAutoRepeat():
            return False
        if not self._plain_mods(event):
            return False
        if not self._capture_allowed():
            return False
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if not self.is_recording:
                return False
            self._cancel()
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if not self.is_recording:
                return False
            self._commit()
            return True
        if self._is_digit(event):
            self._append(event.text())
            return True
        return False

    @staticmethod
    def _is_text_input(widget) -> bool:
        try:
            return isinstance(widget, _TEXT_INPUT_TYPES)
        except RuntimeError:
            return False

    # ── buffer ───────────────────────────────────────────────────────────────

    def _append(self, digit: str):
        self._buffer += digit
        self._timer.start(quick_verse_timeout_ms())
        self.buffer_changed.emit(self._buffer)

    def _commit(self):
        digits = self._buffer
        self._clear(silent=True)
        if digits:
            self.committed.emit(digits)

    def _cancel(self):
        self._clear(silent=True)

    def _on_timeout(self):
        self._clear(silent=True)

    def _on_focus_changed(self, _old, new):
        """Abandon a take that is no longer ours to commit.

        Recording is app-wide, so moving between panels no longer
        invalidates it — that is the whole point. What DOES invalidate it
        is arriving somewhere that wants the digits themselves: typing a
        number into a search box must never leave a buffer that a later
        Enter somewhere else commits as a verse.
        """
        if not self.is_recording:
            return
        try:
            if self._panel() is None:
                self._clear(silent=True)
                return
            if new is None or _is_digit_consuming(new):
                self._clear(silent=True)
        except RuntimeError:
            pass

    def _clear(self, silent=False):
        had = bool(self._buffer)
        self._buffer = ""
        try:
            if self._timer.isActive():
                self._timer.stop()
        except RuntimeError:
            pass
        if had:
            self.buffer_changed.emit("")
