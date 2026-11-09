"""
tests/test_theme_v2_phase4_equivalence.py

Phase 4 gate tests for docs/theme_schema_v2.md:
- Equivalence test: resolved v1-migrated dict deep-equals the resolved v2 file
  for every shipped theme (freeform/slides + 5 scripture themes).
- Animation equivalence: verify that a migrated v1 dict with
  `display_enter`/`between_slides`/`display_exit` produces matching phase
  selection, timing, and keyframes in v2.
- Render equivalence: drive the real renderer in headless Chrome with the
  resolved v2 theme and compare the measured glyph geometry and computed
  typography against `tests/golden_render_v1.json`, which was captured from
  the pre-v2 renderer (commit 5f9acd8) with the pristine v1 theme fixtures.

The render oracle measures glyph ranges, not block boxes: v2 mandates
full-width stack rows (`align-items: stretch`), so block-box widths are
allowed to differ while the visible text may not move.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
import pytest

from core.theme_migrate import migrate_v1_to_v2
from core.theme_schema import normalize_theme, BUILTIN_ANIMATIONS
from core.theme_loader import resolve_theme, get_theme

ROOT = Path(__file__).resolve().parents[1]
FIXTURES_PATH = ROOT / "tests" / "fixtures" / "v1_shipped_themes.json"
GOLDEN_RENDER_PATH = ROOT / "tests" / "golden_render_v1.json"
CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))

SHIPPED_THEMES = [
    ("slides", "freeform"),
    ("default", "scripture"),
    ("fullscreen", "scripture"),
    ("fullscreen_2", "scripture"),
    ("reference", "scripture"),
    ("reference_2", "scripture"),
]

PAYLOADS = {
    "short": {
        "text": "Jesus wept.",
        "reference": "John 11:35",
        "translation": "KJV",
    },
    "long": {
        "text": "For God so loved the world, that he gave his only begotten "
                "Son, that whosoever believeth in him should not perish, but "
                "have everlasting life.",
        "reference": "John 3:16",
        "translation": "KJV",
    },
}

# Exact geometry is measured from glyph ranges: block rows are full-width in
# v2, but the visible text must not move by more than half a pixel.
RECT_TOLERANCE = 0.6
STYLE_PROPS = ["fontSize", "lineHeight", "fontWeight", "letterSpacing",
               "color", "textAlign", "textTransform", "fontStyle",
               "textDecoration"]

DRIVER = r"""
window.__results = [];
function rect(el) {
  if (!el) return null;
  const b = el.getBoundingClientRect();
  return {x: +b.x.toFixed(2), y: +b.y.toFixed(2),
          w: +b.width.toFixed(2), h: +b.height.toFixed(2)};
}
function rangeRect(el) {
  if (!el) return null;
  const r = document.createRange();
  r.selectNodeContents(el);
  const b = r.getBoundingClientRect();
  return {x: +b.x.toFixed(2), y: +b.y.toFixed(2),
          w: +b.width.toFixed(2), h: +b.height.toFixed(2)};
}
function styles(el) {
  if (!el) return null;
  const s = getComputedStyle(el);
  return {
    fontSize: s.fontSize, lineHeight: s.lineHeight, fontWeight: s.fontWeight,
    fontFamily: s.fontFamily, letterSpacing: s.letterSpacing, color: s.color,
    textAlign: s.textAlign, textTransform: s.textTransform,
    fontStyle: s.fontStyle, textDecoration: s.textDecoration,
  };
}
async function __drive(theme, payload) {
  // Offline-first and deterministic: the bundled Nunito is the face under
  // test. Loading it before the payload means auto-fit measures the real
  // font, not whichever fallback wins a network race.
  if (document.fonts && document.fonts.load) {
    try {
      await Promise.all([
        document.fonts.load("700 40px Nunito"),
        document.fonts.load("400 40px Nunito"),
        document.fonts.load("400 40px 'DM Sans'"),
        document.fonts.load("700 40px 'DM Sans'"),
      ]);
    } catch (e) {}
    if (document.fonts.ready) { try { await document.fonts.ready; } catch (e) {} }
  }
  handlePayload({action: "display", text: payload.text,
                 reference: payload.reference,
                 translation: payload.translation, theme_data: theme});
  await new Promise(function (r) { setTimeout(r, 180); });
  const vt = document.getElementById("verse-text");
  const vrt = document.getElementById("verse-ref-text");
  const vtr = document.getElementById("verse-ref-translation");
  window.__results.push({
    container: rect(document.getElementById("container")),
    textRange: rangeRect(vt),
    refRange: rangeRect(vrt),
    transRange: rangeRect(vtr),
    text: styles(vt),
    reference: styles(document.getElementById("verse-ref")),
    translation: styles(vtr),
  });
  const old = document.querySelector("script[data-rc]");
  if (old) old.remove();
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "results");
  tag.textContent = JSON.stringify(window.__results);
  document.body.appendChild(tag);
}
"""


@pytest.fixture(scope="module")
def v1_fixtures():
    assert FIXTURES_PATH.exists(), f"Missing {FIXTURES_PATH}"
    return json.loads(FIXTURES_PATH.read_text("utf-8"))


@pytest.fixture(scope="module")
def golden_render():
    assert GOLDEN_RENDER_PATH.exists(), f"Missing {GOLDEN_RENDER_PATH}"
    return json.loads(GOLDEN_RENDER_PATH.read_text("utf-8"))


# ─── 1. Deep Equality of Resolved v1 Migrated vs Resolved v2 File ───────────


@pytest.mark.parametrize("name,kind", SHIPPED_THEMES)
def test_shipped_themes_v1_migrated_deep_equals_v2_resolved(name, kind, v1_fixtures):
    """The resolved v1-migrated dict must deep-equal the resolved v2 file on disk."""
    v1_raw = v1_fixtures[name]
    v1_migrated = migrate_v1_to_v2(v1_raw, kind=kind)
    resolved_v1, report_v1 = normalize_theme(v1_migrated, kind=kind, name=name)
    assert report_v1.warnings == [], f"v1 migration had warnings: {report_v1.warnings}"

    # Resolve from disk via standard loader
    res_name, resolved_v2 = resolve_theme(name)
    assert res_name == name
    assert resolved_v2["schema_version"] == 2

    # Verify deep equality of all keys
    assert resolved_v1["kind"] == resolved_v2["kind"]
    assert resolved_v1["canvas"] == resolved_v2["canvas"]
    assert len(resolved_v1["containers"]) == len(resolved_v2["containers"])

    c1 = resolved_v1["containers"][0]
    c2 = resolved_v2["containers"][0]
    assert c1["id"] == c2["id"]
    assert c1["position"] == c2["position"]
    assert c1["width"] == c2["width"]
    assert c1["height"] == c2["height"]
    assert c1["background"] == c2["background"]
    assert c1["border"] == c2["border"]
    assert c1["border_radius"] == c2["border_radius"]
    assert c1["box_shadow"] == c2["box_shadow"]
    assert c1["blocks"] == c2["blocks"]

    assert resolved_v1 == resolved_v2, f"Discrepancy in resolved dict for {name}"


# ─── 2. Animation Equivalence ───────────────────────────────────────────────


def test_migrated_v1_animation_timing_and_phases_match_v2():
    """Verify that a migrated v1 animations dict maps onto the v2 container
    structure with exact phase timings and preset keyframes."""
    v1_doc = {
        "containers": {"main": {"x": 0, "y": 0, "text": {}}},
        "animations": {
            "display_enter": {"type": "fade_up", "duration_ms": 450},
            "between_slides": {
                "in_type": "scale_up",
                "out_type": "fade_down",
                "duration_ms": 350,
            },
            "display_exit": {"type": "fade_out", "duration_ms": 250},
        },
    }
    migrated = migrate_v1_to_v2(v1_doc, kind="scripture")
    resolved, report = normalize_theme(migrated, kind="scripture", name="anim_test")
    assert report.warnings == []

    anim = resolved["containers"][0]["animation"]
    registry = resolved["animations"]

    # 1. Entry phase
    assert anim["entry"]["use"] == "fade_up"
    assert anim["entry"]["duration_ms"] == 450
    assert "fade_up" in registry
    assert registry["fade_up"]["keyframes"] == BUILTIN_ANIMATIONS["fade_up"]["keyframes"]

    # 2. Transition phase
    trans = anim["transition"]
    assert trans["in"]["use"] == "scale_up"
    assert trans["in"]["duration_ms"] == 350
    assert "scale_up" in registry
    assert registry["scale_up"]["keyframes"] == BUILTIN_ANIMATIONS["scale_up"]["keyframes"]

    # 3. Exit phase
    assert anim["out"]["use"] == "fade_out"
    assert anim["out"]["duration_ms"] == 250
    assert "fade_out" in registry
    assert registry["fade_out"]["keyframes"] == BUILTIN_ANIMATIONS["fade_out"]["keyframes"]


# ─── 3. Real renderer vs the pre-v2 render oracle ──────────────────────────


def _build_page(theme: dict, payload: dict) -> str:
    html = (ROOT / "display/display.html").read_text()
    css = (ROOT / "display/themes.css").read_text()
    js = (ROOT / "display/display.js").read_text()
    # Deterministic geometry: use the bundled faces, never Google Fonts.
    # A network-fetched Nunito and the bundled one have different metrics,
    # and waiting on the network made this oracle flaky.
    html = re.sub(r'<link rel="preconnect"[^>]*>\s*', "", html)
    html = re.sub(r'<link href="https://fonts\.googleapis\.com[^>]*>\s*', "", html)
    css = css.replace("url('./fonts/",
                      "url('file://" + str(ROOT / "display/fonts") + "/")
    html = html.replace('<link rel="stylesheet" href="themes.css">',
                        f"<style>{css}</style>")
    html = html.replace('<script src="display.js"></script>',
                        f"<script>{js}</script>")
    html = html.replace(
        "</head>",
        "<script>window.WebSocket = function () {this.close = function () {};"
        "this.send = function () {}; this.readyState = 3;}</script></head>", 1)
    boot = ("<script>window.__theme = " + json.dumps(theme) + ";\n" + DRIVER
            + "__drive(window.__theme, " + json.dumps(payload) + ");</script>")
    return html.replace("</body>", boot + "</body>", 1)


def _render(theme: dict, payload: dict) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="rc-equivalence-"))
    try:
        page = tmp / "page.html"
        page.write_text(_build_page(theme, payload))
        out = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--window-size=1920,1080", "--force-device-scale-factor=1",
             f"--user-data-dir={tmp / 'profile'}", "--no-first-run",
             "--virtual-time-budget=4000", "--dump-dom", page.as_uri()],
            capture_output=True, text=True, timeout=120).stdout
        found = re.findall(
            r'<script[^>]*data-rc="results"[^>]*>(.*?)</script>', out, re.S)
        assert found, "renderer produced no results"
        return json.loads(found[-1])[0]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _font_family(value):
    """The first family is the one the browser actually uses."""
    if not value:
        return value
    return value.split(",")[0].strip().strip("'\"").lower()


@pytest.mark.skipif(CHROME is None, reason="no Chrome/Chromium available")
@pytest.mark.parametrize("name,kind", SHIPPED_THEMES)
@pytest.mark.parametrize("case", sorted(PAYLOADS))
def test_resolved_v2_renders_like_the_v1_renderer(name, kind, case, golden_render):
    """The shipped v2 themes must render pixel-identically to v1 at 1920x1080."""
    expected = golden_render[name][case]
    _, theme = resolve_theme(name)
    got = _render(theme, PAYLOADS[case])

    for label in ("container", "textRange", "refRange", "transRange"):
        exp_rect = expected.get(label)
        got_rect = got.get(label)
        assert (exp_rect is None) == (got_rect is None), \
            f"{name}/{case}: {label} presence differs"
        if exp_rect is None:
            continue
        for key in ("x", "y", "w", "h"):
            assert abs(got_rect[key] - exp_rect[key]) <= RECT_TOLERANCE, \
                (f"{name}/{case}: {label}.{key} moved "
                 f"{exp_rect[key]} -> {got_rect[key]}")

    for block in ("text", "reference", "translation"):
        exp_styles = expected.get(block)
        got_styles = got.get(block)
        assert (exp_styles is None) == (got_styles is None), \
            f"{name}/{case}: {block} block presence differs"
        if exp_styles is None:
            continue
        for prop in STYLE_PROPS:
            assert got_styles[prop] == exp_styles[prop], \
                f"{name}/{case}: {block}.{prop} {exp_styles[prop]!r} -> {got_styles[prop]!r}"
        assert _font_family(got_styles["fontFamily"]) == \
            _font_family(exp_styles["fontFamily"]), \
            f"{name}/{case}: {block}.fontFamily {exp_styles['fontFamily']!r} -> {got_styles['fontFamily']!r}"
