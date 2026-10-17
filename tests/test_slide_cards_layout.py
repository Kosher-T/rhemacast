"""
tests/test_slide_cards_layout.py

Tests verifying that SlideCard matches the sketch and behavioral requirements:
1. Two auto-growing textboxes (section textbox and display textbox).
2. Vertical growth as lines of text grow.
3. No horizontal scrolling.
4. Zero change to card size upon highlight / activation.
5. Dull colors when inactive, vibrant colors when in focus.
"""

import os
# Forced (not setdefault): see test_lite_designer_select.py — headless
# Wayland never activates windows, breaking focus/grab verification.
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QTextEdit
from PyQt6.QtCore import Qt
import pytest

from ui.widgets.lite_designer.slide_cards import (
    SlideCard, _SectionEdit, _DisplayBox,
    _CARD_NORMAL, _CARD_ACTIVE,
    _INDEX_NORMAL, _INDEX_ACTIVE,
    _SECTION_NORMAL, _SECTION_ACTIVE,
    _display_box_style, display_text_px
)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


def test_card_structure_matches_sketch(qapp):
    card = SlideCard(0, "Line 1\nLine 2")
    card.set_section("Verse 1")

    # Verify both textboxes are QTextEdit instances
    assert isinstance(card._chip, _SectionEdit)
    assert isinstance(card._chip, QTextEdit)
    assert isinstance(card._display_box, _DisplayBox)
    assert isinstance(card._display_box, QTextEdit)

    # Verify section chip text
    assert card._chip.toPlainText() == "Verse 1"
    assert card._display_box.toPlainText() == "Line 1\nLine 2"

    # Verify index label
    assert card._idx_label.text() == "1"

    # Verify action buttons (SVG icons; tooltips carry the meaning)
    assert card._btn_up.text() == ""
    assert card._btn_up.toolTip() == "Move slide up"
    assert not card._btn_up.icon().isNull()
    assert card._btn_down.text() == ""
    assert card._btn_down.toolTip() == "Move slide down"
    assert not card._btn_down.icon().isNull()
    assert card._btn_add.text() == ""
    assert card._btn_add.toolTip() == "Add slide after"
    assert not card._btn_add.icon().isNull()
    assert card._btn_del.text() == ""
    assert card._btn_del.toolTip() == "Delete slide"
    assert not card._btn_del.icon().isNull()


def test_no_horizontal_scroll(qapp):
    card = SlideCard(0, "A" * 200)
    card.set_section("Section " * 20)

    # Neither textbox permits horizontal scrollbars
    assert card._chip.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert card._display_box.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert card._chip.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth
    assert card._display_box.lineWrapMode() == QTextEdit.LineWrapMode.WidgetWidth


def test_textboxes_grow_vertically(qapp):
    card = SlideCard(0, "One line")
    card.resize(400, 100)
    card.show()
    qapp.processEvents()

    # Display box height with 1 line
    h_1_line = card._display_box.height()

    # Display box height with 4 lines
    card.set_content_text("Line 1\nLine 2\nLine 3\nLine 4")
    qapp.processEvents()
    h_4_lines = card._display_box.height()
    assert h_4_lines > h_1_line, f"Expected {h_4_lines} > {h_1_line}"

    # Display box height with 8 lines
    card.set_content_text("\n".join(f"Line {i}" for i in range(8)))
    qapp.processEvents()
    h_8_lines = card._display_box.height()
    assert h_8_lines > h_4_lines, f"Expected {h_8_lines} > {h_4_lines}"

    # Section edit height with 1 line
    card.set_section("1")
    qapp.processEvents()
    s_1_line = card._chip.height()

    # Section edit height with multi-line section
    card.set_section("Chorus\nPart 2\nContinuation")
    qapp.processEvents()
    s_3_lines = card._chip.height()
    assert s_3_lines > s_1_line, f"Expected {s_3_lines} > {s_1_line}"

    card.close()


def test_zero_size_change_upon_highlight(qapp):
    """Highlighting/focusing a card must NOT alter its dimensions."""
    card = SlideCard(0, "First line\nSecond line\nThird line")
    card.set_section("Verse 1")
    card.resize(400, 150)
    card.show()
    qapp.processEvents()

    # Create an editor like LiteDesigner provides
    editor = QTextEdit()
    editor.setFrameShape(card.frameShape())
    editor.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    editor.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    editor.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    editor.document().setDocumentMargin(0)
    editor.setPlainText("First line\nSecond line\nThird line")

    # Inactive height
    card.set_active(False)
    qapp.processEvents()
    inactive_height = card.sizeHint().height()

    # Host editor and activate (focus)
    card.host_editor(editor)
    card.set_active(True)
    qapp.processEvents()
    active_height = card.sizeHint().height()

    assert active_height == inactive_height, (
        f"Card size changed upon highlight: inactive={inactive_height}, active={active_height}"
    )

    # Release editor and deactivate
    card.release_editor()
    card.set_active(False)
    qapp.processEvents()
    restored_height = card.sizeHint().height()

    assert restored_height == inactive_height

    card.close()
    editor.deleteLater()


