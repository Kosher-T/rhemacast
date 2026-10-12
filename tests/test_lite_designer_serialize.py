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
    # Shared per-process instance (see test_lite_designer_select).
    global _app
    _app = QApplication.instance()
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
    # An explicit line value wins over deck paint: the paint is a deck
    # echo (suppressed), the prop is the line's own voice (emitted).
    doc2 = txt_to_doc("[spaced (spacing=2.0)]")
    apply_spacing_to_doc(doc2, 1.5)
    assert "spacing=2.0" in doc_to_txt(doc2, base_spacing=1.5)


def test_spacing_roundtrip_deck_key():
    # spacing lives on the deck format line, untouched by slide conversion
    parsed = parse_slide_txt("spacing=1.5\n# T\nplain slide\n")
    assert parsed["format"]["spacing"] == 1.5
    assert _roundtrip("plain slide") == "plain slide"


def _fragment_formats(doc):
    """All non-empty fragment char formats in a document."""
    out = []
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.text().replace("\u2029", ""):
                out.append(frag.charFormat())
            it += 1
    return out


def test_size_rides_as_prop_never_point_size():
    """Edit-pane glyphs stay fixed-size: size params load as SIZE_PROP
    metadata (no fragment point size) and serialize back exactly."""
    from PyQt6.QtGui import QTextFormat
    from ui.widgets.lite_designer.rich_txt import (
        SIZE_PROP, txt_to_doc, doc_to_txt)
    _qt()
    doc = txt_to_doc("[huge (size=62)] plain")
    fmts = _fragment_formats(doc)
    assert fmts, "expected fragments"
    for fmt in fmts:
        assert not fmt.hasProperty(QTextFormat.Property.FontPointSize)
    assert fmts[0].property(SIZE_PROP) == 62
    out = doc_to_txt(doc)
    assert "size=62" in out, out


def test_normalize_sizes_to_props():
    """Legacy/rich point sizes fold into SIZE_PROP (visual fixed)."""
    from PyQt6.QtGui import QTextCharFormat, QTextCursor, QTextFormat
    from ui.widgets.lite_designer.rich_txt import (
        SIZE_PROP, doc_to_txt, normalize_sizes_to_props, _PT_PER_PX)
    from PyQt6.QtGui import QTextDocument
    _qt()
    doc = QTextDocument()
    cursor = QTextCursor(doc)
    fmt = QTextCharFormat()
    fmt.setFontPointSize(40 * _PT_PER_PX)
    cursor.insertText("sized words", fmt)
    normalize_sizes_to_props(doc)
    fmts = _fragment_formats(doc)
    assert len(fmts) == 1
    assert not fmts[0].hasProperty(QTextFormat.Property.FontPointSize)
    assert fmts[0].property(SIZE_PROP) == 40
    assert "size=40" in doc_to_txt(doc)


def test_ribbon_size_applies_prop_not_points():
    """Ribbon size changes the model + preview, never pane glyphs."""
    from PyQt6.QtGui import QTextCursor, QTextFormat
    from PyQt6.QtWidgets import QTextEdit
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import (
        SIZE_PROP, doc_to_txt, txt_to_doc)
    _qt()
    edit = QTextEdit()
    edit.setDocument(txt_to_doc("plain words"))
    ribbon = FormatRibbon()
    ribbon.set_editor(edit)
    cursor = edit.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    edit.setTextCursor(cursor)
    ribbon._apply_size_px(32)
    fmts = _fragment_formats(edit.document())
    assert fmts and all(
        not f.hasProperty(QTextFormat.Property.FontPointSize) for f in fmts)
    assert fmts[0].property(SIZE_PROP) == 32
    assert ribbon._current_size_px() == 32
    assert "size=32" in doc_to_txt(edit.document())


def _display_fmts(text: str):
    """[(block_text, [char formats])] for the restricted card view."""
    from ui.widgets.lite_designer.rich_txt import txt_to_display_doc
    _qt()
    doc = txt_to_display_doc(text)
    out = []
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        fmts = []
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid() and frag.text().replace("\u2029", ""):
                fmts.append(frag.charFormat())
            it += 1
        out.append((block.text(), fmts))
    return out


def _word_fmts(text: str):
    """{stripped word: char format} for the restricted card view.

    Spaces between runs are fragments too, so index by word instead.
    """
    from ui.widgets.lite_designer.rich_txt import txt_to_display_doc
    _qt()
    doc = txt_to_display_doc(text)
    pairs = {}
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                ft = frag.text().replace("\u2029", "")
                if ft.strip():
                    pairs[ft.strip()] = frag.charFormat()
            it += 1
    return pairs


