"""The display renderers are plain JS duplicated in two places
(`display/display.js` for OBS and the copy embedded in
`ui/widgets/display_view.py` for the preview). Node is used to evaluate the
real scripts and assert their behaviour, so a divergence or a silent
"render the markup literally" fallback cannot ship unnoticed.

Skipped when node is unavailable; the Python-side contract is covered
separately in tests/test_slide_edit.py.
"""

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from core.constants import OVERLAP_IN_OFFSET_MS as RC_OFFSET

ROOT = Path(__file__).resolve().parents[1]
STUB = Path(__file__).with_name("jsdom_stub.js")

pytestmark = pytest.mark.skipif(shutil.which("node") is None,
                                reason="node not available")


def _script_text(rel_path: str) -> str:
    """The runnable JS of one renderer (display.js, or the embedded copy)."""
    src = (ROOT / rel_path).read_text()
    if rel_path.endswith(".py"):
        html = src.split('_DISPLAY_HTML = r"""', 1)[1].split('"""', 1)[0]
        src = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
    return src


def run(rel_path: str, body: str):
    """Evaluate a renderer under the DOM stub and return its console output."""
    defaults = (ROOT / "display" / "animation_defaults.js").read_text()
    harness = (STUB.read_text() + "\n" + defaults + "\n"
               + _script_text(rel_path) + "\n" + body)
    # The renderers are ~126 KB, and Linux caps one argv string at 128 KiB, so
    # `node -e <harness>` overflows once the stub is prepended. Write the
    # harness to a file and run that instead.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(harness)
        harness_path = fh.name
    try:
        out = subprocess.run(["node", harness_path], capture_output=True,
                             text=True, timeout=60)
    finally:
        Path(harness_path).unlink(missing_ok=True)
    if out.returncode != 0:
        raise AssertionError(f"{rel_path} failed:\n{out.stderr[-2000:]}")
    # The scripts log their own lines (e.g. "Attempting WebSocket connection"),
    # so take the LAST line that parses as JSON.
    for line in reversed(out.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("[") or line.startswith("{"):
            return json.loads(line)
    raise AssertionError(f"{rel_path} produced no JSON: {out.stdout[-500:]}")


RENDERERS = ["display/display.js", "ui/widgets/display_view.py"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_border_draw_helpers_agree(renderer):
    """Direction parsing and the rounded path are shared pure helpers."""
    body = """
const path = _roundedRectPathData(100, 60, 8, "top");
console.log(JSON.stringify({
  clockwise: _borderDirection("clockwise"),
  counter: _borderDirection("counterclockwise"),
  start_left: _borderDirection("start:left counterclockwise"),
  square: _roundedRectPathData(100, 60, 0, "right"),
  path: path,
}));
"""
    out = run(renderer, body)
    assert out["clockwise"] == {"start": "top", "clockwise": True}
    assert out["counter"] == {"start": "top", "clockwise": False}
    assert out["start_left"] == {"start": "left", "clockwise": False}
    assert out["square"].startswith("M 100 0 V 60")
    assert out["path"].startswith("M 8 0 H 92")
    assert out["path"].endswith(" Z")


@pytest.mark.parametrize("renderer", RENDERERS)
def test_outline_width_bounds_match_core_constants(renderer):
    """The JS renderers cannot import core.constants, so the 1..12 outline
    bounds are written out in each parser. They must not drift from the
    Python source of truth: the ribbon clamps to those constants."""
    from core.constants import OUTLINE_MAX_PX, OUTLINE_MIN_PX
    src = _script_text(renderer)
    assert f"Math.max({OUTLINE_MIN_PX}, Math.min({OUTLINE_MAX_PX}," in src, (
        renderer)
    assert f"Math.min({OUTLINE_MAX_PX}, Math.max({OUTLINE_MIN_PX}," in src, (
        renderer)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_outline_caps_at_the_declared_maximum(renderer):
    """A wide outline stays renderable at the max instead of collapsing to a
    thin one: the SVG viewport is padded by the full width, so even the max
    stays inside the container rather than clipping into a box."""
    from core.constants import OUTLINE_MAX_PX
    body = """
console.log(JSON.stringify({
  parts: _outlineParts("%dpx #ff0000"),
  at_max: _outlineParts("%dpx #ff0000"),
  over: _outlineParts("%dpx #ff0000"),
}));
""" % (OUTLINE_MAX_PX, OUTLINE_MAX_PX, OUTLINE_MAX_PX + 500)
    out = run(renderer, body)
    assert out["parts"]["width"] == OUTLINE_MAX_PX, (renderer, out)
    assert out["at_max"]["width"] == OUTLINE_MAX_PX, (renderer, out)
    assert out["over"]["width"] == OUTLINE_MAX_PX, (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_canvas_always_scales_into_its_surface_and_ignores_legacy_fit(renderer):
    """There is no ``canvas.fit`` any more: the canvas always behaves the way
    "contain" used to in the output (and the way the preview always did). A
    legacy theme file that still carries ``fit: "none"`` must render
    identically to one without the key."""
    body = """
function probe(preview, extra) {
    window.__RC_PREVIEW = preview;
    var canvas = {width: 960, height: 540, background: "#102030"};
    if (extra) canvas.fit = extra;
    applyCanvas(canvas);
    var stg = document.getElementById("stage");
    return {tf: stg.style.transform, w: stg.style.width, h: stg.style.height,
            bg: stg.style.background};
}
console.log(JSON.stringify({
    plain: probe(false, null),
    legacy_none: probe(false, "none"),
    preview: probe(true, "none"),
}));
"""
    out = run(renderer, body)
    # 1920x1080 viewport, 960x540 canvas -> exactly 2x, no letterbox offset.
    assert out["plain"]["tf"] == "translate(0px, 0px) scale(2)", (renderer, out)
    assert out["plain"]["w"] == "960px", (renderer, out)
    assert out["plain"]["h"] == "540px", (renderer, out)
    assert out["plain"]["bg"] == "#102030", (renderer, out)
    # A stray legacy key changes nothing in the output.
    assert out["legacy_none"] == out["plain"], (renderer, out)
    # The preview contains the whole canvas too...
    assert out["preview"]["tf"] == "translate(0px, 0px) scale(2)", (renderer, out)
    assert out["preview"]["w"] == "960px", (renderer, out)
    # ...and a transparent canvas paints nothing, not the word "transparent".
    assert out["preview"]["bg"] == "#102030", (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_preview_fits_any_canvas_into_the_fixed_16_9_stage(renderer):
    """A wide LED wall and a portrait canvas are letter/pillarboxed in the
    preview: the whole canvas is scaled into a centred 16:9 box, never
    reshaped or cropped, and the background fills the whole canvas."""
    body = """
function probe(w, h, bg) {
    applyCanvas({width: w, height: h, background: bg});
    const stg = document.getElementById("stage");
    const m = /translate\\(([-\\d.]+)px, ([-\\d.]+)px\\) scale\\(([\\d.]+)\\)/
        .exec(stg.style.transform);
    return {scale: +m[3], left: +m[1], top: +m[2],
            w: stg.style.width, h: stg.style.height,
            bg: stg.style.background};
}
window.__RC_PREVIEW = true;
console.log(JSON.stringify({
    wide: probe(4270, 1080, "#204060"),
    hd: probe(1920, 1080, "#204060"),
    portrait: probe(1080, 1920, "#204060"),
}));
"""
    out = run(renderer, body)
    # 1920x1080 stage: a 4270x1080 wall is letterboxed top and bottom.
    wide = out["wide"]
    assert abs(wide["scale"] - 1920 / 4270) < 1e-6, (renderer, out)
    assert abs(wide["top"] - (1080 - 1080 * wide["scale"]) / 2) < 1e-6
    assert wide["left"] == 0
    assert wide["w"] == "4270px" and wide["h"] == "1080px"
    assert wide["bg"] == "#204060"
    # A matching 16:9 canvas fills the stage exactly.
    assert out["hd"]["scale"] == 1 and out["hd"]["left"] == 0
    assert out["hd"]["top"] == 0
    # 1080x1920 is pillarboxed left and right.
    portrait = out["portrait"]
    assert abs(portrait["scale"] - 1080 / 1920) < 1e-6, (renderer, out)
    assert abs(portrait["left"] - (1920 - 1080 * portrait["scale"]) / 2) < 1e-6
    assert portrait["top"] == 0
    assert portrait["w"] == "1080px" and portrait["h"] == "1920px"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_legacy_containers_use_the_canvas_not_a_1920_box(renderer):
    """Positions are canvas pixels. A fixed 1920x1080 wrapper pushed every
    verse into the left edge of a 4270x1080 wall and clipped the rest."""
    body = """
const theme = {
    canvas: {width: 4270, height: 1080, background: "transparent", fit: "contain"},
    containers: {
        text: {x: 2135, y: 540, width: 3600, height: 600},
        reference: {x: 2135, y: 900, width: 1200, height: 90},
        translation: {x: 2135, y: 1000, width: 400, height: 40}
    }
};
_applyContainers(theme);
const c = document.getElementById("container");
const t = document.getElementById("ct-text");
console.log(JSON.stringify({w: c.style.width, h: c.style.height,
                            left: t.style.left, top: t.style.top}));
"""
    out = run(renderer, body)
    assert out["w"] == "4270px", (renderer, out)
    assert out["h"] == "1080px", (renderer, out)
    # Centred on the canvas: x - width / 2, not clamped to a 1920 frame.
    assert out["left"] == "335px", (renderer, out)
    assert out["top"] == "240px", (renderer, out)


def _inline_render_cases():
    return """
const cases = [
  "[AMEN, AMEN (OUTLINE=NONE)]",
  "IT IS SO [WORD (outline=none)]",
  "IT IS SO [WORD (outline=off)]",
  "IT IS SO [WORD (outline=15px #000000)]",
  "IT IS SO [WORD (outline=OFF)]",
  "[AMEN, AMEN (OUTLINE=20PX #000000; SHADOW=NONE)]",
  "[AMEN, AMEN (Outline=4Px #ABCDEF; Shadow=Off)]",
  "IT IS SO [WORD (bold=true)]",
  "IT IS SO [WORD (shadow=8px 40% 3px #000000)]",
];
console.log(JSON.stringify(cases.map(c => renderInlineColors(c))));
"""


SHADOW_CASES = [
    "8px 40% 3px #000000",       # no angle -> default 45
    "8px 40% 3px #000000 45",    # explicit angle
    "8px 40% 3px #000000 135",   # down-left
    "4px #000",                  # short form: no opacity/distance/angle
    "none",
    "8px 40% 3px #000000 90deg", # deg suffix
    "8px 40% 3px #000000 banana",  # junk -> rejected
    "8px 40% 3px 45",            # no color -> rejected
]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_shadow_parser_matches_python_exactly(renderer):
    """The 5-part shadow value is a wire format: a run's stored string is
    parsed by the ribbon (Python) and by both renderers (JS). If the two
    disagree on what an angle means, the operator's control and what OBS
    shows drift apart."""
    import math

    from core.slide_parser import _parse_shadow

    expected = []
    for value in SHADOW_CASES:
        parsed = _parse_shadow(value)
        assert parsed is None or parsed == "none" or parsed.count(" ") == 4, parsed
        expected.append({"input": value, "parsed": parsed})

    body = """
const cases = %s;
console.log(JSON.stringify(cases.map(function (c) {
  const p = _parseShadow(c);
  if (p === null || p === "none") return {parsed: p === null ? null : p};
  return {parsed: p, size: p.size, opacity: p.opacity, distance: p.distance,
          color: p.color, angle: p.angle, ring: _shadowRing(p)};
})));
""" % json.dumps(SHADOW_CASES)
    got = run(renderer, body)

    for exp, actual in zip(expected, got):
        # "none" is the one value both sides hand back verbatim; everything
        # else Python normalizes to a canonical string and JS to an object,
        # so agreement is checked on the decoded fields below.
        if exp["parsed"] is None or exp["parsed"] == "none":
            assert actual["parsed"] == exp["parsed"], (
                f"{renderer}: {exp['input']!r} -> {actual['parsed']!r}, "
                f"python says {exp['parsed']!r}")
            continue
        # both must agree on every decoded field...
        size, rest = exp["parsed"].split(" ", 1)
        opacity, rest = rest.split(" ", 1)
        distance, rest = rest.split(" ", 1)
        color, _, angle = rest.rpartition(" ")
        want = {"size": int(size[:-2]), "opacity": int(opacity[:-1]),
                "distance": int(distance[:-2]), "color": color,
                "angle": int(angle)}
        for field, value in want.items():
            assert actual[field] == value, (
                f"{renderer}: {exp['input']!r} {field}: "
                f"{actual[field]!r} != python {value!r}")
        # ...and the single shadow sits exactly at distance/angle with
        # blur=size: "dxpx dypx blurpx paint". No slack anymore — one
        # shadow, one deterministic string.
        from core.slide_parser import color_a
        ox = round(want["distance"] * math.cos(math.radians(want["angle"])))
        oy = round(want["distance"] * math.sin(math.radians(want["angle"])))
        alpha = want["opacity"] / 100
        paint = want["color"] if alpha >= 1 else color_a(want["color"], alpha)
        assert actual["ring"] == (
            f"{ox}px {oy}px {want['size']}px {paint}"), (
            f"{renderer}: {exp['input']!r} -> {actual['ring']!r}")


@pytest.mark.parametrize("renderer", RENDERERS)
def test_inline_markup_always_renders_never_literal(renderer):
    """A run whose params are all valid must become a <span>. Falling through
    to the literal branch shows the operator the raw markup on screen."""
    out = run(renderer, _inline_render_cases())
    assert len(out) == 9, out
    for src, html in zip(
            ["[AMEN, AMEN (OUTLINE=NONE)]", "outline=none", "outline=off",
             "outline=15px", "outline=OFF", "upper-20PX", "upper-4Px",
             "bold=true", "shadow"], out):
        assert "<span" in html, f"{renderer}: {src!r} rendered literally -> {html!r}"
        assert "[" not in html, f"{renderer}: {src!r} leaked markup -> {html!r}"


def test_explicit_outline_off_kills_the_inherited_outline():
    """outline=none must actively suppress the inherited outline/shadow."""
    cases = """
console.log(JSON.stringify([
  renderInlineColors("x [y (outline=none)] z"),
  renderInlineColors("x [y (outline=4px #ff0000)] z"),
]));
"""
    for renderer in RENDERERS:
        off, on = run(renderer, cases)
        assert "text-shadow:none" in off, (renderer, off)
        assert "rc-oc" not in off, (renderer, off)
        assert "text-shadow:none" not in on, (renderer, on)


def test_outline_ring_is_deterministic_and_clamped():
    """Same input, same ring, every call: the ring is a pure function of
    (width, color) with no layout, cache, or font dependence. Width clamps to
    the outline's 1-12 range; garbage yields no ring."""
    body = """
console.log(JSON.stringify({
  twice: _outlineRing("6px #ff0000") === _outlineRing("6px #ff0000"),
  upper: _outlineRing("6PX #ABCDEF"),
  clamped: _outlineRing("999px #000000").split(",")[0],
  wide: _outlineRing("99px #000000").split(",")[0],
  floored: _outlineRing("0px #000000").split(",")[0],
  bare: _outlineRing("#f00").split(",")[0],
  garbage: _outlineRing("banana"),
  none: _outlineRing("none"),
}));
"""
    for renderer in RENDERERS:
        out = run(renderer, body)
        assert out["twice"] is True, (renderer, out)
        assert out["upper"].startswith("6px 0px 0 #abcdef"), (renderer, out)
        assert out["clamped"].startswith("12px"), (renderer, out)
        assert out["wide"].startswith("12px"), (renderer, out)
        assert out["floored"].startswith("1px"), (renderer, out)
        assert out["bare"].startswith("1px 0px 0 #ff0000"), (renderer, out)
        assert out["garbage"] == "", (renderer, out)
        assert out["none"] == "", (renderer, out)


def test_explicit_outline_none_beats_a_hard_shadow_in_js():
    """Mirrors the Python contract: text_outline:none wins over text_shadow."""
    hard = ("-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, "
            "-2px 0 0 #000, 2px 0 0 #000, 0 -2px 0 #000, 0 2px 0 #000")
    body = ("const hard = %s;\n"
            "console.log(JSON.stringify([_themeOutline({text_shadow: hard}), "
            "_themeOutline({text_outline: 'none', text_shadow: hard})]));\n"
            % __import__('json').dumps(hard))
    for renderer in RENDERERS:
        hard_ring, explicit_none = run(renderer, body)
        assert hard_ring and "0 transparent" not in hard_ring, (renderer, hard_ring)
        assert explicit_none == "", (renderer, explicit_none)


def test_theme_outline_matches_across_renderers():
    """Same theme in, same outline out — Python (core/theme_loader) included."""
    from core.theme_loader import theme_outline
    themes = [
        {"text_shadow": "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, "
                        "2px 2px 0 #000, -2px 0 0 #000, 2px 0 0 #000, "
                        "0 -2px 0 #000, 0 2px 0 #000"},
        {"text_shadow": "0 4px 12px rgba(0, 0, 0, 0.4)"},
        {"text_outline": "12px #abcdef"},
        {"text_outline": "none"},
        {},
    ]
    body = ("const themes = %s;\n"
            "console.log(JSON.stringify(themes.map(t => _themeOutline(t))));\n"
            % json.dumps(themes))
    for renderer in RENDERERS:
        js = run(renderer, body)
        for theme, got in zip(themes, js):
            want = theme_outline(theme)
            # Both sides return the canonical VALUE ("4px #000000"): the SVG
            # builder parses it later, so any drift breaks the block outline.
            assert (got or "") == (want or ""), (renderer, theme, got, want)

def _theme_vars_body(cases):
    """applyTheme per case, read back the outline/shadow vars. Conversion
    may warn under the stub (no layout); warnings are non-JSON lines the
    harness skips — only a throw surfaces, wrapped per case."""
    return (
        "const cases = %s;\n"
        "const out = cases.map(([theme, fmt]) => {\n"
        "  try {\n"
        "    applyTheme(theme, fmt);\n"
        "    const st = document.documentElement.style;\n"
        "    return [st.getPropertyValue('--rc-text-outline'),\n"
        "            st.getPropertyValue('--rc-text-shadow'),\n"
        "            st.getPropertyValue('--rc-text-outline-value')];\n"
        "  } catch (e) { return ['THREW:' + e.message, '', '']; }\n"
        "});\n"
        "console.log(JSON.stringify(out));\n"
    )


def test_theme_outline_with_shadow_none_paints_no_shadow():
    """The reported bug: outline + shadow none rendered a soft shadow.
    The shadow variable must resolve to none explicitly — an unset
    variable falls back to the stylesheet's default soft shadow."""
    hard = ("-2px -2px 0 #555, 2px -2px 0 #555, -2px 2px 0 #555, "
            "2px 2px 0 #555, -2px 0 0 #555, 2px 0 0 #555, "
            "0 -2px 0 #555, 0 2px 0 #555")
    cases = [
        # [theme, slideFormat] -> [outline, shadow, outline-value]
        ({"containers": {"main": {"text": {
            "text_outline": "4px #000000",
            "text_shadow": "0px 0% 0px #000000 0"}}}}, None),
        ({"containers": {"main": {"text": {
            "text_outline": "10px #000000",
            "text_shadow": "none"}}}}, None),
        ({"containers": {"main": {"text": {
            "text_outline": "4px #000000",
            "text_shadow": "0 4px 12px rgba(0, 0, 0, 0.4)"}}}}, None),
        ({"containers": {"main": {"text": {
            "text_shadow": "0 4px 12px rgba(0, 0, 0, 0.4)"}}}}, None),
        ({"containers": {"main": {"text": {"text_shadow": "none"}}}}, None),
        ({"containers": {"main": {"text": {}}}}, None),
        ({"containers": {"main": {"text": {"text_shadow": hard}}}}, None),
    ]
    want = [
        ("4px #000000", "none", ""),
        ("10px #000000", "none", ""),
        ("4px #000000", "0 4px 12px rgba(0, 0, 0, 0.4)", ""),
        ("", "0 4px 12px rgba(0, 0, 0, 0.4)", ""),
        ("", "none", ""),
        ("", "", ""),
        ("2px #555555", "", ""),
    ]
    body = _theme_vars_body(cases) % json.dumps(cases)
    for renderer in RENDERERS:
        got = run(renderer, body)
        assert got == [list(w) for w in want], (renderer, got)


def test_deck_shadow_beats_theme_shadow():
    """Top-script shadow converts from canonical storage to real CSS and
    wins over the theme; none kills the theme shadow deck-wide; absent
    or garbage leaves the theme's alone."""
    theme = {"containers": {"main": {"text": {
        "text_shadow": "0 4px 12px rgba(0, 0, 0, 0.4)"}}}}
    body = (
        "const theme = %s;\n"
        "const conv = _shadowRing(_parseShadow('8px 40%% 3px #ff0000 45'));\n"
        "const get = () => document.documentElement.style"
        ".getPropertyValue('--rc-text-shadow');\n"
        "const out = {};\n"
        "applyTheme(theme, {shadow: '8px 40%% 3px #ff0000 45'}); out.deck = get();\n"
        "applyTheme(theme, {shadow: 'none'}); out.none = get();\n"
        "applyTheme(theme, {}); out.absent = get();\n"
        "applyTheme(theme, {shadow: 'banana'}); out.garbage = get();\n"
        "console.log(JSON.stringify([out, conv]));\n"
    ) % json.dumps(theme)
    for renderer in RENDERERS:
        out, conv = run(renderer, body)
        assert out["deck"] == conv, (renderer, out)
        assert "255, 0, 0" in out["deck"] and "none" not in out["deck"], (renderer, out)
        assert out["none"] == "none", (renderer, out)
        assert out["absent"] == "0 4px 12px rgba(0, 0, 0, 0.4)", (renderer, out)
        assert out["garbage"] == "0 4px 12px rgba(0, 0, 0, 0.4)", (renderer, out)


def test_deck_outline_beats_theme_outline():
    """Top-script outline lands in --rc-text-outline-value (which the
    block converter reads first); none switches the theme outline off."""
    theme = {"containers": {"main": {"text": {"text_outline": "4px #000000"}}}}
    cases = [
        (theme, {"outline": "6px #ff0000"}),
        (theme, {"outline": "none"}),
        (theme, {}),
        (theme, None),
    ]
    want = ["6px #ff0000", "none", "", ""]
    body = _theme_vars_body(cases) % json.dumps(cases)
    for renderer in RENDERERS:
        got = run(renderer, body)
        assert [g[0] for g in got] == ["4px #000000"] * 4, (renderer, got)
        assert [g[2] for g in got] == want, (renderer, got)


def test_shadow_is_none_matrix():
    """none/off/blank/all-zero -> true; anything with a live knob, or
    unparseable junk (left to the browser), -> false."""
    body = """
console.log(JSON.stringify({
  none: _shadowIsNone("none"),
  off: _shadowIsNone("off"),
  blank: _shadowIsNone("  "),
  zero: _shadowIsNone("0px 0% 0px #000000 0"),
  zeroShort: _shadowIsNone("0 0 0 #000"),
  soft: _shadowIsNone("0 4px 12px rgba(0, 0, 0, 0.4)"),
  deck: _shadowIsNone("8px 40% 3px #000000 45"),
  junk: _shadowIsNone("banana"),
}));
"""
    for renderer in RENDERERS:
        out = run(renderer, body)
        assert out == {"none": True, "off": True, "blank": True,
                       "zero": True, "zeroShort": True, "soft": False,
                       "deck": False, "junk": False}, (renderer, out)


def test_inline_shadow_wins_over_theme_and_deck():
    """Per-character is the top of the chain: an inline shadow paints its
    own value under any theme/deck shadow, and inline none kills both."""
    body = """
console.log(JSON.stringify([
  renderInlineColors("a [b (shadow=8px 40% 3px #ff0000 45)] c"),
  renderInlineColors("a [b (shadow=none)] c"),
  renderInlineColors("a [b (outline=none)] c"),
]));
"""
    for renderer in RENDERERS:
        own, off, ooff = run(renderer, body)
        assert "255, 0, 0" in own, (renderer, own)
        assert "text-shadow:none" in off, (renderer, off)
        assert "text-shadow:none" in ooff, (renderer, ooff)


def _extract_fn(src: str, name: str) -> str:
    """One top-level `function name(...) {...}` body, brace-balanced
    (string/comment aware). Used to pin renderer-mirror equality."""
    start = src.index(f"function {name}(")
    i = src.index("{", start)
    depth, j, n = 0, i, len(src)
    quote, line_comment, block_comment, esc = None, False, False, False
    while j < n:
        ch = src[j]
        nxt = src[j + 1] if j + 1 < n else ""
        if line_comment:
            if ch == "\n":
                line_comment = False
        elif block_comment:
            if ch == "*" and nxt == "/":
                block_comment = False
                j += 1
        elif quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch == "/" and nxt == "/":
            line_comment = True
            j += 1
        elif ch == "/" and nxt == "*":
            block_comment = True
            j += 1
        elif ch in ("'", '"', "`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[start:j + 1]
        j += 1
    raise AssertionError(f"unbalanced function {name}")


def _renderer_sources():
    out = {}
    for rel in RENDERERS:
        out[rel] = _script_text(rel)
    return out


def test_outline_conversion_functions_match_across_renderers():
    """convertOutlineScope/_ocSnapshot must stay byte-identical between
    OBS and preview: a one-side fix ships a one-side bug."""
    srcs = _renderer_sources()
    a, b = (srcs[r] for r in RENDERERS)
    for name in ("convertOutlineScope", "_ocSnapshot"):
        assert _extract_fn(a, name) == _extract_fn(b, name), (
            f"{name} drifted between renderers")


def test_oc_apply_transform_matrix():
    """Case is baked into converted SVG text (measuring untransformed
    text while CSS renders transformed text drifts every word apart)."""
    body = """
console.log(JSON.stringify({
  upper: _ocApplyTransform("red outline", "uppercase"),
  lower: _ocApplyTransform("RED OUTLINE", "lowercase"),
  cap: _ocApplyTransform("red outline", "capitalize"),
  none: _ocApplyTransform("rEd OuTlInE", "none"),
  unknown: _ocApplyTransform("red outline", "full-width"),
}));
"""
    for renderer in RENDERERS:
        out = run(renderer, body)
        assert out == {"upper": "RED OUTLINE", "lower": "red outline",
                       "cap": "Red Outline", "none": "rEd OuTlInE",
                       "unknown": "red outline"}, (renderer, out)


def test_inline_none_runs_carry_opt_out_markers():
    """outline=/shadow=none runs emit data-rc-no markers: the block SVG
    conversion destroys their inline text-shadow:none, so it must know
    which runs opted out of the stroke and the inherited shadow."""
    body = """
console.log(JSON.stringify([
  renderInlineColors("a [b (outline=none)] c"),
  renderInlineColors("a [b (shadow=none)] c"),
  renderInlineColors("a [b (outline=none; shadow=none)] c"),
  renderInlineColors("a [b (color=#ff0000)] c"),
]));
"""
    for renderer in RENDERERS:
        o, s, both, plain = run(renderer, body)
        assert 'data-rc-no="outline"' in o, (renderer, o)
        assert "text-shadow:none" in o, (renderer, o)
        assert 'data-rc-no="shadow"' in s, (renderer, s)
        assert 'data-rc-no="outline shadow"' in both, (renderer, both)
        assert "data-rc-no" not in plain, (renderer, plain)


def test_oc_snapshot_reads_opt_out_markers():
    """Snapshot reports data-rc-no flags so converted tokens skip the
    stroke (outline off) and pin text-shadow:none (shadow off)."""
    body = """
globalThis.getComputedStyle = (el) => el._cs;
const base = { fontSize: "61px", fontWeight: "800", fontStyle: "normal",
  fontFamily: "X", letterSpacing: "1px", wordSpacing: "0px",
  textTransform: "uppercase", whiteSpace: "normal", color: "rgb(17,17,17)",
  textDecorationLine: "none", textShadow: "none" };
const fakeNode = (cs, no) => ({ parentElement: {
  _cs: cs, closest: (sel) => sel === "[data-rc-no]" ? no : null } });
const tag = { getAttribute: () => "outline shadow" };
const s = _ocSnapshot(fakeNode(base, tag));
const p = _ocSnapshot(fakeNode(base, null));
console.log(JSON.stringify([s, p]));
"""
    for renderer in RENDERERS:
        tagged, plain = run(renderer, body)
        assert tagged["noOutline"] is True, (renderer, tagged)
        assert tagged["noShadow"] is True, (renderer, tagged)
        assert plain["noOutline"] is False, (renderer, plain)
        assert plain["noShadow"] is False, (renderer, plain)


def test_oc_snapshot_preserves_deco_shadow_and_nested_outline():
    """The conversion snapshot must carry what SVG cannot infer:
    text-decoration (redrawn as lines), the run's own shadow (re-applied
    per tspan), and a nested run outline (innermost wins)."""
    body = """
globalThis.getComputedStyle = (el) => el._cs;
const base = { fontSize: "61px", fontWeight: "800", fontStyle: "normal",
  fontFamily: "X", letterSpacing: "1px", wordSpacing: "0px",
  textTransform: "uppercase", whiteSpace: "normal", color: "rgb(17,17,17)",
  textDecorationLine: "none", textShadow: "none" };
const fakeNode = (cs, marker) => ({ parentElement: {
  _cs: cs, closest: (sel) => marker } });
const marker = { getAttribute: (n) =>
  n === "data-rc-oc-w" ? "2" : "#ff0000" };
const decorated = _ocSnapshot(fakeNode(
  Object.assign({}, base, { textDecorationLine: "underline",
    textShadow: "rgb(255, 0, 0) 2px 2px 8px" }), marker));
const struck = _ocSnapshot(fakeNode(
  Object.assign({}, base, { textDecorationLine: "line-through" }), null));
const plain = _ocSnapshot(fakeNode(base, null));
console.log(JSON.stringify([decorated, struck, plain]));
"""
    for renderer in RENDERERS:
        decorated, struck, plain = run(renderer, body)
        assert decorated["deco"] == "underline", (renderer, decorated)
        assert "255" in decorated["shadow"], (renderer, decorated)
        assert (decorated["ouW"], decorated["ouC"]) == (2, "#ff0000"), (
            renderer, decorated)
        assert decorated["weight"] == "800", (renderer, decorated)
        assert decorated["transform"] == "uppercase", (renderer, decorated)
        assert struck["deco"] == "line-through", (renderer, struck)
        assert struck["ouW"] == 0 and struck["ouC"] == "", (renderer, struck)
        assert plain["deco"] == "none", (renderer, plain)
        assert plain["shadow"] == "none", (renderer, plain)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_position_anchors_and_keywords(renderer):
    """v2 positioning computes exact left/top coordinates matching spec."""
    body = """
const cases = [
  { anchor: "top_left", x: 10, y: 20 },
  { anchor: "top_right", x: 15, y: 25 },
  { anchor: "bottom_left", x: 30, y: 40 },
  { anchor: "bottom_right", x: 35, y: 45 },
  { anchor: "center", x: 0, y: 0 },
  { anchor: "center", x: 10, y: -10 },
  { anchor: "left", x: 50 },
  { anchor: "right", x: 50 },
  { anchor: "top", y: 60 },
  { anchor: "bottom", y: 70 },
  { anchor: "fill" },
];
const W = 1920, H = 1080, w = 600, h = 300;
const results = cases.map(c => _computePosition(c, w, h, W, H));
console.log(JSON.stringify(results));
"""
    results = run(renderer, body)
    assert results[0] == {"left": 10, "top": 20}
    assert results[1] == {"left": 1305, "top": 25}
    assert results[2] == {"left": 30, "top": 740}
    assert results[3] == {"left": 1285, "top": 735}
    assert results[4] == {"left": 660, "top": 390}
    assert results[5] == {"left": 670, "top": 380}
    assert results[6] == {"left": 50, "top": 390}
    assert results[7] == {"left": 1270, "top": 390}
    assert results[8] == {"left": 660, "top": 60}
    assert results[9] == {"left": 660, "top": 710}
    assert results[10] == {"left": 0, "top": 0, "width": 1920, "height": 1080}


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_percentage_math(renderer):
    """Percentages resolve against canvas width/height (1920x1080)."""
    body = """
const res = [
  _resolveLength("10%", 1920),
  _resolveLength("50%", 1080),
  _resolveLength("100px", 1920),
  _resolveLength(250, 1080),
];
console.log(JSON.stringify(res));
"""
    res = run(renderer, body)
    assert res == [192.0, 540.0, 100.0, 250.0]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_theme_container_and_blocks_resolution(renderer):
    """themeContainer and _getContainerBlocks resolve both v1 and v2 shapes."""
    body = """
const v2Theme = {
  schema_version: 2,
  containers: [
    {
      id: "verse",
      layer: 10,
      visible: true,
      position: { anchor: "top_left", x: 60, y: 40 },
      blocks: {
        text: { color: "#ffffff", size: 48 },
        body: { valign: "center", padding_top: 20 },
      }
    },
    {
      id: "citation",
      layer: 20,
      visible: true,
      blocks: {
        reference: { color: "#gold", position: "below_verse" },
        translation: { color: "#lime", position: "left_of_reference" }
      }
    }
  ]
};
const contVerse = themeContainer(v2Theme, "verse");
const blocksVerse = _getContainerBlocks(contVerse);
const contCit = themeContainer(v2Theme, "citation");
const blocksCit = _getContainerBlocks(contCit);

console.log(JSON.stringify({
  verseId: contVerse.id,
  verseColor: blocksVerse.text.color,
  versePaddingTop: blocksVerse.body.padding_top,
  citRefColor: blocksCit.reference.color,
  citTransPos: blocksCit.translation.position,
}));
"""
    res = run(renderer, body)
    assert res["verseId"] == "verse"
    assert res["verseColor"] == "#ffffff"
    assert res["versePaddingTop"] == 20
    assert res["citRefColor"] == "#gold"
    assert res["citTransPos"] == "left_of_reference"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_reference_and_translation_placement(renderer):
    """Reference above/below verse and translation relative positions reorder DOM."""
    body = """
const themeAbove = {
  schema_version: 2,
  containers: [{
    id: "main",
    blocks: {
      reference: { position: "above_verse" },
      translation: { position: "left_of_reference" }
    }
  }]
};
applyTheme(themeAbove);
const vt = document.getElementById("verse-text");
const vr = document.getElementById("verse-ref");
const vrt = document.getElementById("verse-ref-text");
const vrtl = document.getElementById("verse-ref-translation");
const vc = document.getElementById("verse-content");
const aboveRes = {
  refAboveVerse: vc.children.indexOf(vr) < vc.children.indexOf(vt),
  transLeftOfRef: vr.children.indexOf(vrtl) < vr.children.indexOf(vrt)
};

const themeBelow = {
  schema_version: 2,
  containers: [{
    id: "main",
    blocks: {
      reference: { position: "below_verse" },
      translation: { position: "right_of_reference" }
    }
  }]
};
applyTheme(themeBelow);
const belowRes = {
  refAboveVerse: vc.children.indexOf(vr) < vc.children.indexOf(vt),
  transLeftOfRef: vr.children.indexOf(vrtl) < vr.children.indexOf(vrt)
};
console.log(JSON.stringify({ above: aboveRes, below: belowRes }));
"""
    res = run(renderer, body)
    assert res["above"]["refAboveVerse"] is True
    assert res["above"]["transLeftOfRef"] is True
    assert res["below"]["refAboveVerse"] is False
    assert res["below"]["transLeftOfRef"] is False


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_block_visibility_toggles(renderer):
    """visible: false hides the corresponding block element."""
    body = """
const theme = {
  schema_version: 2,
  containers: [{
    id: "main",
    blocks: {
      text: { visible: false },
      reference: { visible: false },
      translation: { visible: false }
    }
  }]
};
applyTheme(theme);
const vt = document.getElementById("verse-text");
const vrt = document.getElementById("verse-ref-text");
const vrtl = document.getElementById("verse-ref-translation");
console.log(JSON.stringify({
  vtDisplay: vt.style.display,
  vrtDisplay: vrt.style.display,
  vrtlDisplay: vrtl.style.display
}));
"""
    res = run(renderer, body)
    assert res["vtDisplay"] == "none"
    assert res["vrtDisplay"] == "none"
    assert res["vrtlDisplay"] == "none"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_multi_container_payload_rendering(renderer):
    """A two-container scripture theme renders separate dynamic containers with layers and positions."""
    body = """
const payload = {
  action: "display",
  text: "For God so loved the world",
  reference: "John 3:16",
  translation: "NKJV",
  theme_data: {
    schema_version: 2,
    canvas: { width: 1920, height: 1080, fit: "contain" },
    containers: [
      {
        id: "verse",
        layer: 10,
        position: { anchor: "top_left", x: 60, y: 40 },
        width: 1800,
        height: 820,
        blocks: {
          text: { color: "#ffffff", size: 60 },
          body: { padding_top: 24, gap: 10 }
        }
      },
      {
        id: "citation",
        layer: 20,
        position: { anchor: "bottom_left", x: 60, y: 48 },
        width: 1800,
        height: 150,
        blocks: {
          reference: { color: "#gold", position: "below_verse" },
          translation: { color: "#lime", position: "right_of_reference" }
        }
      }
    ]
  }
};
handlePayload(payload);
const vCont = document.getElementById("rc-cont-verse");
const cCont = document.getElementById("rc-cont-citation");
console.log(JSON.stringify({
  vZIndex: vCont ? vCont.style.zIndex : null,
  cZIndex: cCont ? cCont.style.zIndex : null,
  vTop: vCont ? vCont.style.top : null,
  cTop: cCont ? cCont.style.top : null,
  vWidth: vCont ? vCont.style.width : null,
  vHeight: vCont ? vCont.style.height : null,
}));
"""
    res = run(renderer, body)
    assert res["vZIndex"] == 10
    assert res["cZIndex"] == 20
    assert res["vTop"] == "40px"
    assert res["cTop"] == "882px"
    assert res["vWidth"] == "1800px"
    assert res["vHeight"] == "820px"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_out_cloak_uncloak_keeps_exit_held(renderer):
    """Out -> Cloak -> Uncloak must not reveal content; In replays entry."""
    body = """
const theme = {
  schema_version: 2,
  containers: [{ id: "main", animation: { entry: "fade_in", out: "fade_out" } }],
  animations: {
    fade_in: { type: "fade_in", duration_ms: 100, delay_ms: 0, easing: "ease-out" },
    fade_out: { type: "fade_out", duration_ms: 100, delay_ms: 0, easing: "ease-out" }
  }
};
handlePayload({ action: "display", text: "A", reference: "1:1", theme_data: theme });
const shown = _motionState;
handlePayload({ action: "out" });
const out = _motionState;
handlePayload({ action: "out" });
const outTwice = _motionState;
handlePayload({ action: "cloak" });
const cloaked = [_motionState, _motionCovered];
handlePayload({ action: "uncloak", reveal: false });
const afterUncloak = _motionState;
handlePayload({ action: "in" });
const afterIn = _motionState;
console.log(JSON.stringify({ shown, out, outTwice, cloaked, afterUncloak, afterIn }));
"""
    res = run(renderer, body)
    assert res["shown"] == "shown"
    assert res["out"] == res["outTwice"] == "out"
    assert res["cloaked"] == ["cloaked", "out"]
    assert res["afterUncloak"] == "out"
    assert res["afterIn"] == "shown"


_MOTION_THEME = """
const MADEF = {
  fade_in: { type: "fade_in", duration_ms: 0, delay_ms: 0, easing: "ease-out" },
  fade_out: { type: "fade_out", duration_ms: 0, delay_ms: 0, easing: "ease-out" }
};
function motionTheme(name, withPhases) {
  const anim = withPhases
    ? { entry: "fade_in", out: "fade_out",
        transition: { in: "fade_in", out: "fade_out" } }
    : undefined;
  const containers = anim ? [{ id: "main", animation: anim }]
                          : [{ id: "main" }];
  return { schema_version: 2, name: name, containers: containers,
           animations: MADEF };
}
"""


@pytest.mark.parametrize("renderer", RENDERERS)
def test_cloak_hides_the_canvas_background(renderer):
    """Cloak blanks the page (canvas included); uncloak restores it."""
    body = _MOTION_THEME + """
const theme = motionTheme("t", false);
theme.canvas = { width: 1920, height: 1080, background: "#123456" };
handlePayload({ action: "display", kind: "scripture", text: "A",
                reference: "1:1", theme_data: theme });
const before = stage.style.visibility || "";
handlePayload({ action: "cloak" });
const cloaked = stage.style.visibility;
const state = window.__rcMotionState.state;
handlePayload({ action: "uncloak" });
const restored = stage.style.visibility || "";
console.log(JSON.stringify({ before, cloaked, state, restored }));
"""
    res = run(renderer, body)
    assert res["before"] == ""
    assert res["cloaked"] == "hidden"
    assert res["state"] == "cloaked"
    assert res["restored"] == ""


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_pairing_phases_by_kind(renderer):
    body = _MOTION_THEME + """
const a = motionTheme("a", true);
const b = motionTheme("b", true);

handlePayload({ action: "display", kind: "scripture", text: "A", reference: "1:1", theme_data: a });
handlePayload({ action: "display", kind: "scripture", text: "B", reference: "1:2", theme_data: b });
const scripturePair = window.__rcMotionState.plan;

handlePayload({ action: "display", kind: "scripture", text: "C", reference: "1:3", theme_data: a });
handlePayload({ action: "display", kind: "freeform", text: "D", theme_data: b });
const scriptureToFreeform = window.__rcMotionState.plan;

handlePayload({ action: "display", kind: "scripture", text: "E", reference: "1:4", theme_data: a });
const freeformToScripture = window.__rcMotionState.plan;

handlePayload({ action: "display", kind: "other", text: "F", theme_data: b });
const unlabelled = window.__rcMotionState.plan;

console.log(JSON.stringify({ scripturePair, scriptureToFreeform, freeformToScripture, unlabelled }));
"""
    res = run(renderer, body)
    assert res["scripturePair"]["phases"] == ["transition_out", "transition_in"]
    assert res["scriptureToFreeform"]["phases"] == ["out", "in"]
    assert res["freeformToScripture"]["phases"] == ["out", "in"]
    assert res["unlabelled"]["phases"] == ["out", "in"]
    assert res["unlabelled"]["old"] == "scripture"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_overlap_plan_carries_the_fixed_offset(renderer):
    """Both orderings publish the same plan shape; overlap adds the offset."""
    body = _MOTION_THEME + """
const overlapped = motionTheme("o", true);
overlapped.motion = { transition: "overlap", in_out: "overlap",
                      sustain_when_cloaked: "pause", deck_steps: "out_in" };
const plain = motionTheme("p", true);
handlePayload({ action: "display", kind: "scripture", text: "A",
                reference: "1:1", theme_data: plain });
handlePayload({ action: "display", kind: "scripture", text: "B",
                reference: "1:2", theme_data: overlapped });
const transitionPlan = window.__rcMotionState.plan;
handlePayload({ action: "display", kind: "freeform", text: "C",
                theme_data: overlapped });
const inOutPlan = window.__rcMotionState.plan;
console.log(JSON.stringify({ transitionPlan, inOutPlan }));
"""
    res = run(renderer, body)
    for plan in (res["transitionPlan"], res["inOutPlan"]):
        assert plan["order"] == "overlap"
        assert plan["offset_ms"] == RC_OFFSET
    assert res["transitionPlan"]["phases"] == ["transition_out",
                                                "transition_in"]
    assert res["inOutPlan"]["phases"] == ["out", "in"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_transition_pair_actually_animates(renderer):
    """Scripture pairing starts the out phase, then the in phase."""
    body = _MOTION_THEME + """
const slow = {
  schema_version: 2,
  containers: [{ id: "main", animation: {
    entry: "fade_in", out: "fade_out",
    transition: { in: "fade_in", out: "fade_out" } } }],
  animations: {
    fade_in: { type: "fade_in", duration_ms: 200, easing: "ease-out" },
    fade_out: { type: "fade_out", duration_ms: 200, easing: "ease-out" }
  }
};
const played = [];
const originalPlay = _playElementAnimation;
_playElementAnimation = function (el, def, opts) {
  played.push((opts && opts.phase) || "in");
  return originalPlay(el, def, opts);
};
handlePayload({ action: "display", kind: "scripture", text: "A", reference: "1:1", theme_data: slow });
setTimeout(function () {
  played.length = 0;
  handlePayload({ action: "display", kind: "scripture", text: "B", reference: "1:2", theme_data: slow });
  const outAnims = _animatedEls.size;
  setTimeout(function () {
    console.log(JSON.stringify({
      outAnims: outAnims, played: played.slice(),
      state: window.__rcMotionState.state,
      plan: window.__rcMotionState.plan
    }));
  }, 300);
}, 300);
"""
    res = run(renderer, body)
    assert res["outAnims"] >= 1
    assert "out" in res["played"]
    assert "in" in res["played"]
    assert res["state"] == "shown"
    assert res["plan"]["phases"] == ["transition_out", "transition_in"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_freeform_pair_plays_out_then_entry(renderer):
    body = _MOTION_THEME + """
const t = motionTheme("f", true);
const played = [];
const originalPlay = _playElementAnimation;
_playElementAnimation = function (el, def, opts) {
  played.push((opts && opts.phase) || "in");
  return originalPlay(el, def, opts);
};
handlePayload({ action: "display", kind: "freeform", text: "A", theme_data: t });
played.length = 0;
handlePayload({ action: "display", kind: "freeform", text: "B", theme_data: t });
console.log(JSON.stringify({
  played: played.slice(), plan: window.__rcMotionState.plan,
}));
"""
    res = run(renderer, body)
    assert res["plan"]["phases"] == ["out", "in"]
    assert res["played"][0] == "out"
    assert "entry" in res["played"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_no_transition_slots_plays_nothing_for_scripture_pairing(renderer):
    """Zero animation is the correct result when the theme has no slots.

    The pairing rule still says scripture -> scripture. A theme that only
    declares entry/out must not invent a transition: the old content is
    replaced with no motion rather than falling back to OUT/IN.
    """
    body = _MOTION_THEME + """
const t = {
  schema_version: 2,
  containers: [{ id: "main", animation: { entry: "fade_in", out: "fade_out" } }],
  animations: {
    fade_in: { type: "fade_in", duration_ms: 100, easing: "linear" },
    fade_out: { type: "fade_out", duration_ms: 100, easing: "linear" }
  }
};
const played = [];
const originalPlay = _playElementAnimation;
_playElementAnimation = function (el, def, opts) {
  played.push((opts && opts.phase) || "in");
  return originalPlay(el, def, opts);
};
handlePayload({ action: "display", kind: "scripture", text: "A", reference: "1:1", theme_data: t });
setTimeout(function () {
  played.length = 0;
  handlePayload({ action: "display", kind: "scripture", text: "B", reference: "1:2", theme_data: t });
  setTimeout(function () {
    console.log(JSON.stringify({
      played: played.slice(), plan: window.__rcMotionState.plan,
      text: document.getElementById("verse-text").innerHTML
    }));
  }, 300);
}, 300);
"""
    res = run(renderer, body)
    assert res["plan"]["phases"] == ["transition_out", "transition_in"]
    assert res["played"] == []
    assert "B" in res["text"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_no_transition_slots_still_plays_out_then_in_for_a_slide(renderer):
    """Scripture -> slide is not a scripture pair: it keeps OUT then IN.

    The same theme that is silent for scripture -> scripture must still run
    its declared out/entry slots when the content kind changes.
    """
    body = _MOTION_THEME + """
const t = {
  schema_version: 2,
  containers: [{ id: "main", animation: { entry: "fade_in", out: "fade_out" } }],
  animations: {
    fade_in: { type: "fade_in", duration_ms: 100, easing: "linear" },
    fade_out: { type: "fade_out", duration_ms: 100, easing: "linear" }
  }
};
const played = [];
const originalPlay = _playElementAnimation;
_playElementAnimation = function (el, def, opts) {
  played.push((opts && opts.phase) || "in");
  return originalPlay(el, def, opts);
};
handlePayload({ action: "display", kind: "scripture", text: "A", reference: "1:1", theme_data: t });
setTimeout(function () {
  played.length = 0;
  handlePayload({ action: "display", kind: "freeform", text: "B", theme_data: t });
  setTimeout(function () {
    console.log(JSON.stringify({
      played: played.slice(), plan: window.__rcMotionState.plan,
      text: document.getElementById("verse-text").innerHTML
    }));
  }, 300);
}, 300);
"""
    res = run(renderer, body)
    assert res["plan"]["phases"] == ["out", "in"]
    assert res["played"] == ["out", "entry"]
    assert "B" in res["text"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_unlabelled_payload_warns_and_is_treated_as_other(renderer):
    """A missing kind is visible, not silent, and never borrows scripture.

    The server stamps ``kind="other"`` at the wire boundary, so
    ``kind_missing`` is the only surviving evidence; both shapes must warn.
    """
    body = _MOTION_THEME + """
const t = motionTheme("u", true);
const warnings = [];
const originalWarn = console.warn;
console.warn = function () {
  warnings.push(Array.prototype.join.call(arguments, " "));
};
handlePayload({ action: "display", text: "A", reference: "1:1", theme_data: t });
const missing = {
  kind: window.__rcMotionState.kind,
  unlabelled: window.__rcMotionState.unlabelled,
  plan: window.__rcMotionState.plan,
};
handlePayload({ action: "display", kind: "scripture", text: "B", reference: "1:2", theme_data: t });
const labelled = {
  kind: window.__rcMotionState.kind,
  unlabelled: window.__rcMotionState.unlabelled,
  plan: window.__rcMotionState.plan,
};
handlePayload({ action: "display", kind: "other", kind_missing: true,
                text: "C", reference: "1:3", theme_data: t });
const stamped = {
  kind: window.__rcMotionState.kind,
  unlabelled: window.__rcMotionState.unlabelled,
  plan: window.__rcMotionState.plan,
};
console.warn = originalWarn;
console.log(JSON.stringify({ warnings: warnings, missing: missing,
                             labelled: labelled, stamped: stamped }));
"""
    res = run(renderer, body)
    # The first push is an entry: no pairing ran, so there is no plan. The
    # missing label is still recorded and warned about.
    assert res["missing"]["kind"] == "other"
    assert res["missing"]["unlabelled"] is True
    assert res["missing"]["plan"] is None
    assert res["labelled"]["kind"] == "scripture"
    assert res["labelled"]["unlabelled"] is False
    assert res["labelled"]["plan"]["phases"] == ["out", "in"]
    assert res["stamped"]["kind"] == "other"
    assert res["stamped"]["unlabelled"] is True
    assert res["stamped"]["plan"]["phases"] == ["out", "in"]
    assert sum("no kind" in w for w in res["warnings"]) == 2


@pytest.mark.parametrize("renderer", RENDERERS)
def test_theme_deck_steps_can_skip_out_in_inside_one_deck(renderer):
    """A freeform theme may make Prev/Next inside one deck instant."""
    body = _MOTION_THEME + """
const theme = motionTheme("deck", true);
theme.motion = { deck_steps: "instant" };
handlePayload({ action: "display", kind: "freeform", deck_id: 7,
                text: "A", theme_data: theme });
handlePayload({ action: "display", kind: "freeform", deck_id: 7,
                text: "B", theme_data: theme });
const inDeck = window.__rcMotionState.plan;
const state = window.__rcMotionState.state;
const animations = _animatedEls.size;
handlePayload({ action: "display", kind: "freeform", deck_id: 8,
                text: "C", theme_data: theme });
const crossDeck = window.__rcMotionState.plan;
console.log(JSON.stringify({
  inDeck: inDeck, crossDeck: crossDeck, state: state,
  animations: animations,
}));
"""
    res = run(renderer, body)
    assert res["inDeck"]["phases"] == []
    assert res["state"] == "shown"
    assert res["animations"] == 0
    assert res["crossDeck"]["phases"] == ["out", "in"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_pairing_without_phases_is_instant(renderer):
    """No transition slots: the switch is instant, never an exit/entry."""
    body = _MOTION_THEME + """
const bare = motionTheme("bare", false);
const exiting = { schema_version: 2, containers: [{ id: "main",
  animation: { entry: "fade_in", out: "fade_out" } }], animations: MADEF };
handlePayload({ action: "display", kind: "scripture", text: "A", reference: "1:1", theme_data: exiting });
handlePayload({ action: "display", kind: "scripture", text: "B", reference: "1:2", theme_data: bare });
const plan = window.__rcMotionState.plan;
const state = window.__rcMotionState.state;
const animations = _animatedEls.size;
console.log(JSON.stringify({ plan, state, animations }));
"""
    res = run(renderer, body)
    assert res["plan"]["phases"] == ["transition_out", "transition_in"]
    assert res["state"] == "shown"
    # The new theme has no transition slots: no exit or entry substituted.
    assert res["animations"] == 0


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_sustain_runs_until_stopped(renderer):
    """Sustain starts one infinite animation and Out cancels it."""
    body = """
const theme = {
  schema_version: 2,
  containers: [{ id: "main", animation: { sustain: "fade_up" } }],
  animations: { fade_up: { type: "fade_up", duration_ms: 200, delay_ms: 0,
                           easing: "ease-out" } }
};
const el = document.getElementById("rc-cont-main");
const orig = el.animate;
let iterations = null;
el.animate = function (frames, opts) {
  iterations = String(opts.iterations);
  return orig.call(el, frames, opts);
};
handlePayload({ action: "display", text: "A", reference: "1:1", theme_data: theme });
const started = iterations;
handlePayload({ action: "out" });
const afterOut = _motionState;
console.log(JSON.stringify({ started, afterOut }));
"""
    res = run(renderer, body)
    assert res["started"] == "Infinity"
    assert res["afterOut"] == "out"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_motion_cloak_remembers_shown_content(renderer):
    body = """
const theme = { schema_version: 2, containers: [{ id: "main" }] };
handlePayload({ action: "display", text: "A", reference: "1:1", theme_data: theme });
handlePayload({ action: "cloak" });
const cloaked = [_motionState, _motionCovered];
handlePayload({ action: "uncloak" });
console.log(JSON.stringify({ cloaked, after: _motionState }));
"""
    res = run(renderer, body)
    assert res["cloaked"] == ["cloaked", "shown"]
    assert res["after"] == "shown"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_canvas_scaling_is_always_contained(renderer):
    """The canvas scales into its surface and is centred, with or without a
    legacy ``fit`` key on the theme."""
    body = """
function probe(extra) {
    const canvas = { width: 1920, height: 1080 };
    if (extra) canvas.fit = extra;
    window.innerWidth = 960;
    window.innerHeight = 540;
    applyTheme({ schema_version: 2, canvas: canvas, containers: [{ id: "main" }] });
    const stg = document.getElementById("stage");
    return { transform: stg.style.transform, width: stg.style.width,
             height: stg.style.height };
}
console.log(JSON.stringify({ plain: probe(null), legacy: probe("none") }));
"""
    res = run(renderer, body)
    assert "scale(0.5)" in res["plain"]["transform"]
    assert res["plain"]["width"] == "1920px"
    assert res["plain"]["height"] == "1080px"
    assert res["legacy"] == res["plain"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_animation_slot_resolution_and_keyframes(renderer):
    """Slot resolution maps definitions and overrides correctly."""
    body = """
const registry = {
  fade_up: { type: "fade_up", duration_ms: 600, easing: "ease-out" },
  custom_rise: {
    type: "custom",
    duration_ms: 700,
    easing: "spring",
    keyframes: [
      { at: 0, opacity: 0, translate_y: 20 },
      { at: 100, opacity: 1, translate_y: 0 }
    ]
  }
};
const res1 = _resolveSlotDef("fade_up", registry);
const res2 = _resolveSlotDef({ use: "fade_up", duration_ms: 850 }, registry);
const res3 = _resolveSlotDef({ type: "scale_up", duration_ms: 500 }, registry);
const res4 = _resolveSlotDef("none", registry);
console.log(JSON.stringify([res1, res2, res3, res4]));
"""
    res = run(renderer, body)
    assert res[0]["type"] == "fade_up"
    assert res[0]["duration_ms"] == 600
    assert res[1]["type"] == "fade_up"
    assert res[1]["duration_ms"] == 850
    assert res[2]["type"] == "scale_up"
    assert res[2]["duration_ms"] == 500
    assert res[3] is None




@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_unknown_animation_slot_disables_the_slot(renderer):
    """An unknown name resolves to no animation, never a phase fallback."""
    body = """
console.log(JSON.stringify([
  _resolveSlotDef("nope", {}, "in"),
  _resolveSlotDef("nope", {}, "out"),
  _resolveSlotDef({ use: "nope", duration_ms: 900 }, {}, "out"),
  _resolveSlotDef({}, {}, "in"),
  _resolveSlotDef(null, {}, "in")
]));
"""
    res = run(renderer, body)
    assert res[0] is None
    assert res[1] is None
    assert res[2] is None
    assert res[3] is None
    assert res[4] is None


@pytest.mark.parametrize("renderer", RENDERERS)
def test_animation_resolution_has_no_fade_fallback(renderer):
    """The resolver and typewriter must not substitute a hidden fade.

    `_playElementAnimation` legitimately knows how to play a fade that the
    theme asks for; the fallback path is what this guard pins. The empty
    transition object in default_typewriter used to become fade_in here and
    in core/theme_schema.py.
    """
    src = _script_text(renderer)
    for name in ("_resolveSlotDef", "_playTypewriter",
                 "_collectTransitionIn", "_collectTransitionOut"):
        body = _extract_fn(src, name)
        assert "fade_in" not in body, (renderer, name)
        assert "fade_out" not in body, (renderer, name)
        assert "visibility = \"hidden\"" not in body, (renderer, name)
    # The render itself has no timer, opacity or visibility staging: the
    # update swaps DOM and applies the theme in one synchronous call.
    render = _extract_fn(src, "_renderDisplay")
    assert "setTimeout" not in render, renderer
    assert "opacity" not in render, renderer
    assert "visibility" not in render, renderer


def test_stylesheet_content_animation_is_allowlisted():
    """Every CSS animation declaration is a justified, known exception.

    `transition: none` disables inherited transitions on the container.
    `rc-blink` is the theme-authored typewriter cursor. Nothing else may
    animate or transition content in the stylesheet.
    """
    css = (ROOT / "display" / "themes.css").read_text()
    allowed = {
        "transition: none;": "container transitions disabled",
        "animation: rc-blink 1s step-start infinite;": "typewriter cursor",
        "@keyframes rc-blink {": "typewriter cursor frames",
    }
    hits = [line.strip() for line in css.splitlines()
            if "@keyframes" in line or "animation:" in line
            or "transition:" in line]
    for hit in hits:
        assert hit in allowed, hit
    assert len(hits) == len(allowed)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_typewriter_segments_keep_whitespace_with_preceding(renderer):
    """Char reveal splits by grapheme; whitespace rides the preceding
    segment so a line break appears with the word before it."""
    body = """
console.log(JSON.stringify({
  chars: _typewriterSegments("Hi ya", "char"),
  empty: _typewriterSegments("", "char"),
  emoji: _typewriterSegments("A\\u{1F44D}\\u{1F3FD}B", "char"),
  words: _typewriterSegments("Alpha beta  gamma", "word")
}));
"""
    res = run(renderer, body)
    assert res["chars"] == ["H", "i ", "y", "a"]
    assert res["empty"] == []
    # One grapheme cluster, not a surrogate pair plus a skin-tone codepoint.
    assert res["emoji"] == ["A", "\U0001F44D\U0001F3FD", "B"]
    assert res["words"] == ["Alpha ", "beta  ", "gamma"]


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_changed_sources_is_per_block(renderer):
    """Transition triggering compares what is displayed, per block; a
    same-content re-broadcast reports no change."""
    body = """
const a = { action: "display", text: "One", reference: "John 1:1",
            translation: "KJV" };
const same = { action: "display", text: "One", reference: "John 1:1",
               translation: "KJV" };
const themed = { action: "display", text: "One", reference: "John 1:1",
                 translation: "KJV", theme_data: { name: "other" } };
const text = { action: "display", text: "Two", reference: "John 1:1",
               translation: "KJV" };
const ref = { action: "display", text: "One", reference: "John 1:2",
              translation: "KJV" };
const trans = { action: "display", text: "One", reference: "John 1:1",
                translation: "" };
const refField = { action: "display", text: "One", ref: "[KJV] John 1:1" };
console.log(JSON.stringify({
  same: _changedSources(a, same),
  themed: _changedSources(a, themed),
  text: _changedSources(a, text),
  ref: _changedSources(a, ref),
  trans: _changedSources(a, trans),
  refField: _payloadSources(refField)
}));
"""
    res = run(renderer, body)
    assert res["same"]["any"] is False
    assert res["themed"]["any"] is False
    assert res["text"]["text"] is True and res["text"]["any"] is True
    assert res["ref"]["reference"] is True and res["ref"]["text"] is False
    assert res["trans"]["translation"] is True
    assert res["refField"]["reference"] == "John 1:1"
    assert res["refField"]["translation"] == "KJV"


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_reduced_motion_suppresses_animation_plans(renderer):
    """prefers-reduced-motion: no plan, no playback, no out-phase wait."""
    body = """
globalThis.matchMedia = () => ({ matches: true, addEventListener() {} });
const theme = {
  schema_version: 2,
  animations: { rise: { type: "fade_up", duration_ms: 400 } },
  containers: [{
    id: "main", visible: true,
    blocks: { text: { animation: {
      entry: "rise", transition: { out: "fade_out", in: "rise" },
      out: "fade_out" } } }
  }]
};
const changed = { text: true, reference: false, translation: false,
                  title: false, any: true };
const el = document.createElement("div");
console.log(JSON.stringify({
  reduced: _reducedMotion(),
  transitionOut: _collectTransitionOut(theme, changed),
  exit: _collectExit(theme),
  played: _playElementAnimation(el, theme.animations.rise, { kind: "text" }),
  typed: _playTypewriter(el, { type: "typewriter", duration_ms: 500 })
}));
"""
    res = run(renderer, body)
    assert res["reduced"] is True
    assert res["transitionOut"] == []
    assert res["exit"] == []
    assert res["played"] is None
    assert res["typed"] is None


@pytest.mark.parametrize("renderer", RENDERERS)
def test_v2_split_assignment_merges_transition_phases(renderer):
    """A unit overrides only the phases it authors.

    `transition` is a phase map, not an atomic slot: a `first` that authors
    only `transition.out` must keep the parent's `transition.in`, otherwise
    the first unit silently loses its incoming animation.
    """
    body = """
const base = {
  entry: { use: "rise", duration_ms: 400 },
  transition: { in: { use: "fade_in" }, out: { use: "fade_out" } },
  out: { use: "fade_out" },
  split: { by: "line" },
};
const split = {
  first: { transition: { out: { use: "slide_down" } } },
  rest: { transition: { in: { use: "scale_up" } } },
};
console.log(JSON.stringify({
  first: _splitAssignment(base, split, 0),
  rest: _splitAssignment(base, split, 1),
}));
"""
    res = run(renderer, body)
    assert "split" not in res["first"]
    # Parent entry survives; only the authored out phase changes.
    assert res["first"]["entry"] == {"use": "rise", "duration_ms": 400}
    assert res["first"]["transition"]["in"] == {"use": "fade_in"}
    assert res["first"]["transition"]["out"] == {"use": "slide_down"}
    # Parent entry/out survive; only the authored in phase changes.
    assert res["rest"]["entry"] == {"use": "rise", "duration_ms": 400}
    assert res["rest"]["transition"]["in"] == {"use": "scale_up"}
    assert res["rest"]["transition"]["out"] == {"use": "fade_out"}
    assert res["rest"]["out"] == {"use": "fade_out"}


@pytest.mark.parametrize("renderer", RENDERERS)
def test_verse_num_authored_properties_reach_the_number_span(renderer):
    """Every authored number property is an inline style on the span.

    Inline styles beat themes.css, so an authored value is the single
    effective source instead of competing with the stylesheet defaults.
    """
    body = """
const theme = {
  schema_version: 2,
  canvas: { width: 1920, height: 1080 },
  containers: [{
    id: "main", visible: true,
    blocks: {
      text: { visible: true },
      verse_num: {
        visible: true, mode: "inline", color: "#abcdef",
        size: "1.1em", weight: 800, opacity: 0.55,
        line_height: 1.4, vertical_align: "middle", margin_right: 12
      }
    }
  }]
};
handlePayload({ action: "display", text: "Hello", reference: "John 3:16",
                theme_data: theme });
console.log(JSON.stringify({
  html: document.getElementById("verse-text").innerHTML,
  attrs: _verseNumAttrs(theme.containers[0].blocks.verse_num)
}));
"""
    res = run(renderer, body)
    assert "class=\"verse-num\"" in res["html"], (renderer, res)
    for expected in ("color:#abcdef", "font-size:1.1em", "font-weight:800",
                     "opacity:0.55", "line-height:1.4",
                     "vertical-align:middle", "margin-right:12px"):
        assert expected in res["html"], (renderer, expected, res)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_text_shadow_object_string_none_and_shared(renderer):
    """Structured shadows become valid CSS; shared text references paint none."""
    body = """
console.log(JSON.stringify({
  object: _textShadowCss({x: 2, y: 3, blur: 4, spread: 9, color: "#112233"}),
  inset: _textShadowCss({x: 0, y: 1, blur: 0, color: "red", inset: true}),
  string: _textShadowCss("0 4px 12px rgba(0,0,0,0.4)"),
  none: _textShadowCss("none"),
  shared: _textShadowCss({shared: "soft"})
}));
"""
    res = run(renderer, body)
    assert res["object"] == "2px 3px 4px #112233", (renderer, res)
    assert "9px" not in res["object"], (renderer, res)
    assert res["inset"] == "inset 0px 1px 0px red", (renderer, res)
    assert res["string"] == "0 4px 12px rgba(0,0,0,0.4)", (renderer, res)
    assert res["none"] == "none", (renderer, res)
    assert res["shared"] == "", (renderer, res)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_text_shadow_object_reaches_the_root_css_variable(renderer):
    body = """
const theme = {
  schema_version: 2,
  canvas: { width: 1920, height: 1080 },
  containers: [{ id: "main", visible: true,
    blocks: { text: { text_shadow: {x: 1, y: 2, blur: 3,
                                    color: "#445566"} } } }]
};
applyTheme(theme);
console.log(JSON.stringify({
  shadow: document.documentElement.style.getPropertyValue("--rc-text-shadow")
}));
"""
    res = run(renderer, body)
    assert res["shadow"] == "1px 2px 3px #445566", (renderer, res)


# ── Designer preview paint scheduler (left-panel live updates) ─────────────

@pytest.mark.parametrize("renderer", RENDERERS)
def test_preview_coalesces_edits_into_the_next_frame(renderer):
    """Left-panel edits must not need a mode switch to appear: the first
    change is painted on the next animation frame and later changes inside
    that frame collapse into the newest value."""
    body = """
(async () => {
  window.__RC_PREVIEW = true;
  const stg = document.getElementById("stage");
  const theme = (bg) => ({canvas: {width: 1920, height: 1080,
                                   background: bg, fit: "contain"},
                          containers: [{id: "main"}]});
  stg.style.background = "#000000";
  applyThemeInPlace(theme("#ff0000"));
  const sync = stg.style.background;
  applyThemeInPlace(theme("#00ff00"));
  applyThemeInPlace(theme("#123456"));
  await new Promise((r) => setTimeout(r, 60));
  console.log(JSON.stringify({sync: sync, after: stg.style.background,
                              stats: previewRenderStats()}));
})();
"""
    out = run(renderer, body)
    # Deferred, not synchronous...
    assert out["sync"] == "#000000", (renderer, out)
    # ...and the newest value wins.
    assert out["after"] == "#123456", (renderer, out)
    assert out["stats"]["activePaints"] >= 1, (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_release_paints_immediately(renderer):
    """A pointer release flushes the value on the same call, not the frame."""
    body = """
window.__RC_PREVIEW = true;
const stg = document.getElementById("stage");
stg.style.background = "#000000";
applyThemeNow({canvas: {width: 960, height: 540, background: "#123456",
                        fit: "contain"}, containers: [{id: "main"}]});
console.log(JSON.stringify({bg: stg.style.background, w: stg.style.width,
                            stats: previewRenderStats()}));
"""
    out = run(renderer, body)
    assert out["bg"] == "#123456", (renderer, out)
    assert out["w"] == "960px", (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_preview_runs_at_60hz_while_editing_then_idles(renderer):
    """Edits keep the 60 Hz run alive; after the 500 ms grace window the
    scheduler drops to the 1 Hz heartbeat, and the next change wakes it."""
    body = """
(async () => {
  window.__RC_PREVIEW = true;
  const theme = (i) => ({canvas: {width: 1920, height: 1080,
      background: i % 2 ? "#ff0000" : "#0000ff", fit: "contain"},
      containers: [{id: "main"}]});
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  for (let i = 0; i < 30; i++) { applyThemeInPlace(theme(i)); await sleep(5); }
  const during = previewRenderStats();
  await sleep(900);
  const after = previewRenderStats();
  applyThemeInPlace(theme(1));
  const resumed = previewRenderStats();
  await sleep(20);
  console.log(JSON.stringify({during: during, after: after,
                              resumed: resumed}));
})();
"""
    out = run(renderer, body)
    # ~150 ms of edits, capped at 60 Hz (16.7 ms/frame), never per event.
    assert 3 <= out["during"]["activePaints"] <= 16, (renderer, out)
    assert out["after"]["mode"] == "idle", (renderer, out)
    assert out["resumed"]["mode"] == "active", (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_idle_heartbeat_paints_a_value_whose_frame_never_ran(renderer):
    """The 1 Hz heartbeat is the safety net: an update whose rAF never ran
    (paused/hidden page, dropped tick) is still painted by the heartbeat."""
    body = """
window.__RC_PREVIEW = true;
const stg = document.getElementById("stage");
stg.style.background = "#000000";
globalThis.requestAnimationFrame = () => 0;   // frames never arrive
applyThemeInPlace({canvas: {width: 1920, height: 1080,
                            background: "#abcdef", fit: "contain"},
                   containers: [{id: "main"}]});
const before = stg.style.background;
_rcHeartbeatTick();
console.log(JSON.stringify({before: before, after: stg.style.background,
                            stats: previewRenderStats()}));
"""
    out = run(renderer, body)
    assert out["before"] == "#000000", (renderer, out)
    assert out["after"] == "#abcdef", (renderer, out)
    assert out["stats"]["idleTicks"] >= 1, (renderer, out)
    assert out["stats"]["idlePaints"] == 1, (renderer, out)


@pytest.mark.parametrize("renderer", RENDERERS)
def test_idle_heartbeat_leaves_a_clean_frame_alone(renderer):
    """A tick with nothing missed paints nothing, so the heartbeat cannot
    disturb a running right-panel animation."""
    body = """
window.__RC_PREVIEW = true;
applyThemeNow({canvas: {width: 1920, height: 1080,
                        background: "#abcdef", fit: "contain"},
               containers: [{id: "main"}]});
_rcHeartbeatTick();
console.log(JSON.stringify(previewRenderStats()));
"""
    out = run(renderer, body)
    assert out["idlePaints"] == 0, (renderer, out)
    assert out["idleTicks"] >= 1, (renderer, out)
    assert out["dirty"] is False, (renderer, out)
