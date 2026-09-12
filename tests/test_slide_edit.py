"""Song text round-trip: deck_to_txt <-> parse_slide_txt.

Parser-only (no DB): the temporary external text-edit flow depends on an
exact round-trip, including section-less slides after sectioned ones.
"""

from core.slide_parser import deck_to_txt, parse_slide_txt, split_multisong

SLIDES = [
    {"section": "Verse 1", "text": "Amazing grace how sweet\nthe sound"},
    {"section": "Verse 1", "text": "That saved a wretch like me"},
    {"section": "Chorus", "text": "My chains are [gone: (#ffd700)]\nBeen set free"},
    {"section": None, "text": "Tag line only"},
    {"section": None, "text": "Another tag"},
    {"section": "Bridge", "text": "Back to section"},
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
        {"section": "V", "text": "a"},
        {"section": None, "text": "b"},
    ]


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
                   "outline": None, "dir": None, "hr": None, "font": None}


def test_deck_format_partial_and_zone():
    from core.slide_parser import parse_deck_format, parse_slide_txt
    # partial size: missing parts inherit (None)
    assert parse_slide_txt("size=30\n# T\nx")["format"]["size_nominal"] == 30
    assert parse_slide_txt("size=30\n# T\nx")["format"]["size_min"] is None
    # format-looking lines after the title are lyrics, not formatting
    assert parse_slide_txt("# T\nsize=30\nx")["slides"] == [
        {"section": None, "text": "size=30\nx"}]
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
    assert "-webkit-text-stroke:1px #ff0000" in html
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