def test_display_doc_renders_bisu_only():
    from PyQt6.QtGui import QFont, QTextCharFormat
    fmts = _word_fmts(
        "[b (bold=true)] [i (italics=true)] [s (strike=true)] [u (underline=true)]")
    assert set(fmts) == {"b", "i", "s", "u"}, set(fmts)
    assert fmts["b"].fontWeight() >= 600
    assert fmts["i"].fontItalic()
    assert fmts["s"].fontStrikeOut()
    assert fmts["u"].underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline


def test_display_doc_ignores_everything_else():
    from PyQt6.QtGui import QFont, QTextCharFormat, QTextFormat
    fmts = _word_fmts(
        "[c (color=#ff0000; size=40; case=upper; align=center; spacing=2.0; "
        "outline=#00ff00; dir=rtl; font=Georgia)]")
    fmt = fmts["c"]
    assert fmt.fontWeight() < 600 and not fmt.fontItalic()
    assert not fmt.fontStrikeOut()
    assert fmt.underlineStyle() == QTextCharFormat.UnderlineStyle.NoUnderline
    assert fmt.fontCapitalization() != QFont.Capitalization.AllUppercase
    # No explicit brush: app-palette defaults don't count (property unset).
    assert not fmt.hasProperty(QTextFormat.Property.ForegroundBrush)
    assert fmt.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignNormal


def test_display_doc_renders_super_sub_and_lists():
    from PyQt6.QtGui import QTextCharFormat
    fmts = _word_fmts("[up (super=true)] [down (sub=true)]")
    assert fmts["up"].verticalAlignment() == \
        QTextCharFormat.VerticalAlignment.AlignSuperScript
    assert fmts["down"].verticalAlignment() == \
        QTextCharFormat.VerticalAlignment.AlignSubScript
    from ui.widgets.lite_designer.rich_txt import txt_to_display_doc
    _qt()
    doc = txt_to_display_doc("\u2022 point one\n2. point two")
    assert doc.findBlockByNumber(0).blockFormat().indent() == 1
    assert doc.findBlockByNumber(1).blockFormat().indent() == 1
    assert "point one" in doc.findBlockByNumber(0).text()


def _editor_word_fmt(text: str):
    """{word: (char format, block format)} for the full editor loader."""
    from ui.widgets.lite_designer.rich_txt import txt_to_doc
    _qt()
    doc = txt_to_doc(text)
    out = {}
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                ft = frag.text().replace("\u2029", "")
                if ft.strip():
                    out[ft.strip()] = (frag.charFormat(), block.blockFormat())
            it += 1
    return out, doc


def test_loader_suppresses_non_display_visuals():
    """Non-display params load as metadata with zero native metrics —
    the edit pane stays inviolable while the model stays lossless."""
    from PyQt6.QtGui import QTextFormat, QFont
    from PyQt6.QtCore import Qt
    from ui.widgets.lite_designer.rich_txt import (
        COLOR_PROP, CASE_PROP, FONT_PROP, ALIGN_PROP, DIR_PROP, SPACING_PROP)
    pairs, _doc = _editor_word_fmt(
        "[w (color=#112233; case=upper; font=Georgia; align=center; "
        "spacing=1.5; dir=rtl)]")
    cf, bf = pairs["w"]
    assert not cf.hasProperty(QTextFormat.Property.ForegroundBrush)
    assert not cf.hasProperty(QTextFormat.Property.FontFamilies)
    assert cf.fontCapitalization() == QFont.Capitalization.MixedCase
    assert cf.property(COLOR_PROP) == "#112233"
    assert cf.property(CASE_PROP) == "upper"
    assert cf.property(FONT_PROP) == "Georgia"
    assert not (bf.alignment() & (Qt.AlignmentFlag.AlignCenter
                                  | Qt.AlignmentFlag.AlignRight
                                  | Qt.AlignmentFlag.AlignJustify))
    assert bf.layoutDirection() != Qt.LayoutDirection.RightToLeft
    assert bf.property(ALIGN_PROP) == "center"
    assert bf.property(DIR_PROP) == "rtl"
    assert float(bf.property(SPACING_PROP)) == 1.5


def test_all_params_round_trip():
    """Char params round-trip exactly; block params survive via the
    whole-line wrap. (Mixing both in ONE bracket nests on emit — a
    pre-existing serializer limitation, unchanged here — so block keys
    ride their own whole-line run, the supported authoring shape.)"""
    char_src = ("[all (bold=true; italics=true; underline=true; strike=true; "
                "color=#112233; size=24; case=upper; super=true; "
                "outline=#445566; font=Georgia)]")
    assert _runs(_roundtrip(char_src)) == _runs(char_src)
    block_src = "[line (align=center; spacing=1.5; dir=rtl)]"
    out = _roundtrip(block_src)
    for key in ("align=center", "spacing=1.5", "dir=rtl"):
        assert key in out, out
    assert _runs(out) == _runs(block_src)


