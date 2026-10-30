"""Navigator (Book | Chapter | Verse): one lane for chapter+verse, centred
digits, and the numbering tandem.

Contract under test:
  * chapter and verse are exactly the same size, and a growing number never
    reflows either of them
  * chapter and verse centre their digits (book keeps its left-aligned
    autofill)
  * editing the chapter resets the verse to 1 on the edit itself — no Space
    or Right needed — and editing the book resets chapter+verse the same way
  * one edit produces ONE navigation, carrying the already-reset numbers
  * restoring a reference programmatically (highlight, reset) never rewrites
    its own numbers
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

QCoreApplication.setAttribute(
    Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)

import pytest

import ui.widgets.predictive_input as pi


_app = None
_NAVS = []


def _qt():
    # Module-global handle: if the last Python reference to the QApplication
    # dies, PyQt tears down the C++ app and every later widget aborts.
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


@pytest.fixture
def navigator(monkeypatch):
    """A shown navigator with DB-independent chapter/verse maxima."""
    monkeypatch.setattr(pi, "get_chapter_count", lambda v, b: 150)
    monkeypatch.setattr(pi, "get_verse_count", lambda v, b, c: 176)
    app = _qt()
    nav = pi.PredictiveScriptureInput()
    nav.resize(207, 36)
    nav.show()
    app.processEvents()
    app.processEvents()
    _NAVS.append(nav)
    yield nav
    nav.close()
    nav.deleteLater()
    app.processEvents()


def _record(nav):
    seen = []
    nav.navigate_requested.connect(lambda b, c, v: seen.append((b, c, v)))
    return seen


# ── 1. one size for chapter and verse ──────────────────────────────────────

def test_chapter_and_verse_are_the_same_size(navigator):
    nav = navigator
    assert nav.chapter_input.size() == nav.verse_input.size()
    assert nav.chapter_input.width() >= 48
    assert nav.chapter_input.height() == nav.verse_input.height()


def test_a_growing_number_never_reflows_the_pair(navigator):
    """The lane is fitted to 3 digits, not to whatever is on screen."""
    nav = navigator
    nav.set_values("Psalms", 1, 1)
    before = (nav.chapter_input.width(), nav.verse_input.width())
    nav.set_values("Psalms", 176, 119)
    _qt().processEvents()
    assert (nav.chapter_input.width(), nav.verse_input.width()) == before
    assert before[0] == before[1]


def test_a_larger_saved_font_refits_both_together(navigator):
    nav = navigator
    for field in (nav.chapter_input, nav.verse_input):
        field.setStyleSheet("QLineEdit { font-size: 24px; font-weight: 600; }")
        field.ensurePolished()
    nav._fit_numeric_fields()
    assert nav.chapter_input.width() == nav.verse_input.width()
    assert nav.chapter_input.width() > 48, "three digits must still fit"


def test_extra_width_never_lands_in_the_colon(navigator):
    nav = navigator
    colon = nav._separator.width()
    nav.resize(320, 36)
    _qt().processEvents()
    assert nav._separator.width() == colon
    assert nav.chapter_input.width() == nav.verse_input.width()


# ── 2. centred digits ──────────────────────────────────────────────────────

def test_digits_are_centred_and_the_book_is_not(navigator):
    nav = navigator
    for field in (nav.chapter_input, nav.verse_input):
        assert field.alignment() & Qt.AlignmentFlag.AlignHCenter
    assert not (nav.book_input.alignment() & Qt.AlignmentFlag.AlignHCenter)


# ── 3. the numbering tandem ────────────────────────────────────────────────

def test_editing_the_chapter_resets_the_verse_immediately(navigator):
    """No Space, no Right: the verse is 1 the moment the chapter changes."""
    nav = navigator
    nav.set_values("Genesis", 3, 16)
    seen = _record(nav)

    nav.chapter_input.setFocus()
    _qt().processEvents()
    nav.chapter_input.selectAll()
    QTest.keyClicks(nav.chapter_input, "2")
    _qt().processEvents()

    assert nav.chapter_input.text() == "2"
    assert nav.verse_input.text() == "1", "verse reset on the edit itself"
    assert nav.chapter_input.hasFocus(), "the reset must not steal focus"
    assert seen == [("Genesis", 2, 1)], "one navigation, already reset"


def test_editing_the_book_resets_chapter_and_verse_immediately(navigator):
    nav = navigator
    nav.set_values("Genesis", 3, 16)
    seen = _record(nav)

    nav.book_input._on_focus_arrived()      # what a click does
    _qt().processEvents()
    QTest.keyClicks(nav.book_input, "j")
    _qt().processEvents()

    assert nav.book_input.text().startswith("J")
    assert nav.chapter_input.text() == "1"
    assert nav.verse_input.text() == "1"
    assert seen == [(nav.book_input.text(), 1, 1)]


def test_the_verse_reset_happens_on_every_chapter_edit(navigator):
    """Each keystroke is an edit, so the verse keeps falling back to 1."""
    nav = navigator
    nav.set_values("Genesis", 1, 16)
    nav.chapter_input.setFocus()
    _qt().processEvents()
    nav.chapter_input.selectAll()
    QTest.keyClicks(nav.chapter_input, "1")
    _qt().processEvents()
    assert nav.verse_input.text() == "1"
    nav.verse_input.set_value(9)             # operator had moved on
    QTest.keyClicks(nav.chapter_input, "2")  # chapter becomes 12
    _qt().processEvents()
    assert nav.chapter_input.text() == "12"
    assert nav.verse_input.text() == "1"


def test_space_still_advances_to_the_already_reset_verse(navigator):
    nav = navigator
    nav.set_values("John", 3, 16)
    nav.book_input._on_focus_arrived()
    _qt().processEvents()
    QTest.keyClick(nav.book_input, Qt.Key.Key_Space)
    _qt().processEvents()
    assert (nav.chapter_input.text(), nav.verse_input.text()) == ("1", "1")
    assert nav.chapter_input.hasFocus()

    QTest.keyClick(nav.chapter_input, Qt.Key.Key_Space)
    _qt().processEvents()
    assert nav.verse_input.text() == "1"
    assert nav.verse_input.hasFocus()


# ── 4. programmatic writes are not edits ───────────────────────────────────

def test_restoring_a_reference_keeps_its_numbers(navigator):
    nav = navigator
    nav.set_values("John", 3, 16)
    assert (nav.book_input.text(),
            nav.chapter_input.text(),
            nav.verse_input.text()) == ("John", "3", "16")


def test_reset_leaves_the_navigator_empty(navigator):
    nav = navigator
    nav.set_values("John", 3, 16)
    nav.reset()
    _qt().processEvents()
    assert (nav.book_input.text(),
            nav.chapter_input.text(),
            nav.verse_input.text()) == ("", "", "")


def test_a_programmatic_verse_keeps_its_value(navigator):
    """The quick-verse commit writes the verse directly; nothing resets it."""
    nav = navigator
    nav.set_values("Genesis", 1, 1)
    nav.verse_input.set_value(12)
    _qt().processEvents()
    assert nav.verse_input.text() == "12"
    assert nav.chapter_input.text() == "1"