def test_dull_vs_vibrant_colors(qapp):
    card = SlideCard(0, "Some slide text")
    card.set_section("Chorus")

    # Inactive state: dull (base style first; positional corners append)
    card.set_active(False)
    assert card.styleSheet().startswith(_CARD_NORMAL)
    assert card._idx_label.styleSheet() == _INDEX_NORMAL
    assert card._chip.styleSheet() == _SECTION_NORMAL
    assert card._display_box.styleSheet() == _display_box_style(
        False, card._display_box._px)

    # Active state: vibrant
    card.set_active(True)
    assert card.styleSheet().startswith(_CARD_ACTIVE)
    assert card._idx_label.styleSheet() == _INDEX_ACTIVE
    assert card._chip.styleSheet() == _SECTION_ACTIVE
    assert card._display_box.styleSheet() == _display_box_style(
        True, card._display_box._px)
    # Box size tracks the fixed display setting (13px default here).
    assert f"font-size: {display_text_px()}px" in \
        card._display_box.styleSheet()


def test_display_box_has_no_boundary(qapp):
    """Display textbox is boundary-less: transparent fill, so pixels
    inside it match the surrounding card background exactly."""
    from PyQt6.QtCore import QPoint
    card = SlideCard(0, "Slide 1")
    card.resize(400, 120)
    card.show()
    qapp.processEvents()
    img = card.grab().toImage()
    box = card._display_box
    inside = img.pixelColor(box.mapTo(card, QPoint(2, 2)))
    outside = img.pixelColor(box.mapTo(card, QPoint(-6, 2)))
    assert inside == outside, f"inside={inside.getRgb()} outside={outside.getRgb()}"
    card.close()


def test_display_box_takes_no_focus(qapp):
    """Display box is chromeless like the section box: NoFocus policy,
    so no focus rect or caret can ever draw on it. Section stays typable."""
    card = SlideCard(0, "Slide 1")
    assert card._display_box.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert card._chip.focusPolicy() != Qt.FocusPolicy.NoFocus
    # Cursor parity: display viewport shows the I-beam text cursor on
    # hover, same as the section textbox (no hand pointer).
    assert card._display_box.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    assert card._chip.viewport().cursor().shape() == Qt.CursorShape.IBeamCursor
    card.close()


def _edge_has_red(img, widget, host):
    """Scan the widget rect's top/left edges for hostile-ancestor red."""
    from PyQt6.QtCore import QPoint
    top_left = widget.mapTo(host, QPoint(0, 0))
    x0, y0 = top_left.x(), top_left.y()
    for dx in range(0, widget.width(), 3):
        c = img.pixelColor(x0 + dx, y0)
        if c.red() > 200 and c.green() < 100 and c.blue() < 100:
            return True
    for dy in range(0, widget.height(), 3):
        c = img.pixelColor(x0, y0 + dy)
        if c.red() > 200 and c.green() < 100 and c.blue() < 100:
            return True
    return False


def test_display_row_ignores_hostile_ancestor_border(qapp):
    """Ancestor bare-QWidget border rules (like the designer popup's
    `QWidget { border: 1px solid ... }`) must not paint a boundary on
    the display row: neither the container nor the textbox viewport."""
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    host = QWidget()
    host.setStyleSheet("QWidget { border: 2px solid #ff0000; }")
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    card = SlideCard(0, "Slide 1")
    card.set_section("Verse 1")
    lay.addWidget(card)
    host.resize(420, 160)
    host.show()
    qapp.processEvents()
    img = host.grab().toImage()
    assert not _edge_has_red(img, card._display_box, host), \
        "ancestor border paints on the display textbox"
    assert not _edge_has_red(img, card._display_container, host), \
        "ancestor border paints on the display container"
    assert not _edge_has_red(img, card._chip, host), \
        "ancestor border paints on the section textbox"
    host.close()


