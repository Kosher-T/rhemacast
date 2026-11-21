"""ui/theme_kit/paint_field.py — the gradient ramp and the value it emits.

Reported against the running Theme Designer: dragging the two handles of the
Border ▸ Fill gradient past each other (transparent handle to the left, colour
handle to the right) produced a hard edge instead of the gradient the ramp
shows, with one flat colour filling most of the shape.

Root cause: the emitted CSS kept the order the stops were added in, and CSS
clamps a stop that sits before its predecessor to that predecessor's position
(CSS Images 3 §3.4.1). ``linear-gradient(180deg, #ffffff 90%, #000000 10%)``
is therefore white up to 90% and then an abrupt switch — while the ramp in the
popover looked smooth, because Qt sorts the stops it paints. Stops are now
emitted (and painted, and sampled) in ascending position order, so the ramp,
the canvas, the preview and OBS all describe the same gradient.
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtWidgets import QApplication

from ui.theme_kit.paint_field import (
    GradientEditor, GradientSpec, GradientStop, _painted_order, format_gradient,
    parse_gradient, sample_gradient,
)


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _positions(css: str) -> list[float]:
    spec = parse_gradient(css)
    assert spec is not None, css
    return [stop.at for stop in spec.stops]


def _drag(bar, x: float, y: float, *, press: bool) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress if press else QEvent.Type.MouseMove,
        QPointF(x, y), QPointF(bar.mapToGlobal(QPointF(x, y).toPoint())),
        Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier)
    if press:
        bar.mousePressEvent(event)
    else:
        bar.mouseMoveEvent(event)


# ── the emitted value follows the ramp ──────────────────────────────────────

def test_stops_dragged_past_each_other_emit_in_paint_order(app):
    spec = GradientSpec(stops=[GradientStop(90.0, "#ffffff"),
                               GradientStop(10.0, "#000000")])

    css = format_gradient(spec)

    positions = _positions(css)
    assert positions == sorted(positions), (
        f"CSS clamps a descending stop, which is the hard edge: {css}")
    assert positions == [10.0, 90.0]
    assert css.index("#000000") < css.index("#ffffff"), css


def test_a_transparent_stop_stays_where_the_ramp_shows_it(app):
    """The reported gradient: transparent one way, colour the other."""
    spec = GradientSpec(stops=[GradientStop(85.0, "#ffffff00"),
                               GradientStop(15.0, "#0000ff")])

    css = format_gradient(spec)

    assert _positions(css) == [15.0, 85.0], css
    assert css.startswith("linear-gradient(180deg, #0000ff 15%"), css
    assert css.endswith("#ffffff00 85%)"), css
    # …and the painted sample agrees: opaque blue at the start, clear at the
    # end, a mix between them.
    assert sample_gradient(spec, 0).lower() == "#0000ff"
    assert sample_gradient(spec, 100).lower() == "#ffffff00"
    middle = sample_gradient(spec, 50).lower()
    assert middle not in ("#0000ff", "#ffffff00"), middle


def test_a_dragged_handle_previews_in_paint_order(app):
    """The drag itself must emit the sorted value, not just the release."""
    editor = GradientEditor(
        "linear-gradient(180deg, #ffffff 0%, #000000 30%)")
    editor.resize(320, 520)
    bar = editor.bar
    bar.resize(300, 34)
    previews = []
    editor.preview.connect(previews.append)

    ramp = bar._ramp()
    first = _painted_order(editor.spec().stops)[0][0]
    start_x = ramp.left() + ramp.width() * first / 100.0
    _drag(bar, start_x, ramp.center().y(), press=True)
    # Drag the leading handle well past the trailing one.
    _drag(bar, ramp.left() + ramp.width() * 0.8, ramp.center().y(),
          press=False)

    assert previews, "the drag emitted no preview"
    positions = _positions(previews[-1])
    assert positions == sorted(positions), (
        f"a mid-drag preview kept the model order: {previews[-1]}")
    assert positions == [30.0, pytest.approx(positions[1])], previews[-1]
    assert positions[1] > 30.0, previews[-1]


def test_a_new_stop_samples_the_painted_gradient(app):
    """Adding a stop after the handles crossed takes the colour on screen."""
    editor = GradientEditor("linear-gradient(180deg, #ffffff 0%, #000000 100%)")
    spec = editor.spec()
    spec.stops[0].at = 90.0        # white
    spec.stops[1].at = 10.0        # black

    editor._add_stop()

    added = [stop for stop in spec.stops if stop.at == 50.0]
    assert added, [(stop.at, stop.color) for stop in spec.stops]
    assert added[0].color.lower() == sample_gradient(
        GradientSpec(stops=[GradientStop(10.0, "#000000"),
                            GradientStop(90.0, "#ffffff")]), 50.0).lower()
    # The list is model-sorted now, so the handles and the CSS agree.
    assert [stop.at for stop in spec.stops] == [10.0, 50.0, 90.0]


def test_equal_positions_stay_a_hard_stop(app):
    """Two handles on the same spot are a deliberate hard edge, not a bug."""
    spec = GradientSpec(stops=[GradientStop(50.0, "#ff0000"),
                               GradientStop(50.0, "#0000ff")])
    assert format_gradient(spec) == (
        "linear-gradient(180deg, #ff0000 50%, #0000ff 50%)")
    assert sample_gradient(spec, 49).lower() == "#ff0000"
    assert sample_gradient(spec, 51).lower() == "#0000ff"
