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


def _mem_store(saved=None):
    """In-memory recent-colors store: suites never touch the dev DB."""
    box = {"saved": saved if saved is not None else []}

    def load():
        return list(box["saved"])

    def save(colors):
        box["saved"] = list(colors)

    return (load, save), box


def _ribbon(theme_defaults=None, store=None):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    if store is None:
        store, _box = _mem_store()
    r = FormatRibbon(recent_store=store)
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

def test_slides_theme_maps_to_bold_with_outline(qapp):
    """The slides theme is bold with a 6px black outline and no shadow, so
    the ribbon must show B lit and the outline value surfaced — the theme
    outline stays a VALUE ("Npx #hex") when set, the same property a
    deck's outline= sets, so the size box can show its thickness."""
    import core.theme_loader as tl
    d = tl.display_format_defaults(tl.get_theme("slides"))
    assert d["bold"] is True
    assert d["outline"] == "6px #000000"
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


def test_plain_run_shows_effective_theme_state(qapp):
    """Buttons show what display renders: plain text under the caret in a
    fully-opinionated theme reads ON for every themed axis."""
    r = _ribbon({"bold": True, "outline": "2px #000000"})
    r.set_editor(_editor())
    assert r._btn_bold.isChecked()
    assert r._btn_outline.isChecked()


def test_run_prop_overrides_theme(qapp):
    """An explicit run weight wins over the theme baseline."""
    from PyQt6.QtGui import QTextCharFormat
    r = _ribbon({"bold": True, "outline": "2px #000000"})
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
    _caret(e, 1)
    assert not r._btn_bold.isChecked()  # run says normal → B off


def test_no_theme_means_no_false_positives(qapp):
    r = _ribbon({})
    r.set_editor(_editor())
    assert not r._btn_bold.isChecked()
    assert not r._btn_outline.isChecked()
    assert not r._btn_upper.isChecked()


# ─── toggles still round-trip as deck overrides ────────────────────────────

def test_bold_toggle_turns_theme_bold_off(qapp):
    """Clicking a lit B writes explicit Normal (never a redundant Bold):
    the toggle flips the EFFECTIVE state the button shows, so the first
    click on theme-bold text always does something visible. Clicking
    again writes explicit Bold."""
    from ui.widgets.lite_designer.rich_txt import doc_to_txt
    r = _ribbon({"bold": True})
    e = _editor()
    r.set_editor(e)
    assert r._btn_bold.isChecked()
    r._btn_bold.click()
    assert not r._btn_bold.isChecked()
    assert "bold=false" in doc_to_txt(e.document())
    r._btn_bold.click()
    assert r._btn_bold.isChecked()
    assert "bold=true" in doc_to_txt(e.document())


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


def test_outline_knobs_show_effective_params(qapp):
    """A themed outline lights the button AND shows its params in the
    knobs (theme color/size, not stale picks); an explicit run outline
    shows the run's own. Either way the first knob touch seeds a run
    override from what is shown."""
    from PyQt6.QtGui import QTextCharFormat
    from ui.widgets.lite_designer.rich_txt import OUTLINE_PROP
    r = _ribbon({"outline": "4px #123456"})
    e = _editor()
    r.set_editor(e)
    assert r._btn_outline.isChecked()
    assert not r._btn_outline_color.isHidden()
    assert r._outline_size.value() == 4
    assert "#123456" in r._btn_outline_color.styleSheet()
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "3px #654321")
    e.textCursor().mergeCharFormat(fmt)
    r.refresh_state()
    assert r._outline_size.value() == 3
    assert "#654321" in r._btn_outline_color.styleSheet()

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
    """A theme outline lights the button on plain text (effective state);
    switching it off writes the OUTLINE_OFF sentinel, which keeps it off
    across refreshes instead of snapping back to the theme."""
    r = _ribbon(theme_defaults={"outline": "2px #000000"})
    e = _editor()
    # No editor attached yet: the ribbon shows theme truth (no caret).
    r.refresh_state()
    assert r._btn_outline.isChecked(), "theme outline must show as active"
    r.set_editor(e)
    # Plain text under the caret still reads ON: the theme outlines it.
    r.refresh_state()
    assert r._btn_outline.isChecked()

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
    if cursor.position() == pos and not cursor.hasSelection():
        # Same spot fires no cursorPositionChanged: step away first so
        # the ribbon always re-reads (stale buttons otherwise).
        cursor.setPosition(0 if pos != 0 else e.document().characterCount() - 1)
        e.setTextCursor(cursor)
        cursor = e.textCursor()
    cursor.setPosition(pos)
    e.setTextCursor(cursor)  # fires cursorPositionChanged -> refresh_state