def test_minimal_padding_below_display(qapp):
    """Vertical padding below the display textbox is utterly minimal."""
    card = SlideCard(0, "Slide 1")
    assert card.layout().contentsMargins().bottom() <= 2
    card.close()


def test_joined_seam_renders_flat(qapp):
    """Seam ends match seam middle pixel-for-pixel: square corners with
    no rounded notches where stacked cards meet."""
    from PyQt6.QtWidgets import QWidget, QVBoxLayout
    from PyQt6.QtCore import QPoint
    host = QWidget()
    host.setStyleSheet("QWidget { background: #0f172a; border: none; }")
    lay = QVBoxLayout(host)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    c0 = SlideCard(0, "a")
    c0.set_section("V")
    c0.set_joined(True, False)
    c0.set_active(False)
    c1 = SlideCard(1, "b")
    c1.set_section("")
    c1.set_joined(False, True)
    c1.set_active(False)
    lay.addWidget(c0)
    lay.addWidget(c1)
    host.resize(400, 160)
    host.show()
    qapp.processEvents()
    img = host.grab().toImage()
    o = c0.mapTo(host, QPoint(0, 0))
    seam_y = o.y() + c0.height() - 1  # shared edge row (c1's top border)
    mid = img.pixelColor(o.x() + c0.width() // 2, seam_y)
    end = img.pixelColor(o.x() + 3, seam_y)
    assert all(abs(a - b) <= 14
               for a, b in zip(mid.getRgb(), end.getRgb())), \
        f"notched seam: mid={mid.getRgb()} end={end.getRgb()}"
    host.close()


def test_joined_stack_shapes(qapp):
    """Touching edges square, outer edges round; idle non-last cards
    drop the bottom edge (shared 1px seam); highlight keeps full outline."""
    top = SlideCard(0, "a")
    top.set_joined(True, False)
    top.set_active(False)
    ss = top.styleSheet()
    assert "border-top-left-radius: 8px" in ss
    assert "border-bottom-left-radius: 0px" in ss
    assert "border-bottom: none;" in ss
    mid = SlideCard(1, "b")
    mid.set_joined(False, False)
    mid.set_active(True)
    ss = mid.styleSheet()
    assert "border-top-left-radius: 0px" in ss
    assert "border-bottom-left-radius: 0px" in ss
    assert "border-bottom: none;" not in ss  # focus traces full shape
    last = SlideCard(2, "c")
    last.set_joined(False, True)
    last.set_active(False)
    ss = last.styleSheet()
    assert "border-top-left-radius: 0px" in ss
    assert "border-bottom-left-radius: 8px" in ss
    assert "border-bottom: none;" not in ss
    single = SlideCard(0, "only")
    single.set_joined(True, True)
    single.set_active(False)
    assert "border-top-left-radius: 8px" in single.styleSheet()
    assert "border-bottom-left-radius: 8px" in single.styleSheet()
    assert "border-bottom: none;" not in single.styleSheet()
    for c in (top, mid, last, single):
        c.close()


def test_word_ahead_stop(qapp):
    from ui.widgets.lite_designer.slide_cards import word_ahead_stop
    assert word_ahead_stop("hello, world", 5) == 6
    assert word_ahead_stop("word; x", 4) == 5
    # Letters, spaces, block ends: Qt default (shared kernel).
    assert word_ahead_stop("ab cd", 0) is None
    assert word_ahead_stop("ab cd", 2) is None
    assert word_ahead_stop("a  b", 1) is None
    assert word_ahead_stop("ab", 2) is None
    assert word_ahead_stop("ab\ncd", 2) is None
    assert word_ahead_stop("x ,y", 1) is None


def _doc_cursor(text, pos):
    from PyQt6.QtGui import QTextDocument, QTextCursor
    doc = QTextDocument(text)
    cur = QTextCursor(doc)
    cur.setPosition(pos)
    return doc, cur


def test_select_word_at_contractions(qapp):
    from ui.widgets.lite_designer.slide_cards import select_word_at
    doc, cur = _doc_cursor("don't stop", 1)
    assert select_word_at(cur) is True
    assert (cur.selectionStart(), cur.selectionEnd()) == (0, 5)
    doc, cur = _doc_cursor("hello, world", 1)
    assert select_word_at(cur) is True
    assert (cur.selectionStart(), cur.selectionEnd()) == (0, 5)
    doc, cur = _doc_cursor("hello, world", 5)
    assert select_word_at(cur) is False
    doc, cur = _doc_cursor("'tis fine", 1)
    assert select_word_at(cur) is True
    assert (cur.selectionStart(), cur.selectionEnd()) == (1, 4)


def test_select_block_includes_newline(qapp):
    from ui.widgets.lite_designer.slide_cards import select_block
    doc, cur = _doc_cursor("a\nbb\nc", 3)
    select_block(cur)
    assert (cur.selectionStart(), cur.selectionEnd()) == (2, 5)
    assert cur.selectedText() == "bb\u2029"
    doc, cur = _doc_cursor("a\nbb\nc", 6)
    select_block(cur)
    assert (cur.selectionStart(), cur.selectionEnd()) == (5, 6)


def test_smart_delete_word_rule(qapp):
    from ui.widgets.lite_designer.slide_cards import smart_delete_extend
    doc, _ = _doc_cursor("hello world", 0)
    assert smart_delete_extend(doc, 0, 5, True) == (0, 6)
    assert smart_delete_extend(doc, 0, 5, False) == (0, 5)
    doc, _ = _doc_cursor("hello, world", 0)
    assert smart_delete_extend(doc, 0, 5, True) == (0, 5)
    doc, _ = _doc_cursor("a hello", 0)
    assert smart_delete_extend(doc, 2, 7, False) == (1, 7)
    assert smart_delete_extend(doc, 2, 7, True) == (2, 7)
    doc, _ = _doc_cursor("a  b", 0)
    assert smart_delete_extend(doc, 0, 1, True) == (0, 2)


def test_smart_delete_paragraph_rule(qapp):
    from ui.widgets.lite_designer.slide_cards import smart_delete_extend
    doc, _ = _doc_cursor("a\nbb\nc", 0)
    assert smart_delete_extend(doc, 2, 5, True) == (2, 5)
    assert smart_delete_extend(doc, 2, 5, False) == (1, 5)
    assert smart_delete_extend(doc, 0, 2, True) == (0, 2)
    assert smart_delete_extend(doc, 0, 1, True) == (0, 2)
    assert smart_delete_extend(doc, 5, 6, False) == (4, 6)
    assert smart_delete_extend(doc, 5, 6, True) == (5, 6)


def test_triple_tracker_counts(qapp):
    from PyQt6.QtCore import Qt, QPoint
    from ui.widgets.lite_designer.slide_cards import TripleTracker
    t = TripleTracker()
    p = QPoint(10, 10)
    assert t.register(Qt.MouseButton.LeftButton, p) == 1
    assert t.register(Qt.MouseButton.LeftButton, p) == 2
    assert t.register(Qt.MouseButton.LeftButton, p) == 3
    assert t.register(Qt.MouseButton.LeftButton, p) == 1
    assert t.register(Qt.MouseButton.RightButton, p) == 0


def _hop(text, pos, keep_anchor=False):
    from PyQt6.QtGui import QTextDocument, QTextCursor
    from ui.widgets.lite_designer.slide_cards import move_to_word_end_right
    doc = QTextDocument(text)
    cur = QTextCursor(doc)
    cur.setPosition(pos)
    anchor_before = cur.anchor()
    handled = move_to_word_end_right(cur, keep_anchor=keep_anchor)
    return handled, cur.position(), anchor_before


def test_word_end_right_stops_at_punctuation_clusters(qapp):
    assert _hop("hello, world", 5) == (True, 6, 5)
    assert _hop("word; another", 4) == (True, 5, 4)
    assert _hop("a,; b", 1) == (True, 3, 1)
    assert _hop("word;", 4) == (True, 5, 4)


def test_word_end_right_defers_to_qt_otherwise(qapp):
    assert _hop("hello, world", 0) == (False, 0, 0)
    assert _hop("hello world", 5) == (False, 5, 5)
    assert _hop("ab", 2) == (False, 2, 2)


def test_word_end_right_extends_selection(qapp):
    assert _hop("hello, world", 5, keep_anchor=True) == (True, 6, 5)


def test_update_style_skips_identical_repolish(qapp):
    """Re-applying the same visual state issues zero setStyleSheet calls
    (redundant repolish measured ~5ms/call with no visual effect)."""
    card = SlideCard(0, "x")
    calls = []
    orig = card.setStyleSheet
    card.setStyleSheet = lambda ss: (calls.append(ss), orig(ss))
    card.set_active(False)  # unchanged from init: skip
    assert calls == []
    card.set_active(True)  # changed: exactly one polish
    assert len(calls) == 1
    card.set_active(True)  # unchanged: skip
    card.set_joined(True, True)  # unchanged: skip
    assert len(calls) == 1
    card.close()
