"""
Ribbon shows the EFFECTIVE formatting on load: the theme's display
baseline (weight → B, text_shadow → outline, text_transform → case,
text_align → alignment) with the deck's own run props taking precedence,
and toggles still round-trip as explicit deck overrides.

NOTE: no processEvents() anywhere in this file. A bare FormatRibbon
(whose row 1 holds a QFontComboBox) aborts the offscreen Qt plugin when
events are pumped — a pre-existing environment quirk, reproducible on
an unmodified tree. Every assertion here reads synchronously-set button
state, so the event loop is not needed.
"""

import os

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6.QtWidgets import QApplication, QTextEdit
from PyQt6.QtGui import QTextCursor
import pytest

from ui.widgets.lite_designer.rich_txt import (
    OUTLINE_PROP, OUTLINE_OFF, SHADOW_PROP, SHADOW_OFF)

_RIBBONS = []


@pytest.fixture(scope="module")
def qapp():
    """QApplication must exist BEFORE any widget is constructed (Qt
    aborts otherwise). Module-scoped, like the other designer tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication(["test"])
    return app


@pytest.fixture(autouse=True)
def _close():
    yield
    # Detach editors from ribbons before anything is destroyed: a ribbon
    # holding a deleted QTextEdit segfaults on teardown.
    for r in _RIBBONS:
        try:
            r.set_editor(None)
        except RuntimeError:
            pass
    _RIBBONS.clear()


def _ribbon(theme_defaults=None):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = FormatRibbon()
    _RIBBONS.append(r)
    if theme_defaults is not None:
        r.set_theme_defaults(theme_defaults)
    return r


def _editor(text="Amen, amen", select=4):
    e = QTextEdit()
    e.setPlainText(text)
    c = e.textCursor()
    c.setPosition(0)
    c.setPosition(select, QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(c)
    return e


# ─── theme → defaults mapping ──────────────────────────────────────────────

def test_slides_theme_maps_to_bold_without_outline(qapp):
    """The slides theme is bold with a soft shadow and NO outline, so the
    ribbon must show B lit and Outline off with nothing focused. The theme
    outline stays a VALUE ("Npx #hex") when set — the same property a deck's
    outline= sets — so the size box can show its thickness."""
    import core.theme_loader as tl
    d = tl.display_format_defaults(tl.get_theme("slides"))
    assert d["bold"] is True
    assert "outline" not in d
    assert d["case"] == "upper"
    assert d["align"] == "center"
    # ...while a theme that does declare one surfaces the value itself.
    d2 = tl.display_format_defaults({"text": {"text_outline": "3px #123456"}})
    assert d2["outline"] == "3px #123456"


def test_defaults_absent_keys_mean_no_opinion(qapp):
    import core.theme_loader as tl
    # None / no text block / no opinion keys → empty
    assert tl.display_format_defaults(None) == {}
    assert tl.display_format_defaults({}) == {}
    assert tl.display_format_defaults({"text": {}}) == {}
    # weight below 600 is not bold; "none" shadow is not an outline
    d = tl.display_format_defaults({"text": {"weight": 400,
                                            "text_shadow": "none"}})
    assert d["bold"] is False
    assert "outline" not in d


def test_weight_parses_css_values(qapp):
    import core.theme_loader as tl
    assert tl.display_format_defaults({"text": {"weight": 700}})["bold"] is True
    assert tl.display_format_defaults({"text": {"weight": "600"}})["bold"] is True
    assert tl.display_format_defaults({"text": {"weight": 500}})["bold"] is False


# ─── ribbon reflects the baseline ──────────────────────────────────────────

def test_ribbon_shows_theme_baseline_with_no_editor(qapp):
    r = _ribbon({"bold": True, "outline": True, "case": "upper",
                 "align": "center"})
    assert r._btn_bold.isChecked()
    assert r._btn_outline.isChecked()
    assert r._btn_upper.isChecked()
    assert r._align_btns["center"].isChecked()
    # Theme says nothing about these → stay off.
    assert not r._btn_italic.isChecked()
    assert not r._btn_underline.isChecked()


def test_plain_run_shows_no_theme_baseline(qapp):
    """A deck with no run props: buttons describe the caret, not the theme —
    plain text under the caret reads off even inside a fully-opinionated
    theme. (Theme truth still shows with no editor attached.)"""
    r = _ribbon({"bold": True, "outline": True})
    r.set_editor(_editor())
    assert not r._btn_bold.isChecked()
    assert not r._btn_outline.isChecked()


def test_run_prop_overrides_theme(qapp):
    """An explicit run weight wins over the theme baseline."""
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon({"bold": True, "outline": True})
    e = _editor()
    e.setText("Amen, amen")
    c = e.textCursor()
    c.setPosition(0)
    c.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    f = QTextCharFormat()
    f.setFontWeight(400)
    c.mergeCharFormat(f)
    e.setTextCursor(c)
    r.set_editor(e)
    assert not r._btn_bold.isChecked()  # run says normal → B off


def test_no_theme_means_no_false_positives(qapp):
    r = _ribbon({})
    r.set_editor(_editor())
    assert not r._btn_bold.isChecked()
    assert not r._btn_outline.isChecked()
    assert not r._btn_upper.isChecked()


# ─── toggles still round-trip as deck overrides ────────────────────────────

def test_bold_toggle_turns_theme_bold_off(qapp):
    """Clicking an unlit B writes explicit bold (never a no-op Normal): the
    toggle flips the run state the button shows, not the theme behind it.
    Clicking again writes explicit Normal. (clicked fires after the button
    flips, so the slot must read the run, not the button.)"""
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    r = _ribbon({"bold": True})
    e = _editor()
    r.set_editor(e)
    assert not r._btn_bold.isChecked()
    r._btn_bold.click()
    assert r._btn_bold.isChecked()
    assert "bold=true" in doc_to_txt(e.document())
    r._btn_bold.click()
    assert not r._btn_bold.isChecked()
    assert "bold=false" in doc_to_txt(e.document())


def test_bold_toggle_without_theme_is_unchanged(qapp):
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    r = _ribbon({})
    e = _editor()
    r.set_editor(e)
    assert not r._btn_bold.isChecked()
    r._btn_bold.click()
    assert r._btn_bold.isChecked()
    assert "bold=true" in doc_to_txt(e.document())
    r._btn_bold.click()
    assert not r._btn_bold.isChecked()
    assert "bold=false" in doc_to_txt(e.document())


def test_outline_button_visibility_follows_run_prop_only(qapp):
    """The colour swatch shows only for an explicit outline run (it has
    a colour to pick); a themed outline with plain text under the caret
    keeps the button off and the swatch hidden."""
    from PyQt6.QtGui import QTextCharFormat
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    r = _ribbon({"outline": True})
    e = _editor()
    r.set_editor(e)
    assert not r._btn_outline.isChecked()
    assert r._btn_outline_color.isHidden()
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "3px #123456")
    e.textCursor().mergeCharFormat(fmt)
    r.refresh_state()
    assert r._btn_outline.isChecked()
    assert not r._btn_outline_color.isHidden()

# ─── outline toggle / color / size ───────────────────────────────────────

def _outline_at(edit, pos=0):
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    cursor = edit.textCursor()
    cursor.setPosition(pos)
    return cursor.charFormat().property(OUTLINE_PROP)


def test_outline_toggle_off_marks_run_un_outlined(qapp):
    """Turning outline off must beat a theme baseline, so it writes the
    OUTLINE_OFF sentinel rather than clearing the property."""
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "1px #ff0000")
    e.textCursor().mergeCharFormat(fmt)
    r.refresh_state()
    assert r._btn_outline.isChecked()

    r._btn_outline.setChecked(False)
    r._on_outline_toggled()

    assert _outline_at(e) == OUTLINE_OFF
    assert not r._btn_outline.isChecked()


def test_outline_off_overrides_inherited_theme_outline(qapp):
    """The reported bug: a theme whose text_shadow outlines text re-asserted
    the outline on the next refresh, so the toggle snapped back on."""
    r = _ribbon(theme_defaults={"outline": True})
    e = _editor()
    # No editor attached yet: the ribbon shows theme truth (no caret).
    r.refresh_state()
    assert r._btn_outline.isChecked(), "theme outline must show as active"
    r.set_editor(e)
    # Caret placed in plain text: buttons describe the run, not the theme.
    r.refresh_state()
    assert not r._btn_outline.isChecked()

    r._btn_outline.setChecked(False)
    r._on_outline_toggled()

    assert _outline_at(e) == OUTLINE_OFF
    assert not r._btn_outline.isChecked(), "toggle snapped back to theme"
    # Still off after another refresh cycle (e.g. caret moved away/back).
    r.refresh_state()
    assert not r._btn_outline.isChecked()


def _caret(e, pos):
    from PyQt6.QtGui import QTextCursor
    cursor = e.textCursor()
    cursor.setPosition(pos)
    e.setTextCursor(cursor)  # fires cursorPositionChanged -> refresh_state


def test_caret_position_drives_all_states_despite_theme(qapp):
    """Buttons describe the caret's run, never the theme: with a fully
    opinionated theme and plain text under the caret, everything reads off.
    """
    r = _ribbon(theme_defaults={"bold": True, "case": "upper",
                                "align": "center",
                                "outline": "2px #000000"})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert not r._btn_bold.isChecked()
    assert not r._btn_upper.isChecked() and not r._btn_lower.isChecked()
    assert not any(b.isChecked() for b in r._align_btns.values())
    assert not r._btn_outline.isChecked()
    assert r._btn_outline_color.isHidden() and r._outline_size.isHidden()
    assert not r._btn_shadow.isChecked()


def test_caret_inside_explicit_runs_lights_each_axis(qapp):
    from PyQt6.QtGui import QTextCharFormat, QTextCursor, QTextFormat
    r = _ribbon(theme_defaults={"bold": True, "case": "upper",
                                "align": "center",
                                "outline": "2px #000000"})
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setFontWeight(700)
    cursor = e.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)
    _caret(e, 1)
    assert r._btn_bold.isChecked()
    _caret(e, 6)
    assert not r._btn_bold.isChecked()


def test_no_editor_still_shows_theme_truth(qapp):
    """Unchanged contract: with no caret anywhere, the ribbon shows what
    display will render."""
    r = _ribbon(theme_defaults={"bold": True, "case": "upper",
                                "align": "center",
                                "outline": "2px #000000"})
    r.refresh_state()
    assert r._btn_bold.isChecked()
    assert r._btn_upper.isChecked()
    assert r._align_btns["center"].isChecked()
    assert r._btn_outline.isChecked()


def test_bold_toggle_basis_is_the_run(qapp):
    """Clicking B on plain text in a bold theme writes explicit Bold (not a
    no-op Normal), and clicking again writes explicit Normal."""
    from PyQt6.QtGui import QTextFormat
    r = _ribbon(theme_defaults={"bold": True})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert not r._btn_bold.isChecked()
    r._toggle_bold()
    cursor = e.textCursor()
    cursor.setPosition(1)
    assert cursor.charFormat().fontWeight() >= 600
    assert r._btn_bold.isChecked()
    r._toggle_bold()
    cursor = e.textCursor()
    cursor.setPosition(1)
    assert cursor.charFormat().fontWeight() < 600
    assert not r._btn_bold.isChecked()


def test_outline_toggle_on_after_off_restores_stroke(qapp):
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_outline.setChecked(True)
    r._on_outline_toggled()
    r._btn_outline.setChecked(False)
    r._on_outline_toggled()
    assert _outline_at(e) == OUTLINE_OFF

    r.set_outline_color("#0000ff")
    r._btn_outline.setChecked(True)
    r._on_outline_toggled()

    value = _outline_at(e)
    assert value and value != OUTLINE_OFF
    assert "#0000ff" in value


def test_outline_off_keeps_selection(qapp):
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_outline.setChecked(True)
    r._on_outline_toggled()
    assert e.textCursor().hasSelection()

    r._btn_outline.setChecked(False)
    r._on_outline_toggled()

    assert e.textCursor().hasSelection(), "toggling off dropped the selection"


def test_outline_off_is_serialized_as_outline_none(qapp):
    """Toggling off has to REACH the display, otherwise the theme's outline
    reasserts itself there and the toggle looks broken."""
    from core.slide_parser import inline_markup_to_html
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_outline.setChecked(False)
    r._on_outline_toggled()
    assert _outline_at(e) == OUTLINE_OFF

    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    txt = doc_to_txt(e.document())
    assert "outline=none" in txt, txt
    # and the rendered run actively drops any inherited outline/shadow
    assert "text-shadow:none" in inline_markup_to_html(txt)


def _shadow_at(edit, pos=0):
    from ui.widgets.lite_designer.rich_txt import SHADOW_PROP
    cursor = edit.textCursor()
    cursor.setPosition(pos)
    return cursor.charFormat().property(SHADOW_PROP)


def test_shadow_toggle_applies_size_opacity_distance(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_shadow.setChecked(True)
    r._on_shadow_toggled()
    assert _shadow_at(e) == "8px 100% 0px #000000 45"

    r.set_shadow_color("#ff0000")
    assert _shadow_at(e) == "8px 100% 0px #ff0000 45"
    r._shadow_opacity.setValue(40)
    assert _shadow_at(e) == "8px 40% 0px #ff0000 45"
    r._shadow_distance.setValue(3)
    assert _shadow_at(e) == "8px 40% 3px #ff0000 45"
    r._shadow_angle.setValue(135)
    assert _shadow_at(e) == "8px 40% 3px #ff0000 135"
    r._shadow_size.setValue(10)
    assert _shadow_at(e) == "10px 40% 3px #ff0000 135"
    # over-max entries clamp to the max instead of sticking.
    from core.constants import SHADOW_SIZE_MAX_PX
    r._shadow_size.setValue(SHADOW_SIZE_MAX_PX + 500)
    assert _shadow_at(e) == f"{SHADOW_SIZE_MAX_PX}px 40% 3px #ff0000 135"


def test_shadow_controls_keep_the_runs_own_color(qapp):
    """Changing size/opacity/distance must not reset the color to the default."""
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_shadow.setChecked(True)
    r._on_shadow_toggled()
    r.set_shadow_color("#00ff00")
    r._shadow_size.setValue(12)
    assert "#00ff00" in _shadow_at(e), _shadow_at(e)
    r._shadow_opacity.setValue(75)
    assert _shadow_at(e) == "12px 75% 0px #00ff00 45", _shadow_at(e)


def test_shadow_toggle_off_serializes_as_none(qapp):
    from core.slide_parser import inline_markup_to_html
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_shadow.setChecked(True)
    r._on_shadow_toggled()
    r._btn_shadow.setChecked(False)
    r._on_shadow_toggled()
    assert _shadow_at(e) == SHADOW_OFF
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    txt = doc_to_txt(e.document())
    assert "shadow=none" in txt, txt
    assert "text-shadow:none" in inline_markup_to_html(txt)


def test_shadow_refresh_state_reads_the_run(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setProperty(SHADOW_PROP, "6px 30% 2px #123456 45")
    e.textCursor().mergeCharFormat(fmt)
    r.refresh_state()
    assert r._btn_shadow.isChecked()
    assert (r._shadow_size.value(), r._shadow_opacity.value(),
            r._shadow_distance.value(),
            r._shadow_angle.value()) == (6, 30, 2, 45)
    assert r._shadow_color == "#123456"


def _outline_color_at(edit, pos=0):
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    cursor = edit.textCursor()
    cursor.setPosition(pos)
    return cursor.charFormat().property(OUTLINE_PROP)


def test_outline_color_button_opens_inline_picker_not_a_dialog(qapp):
    """The designer is a Popup: a modal QColorDialog would deactivate and
    close it on every click, so picking must never open a window."""
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    assert r._color_bar.isHidden()
    r._btn_outline_color.clicked.emit()
    assert not r._color_bar.isHidden()
    assert r._color_target == "outline"
    # clicking the same button again hides the bar
    r._btn_outline_color.clicked.emit()
    assert r._color_bar.isHidden()


def test_outline_swatch_pick_applies_and_hides(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_outline.setChecked(True)
    r._on_outline_toggled()
    r._btn_outline_color.clicked.emit()
    r._pick_color("#ff0000")
    assert "#ff0000" in (_outline_color_at(e) or "")
    assert r._color_bar.isHidden()


def test_hex_entry_validates_before_applying(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_outline.setChecked(True)
    r._on_outline_toggled()
    r._btn_outline_color.clicked.emit()
    before = _outline_color_at(e)
    r._hex_edit.setText("not a color")
    r._on_hex_entered()
    assert _outline_color_at(e) == before
    assert not r._color_bar.isHidden(), "invalid hex must not dismiss the bar"
    r._hex_edit.setText("#0f0")
    r._on_hex_entered()
    assert "#00ff00" in (_outline_color_at(e) or "")


def test_color_target_switching(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import COLOR_PROP
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._btn_shadow_color.clicked.emit()
    assert r._color_target == "shadow"
    r._btn_color.clicked.emit()
    assert r._color_target == "text"
    assert not r._color_bar.isHidden()
    r._pick_color("#123456")
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(COLOR_PROP) == "#123456"


def test_outline_color_change_applies_to_selection(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP, OUTLINE_OFF
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "1px #ff0000")
    e.textCursor().mergeCharFormat(fmt)
    r._btn_outline.setChecked(True)
    r.set_outline_color("#00ff00")
    cursor = e.textCursor(); cursor.setPosition(0)
    assert cursor.charFormat().property(OUTLINE_PROP) == "1px #00ff00", (
        f"got {cursor.charFormat().property(OUTLINE_PROP)!r}")


def test_outline_size_change_updates_prop_and_clamped(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "1px #ff0000")
    e.textCursor().mergeCharFormat(fmt)
    r._btn_outline.setChecked(True)
    r._outline_size.setValue(12)
    cursor = e.textCursor(); cursor.setPosition(0)
    assert cursor.charFormat().property(OUTLINE_PROP) == "12px #ff0000", (
        f"got {cursor.charFormat().property(OUTLINE_PROP)!r}")


def test_outline_controls_show_with_outline(qapp):
    from PyQt6.QtGui import QTextCharFormat
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    r = _ribbon({"outline": True})
    e = _editor()
    r.set_editor(e)
    # Plain text under the caret: button off, controls hidden.
    assert not r._btn_outline.isChecked()
    assert r._btn_outline_color.isHidden()
    assert r._outline_size.isHidden()
    # With an explicit run prop the button is lit and the color+size
    # controls are visible while active.
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "3px #123456")
    e.textCursor().mergeCharFormat(fmt)
    r._btn_outline.setChecked(True)
    r.refresh_state()
    assert not r._btn_outline_color.isHidden()
    assert not r._outline_size.isHidden()


def test_outline_size_spinbox_clamps(qapp):
    """The spin box tracks OUTLINE_MIN_PX..OUTLINE_MAX_PX: a wide outline has
    to be enterable (it is padded into the SVG viewport, not clipped)."""
    from core.constants import OUTLINE_MAX_PX, OUTLINE_MIN_PX
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP

    r = _ribbon({"outline": True})
    r.set_editor(_editor())
    r._btn_outline.setChecked(True)
    assert (r._outline_size.minimum(), r._outline_size.maximum()) == (
        OUTLINE_MIN_PX, OUTLINE_MAX_PX), (
            OUTLINE_MIN_PX, OUTLINE_MAX_PX)
    r._outline_size.setValue(OUTLINE_MAX_PX)
    assert r._outline_size.value() == OUTLINE_MAX_PX
    r._outline_size.setValue(OUTLINE_MAX_PX + 500)
    # QSpinBox clamps to its max, and the merge uses that max.
    assert r._outline_size.value() == OUTLINE_MAX_PX
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    assert f"outline={OUTLINE_MAX_PX}px" in doc_to_txt(r._edit.document()), (
        doc_to_txt(r._edit.document()))
    assert r._edit.textCursor().charFormat().property(OUTLINE_PROP)


def test_outline_controls_hide_when_outline_off(qapp):
    r = _ribbon()
    r.set_editor(_editor())
    r._btn_outline.setChecked(False)
    r.refresh_state()
    assert r._btn_outline_color.isHidden()
    assert r._outline_size.isHidden()