def test_caret_position_drives_effective_states(qapp):
    """Buttons show what display renders at the caret: with a fully
    opinionated theme and plain text under the caret, everything themed
    reads on. The shadow swatch stays hidden — no run carries a shadow
    to edit."""
    r = _ribbon(theme_defaults={"bold": True, "case": "upper",
                                "align": "center",
                                "outline": "2px #000000"})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert r._btn_bold.isChecked()
    assert r._btn_upper.isChecked() and not r._btn_lower.isChecked()
    assert r._align_btns["center"].isChecked()
    assert r._btn_outline.isChecked()
    assert not r._btn_outline_color.isHidden()
    assert r._outline_size.value() == 2
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
    # Outside the explicit run the theme still bolds: effective stays on.
    assert r._btn_bold.isChecked()


def test_explicit_normal_run_reads_off_inside_bold_theme(qapp):
    """The other direction: an explicit bold=false run under a bold theme
    reads OFF — the run wins, and the toggle would flip it back on."""
    from PyQt6.QtGui import QTextCharFormat, QTextCursor
    r = _ribbon(theme_defaults={"bold": True})
    e = _editor()
    r.set_editor(e)
    fmt = QTextCharFormat()
    fmt.setFontWeight(400)
    cursor = e.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)
    _caret(e, 1)
    assert not r._btn_bold.isChecked()


def test_deck_format_beats_theme(qapp):
    """Top-script is the middle of the chain: deck False beats theme True,
    and deck values light outline/chip/size with no run props at all."""
    r = _ribbon({"bold": True, "outline": "2px #000000", "color": "#ffffff",
                 "size": 62})
    r.set_editor(_editor())
    assert r._btn_bold.isChecked()
    r.set_deck_format({"bold": False, "outline": "3px #123456",
                       "color": "#00ff00", "size_nominal": 42})
    assert not r._btn_bold.isChecked()
    assert r._btn_outline.isChecked()
    assert "#00ff00" in r._color_chip.styleSheet()
    assert r._size_combo.currentText() == "42"


def test_run_beats_deck_beats_theme(qapp):
    """Full chain in one: theme says bold, deck says not, run says bold —
    the run wins. Clear the run override and the deck shows through."""
    from PyQt6.QtGui import QTextCharFormat, QTextCursor
    r = _ribbon({"bold": True})
    r.set_deck_format({"bold": False})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert not r._btn_bold.isChecked()
    fmt = QTextCharFormat()
    fmt.setFontWeight(700)
    cursor = e.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)
    _caret(e, 1)
    assert r._btn_bold.isChecked()


def test_deck_outline_none_kills_theme_outline(qapp):
    r = _ribbon({"outline": "2px #000000"})
    r.set_editor(_editor())
    assert r._btn_outline.isChecked()
    r.set_deck_format({"outline": "none"})
    assert not r._btn_outline.isChecked()
    r.set_deck_format({})
    assert r._btn_outline.isChecked()


