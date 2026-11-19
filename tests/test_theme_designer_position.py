"""Container position, round 4: the pin model, its resolver and the panel.

A container pins one of nine points of its own box to a point of the canvas, so
resizing grows it around the pin. The rules live in
``docs/PANEL_ORGANIZATION.md`` §3 and the property contract in
``docs/theme_file_reference.md`` §5.3.

The resolver exists once in Python (``container_geometry.resolve_origin``) and
once in each JS renderer (``_modelPosition`` in ``display/display.js`` and in
the mirror embedded in ``ui/widgets/display_view.py``). These tests run the
same case table through all three so they cannot drift.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PyQt6.QtCore import QPoint, Qt  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402

from ui.theme_kit import panel_state  # noqa: E402
from ui.theme_kit.property_row import PropertyRow  # noqa: E402
from ui.widgets.theme_designer import container_geometry as geometry  # noqa: E402

_QAPP = None

ROOT = Path(__file__).resolve().parents[1]
CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))
RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]

CANVAS = (1920.0, 1080.0)
BOX = (600.0, 400.0)


@pytest.fixture(scope="module")
def qapp():
    global _QAPP
    _QAPP = QApplication.instance() or QApplication(["test"])
    return _QAPP


@pytest.fixture(autouse=True)
def saved_state(monkeypatch):
    """In-memory settings store, so tests never touch the app database."""
    panel_state.reset_cache()
    store: dict[str, dict[str, bool]] = {}
    monkeypatch.setattr(panel_state, "_read",
                        lambda panel: dict(store.get(panel, {})))
    monkeypatch.setattr(panel_state, "_write",
                        lambda panel, state: store.__setitem__(panel,
                                                               dict(state)))
    yield store
    panel_state.reset_cache()


# ─── helpers ────────────────────────────────────────────────────────────────

def _canvas(aligned, anchor, x=0, y=0):
    return {"mode": "canvas",
            "canvas": {"aligned": aligned, "anchor": anchor,
                       "x": x, "y": y}}


def _edge(edge_name, anchor="top_left", d=0, unit="px"):
    return {"mode": "edge",
            "edge": {"anchor": anchor, "edge": edge_name, "d": d,
                     "unit": unit, "target": "canvas"}}


def _container(position, width=BOX[0], height=BOX[1], **extra):
    container = {"id": "main", "position": position,
                 "width": width, "height": height}
    container.update(extra)
    return container


def _rect(position, width=BOX[0], height=BOX[1], canvas=CANVAS, **extra):
    return geometry.container_rect(_container(position, width, height, **extra),
                                   canvas)


def _origin(position, **kwargs):
    rect = _rect(position, **kwargs)
    return (rect["x"], rect["y"])


# The panel's nine points, with the box expected at that alignment.
ALIGNED = [
    ("top_left", (0.0, 0.0)),
    ("top", (660.0, 0.0)),
    ("top_right", (1320.0, 0.0)),
    ("left", (0.0, 340.0)),
    ("center", (660.0, 340.0)),
    ("right", (1320.0, 340.0)),
    ("bottom_left", (0.0, 680.0)),
    ("bottom", (660.0, 680.0)),
    ("bottom_right", (1320.0, 680.0)),
]

_FRACTIONS = geometry.FRACTIONS


def _aligned_payload(point):
    ax, ay = _FRACTIONS[point]
    return _canvas(point, point, ax * CANVAS[0], ay * CANVAS[1])


# ─── resolver: canvas mode ──────────────────────────────────────────────────

@pytest.mark.parametrize("point, expected", ALIGNED)
def test_every_alignment_pins_that_point_of_the_box(point, expected):
    assert _origin(_aligned_payload(point)) == pytest.approx(expected)


def test_a_resize_grows_the_box_around_its_pin():
    centred = _aligned_payload("center")
    rect = _rect(centred, 300, 200)
    assert (rect["x"], rect["y"]) == pytest.approx((810.0, 440.0))

    flush = _aligned_payload("bottom_right")
    rect = _rect(flush, 300, 200)
    assert rect["x"] + rect["width"] == pytest.approx(CANVAS[0])
    assert rect["y"] + rect["height"] == pytest.approx(CANVAS[1])


def test_min_max_are_applied_before_the_pin_is_resolved():
    payload = _aligned_payload("center")
    rect = _rect(payload, 600, 400, max_width=400, max_height=300)
    assert rect["width"] == 400
    assert rect["height"] == 300
    assert (rect["x"], rect["y"]) == pytest.approx((760.0, 390.0))

    grown = _rect(payload, 100, 100, min_width=500, min_height=200)
    assert (grown["width"], grown["height"]) == (500, 200)
    assert (grown["x"], grown["y"]) == pytest.approx((710.0, 440.0))


def test_a_free_pin_is_used_as_is_even_off_canvas():
    payload = _canvas(None, "top_left", -40, 1200)
    assert _origin(payload) == (-40.0, 1200.0)

    payload = _canvas(None, "center", 0, 0)
    assert _origin(payload) == pytest.approx((-300.0, -200.0))


# ─── resolver: edge mode ────────────────────────────────────────────────────

#: Each edge is measured with the anchor that lays the box against it, so the
#: distance is the gap from that canvas edge to the box.
EDGE_CASES = [
    ("left", "top_left", 0, (0.0, 0.0)),
    ("left", "top_left", 40, (40.0, 0.0)),
    ("left", "top_left", -20, (-20.0, 0.0)),
    ("right", "top_right", 0, (1320.0, 0.0)),
    ("right", "top_right", 40, (1280.0, 0.0)),
    ("right", "top_right", -20, (1340.0, 0.0)),
    ("top", "top_left", 0, (0.0, 0.0)),
    ("top", "top_left", 40, (0.0, 40.0)),
    ("top", "top_left", -20, (0.0, -20.0)),
    ("bottom", "bottom_left", 0, (0.0, 680.0)),
    ("bottom", "bottom_left", 40, (0.0, 640.0)),
    ("bottom", "bottom_left", -20, (0.0, 700.0)),
]


@pytest.mark.parametrize("edge_name, anchor, d, expected", EDGE_CASES)
def test_each_edge_measures_inwards_and_accepts_negatives(edge_name, anchor, d,
                                                          expected):
    assert _origin(_edge(edge_name, anchor, d)) == pytest.approx(expected)


@pytest.mark.parametrize("edge_name, anchor, d, expected", [
    ("left", "top_left", 10, (192.0, 0.0)),
    ("right", "top_right", 10, (1128.0, 0.0)),
    ("top", "top_left", 10, (0.0, 108.0)),
    ("bottom", "bottom_left", 10, (0.0, 572.0)),
])
def test_percent_distances_use_the_axis_they_measure(edge_name, anchor, d,
                                                     expected):
    assert _origin(_edge(edge_name, anchor, d, "percent")) == pytest.approx(
        expected)


def test_the_untied_axis_follows_the_anchor_in_edge_mode():
    # Pinned to the left edge, the box's bottom edge stays on the canvas.
    bottom = _origin(_edge("left", "bottom_left", 40))
    assert bottom == pytest.approx((40.0, 680.0))

    # Pinned to the top edge, the box's right edge stays on the canvas.
    right = _origin(_edge("top", "top_right", 40))
    assert right == pytest.approx((1320.0, 40.0))

    # A centre anchor hangs half the box above the pinned top edge.
    centre = _origin(_edge("top", "center", 40))
    assert centre == pytest.approx((660.0, -160.0))


# ─── legacy ─────────────────────────────────────────────────────────────────

def test_a_legacy_position_keeps_the_old_arithmetic():
    legacy = {"anchor": "center", "x": 8, "y": 8}
    assert geometry.position_model(legacy) is None
    assert _origin(legacy) == pytest.approx((668.0, 348.0))

    # And it still tracks a resize the way it always did.
    rect = _rect(legacy, 300, 200)
    assert (rect["x"], rect["y"]) == pytest.approx((818.0, 448.0))


def test_a_legacy_theme_is_not_rewritten_on_load(qapp):
    theme = _theme(position={"anchor": "center", "x": 8, "y": 8})
    editor = _editor(qapp, theme)
    stored = editor.get_theme()["containers"][0]["position"]
    assert stored == {"anchor": "center", "x": 8, "y": 8}
    assert "mode" not in stored and "canvas" not in stored

    # The panel presents the rectangle it paints as a top-left pin.
    state = editor._position_state()
    assert state["mode"] == "canvas"
    assert state["canvas"]["aligned"] is None
    assert state["canvas"]["anchor"] == "top_left"
    assert (state["canvas"]["x"], state["canvas"]["y"]) == (668, 348)
    editor.close()


# ─── panel ──────────────────────────────────────────────────────────────────

def _theme(**container):
    values = {
        "id": "main",
        "label": "Main",
        "visible": True,
        "layer": 2,
        "width": 600,
        "height": 400,
        "border": "none",
        "blocks": {},
    }
    values.update(container)
    return {"kind": "scripture",
            "canvas": {"width": 1920, "height": 1080},
            "containers": [values]}


def _editor(qapp, theme=None):
    from ui.widgets.theme_designer import ThemePropertyEditor

    editor = ThemePropertyEditor()
    editor.resize(240, 1000)
    editor.load_theme(theme if theme is not None else _theme())
    editor._pages.set_value("container")
    editor._on_page("container")
    editor.show()
    qapp.processEvents()
    return editor


def _position(editor):
    assert editor._position is not None, "the Position heading is missing"
    return editor._position


def _row(editor, label):
    return next(row for row in editor._host.findChildren(PropertyRow)
                if row.label() == label)


def _click_grid(qapp, editor, point):
    """Click the grid cell for ``point`` with a real press/release pair."""
    grid = _position(editor)["grid"]
    row, column = {
        "top_left": (0, 0), "top": (0, 1), "top_right": (0, 2),
        "left": (1, 0), "center": (1, 1), "right": (1, 2),
        "bottom_left": (2, 0), "bottom": (2, 1), "bottom_right": (2, 2),
    }[point]
    rect = grid._cell_rect(row, column)
    pos = QPoint(int(rect.center().x()), int(rect.center().y()))
    QTest.mousePress(grid, Qt.MouseButton.LeftButton, pos=pos)
    QTest.mouseRelease(grid, Qt.MouseButton.LeftButton, pos=pos)
    qapp.processEvents()


def _stored(editor):
    return editor.get_theme()["containers"][0]["position"]


def test_the_position_heading_shows_the_canvas_controls(qapp):
    editor = _editor(qapp)
    ui = _position(editor)
    assert ui["mode"].value() == "canvas"
    assert ui["rows"]["align"].isVisibleTo(editor)
    assert ui["rows"]["x"].isVisibleTo(editor)
    assert ui["rows"]["y"].isVisibleTo(editor)
    assert not ui["rows"]["edge"].isVisibleTo(editor)
    assert not ui["rows"]["distance"].isVisibleTo(editor)
    editor.close()


def test_clicking_the_grid_pins_that_point(qapp):
    editor = _editor(qapp)
    _click_grid(qapp, editor, "center")
    canvas = _stored(editor)["canvas"]
    assert canvas == {"aligned": "center", "anchor": "center",
                      "x": 960, "y": 540}
    assert _stored(editor)["mode"] == "canvas"
    rect = _rect(_stored(editor))
    assert (rect["x"], rect["y"]) == pytest.approx((660.0, 340.0))
    editor.close()


def test_a_mouse_drag_on_x_moves_the_pin_and_detaches_the_grid(qapp):
    editor = _editor(qapp)
    _click_grid(qapp, editor, "center")
    ui = _position(editor)
    field = ui["x"]
    before = field.numeric_value()
    pos = QPoint(30, field.height() // 2)
    QTest.mousePress(field, Qt.MouseButton.LeftButton, pos=pos)
    for step in (1, 2, 3):
        QTest.mouseMove(field, pos + QPoint(step * 6, 0))
        qapp.processEvents()
    QTest.mouseRelease(field, Qt.MouseButton.LeftButton,
                       pos=pos + QPoint(18, 0))
    qapp.processEvents()

    assert field.numeric_value() != before
    canvas = _stored(editor)["canvas"]
    assert canvas["aligned"] is None
    assert canvas["x"] == field.numeric_value()
    assert ui["grid"].value() == "", "the grid must go dormant"
    editor.close()


def test_clicking_the_grid_again_wakes_the_alignment(qapp):
    editor = _editor(qapp)
    _click_grid(qapp, editor, "center")
    field = _position(editor)["x"]
    field.set_value(200, emit=True)
    qapp.processEvents()
    assert _stored(editor)["canvas"]["aligned"] is None

    _click_grid(qapp, editor, "center")
    canvas = _stored(editor)["canvas"]
    assert canvas["aligned"] == "center"
    assert (canvas["x"], canvas["y"]) == (960, 540)
    editor.close()


def test_choosing_the_point_sets_the_anchor_and_frees_the_grid(qapp):
    editor = _editor(qapp)
    _click_grid(qapp, editor, "bottom_right")
    point = _position(editor)["point"]
    point.set_value("top", emit=True)
    qapp.processEvents()
    canvas = _stored(editor)["canvas"]
    assert canvas["aligned"] is None
    assert canvas["anchor"] == "top"
    assert (canvas["x"], canvas["y"]) == (1920, 1080)
    # A top anchor pins the box's top centre to the stored point.
    rect = _rect({"mode": "canvas", "canvas": canvas})
    assert (rect["x"], rect["y"]) == pytest.approx((1620.0, 1080.0))
    editor.close()


def test_a_canvas_resize_moves_an_aligned_container_but_not_a_pinned_one(qapp):
    editor = _editor(qapp, _theme(position=_canvas("center", "center", 960, 540)))
    before = editor._position_state()["rect"]
    assert (before["x"], before["y"]) == pytest.approx((660.0, 340.0))

    editor.set_field("canvas.width", 2560)
    qapp.processEvents()
    after = editor._position_state()["rect"]
    assert (after["x"], after["y"]) == pytest.approx((980.0, 340.0))
    assert _position(editor)["x"].numeric_value() == 1280

    # A free pin keeps its coordinates.
    editor.set_field("containers.0.position.canvas.aligned", None)
    editor.set_field("containers.0.position.canvas.anchor", "top_left")
    editor.set_field("containers.0.position.canvas.x", 100)
    editor.set_field("containers.0.position.canvas.y", 100)
    editor.set_field("canvas.width", 1920)
    qapp.processEvents()
    pinned = editor._position_state()["rect"]
    assert (pinned["x"], pinned["y"]) == (100, 100)
    editor.close()


def test_switching_to_edge_keeps_the_pinned_axis(qapp):
    editor = _editor(qapp)
    _click_grid(qapp, editor, "center")
    before = editor._position_state()["rect"]
    revision = editor._document.revision
    emissions: list = []
    editor._document.changed.connect(lambda paths, source: emissions.append(paths))

    _position(editor)["mode"].changed.emit("edge")
    qapp.processEvents()

    stored = _stored(editor)
    assert stored["mode"] == "edge"
    # The anchor's x fraction is pinned to the left edge: the pin sits at
    # 660 + 300, so d = 960 keeps the box exactly where it was.
    assert stored["edge"] == {"anchor": "center", "edge": "left", "d": 960,
                              "unit": "px", "target": "canvas"}
    after = editor._position_state()["rect"]
    assert after["x"] == pytest.approx(before["x"])
    # One edit, one change: the whole position object is a single write.
    assert editor._document.revision == revision + 1
    assert len(emissions) == 1
    editor.close()


def test_switching_back_to_canvas_keeps_the_other_axis(qapp):
    editor = _editor(qapp)
    ui = _position(editor)
    ui["mode"].changed.emit("edge")
    qapp.processEvents()
    ui["distance"].set_value("40px", emit=True)
    qapp.processEvents()
    before = editor._position_state()["rect"]

    ui["mode"].changed.emit("canvas")
    qapp.processEvents()
    after = editor._position_state()["rect"]
    assert (after["x"], after["y"]) == pytest.approx((before["x"], before["y"]))
    canvas = _stored(editor)["canvas"]
    assert canvas["aligned"] is None
    assert (canvas["x"], canvas["y"]) == pytest.approx((before["x"], before["y"]))
    editor.close()


def test_both_mode_payloads_survive_a_round_trip(qapp):
    editor = _editor(qapp, _theme(position=_canvas("bottom_right",
                                                   "bottom_right", 1920, 1080)))
    ui = _position(editor)
    ui["mode"].changed.emit("edge")
    qapp.processEvents()
    ui["mode"].changed.emit("canvas")
    qapp.processEvents()
    stored = _stored(editor)
    # Coming back seeds the canvas pin from the rendered position, which is
    # the free-pin rule: the alignment itself is not restored (docs §3).
    assert stored["canvas"] == {"aligned": None, "anchor": "bottom_right",
                                "x": 1920, "y": 1080}
    assert stored["edge"]["target"] == "canvas"
    assert stored["edge"]["anchor"] == "bottom_right"
    assert stored["edge"]["edge"] == "left"
    editor.close()


def test_edge_mode_swaps_the_distance_label_with_the_axis(qapp):
    editor = _editor(qapp)
    ui = _position(editor)
    ui["mode"].changed.emit("edge")
    qapp.processEvents()
    assert ui["rows"]["distance"].label() == "X"
    assert not ui["rows"]["align"].isVisibleTo(editor)

    ui["edge"].set_value("top", emit=True)
    qapp.processEvents()
    assert ui["rows"]["distance"].label() == "Y"
    assert _stored(editor)["edge"]["edge"] == "top"
    editor.close()


def test_a_percent_distance_round_trips_through_the_field(qapp):
    editor = _editor(qapp)
    ui = _position(editor)
    ui["mode"].changed.emit("edge")
    qapp.processEvents()
    ui["distance"].set_value("10%", emit=True)
    qapp.processEvents()
    edge = _stored(editor)["edge"]
    assert (edge["d"], edge["unit"]) == (10, "percent")
    assert ui["distance"].value() == "10%"
    editor.close()


# ─── schema ─────────────────────────────────────────────────────────────────

def test_the_schema_keeps_both_payloads_and_their_unknown_target():
    from core import theme_schema

    theme = _theme(position={
        "mode": "edge",
        "canvas": {"aligned": "center", "anchor": "center", "x": 960, "y": 540},
        "edge": {"anchor": "top_left", "edge": "right", "d": 12.5,
                 "unit": "percent", "target": "other-panel"},
    })
    out, report = theme_schema.normalize_theme(theme, kind="scripture")
    position = out["containers"][0]["position"]
    assert position["mode"] == "edge"
    assert position["canvas"]["aligned"] == "center"
    assert position["edge"]["target"] == "other-panel"
    assert position["edge"]["unit"] == "percent"
    messages = report.warnings + report.errors
    assert not [item for item in messages if "position" in item]


def test_missing_or_invalid_payload_fields_fall_back_to_the_defaults():
    from core import theme_schema

    theme = _theme(position={
        "mode": "sideways",
        "canvas": {"aligned": "middle_centre", "anchor": "nowhere",
                   "x": "left", "y": None},
        "edge": {"edge": "diagonal", "d": None},
    })
    out, report = theme_schema.normalize_theme(theme, kind="scripture")
    position = out["containers"][0]["position"]
    assert position["mode"] == "canvas"
    assert position["canvas"] == {"aligned": None, "anchor": "top_left",
                                  "x": 0, "y": 0}
    assert position["edge"]["edge"] == "left"
    assert position["edge"]["d"] == 0
    assert position["edge"]["unit"] == "px"
    assert position["edge"]["target"] == "canvas"
    assert [item for item in report.warnings if "position" in item]


# ─── renderers ──────────────────────────────────────────────────────────────

RENDER_THEME = {
    "schema_version": 2,
    "name": "round4_position",
    "kind": "scripture",
    "canvas": {"width": 1920, "height": 1080},
    "containers": [{
        "id": "main", "visible": True, "layer": 1,
        "position": {"anchor": "center", "x": 8, "y": 8},
        "width": 600, "height": 400,
        "background": "rgba(15, 23, 42, 0.6)",
        "border": "none",
        "blocks": {
            "body": {"visible": True, "valign": "center", "gap": 0,
                     "padding": 0},
            "text": {"visible": True, "size": 48, "color": "#ffffff"},
            "reference": {"visible": True, "size": 24, "color": "#dddddd"},
        },
    }],
    "animations": {},
}

RENDER_CASES = [
    ("legacy", {"anchor": "center", "x": 8, "y": 8}),
    ("legacy-top-left", {"anchor": "top_left", "x": 120, "y": 240}),
    ("aligned-center", _aligned_payload("center")),
    ("aligned-bottom-right", _aligned_payload("bottom_right")),
    ("aligned-top-right", _aligned_payload("top_right")),
    ("pinned-free", _canvas(None, "top_left", 120, 60)),
    ("pinned-negative", _canvas(None, "center", 40, -80)),
    ("edge-left", _edge("left", "top_left", 40)),
    ("edge-right", _edge("right", "top_left", 40)),
    ("edge-bottom", _edge("bottom", "bottom_right", 40)),
    ("edge-top-percent", _edge("top", "center", 10, "percent")),
    ("edge-cross-axis", _edge("left", "bottom_left", 0)),
]

POSITION_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };
window.__box = function () {
  const el = document.getElementById("rc-cont-main")
    || document.getElementById("container");
  if (!el) return null;
  return {left: el.offsetLeft, top: el.offsetTop,
          width: el.offsetWidth, height: el.offsetHeight};
};
window.__run = async function () {
  const cases = window.__cases;
  for (let i = 0; i < cases.length; i++) {
    const entry = cases[i];
    const theme = JSON.parse(JSON.stringify(window.__base));
    theme.containers[0].position = entry.position;
    applyTheme(theme);
    handlePayload({action: "display", theme_data: theme,
                   text: "Jesus wept.", reference: "John 11:35"});
    await window.__wait(150);
    window.__log.push({label: entry.label, box: window.__box()});
  }
  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _drive_positions(script_path: str) -> dict:
    from tests.test_theme_v2_animation_runtime import _build_page

    driver = (POSITION_DRIVER
              + "\nwindow.__base = " + json.dumps(RENDER_THEME) + ";\n"
              + "window.__cases = " + json.dumps(
                  [{"label": label, "position": position}
                   for label, position in RENDER_CASES]) + ";\n")
    page_html = _build_page(script_path, theme=RENDER_THEME, driver=driver)
    tmp = Path(tempfile.mkdtemp(prefix="rc-round4-"))
    try:
        page = tmp / "page.html"
        page.write_text(page_html)
        out = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--window-size=1920,1080", "--force-device-scale-factor=1",
             f"--user-data-dir={tmp / 'profile'}", "--no-first-run",
             "--virtual-time-budget=9000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, timeout=180).stdout
        found = re.findall(r'<script[^>]*data-rc="log"[^>]*>(.*?)</script>',
                           out, re.S)
        assert found, f"renderer produced no log: {out[:800]}"
        return {entry["label"]: entry for entry in json.loads(found[-1])
                if "label" in entry}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_the_renderer_places_every_position_like_the_resolver(renderer):
    log = _drive_positions(renderer)
    assert log["errors"]["errs"] == [], log["errors"]["errs"]
    for label, position in RENDER_CASES:
        expected = _rect(position)
        box = log[label]["box"]
        assert box is not None, label
        assert (box["left"], box["top"]) == pytest.approx(
            (expected["x"], expected["y"]), abs=0.75), label
        assert (box["width"], box["height"]) == (600, 400), label


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_the_renderer_keeps_a_legacy_position_exactly_where_it_was(renderer):
    log = _drive_positions(renderer)
    legacy = log["legacy"]["box"]
    # The theme's stored anchor/x/y, through the old arithmetic: no payload,
    # no migration, same pixels as before round 4.
    assert (legacy["left"], legacy["top"]) == pytest.approx((668.0, 348.0),
                                                            abs=0.75)
    pinned = log["legacy-top-left"]["box"]
    assert (pinned["left"], pinned["top"]) == pytest.approx((120.0, 240.0),
                                                            abs=0.75)
