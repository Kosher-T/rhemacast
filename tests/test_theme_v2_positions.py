"""
tests/test_theme_v2_positions.py

Positioning gate for docs/theme_schema_v2.md §4.3:

- the anchor table is exact for `top_left` / `top_right` / `bottom_left` /
  `bottom_right` / `center` / `left` / `right` / `top` / `bottom` / `fill`;
- the unconstrained axis is centered unless its coordinate is given, and an
  explicit `0` counts as given;
- `center` is the only anchor where `x`/`y` are offsets;
- percentages resolve against the 1920×1080 design canvas, never the box;
- `fill` ignores size and offset (warned);
- corner booleans are a legacy spelling of the same anchors, first in the
  fixed order wins, extras are warned;
- an invalid anchor falls back to `center` with a warning;
- the projection bridge emits the same geometry the v1 renderer needs.

Geometry is asserted against `core.theme_compat._position_to_v1`, which is the
temporary v2→v1 bridge. Phase 3 re-implements the same table in `display.js`.
"""

import pytest

from core.theme_compat import _position_to_v1, project_legacy
from core.theme_schema import normalize_theme

CANVAS_W = 1920
CANVAS_H = 1080
BOX_W = 600
BOX_H = 300
CENTER_X = (CANVAS_W - BOX_W) / 2     # 660
CENTER_Y = (CANVAS_H - BOX_H) / 2     # 390


def _resolve(position, *, width=BOX_W, height=BOX_H,
             canvas=(CANVAS_W, CANVAS_H)):
    container = {
        "id": "main",
        "position": position,
        "blocks": {"text": {}},
    }
    # `None` means "leave the size at auto" (needed by the `fill` tests).
    if width is not None:
        container["width"] = width
    if height is not None:
        container["height"] = height
    raw = {
        "schema_version": 2,
        "canvas": {"width": canvas[0], "height": canvas[1]},
        "containers": [container],
    }
    return normalize_theme(raw, name="probe")


def _position(position, *, width=BOX_W, height=BOX_H,
              canvas=(CANVAS_W, CANVAS_H)):
    resolved, report = _resolve(position, width=width, height=height,
                                canvas=canvas)
    return resolved["containers"][0]["position"], report


def _box(position, *, width=BOX_W, height=BOX_H, canvas=(CANVAS_W, CANVAS_H)):
    """Resolved position -> (left, top) for a fixed box size."""
    validated, report = _position(position, width=width, height=height,
                                  canvas=canvas)
    return _position_to_v1(validated, width, height,
                           canvas_w=canvas[0], canvas_h=canvas[1]), report


def _joined(report) -> str:
    return "\n".join(report.warnings)


# ─── Corner anchors ─────────────────────────────────────────────────────────


def test_default_position_is_centered():
    (left, top), report = _box({})
    assert (left, top) == pytest.approx((CENTER_X, CENTER_Y))
    assert report.warnings == []


def test_top_left_defaults_to_the_canvas_origin():
    (left, top), report = _box({"anchor": "top_left"})
    assert (left, top) == (0.0, 0.0)
    assert report.warnings == []


def test_top_left_places_both_named_edges():
    (left, top), _ = _box({"anchor": "top_left", "x": 60, "y": 40})
    assert (left, top) == (60.0, 40.0)


def test_top_right_measures_x_inward_from_the_right_edge():
    (left, top), _ = _box({"anchor": "top_right"})
    assert (left, top) == (CANVAS_W - BOX_W, 0.0)

    (left, top), _ = _box({"anchor": "top_right", "x": 60, "y": 40})
    assert (left, top) == (CANVAS_W - BOX_W - 60, 40.0)


def test_bottom_left_measures_y_inward_from_the_bottom_edge():
    (left, top), _ = _box({"anchor": "bottom_left"})
    assert (left, top) == (0.0, CANVAS_H - BOX_H)

    (left, top), _ = _box({"anchor": "bottom_left", "x": 60, "y": 40})
    assert (left, top) == (60.0, CANVAS_H - BOX_H - 40)


def test_bottom_right_measures_both_edges_inward():
    (left, top), _ = _box({"anchor": "bottom_right"})
    assert (left, top) == (CANVAS_W - BOX_W, CANVAS_H - BOX_H)

    (left, top), _ = _box({"anchor": "bottom_right", "x": 60, "y": 40})
    assert (left, top) == (CANVAS_W - BOX_W - 60, CANVAS_H - BOX_H - 40)


def test_corner_anchors_use_the_box_size():
    # A wider box on the right edge starts further left.
    (left, _), _ = _box({"anchor": "top_right"}, width=800)
    assert left == CANVAS_W - 800
    (_, top), _ = _box({"anchor": "bottom_left"}, height=500)
    assert top == CANVAS_H - 500


# ─── Center ─────────────────────────────────────────────────────────────────


def test_center_offsets_are_relative_to_the_centered_position():
    (left, top), report = _box({"anchor": "center", "x": 10, "y": -20})
    assert (left, top) == (CENTER_X + 10, CENTER_Y - 20)
    assert report.warnings == []


