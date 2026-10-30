"""Song text round-trip: deck_to_txt <-> parse_slide_txt.

Parser-only (no DB): the temporary external text-edit flow depends on an
exact round-trip, including section-less slides after sectioned ones.
"""

import json
from pathlib import Path

from core.slide_parser import deck_to_txt, parse_slide_txt, split_multisong

SLIDES = [
    {"section": "Verse 1", "text": "Amazing grace how sweet\nthe sound",
     "marker": True},
    {"section": "Verse 1", "text": "That saved a wretch like me",
     "marker": False},
    {"section": "Chorus", "text": "My chains are [gone: (#ffd700)]\nBeen set free",
     "marker": True},
    {"section": None, "text": "Tag line only", "marker": True},
    {"section": None, "text": "Another tag", "marker": False},
    {"section": "Bridge", "text": "Back to section", "marker": True},
]


def test_round_trip_exact():
    raw = deck_to_txt("Amazing Grace", SLIDES)
    parsed = parse_slide_txt(raw)
    assert parsed["title"] == "Amazing Grace"
    assert parsed["slides"] == SLIDES


def test_section_marker_only_on_change():
    raw = deck_to_txt("Amazing Grace", SLIDES)
    assert raw.count("*Verse 1") == 1  # spans two slides, emitted once
    assert raw.count("*Chorus") == 1
    assert raw.count("*Bridge") == 1
    # Section-less run after Chorus: exactly one bare `*` clears it
    bare = [line for line in raw.splitlines() if line.strip() == "*"]
    assert len(bare) == 1


def test_serializer_never_splits_multisong():
    raw = deck_to_txt("Amazing Grace", SLIDES)
    assert split_multisong(raw) == [raw]


def test_round_trip_empty():
    assert parse_slide_txt(deck_to_txt("", []))["title"] == "(untitled)"
    assert parse_slide_txt(deck_to_txt("", []))["slides"] == []


def test_bare_star_clears_section():
    parsed = parse_slide_txt("# T\n*V\na\n\n\n*\nb\n")
    assert parsed["slides"] == [
        {"section": "V", "text": "a", "marker": True},
        {"section": None, "text": "b", "marker": True},
    ]


def test_repeated_section_syntax_never_merges():
    """Section syntax always starts a new section — even when the name is
    identical to the section above. Each `*Name` line owns its slide."""
    parsed = parse_slide_txt("# T\n\n\n*V1\na\n\n\n*V1\nb\n")
    assert parsed["slides"] == [
        {"section": "V1", "text": "a", "marker": True},
        {"section": "V1", "text": "b", "marker": True},
    ]
    # Serialize: both markers persist as repeated `*V1` lines…
    raw = deck_to_txt("T", parsed["slides"])
    assert raw.count("*V1") == 2
    # …and re-parse losslessly (still two owned sections, not one run).
    reparsed = parse_slide_txt(raw)["slides"]
    assert [(s["section"], s["marker"]) for s in reparsed] == [
        ("V1", True), ("V1", True)]


def test_slides_body_to_txt_carries_markers():
    """Tier-scoped copy: a run subset serializes with its own `*` lines
    (no title, no format line) and re-parses with identical structure."""
    from core.slide_parser import slides_body_to_txt
    slides = [
        {"section": "V1", "text": "a", "marker": True},
        {"section": "V1", "text": "b", "marker": False},
    ]
    body = slides_body_to_txt(slides)
    assert body == "*V1\na\n\n---\n\nb"
    reparsed = parse_slide_txt(f"# T\n\n\n{body}\n")["slides"]
    assert [(s["section"], s["text"]) for s in reparsed] == [
        ("V1", "a"), ("V1", "b")]


def test_deck_format_line():
    from core.slide_parser import parse_deck_format
    fmt = parse_deck_format(
        "size=35, 25, 35; bold=true; color=#66ff00; italics=false; case=origin\n# T\nx"
    )
    assert fmt == {"size_nominal": 35, "size_min": 25, "size_max": 35,
                   "bold": True, "color": "#66ff00", "italics": False,
                   "case": "origin",
                   "underline": None, "strike": None, "align": None,
                   "spacing": None, "super": None, "sub": None,
                   "outline": None, "shadow": None, "dir": None, "hr": None,
                   "font": None}


