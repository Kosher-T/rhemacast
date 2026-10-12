"""Shared editing gestures (ui/widgets/text_nav.py): pure kernels moved
intact from slide cards, plus QLineEdit behavior via real events."""

import os

# Forced (not setdefault): the shell may export QT_QPA_PLATFORM=wayland,
# under which headless windows never activate and focus is untestable.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QLineEdit

# Search boxes built by the gesture tests at the bottom of this file.
# Retained for the module's lifetime: dropping the last Python ref to a
# shown widget destroys it, and the next test touches dead C++.
_KEEP = []
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtGui import QTextCursor
import pytest

from ui.widgets.text_nav import (
    install_line_edit_nav, word_end_right_stop, word_span_at,
    _LineEditNav,
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def _field(qapp, text=""):
    edit = QLineEdit()
    edit.setText(text)
    install_line_edit_nav(edit)
    edit.resize(300, 30)
    edit.show()
    qapp.processEvents()
    return edit


def test_kernels_moved_intact(qapp):
    assert word_end_right_stop("hello, world", 5) == 6
    assert word_end_right_stop("hello, world", 0) is None
    assert word_span_at("don't stop", 1) == (0, 5)
    assert word_span_at("hello, world", 5) is None


def test_install_is_idempotent(qapp):
    edit = QLineEdit()
    first = install_line_edit_nav(edit)
    assert install_line_edit_nav(edit) is first
    assert len(edit.findChildren(_LineEditNav)) == 1


def test_lineedit_ctrl_right_punct_stop(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(5)
    QTest.keyClick(edit, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.cursorPosition() == 6


def test_lineedit_ctrl_right_falls_through(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(0)
    QTest.keyClick(edit, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.cursorPosition() == 5


def test_lineedit_ctrl_left_explicit(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(12)
    QTest.keyClick(edit, Qt.Key.Key_Left,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.cursorPosition() == 7
    QTest.keyClick(edit, Qt.Key.Key_Left,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.cursorPosition() == 5


def test_lineedit_ctrl_right_space_explicit(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(6)
    QTest.keyClick(edit, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.cursorPosition() == 7


def test_lineedit_shift_ctrl_variants_qt(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(5)
    QTest.keyClick(edit, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert edit.selectedText() == ","
    edit.setCursorPosition(12)
    QTest.keyClick(edit, Qt.Key.Key_Left,
                   Qt.KeyboardModifier.ControlModifier
                   | Qt.KeyboardModifier.ShiftModifier)
    assert edit.selectedText() == "world"


def test_lineedit_ctrl_delete(qapp):
    edit = _field(qapp, "hello, world")
    edit.setCursorPosition(5)
    QTest.keyClick(edit, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.ControlModifier)
    assert edit.text() == "hello world"


def test_lineedit_double_click_contraction(qapp):
    edit = _field(qapp, "don't stop")
    edit.setCursorPosition(1)
    center = edit.cursorRect().center()
    QTest.mouseDClick(edit, Qt.MouseButton.LeftButton, pos=center)
    qapp.processEvents()
    assert edit.selectedText() == "don't"


def test_lineedit_triple_click_selects_all(qapp):
    edit = _field(qapp, "some query words")
    center = edit.cursorRect().center()
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseDClick(edit, Qt.MouseButton.LeftButton, pos=center)
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton, pos=center)
    qapp.processEvents()
    assert edit.selectedText() == "some query words"


def test_lineedit_delete_keeps_space(qapp):
    """Scoped out for search fields: plain Delete removes exactly the
    selection, no smart space-eating."""
    edit = _field(qapp, "hello world")
    edit.setSelection(0, 5)
    QTest.keyClick(edit, Qt.Key.Key_Delete)
    assert edit.text() == " world"


def test_lineedit_backspace_keeps_space(qapp):
    edit = _field(qapp, "hello world")
    edit.setSelection(6, 5)
    QTest.keyClick(edit, Qt.Key.Key_Backspace)
    assert edit.text() == "hello "


def test_lineedit_alt_delete_untouched(qapp):
    edit = _field(qapp, "hello world")
    edit.setCursorPosition(5)
    QTest.keyClick(edit, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.AltModifier)
    assert edit.text() == "hello world"
    assert edit.cursorPosition() == 5


def test_lineedit_focus_empty_selects_nothing(qapp):
    edit = _field(qapp, "")
    edit.setFocus()
    qapp.processEvents()
    assert edit.selectedText() == ""





def test_search_panels_use_plain_qlineedits(qapp, tmp_path):
    """Wiring: the FTS + fuzzy query inputs are plain QLineEdits.

    Pinned deliberately. They were briefly a QTextEdit subclass
    (SearchField) emulating a single-line field, and every selection /
    focus / caret problem the operator reported traced back to that
    emulation. The native widget is the contract; if something needs
    different behaviour, it belongs in a subclass of QLineEdit — not in
    a text edit pretending to be one.
    """
    from PyQt6.QtWidgets import QLineEdit
    import core.database as db
    from ui.panels.fts_search_panel import FtsSearchPanel
    from ui.panels.search_panel import SearchPanel
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    fts = FtsSearchPanel()
    fuzzy = SearchPanel()
    for panel in (fts, fuzzy):
        assert type(panel.query_input) is QLineEdit, type(panel.query_input)
        assert panel.query_input.isEnabled()
    fts.close()
    fuzzy.close()


def _send_override(widget, key, mods=Qt.KeyboardModifier.NoModifier):
    """Synchronous ShortcutOverride delivery; returns accepted flag."""
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtCore import QEvent
    ev = QKeyEvent(QEvent.Type.ShortcutOverride, key, mods)
    QApplication.instance().sendEvent(widget, ev)
    return ev.isAccepted()




def test_fuzzy_panel_input_focusable(qapp, tmp_path):
    """Smoke: fuzzy panel builds with an enabled, focusable query
    input (the input must never be disabled mid-search — that blurs
    focus and flapped focus-select in loops)."""
    import core.database as db
    from ui.panels.search_panel import SearchPanel
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    panel = SearchPanel()
    panel.show()
    qapp.processEvents()
    panel.query_input.setText("david")
    panel.query_input.setFocus()
    qapp.processEvents()
    assert panel.query_input.hasFocus()
    assert panel.query_input.isEnabled()
    panel.close()



def test_press_explicitly_focuses_lineedit(qapp):
    edit = _field(qapp, "ab")
    calls = []
    orig = edit.setFocus
    edit.setFocus = lambda *a, **k: (calls.append(True), orig(*a, **k))
    edit.clearFocus()
    qapp.processEvents()
    QTest.mousePress(edit, Qt.MouseButton.LeftButton,
                     pos=edit.rect().center())
    assert calls, "press must explicitly request focus"
    edit.close()



def test_no_qtextedit_search_field_exists_anymore():
    """The QTextEdit-based search box was reverted out; keep it out.

    A source-level guard, deliberately. Every symptom the operator
    reported about the search boxes — selection not clearing, highlights
    toggling, a click in the dark area selecting everything — came from
    emulating a single-line field on top of QTextEdit: suppressing wrap,
    hiding scrollbars, intercepting Enter, and hand-rolling select-all.
    Behavioural tests cannot express "don't put this back", because the
    class works well enough to pass them.
    """
    import inspect
    import ui.widgets.text_nav as tn
    assert not hasattr(tn, "SearchField"), (
        "SearchField is back — search boxes are plain QLineEdits")
    assert not hasattr(tn, "_FocusSelectAll"), (
        "the synthetic focus→select-all watcher is back")
    # The docstring deliberately NAMES the reverted class to explain why it
    # went, so a source scan for the word would flag the explanation. Check
    # code instead: no panel may reach for it.
    import ui.panels.fts_search_panel as fts_mod
    import ui.panels.search_panel as fuzzy_mod
    import ui.panels.deck_list_panel as deck_mod
    for mod in (fts_mod, fuzzy_mod, deck_mod):
        assert "SearchField" not in inspect.getsource(mod), (
            "%s reached for the reverted SearchField" % mod.__name__)


# ─── the three search-box gestures ─────────────────────────────────────────
#
# 1. double-click highlights a word
# 2. triple-click highlights all
# 3. focus arrival highlights all, and ONLY on focus arrival
#
# All three are wanted behaviours, so each is pinned individually — and
# #3 is pinned hardest, because "only on focus arrival" is the part that
# regressed before: when highlight-on-focus also fired from a click, the
# operator could not place the caret to fix a typo without the whole
# query snapping back to selected.

def _search_box(qapp, text):
    from ui.widgets.text_nav import install_line_edit_nav
    edit = QLineEdit()
    install_line_edit_nav(edit)
    edit.setText(text)
    edit.resize(300, 30)
    edit.show()
    qapp.processEvents()
    _KEEP.append(edit)
    return edit


def _nav(edit):
    from ui.widgets.text_nav import _LineEditNav
    return edit.findChild(_LineEditNav)


def _click(edit, x, gap=15):
    QTest.mouseClick(edit, Qt.MouseButton.LeftButton,
                     pos=QPoint(x, edit.rect().center().y()))
    app = QApplication.instance()
    app.processEvents()
    QTest.qWait(gap)


def _dbl(edit, x):
    QTest.mouseDClick(edit, Qt.MouseButton.LeftButton,
                      pos=QPoint(x, edit.rect().center().y()))
    QApplication.instance().processEvents()


def test_focus_arrival_highlights_all_and_only_then(qapp):
    text = "psalm 23 the lord is my shepherd"
    edit = _search_box(qapp, text)
    edit.clearFocus()
    qapp.processEvents()
    edit.setFocus()
    qapp.processEvents()
    assert edit.selectedText() == text, "focus arrival must highlight all"
    # ...and a click inside must NOT bring it back
    _click(edit, 30)
    assert edit.selectedText() == "", "a click must not re-highlight"
    _click(edit, edit.width() - 4)
    assert edit.selectedText() == "", (
        "a click in the empty area must not re-highlight")
    # refocusing highlights again
    edit.clearFocus()
    qapp.processEvents()
    edit.setFocus()
    qapp.processEvents()
    assert edit.selectedText() == text


def test_focus_on_an_empty_box_highlights_nothing(qapp):
    edit = _search_box(qapp, "")
    edit.clearFocus()
    qapp.processEvents()
    edit.setFocus()
    qapp.processEvents()
    assert edit.selectedText() == ""


def test_double_click_highlights_one_word(qapp):
    edit = _search_box(qapp, "psalm 23 the lord is my shepherd")
    edit.setFocus()
    qapp.processEvents()
    _dbl(edit, 30)
    word = edit.selectedText()
    assert word, "double-click selected nothing"
    assert " " not in word, f"expected one word, got {word!r}"
    assert word in edit.text()


def test_double_click_treats_a_contraction_as_one_word(qapp):
    """What the shared `word_span_at` kernel buys over the native widget.

    Qt's own double-click stops at the apostrophe: double-clicking "don't"
    selects "don", leaving the operator to drag for the rest. The kernel
    knows contractions are one word.
    """
    from ui.widgets.text_nav import word_span_at
    text = "don't stop believing now"
    assert word_span_at(text, 2) == (0, 5), "kernel must span the contraction"

    edit = _search_box(qapp, text)
    edit.setFocus()
    qapp.processEvents()
    _dbl(edit, 12)          # inside "don't"
    assert edit.selectedText() == "don't", (
        f"selected {edit.selectedText()!r}; Qt alone would pick 'don'")


def test_triple_click_highlights_all(qapp):
    text = "psalm 23 the lord is my shepherd"
    edit = _search_box(qapp, text)
    edit.setFocus()
    qapp.processEvents()
    _nav(edit)._count = 0
    for _ in range(3):
        _click(edit, 30)
    assert edit.selectedText() == text, "triple-click must highlight all"


def test_triple_click_highlights_all_from_the_empty_area(qapp):
    """Clicking past the end of the words is still three aimed clicks."""
    text = "psalm 23 the lord is my shepherd"
    edit = _search_box(qapp, text)
    edit.setFocus()
    qapp.processEvents()
    _nav(edit)._count = 0
    for _ in range(3):
        _click(edit, edit.width() - 4)
    assert edit.selectedText() == text


def test_three_clicks_that_are_not_a_triple_click_do_not_highlight(qapp):
    """Spread out, or aimed at different spots: not a triple-click."""
    text = "psalm 23 the lord is my shepherd"
    for gap, spots in ((15, (30, 90, 30)), (600, (30, 30, 30))):
        edit = _search_box(qapp, text)
        edit.setFocus()
        qapp.processEvents()
        _nav(edit)._count = 0
        for x in spots:
            _click(edit, x, gap=gap)
        assert edit.selectedText() == "", (
            f"gap={gap} spots={spots} wrongly highlighted all")