def test_center_with_zero_offsets_stays_centered():
    (left, top), _ = _box({"anchor": "center", "x": 0, "y": 0})
    assert (left, top) == (CENTER_X, CENTER_Y)


# ─── Edge anchors: the unconstrained axis is centered ───────────────────────


def test_left_centers_vertically_unless_y_is_given():
    (left, top), _ = _box({"anchor": "left", "x": 60})
    assert (left, top) == (60.0, CENTER_Y)


def test_left_with_an_explicit_zero_y_is_top_aligned():
    # "Given" means present and not null: 0 is a real coordinate.
    (left, top), _ = _box({"anchor": "left", "x": 60, "y": 0})
    assert (left, top) == (60.0, 0.0)


def test_left_with_y_is_exactly_top_left():
    edge, _ = _box({"anchor": "left", "x": 60, "y": 40})
    corner, _ = _box({"anchor": "top_left", "x": 60, "y": 40})
    assert edge == corner


def test_right_mirrors_left():
    (left, top), _ = _box({"anchor": "right", "x": 60})
    assert (left, top) == (CANVAS_W - BOX_W - 60, CENTER_Y)
    (left, top), _ = _box({"anchor": "right", "x": 60, "y": 0})
    assert (left, top) == (CANVAS_W - BOX_W - 60, 0.0)
    edge, _ = _box({"anchor": "right", "x": 60, "y": 40})
    corner, _ = _box({"anchor": "top_right", "x": 60, "y": 40})
    assert edge == corner


def test_top_centers_horizontally_unless_x_is_given():
    (left, top), _ = _box({"anchor": "top", "y": 40})
    assert (left, top) == (CENTER_X, 40.0)


def test_top_with_an_explicit_zero_x_is_left_aligned():
    (left, top), _ = _box({"anchor": "top", "x": 0, "y": 40})
    assert (left, top) == (0.0, 40.0)


def test_top_with_x_is_exactly_top_left():
    edge, _ = _box({"anchor": "top", "x": 60, "y": 40})
    corner, _ = _box({"anchor": "top_left", "x": 60, "y": 40})
    assert edge == corner


def test_bottom_mirrors_top():
    (left, top), _ = _box({"anchor": "bottom", "y": 40})
    assert (left, top) == (CENTER_X, CANVAS_H - BOX_H - 40)
    (left, top), _ = _box({"anchor": "bottom", "x": 0, "y": 40})
    assert (left, top) == (0.0, CANVAS_H - BOX_H - 40)
    edge, _ = _box({"anchor": "bottom", "x": 60, "y": 40})
    corner, _ = _box({"anchor": "bottom_left", "x": 60, "y": 40})
    assert edge == corner


def test_a_null_coordinate_counts_as_absent():
    (left, top), _ = _box({"anchor": "left", "x": 60, "y": None})
    assert (left, top) == (60.0, CENTER_Y)


# ─── Percentages ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("anchor, axis, value, expected", [
    ("top", "x", "25%", 0.25 * CANVAS_W),             # horizontal % of W
    ("bottom", "x", "50%", 0.50 * CANVAS_W),
    ("left", "y", "50%", 0.50 * CANVAS_H),            # vertical % of H
    ("right", "y", "10%", 0.10 * CANVAS_H),
])
def test_percentages_resolve_against_the_canvas(anchor, axis, value, expected):
    position = {"anchor": anchor, axis: value}
    (left, top), report = _box(position)
    assert report.warnings == []
    actual = left if axis == "x" else top
    assert actual == pytest.approx(expected)


def test_percentages_ignore_the_box_size():
    # The same coordinate resolves identically for a tiny and a huge box.
    small, _ = _box({"anchor": "top", "x": "25%", "y": "50%"}, width=100,
                    height=40)
    large, _ = _box({"anchor": "top", "x": "25%", "y": "50%"}, width=1500,
                    height=800)
    assert small[0] == large[0] == pytest.approx(0.25 * CANVAS_W)
    assert small[1] == large[1] == pytest.approx(0.50 * CANVAS_H)


def test_percentages_use_the_declared_canvas_not_a_fixed_1920():
    (left, top), _ = _box({"anchor": "top", "x": "25%", "y": "50%"},
                          canvas=(1280, 720))
    assert (left, top) == pytest.approx((0.25 * 1280, 0.50 * 720))


def test_corner_percentages_are_inward_edges():
    (left, top), _ = _box({"anchor": "bottom_right", "x": "10%", "y": "10%"})
    assert left == pytest.approx(CANVAS_W - BOX_W - 0.10 * CANVAS_W)
    assert top == pytest.approx(CANVAS_H - BOX_H - 0.10 * CANVAS_H)


def test_center_percentage_offsets_resolve_against_the_canvas():
    (left, top), _ = _box({"anchor": "center", "x": "10%", "y": "10%"})
    assert left == pytest.approx(CENTER_X + 0.10 * CANVAS_W)
    assert top == pytest.approx(CENTER_Y + 0.10 * CANVAS_H)


# ─── fill ───────────────────────────────────────────────────────────────────


