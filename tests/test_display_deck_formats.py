"""Real-browser rendering tests for TIER-4 deck formats on the display.

The deck's whole-display format (Every highlight tier 4: font, size, bold,
outline, shadow, case, align, color…) rides the payload as `slide_format`
and cascades OVER the theme text in `applyTheme(theme, slideFormat)`. The
payload-only checks of the designer/ribbon suites cannot see the render:
this file drives the real `handlePayload` in headless Chrome and asserts
the text element's COMPUTED styles, for both renderers (the OBS page and
the designer-preview embed must stay identical).

Locked here after the auto-fit regression it fixes: autoFitText picked
any size between the theme's min/max and silently swallowed the deck's
explicit `size=` (42 rendered as 61px).
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from tests.test_display_render_matrix import CHROME, pytestmark  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]

# The OBS renderer and the copy embedded in the preview widget must render
# identically; both are driven through the same payload sequence.
RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]

TEXT = "The Williams Family"

# Every knob a tier-4 highlight can set, in one payload. Align its values
# against the "slides" theme's defaults (weight 800, uppercase, Nunito,
# outline 6px black, no shadow) so each assertion proves the DECK layer.
DECK_FULL = {
    "size_nominal": 42, "size_min": None, "size_max": None,
    "bold": True, "color": "#00FF00", "italics": True,
    "case": "upper", "underline": True, "strike": False,
    "align": "left", "spacing": None, "dir": None,
    "outline": "6px #FF0000", "shadow": "8px 100% 3px #000000 45",
    "font": "Georgia",
}
DECK_SIZE_ONLY = {"size_nominal": 48, "size_min": None, "size_max": None,
                  "bold": None, "color": None, "italics": None, "case": None,
                  "underline": None, "strike": None, "align": None,
                  "spacing": None, "super": None, "sub": None,
                  "outline": None, "shadow": None, "dir": None, "hr": None,
                  "font": None}

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
    const vt = document.getElementById("verse-text");
    try {
      const payload = {action: "display", text: c.text,
                       reference: "Ps 133", containers: {},
                       theme_data: window.__realTheme};
      if (c.mode === "theme_only") {
        applyTheme(window.__realTheme);   // py pushTheme: no slideFormat arg
      } else {
        payload.slide_format = c.format;
      }
      handlePayload(payload);
      await new Promise(function (r) { setTimeout(r, 60); });
      const cs = getComputedStyle(vt);
      const svgs = [...vt.querySelectorAll("svg")].map(function (s) {
        const t = s.querySelector("text");
        return {w: parseInt(s.getAttribute("width"), 10),
                h: parseInt(s.getAttribute("height"), 10),
                strokeW: t ? t.getAttribute("stroke-width") : null};
      });
      window.__results.push({
        name: c.name,
        fontSize: cs.fontSize,
        fontFamily: cs.fontFamily.slice(0, 40),
        fontWeight: cs.fontWeight,
        fontStyle: cs.fontStyle,
        textTransform: cs.textTransform,
        textDecoration: cs.textDecorationLine,
        textAlign: cs.textAlign,
        color: cs.color,
        textShadow: cs.textShadow,
        svgs: svgs,
        text: vt.textContent,
      });
    } catch (e) {
      window.__results.push({name: c.name, error: String(e)});
    }
    __flush();
  }
}
"""

# The order is the contract: deck applied -> pure theme re-apply (deck KiLL
# must survive) -> deck cleared (slide_format null: verse takes the free
# theme fit back).
SEQUENCE = [
    {"name": "deck_full", "text": TEXT, "mode": "format", "format": DECK_FULL},
    {"name": "theme_reapply", "text": TEXT, "mode": "theme_only"},
    {"name": "deck_full_again", "text": TEXT, "mode": "format",
     "format": DECK_FULL},
    {"name": "deck_size_only", "text": TEXT, "mode": "format",
     "format": DECK_SIZE_ONLY},
    {"name": "deck_cleared", "text": TEXT, "mode": "format", "format": None},
]


def _page_html(rel_path: str) -> str:
    """The page a renderer is actually served in (same rule as the matrix)."""
    if rel_path.endswith(".py"):
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


