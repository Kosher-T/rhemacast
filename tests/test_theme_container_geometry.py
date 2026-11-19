"""Container geometry contract: exact rectangle, inset ring, two paints.

The renderer used to cap every container at 80 % of the canvas and raise it
to 60 % (`.rc-container { min-width: 60%; max-width: 80% }`), so an authored
1920x1080 container painted 1536x1080 and a 600px panel grew to 1152px and ran
off the right edge. The rectangle is now absolute: `width` x `height` at the
anchor, with the border ring and border fill on an inset layer
(docs/theme_file_reference.md §5.0).

The geometry half drives the real renderer in headless Chrome; the rest is
schema and source coverage that also runs without a browser.
"""

from __future__ import annotations

import pytest

from core.theme_schema import normalize_theme
from tests.test_theme_v2_animation_runtime import CHROME, RENDERERS, _drive

GEOMETRY_DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };
window.__measure = function () {
  const stage = document.getElementById("stage");
  const sr = stage.getBoundingClientRect();
  const scale = sr.width / 1920;
  const rows = [];
  const els = [document.getElementById("container")].concat(
    Array.prototype.slice.call(
      document.querySelectorAll(".rc-dynamic-container")));
  els.forEach(function (el) {
    if (!el) return;
    const cs = getComputedStyle(el);
    if (cs.display === "none") return;
    const cr = el.getBoundingClientRect();
    const layer = el.querySelector(".rc-border-layer");
    const lr = layer ? layer.getBoundingClientRect() : null;
    const ls = layer ? getComputedStyle(layer) : null;
    const round = v => Math.round(v * 1000) / 1000;
    rows.push({
      id: el.id,
      rect: [round((cr.left - sr.left) / scale), round((cr.top - sr.top) / scale),
             round(cr.width / scale), round(cr.height / scale)],
      layer: lr ? [round((lr.left - sr.left) / scale),
                   round((lr.top - sr.top) / scale),
                   round(lr.width / scale), round(lr.height / scale)] : null,
      layer_border: ls ? ls.borderTopWidth : null,
      layer_radius: ls ? ls.borderTopLeftRadius : null,
      container_bg: cs.backgroundColor,
      container_radius: cs.borderTopLeftRadius,
      fill: ls ? ls.backgroundColor : null
    });
  });
  return {scale: scale, rows: rows};
};
window.__run = async function () {
  handlePayload({action: "display", kind: "scripture",
                 theme_data: window.__theme,
                 text: "In the beginning God created the heaven and the earth.",
                 reference: "GENESIS 1:1"});
  await window.__wait(400);
  window.__log.push(Object.assign({label: "layout"}, window.__measure()));
  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _container(**overrides):
    container = {
        "id": "main",
        "label": "Main",
        "visible": True,
        "width": 1920,
        "height": 1080,
        "position": {"anchor": "top_left", "x": 0, "y": 0},
        "blocks": {
            "body": {"padding": 40, "valign": "center", "gap": 12},
            "text": {"size": 60, "visible": True},
            "reference": {"size": 24, "visible": True},
        },
    }
    container.update(overrides)
    return container


def _theme(*containers):
    return {
        "schema_version": 2,
        "kind": "scripture",
        "canvas": {"width": 1920, "height": 1080,
                   "background": "transparent"},
        "containers": list(containers) or [_container()],
    }


def _layout(renderer, theme, budget_ms=6000):
    log = _drive(renderer, theme=theme, driver=GEOMETRY_DRIVER,
                 budget_ms=budget_ms)
    assert log["errors"]["errs"] == []
    # Every rect below is reported in canvas pixels: the driver divides the
    # measured box by the stage scale, so the assertion values do not depend
    # on the headless viewport size.
    return log["layout"]["rows"]


# ── schema ─────────────────────────────────────────────────────────────────

def test_container_paint_defaults_are_documented():
    resolved, report = normalize_theme(
        {"schema_version": 2, "containers": [{"id": "main"}]}, name="probe")

    assert report.ok and report.warnings == []
    container = resolved["containers"][0]
    assert container["container_background"] == "transparent"
    assert container["background"] == "transparent"
    assert container["border_padding"] == 0


def test_container_background_is_a_validated_paint():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main",
                        "container_background": "rgba(10, 20, 30, 0.9)",
                        "background": "linear-gradient(90deg, #000000, #ffffff)"}],
    }, name="probe")

    assert report.ok and report.warnings == []
    container = resolved["containers"][0]
    assert container["container_background"] == "rgba(10, 20, 30, 0.9)"
    assert container["background"].startswith("linear-gradient(")

    _, bad = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "container_background": "not a paint"}],
    }, name="probe")
    assert any("container_background" in w for w in bad.warnings)