def test_deck_format_partial_and_zone():
    from core.slide_parser import parse_deck_format, parse_slide_txt
    # partial size: missing parts inherit (None)
    assert parse_slide_txt("size=30\n# T\nx")["format"]["size_nominal"] == 30
    assert parse_slide_txt("size=30\n# T\nx")["format"]["size_min"] is None
    # format-looking lines after the title are lyrics, not formatting
    assert parse_slide_txt("# T\nsize=30\nx")["slides"] == [
        {"section": None, "text": "size=30\nx", "marker": False}]
    assert parse_deck_format("# T\nsize=30\nx")["size_nominal"] is None
    # unknown keys / bad values never become formatting
    assert parse_slide_txt("God = love\n# T\nx")["slides"][0]["text"] == "God = love\nx"
    assert parse_slide_txt("color=#gggggg\n# T\nx")["format"]["color"] is None


def test_inline_runs_new_syntax_and_legacy():
    from core.slide_parser import (strip_inline_markup, inline_markup_to_html,
                                   has_inline_markup)
    text = "I want to [work on (color=#ff6600; size=20; italics=true; bold=false; case=upper)], ok"
    assert strip_inline_markup(text) == "I want to work on, ok"
    html = inline_markup_to_html(text)
    for frag in ("color:#ff6600", "font-size:20px", "font-style:italic",
                 "font-weight:400", "text-transform:uppercase"):
        assert frag in html, frag
    # legacy color-only still works
    assert strip_inline_markup("a [b: (#fff)] c") == "a b c"
    assert "color:#ffffff" in inline_markup_to_html("a [b: (#fff)] c")
    # non-final parens / unknown shapes stay literal
    assert not has_inline_markup("plain (note)")
    assert not has_inline_markup("[see (Fig. 3)]")
    assert "[see (Fig. 3)]" in strip_inline_markup("[see (Fig. 3)]")


def test_explicit_outline_none_beats_a_hard_shadow():
    """text_outline:none is a decision: the outline stays off even when a
    legacy hard text_shadow is present (that shadow then renders literally,
    as the shadow it claims to be)."""
    import core.theme_loader as tl
    hard = ("-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000, "
            "-2px 0 0 #000, 2px 0 0 #000, 0 -2px 0 #000, 0 2px 0 #000")
    assert tl.theme_outline({"text_shadow": hard}) == "2px #000000"
    assert tl.theme_outline({"text_outline": "none",
                             "text_shadow": hard}) is None
    assert tl.display_format_defaults({"text": {"text_outline": "none",
                                                "text_shadow": hard}}).get(
        "outline") is None


def test_all_zero_shadow_is_valid_but_invisible():
    """A zeroed shadow ("0px 0% 0px #000000 0") must never paint: size
    clamps to the 1px minimum, but zero opacity means zero alpha in the
    emitted paint. Explicit offs kill inherited shadow/outline alike."""
    from core.slide_parser import _parse_shadow, _shadow_to_css, _span_style
    assert _parse_shadow("0px 0% 0px #000000 0") == "1px 0% 0px #000000 0"
    assert "rgba(0, 0, 0, 0)" in _shadow_to_css("0px 0% 0px #000000 0")
    assert "text-shadow:none" in _span_style({"shadow": "none"})
    assert "text-shadow:none" in _span_style({"outline": "none"})


def test_deck_shadow_round_trips_through_top_script():
    """Deck shadow serializes into the format line and parses back to
    the canonical value (tier-4 writes persist through Save)."""
    from core.slide_parser import (
        deck_to_txt, format_to_line, parse_slide_txt)
    fmt = {"shadow": "8px 40% 3px #ff0000 45", "outline": "none",
           "bold": True}
    line = format_to_line(fmt)
    assert "shadow=8px 40% 3px #ff0000 45" in line, line
    assert "outline=none" in line, line
    raw = deck_to_txt("T", [{"section": "1", "text": "Words"}], fmt)
    back = parse_slide_txt(raw)
    assert back["format"]["shadow"] == "8px 40% 3px #ff0000 45"
    assert back["format"]["outline"] == "none"
    assert back["format"]["bold"] is True
    assert back["slides"][0]["text"] == "Words"


