"""Headless Chrome coverage for the `border.draw` property track.

The renderer draws the container border as one rounded SVG path and reveals
it by animating `stroke-dashoffset`. The static border is hidden while the
overlay owns the ring, then restored when the draw finishes or is cancelled.
"""

from __future__ import annotations

import shutil

import pytest

from tests.test_theme_v2_animation_runtime import RENDERERS, _drive

CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))


DRIVER = r"""
window.__log = [];
window.__errs = [];
window.addEventListener("error", function (e) {
  window.__errs.push(String(e.message) + " @" + e.lineno + ":" + e.colno);
});
window.__snap = function (label) {
  const el = document.getElementById("rc-cont-main")
    || document.getElementById("container");
  const svg = el ? el.querySelector(".rc-border-draw") : null;
  const path = svg ? svg.querySelector("path") : null;
  const anims = path && path.getAnimations ? path.getAnimations() : [];
  const cs = el ? getComputedStyle(el) : null;
  const pcs = path ? getComputedStyle(path) : null;
  window.__log.push({
    label: label, t: +performance.now().toFixed(0),
    svg: !!svg,
    d: path ? path.getAttribute("d") : null,
    direction: svg ? svg.getAttribute("data-rc-direction") : null,
    duration: svg ? svg.getAttribute("data-rc-duration-ms") : null,
    perimeter: svg ? svg.getAttribute("data-rc-perimeter") : null,
    transform: path ? path.getAttribute("transform") : null,
    dash: path ? path.getAttribute("stroke-dashoffset") : null,
    dashComputed: pcs ? pcs.strokeDashoffset : null,
    anims: anims.length,
    state: anims.length ? anims[0].playState : "",
    border: cs ? cs.borderTopColor : "",
    width: el ? el.clientWidth : 0,
    height: el ? el.clientHeight : 0,
  });
};
window.__payload = function (p) {
  handlePayload({action: "display", kind: "scripture",
                 theme_data: window.__theme, ...p});
};
window.__wait = function (ms) { return new Promise(r => setTimeout(r, ms)); };
window.__run = async function () {
  window.__payload({text: "Border draw", reference: "John 1:1"});
  window.__snap("start");
  await window.__wait(120);
  window.__snap("mid");
  await window.__wait(700);
  window.__snap("done");
  window.__log.push({label: "errors", errs: window.__errs});
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "log");
  tag.textContent = JSON.stringify(window.__log);
  document.body.appendChild(tag);
};
"""


def _theme(track=None, reduced_hint=None):
    if track is None:
        track = {"phase": "entry", "direction": "clockwise",
                 "speed": 4000, "from": 0, "to": 1, "easing": "linear"}
    return {
        "schema_version": 2,
        "name": "border_draw_probe",
        "kind": "scripture",
        "canvas": {"width": 960, "height": 540, "fit": "contain",
                   "background": "transparent"},
        "containers": [{
            "id": "main", "visible": True, "layer": 1,
            "width": 400, "height": 200,
            "position": {"anchor": "center"},
            "opacity": 1, "overflow": "hidden",
            "border": {"width": 3, "style": "solid", "color": "#ff00ff"},
            "animation": {"properties": {"border.draw": dict(track)}},
            "blocks": {
                "body": {"visible": True, "valign": "center", "gap": 8,
                         "padding": 0},
                "text": {"visible": True, "size": 36, "color": "#ffffff",
                         "line_height": 1.2, "text_align": "center"},
                "reference": {"visible": True, "size": 18, "color": "#dddddd"},
            },
        }],
        "animations": {},
    }


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_draw_clockwise_uses_speed_and_restores_the_border(renderer):
    log = _drive(renderer, theme=_theme(), driver=DRIVER, budget_ms=6000)
    start = log["start"]
    mid = log["mid"]
    done = log["done"]

    assert log["errors"]["errs"] == []
    assert start["svg"] is True
    assert start["direction"] == "top clockwise"
    assert start["transform"] is None
    assert start["border"] == "rgba(0, 0, 0, 0)"
    assert start["anims"] == 1 and start["state"] == "running"
    perimeter = int(start["perimeter"])
    assert perimeter > 0
    # Speed overrides duration: the path is drawn at 4000 px/s.
    expected = round(perimeter / 4000 * 1000)
    assert abs(int(start["duration"]) - expected) <= 1
    assert start["d"].startswith("M ")
    assert start["d"].endswith(" Z")

    assert mid["svg"] is True
    assert mid["border"] == "rgba(0, 0, 0, 0)"

    assert done["svg"] is False
    assert done["border"] == "rgb(255, 0, 255)"
    assert done["anims"] == 0


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_draw_counterclockwise_mirrors_the_path(renderer):
    theme = _theme({
        "phase": "entry",
        "direction": "start:left counterclockwise",
        "duration_ms": 500,
        "from": 0,
        "to": 1,
    })
    log = _drive(renderer, theme=theme, driver=DRIVER, budget_ms=6000)
    start = log["start"]

    assert log["errors"]["errs"] == []
    assert start["svg"] is True
    assert start["direction"] == "left counterclockwise"
    assert "scale(-1,1)" in (start["transform"] or "")
    assert start["anims"] == 1


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_draw_partial_state_keeps_the_overlay(renderer):
    theme = _theme({
        "phase": "entry", "direction": "clockwise",
        "duration_ms": 200, "from": 0, "to": 0.4,
    })
    log = _drive(renderer, theme=theme, driver=DRIVER, budget_ms=6000)
    done = log["done"]

    assert log["errors"]["errs"] == []
    assert done["svg"] is True
    assert done["border"] == "rgba(0, 0, 0, 0)"
    assert done["anims"] == 1


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_draw_reduced_motion_keeps_the_static_border(renderer):
    theme = _theme()
    log = _drive(renderer, theme=theme, driver=DRIVER, budget_ms=3000,
                 reduced=True)

    assert log["errors"]["errs"] == []
    assert log["start"]["svg"] is False
    assert log["start"]["border"] == "rgb(255, 0, 255)"
