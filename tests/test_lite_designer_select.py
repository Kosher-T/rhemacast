"""Lite Designer deck-wide Ctrl+A: promote slide selection to the deck.

Needs offscreen Qt (WebEngine pre-import first — same ordering rule as the
serialize tests, else later UI imports break in-process).
"""

import os

# Forced (not setdefault): the shell may export QT_QPA_PLATFORM=wayland,
# under which headless windows never activate and real focus is untestable.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QTextCursor

import pytest

import core.database as db
from core.clipboard import write_text

_OPEN_DESIGNERS = []


@pytest.fixture(autouse=True)
def _hermetic_clipboard(monkeypatch):
    """Keep paste tests off the machine-global clipboard.

    `core.clipboard.read_text` prefers the SYSTEM clipboard when it
    disagrees with the last in-app write's baseline — and the system
    clipboard is shared by every test in the session, including this
    file's own. A test that wrote "First slide words" would then be read
    back by a later paste test here, which shatters into the wrong slides.

    It cannot be fixed by clearing: `wl-copy` writes from a daemon thread,
    so a pending publish from an earlier test can land at any point, and a
    clear of one clipboard does not cancel the other. Read from the Qt
    clipboard only — it is per-process and written synchronously, which is
    exactly the path the app takes on a machine with no clipboard tools.

    `_publish_system` is stubbed as well so this file stops seeding the
    real clipboard for the rest of the session.
    """
    import core.clipboard as cb
    monkeypatch.setattr(cb, "_tools_available", lambda: False)
    monkeypatch.setattr(cb, "_system_read", lambda: "")
    monkeypatch.setattr(cb, "_publish_system", lambda text: None)
    cb._baseline = None
    app = _qt()
    app.clipboard().clear()
    yield
    app.clipboard().clear()
    cb._baseline = None


_app = None