def test_outline_ring_agrees_across_renderers():
    """The outline ring is built three times (Python parser, the OBS display,
    the embedded preview) from (width, color) alone. Byte-identical output
    is the determinism proof: same input, same ring, every renderer.
    """
    import re
    import shutil
    import subprocess
    from core.slide_parser import _outline_ring

    node = shutil.which("node")
    if not node:
        return  # no JS runtime available; Python contract is still asserted

    cases = ["1px #ff0000", "#ff0000", "#f00", "6px #123456", "25px #000000",
             "99px #000000", "0px #000000", "12px #abc", "6PX #ABCDEF",
             "none", "off", "garbage", "4px", ""]
    harness = '%s\nconsole.log(JSON.stringify(%s.map(v => _outlineRing(v))));' 

    def run(source_path, embedded=False):
        src = Path(source_path).read_text()
        if embedded:
            html = src.split('_DISPLAY_HTML = r"""', 1)[1].rsplit('"""', 1)[0]
            src = "\n".join(re.findall(r"<script>(.*?)</script>", html, re.S))
        helper = re.search(r"function _outlineRing\(value\) \{.*?\n\}\n", src, re.S)
        assert helper, f"_outlineRing missing from {source_path}"
        color_fn = re.search(
            r"function _parseInlineColor\(value\) \{.*?\n\}\n", src, re.S)
        assert color_fn, f"_parseInlineColor missing from {source_path}"
        parts_fn = re.search(
            r"function _outlineParts\(value\) \{.*?\n\}\n", src, re.S)
        assert parts_fn, f"_outlineParts missing from {source_path}"
        out = subprocess.run(
            [node, "-e", harness % (color_fn.group(0) + parts_fn.group(0)
                                   + helper.group(0), json.dumps(cases))],
            capture_output=True, text=True)
        assert out.returncode == 0, out.stderr
        return json.loads(out.stdout)

    obs = run(Path(__file__).resolve().parents[1] / "display" / "display.js")
    preview = run(Path(__file__).resolve().parents[1] / "ui" / "widgets"
                  / "display_view.py", embedded=True)
    python = [_outline_ring(c) for c in cases]
    assert obs == preview, "display.js and display_view.js disagree"
    assert python == obs, (
        "parser and display disagree:\n%s\n%s" % (python, obs))


def test_outline_reaches_html_without_a_style():
    """The outline must never reach HTML as a style: -webkit-text-stroke
    straddles the glyph path (it eats the letters) and a shadow ring is not
    an outline. The display renderers build a duplicated stroke layer
    instead, so the parser emits a style-free span here."""
    from core.slide_parser import inline_markup_to_html
    html = inline_markup_to_html("a [God (outline=6px #ff0000)] b")
    assert "-webkit-text-stroke" not in html
    assert "text-shadow" not in html
    assert "<span" in html and "God" in html
    # navigation surfaces (color/italics only) never grow an outline
    assert "text-shadow" not in inline_markup_to_html(
        "a [God (outline=6px #ff0000)] b",
        allow=frozenset(("color", "italics")))



def test_outline_thickness_round_trip():
    """outline= carries an optional thickness; bare colors stay 1px."""
    from core.slide_parser import (inline_markup_to_html, parse_format_line,
                                   parse_slide_txt)
    # explicit thickness is carried through the parser untouched...
    assert parse_format_line("outline=4px #123456")["outline"] == "4px #123456"
    # ...and legacy bare colors still parse (width 1 by convention)
    assert parse_format_line("outline=#123456")["outline"] == "#123456"
    # a width without a color is not a formatting decision
    assert parse_format_line("outline=4px")["outline"] is None
    # runs survive the txt round trip verbatim
    raw = "a [God (outline=3px #00ff00)] b"
    assert parse_slide_txt(raw)["slides"][0]["text"] == raw
    # ...and render with no inline stroke/shadow: the outline is a
    # duplicated layer built by the display JS, not a span style.
    html = inline_markup_to_html(raw)
    assert "-webkit-text-stroke" not in html, "stroke eats the letterform"
    assert "text-shadow" not in html



