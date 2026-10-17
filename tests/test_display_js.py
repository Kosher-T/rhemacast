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
from pathlib import Path

import pytest

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
    harness = STUB.read_text() + "\n" + _script_text(rel_path) + "\n" + body
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True,
                         timeout=60)
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