def _run(rel_path: str) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="rc-deck-fmt-"))
    try:
        html = _page_html(rel_path)
        html = re.sub(r'<script src="display\.js"></script>', "", html)
        html = html.replace(
            "</head>",
            "<script>window.WebSocket = function () {this.close = "
            "function () {};this.send = function () {};this.readyState = 3;}"
            "</script></head>", 1)
        theme = json.loads(
            (ROOT / "themes/freeform/slides.json").read_text())
        boot = ("<script>window.__realTheme = " + json.dumps(theme) + ";"
                + DRIVER + "__drive(" + json.dumps(SEQUENCE) + ");\n</script>")
        html = html.replace("</body>", boot + "</body>", 1)
        page = tmp / "page.html"
        page.write_text(html)
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
        assert [r["name"] for r in rows] == [c["name"] for c in SEQUENCE], rows
        return {r["name"]: r for r in rows}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture(scope="module")
def rendered():
    return {rel: _run(rel) for rel in RENDERERS}


def test_deck_size_is_honored_exactly_when_it_fits(rendered):
    """A deck `size=42` renders 42px — the fit may neither grow past it
    (auto-fit's free range) nor floor just under it (41.98 binary step)."""
    for rel, rows in rendered.items():
        assert rows["deck_full"]["fontSize"] == "42px", (rel, rows["deck_full"])
        assert rows["deck_size_only"]["fontSize"] == "48px", (
            rel, rows["deck_size_only"])


def test_deck_size_survives_a_plain_theme_reapply(rendered):
    """apply_theme pushes the theme WITHOUT slide_format: the on-screen
    deck's size must stay (it is not a content switch, only a skin)."""
    for rel, rows in rendered.items():
        assert rows["theme_reapply"]["fontSize"] == "42px", rel


def test_deck_style_cleared_lets_the_free_fit_back(rendered):
    """slide_format:null (deck -> verse switch) must drop everything the
    deck layer set: sizing, face, posture, alignment all return to the
    theme's own rendering."""
    for rel, rows in rendered.items():
        row = rows["deck_cleared"]
        assert row["fontStyle"] == "normal", (rel, row)
        assert row["fontFamily"].startswith("Nunito"), (rel, row)
        assert row["textDecoration"] == "none", (rel, row)
        assert row["textAlign"] == "center", (rel, row)
        assert row["fontSize"] != "42px", (rel, row)


def test_deck_font_weight_style_and_case_render(rendered):
    for rel, rows in rendered.items():
        row = rows["deck_full"]
        assert row["fontWeight"] == "800", (rel, row)
        assert row["fontStyle"] == "italic", (rel, row)
        assert row["textTransform"] == "uppercase", (rel, row)
        assert "Georgia" in row["fontFamily"], (rel, row)


def test_deck_align_and_color_and_decoration_render(rendered):
    for rel, rows in rendered.items():
        row = rows["deck_full"]
        assert row["textAlign"] == "left", (rel, row)
        assert row["color"] == "rgb(0, 255, 0)", (rel, row)
        assert "underline" in row["textDecoration"], (rel, row)


def test_deck_shadow_rings_the_theme_shadow(rendered):
    """The deck shadow is stored canonically and converts to a CSS ring
    replacing the theme's. 8px 100% 3px #000000 45 -> computed offset ring."""
    for rel, rows in rendered.items():
        row = rows["deck_full"]
        assert re.search(r"(\d+)px", row["textShadow"]), (rel, row)
        assert re.search(r"rgba?\(?\s*0?\s*,", row["textShadow"].lower()) or \
            "rgb(0, 0, 0)" in row["textShadow"], (rel, row)


def test_deck_outline_is_a_real_stroke_copy(rendered):
    """The deck outline converts the text to the layered stroke copy (an
    SVG behind opaque glyphs), not a text-stroke. Theme outline notes
    `svgs` may also exist for the theme itself — assert at least one."""
    for rel, rows in rendered.items():
        row = rows["deck_full"]
        assert row["svgs"], (rel, row)
        stroke = row["svgs"][-1].get("strokeW")
        assert stroke is not None and int(stroke) > 0, (rel, row)
