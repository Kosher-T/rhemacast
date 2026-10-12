"""Tier selections must survive ribbon formatting.

The reported bug: highlight text, click the outline-size arrow once (works),
click again (nothing) — the highlight died after the first click, so every
further spin click hit an empty caret. Root cause was two tier-collapses
firing on *format* changes: _on_content_edited cleared unconditionally on the
ribbon signal, and _on_editor_text cleared on textChanged, which Qt also
emits for pure format merges. Ribbon formats now mark _in_ribbon_merge and
only real text changes (contentsChange with chars removed/added) collapse.

Needs offscreen Qt (WebEngine pre-import first — same ordering rule as the
other designer tests, else later UI imports break in-process).
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


def _designer(tmp_path, raw="# T\n\n\n*1\nFirst slide words\n"):
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


def _ladder_to(w, tier: int):
    """Drive the Ctrl+A ladder directly (not via key events): after the
    theme-awareness file crashes WebEngine teardown in-process, real key
    delivery flakes for every later file. The key-event path itself is
    covered by test_lite_designer_select.py; what matters here is the
    tier/format interaction."""
    for _ in range(6):
        if w._sel_tier == tier:
            break
        w._advance_tier()
    assert w._sel_tier == tier, f"ladder stuck at {w._sel_tier}, want {tier}"


def _outline_width(w, pos=0):
    from ui.widgets.lite_designer.format_ribbon import _parse_outline_value
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    cursor = w._edit.textCursor()
    cursor.setPosition(pos)
    fmt = cursor.charFormat()
    if not fmt.hasProperty(OUTLINE_PROP):
        return None
    return _parse_outline_value(fmt.property(OUTLINE_PROP))[1]


def _selected(w):
    cursor = w._edit.textCursor()
    assert cursor.hasSelection(), "editor selection lost"
    return cursor.selectionStart(), cursor.selectionEnd()


def test_outline_size_repeated_clicks_keep_tier_and_selection(tmp_path):
    """The reported bug: spin the outline size repeatedly on one highlight."""
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    start, end = _selected(w)
    r = w._ribbon
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(2)
    assert _selected(w) == (start, end)
    assert _outline_width(w) == 2
    assert w._sel_tier == 1
    r._outline_size.setValue(3)
    assert _selected(w) == (start, end)
    assert _outline_width(w) == 3
    assert w._sel_tier == 1
    r._outline_size.setValue(4)
    assert _selected(w) == (start, end)
    assert _outline_width(w) == 4
    assert w._sel_tier == 1


def test_bold_then_italic_chain_under_tier(tmp_path):
    """Bold-then-Italic on one highlight must both land (tiers exist so
    multi-format chains keep working)."""
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    start, end = _selected(w)
    r = w._ribbon
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    bold_before = cursor.charFormat().fontWeight() >= 600
    italic_before = cursor.charFormat().fontItalic()
    r._toggle_bold()
    r._toggle_italic()
    assert _selected(w) == (start, end)
    assert w._sel_tier == 1
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    # each toggle lands its own axis on the same highlight (the slides theme
    # is bold by default, so Bold writes explicit-Normal: assert the property
    # arrived, not an absolute weight).
    from PyQt6.QtGui import QTextFormat
    assert cursor.charFormat().hasProperty(QTextFormat.Property.FontWeight)
    assert cursor.charFormat().fontItalic() != italic_before


def test_block_format_preserves_tier(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    start, end = _selected(w)
    w._ribbon._on_align("center")
    assert _selected(w) == (start, end)
    assert w._sel_tier == 1


def test_outline_off_preserves_tier_for_next_pick(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    start, end = _selected(w)
    r = w._ribbon
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(5)
    assert _outline_width(w) == 5
    r._btn_outline.setChecked(False)
    r._on_outline_toggled()
    assert _selected(w) == (start, end)
    assert w._sel_tier == 1


def _scope_selected(w, indices):
    """Every scoped slide shows a selection: the editor for the active
    slide, the card display box everywhere else."""
    for i in indices:
        if i == w._active:
            cursor = w._edit.textCursor()
        else:
            cursor = w._cards[i]._display_box.textCursor()
        if not cursor.hasSelection():
            return False
    return True


def _doc_outline_width(w, index, pos=0):
    from ui.widgets.lite_designer.format_ribbon import _parse_outline_value
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    from PyQt6.QtGui import QTextCursor
    doc = w._doc_for(index)
    cursor = QTextCursor(doc)
    cursor.setPosition(pos)
    fmt = cursor.charFormat()
    if not fmt.hasProperty(OUTLINE_PROP):
        return None
    return _parse_outline_value(fmt.property(OUTLINE_PROP))[1]


def test_tier4_scope_survives_repeated_size_clicks(tmp_path):
    """Tier 3/4 reported bug: the first style click collapsed the multi-card
    highlight (card documents were rebuilt, dropping the scope painting)."""
    w = _designer(tmp_path, "# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    _ladder_to(w, 4)
    indices = w._scope_indices()
    assert len(indices) == 2, indices
    assert _scope_selected(w, indices)
    r = w._ribbon
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(2)
    assert w._sel_tier == 4
    assert _scope_selected(w, indices)
    assert all(_doc_outline_width(w, i) == 2 for i in indices)
    r._outline_size.setValue(3)
    assert w._sel_tier == 4
    assert _scope_selected(w, indices)
    assert all(_doc_outline_width(w, i) == 3 for i in indices)


def test_tier3_bold_marks_every_scoped_slide(tmp_path):
    w = _designer(tmp_path, "# T\n\n\n*Same\nSlide one words\n\n\nSlide two words\n")
    _ladder_to(w, 3)
    indices = w._scope_indices()
    assert len(indices) > 1, indices
    assert _scope_selected(w, indices)
    w._ribbon._toggle_bold()
    assert w._sel_tier == 3
    assert _scope_selected(w, indices)
    from PyQt6.QtGui import QTextCursor, QTextFormat
    for i in indices:
        cursor = QTextCursor(w._doc_for(i))
        cursor.setPosition(0)
        assert cursor.charFormat().hasProperty(QTextFormat.Property.FontWeight)


def test_tier4_outline_off_keeps_scope(tmp_path):
    w = _designer(tmp_path, "# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    _ladder_to(w, 4)
    indices = w._scope_indices()
    r = w._ribbon
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(5)
    assert all(_doc_outline_width(w, i) == 5 for i in indices)
    r._btn_outline.setChecked(False)
    r._on_outline_toggled()
    assert w._sel_tier == 4
    assert _scope_selected(w, indices)


def test_clicking_unfocused_card_places_caret_at_click(tmp_path):
    """Clicking a card's display box hands focus to the live editor AND the
    click position: before, the editor kept its stale cursor (usually 0) so
    the caret appeared at the start instead of under the cursor."""
    from PyQt6.QtGui import QMouseEvent, QTextCursor
    from PyQt6.QtCore import QEvent, QPointF, Qt
    w = _designer(tmp_path, "# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    w._activate(1)
    _qt().processEvents()
    box = w._cards[0]._display_box
    assert box.isVisible(), "inactive card must show its copy box"
    # aim mid-text: cursorRect of a mid-text caret, as a real click would land
    probe = box.textCursor()
    probe.setPosition(5)
    target = box.cursorRect(probe).center()
    ev = QMouseEvent(QEvent.Type.MouseButtonPress, QPointF(target),
                     Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
                     Qt.KeyboardModifier.NoModifier)
    box.mousePressEvent(ev)
    _qt().processEvents()
    assert w._active == 0
    # the live editor carries the click position (clamped to its own doc)
    want = box.textCursor().position()
    got = w._edit.textCursor().position()
    assert got == min(want, w._edit.document().characterCount() - 1) == 5, (got, want)
    assert w._edit.hasFocus()


def test_preview_white_toggle_sends_page_only_override(tmp_path):
    """The White button next to Preview flips a page-level canvas override
    (payloads and OBS output never see it)."""
    w = _designer(tmp_path)
    btn = w._preview_white_btn
    assert btn.text() == "White" and btn.isCheckable()
    sent = []
    w._preview._run_js = lambda js, cb=None: sent.append(js)
    btn.setChecked(True)
    assert w._preview._screen_white is True
    assert "setProperty" in sent[-1] and "#ffffff" in sent[-1]
    assert "important" in sent[-1]
    # both root and body: the stylesheet paints body black, which would
    # otherwise cover a root-only override everywhere but a strip
    assert "documentElement" in sent[-1] and "document.body" in sent[-1]
    btn.setChecked(False)
    assert w._preview._screen_white is False
    assert "removeProperty" in sent[-1]


def test_typing_collapses_tier(tmp_path):
    """Real text changes still collapse: typing replaces the highlight."""
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    w._edit.insertPlainText("x")
    assert w._sel_tier == 0
    assert not w._edit.textCursor().hasSelection()


def test_exact_length_typing_collapses_tier(tmp_path):
    """Typing exactly as many chars as selected still counts as typing.

    This is the discriminator a naive removed==added check gets wrong:
    mergeCharFormat also reports equal counts, so only the ribbon-origin
    flag may suppress the collapse.
    """
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(2, QTextCursor.MoveMode.KeepAnchor)
    w._edit.setTextCursor(cursor)
    w._edit.insertPlainText("ab")  # 2 out, 2 in — still typing, not format
    assert w._sel_tier == 0


def test_contents_change_ignores_ribbon_flag_directly(tmp_path):
    """Unit pin: the discriminator itself."""
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    w._ribbon._in_ribbon_merge = True
    try:
        w._on_contents_change(0, 4, 4)
        assert w._sel_tier == 1
    finally:
        w._ribbon._in_ribbon_merge = False
    w._on_contents_change(0, 4, 4)
    assert w._sel_tier == 0


def test_format_after_doc_swap_stays_wired(tmp_path):
    """contentsChange follows per-slide documents: switching slides must not
    strand the wiring on the old doc."""
    w = _designer(tmp_path, "# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    w._activate(1)
    _qt().processEvents()
    _ladder_to(w, 1)
    r = w._ribbon
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(2)
    assert _outline_width(w) == 2
    assert w._sel_tier == 1
    r._outline_size.setValue(3)
    assert _outline_width(w) == 3
    assert w._sel_tier == 1