def test_italic_underline_strike_follow_effective(qapp):
    """Deck true lights each axis with no run props; an explicit run
    false beats the deck."""
    from PyQt6.QtGui import QTextCharFormat, QTextCursor
    from ui.widgets.lite_designer.rich_txt import UL_PROP, SO_PROP
    r = _ribbon({})
    r.set_deck_format({"italics": True, "underline": True, "strike": True})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert r._btn_italic.isChecked()
    assert r._btn_underline.isChecked()
    assert r._btn_strike.isChecked()
    fmt = QTextCharFormat()
    fmt.setProperty(UL_PROP, False)
    fmt.setProperty(SO_PROP, False)
    cursor = e.textCursor()
    cursor.setPosition(0)
    cursor.setPosition(4, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)
    _caret(e, 1)
    assert not r._btn_underline.isChecked()
    assert not r._btn_strike.isChecked()
    assert r._btn_italic.isChecked()


def test_theme_shadow_and_size_defaults(qapp):
    """display_format_defaults carries what the ribbon needs: a genuine
    shadow rides as a value, a consumed ring collapses to nothing, and
    size parses to int px."""
    import core.theme_loader as tl
    assert tl.display_format_defaults(
        {"text": {"text_shadow": "0 4px 12px rgba(0, 0, 0, 0.4)"}}
    )["shadow"] == "0 4px 12px rgba(0, 0, 0, 0.4)"
    assert tl.display_format_defaults(
        {"text": {"text_shadow": "none"}})["shadow"] == "none"
    hard = ("-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, "
            "2px 2px 0 #000, -2px 0 0 #000, 2px 0 0 #000, "
            "0 -2px 0 #000, 0 2px 0 #000")
    d = tl.display_format_defaults({"text": {"text_shadow": hard}})
    assert d["outline"] == "2px #000000"
    assert "shadow" not in d
    assert tl.display_format_defaults({"text": {}}).get("shadow") is None
    assert tl.display_format_defaults({"text": {"size": "62px"}})["size"] == 62


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


def test_bold_toggle_basis_is_the_effective_state(qapp):
    """Clicking B on theme-bold text writes explicit Normal (visible
    change), and clicking again writes explicit Bold."""
    from PyQt6.QtGui import QTextFormat
    r = _ribbon(theme_defaults={"bold": True})
    e = _editor()
    r.set_editor(e)
    _caret(e, 1)
    assert r._btn_bold.isChecked()
    r._toggle_bold()
    cursor = e.textCursor()
    cursor.setPosition(1)
    assert cursor.charFormat().fontWeight() < 600
    assert not r._btn_bold.isChecked()
    r._toggle_bold()
    cursor = e.textCursor()
    cursor.setPosition(1)
    assert cursor.charFormat().fontWeight() >= 600
    assert r._btn_bold.isChecked()


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


def test_shadow_knobs_seed_from_deck_without_run(qapp):
    """Deck shadow lights the button and fills the knobs; the first knob
    touch seeds an explicit run override from those (keeping the color),
    it never reverts to a stale pick."""
    from ui.widgets.lite_designer.rich_txt import SHADOW_PROP
    r = _ribbon({})
    r.set_deck_format({"shadow": "6px 30% 2px #123456 45"})
    e = _editor()
    r.set_editor(e)
    assert r._btn_shadow.isChecked()
    assert (r._shadow_size.value(), r._shadow_opacity.value(),
            r._shadow_distance.value(),
            r._shadow_angle.value()) == (6, 30, 2, 45)
    assert r._shadow_color == "#123456"
    r._shadow_size.setValue(10)
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(SHADOW_PROP) == \
        "10px 30% 2px #123456 45"


def test_outline_size_touch_seeds_run_override_from_effective(qapp):
    r = _ribbon({"outline": "4px #123456"})
    e = _editor()
    r.set_editor(e)
    r._outline_size.setValue(7)
    assert _outline_at(e) == "7px #123456"


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
    r = _ribbon({"outline": "2px #000000"})
    e = _editor()
    r.set_editor(e)
    # Plain text under the caret: effective ON (theme), and the colour
    # and size controls show the theme's params (edits seed a run
    # override from those, never a stale pick).
    assert r._btn_outline.isChecked()
    assert not r._btn_outline_color.isHidden()
    assert r._outline_size.value() == 2
    # With an explicit run prop the knobs show the run's own values.
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, "3px #123456")
    e.textCursor().mergeCharFormat(fmt)
    r._btn_outline.setChecked(True)
    r.refresh_state()
    assert r._outline_size.value() == 3
    assert not r._btn_outline_color.isHidden()


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


