"""Ribbon ↔ designer ↔ theme wiring, end to end.

The unit suites drive a bare FormatRibbon against a bare QTextEdit, so a
whole class of real bugs — buttons ignoring the theme, toggles firing
inverted, deck format never reaching the ribbon — shipped unnoticed.
Here the FULL stack runs: a real LiteDesigner, the on-disk slides theme
(bold + outlined), the live editor, and the ribbon bound to it.

Needs offscreen Qt (WebEngine pre-import first — same ordering rule as
the other designer tests).
"""

import os

# Forced (not setdefault): the shell may export QT_QPA_PLATFORM=wayland,
# under which headless windows never activate and real focus is untestable.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QTextCursor

import pytest

import core.database as db

_OPEN = []


@pytest.fixture(autouse=True)
def _close():
    yield
    while _OPEN:
        w = _OPEN.pop()
        try:
            w.close()
            w.deleteLater()
        except RuntimeError:
            pass
    _qt().processEvents()


_app = None


def _qt():
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _designer(tmp_path, raw="# T\n\n\n*1\nPlain words here\n"):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    deck = create_deck(raw)
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    w._edit.setFocus()
    _qt().processEvents()
    _qt().processEvents()
    _OPEN.append(w)
    return w


def test_launch_shows_effective_theme_state(tmp_path):
    """On launch, plain text under the slides theme (bold + 4px outline)
    must light B and Outline — the buttons show what display renders,
    not the run's empty private state."""
    w = _designer(tmp_path)
    r = w._ribbon
    assert r._edit is w._edit
    assert r._btn_bold.isChecked(), "theme-bold text must light B"
    assert r._btn_outline.isChecked(), "theme-outlined text must light O"
    assert "#ffffff" in r._color_chip.styleSheet()
    assert r._size_combo.currentText() == "62"
    assert r._align_btns["center"].isChecked()
    assert r._btn_upper.isChecked()


def test_bold_click_on_theme_bold_writes_explicit_off(tmp_path):
    """The reported inversion: first B click must visibly un-bold (an
    explicit bold=false run), not a redundant bold=true no-op."""
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    w = _designer(tmp_path)
    r = w._ribbon
    assert r._btn_bold.isChecked()
    w._edit.selectAll()  # bare caret would only retune typing format
    r._btn_bold.click()
    assert not r._btn_bold.isChecked()
    txt = doc_to_txt(w._edit.document())
    assert "bold=false" in txt, txt
    w._store_active()
    assert "bold=false" in w._slides[0]["text"]
    # ...and back on again.
    r._btn_bold.click()
    assert r._btn_bold.isChecked()
    assert "bold=true" in doc_to_txt(w._edit.document())


def test_outline_click_on_theme_outline_writes_off_sentinel(tmp_path):
    """Same for outline: the lit O switches the theme outline off for
    the selection via the OFF sentinel (inheritable again on re-enable)."""
    from ui.widgets.lite_designer.rich_txt import OUTLINE_OFF, doc_to_txt
    w = _designer(tmp_path)
    r = w._ribbon
    assert r._btn_outline.isChecked()
    w._edit.selectAll()  # bare caret would only retune typing format
    r._btn_outline.setChecked(False)  # post-click state, as a real click
    r._on_outline_toggled()
    assert not r._btn_outline.isChecked()
    txt = doc_to_txt(w._edit.document())
    assert "outline=none" in txt, txt
    assert OUTLINE_OFF in txt or "outline=none" in txt


def test_top_script_format_reaches_the_ribbon(tmp_path):
    """Deck top-script is the middle of the chain: bold=false there beats
    the theme's bold at the ribbon with no run props involved."""
    w = _designer(tmp_path, "bold=false\n# T\n\n\n*1\nPlain words here\n")
    r = w._ribbon
    assert not r._btn_bold.isChecked()
    assert r._deck_format.get("bold") is False
    # ...while outline still rides the theme (deck says nothing about it).
    assert r._btn_outline.isChecked()


def test_clicking_between_slides_refreshes_state(tmp_path):
    """Activating another card re-points the live editor and refreshes:
    an explicitly-unbolded run on slide 2 reads OFF while slide 1 (plain
    theme-bold) reads ON."""
    w = _designer(
        tmp_path,
        "# T\n\n\n*1\nFirst slide words\n\n\n*2\n"
        "[Second slide words (bold=false)]\n")
    r = w._ribbon
    w._activate(0)
    _qt().processEvents()
    assert r._btn_bold.isChecked()
    w._activate(1)
    _qt().processEvents()
    assert not r._btn_bold.isChecked()