def test_fill_starts_at_the_origin():
    resolved, report = _resolve({"anchor": "fill"}, width=None, height=None)
    assert report.warnings == []
    legacy = project_legacy(resolved)["containers"]["main"]
    assert (legacy["x"], legacy["y"]) == (0.0, 0.0)
    assert legacy["width"] == "1920px"
    assert legacy["height"] == "1080px"


def test_fill_ignores_x_and_y_with_a_warning():
    (left, top), report = _box({"anchor": "fill", "x": 100, "y": 50})
    assert (left, top) == (0.0, 0.0)
    assert "fill ignores size and offset" in _joined(report)
    assert "'x'" in _joined(report) and "'y'" in _joined(report)


def test_fill_ignores_explicit_size_and_projects_the_whole_canvas():
    resolved, report = _resolve({"anchor": "fill"}, width=800, height=400)
    assert resolved["containers"][0]["position"]["anchor"] == "fill"
    assert "fill ignores size and offset" in _joined(report)

    legacy = project_legacy(resolved)["containers"]["main"]
    assert legacy["width"] == "1920px"
    assert legacy["height"] == "1080px"
    assert (legacy["x"], legacy["y"]) == (0.0, 0.0)


def test_fill_is_the_only_anchor_that_overrides_a_size():
    resolved, report = _resolve({"anchor": "top_left"}, width=800, height=400)
    assert report.warnings == []
    legacy = project_legacy(resolved)["containers"]["main"]
    assert legacy["width"] == "800px"
    assert legacy["height"] == "400px"


# ─── Legacy corner booleans ─────────────────────────────────────────────────


def test_a_corner_boolean_selects_its_anchor_with_a_legacy_warning():
    position, report = _position({"top_right": True})
    assert position["anchor"] == "top_right"
    assert "corner boolean position is legacy" in _joined(report)


def test_no_corner_boolean_means_center():
    position, report = _position({"top_left": False, "bottom_right": False})
    assert position["anchor"] == "center"
    assert report.warnings == []


def test_the_first_corner_in_the_fixed_order_wins():
    # Fixed order: top_left, top_right, bottom_left, bottom_right.
    position, report = _position({"bottom_right": True, "top_left": True})
    assert position["anchor"] == "top_left"
    assert "extra corner key ignored" in _joined(report)

    position, report = _position({"bottom_left": True, "top_right": True})
    assert position["anchor"] == "top_right"
    assert "extra corner key ignored" in _joined(report)


def test_every_extra_corner_is_warned():
    position, report = _position({
        "top_left": True, "top_right": True,
        "bottom_left": True, "bottom_right": True,
    })
    assert position["anchor"] == "top_left"
    assert _joined(report).count("extra corner key ignored") == 3


def test_an_explicit_anchor_wins_over_corner_booleans():
    position, report = _position({"anchor": "left", "top_left": True})
    assert position["anchor"] == "left"
    assert report.warnings == []
    assert any("corner key ignored because anchor is set" in note
               for note in report.notes)


# ─── Invalid input ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_anchor", ["middle", "TOP_LEFT", "", 3, False])
def test_an_invalid_anchor_falls_back_to_center_with_a_warning(bad_anchor):
    position, report = _position({"anchor": bad_anchor})
    assert position["anchor"] == "center"
    assert "invalid enum value" in _joined(report)


def test_an_absent_position_is_center():
    position, report = _position(None)
    assert position == {"anchor": "center"}
    assert report.warnings == []


def test_a_non_object_position_falls_back_to_center():
    position, report = _position("top_left")
    assert position == {"anchor": "center"}
    assert "position must be an object" in _joined(report)


def test_unknown_position_keys_are_notes_not_warnings():
    position, report = _position({"anchor": "center", "z": 3, "offset": 10})
    assert position == {"anchor": "center"}
    assert report.warnings == []
    assert any("ignoring unknown position keys" in note for note in report.notes)


def test_numeric_strings_are_accepted_for_coordinates():
    (left, top), report = _box({"anchor": "top_left", "x": "60", "y": "40px"})
    assert (left, top) == (60.0, 40.0)
    assert report.warnings == []


def test_negative_coordinates_are_kept():
    (left, top), report = _box({"anchor": "center", "x": -10, "y": -20})
    assert (left, top) == (CENTER_X - 10, CENTER_Y - 20)
    assert report.warnings == []


# ─── The bridge emits absolute v1 geometry ──────────────────────────────────


def test_projection_emits_the_absolute_box_for_an_edge_anchor():
    resolved, report = _resolve({"anchor": "right", "x": 60, "y": 40})
    assert report.warnings == []
    legacy = project_legacy(resolved)["containers"]["main"]
    assert (legacy["x"], legacy["y"]) == (CANVAS_W - BOX_W - 60, 40.0)
    assert legacy["width"] == "600px"
    assert legacy["height"] == "300px"


def test_projection_resolves_percentage_offsets():
    resolved, _ = _resolve({"anchor": "top", "x": "25%", "y": "50%"})
    legacy = project_legacy(resolved)["containers"]["main"]
    assert legacy["x"] == 0.25 * CANVAS_W
    assert legacy["y"] == 0.50 * CANVAS_H
