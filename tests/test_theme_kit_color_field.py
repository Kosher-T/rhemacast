"""ui/theme_kit/color_field.py — the colour field's picker behaviour.

Three bugs reported against the running Theme Designer are pinned here:

* a theme default of ``transparent`` seeds the plane at alpha 0, so picking a
  hue produced ``#rrggbb00`` — an invisible "nothing happened" edit;
* ``PopupSurface`` is not deleted on close, so waiting for ``destroyed`` left
  the owner holding a stale popup and the second click never reopened it;
* a symbolic value (``@token`` / ``transparent``) was shown verbatim in the
  text field, but the field paints a colour.
"""

import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication

from ui.theme_kit.color_field import (
    ColorEditor, ColorField, display_color_text,
)
from ui.theme_kit.paint_field import PaintField, _describe

GOLD = "#d4af37"


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ── bug: a transparent value could not be painted ───────────────────────────

def test_picking_on_the_plane_resurrects_a_transparent_value(app):
    editor = ColorEditor("transparent", palette=[("Gold", GOLD)])
    editor.plane.resize(200, 104)
    editor.plane.set_color(QColor(0, 0, 0, 0))
    assert editor.plane.color().alpha() == 0

    editor.plane._apply_position(150, 30)

    assert editor.plane.color().alpha() == 255
    # …and the emitted preview is an opaque, visible colour.
    assert editor.value().startswith("#")
    assert len(editor.value()) == 7, "alpha must be back at 255"


def test_hue_change_resurrects_a_transparent_value(app):
    editor = ColorEditor("#00000000")
    editor.hue.resize(160, 12)
    editor.plane.set_color(QColor(0, 0, 0, 0))
    editor.hue._apply(editor.hue.rect().left() + 80)
    assert editor.plane.color().alpha() == 255
    assert len(editor.value()) == 7, "alpha must be back at 255"


def test_the_alpha_strip_still_lowers_alpha(app):
    """Resurrection is a floor for picking, not a lock on the strip."""
    editor = ColorEditor("transparent")
    editor.plane.resize(200, 104)
    editor.plane._apply_position(150, 30)
    assert editor.plane.color().alpha() == 255
    editor.alpha.resize(160, 12)
    editor.alpha._apply(editor.alpha.rect().left() + 1)
    assert editor.plane.color().alpha() == 0


# ── bug: the colour dialog could not be opened twice ────────────────────────

def test_color_field_popover_reopens_after_close(app):
    field = ColorField("#ff0000")
    field._open_popover()
    first = field._popover
    assert first is not None

    first.close()
    assert field._popover is None, "a closed popup must release the field"

    field._open_popover()
    assert field._popover is not None
    assert field._popover is not first
    field._popover.close()
    assert field._popover is None


def test_paint_field_popover_reopens_after_close(app):
    field = PaintField("#ff0000")
    field._open_popover()
    first = field._popover
    assert first is not None
    first.close()
    assert field._popover is None
    field._open_popover()
    assert field._popover is not None
    assert field._popover is not first
    field._popover.close()


# ── bug: symbolic values were shown instead of the colour ──────────────────

def test_display_text_resolves_tokens_to_hex():
    assert display_color_text("@gold", {"gold": GOLD}) == GOLD
    assert display_color_text("transparent") == "#00000000"
    assert display_color_text("#ff0000") == "#ff0000"
    assert display_color_text(None) == ""


def test_color_field_shows_hex_but_keeps_the_token(app):
    field = ColorField("@gold", palette=[("Gold", GOLD)])
    field._sync()
    assert field._edit.text() == GOLD

    # Focus-out re-emits the text the field painted; that is not an edit and
    # must not rewrite the token stored in the theme.
    field._commit_text()
    assert field.value() == "@gold"

    # A real edit still wins.
    field._edit.setText("#00ff00")
    field._commit_text()
    assert field.value() == "#00ff00"


def test_paint_field_describes_tokens_as_hex():
    palette = {"gold": GOLD}
    assert _describe("@gold", palette) == GOLD
    assert _describe("transparent", palette) == "#00000000"
    assert _describe(None, palette) == "Not set"


def test_paint_field_keeps_the_token_while_showing_hex(app):
    field = PaintField("@gold", palette=[("Gold", GOLD)])
    assert field.value() == "@gold"
    assert _describe(field._value, field._palette_map) == GOLD