def test_ribbon_non_display_applies_props_not_metrics():
    from PyQt6.QtGui import QTextCursor, QTextFormat, QFont
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTextEdit
    from ui.widgets.lite_designer.format_ribbon import FormatRibbon
    from ui.widgets.lite_designer.rich_txt import (
        txt_to_doc, doc_to_txt, COLOR_PROP, CASE_PROP, FONT_PROP,
        ALIGN_PROP, DIR_PROP)
    _qt()
    edit = QTextEdit()
    edit.setDocument(txt_to_doc("plain words here"))
    ribbon = FormatRibbon()
    ribbon.set_editor(edit)
    cursor = edit.textCursor()
    cursor.select(QTextCursor.SelectionType.Document)
    edit.setTextCursor(cursor)
    # Color (standing in for the color dialog result) / case / font:
    # props set, natives untouched.
    fmt = __import__("PyQt6.QtGui", fromlist=["QTextCharFormat"]).QTextCharFormat()
    fmt.setProperty(COLOR_PROP, "#ff0000")
    ribbon._merge(fmt)
    cf = edit.textCursor().charFormat()
    assert cf.property(COLOR_PROP) == "#ff0000"
    assert not cf.hasProperty(QTextFormat.Property.ForegroundBrush)
    ribbon._on_case(True)
    cf = edit.textCursor().charFormat()
    assert cf.property(CASE_PROP) == "upper"
    assert cf.fontCapitalization() == QFont.Capitalization.MixedCase
    assert ribbon._btn_upper.isChecked()
    # Align / direction: block props set, native metrics untouched.
    ribbon._on_align("center")
    bf = edit.textCursor().blockFormat()
    assert bf.property(ALIGN_PROP) == "center"
    assert not (bf.alignment() & Qt.AlignmentFlag.AlignCenter)
    assert ribbon._align_btns["center"].isChecked()
    ribbon._on_direction(True)
    bf = edit.textCursor().blockFormat()
    assert bf.property(DIR_PROP) == "rtl"
    assert bf.layoutDirection() != Qt.LayoutDirection.RightToLeft
    assert ribbon._btn_rtl.isChecked()
    # Everything serializes.
    out = doc_to_txt(edit.document())
    for key in ("color=#ff0000", "case=upper", "align=center", "dir=rtl"):
        assert key in out, out


def test_normalize_folds_everything():
    """Smuggled natives (rich paste) fold into props; indent survives;
    block scrub returns metrics to defaults; model keeps it all."""
    from PyQt6.QtGui import (QTextCharFormat, QTextCursor, QTextDocument,
                             QTextBlockFormat, QTextFormat, QFont, QColor,
                             QBrush)
    from PyQt6.QtCore import Qt
    from ui.widgets.lite_designer.rich_txt import (
        normalize_formatting, doc_to_txt, COLOR_PROP, CASE_PROP, FONT_PROP,
        ALIGN_PROP, DIR_PROP, SPACING_PROP)
    _qt()
    doc = QTextDocument()
    cursor = QTextCursor(doc)
    fmt = QTextCharFormat()
    fmt.setForeground(QBrush(QColor("#123456")))
    fmt.setFontCapitalization(QFont.Capitalization.AllUppercase)
    fmt.setFontFamily("Georgia")
    fmt.setFontPointSize(30 * 0.75)
    cursor.insertText("smuggled", fmt)
    cursor.insertBlock()
    cursor.insertText("second line")
    second = doc.findBlockByNumber(1)
    bfmt = QTextBlockFormat()
    bfmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    bfmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    bfmt.setLineHeight(150.0, 1)
    bfmt.setIndent(1)
    bcursor = QTextCursor(second)
    bcursor.setBlockFormat(bfmt)
    normalize_formatting(doc)
    normalize_formatting(doc)  # idempotent: second pass folds nothing
    out = doc_to_txt(doc)
    for key in ("color=#123456", "case=upper", "font=Georgia", "size=30",
                "align=center", "dir=rtl", "spacing=1.5"):
        assert key in out, out
    assert doc.findBlockByNumber(1).blockFormat().indent() == 1


def test_display_doc_gaps_and_hr_collapse():
    rows = _display_fmts("First\n[\\n (size=14)]\nSecond")
    assert [t for t, _ in rows] == ["First", "", "Second"], rows
    rows = _display_fmts("a\n[ (hr=true)]\nb")
    assert [t for t, _ in rows] == ["a", "", "b"], rows
    # HR runs are rule-only (full preview renders a rule, no words) —
    # cards show nothing for them.
    rows = _display_fmts("[keep (hr=true)]")
    assert rows[0][0] == "", rows
