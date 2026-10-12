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