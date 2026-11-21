"""ui/theme_kit/border_editor.py — the Border surface behaves like one editor.

Three reports against the running Theme Designer are pinned here, plus the two
that came before them:

* the popover disappeared after the first edit, so a border could never be
  finished in one visit — ``_BorderPopover._on_committed`` emitted the value
  and then called ``close()``. It now writes through and closes only on
  dismissal, like the colour, paint and shadow surfaces;
* ``None`` did not stick: the switch was a preview only, so dismissing the
  popover rewound the field to the border it opened with. A switch commits;
* a side drag was not live-previewed: the preview was composed from the
  committed model, which does not know the in-flight override;
* clicking a side reset the base row to the defaults, because the row was
  rewritten from the value the popover opened with instead of the fields;
* a base edit made while a side was selected froze the seeded side values
  into ``sides``, and a side colour pick never left the popover.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import Qt

from ui.theme_kit.border_editor import BorderField, _BorderPopover
from ui.theme_kit.shadow_editor import ShadowField

VALUE = "6px solid rgba(255, 255, 255, 0.8)"


@pytest.fixture(scope="module")
def app():
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def _field(app, value=VALUE) -> BorderField:
    field = BorderField(value)
    field.resize(180, 28)
    field.show()
    app.processEvents()
    field._open_popover()
    # No event-loop turn while the popup is open: the offscreen platform
    # deactivates a Qt.Popup on the first pass, which is not this behaviour.
    return field


def _spy_close(popover):
    """Record close() calls without hiding the platform path."""
    calls = []
    original = popover.close

    def close():
        calls.append(True)
        original()

    popover.close = close
    return calls


# ── the reported bug ────────────────────────────────────────────────────────

def test_first_border_edit_keeps_the_popover_open(app):
    field = _field(app)
    popover = field._popover
    assert isinstance(popover, _BorderPopover)
    closes = _spy_close(popover)

    popover.editor.width_field.set_value("14", emit=True)

    assert not closes, "the first committed field closed the surface"
    assert popover.isVisible(), "the popover vanished on the first edit"
    assert field.value()["width"] == 14, "the edit did not reach the field"
    field.close()


def test_every_border_field_is_reachable_in_one_visit(app):
    """Width, style, colour and a side override, without reopening."""
    field = _field(app, "none")
    popover = field._popover
    editor = popover.editor
    closes = _spy_close(popover)
    seen = []
    field.changed.connect(seen.append)

    editor.mode.set_value("custom", emit=True)
    editor.width_field.set_value("4", emit=True)
    editor.style_dropdown.set_value("dashed")
    editor._emit_commit()
    editor.color_field.set_value("#ff0000", emit=True)

    assert not closes, "a field edit took the surface down mid-edit"
    assert popover.isVisible()
    assert len(seen) >= 3, f"edits were swallowed: {seen}"
    last = seen[-1]
    assert last["width"] == 4 and last["style"] == "dashed"
    assert last["color"] == "#ff0000", last
    field.close()


def test_dismissing_after_editing_is_not_a_cancel(app):
    field = _field(app)
    popover = field._popover
    cancels = []
    popover.cancelled.connect(lambda: cancels.append(True))

    popover.editor.width_field.set_value("10", emit=True)
    committed = field.value()
    popover.close()

    assert cancels == [], "closing after an edit rewound it like an Escape"
    assert field.value() == committed, "the committed border was reverted"
    field.close()


def test_choosing_none_commits_and_survives_the_dismissal(app):
    """Reported: the border came back once the popover was closed.

    ``None`` only ever emitted a preview, so the dismiss rewound the field to
    the border the popover opened with. The switch commits now that a commit
    keeps the surface open.
    """
    field = _field(app, "14px dotted")
    popover = field._popover
    editor = popover.editor
    seen = []
    field.changed.connect(seen.append)

    editor.mode.set_value("none", emit=True)

    assert seen and seen[-1] == "none", seen
    assert field.value() == "none"
    popover.close()
    assert field.value() == "none", "the dismiss resurrected the border"
    field.close()


def test_a_drag_that_never_committed_is_still_rewound(app):
    """Cancel semantics are kept for an in-flight value."""
    field = _field(app, VALUE)
    popover = field._popover
    editor = popover.editor
    cancels = []
    popover.cancelled.connect(lambda: cancels.append(True))

    # Mid-drag: the field advanced, nothing committed yet.
    editor.width_field.set_value("22")
    editor._emit_preview()
    popover.close()

    assert cancels, "an uncommitted drag was treated as a commit"
    assert field.value() == VALUE, "the in-flight value outlived its dismissal"
    field.close()


# ── the reported side bugs ──────────────────────────────────────────────────

def test_a_side_colour_pick_commits_the_side_spec(app):
    """A side colour must reach the value, not just the swatch.

    Reported against the running Theme Designer: the side colour field showed
    ``#ffffff`` while the theme kept ``currentColor``, so the side kept
    painting black. The pick goes through the colour popover's preview and
    release callbacks, which is where the commit used to be swallowed.
    """
    field = _field(app, "15px solid")
    editor = field._popover.editor
    seen = []
    field.changed.connect(seen.append)

    editor.set_editing_side("bottom")
    editor.side_width.set_value("33", emit=True)
    editor.side_style.set_value("dotted")
    editor._emit_side_commit()
    editor.side_color._on_popover_preview("#ffffff")
    editor.side_color._on_popover_committed("#ffffff")

    assert seen, "the side colour never committed"
    assert seen[-1]["sides"]["bottom"] == {
        "width": 33, "style": "dotted", "color": "#ffffff"}, seen[-1]
    # The base is untouched by a side edit.
    assert (seen[-1]["width"], seen[-1]["style"]) == (15, "solid")
    assert seen[-1]["color"] == "currentColor"
    field.close()


def test_a_base_edit_does_not_freeze_a_side_override(app):
    """Selecting a side seeds its row; a base edit must not write that row.

    Every field used to route through one commit handler, so editing the base
    while a side was selected stored the seeded side values (the *old* base
    width, plus an always-present colour) as an override — the side then
    stopped following the base.
    """
    field = _field(app, "15px solid")
    editor = field._popover.editor

    editor.set_editing_side("bottom")
    editor.width_field.set_value("20", emit=True)

    value = field.value()
    assert value["width"] == 20, value
    assert "sides" not in value, f"a base edit invented a side override: {value}"
    field.close()


def test_selecting_a_side_without_changing_it_adds_no_override(app):
    field = _field(app, "15px solid")
    editor = field._popover.editor
    seen = []
    field.changed.connect(seen.append)

    editor.set_editing_side("bottom")
    editor._emit_side_commit()

    assert seen, "the commit was swallowed"
    assert "sides" not in seen[-1], seen[-1]
    field.close()


def test_a_side_keeps_inheriting_a_changed_base_colour(app):
    """An untouched side colour follows the base instead of pinning it."""
    field = _field(app, "15px solid")
    editor = field._popover.editor

    editor.set_editing_side("bottom")
    editor.side_width.set_value("33", emit=True)
    editor.color_field.set_value("#ff0000", emit=True)

    value = field.value()
    assert value["color"] == "#ff0000", value
    assert value["sides"]["bottom"] == {"width": 33}, value
    field.close()


def test_clicking_a_side_keeps_the_base_row_as_edited(app):
    """Reported: selecting a side reset the base row to the defaults.

    ``_sync_fields`` rewrote the base fields from ``_base`` — the value the
    popover opened with — so a border opened as "none" showed 1px / Solid /
    currentColor the moment a side was clicked. The document was right; the
    row was not, and the side row was seeded from those stale numbers.
    """
    field = _field(app, "none")
    editor = field._popover.editor
    editor.mode.set_value("custom", emit=True)
    editor.width_field.set_value("14", emit=True)
    editor.style_dropdown.set_value("dotted")
    editor._emit_commit()

    editor.set_editing_side("right")

    assert editor.width_field.numeric_value() == 14
    assert editor.style_dropdown.value() == "dotted"
    # …and the side row starts from what the operator sees, not from defaults.
    assert editor.side_width.numeric_value() == 14
    assert editor.side_style.value() == "dotted"
    field.close()


def test_a_side_drag_previews_the_override(app):
    """Reported: a side edit was not live-previewed like every other edit.

    A drag updates the fields, not the model: ``_side_specs`` only learns the
    override on release, so a preview composed from it dropped the side and
    the renderer kept painting the old border until the release.
    """
    field = _field(app, "10px solid")
    editor = field._popover.editor
    previews = []
    editor.preview.connect(previews.append)

    editor.set_editing_side("bottom")
    editor.side_width.begin_scrub()
    editor.side_width.scrub_to(18)
    dragged = editor.side_width.numeric_value()

    assert dragged != 10, "the scrub did not move the side width"
    assert previews, "a side drag emitted no preview"
    assert previews[-1]["sides"]["bottom"]["width"] == dragged, previews[-1]

    editor.side_width.end_scrub()
    assert field.value()["sides"]["bottom"]["width"] == dragged, field.value()
    field.close()


# ── the same contract on the other multi-field popover ──────────────────────

def test_shadow_edit_keeps_its_popover_open(app):
    """Parity check: the shadow surface never adopted close-on-commit."""
    field = ShadowField("0px 4px 12px rgba(0, 0, 0, 0.6)", structured=True)
    field.resize(180, 28)
    field.show()
    app.processEvents()
    field._open_popover()
    popover = field._popover
    assert popover is not None
    closes = _spy_close(popover)

    popover.editor._rows[0].x.set_value(18, emit=True)

    assert not closes and popover.isVisible()
    assert str(field.value()).startswith("18px"), field.value()
    field.close()