def test_paragraph_gap_markers():
    from core.slide_parser import (strip_inline_markup, inline_markup_to_html,
                                   has_inline_markup)
    # bare marker → plain break; words stay separated in stripped text
    assert strip_inline_markup("one\\nsecond") == "one\nsecond"
    assert inline_markup_to_html("one\\nsecond") == "one<br/>second"
    # sized gap run → sized break span
    assert strip_inline_markup("a[\\n (size=12)]b") == "a\nb"
    assert (inline_markup_to_html("a[\\n (size=12)]b")
            == 'a<span style="font-size:12px"><br/></span>b')
    # bare bracket gap → unstyled break span
    assert strip_inline_markup("a[\\n]b") == "a\nb"
    assert (inline_markup_to_html("a[\\n]b")
            == 'a<span style=""><br/></span>b')
    assert has_inline_markup("[\\n]")
    # gap inside a parsed slide survives the full slide pipeline
    from core.slide_parser import parse_slide_txt
    slides = parse_slide_txt("# T\n\n\nFirst\n[\\n (size=10)]\nSecond\n")["slides"]
    assert len(slides) == 1
    assert "font-size:10px" in inline_markup_to_html(slides[0]["text"])


def test_tier1_deck_keys():
    from core.slide_parser import parse_deck_format, format_to_line
    fmt = parse_deck_format(
        "underline=true; strike=true; align=center; spacing=1.5; dir=rtl; "
        "outline=#000000; font=Arial Black\n# T\nx")
    assert fmt["underline"] is True
    assert fmt["strike"] is True
    assert fmt["align"] == "center"
    assert fmt["spacing"] == 1.5
    assert fmt["dir"] == "rtl"
    assert fmt["outline"] == "#000000"
    assert fmt["font"] == "Arial Black"
    # bad values are ignored, never crash
    bad = parse_deck_format("align=middle; spacing=9; dir=up; font=;\n# T\nx")
    assert bad["align"] is None and bad["spacing"] is None
    assert bad["dir"] is None and bad["font"] is None
    # full round-trip through the format line
    line = format_to_line(fmt)
    assert line is not None
    assert parse_deck_format(line + "\n# T\nx") == fmt


def test_tier1_inline_runs():
    from core.slide_parser import inline_markup_to_html, strip_inline_markup
    html = inline_markup_to_html(
        "[u (underline=true)] [s (strike=true)] [b (underline=true; strike=true)]")
    assert "text-decoration:underline" in html
    assert "text-decoration:line-through" in html
    assert "text-decoration:underline line-through" in html
    html = inline_markup_to_html("[x (super=true)] [y (sub=true)]")
    assert "<sup>x</sup>" in html and "<sub>y</sub>" in html
    html = inline_markup_to_html("[o (outline=#ff0000)]")
    assert "text-shadow" not in html and "<span" in html
    html = inline_markup_to_html("[a (align=right)]")
    assert "text-align:right" in html
    html = inline_markup_to_html("[d (dir=rtl)]")
    assert "direction:rtl" in html
    html = inline_markup_to_html("[f (font=Georgia; size=20)]")
    assert "font-family:'Georgia'" in html
    assert strip_inline_markup("[o (outline=#ff0000)]") == "o"


def test_hr_run():
    from core.slide_parser import (inline_markup_to_html, strip_inline_markup,
                                   has_inline_markup, is_hr_run,
                                   parse_format_segments)
    assert is_hr_run(parse_format_segments(["hr=true"], inline=True))
    html = inline_markup_to_html("above\n[ (hr=true)]\nbelow")
    assert "border-top:2px solid currentColor" in html
    assert "above" in html and "below" in html
    assert has_inline_markup("[ (hr=true)]")


def test_same_name_split_persists():
    from core.slide_parser import slide_owns_marker
    # Two adjacent runs both named "2" stay two runs through txt.
    slides = [
        {"section": "2", "text": "a", "marker": True},
        {"section": "2", "text": "b", "marker": True},
        {"section": "2", "text": "c", "marker": False},
    ]
    raw = deck_to_txt("T", slides)
    assert raw.count("*2") == 2  # repeated marker, not merged
    reparsed = parse_slide_txt(raw)["slides"]
    assert [s["marker"] for s in reparsed] == [True, True, False]
    assert slide_owns_marker(reparsed, 0)
    assert slide_owns_marker(reparsed, 1)
    assert not slide_owns_marker(reparsed, 2)


def test_owns_marker_falls_back_to_value_change():
    from core.slide_parser import slide_owns_marker
    # Marker-less dicts (imports, old DB rows) group exactly as before.
    slides = [{"section": "V", "text": "a"}, {"section": "V", "text": "b"},
              {"section": None, "text": "c"}, {"section": None, "text": "d"}]
    assert [slide_owns_marker(slides, i) for i in range(4)] == [True, False, True, False]
    # ...and serialize without adding or dropping markers.
    raw = deck_to_txt("T", slides)
    assert raw.count("*V") == 1
    assert [line for line in raw.splitlines() if line.strip() == "*"] == ["*"]


