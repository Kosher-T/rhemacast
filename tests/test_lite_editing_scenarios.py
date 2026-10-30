"""The lite-editing closed-loop smoke pattern.

One scenario: boot → edit → split → type → checkpoint (save → re-parse →
fresh re-open → compare) → verify the model survived. This file proves
the harness itself; feature scenarios land here as they are implemented.

Designers are kept referenced (never close()d) — the same teardown rule
tests/test_lite_designer_select.py follows; see the harness docstring.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

import ui.widgets.display_view  # noqa: F401

from PyQt6.QtCore import Qt as _Qt

from tests.harness.lite_editing import Lab

_LABS = []

DECK = ("# Amazing Grace\n\n*Verse 1\n"
        "Amazing grace how sweet\nthe sound\n\n---\n\n"
        "*Chorus\nMy chains are gone\n")


def _lab(tmp_path, deck=DECK):
    lab = Lab(tmp_path, deck)
    _LABS.append(lab)
    return lab


def test_closed_loop_edit_split_checkpoint(tmp_path):
    """The whole chain — keystrokes, split, save, reopen — holds."""
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    lab.ctrl_enter()                  # boundary at the caret (v3: `---`)
    lab.text("that saved a wretch like me")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", "that saved a wretch like me"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("after split")
    lab.checkpoint("smoke")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", "that saved a wretch like me"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("after reopen")


def test_closed_loop_word_replace(tmp_path):
    """Word-replace via double-click survives save and reopen."""
    lab = _lab(tmp_path)
    lab.dblclick_at(0, 9)             # select "grace" in slide 0
    lab.text("GRACE")
    lab.expect_brief([
        ("Verse 1", "Amazing GRACE how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.checkpoint("word-replace")
    lab.expect_brief([
        ("Verse 1", "Amazing GRACE how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])


def test_split_keeps_keyboard_focus(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    lab.ctrl_enter()                  # split — caret moves to the new card
    lab.expect_focus("text:1")
    lab.text("lost without the fix")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", "lost without the fix"),
        ("Chorus", "My chains are gone"),
    ])


def test_blank_line_inside_slide_survives_save(tmp_path):
    """Regression: blank lines are slide content. The parser keeps them and
    the doc round-trip (txt_to_doc -> doc_to_txt) must not collapse the
    empty block on load."""
    lab = _lab(tmp_path)
    lab.focus_text(0, 3)
    lab.enter()
    lab.enter()                       # one blank line mid-slide
    lab.text("AB ")                   # same paragraph, after the gap
    lab.expect_brief([
        ("Verse 1", "Ama\n\nAB zing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.checkpoint("blank-line")


def test_structural_rerender_is_a_single_visible_frame(tmp_path):
    """Add-card must rearrange in one frame — never paint a half-built
    middle state. Frames (PNG evidence) are saved under tmp_path/frames."""
    lab = _lab(tmp_path)
    rows = lab.capture_frames(lambda: lab.click_add(0), label="add-card",
                              scope=lab.w._cards_scroll)
    assert len(rows) >= 10
    changed = [r for r in rows if r["diff"] > 0]
    assert changed, "the captured window never showed the new card"
    assert len(changed) == 1, (
        "the rerender was visible across multiple frames — a half-built "
        f"layout leaked: {changed}")
    assert os.path.isfile(changed[0]["png"])


def test_ctrl_enter_splits_at_caret(tmp_path):
    """The boundary lands where the caret is; the caret continues below."""
    lab = _lab(tmp_path)
    lab.focus_text(0, 7)              # between "Amazing" and " grace"
    lab.ctrl_enter()
    lab.expect_focus("text:1")
    lab.expect_caret(0)
    lab.expect_brief([
        ("Verse 1", "Amazing"),
        ("Verse 1", " grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.end_doc()
    lab.text(" endless")
    lab.check("split at caret")
    lab.checkpoint("split at caret")
    lab.expect_brief([
        ("Verse 1", "Amazing"),
        ("Verse 1", " grace how sweet\nthe sound endless"),
        ("Chorus", "My chains are gone"),
    ])


def test_ctrl_insert_and_ctrl_down_add_and_continue(tmp_path):
    """Both add-and-continue keys leave the caret typing in the new card."""
    from PyQt6.QtCore import Qt as _Qt
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    lab.tap(_Qt.Key.Key_Insert, _Qt.KeyboardModifier.ControlModifier)
    lab.expect_focus("text:1")
    lab.text("first")
    lab.tap(_Qt.Key.Key_Down, _Qt.KeyboardModifier.ControlModifier)
    lab.expect_focus("text:2")
    lab.text("second")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", "first"),
        ("Verse 1", "second"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("add-and-continue")
    lab.checkpoint("add-and-continue")


def test_tab_indents_and_round_trips(tmp_path):
    """Tab indents the paragraph and the txt keeps it; Shift+Tab reverses."""
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.tab()
    lab.expect_brief([
        ("Verse 1", "    Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.checkpoint("tab-indent")
    lab.focus_text(0, 0)              # a fresh window boots unfocused
    lab.tab(shift=True)
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("outdent")


def test_ctrl_bold_italic_underline_write_runs(tmp_path):
    """Ctrl+B/I/U drive the ribbon toggles and survive serialization."""
    from PyQt6.QtCore import Qt as _Qt
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.select_range(0, 0, 7)        # "Amazing"
    lab.tap(_Qt.Key.Key_B, _Qt.KeyboardModifier.ControlModifier)
    assert "bold=" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]
    lab.tap(_Qt.Key.Key_I, _Qt.KeyboardModifier.ControlModifier)
    lab.tap(_Qt.Key.Key_U, _Qt.KeyboardModifier.ControlModifier)
    txt = lab.body_doc_parts(0)[0]
    assert "italics=" in txt and "underline=" in txt, txt
    lab.checkpoint("format shortcuts")
    txt = lab.body_doc_parts(0)[0]
    assert "italics=" in txt and "underline=" in txt, txt


MEMBER_DECK = ("# Amazing Grace\n\n*Verse 1\nA\n\n---\n\nB\n\n---\n\n"
               "*Chorus\nC\n")


def test_caret_queue_section_and_body(tmp_path):
    """The section box is in the queue: body ↔ section ↔ neighbour card."""
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.up()                          # body start -> same card's section end
    lab.expect_focus("section:0")
    lab.expect_caret(len("Verse 1"))
    lab.down()                        # section end -> same card's body start
    lab.expect_focus("text:0")
    lab.expect_caret(0)
    lab.end_doc()
    lab.down()                        # body end -> next card's section start
    lab.expect_focus("section:1")
    lab.expect_caret(0)
    lab.up()                          # section start -> previous body end
    lab.expect_focus("text:0")
    lab.expect_caret(len(lab.slides()[0][1]))
    lab.focus_text(0, 0)
    lab.left()                        # body start -> same card's section end
    lab.expect_focus("section:0")
    lab.expect_caret(len("Verse 1"))
    lab.right()                       # section end -> body start
    lab.expect_focus("text:0")
    lab.expect_caret(0)


def test_backspace_body_start_absorbs_first_paragraph_into_section(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.backspace()
    lab.expect_focus("section:0")
    lab.expect_brief([
        ("Verse 1Amazing grace how sweet", "the sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("section absorb")
    lab.checkpoint("section absorb")
    lab.expect_brief([
        ("Verse 1Amazing grace how sweet", "the sound"),
        ("Chorus", "My chains are gone"),
    ])


def test_backspace_body_start_merges_into_previous_card(tmp_path):
    lab = _lab(tmp_path, MEMBER_DECK)
    lab.focus_text(1, 0)              # card with an empty section box
    lab.backspace()
    lab.expect_focus("text:0")
    lab.expect_caret(len("A"))
    lab.expect_brief([
        ("Verse 1", "A\nB"),
        ("Chorus", "C"),
    ])
    lab.check("merge up")
    lab.checkpoint("merge up")
    lab.expect_brief([
        ("Verse 1", "A\nB"),
        ("Chorus", "C"),
    ])


def test_delete_body_end_absorbs_next_card_and_drops_its_section(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    lab.delete()
    lab.expect_focus("text:0")
    lab.expect_caret(len("Amazing grace how sweet\nthe sound"))
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound\nMy chains are gone"),
    ])
    lab.check("merge down")
    lab.checkpoint("merge down")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound\nMy chains are gone"),
    ])


def test_section_enter_spills_tail_into_body(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_section(0)
    lab.end_doc()
    lab.text(" Second")
    lab.focus_section(0, len("Verse 1 "))
    lab.enter()
    lab.expect_focus("text:0")
    lab.expect_caret(0)
    lab.expect_brief([
        ("Verse 1", "Second\nAmazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("section spill")
    lab.checkpoint("section spill")


NO_SECTION_DECK = "# T\n\nA\n\n---\n\nB\n"


def test_boundary_deletes_are_noops(tmp_path):
    lab = _lab(tmp_path, NO_SECTION_DECK)
    before = lab.slides()
    lab.focus_text(0, 0)
    lab.backspace()                   # nothing above, no section name
    lab.expect_brief(before)
    lab.end_doc()
    lab.focus_text(1)
    lab.end_doc()
    lab.delete()                      # last card: nothing below
    lab.expect_brief(before)
    lab.expect_focus("text:1")


def test_undo_redo_typing(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.text("X")
    lab.undo()
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.redo()
    lab.expect_brief([
        ("Verse 1", "XAmazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.check("typing undo/redo")


def test_undo_structural_step_order(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.ctrl_insert()                 # add-and-continue: new card below
    lab.text("New")
    lab.undo()                        # typing is its own step
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", ""),
        ("Chorus", "My chains are gone"),
    ])
    lab.undo()                        # then the add
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.redo()                        # redo the add
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", ""),
        ("Chorus", "My chains are gone"),
    ])


def test_undo_split_and_merge(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 7)
    lab.ctrl_enter()
    lab.undo()
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.redo()
    lab.expect_brief([
        ("Verse 1", "Amazing"),
        ("Verse 1", " grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])
    lab.undo()
    lab.focus_text(0, 0)
    lab.backspace()                   # absorb first paragraph into the section
    lab.undo()
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])


def test_undo_indent(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 3)
    lab.tap(_Qt.Key.Key_Tab)
    lab.check("indent applied")
    lab.undo()
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])


def test_undo_survives_checkpoint(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.text("Q")
    lab.undo()
    lab.checkpoint("undo checkpoint")
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ])


def test_open_focuses_active_editor(tmp_path):
    lab = _lab(tmp_path)              # no explicit focus_text: fresh open
    lab.expect_focus("text:0")


def test_save_prunes_empty_cards(tmp_path):
    from core.slide_parser import parse_slide_txt
    from core.slide_service import get_deck

    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.ctrl_insert()                 # empty placeholder card
    lab.expect_brief([
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Verse 1", ""),
        ("Chorus", "My chains are gone"),
    ])
    lab.save()
    deck = get_deck(lab.deck_id)
    parsed = parse_slide_txt(deck["raw_text"])
    assert [(s.get("section") or "", s.get("text") or "")
            for s in parsed["slides"]] == [
        ("Verse 1", "Amazing grace how sweet\nthe sound"),
        ("Chorus", "My chains are gone"),
    ]


def test_delete_card_no_confirm_and_rehosts_next(tmp_path):
    lab = _lab(tmp_path)
    assert lab.slides()[0][0] == "Verse 1"
    lab.w._cards[0]._btn_del.click()
    lab.settle()
    assert lab.confirm_calls == 0, "delete must not ask for confirmation"
    lab.expect_brief([("Chorus", "My chains are gone")])
    lab.expect_focus("text:0")


def test_close_prompt_cancel_then_discard(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 3)
    lab.text("Z")                     # dirty deck
    lab.request_close()
    assert lab.w.isVisible(), "first close with edits must be vetoed"
    overlay = lab.w._close_overlay
    assert overlay is not None and overlay.isVisible()
    lab.answer_close(discard=False)
    assert lab.w.isVisible() and not overlay.isVisible()
    lab.request_close()
    lab.answer_close(discard=True)
    assert not lab.w.isVisible()


def test_clean_close_needs_no_prompt(tmp_path):
    lab = _lab(tmp_path)
    lab.request_close()
    assert lab.w._close_overlay is None
    assert not lab.w.isVisible()


def test_runs_survive_structural_ops(tmp_path):
    from PyQt6.QtCore import Qt as _Qt
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.select_range(0, 0, 7)         # "Amazing" (part of line 1)
    lab.tap(_Qt.Key.Key_I, _Qt.KeyboardModifier.ControlModifier)
    assert "italics=true" in lab.body_doc_parts(0)[0]
    lab.focus_text(0, 7)
    lab.ctrl_enter()                  # split keeps the run with its text
    assert "italics=true" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]
    lab.tap(_Qt.Key.Key_Tab)          # indent
    assert "italics=true" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]
    lab.undo()                        # indent undone, run still there
    assert "italics=true" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]
    lab.checkpoint("runs after split")
    assert "italics=true" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]
    lab.focus_text(0)
    lab.end_doc()
    lab.delete()                      # merge forward
    assert "italics=true" in lab.body_doc_parts(0)[0], lab.body_doc_parts(0)[0]


def test_html_paste_lands_as_plain_text(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    lab.set_clipboard(
        "Plain <b>bold</b>",
        html="<html><body><b>Plain</b> bold</body></html>")
    lab.paste()
    body = lab.body_doc_parts(0)[0]
    assert body.startswith("Plain <b>bold</b>"), body
    assert "bold=" not in body and "italics=" not in body, body
    lab.undo()
    lab.set_clipboard(
        "", html="<html><body><p>From <b>HTML</b></p></body></html>")
    lab.paste()
    body = lab.body_doc_parts(0)[0]
    assert "From HTML" in body, body
    assert "bold=" not in body and "italics=" not in body, body


def test_whole_deck_paste_is_fast(tmp_path):
    import time
    lab = _lab(tmp_path)
    lab.focus_text(0, 0)
    big = "\n\n".join(f"*Section {i}\nline {i}" for i in range(60))
    lab.set_clipboard(big)
    t0 = time.monotonic()
    lab.paste()
    lab.settle()
    elapsed_ms = (time.monotonic() - t0) * 1000.0
    slides = lab.slides()
    # The pasted fragment replaces the active slide; the untouched
    # trailing slide (Chorus) survives after it.
    assert len(slides) == 61, len(slides)
    assert slides[0] == ("Section 0", "line 0")
    assert slides[59] == ("Section 59", "line 59")
    assert slides[60] == ("Chorus", "My chains are gone")
    assert elapsed_ms < 1500, f"60-section paste took {elapsed_ms:.0f}ms"


def test_delete_and_merge_rerender_are_single_frames(tmp_path):
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    rows = lab.capture_frames(lambda: lab.delete(), label="merge-forward",
                              scope=lab.w._cards_scroll)
    changed = [r for r in rows if r["diff"] > 0]
    assert changed and len(changed) == 1, [r["diff"] for r in rows]
    lab.undo()
    assert len(lab.slides()) == 2
    rows = lab.capture_frames(lambda: lab.click_delete(1),
                              label="delete-card",
                              scope=lab.w._cards_scroll)
    changed = [r for r in rows if r["diff"] > 0]
    assert changed and len(changed) == 1, [r["diff"] for r in rows]
    lab.expect_brief([("Verse 1", "Amazing grace how sweet\nthe sound")])


def test_combination_format_structure_undo_checkpoint(tmp_path):
    from PyQt6.QtCore import Qt as _Qt
    lab = _lab(tmp_path)
    lab.focus_text(0)
    lab.end_doc()
    lab.text(" more")
    lab.select_range(0, 0, 7)         # "Amazing"
    lab.tap(_Qt.Key.Key_I, _Qt.KeyboardModifier.ControlModifier)
    lab.focus_text(0, 7)
    lab.ctrl_enter()                  # split at the caret
    assert len(lab.slides()) == 3
    lab.tap(_Qt.Key.Key_Tab)          # indent the new card's first line
    assert lab.body_doc_parts(1)[0].startswith("     grace"), \
        lab.body_doc_parts(1)[0]
    lab.undo()                        # unindent
    assert lab.body_doc_parts(1)[0] == " grace how sweet\nthe sound more"
    lab.undo()                        # unsplit
    assert len(lab.slides()) == 2
    assert "italics=true" in lab.body_doc_parts(0)[0]
    lab.redo()                        # split again
    assert len(lab.slides()) == 3
    lab.redo()                        # indent again
    assert lab.body_doc_parts(1)[0].startswith("     grace")
    lab.checkpoint("combination")
    assert "italics=true" in lab.body_doc_parts(0)[0]
    assert lab.body_doc_parts(1)[0].startswith("     grace")
    lab.click_delete(1)
    assert len(lab.slides()) == 2


def _box_visual(box):
    """Everything the operator sees in a card's display textbox.

    Widths/heights come from the actual QTextDocument layout, so a font or
    size leaking past the metadata layer changes these numbers.
    """
    doc = box.document()
    doc.documentLayout().documentSize()
    block = doc.firstBlock()
    layout = block.layout()
    line_w = (layout.lineAt(0).naturalTextWidth()
              if layout is not None and layout.lineCount() else -1.0)
    return {
        "text": doc.toPlainText(),
        "family": doc.defaultFont().family(),
        "metrics_h": box.fontMetrics().height(),
        "line_w": line_w,
        "doc_h": doc.documentLayout().documentSize().height(),
    }


def _preview_payload(lab):
    from unittest.mock import patch
    with patch.object(lab.w._preview, "display_verse") as spy:
        lab.w._refresh_preview()
        assert spy.call_count == 1, spy.call_count
        return spy.call_args[0][0]


def _installed_alternative(display_family):
    from PyQt6.QtGui import QFontDatabase
    for family in ("DejaVu Serif", "Liberation Serif", "Serif"):
        if family in QFontDatabase.families() and family != display_family:
            return family
    return None


def test_font_family_is_preview_only_and_persists(tmp_path):
    """Family lands in run metadata, never in either textbox — and the
    ribbon reads it back after save/reopen."""
    import pytest
    from PyQt6.QtGui import QFont
    lab = _lab(tmp_path)
    family = _installed_alternative(lab.w._edit.font().family())
    if family is None:
        pytest.skip("no alternative serif family installed")

    lab.click_card(1)                 # card 0's display box is now visible
    before = _box_visual(lab.w._cards[0]._display_box)
    lab.focus_text(0)
    lab.select_range(0, 0, 7)         # "Amazing"
    editor_font = (lab.w._edit.font().family(),
                   lab.w._edit.fontMetrics().height())
    lab.w._ribbon._font_combo.setCurrentFont(QFont(family))
    lab.settle()

    assert f"font={family}" in lab.body_doc_parts(0)[0]
    assert (lab.w._edit.font().family(),
            lab.w._edit.fontMetrics().height()) == editor_font, \
        "the live editor must keep its constant font"
    payload = _preview_payload(lab)
    assert f"font={family}" in payload["text"], payload["text"]
    lab.focus_text(1)
    lab.focus_text(0, 3)
    assert lab.w._ribbon._font_combo.currentFont().family() == family, \
        "the ribbon must read back the run's family"
    assert lab.body_doc_parts(0)[0].count("font=") == 1, \
        "syncing the combo must not stamp the font onto other runs"
    lab.click_card(1)
    assert _box_visual(lab.w._cards[0]._display_box) == before, \
        "the card display textbox must keep its constant font"

    lab.checkpoint("font")
    lab.focus_text(0, 3)               # caret inside the font run
    assert lab.body_doc_parts(0)[0].count("font=") == 1
    assert f"font={family}" in lab.body_doc_parts(0)[0]
    assert lab.w._ribbon._font_combo.currentFont().family() == family, \
        lab.w._ribbon._font_combo.currentFont().family()
    lab.click_card(1)
    assert _box_visual(lab.w._cards[0]._display_box) == before


def test_size_steppers_step_one_and_stay_out_of_textboxes(tmp_path):
    """−/+ move exactly one unit; the preset ladder stays in the dropdown;
    neither textbox renders the run size."""
    lab = _lab(tmp_path)
    lab.click_card(1)
    before = _box_visual(lab.w._cards[0]._display_box)
    lab.focus_text(0)
    lab.select_range(0, 0, 7)
    editor_font = (lab.w._edit.font().family(),
                   lab.w._edit.fontMetrics().height())
    ribbon = lab.w._ribbon
    base = ribbon._current_size_px()

    ribbon._size_plus.click()
    lab.settle()
    assert ribbon._current_size_px() == base + 1, ribbon._current_size_px()
    ribbon._size_plus.click()
    lab.settle()
    assert ribbon._current_size_px() == base + 2, ribbon._current_size_px()
    ribbon._size_minus.click()
    lab.settle()
    assert ribbon._current_size_px() == base + 1, ribbon._current_size_px()
    assert f"size={base + 1}" in lab.body_doc_parts(0)[0]
    assert (lab.w._edit.font().family(),
            lab.w._edit.fontMetrics().height()) == editor_font, \
        "the live editor must keep its constant size"

    presets = [ribbon._size_combo.itemText(i)
               for i in range(ribbon._size_combo.count())]
    assert "20" in presets and "24" in presets, presets
    assert str(base + 1) not in presets, (base + 1, presets)

    assert f"size={base + 1}" in _preview_payload(lab)["text"]
    lab.click_card(1)
    assert _box_visual(lab.w._cards[0]._display_box) == before, \
        "the card display textbox must not render the run size"

    lab.checkpoint("size")
    lab.focus_text(0, 3)
    assert lab.body_doc_parts(0)[0].count("size=") == 1
    assert f"size={base + 1}" in lab.body_doc_parts(0)[0]
    assert ribbon is not lab.w._ribbon
    assert lab.w._ribbon._current_size_px() == base + 1
    assert f"size={base + 1}" in _preview_payload(lab)["text"]


def test_deck_font_stays_out_of_text_and_persists(tmp_path):
    """Tier 4 font is a top-script override: no inline runs, no textbox
    change, preview gets it, save/reopen keeps it."""
    import pytest
    from PyQt6.QtGui import QFont
    lab = _lab(tmp_path)
    family = _installed_alternative(lab.w._edit.font().family())
    if family is None:
        pytest.skip("no alternative serif family installed")

    lab.click_card(1)
    before = _box_visual(lab.w._cards[0]._display_box)
    lab.focus_text(0)
    lab.select_all_tier(4)
    assert lab.w._sel_tier == 4
    lab.w._ribbon._font_combo.setCurrentFont(QFont(family))
    lab.settle()

    assert lab.w._format.get("font") == family, lab.w._format
    assert "font=" not in lab.body_doc_parts(0)[0]
    lab.click_card(1)
    assert _box_visual(lab.w._cards[0]._display_box) == before
    assert _preview_payload(lab)["slide_format"].get("font") == family

    lab.checkpoint("deck-font")
    assert lab.w._format.get("font") == family, lab.w._format
    assert "font=" not in lab.body_doc_parts(0)[0]
    assert lab.w._ribbon._font_combo.currentFont().family() == family, \
        "the ribbon must read back the deck's family"
    lab.click_card(1)
    assert _box_visual(lab.w._cards[0]._display_box) == before


def test_typed_text_inherits_font_and_size_across_checkpoint(tmp_path):
    """Choosing family/size at a bare caret formats what is typed next —
    and that run survives save/reopen."""
    import pytest
    from PyQt6.QtGui import QFont
    lab = _lab(tmp_path)
    family = _installed_alternative(lab.w._edit.font().family())
    if family is None:
        pytest.skip("no alternative serif family installed")

    lab.focus_text(0, 0)
    ribbon = lab.w._ribbon
    base = ribbon._current_size_px()
    ribbon._font_combo.setCurrentFont(QFont(family))
    ribbon._size_plus.click()
    ribbon._size_plus.click()
    lab.settle()
    lab.text("X")
    lab.settle()

    txt, _runs = lab.body_doc_parts(0)
    first = txt.split(")")[0]
    assert first.startswith("[X ("), txt
    assert f"font={family}" in first, txt
    assert f"size={base + 2}" in first, txt

    lab.checkpoint("typed-format")
    txt = lab.body_doc_parts(0)[0]
    first = txt.split(")")[0]
    assert first.startswith("[X ("), txt
    assert f"font={family}" in first, txt
    assert f"size={base + 2}" in first, txt
    assert lab.w._ribbon._font_combo.currentFont().family() == family
    assert lab.w._ribbon._current_size_px() == base + 2


def test_refreshing_a_card_keeps_the_pane_font_and_layout(tmp_path):
    """A display-box refresh (format fan-out, card switch) must not fall
    back to the application font: the card text stays the pane size."""
    from ui.widgets.lite_designer.slide_cards import display_text_px

    lab = _lab(tmp_path)
    box = lab.w._cards[0]._display_box
    before = _box_visual(box)
    px = display_text_px()
    assert box.document().defaultFont().pixelSize() == px, \
        box.document().defaultFont().pixelSize()

    # Same visible words, new metadata: this takes the rebuild path, not
    # the identical-text early return.
    lab.w._slides[0]["text"] = (
        "[Amazing (size=40)] grace how sweet\nthe sound")
    lab.w._refresh_card_states()
    lab.settle()

    after = _box_visual(box)
    assert after["text"] == before["text"], (after["text"], before["text"])
    assert after["line_w"] == before["line_w"], (after["line_w"], before["line_w"])
    assert box.document().defaultFont().pixelSize() == px, \
        box.document().defaultFont().pixelSize()


def test_live_editor_document_keeps_the_pane_font(tmp_path):
    """Loading another slide's document must not shrink the live editor
    to the application font."""
    lab = _lab(tmp_path)
    lab.focus_text(0)
    edit = lab.w._edit
    assert edit.document().defaultFont().pixelSize() == edit.font().pixelSize()
    lab.focus_text(1)
    assert edit.document().defaultFont().pixelSize() == edit.font().pixelSize()


def test_designer_is_a_tool_window_not_a_popup(tmp_path):
    """Qt.Popup surfaces are dismissed by the compositor on outside
    focus (screenshots) and can strand the app's input grab. The editor
    must be a frameless tool window with no popup grab."""
    lab = _lab(tmp_path)
    # Tool shares the Popup bit by definition; the type mask is what
    # decides whether the compositor makes it an xdg_popup.
    assert lab.w.windowType() == _Qt.WindowType.Tool, lab.w.windowType()


def test_tier3_size_fan_out_keeps_every_card_at_pane_size(tmp_path):
    """The exact reported flow: a tier-3 size change across a section run
    must not resize any display textbox (mixed sizes on screen)."""
    from ui.widgets.lite_designer.slide_cards import display_text_px

    deck = "# T\n\n\n*1\nOne\n\n\nTwo\n\n\nThree\n"
    lab = _lab(tmp_path, deck)
    lab.focus_text(1)
    before = {i: _box_visual(lab.w._cards[i]._display_box)
              for i in range(3)}
    assert lab.w._sel_tier == 0

    # This deck's active slide has no own section chip text, so the
    # Ctrl+A ladder skips tier 2 (0 -> 1 -> 3); two taps is tier 3.
    lab.select_all_tier(2)
    assert lab.w._sel_tier == 3
    lab.w._ribbon._size_combo.setCurrentText("42")
    lab.w._ribbon._on_size_typed()
    lab.settle()

    for i in range(3):
        assert "size=42" in lab.body_doc_parts(i)[0], \
            (i, lab.body_doc_parts(i)[0])

    lab.click_card(0)                 # refresh/switch every display box
    lab.settle()
    px = display_text_px()
    for i in range(3):
        box = lab.w._cards[i]._display_box
        assert box.document().defaultFont().pixelSize() == px, \
            (i, box.document().defaultFont().pixelSize())
        assert box.document().defaultFont().family() == box.font().family(), \
            (i, box.document().defaultFont().family(), box.font().family())
        assert _box_visual(box)["line_w"] == before[i]["line_w"], \
            (i, _box_visual(box)["line_w"], before[i]["line_w"])
