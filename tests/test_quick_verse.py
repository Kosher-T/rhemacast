"""Bible quick-verse typing: bare digits + Enter push a verse from anywhere
in the Bible panel (outside real inputs), with a short-lived buffer.

Contract under test:
  * digits typed < timeout apart accumulate; anything else passes through
  * Enter commits the buffer (inject → navigate → push), then consumes
  * Esc cancels the buffer and hijacks Esc — a hotkey bound to Esc must NOT
    fire while recording (but fires normally when not recording)
  * timeout or focus leaving the panel silently discards the buffer
  * text inputs never lose keystrokes to the recorder
  * an invalid verse number commits to nothing (no navigate, no push)
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtWidgets import (QApplication, QComboBox, QLineEdit,
                             QPushButton, QTextEdit, QVBoxLayout,
                             QWidget)

QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest

import core.database as db


_app = None


def _qt():
    # Module-global reference: if the last Python handle to the
    # QApplication wrapper dies, PyQt tears down the C++ app with it and
    # every later QWidget() aborts the process. (Same pattern as
    # test_panel_focus_ring.py.)
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


_HOSTS = []


def _host(*widgets):
    """Show widgets in a kept-alive active window (focusWidget only reports
    the active window's focus)."""
    app = _qt()
    host = QWidget()
    lay = QVBoxLayout(host)
    for w in widgets:
        lay.addWidget(w)
    host.resize(500, 400)
    host.show()
    app.setActiveWindow(host)
    app.processEvents()
    _HOSTS.append(host)
    return host


def _panel_fixture():
    """A stand-in Bible panel: a focusable non-input plus a real text input."""
    from ui.widgets.quick_verse import QuickVerseRecorder
    _qt()
    panel = QWidget()
    lay = QVBoxLayout(panel)
    pad = QPushButton("row")   # focusable, not a text input: eligible
    edit = QLineEdit()         # real typing: never hijacked
    lay.addWidget(pad)
    lay.addWidget(edit)
    host = _host(panel)
    recorder = QuickVerseRecorder(panel)
    committed, changed = [], []
    recorder.committed.connect(committed.append)
    recorder.buffer_changed.connect(changed.append)
    return {
        "panel": panel, "host": host, "pad": pad, "edit": edit,
        "recorder": recorder, "committed": committed, "changed": changed,
    }


class _Focusable(QWidget):
    """A focusable widget that is not a text input."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)


def _within(widget, ancestor):
    """Is `widget` `ancestor` or a descendant of it?"""
    if widget is None or ancestor is None:
        return False
    w = widget
    while w is not None:
        if w is ancestor:
            return True
        w = w.parentWidget()
    return False


def _key(widget, key):
    from PyQt6.QtTest import QTest
    QTest.keyClick(widget, key)
    _qt().processEvents()


# ─── buffering + commit ─────────────────────────────────────────────────────

def test_digits_buffer_and_enter_commits():
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]

    _key(fx["pad"], Qt.Key.Key_1)
    _key(fx["pad"], Qt.Key.Key_2)
    assert fx["recorder"].buffer == "12"
    assert fx["committed"] == []

    _key(fx["pad"], Qt.Key.Key_Return)
    assert fx["committed"] == ["12"]
    assert fx["recorder"].buffer == ""
    # badge cleared after commit
    assert fx["changed"][-1] == ""


def test_non_digits_pass_through_untouched():
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]
    _key(fx["pad"], Qt.Key.Key_A)
    assert fx["recorder"].buffer == ""
    assert fx["committed"] == []
    assert fx["changed"] == []


def test_text_inputs_keep_their_keystrokes():
    fx = _panel_fixture()
    fx["edit"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["edit"]
    _key(fx["edit"], Qt.Key.Key_5)
    assert fx["recorder"].buffer == ""
    assert fx["committed"] == []
    assert fx["edit"].text() == "5"


def test_enter_without_recording_passes_through():
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]
    _key(fx["pad"], Qt.Key.Key_Return)
    assert fx["committed"] == []
    assert fx["changed"] == []


# ─── timeout ────────────────────────────────────────────────────────────────

def test_timeout_discards_the_buffer(monkeypatch):
    import ui.widgets.quick_verse as qv
    monkeypatch.setattr(qv, "quick_verse_timeout_ms", lambda: 40)
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]
    _key(fx["pad"], Qt.Key.Key_5)
    assert fx["recorder"].buffer == "5"
    # the discard is armed with the configured budget (no wall-clock sleep:
    # QTimer firing itself is Qt's business, not ours to re-prove)
    assert fx["recorder"]._timer.isActive()
    assert fx["recorder"]._timer.interval() == 40
    fx["recorder"]._on_timeout()
    assert fx["recorder"].buffer == ""
    assert fx["committed"] == []
    assert fx["changed"][-1] == ""


def test_timeout_setting_default_and_clamp(tmp_path, monkeypatch):
    import ui.widgets.quick_verse as qv
    import core.constants as const
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    assert qv.quick_verse_timeout_ms() == const.QUICK_VERSE_TIMEOUT_MS_DEFAULT
    db.set_setting("bible.quick_verse_timeout_ms", "99999")
    assert qv.quick_verse_timeout_ms() == const.QUICK_VERSE_TIMEOUT_MS_MAX
    db.set_setting("bible.quick_verse_timeout_ms", "not-a-number")
    assert qv.quick_verse_timeout_ms() == const.QUICK_VERSE_TIMEOUT_MS_DEFAULT


# ─── Esc hijack ─────────────────────────────────────────────────────────────

def test_esc_cancels_and_hijacks_hotkey_while_recording():
    from PyQt6.QtGui import QShortcut, QKeySequence
    fx = _panel_fixture()
    fired = []
    esc = QShortcut(QKeySequence(Qt.Key.Key_Escape), fx["host"])
    esc.activated.connect(lambda: fired.append("esc"))
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]

    _key(fx["pad"], Qt.Key.Key_3)
    assert fx["recorder"].buffer == "3"
    _key(fx["pad"], Qt.Key.Key_Escape)
    # buffer gone AND the Esc hotkey never fired
    assert fx["recorder"].buffer == ""
    assert fx["committed"] == []
    assert fired == []

    # not recording anymore: Esc behaves normally again
    _key(fx["pad"], Qt.Key.Key_Escape)
    assert fired == ["esc"]


def test_focus_entering_a_text_input_abandons_the_take():
    """A number typed into a box must never leave a buffer behind that a
    later Enter somewhere else commits as a verse."""
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is fx["pad"]
    _key(fx["pad"], Qt.Key.Key_7)
    assert fx["recorder"].buffer == "7"
    elsewhere = QLineEdit()
    other_host = _host(elsewhere)
    _qt().setActiveWindow(other_host)
    elsewhere.setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is elsewhere
    assert fx["recorder"].buffer == ""
    assert fx["committed"] == []


def test_moving_between_panels_keeps_the_take():
    """Recording is app-wide, so walking off the Bible panel and back must
    NOT discard what was typed. This is the behaviour change from scoping
    the recorder to the panel."""
    fx = _panel_fixture()
    fx["pad"].setFocus()
    _qt().processEvents()
    _key(fx["pad"], Qt.Key.Key_1)
    _key(fx["pad"], Qt.Key.Key_9)
    assert fx["recorder"].buffer == "19"

    # somewhere else entirely, but still not a digit-consuming widget
    elsewhere = QPushButton("elsewhere")
    other_host = _host(elsewhere)
    _qt().setActiveWindow(other_host)
    elsewhere.setFocus()
    _qt().processEvents()
    assert QApplication.focusWidget() is elsewhere
    assert fx["recorder"].buffer == "19", "take abandoned by a panel change"

    _key(elsewhere, Qt.Key.Key_Return)
    assert fx["committed"] == ["19"], "Enter away from the panel must commit"


def test_capture_works_from_outside_the_bible_panel():
    """The shortcut is not gated on being inside the Bible panel."""
    fx = _panel_fixture()
    elsewhere = QPushButton("elsewhere")
    other_host = _host(elsewhere)
    _qt().setActiveWindow(other_host)
    elsewhere.setFocus()
    _qt().processEvents()
    assert not _within(QApplication.focusWidget(), fx["panel"])

    _key(elsewhere, Qt.Key.Key_2)
    _key(elsewhere, Qt.Key.Key_3)
    assert fx["recorder"].buffer == "23"
    _key(elsewhere, Qt.Key.Key_Return)
    assert fx["committed"] == ["23"]


def test_search_boxes_are_never_hijacked():
    """FTS and Fuzzy boxes are the case that matters: the operator is
    typing a query, and every digit must reach the box."""
    for factory in (lambda: QLineEdit(), lambda: QTextEdit()):
        fx = _panel_fixture()
        box = factory()
        host = _host(box)
        _qt().setActiveWindow(host)
        box.setFocus()
        _qt().processEvents()
        assert QApplication.focusWidget() is box
        _key(box, Qt.Key.Key_1)
        _key(box, Qt.Key.Key_9)
        assert fx["recorder"].buffer == "", (
            "a search box lost its digits to the verse shortcut")
        assert fx["committed"] == []


def test_spin_boxes_and_combos_keep_their_digits():
    """Same rule for the other widgets that legitimately consume digits."""
    from PyQt6.QtWidgets import QSpinBox
    for widget in (QSpinBox(), QComboBox()):
        fx = _panel_fixture()
        host = _host(widget)
        _qt().setActiveWindow(host)
        widget.setFocus()
        _qt().processEvents()
        _key(widget, Qt.Key.Key_5)
        assert fx["recorder"].buffer == "", (
            "%s lost a digit to the verse shortcut" % type(widget).__name__)


# ─── commit path on the real panel ──────────────────────────────────────────

def _browser_panel(monkeypatch, tmp_path):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    from ui.panels.browser_panel import BrowserPanel
    panel = BrowserPanel(translations=["KJV"])
    host = _host(panel)
    return panel, host


def test_commit_injects_navigates_and_pushes(monkeypatch, tmp_path):
    import core.bible_service as bible_service
    monkeypatch.setattr(bible_service, "get_verse_count", lambda v, b, c: 50)
    panel, _host = _browser_panel(monkeypatch, tmp_path)
    panel.predictive_input.book_input.set_value("Genesis")
    panel.predictive_input.chapter_input.set_value(1)

    navigated, pushed = [], []
    monkeypatch.setattr(panel, "navigate_to_reference",
                        lambda b, c, v, translation=None: navigated.append((b, c, v)))
    panel.navigator_push.connect(lambda b, c, v: pushed.append((b, c, v)))

    panel._on_quick_verse_committed("12")
    assert panel.predictive_input.verse_input.text() == "12"
    assert navigated == [("Genesis", "1", "12")]
    assert pushed == [("Genesis", "1", "12")]


def test_commit_invalid_verse_does_nothing(monkeypatch, tmp_path):
    import core.bible_service as bible_service
    monkeypatch.setattr(bible_service, "get_verse_count", lambda v, b, c: 50)
    panel, _host = _browser_panel(monkeypatch, tmp_path)
    panel.predictive_input.book_input.set_value("Genesis")
    panel.predictive_input.chapter_input.set_value(1)

    navigated, pushed = [], []
    monkeypatch.setattr(panel, "navigate_to_reference",
                        lambda b, c, v, translation=None: navigated.append((b, c, v)))
    panel.navigator_push.connect(lambda b, c, v: pushed.append((b, c, v)))

    panel._on_quick_verse_committed("99")   # beyond the chapter
    panel._on_quick_verse_committed("0")    # not a verse
    panel._on_quick_verse_committed("abc")  # not even a number
    assert navigated == []
    assert pushed == []


def test_badge_shows_take_and_hides_after(monkeypatch, tmp_path):
    panel, _host = _browser_panel(monkeypatch, tmp_path)
    badge = panel._quick_badge
    assert badge.isHidden()
    panel._on_quick_verse_buffer("12")
    assert badge.isVisible()
    assert badge.text() == "12"
    # badge stays inside the panel, bottom-right
    assert badge.x() + badge.width() <= panel.width()
    assert badge.y() + badge.height() <= panel.height()
    panel._on_quick_verse_buffer("")
    assert badge.isHidden()


def test_navigator_push_hands_focus_to_the_verse_list(monkeypatch, tmp_path):
    """Pushing a scripture with Enter must hand keyboard focus back to the
    Bible panel.

    Otherwise the operator's next keystrokes land in the navigator's text
    input, where the recorder deliberately does not listen — so typing a
    verse number to push it does nothing, and the only way back is to
    click a row in the bible list. One Enter should be enough.
    """
    panel, _host = _browser_panel(monkeypatch, tmp_path)
    panel.predictive_input.setFocus()
    _qt().processEvents()

    pushed = []
    panel.navigator_push.connect(lambda b, c, v: pushed.append((b, c, v)))
    panel._on_navigator_push("Psalms", 23, 1)
    _qt().processEvents()

    assert pushed == [("Psalms", "23", "1")], "the push itself must still fire"
    assert panel.verse_list.hasFocus(), (
        "focus stayed on %r; digit-capture would be dead"
        % type(_qt().focusWidget()).__name__)


def test_verse_number_typed_after_a_navigator_push_commits(monkeypatch,
                                                           tmp_path):
    """The whole point of the handoff, end to end: navigator Enter → push,
    then type a verse number and Enter, with no click in between."""
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent

    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "app.db"))
    db.init_db()
    import core.bible_service as bible_service
    monkeypatch.setattr(bible_service, "get_verse_count", lambda v, b, c: 50)
    from ui.panels.browser_panel import BrowserPanel
    panel = BrowserPanel(translations=["KJV"])
    _host(panel)

    committed = []
    panel._quick_verse.committed.connect(committed.append)

    panel.predictive_input.setFocus()
    _qt().processEvents()
    panel._on_navigator_push("Psalms", 23, 1)
    _qt().processEvents()

    focus = _qt().focusWidget()
    assert focus is panel.verse_list
    for ch in "1919":
        QApplication.sendEvent(focus, QKeyEvent(
            QEvent.Type.KeyPress, int(ch), Qt.KeyboardModifier.NoModifier, ch))
    QApplication.sendEvent(focus, QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Return,
        Qt.KeyboardModifier.NoModifier, "\r"))
    _qt().processEvents()

    assert committed == ["1919"], (
        "typing a verse after a navigator push did not commit")


class TestFocusEnforcement:
    """If the work-area ring is lit (scripture is displayed) and the caret
    is not in a text box, the caret belongs on the verse list.

    Scoped to the work area on purpose: the ring is lit whenever scripture
    is displayed, including while the operator is in the schedule, so an
    unscoped version would make the schedule unusable.
    """

    def _tab(self, scripture_on_live=True):
        """A tab over REAL widgets, inside ONE window.

        The enforcement walks parentWidget() chains, so the work area and
        the Bible panel must be genuine QWidgets — a stub would make the
        ancestor test raise rather than match. Everything lives in a single
        shown window: a second top-level takes the activation away from
        the first, and focusWidget() then reports the wrong window.
        """
        from ui.tabs.presentation_tab import PresentationTab

        class _Browser(QWidget):
            def __init__(self):
                super().__init__()
                self.verse_list = _Focusable()
                self.verse_list.setParent(self)
                self.forced = 0

            def focus_verse_list(self):
                self.forced += 1
                return True

        host = QWidget()
        lay = QVBoxLayout(host)
        tab = PresentationTab.__new__(PresentationTab)
        live = ({"book": "John", "chapter": 3, "verse_num": 16,
                 "version": "KJV", "text": "t"}
                if scripture_on_live else
                {"item_type": "slide", "slides": [], "slide_index": 0})
        tab._display = type("D", (), {"live_data": live})()
        tab._work_wrap = QWidget()
        tab.browser_panel = _Browser()
        tab.browser_panel.setParent(tab._work_wrap)

        # A sibling of the work area: standing in for the schedule, i.e.
        # focus that is in this window but NOT in the scripture work area.
        outside = QPushButton("schedule row")

        lay.addWidget(outside)
        lay.addWidget(tab._work_wrap)
        host.resize(400, 300)
        host.show()
        _qt().setActiveWindow(host)
        _qt().processEvents()
        # Retain: dropping the last Python ref to a shown window destroys
        # its children too, and the next test then touches dead C++ objects.
        _HOSTS.append(host)
        tab.outside = outside
        return tab

    def _focus(self, tab, widget):
        app = _qt()
        if widget.parentWidget() is None:
            widget.setParent(tab._work_wrap)
        widget.show()
        _qt().processEvents()
        widget.setFocus()
        _qt().processEvents()
        assert app.focusWidget() is widget, "test setup: focus not taken"
        return widget

    def test_caret_drifted_inside_the_work_area_is_corrected(self):
        tab = self._tab()
        self._focus(tab, _Focusable())
        tab._enforce_verse_typing_focus()
        assert tab.browser_panel.forced == 1, (
            "caret left on a non-input work-area widget with the ring lit")

    def test_text_boxes_are_never_taken_over(self):
        tab = self._tab()
        self._focus(tab, QLineEdit())
        tab._enforce_verse_typing_focus()
        assert tab.browser_panel.forced == 0, "stole the caret from a text box"

    def test_the_schedule_is_left_alone(self):
        tab = self._tab()
        self._focus(tab, tab.outside)
        tab._enforce_verse_typing_focus()
        assert tab.browser_panel.forced == 0, (
            "yanked the caret out of the schedule")

    def test_a_deck_on_live_stands_the_correction_down(self):
        """A slide deck on live means the operator is working slides."""
        tab = self._tab(scripture_on_live=False)
        self._focus(tab, _Focusable())
        tab._enforce_verse_typing_focus()
        assert tab.browser_panel.forced == 0

    def test_already_inside_the_bible_panel_is_left_alone(self):
        """Idempotent: enforcement must not bounce the caret around."""
        tab = self._tab()
        self._focus(tab, tab.browser_panel.verse_list)
        tab._enforce_verse_typing_focus()
        assert tab.browser_panel.forced == 0