# ── `---` divider format (txt is the source of truth) ─────────────────────


def _texts(raw: str) -> list[str]:
    return [s["text"] for s in parse_slide_txt(raw)["slides"]]


def test_divider_accepts_extra_padding():
    for raw in (
        "# T\n\nA\n\n---\n\nB\n",
        "# T\n\nA\n\n\n\n---\n\n\n\nB\n",
        "# T\n\nA\n\n\n---\n\n\nB\n",
        "# T\n\nA\n \n---\n \nB\n",
    ):
        assert _texts(raw) == ["A", "B"], raw


def test_divider_requires_blank_padding():
    # No blank line before or after: not a boundary, stays content.
    raw = "# T\n\nA\n---\nB\n"
    assert _texts(raw) == ["A\n---\nB"]


def test_spacing_inside_a_slide_is_preserved():
    raw = "# T\n\nA\n\nB\n\n\nC\n\n---\n\nD\n"
    assert _texts(raw) == ["A\n\nB\n\n\nC", "D"]
    slides = parse_slide_txt(raw)["slides"]
    assert _texts(deck_to_txt("T", slides)) == ["A\n\nB\n\n\nC", "D"]


def test_empty_slides_between_dividers_and_at_edges():
    assert _texts("# T\n\nA\n\n---\n\n\n\n---\n\nB\n") == ["A", "", "B"]
    assert _texts("# T\n\n\n---\n\nA\n") == ["", "A"]
    # A trailing divider at EOF is an end-marker, not an empty last slide.
    assert _texts("# T\n\nA\n\n---\n\n") == ["A"]


def test_indent_survives_round_trip():
    raw = "# T\n\n\n    indented\n\tTabbed\nplain\n"
    slides = parse_slide_txt(raw)["slides"]
    assert slides[0]["text"] == "    indented\n\tTabbed\nplain"
    assert parse_slide_txt(deck_to_txt("T", slides))["slides"][0]["text"] == slides[0]["text"]


def test_legacy_single_blank_is_content_but_double_blank_splits():
    assert _texts("# T\n\nA\n\nB\n") == ["A\n\nB"]
    assert _texts("# T\n\nA\n\n\nB\n") == ["A", "B"]


def test_legacy_section_still_starts_a_slide():
    slides = parse_slide_txt("# T\n\n*V1\nA\n\n\n*V2\nB\n")["slides"]
    assert [(s["section"], s["text"]) for s in slides] == [
        ("V1", "A"), ("V2", "B")]


def test_bordered_section_marker_does_not_split():
    slides = parse_slide_txt(
        "# T\n\n*V1\nA\n\n---\n\n*Chorus\nB\n")["slides"]
    assert [(s["section"], s["text"], s["marker"]) for s in slides] == [
        ("V1", "A", True), ("Chorus", "B", True)]


def test_bordered_bare_star_clears_section_without_splitting():
    slides = parse_slide_txt(
        "# T\n\n*V1\nA\n\n---\n\n*\nB\n")["slides"]
    assert slides[1] == {"section": None, "text": "B", "marker": True}


def test_bordered_round_trip_with_empty_and_spaced_slides():
    slides = [
        {"section": "V", "text": "a\n\nb", "marker": True},
        {"section": None, "text": "", "marker": True},
        {"section": "C", "text": "c", "marker": True},
    ]
    assert parse_slide_txt(deck_to_txt("T", slides))["slides"] == slides


def test_single_slide_serializes_as_bordered_for_lossless_spacing():
    raw = "# T\n\nA\n\nB\n\n\nC\n\n---\n"
    slides = parse_slide_txt(raw)["slides"]
    assert len(slides) == 1
    out = deck_to_txt("T", slides)
    assert out.rstrip().endswith("---")
    assert parse_slide_txt(out)["slides"][0]["text"] == "A\n\nB\n\n\nC"


def test_prune_empty_slides_keeps_section_only_cards():
    from core.slide_parser import prune_empty_slides
    slides = [
        {"section": None, "text": "", "marker": False},
        {"section": None, "text": "  \n\n ", "marker": False},
        {"section": "V", "text": "", "marker": True},
        {"section": "V", "text": "a", "marker": False},
    ]
    assert prune_empty_slides(slides) == [slides[2], slides[3]]