def test_display_defaults_include_theme_text_color(qapp):
    import core.theme_loader as tl
    assert tl.display_format_defaults(
        {"text": {"color": "#D4AF37"}})["color"] == "#d4af37"
    assert tl.display_format_defaults(
        {"containers": {"main": {"text": {"color": "#D4AF37"}}}}
    )["color"] == "#d4af37"
    assert "color" not in tl.display_format_defaults(
        {"text": {"color": "not-a-color"}})


def test_text_picker_opens_with_run_color(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import COLOR_PROP
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._apply_text_color("#123456")
    r._btn_color.clicked.emit()
    assert r._color_target == "text"
    assert not r._color_bar.isHidden()
    assert r._hex_edit.text() == "#123456"
    assert r._pending_color == "#123456"
    assert r._wheel.colorHex() == "#123456"


def test_text_picker_defaults_to_theme_color(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon({"color": "#d4af37"})
    r.set_editor(_editor())
    r._btn_color.clicked.emit()
    assert r._hex_edit.text() == "#d4af37"
    assert r._pending_color == "#d4af37"


def test_text_button_shows_effective_color(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon({"color": "#d4af37"})
    e = _editor()
    r.set_editor(e)
    assert "#d4af37" in r._color_chip.styleSheet()
    r._apply_text_color("#123456")
    assert "#123456" in r._color_chip.styleSheet()


def test_wheel_geometry_round_trip(qapp):
    from ui.widgets.lite_designer.format_ribbon import (
        _wheel_hue_sat_for_point, _wheel_point_for_hue_sat)
    cx = cy = 72.0
    radius = 64.0
    for hue in (0, 60, 120, 180, 240, 300):
        for sat in (32, 128, 255):
            x, y = _wheel_point_for_hue_sat(hue, sat, cx, cy, radius)
            got = _wheel_hue_sat_for_point(x, y, cx, cy, radius)
            assert got is not None
            assert abs((got[0] - hue + 180) % 360 - 180) <= 2
            assert abs(got[1] - sat) <= 2
    x, y = _wheel_point_for_hue_sat(123, 0, cx, cy, radius)
    assert _wheel_hue_sat_for_point(x, y, cx, cy, radius)[1] == 0
    assert _wheel_hue_sat_for_point(cx + radius + 10, cy, cx, cy, radius) is None
    assert _wheel_hue_sat_for_point(cx, cy, cx, cy, 0) is None


def test_wheel_preview_stages_then_apply_commits(qapp):
    from PyQt6.QtGui import QColor
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import COLOR_PROP
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._apply_text_color("#ff0000")
    r._btn_color.clicked.emit()
    expected = QColor.fromHsv(0, 255, 128).name()
    assert r._wheel._set_hsv(0, 255, 128, True) is True
    assert r._pending_color == expected
    assert r._hex_edit.text() == expected
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(COLOR_PROP) == "#ff0000"
    r._on_color_apply()
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(COLOR_PROP) == expected
    assert r._color_bar.isHidden()


def test_value_slider_stages_without_applying(qapp):
    from PyQt6.QtGui import QColor
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import COLOR_PROP
    r = _ribbon()
    e = _editor()
    r.set_editor(e)
    r._apply_text_color("#ff0000")
    r._btn_color.clicked.emit()
    expected = QColor.fromHsv(0, 255, 128).name()
    r._value_slider.setValue(128)
    assert r._pending_color == expected
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(COLOR_PROP) == "#ff0000"
    assert not r._color_bar.isHidden()


def test_apply_without_pending_keeps_picker_open(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    r.set_editor(_editor())
    r._btn_color.clicked.emit()
    r._pending_color = None
    r._on_color_apply()
    assert not r._color_bar.isHidden()
    assert r._color_target == "text"


def test_wheel_is_inline_child_not_a_window(qapp):
    from PyQt6.QtCore import Qt
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    r = _ribbon()
    r.set_editor(_editor())
    r._btn_color.clicked.emit()
    assert r._wheel.parent() is r._color_bar
    assert r._color_bar.parent() is r
    assert not (r._wheel.windowFlags() & Qt.WindowType.Window)


def test_recent_colors_record_dedupe_and_cap(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    store, box = _mem_store()
    r = _ribbon(store=store)
    r.set_editor(_editor())
    r._btn_color.clicked.emit()
    picks = [f"#{i:02x}0000" for i in range(12)]
    for hx in picks:
        r._pick_color(hx)
        # swatch picks hide the bar; reopen for the next pick
        r._btn_color.clicked.emit()
    assert r._recents == list(reversed(picks))[:10]
    assert box["saved"] == r._recents
    assert r._recent_chips.count() == 10
    # re-picking an old color moves it to the front, no duplicate
    r._pick_color(picks[0])
    assert r._recents[0] == picks[0]
    assert r._recents.count(picks[0]) == 1


def test_recent_colors_persist_across_ribbon_instances(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    store, _box = _mem_store(["#123456", "#abcdef"])
    r = _ribbon(store=store)
    assert r._recents == ["#123456", "#abcdef"]
    assert r._recent_chips.count() == 2


def test_recent_chip_click_reuses_color(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import COLOR_PROP
    store, _box = _mem_store(["#123456"])
    r = _ribbon(store=store)
    e = _editor()
    r.set_editor(e)
    r._btn_color.clicked.emit()
    chip = r._recent_chips.itemAt(0).widget()
    assert chip.toolTip() == "Reuse #123456"
    chip.clicked.emit()
    cursor = e.textCursor()
    cursor.setPosition(0)
    assert cursor.charFormat().property(COLOR_PROP) == "#123456"
    assert r._color_bar.isHidden()


def test_recent_load_failure_means_no_recents(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon

    def _boom():
        raise RuntimeError("no db")

    r = _ribbon(store=(_boom, lambda colors: None))
    assert r._recents == []
    assert r._recent_chips.count() == 0


def test_partial_clear_splits_formatted_run(qapp):
    """The user's example: clearing a middle highlight splits the run,
    keeping the format on both sides and plain text in the middle."""
    from PyQt6.QtGui import QTextCursor
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import doc_to_txt, txt_to_doc
    r = _ribbon()
    doc = txt_to_doc(
        "This is the text sample [I'm working with. I have to show you "
        "what I want. (color=#000000; bold=true)]")
    e = _editor()
    e.setDocument(doc)
    r.set_editor(e)
    cursor = e.textCursor()
    start = doc.toPlainText().find("I have to show you")
    cursor.setPosition(start)
    cursor.setPosition(start + len("I have to show you"),
                       QTextCursor.MoveMode.KeepAnchor)
    e.setTextCursor(cursor)
    r._btn_clear.clicked.emit()
    assert doc_to_txt(doc) == (
        "This is the text sample [I'm working with. "
        "(bold=true; color=#000000)] I have to show you "
        "[what I want. (bold=true; color=#000000)]")


def test_full_doc_clear_strips_all_inline_syntax(qapp):
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import (
        clear_char_formatting, doc_to_txt, txt_to_doc)
    doc = txt_to_doc(
        "This is the text sample [I'm working with. I have to show you "
        "what I want. (color=#000000; bold=true)]")
    clear_char_formatting(doc)
    assert doc_to_txt(doc) == (
        "This is the text sample I'm working with. "
        "I have to show you what I want.")