def test_border_padding_clamps_with_a_warning():
    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "border_padding": 900}],
    }, name="probe")
    assert resolved["containers"][0]["border_padding"] == 400
    assert any("border_padding" in w for w in report.warnings)

    resolved, report = normalize_theme({
        "schema_version": 2,
        "containers": [{"id": "main", "border_padding": -20}],
    }, name="probe")
    assert resolved["containers"][0]["border_padding"] == 0
    assert any("border_padding" in w for w in report.warnings)


def test_border_padding_limits_are_shared_with_the_designer():
    from core.theme_schema import FIELD_LIMITS

    assert FIELD_LIMITS["border_padding"]["px"] == (0, 400, 1)


# ── source contract (no browser needed) ────────────────────────────────────

def test_stylesheet_no_longer_caps_container_width():
    css = open("display/themes.css").read()
    assert "--rc-min-width" not in css
    assert "--rc-max-width" not in css
    assert ".rc-border-layer" in css
    # The ring never lives on the container itself any more.
    block = css.split("#container, .rc-container {", 1)[1].split("}", 1)[0]
    declarations = [line.strip() for line in block.splitlines()]
    assert "border: 0;" in declarations
    assert "border-radius: 0;" in declarations
    assert "isolation: isolate;" in declarations
    assert not any(line.startswith(("min-width:", "max-width:"))
                   for line in declarations)


def test_page_markup_has_the_border_layer():
    from ui.widgets.display_view import _DISPLAY_HTML

    for page in (open("display/display.html").read(), _DISPLAY_HTML):
        head = page.split('<div id="container"', 1)[1][:400]
        assert 'class="rc-border-layer"' in head


# ── renderer geometry (headless Chrome) ────────────────────────────────────

@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_full_canvas_container_is_exactly_the_canvas(renderer):
    rows = _layout(renderer, _theme(_container(
        container_background="rgba(10, 40, 90, 0.9)",
        background="rgba(200, 20, 20, 0.8)")))

    row = rows[0]
    assert row["rect"] == [0, 0, 1920, 1080]
    # No border, no radius: the fill touches all four edges.
    assert row["layer"] == [0, 0, 1920, 1080]
    assert row["layer_border"] == "0px"
    assert row["layer_radius"] == "0px"
    # Two paints: the rectangle carries the container paint, the layer the
    # border fill.
    assert row["container_bg"] == "rgba(10, 40, 90, 0.9)"
    assert row["fill"] == "rgba(200, 20, 20, 0.8)"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_radius_and_border_never_change_the_rectangle(renderer):
    rows = _layout(renderer, _theme(_container(
        border={"width": 20, "style": "solid", "color": "#ffffff"},
        border_radius=60,
        container_background="rgba(10, 40, 90, 0.9)",
        background="rgba(200, 20, 20, 0.8)")))

    row = rows[0]
    assert row["rect"] == [0, 0, 1920, 1080]
    # The ring rounds its own outer edge; the rectangle stays square.
    assert row["layer"] == [0, 0, 1920, 1080]
    assert row["layer_border"] == "20px"
    assert row["layer_radius"] == "60px"
    assert row["container_radius"] == "0px"
    assert row["container_bg"] == "rgba(10, 40, 90, 0.9)"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_padding_insets_the_ring_only(renderer):
    rows = _layout(renderer, _theme(_container(
        border={"width": 20, "style": "solid", "color": "#ffffff"},
        border_radius=60,
        border_padding=40)))

    row = rows[0]
    assert row["rect"] == [0, 0, 1920, 1080]
    assert row["layer"] == [40, 40, 1840, 1000]
    assert row["layer_border"] == "20px"
    assert row["layer_radius"] == "60px"


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_panel_keeps_its_authored_size_at_its_anchor(renderer):
    panel = _container(
        id="footer", label="Footer", width=600, height=120,
        position={"anchor": "bottom_right", "x": 40, "y": 40},
        blocks={"body": {"padding": 10, "valign": "center"},
                "reference": {"size": 20, "visible": True}},
        container_background="rgba(0, 100, 0, 0.9)",
        background="rgba(255, 255, 0, 0.5)",
        border={"width": 4, "style": "solid", "color": "#ff0000"},
        border_radius=24,
    )
    rows = _layout(renderer, _theme(_container(), panel))

    by_id = {row["id"]: row for row in rows}
    assert by_id["rc-cont-main"]["rect"] == [0, 0, 1920, 1080]
    footer = by_id["rc-cont-footer"]
    # 1920 - 600 - 40 = 1280, 1080 - 120 - 40 = 920; the old 60 % floor made
    # this 1152 wide and pushed it off the right edge.
    assert footer["rect"] == [1280, 920, 600, 120]
    assert footer["layer"] == [1280, 920, 600, 120]
