"""Round-trip: slide txt <-> QTextDocument (Lite Designer converters).

Needs offscreen Qt (QT_QPA_PLATFORM=offscreen is set by conftest).
"""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Import the WebEngine-backed widget BEFORE any QApplication exists:
# importing QtWebEngineWidgets after app creation raises ImportError, which
# would poison later UI imports in the same pytest process (phase10).
import ui.widgets.display_view  # noqa: F401

from PyQt6.QtWidgets import QApplication

from core.slide_parser import parse_slide_txt, _iter_inline_parts
from ui.widgets.lite_designer.rich_txt import txt_to_doc, doc_to_txt

_app = None


def _qt():
    global _app
    if _app is None:
        _app = QApplication(["t"])
    return _app


def _runs(text: str):
    """Normalized (display, sorted-params) run list for comparison."""
    out = []
    for part, params in _iter_inline_parts(text):
        if params is None:
            out.append((part, None))
        else:
            sparse = {k: v for k, v in params.items() if v is not None}
            out.append((part, sparse or None))
    return out


def _roundtrip(text: str) -> str:
    _qt()
    return doc_to_txt(txt_to_doc(text))


def test_plain_and_breaks():
    assert _roundtrip("Amazing grace\nhow sweet") == "Amazing grace\nhow sweet"
    assert _roundtrip("") == ""


def test_tier0_runs():
    src = ("I want to [work on (color=#ff6600; size=20; italics=true; "
           "bold=false; case=upper)], ok")
    assert _runs(_roundtrip(src)) == _runs(src)


def test_tier1_runs():
    src = ("[u (underline=true)] [s (strike=true)] [x (super=true)] "
           "[y (sub=true)] [o (outline=#ff0000)] [f (font=Georgia)]")
    assert _runs(_roundtrip(src)) == _runs(src)
    # Block keys are line-scoped: values survive, normalized whole-line.
    # Stable after the first pass (round-trip of round-trip is identical).
    scoped = "[a (align=center)] mid [d (dir=rtl)]"
    once = _roundtrip(scoped)
    assert _runs(_roundtrip(once)) == _runs(once)
    assert "align=center" in once and "dir=rtl" in once


def test_gaps_and_hr():
    from core.slide_parser import strip_inline_markup, inline_markup_to_html
    # Bare markers and gap blocks are semantically identical breaks.
    assert strip_inline_markup(_roundtrip("one\\nsecond")) == "one\nsecond"
    assert (strip_inline_markup(_roundtrip("a[\\n (size=12)]b")) == "a\nb")
    assert "font-size:12px" in inline_markup_to_html(
        _roundtrip("a[\\n (size=12)]b"))
    assert "hr" in _roundtrip("above\n[ (hr=true)]\nbelow")


def test_lists_literal():
    src = "\u2022 first\n\u2022 second\n1. one\n2. two"
    assert _roundtrip(src) == src


def test_structure_guard():
    out = _roundtrip("*wow\n#hashtag lyric")
    parsed = parse_slide_txt("# T\n\n\n" + out + "\n")
    assert len(parsed["slides"]) == 1  # no phantom sections/songs


def test_block_wrap_alignment():
    src = "[Centered line (align=center)]"
    assert _roundtrip(src) == src


def test_block_spacing_wrap_and_suppression():
    from ui.widgets.lite_designer.rich_txt import apply_spacing_to_doc
    _qt()
    # Inline spacing run -> block line-height -> wrap preserved.
    doc = txt_to_doc("[spaced (spacing=1.5)]")
    out = doc_to_txt(doc)
    assert "spacing=1.5" in out, out
    # ...unless it merely echoes the deck spacing (WYSIWYG paint).
    apply_spacing_to_doc(doc, 1.5)
    assert "spacing" not in doc_to_txt(doc, base_spacing=1.5)
    # ...but a genuinely different block spacing still persists.
    apply_spacing_to_doc(doc, 2.0)
    assert "spacing=2.0" in doc_to_txt(doc, base_spacing=1.5)


def test_spacing_roundtrip_deck_key():
    # spacing lives on the deck format line, untouched by slide conversion
    parsed = parse_slide_txt("spacing=1.5\n# T\nplain slide\n")
    assert parsed["format"]["spacing"] == 1.5
    assert _roundtrip("plain slide") == "plain slide"