def _qt():
    # One QApplication per pytest process: a second instance corrupts
    # native state (WebEngine) and core-dumps the suite.
    global _app
    _app = QApplication.instance()
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _designer(tmp_path):
    _qt()
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    deck = create_deck("# T\n\n\n*1\nFirst slide words\n\n\n*2\nSecond slide words\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    w._edit.setFocus()
    _qt().processEvents()
    _OPEN_DESIGNERS.append(w)
    return w


def _select_all_in_editor(w):
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(w._edit.document().characterCount() - 1,
                       QTextCursor.MoveMode.KeepAnchor)
    w._edit.setTextCursor(cursor)


def test_opening_designer_preserves_slides(tmp_path):
    """Regression: first activation must never serialize the placeholder
    empty document over the loaded slide text (data loss on save)."""
    w = _designer(tmp_path)
    assert w._slides[0]["text"] == "First slide words"
    assert w._slides[1]["text"] == "Second slide words"
    assert w._edit.document().toPlainText() == "First slide words"
    w._activate(1)
    w._activate(0)
    assert w._slides[0]["text"] == "First slide words"
    assert w._slides[1]["text"] == "Second slide words"


def _ladder_to(w, tier: int):
    """Press Ctrl+A until the ladder reaches `tier` (text-only)."""
    for _ in range(6):
        if w._sel_tier == tier:
            break
        QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == tier, f"ladder stuck at {w._sel_tier}, want {tier}"


def _tier_selections(w):
    """(editor_selected, chip selections per card, box selections per card).

    The active card's display box is hidden (it hosts the live editor),
    so its display selection reads from the editor itself.
    """
    chips = [bool(c._chip.textCursor().hasSelection()) for c in w._cards]
    boxes = [bool(c._display_box.textCursor().hasSelection())
             for c in w._cards]
    editor_selected = w._edit.textCursor().hasSelection()
    boxes[w._active] = boxes[w._active] or editor_selected
    return (editor_selected, chips, boxes)


def test_ctrl_a_ladder_is_text_only_no_card_paint(tmp_path):
    w = _designer(tmp_path)
    paint_before = [c.styleSheet() for c in w._cards]
    # Tier 1: active display box only.
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 1
    selected, chips, _boxes = _tier_selections(w)
    assert selected and not any(chips)
    # Tier 2: display + section chip (chip "1" is non-empty).
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 2
    selected, chips, _boxes = _tier_selections(w)
    assert selected and chips == [True, False]
    # Tier 3: the active slide's run ([0] here) — card 1 untouched.
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 3
    assert w._scope_indices() == [0]
    _selected, chips, boxes = _tier_selections(w)
    assert chips == [True, False] and boxes == [True, False]
    # Tier 4: every textbox in the deck.
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 4
    _selected, chips, boxes = _tier_selections(w)
    assert chips == [True, True] and boxes == [True, True]
    # No card highlight at any tier: paint identical, no selected flag.
    assert [c.styleSheet() for c in w._cards] == paint_before
    assert all(c.property("deckselected") is None for c in w._cards)


def test_tier2_skipped_without_section(tmp_path):
    w = _run_designer(tmp_path, "# T\n\n\nplain slide\n")
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 1
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 3  # empty chip: tier 2 skipped
    assert w._scope_indices() == [0]


def test_chip_focus_selects_chip_first(tmp_path):
    """Ctrl+A while editing a section name selects the chip natively
    first; the next Ctrl+A climbs from the display box (tier 1)."""
    w = _designer(tmp_path)
    chip = w._cards[0]._chip
    chip.setFocus()
    _qt().processEvents()
    cursor = chip.textCursor()
    cursor.setPosition(0)
    chip.setTextCursor(cursor)
    QTest.keyClick(chip, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 0
    assert chip.textCursor().hasSelection()
    QTest.keyClick(chip, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 1
    assert w._edit.textCursor().hasSelection()


def test_partial_selection_first_ctrl_a_reaches_tier1(tmp_path):
    w = _designer(tmp_path)
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
    w._edit.setTextCursor(cursor)
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    assert w._sel_tier == 1
    assert w._display_fully_selected()


def test_tier_copy_scopes(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    QTest.keyClick(w._edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "First slide words"
    _ladder_to(w, 4)
    QTest.keyClick(w._edit, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    text = QApplication.clipboard().text()
    assert "First slide words" in text and "Second slide words" in text
    assert "# T" not in text  # body only: title never in any scope


def test_typing_esc_and_click_collapse_tier(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 3)
    QTest.keyClicks(w._edit, "X")  # plain typing collapses
    assert w._sel_tier == 0
    _ladder_to(w, 2)
    QTest.keyClick(w._edit, Qt.Key.Key_Escape)
    assert w._sel_tier == 0
    assert not any(c._chip.textCursor().hasSelection() for c in w._cards)
    _ladder_to(w, 3)
    QTest.mouseClick(w._cards[1]._display_box, Qt.MouseButton.LeftButton)
    _qt().processEvents()
    assert w._sel_tier == 0 and w._active == 1


def _snapshot_texts(w):
    w._store_active()
    return [s.get("text", "") for s in w._slides]


def test_tier1_typing_replaces_highlight(tmp_path):
    """Ctrl+A (tier 1) then typing must REPLACE the highlight.

    Regression: the tier was cleared before Qt inserted the character,
    which collapsed the cursor to the end of the selection — the new text
    appended after the old instead of replacing it.
    """
    w = _designer(tmp_path)
    w._activate(0)
    w._edit.setFocus()
    _qt().processEvents()
    assert w._slides[0]["text"].strip()

    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    _qt().processEvents()
    assert w._sel_tier == 1
    assert w._edit.textCursor().hasSelection()

    QTest.keyClicks(w._edit, "Z")
    _qt().processEvents()
    assert w._edit.toPlainText() == "Z", repr(w._edit.toPlainText())
    assert w._sel_tier == 0  # typing collapses the ladder


def test_tier1_partial_highlight_replaces_only_that_run(tmp_path):
    """A partial highlight is replaced; the rest of the line survives."""
    w = _designer(tmp_path)
    w._activate(0)
    w._edit.setFocus()
    _qt().processEvents()
    original = w._edit.toPlainText()
    assert "First" in original

    cursor = w._edit.textCursor()
    start = original.index("First")
    cursor.setPosition(start)
    cursor.setPosition(start + len("First"), QTextCursor.MoveMode.KeepAnchor)
    w._edit.setTextCursor(cursor)
    QTest.keyClicks(w._edit, "Q")
    _qt().processEvents()
    text = w._edit.toPlainText()
    assert "First" not in text
    assert "Q" in text
    assert len(text) == len(original) - len("First") + 1


def test_tier3_typing_collapses_to_focused_box(tmp_path):
    """At a deck-wide tier, typing lands in the focused display box and
    replaces ITS content — the cross-card highlight is visualization only
    and must not leave stale selections behind."""
    w = _designer(tmp_path)
    w._activate(0)
    w._edit.setFocus()
    _qt().processEvents()
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(w._edit, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    _qt().processEvents()
    assert w._sel_tier >= 3, w._sel_tier

    QTest.keyClicks(w._edit, "Z")
    _qt().processEvents()
    assert w._edit.toPlainText() == "Z", repr(w._edit.toPlainText())
    # No stale highlight left on the other card.
    other = w._cards[1]
    assert not other._display_box.textCursor().hasSelection()
    assert not other._chip.textCursor().hasSelection()


def test_tier3_bold_fans_out_run_and_chains(tmp_path):
    w = _three_slide_designer(tmp_path)  # *1 a / b / *2 c
    # Fan-out SCOPE is what's under test here, so pin the ribbon to no
    # theme baseline: with a bold theme, B reads as lit and toggling it
    # means "un-bold" (see test_lite_designer_ribbon_state). Clearing the
    # baseline keeps "toggle bold" meaning "apply bold", as below expects.
    w._ribbon.set_theme_defaults({})
    w._activate(0)
    _ladder_to(w, 3)
    assert w._scope_indices() == [0, 1]
    w._ribbon._toggle_bold()
    texts = _snapshot_texts(w)
    assert "bold=true" in texts[0] and "bold=true" in texts[1], texts
    assert "bold" not in texts[2], texts
    assert w._sel_tier == 3  # fan-out preserves the tier for chains
    w._ribbon._toggle_italic()
    texts = _snapshot_texts(w)
    assert "italics=true" in texts[0] and "italics=true" in texts[1]


def test_tier4_bold_applies_line_by_line(tmp_path):
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    deck = create_deck("# T\n\n\n*V\nline one here\nline two here\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    _OPEN_DESIGNERS.append(w)
    _qt().processEvents()
    w._ribbon.set_theme_defaults({})  # see tier3 test
    _ladder_to(w, 4)
    w._ribbon._toggle_bold()
    w._store_active()
    assert w._slides[0]["text"] == (
        "[line one here (bold=true)]\n[line two here (bold=true)]")


def test_loaded_false_flips_true(tmp_path):
    # Ribbon toggles must RECORD (not clear) so loaded runs flip correctly.
    from ui.widgets.lite_designer.rich_txt import txt_to_doc
    w = _designer(tmp_path)
    w._slides[0]["text"] = "[x (strike=false)] plain [y (underline=false)]"
    w._docs.pop(0, None)
    w._rebuild_cards()
    w._activate(0)
    cursor = w._edit.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(1, QTextCursor.MoveMode.KeepAnchor)
    w._edit.setTextCursor(cursor)
    w._ribbon._toggle_strike()
    assert "strike=true" in _snapshot_texts(w)[0]
    _select_all_in_editor(w)
    w._ribbon._toggle_underline()
    assert "underline=true" in _snapshot_texts(w)[0]


def test_tier4_delete_collapses_to_one_card(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 4)
    QTest.keyClick(w._edit, Qt.Key.Key_Delete)
    assert len(w._slides) == 1
    assert w._slides[0]["text"] == ""
    assert len(w._cards) == 1
    assert w._sel_tier == 0
    assert w._title == "T"  # title survives the collapse


def test_tier1_delete_removes_only_that_slide(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 1)
    QTest.keyClick(w._edit, Qt.Key.Key_Delete)
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("2", "Second slide words")]
    assert w._sel_tier == 0


def test_tier4_cut_copies_and_collapses(tmp_path):
    w = _designer(tmp_path)
    _ladder_to(w, 4)
    QTest.keyClick(w._edit, Qt.Key.Key_X, Qt.KeyboardModifier.ControlModifier)
    assert "First slide words" in QApplication.clipboard().text()
    assert len(w._slides) == 1 and w._slides[0]["text"] == ""


def test_tier4_paste_replaces_whole_deck(tmp_path):
    w = _designer(tmp_path)
    write_text(
        "size=30\n# Pasted\n\n\n*V\none\n\n\ntwo\n\n\n*C\nthree\n")
    _ladder_to(w, 4)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("V", "one"), ("V", "two"), ("C", "three")]
    assert [c._chip.toPlainText() for c in w._cards] == ["V", "", "C"]
    assert w._title == "T"  # deck title kept
    assert w._format.get("size_nominal") == 30  # pasted format merges in
    assert w._sel_tier == 0  # nothing stays armed


def test_tier2_paste_replaces_slide_and_section(tmp_path):
    w = _designer(tmp_path)
    write_text("*NewSec\nhello\n")
    _ladder_to(w, 2)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("NewSec", "hello"), ("2", "Second slide words")]
    assert [c._chip.toPlainText() for c in w._cards] == ["NewSec", "2"]


def test_tier3_paste_replaces_run(tmp_path):
    w = _three_slide_designer(tmp_path)  # *1 a / b / *2 c
    write_text("*N\nx\n\n\ny\n")
    w._activate(0)
    _ladder_to(w, 3)
    assert w._scope_indices() == [0, 1]
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("N", "x"), ("N", "y"), ("2", "c")]
    assert [c._chip.toPlainText() for c in w._cards] == ["N", "", "2"]


def test_tier1_single_word_paste_replaces_text_only(tmp_path):
    w = _designer(tmp_path)
    write_text("just some words")
    _ladder_to(w, 1)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert len(w._slides) == 2  # no newcomers: text replaced in place
    assert w._slides[0]["text"] == "just some words"
    assert w._slides[0]["section"] == "1"  # section kept
    assert w._sel_tier == 0


def test_plain_paste_trims_stray_boundary_blanks(tmp_path):
    """Real-world copies carry trailing newlines: they must insert as
    text, never spawn a phantom split that strands the user on an
    empty card."""
    w = _designer(tmp_path)
    write_text("tail\n\n")
    cur = w._edit.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert len(w._slides) == 2  # no phantom split, still on the same card
    assert w._edit.document().toPlainText() == "First slide wordstail"
    assert w._active == 0


def test_blank_only_paste_is_quiet_noop(tmp_path):
    w = _designer(tmp_path)
    before = w._edit.document().toPlainText()
    write_text("   \n  \n")
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert w._edit.document().toPlainText() == before
    assert len(w._slides) == 2


def test_structural_paste_with_trailing_blanks_shatters(tmp_path):
    w = _designer(tmp_path)
    write_text("one\n\n\ntwo\n\n")
    w._activate(0)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert [s.get("text") for s in w._slides] == [
        "one", "two", "Second slide words"]


def test_structural_paste_shatters_into_slides(tmp_path):
    w = _designer(tmp_path)
    write_text(
        "# Pasted Song\n\n\n*V\none\n\n\ntwo\n\n\n*C\nthree\n")
    w._activate(0)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert len(w._slides) == 4, [s.get("text") for s in w._slides]
    # "two" inherits the fragment's sticky V — chips still read V, "", C.
    assert [(s.get("section"), s.get("text")) for s in w._slides[:3]] == [
        ("V", "one"), ("V", "two"), ("C", "three")]
    assert [c._chip.toPlainText() for c in w._cards[:3]] == ["V", "", "C"]
    assert w._title == "T"  # deck title kept, fragment title ignored


def test_structural_paste_head_adopts_context(tmp_path):
    w = _designer(tmp_path)
    write_text("plain one\n\n\nplain two\n")
    w._activate(1)  # current slide owns section "2"
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    # Unmarked head inherits the replaced slide's run; tail stays member.
    assert [(s.get("section"), s.get("text")) for s in w._slides] == [
        ("1", "First slide words"),
        ("2", "plain one"), (None, "plain two")]
    assert [c._chip.toPlainText() for c in w._cards] == ["1", "2", ""]


def test_activation_renders_preview_instantly(tmp_path):
    w = _designer(tmp_path)
    payloads = []
    orig = w._preview.display_verse
    w._preview.display_verse = lambda p: (payloads.append(p), orig(p))
    w._activate(1)
    # Synchronous: no debounce wait between click and render.
    assert payloads and payloads[-1]["text"] == "Second slide words"
    n = len(payloads)
    w._activate(1)
    assert len(payloads) == n  # same-card reclick renders nothing


def test_plain_paste_falls_through(tmp_path):
    w = _designer(tmp_path)
    write_text("just some words")
    w._activate(0)
    before = len(w._slides)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert len(w._slides) == before
    assert "just some words" in w._edit.document().toPlainText()


def test_display_text_fixed_size_from_settings(tmp_path):
    """Display textboxes render one settings-driven size: size params
    never touch glyph metrics, while the model keeps them."""
    _qt()
    import core.database as db
    from core.database import set_setting
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    from ui.widgets.lite_designer.slide_cards import (
        display_text_px, DISPLAY_TEXT_PX_DEFAULT)
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    assert display_text_px() == DISPLAY_TEXT_PX_DEFAULT
    set_setting("slides.editor_font_size", "17")
    assert display_text_px() == 17
    set_setting("slides.editor_font_size", "abc")
    assert display_text_px() == DISPLAY_TEXT_PX_DEFAULT
    set_setting("slides.editor_font_size", "17")
    deck = create_deck("# T\n\n\n*1\nFirst [big (size=62)] words\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    _OPEN_DESIGNERS.append(w)
    _qt().processEvents()
    # Fixed settings size in the QTextEdit-selected rules (a bare-QWidget
    # ancestor rule would otherwise impose the popup's 11px).
    assert "font-size: 17px" in w._edit.styleSheet()
    assert "font-size: 17px" in w._cards[0]._display_box.styleSheet()
    # No fragment anywhere in pane docs carries a point size…
    from PyQt6.QtGui import QTextFormat
    docs = [w._edit.document()] + \
        [w._doc_for(i) for i in range(len(w._slides))]
    for doc in docs:
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    assert not frag.charFormat().hasProperty(
                        QTextFormat.Property.FontPointSize)
                it += 1
    # …but the model kept size=62 for preview/display.
    assert "size=62" in w._slides[0]["text"]


def test_rich_paste_keeps_text_drops_glyph_size(tmp_path, monkeypatch):
    """Rich clipboard: words land with formatting metadata intact, but
    smuggled point sizes fold into SIZE_PROP — pane glyphs stay fixed."""
    from PyQt6.QtCore import QMimeData
    from PyQt6.QtGui import QTextFormat
    import core.clipboard as _cb
    # Hermetic system leg (empty here) so the test never depends on the
    # machine's real clipboard content.
    monkeypatch.setattr(_cb, "_system_read", lambda: "")
    w = _designer(tmp_path)
    md = QMimeData()
    md.setText("rich words")
    md.setHtml('<span style="font-size:48px;font-weight:700">rich words</span>')
    QApplication.clipboard().setMimeData(md)
    cur = w._edit.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_V, Qt.KeyboardModifier.ControlModifier)
    assert "rich words" in w._edit.document().toPlainText()
    for doc in (w._edit.document(),):
        for i in range(doc.blockCount()):
            block = doc.findBlockByNumber(i)
            it = block.begin()
            steps = 0
            while not it.atEnd():
                steps += 1
                assert steps < 1000, f"fragment walk stuck at block {i}"
                frag = it.fragment()
                if frag.isValid() and frag.text().strip():
                    assert not frag.charFormat().hasProperty(
                        QTextFormat.Property.FontPointSize)
                it += 1


def _commit_chip(w, index, text):
    """Mirror a real chip commit: widget text + finished-edit handler."""
    w._cards[index].set_section(text)
    w._on_section_changed(index, text)


def test_move_preserves_values_through_save(tmp_path):
    from core.slide_service import create_deck, get_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    deck = create_deck("# T\n\n\n*1\na\n\n\nb\n\n\n*2\nc\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    # Member (b) to deck top: adopts ownership, keeps its value.
    w._move_slide(1, -1)
    assert w._slides[0]["section"] == "1"
    assert w._cards[0]._chip.toPlainText() == "1"
    w._on_save()
    fresh = get_deck(deck["id"])
    assert [(s.get("section"), s.get("text")) for s in fresh["slides"]] == [
        ("1", "b"), ("1", "a"), ("2", "c")]
    # Reload: flags traveled, so the split structure round-trips.
    w2 = LiteDesigner(deck_id=deck["id"])
    _OPEN_DESIGNERS.append(w2)
    assert [c._chip.toPlainText() for c in w2._cards] == ["1", "1", "2"]


def _three_slide_designer(tmp_path):
    _qt()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    deck = create_deck("# T\n\n\n*1\na\n\n\nb\n\n\n*2\nc\n")
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    _OPEN_DESIGNERS.append(w)
    return w


def test_identical_chip_text_splits_run(tmp_path):
    w = _three_slide_designer(tmp_path)
    assert [c._chip.toPlainText() for c in w._cards] == ["1", "", "2"]
    _commit_chip(w, 1, "1")  # member adopts same name -> new run anyway
    assert [r for _, r in w._section_runs()] == [[0], [1], [2]]
    assert [c._chip.toPlainText() for c in w._cards] == ["1", "1", "2"]


def test_clear_header_merges_up(tmp_path):
    w = _three_slide_designer(tmp_path)
    _commit_chip(w, 2, "")  # header "2" cleared -> joins the 1-run above
    assert [r for _, r in w._section_runs()] == [[0, 1, 2]]
    assert [c._chip.toPlainText() for c in w._cards] == ["1", "", ""]


def _run_designer(tmp_path, raw):
    _qt()
    from core.slide_service import create_deck
    from ui.widgets.lite_designer.lite_designer import LiteDesigner
    import core.database as db
    db.DB_PATH = str(tmp_path / "app.db")
    db.init_db()
    deck = create_deck(raw)
    w = LiteDesigner(deck_id=deck["id"])
    w.show()
    _OPEN_DESIGNERS.append(w)
    _qt().processEvents()
    return w


def test_move_swaps_members_in_place(tmp_path):
    """Fast path: runs identical -> values exchange with zero widget
    churn (same card objects, same editor document, focus preserved)."""
    w = _run_designer(tmp_path, "# T\n\n\n*1\na\n\n\nb\n\n\nc\n")
    assert [r for _, r in w._section_runs()] == [[0, 1, 2]]
    w._activate(1)
    _qt().processEvents()
    c1, c2 = w._cards[1], w._cards[2]
    doc_before = w._edit.document()
    runs_before = [r for _, r in w._section_runs()]
    w._edit.setFocus()
    w._move_slide(1, +1)
    _qt().processEvents()
    assert [s["text"] for s in w._slides] == ["a", "c", "b"]
    assert w._cards[1] is c1 and w._cards[2] is c2
    assert [r for _, r in w._section_runs()] == runs_before
    assert w._active == 2 and w._hosted == 2
    assert w._edit.document() is doc_before
    assert w._docs[2] is doc_before
    assert _qt().focusWidget() is w._edit


def test_move_across_runs_falls_back_correctly(tmp_path):
    """Slow path: runs changed -> same correct result via regroup."""
    w = _three_slide_designer(tmp_path)  # *1 a / b / *2 c
    w._activate(0)
    _qt().processEvents()
    w._move_slide(0, +1)
    _qt().processEvents()
    assert [s["text"] for s in w._slides] == ["b", "a", "c"]
    assert w._active == 1 and w._hosted == 1
    assert w._docs[1] is w._edit.document()
    runs = [r for _, r in w._section_runs()]
    assert sorted(i for run in runs for i in run) == [0, 1, 2]
    assert len(w._cards) == 3


def test_move_buttons_hide_at_deck_edges(tmp_path):
    w = _designer(tmp_path)  # 2 slides
    _qt().processEvents()
    assert not w._cards[0]._btn_up.isVisible()
    assert w._cards[0]._btn_down.isVisible()
    assert w._cards[1]._btn_up.isVisible()
    assert not w._cards[1]._btn_down.isVisible()
    # Adding a middle slide updates edges through the sync loop.
    w._add_slide(1)
    _qt().processEvents()
    assert len(w._cards) == 3
    assert not w._cards[0]._btn_up.isVisible()
    assert w._cards[1]._btn_up.isVisible()
    assert w._cards[1]._btn_down.isVisible()
    assert not w._cards[2]._btn_down.isVisible()


def test_section_gap_above_headed_runs(tmp_path):
    """A headed non-first run gets exactly one gap above it (between the
    run groups); nothing precedes the first card."""
    from PyQt6.QtWidgets import QWidget
    from ui.widgets.lite_designer.lite_designer import _SECTION_GAP
    w = _three_slide_designer(tmp_path)  # *1 a / b / *2 c -> [[0,1],[2]]
    _qt().processEvents()
    gaps = w.findChildren(QWidget, "SectionGap")
    assert len(gaps) == 1
    assert gaps[0].minimumHeight() == _SECTION_GAP
    lay = w._cards_layout
    gi = next(i for i in range(lay.count())
              if lay.itemAt(i).widget() is gaps[0])
    assert gi > 0  # never before the first card
    # Flat layout: the gap sits directly between the last card of run 0
    # (chip "" — member of the "1" run) and the first card of run 1.
    from ui.widgets.lite_designer.slide_cards import SlideCard
    prev_w = lay.itemAt(gi - 1).widget()
    next_w = lay.itemAt(gi + 1).widget()
    assert isinstance(prev_w, SlideCard) and isinstance(next_w, SlideCard)
    assert prev_w._chip.toPlainText() == ""
    assert next_w._chip.toPlainText() == "2"


def test_no_gap_for_single_run(tmp_path):
    from PyQt6.QtWidgets import QWidget
    w = _run_designer(tmp_path, "# T\n\n\n*1\na\n\n\nb\n")
    _qt().processEvents()
    assert w.findChildren(QWidget, "SectionGap") == []


def test_cards_scrollbar_reserved_and_shift_free(tmp_path):
    """Scrollbar lane is permanent (present even when everything fits)
    so rapid adds never shove card buttons sideways under the cursor."""
    w = _designer(tmp_path)
    _qt().processEvents()
    assert w._cards_scroll.verticalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOn
    assert w._cards_scroll.horizontalScrollBarPolicy() == \
        Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    bar = w._cards_scroll.verticalScrollBar()
    assert bar.isVisibleTo(w)
    btn = w._cards[0]._btn_add
    x_before = btn.mapToGlobal(btn.rect().center()).x()
    for _ in range(8):
        w._add_slide(len(w._slides))
    _qt().processEvents()
    btn_after = w._cards[0]._btn_add
    x_after = btn_after.mapToGlobal(btn_after.rect().center()).x()
    assert x_after == x_before


def test_cards_join_without_gaps(tmp_path):
    """Zero inter-card spacing; envelopes transparent and marginless;
    first/last cards carry the outer rounding."""
    from PyQt6.QtWidgets import QFrame
    w = _designer(tmp_path)  # 2 slides
    w._activate(1)
    _qt().processEvents()
    assert w._cards_layout.spacing() == 0
    c0, c1 = w._cards
    assert "border-bottom-left-radius: 0px" in c0.styleSheet()
    assert "border-bottom: none;" in c0.styleSheet()
    assert "border-top-left-radius: 0px" in c1.styleSheet()
    assert "border-bottom-left-radius: 8px" in c1.styleSheet()
    assert "border-bottom: none;" not in c1.styleSheet()
    for i in range(w._cards_layout.count()):
        item = w._cards_layout.itemAt(i)
        wdg = item.widget() if item is not None else None
        if isinstance(wdg, QFrame) and type(wdg) is QFrame:
            assert "transparent" in wdg.styleSheet()
            m = wdg.layout().contentsMargins()
            assert (m.left(), m.top(), m.right(), m.bottom()) == (0, 0, 0, 0)
            assert wdg.layout().spacing() == 0


def test_section_box_keeps_focus_on_click(tmp_path):
    """Clicking a card's section box must leave focus there (typable).

    Regression: the activation cascade used to yank focus into the
    shared display editor, making the section box untypable.
    """
    w = _designer(tmp_path)
    assert w._active == 0
    chip = w._cards[1]._chip
    QTest.mouseClick(chip, Qt.MouseButton.LeftButton)
    _qt().processEvents()
    assert w._active == 1
    assert _qt().focusWidget() is chip
    QTest.keyClicks(chip, "Chorus")
    _qt().processEvents()
    assert "Chorus" in chip.toPlainText()
    # Clicking the (focusless) display box still hands focus to the
    # live editor so slide text stays immediately typable.
    QTest.mouseClick(w._cards[1]._display_box, Qt.MouseButton.LeftButton)
    _qt().processEvents()
    assert _qt().focusWidget() is w._edit


def test_ctrl_right_stops_before_space_after_punct(tmp_path):
    """Custom word-end hop works through real key presses in both the
    shared editor and the section box; Ctrl+Left stays Qt default."""
    w = _designer(tmp_path)
    w._edit.setPlainText("ab, cd")
    cur = w._edit.textCursor()
    cur.setPosition(2)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier)
    assert w._edit.textCursor().position() == 3
    chip = w._cards[1]._chip
    w._cards[1].set_section("ab, cd")
    chip.setFocus()
    _qt().processEvents()
    cur = chip.textCursor()
    cur.setPosition(2)
    chip.setTextCursor(cur)
    QTest.keyClick(chip, Qt.Key.Key_Right,
                   Qt.KeyboardModifier.ControlModifier)
    assert chip.textCursor().position() == 3
    cur = chip.textCursor()
    cur.setPosition(6)
    chip.setTextCursor(cur)
    QTest.keyClick(chip, Qt.Key.Key_Left,
                   Qt.KeyboardModifier.ControlModifier)
    assert chip.textCursor().position() == 4


def test_ctrl_enter_adds_and_continues_in_editor(tmp_path):
    """Type, Ctrl+Enter, keep typing: new slide after active, old text
    kept, focus stays in the editor."""
    w = _designer(tmp_path)
    cur = w._edit.textCursor()
    cur.movePosition(QTextCursor.MoveOperation.End)
    w._edit.setTextCursor(cur)
    QTest.keyClicks(w._edit, "XYZ")
    QTest.keyClick(w._edit, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.ControlModifier)
    _qt().processEvents()
    assert len(w._slides) == 3 and w._active == 1
    assert w._slides[0]["text"].endswith("XYZ")
    assert w._slides[1]["text"] == ""
    assert _qt().focusWidget() is w._edit
    QTest.keyClicks(w._edit, "ABC")
    assert "ABC" in w._edit.document().toPlainText()


def test_ctrl_enter_from_section_keeps_section(tmp_path):
    w = _designer(tmp_path)
    chip = w._cards[0]._chip
    chip.setFocus()
    _qt().processEvents()
    QTest.keyClick(chip, Qt.Key.Key_A,
                   Qt.KeyboardModifier.ControlModifier)
    QTest.keyClicks(chip, "V")  # typed, so Ctrl+Enter must commit it
    QTest.keyClick(chip, Qt.Key.Key_Return,
                   Qt.KeyboardModifier.ControlModifier)
    _qt().processEvents()
    assert len(w._slides) == 3 and w._active == 1
    assert w._slides[0]["section"] == "V"
    assert _qt().focusWidget() is w._edit


def test_ctrl_enter_new_slide_scrolled_into_view(tmp_path):
    w = _run_designer(tmp_path, "# T\n\n\n" + "\n\n\n".join(
        f"*S{i}\nwords {i}" for i in range(12)))
    w._add_slide_and_continue(len(w._slides))
    _qt().processEvents()
    _qt().processEvents()  # fire the deferred ensure-visible
    vp = w._cards_scroll.viewport()
    card = w._cards[-1]
    assert vp.rect().contains(card.mapTo(vp, card.rect().topLeft()))
    assert vp.rect().contains(card.mapTo(vp, card.rect().bottomRight()))
    assert _qt().focusWidget() is w._edit


def test_burst_gate_truth_table(tmp_path):
    from ui.widgets.lite_designer.lite_designer import _burst_render_due
    assert _burst_render_due(None, None, 1000) is False
    assert _burst_render_due(1000, 1300, 1100) is False
    assert _burst_render_due(1150, 1300, 1300) is True
    assert _burst_render_due(1250, 1300, 1400) is True
    assert _burst_render_due(500, None, 900) is False
    assert _burst_render_due(500, 800, 900) is False
    assert _burst_render_due(1150, 1300, 1500) is False


def test_burst_renders_periodically_then_trailing(tmp_path):
    """Sustained burst renders at most every throttle window, then the
    trailing timer fires — the list always ends with an update."""
    w = _designer(tmp_path)
    renders = []
    w._preview.display_verse = lambda payload: renders.append(payload)
    for t in (0, 100, 200, 300, 450, 600):
        w._note_editor_burst(t)
    assert len(renders) == 2
    assert w._preview_timer.isActive()
    w._preview_timer.timeout.emit()
    assert len(renders) == 3


def test_preview_silent_when_idle(tmp_path):
    """One instant render from opening activation, then silence: no
    timer armed, no renders without events."""
    w = _designer(tmp_path)
    renders = []
    w._preview.display_verse = lambda payload: renders.append(payload)
    _qt().processEvents()
    assert len(renders) == 0
    assert not w._preview_timer.isActive()


def test_ctrl_delete_stops_at_punctuation_end(tmp_path):
    """Custom Ctrl+Delete: 'hello,| world' loses only the comma."""
    w = _designer(tmp_path)
    w._edit.setPlainText("hello, world")
    cur = w._edit.textCursor()
    cur.setPosition(5)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.ControlModifier)
    assert w._edit.toPlainText() == "hello world"
    assert w._edit.textCursor().position() == 5


def test_ctrl_backspace_mirrors_word_left(tmp_path):
    w = _designer(tmp_path)
    w._edit.setPlainText("hello, world")
    cur = w._edit.textCursor()
    cur.setPosition(12)
    w._edit.setTextCursor(cur)
    QTest.keyClick(w._edit, Qt.Key.Key_Backspace,
                   Qt.KeyboardModifier.ControlModifier)
    assert w._edit.toPlainText() == "hello, "


def test_section_ctrl_delete(tmp_path):
    w = _designer(tmp_path)
    chip = w._cards[1]._chip
    w._cards[1].set_section("ab, cd")
    chip.setFocus()
    _qt().processEvents()
    cur = chip.textCursor()
    cur.setPosition(2)
    chip.setTextCursor(cur)
    QTest.keyClick(chip, Qt.Key.Key_Delete,
                   Qt.KeyboardModifier.ControlModifier)
    assert chip.toPlainText() == "ab cd"


def test_double_click_selects_contraction_then_smart_delete(tmp_path):
    w = _designer(tmp_path)
    w._edit.setPlainText("don't stop")
    _qt().processEvents()
    cur = w._edit.textCursor()
    cur.setPosition(1)
    w._edit.setTextCursor(cur)
    QTest.mouseDClick(w._edit.viewport(), Qt.MouseButton.LeftButton,
                      pos=w._edit.cursorRect(cur).center())
    _qt().processEvents()
    assert w._edit.textCursor().selectedText() == "don't"
    QTest.keyClick(w._edit, Qt.Key.Key_Delete)
    assert w._edit.toPlainText() == "stop"


def test_triple_click_selects_paragraph_then_delete(tmp_path):
    w = _designer(tmp_path)
    w._edit.setPlainText("first para\nsecond line here\n\nnext para")
    _qt().processEvents()
    cur = w._edit.textCursor()
    cur.setPosition(w._edit.document().find("second").position() + 1)
    w._edit.setTextCursor(cur)
    pos = w._edit.cursorRect(w._edit.textCursor()).center()
    QTest.mouseClick(w._edit.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseDClick(w._edit.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseClick(w._edit.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    _qt().processEvents()
    sel = w._edit.textCursor()
    assert (sel.selectionStart(), sel.selectionEnd()) == (11, 28)
    QTest.keyClick(w._edit, Qt.Key.Key_Delete)
    assert w._edit.toPlainText() == "first para\nnext para"
