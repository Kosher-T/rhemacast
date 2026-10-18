"""Real-browser rendering tests for the display renderers.

`tests/test_display_js.py` evaluates the renderer scripts under a DOM stub,
which has no layout: the outline conversion cleanly no-ops there. That is
enough for parsing and determinism, but NOT for the render path — a stale
inline-formatting stash, a clipped outline or a spacing regression are only
visible in a browser that actually lays text out.

So these tests build a page from the real `display/display.html` + CSS + JS,
drive `handlePayload()` with a sequence of payloads, and assert on the DOM
that comes back. Skipped when no Chrome/Chromium is available.

The payload sequence matters as much as each payload: the bug this file
exists for only appeared on the payload AFTER a theme-outlined one.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CHROME = (shutil.which("google-chrome-stable")
          or shutil.which("google-chrome")
          or shutil.which("chromium")
          or shutil.which("chromium-browser"))

pytestmark = pytest.mark.skipif(CHROME is None,
                                reason="no Chrome/Chromium available")

# The OBS renderer and the copy embedded in the preview widget must render
# identically; both are driven through the same payload sequence.
RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]

TEXT = "The Williams Family"
# The marked-up runs spell exactly TEXT, so every case must end up displaying
# the same words: an outline may not add, drop or reorder a glyph.
OUTLINE_RUN = "The Williams [Family (outline=6px #ff2d55)]"
SHADOW_RUN = "The Williams [Family (shadow=10px 45% 6px #ff2d55 135)]"
# Over-max on purpose: stored 25px must clamp to the 12px max, never render thin.
WIDE_RUN = "The Williams [Family (outline=25px #ff2d55)]"

# The sequence is the point: theme outline -> inline shadow -> theme outline.
# Before the stash was invalidated on a new payload, the middle case lost its
# inline shadow to the previous payload's restored pristine HTML.
SEQUENCE = [
    ("plain", TEXT, None),
    ("theme_outline", TEXT, "8px #22d3ee"),
    ("inline_shadow", SHADOW_RUN, None),
    ("inline_outline", OUTLINE_RUN, None),
    ("shadow_again", SHADOW_RUN, None),
    ("wide", WIDE_RUN, None),
]

DRIVER = """
window.__results = [];
function __flush() {
  const old = document.querySelector("script[data-rc]");
  if (old) old.remove();
  const tag = document.createElement("script");
  tag.type = "text/plain";
  tag.setAttribute("data-rc", "results");
  tag.textContent = JSON.stringify(window.__results);
  document.body.appendChild(tag);
}
async function __drive(cases) {
  __flush();
  for (const c of cases) {
    const base = window.__realTheme || {};
    const theme = Object.assign({}, base,
      {text: Object.assign({}, base.text)});
    // Content blocks live in the active container; the flat top level is
    // only a fallback for hand-written themes.
    let textBlock = theme.text;
    const cnames = theme.containers && Object.keys(theme.containers);
    if (cnames && cnames.length) {
      const cont = Object.assign({}, theme.containers[cnames[0]]);
      theme.containers = Object.assign({}, theme.containers);
      theme.containers[cnames[0]] = cont;
      cont.text = Object.assign({}, cont.text);
      textBlock = cont.text;
    }
    delete textBlock.text_outline;
    delete textBlock.text_shadow;
    if (c.themeOutline) textBlock.text_outline = c.themeOutline;
    const vt = document.getElementById("verse-text");
    try {
      handlePayload({action: "display", text: c.text, reference: "Ps 133",
                     containers: {}, theme_data: theme});
      // a timer, not rAF: rAF never fires under --virtual-time-budget
      await new Promise(function (r) { setTimeout(r, 40); });
      const svgs = [...vt.querySelectorAll("svg")].map(function (s) {
        const b = s.getBoundingClientRect();
        return {w: Math.round(b.width), h: Math.round(b.height),
                x: Math.round(b.x), y: Math.round(b.y),
                // the attribute is in CSS px: unaffected by the preview's
                // body scale(), so widths can be compared across renderers
                attrW: parseInt(s.getAttribute("width"), 10),
                attrH: parseInt(s.getAttribute("height"), 10),
                stroke: (s.querySelector("text") || {}).getAttribute
                    ? s.querySelector("text").getAttribute("stroke-width") : null};
      });
      window.__results.push({
        name: c.name,
        svgs: svgs,
        hasShadow: /text-shadow/.test(vt.innerHTML),
        hasStroke: /-webkit-text-stroke/.test(vt.innerHTML),
        literal: /\\[Family \\(/.test(vt.textContent),
        text: vt.textContent,
        stash: vt.dataset.rcOcSrc !== undefined,
        box: [Math.round(vt.getBoundingClientRect().width),
              Math.round(vt.getBoundingClientRect().height)],
        fontPx: Math.round(parseFloat(getComputedStyle(vt).fontSize) * 10) / 10,
        overflowX: document.documentElement.scrollWidth -
                   document.documentElement.clientWidth,
      });
    } catch (e) {
      window.__results.push({name: c.name,
                             error: String(e && e.message ? e.message : e)});
    }
    __flush();
  }
  __flush();
}
"""


def _page_html(rel_path: str) -> str:
    """The page a renderer is actually served in.

    `display/display.js` runs in `display/display.html` with `themes.css`
    linked, so that page is rebuilt with both inlined. The preview copy is
    already shipped as a complete self-contained document
    (`display_view._DISPLAY_HTML` carries its own <style> and <script>), so
    it is used verbatim -- feeding it the OBS markup would test a page that
    does not exist.
    """
    if rel_path.endswith(".py"):
        # The document is a raw string that ends at the FIRST closing
        # triple quote (line 1128, "</html>\"\"\""). Using the last one
        # instead swallows the rest of the Python file, which yields a
        # malformed page (see the sibling test that boots the real page).
        src = (ROOT / rel_path).read_text()
        return src.split('_DISPLAY_HTML = r"""', 1)[1].split('"""', 1)[0]
    html = (ROOT / "display/display.html").read_text()
    css = (ROOT / "display/themes.css").read_text()
    js = (ROOT / rel_path).read_text()
    html = html.replace('<link rel="stylesheet" href="themes.css">',
                        f"<style>{css}</style>")
    html = html.replace('<script src="display.js"></script>',
                        f"<script>{js}</script>")
    return html


def _build_page(rel_path: str, tmp: Path) -> Path:
    """A self-contained page: real CSS + the renderer, no server needed."""
    html = _page_html(rel_path)
    html = re.sub(r'<script src="display\.js"></script>', "", html)
    html = html.replace(
        "</head>",
        "<script>window.WebSocket = function () {this.close = function () {};"
        "this.send = function () {}; this.readyState = 3;}</script></head>", 1)
    theme = json.loads((ROOT / "themes/freeform/slides.json").read_text())
    boot = ("<script>window.__realTheme = " + json.dumps(theme) + ";"
            + DRIVER +
            "__drive(" + json.dumps([
                {"name": n, "text": t, "themeOutline": o}
                for n, t, o in SEQUENCE]) + ");\n</script>")
    html = html.replace("</body>", boot + "</body>", 1)
    page = tmp / "page.html"
    page.write_text(html)
    return page


def _run(rel_path: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="rc-render-"))
    try:
        page = _build_page(rel_path, tmp)
        out = subprocess.run(
            [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--window-size=1400,700", f"--user-data-dir={tmp / 'profile'}",
             "--no-first-run", "--virtual-time-budget=8000", "--dump-dom",
             page.as_uri()],
            capture_output=True, text=True, timeout=120).stdout
        found = re.findall(
            r'<script[^>]*data-rc="results"[^>]*>(.*?)</script>', out, re.S)
        assert found, f"{rel_path}: renderer produced no results"
        rows = json.loads(found[-1])
        assert [r["name"] for r in rows] == [n for n, _, _ in SEQUENCE], rows
        return {r["name"]: r for r in rows}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def rendered():
    return {rel: _run(rel) for rel in RENDERERS}


@pytest.mark.parametrize("renderer", RENDERERS)
def test_inline_shadow_survives_a_previous_theme_outline(rendered, renderer):
    """A theme outline converts the whole block and stashes the pristine
    markup for re-conversion. The stash belongs to the payload that created
    it: on the NEXT payload, applyTheme must not restore it, or that
    payload's inline formatting is silently discarded."""
    rows = rendered[renderer]
    assert rows["theme_outline"]["svgs"], rows["theme_outline"]
    assert rows["inline_shadow"]["hasShadow"] is True, rows["inline_shadow"]
    assert rows["shadow_again"]["hasShadow"] is True, rows["shadow_again"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_no_payload_ever_renders_markup_literally(rendered, renderer):
    for name, row in rendered[renderer].items():
        assert row.get("literal") is False, (renderer, name, row.get("text"))


@pytest.mark.parametrize("renderer", RENDERERS)
def test_outline_is_never_a_text_stroke(rendered, renderer):
    """-webkit-text-stroke straddles the glyph path and eats the letters."""
    for name, row in rendered[renderer].items():
        assert row.get("hasStroke") is False, (renderer, name)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_wide_outline_is_not_clipped_to_a_thin_one(rendered, renderer):
    """An over-max stored outline (25px) clamps to the 12px max instead of
    collapsing to a thin one. The SVG viewport is padded by the full width,
    which is what keeps it inside the container."""
    from core.constants import OUTLINE_MAX_PX
    assert OUTLINE_MAX_PX == 12
    rows = rendered[renderer]
    narrow = rows["inline_outline"]
    wide = rows["wide"]
    assert narrow["svgs"] and wide["svgs"], (narrow, wide)
    # The viewport is padded by the full outline width on each side, so going
    # 6px -> clamped 12px must grow the SVG by 2 * (12 - 6) = 12 CSS px.
    # Compared in CSS px (the width attribute) because the preview scales
    # its whole DOM.
    grew = wide["svgs"][0]["attrW"] - narrow["svgs"][0]["attrW"]
    # Tolerant by 1px: each row's viewport is ceil(ink advance + 2 * pad) and
    # the two rows are measured independently, so sub-pixel rasterization
    # noise in the advance can push one ceil across an integer boundary.
    # A collapse to the thin outline (~0) or a missing clamp (~38) still fails.
    assert abs(grew - 2 * (OUTLINE_MAX_PX - 6)) <= 1, (
        narrow["svgs"][0], wide["svgs"][0])
    # ...and the stroke itself is the full max (2x half-width).
    assert wide["svgs"][0]["stroke"] == str(2 * OUTLINE_MAX_PX), wide["svgs"][0]
    assert narrow["svgs"][0]["stroke"] == "12", narrow["svgs"][0]
    # and it stays inside the container rather than clipping into a box. The
    # preview scales its whole DOM to fit the panel, so its document overflows
    # on its own; what matters is that the outline adds none.
    assert wide["overflowX"] <= rows["plain"]["overflowX"], (
        wide["overflowX"], rows["plain"]["overflowX"])


@pytest.mark.parametrize("renderer", RENDERERS)
def test_outline_does_not_change_the_text_or_its_size(rendered, renderer):
    """The stroke lives in a padded SVG viewport: the glyphs themselves, their
    advances and their computed font size must be untouched."""
    rows = rendered[renderer]
    assert rows["plain"]["fontPx"] == rows["inline_outline"]["fontPx"], rows
    assert rows["plain"]["fontPx"] == rows["wide"]["fontPx"], rows
    # the visible words are the same in every case. textContent counts
    # both paint layers of an outlined run (stroke + fill), so an outlined
    # "Family" reads twice in the DOM while painting once on screen; the
    # stroke layer is aria-hidden so assistive tech still reads it once.
    # A shadow is a plain style (no second layer) and reads once.
    # (The driver theme uppercases: conversion paints the transformed text
    # into both layers, replacing the mixed-case source node entirely.)
    assert rows["inline_outline"]["text"] == "The Williams FAMILYFAMILY", rows["inline_outline"]
    assert rows["wide"]["text"] == "The Williams FAMILYFAMILY", rows["wide"]
    assert rows["shadow_again"]["text"] == TEXT, rows["shadow_again"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_no_case_raises(rendered, renderer):
    for name, row in rendered[renderer].items():
        assert "error" not in row, (renderer, name, row["error"])