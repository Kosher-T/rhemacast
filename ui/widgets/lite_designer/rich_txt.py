r"""
ui/widgets/lite_designer/rich_txt.py

Two-way conversion between slide-format txt (core.slide_parser) and
QTextDocument rich text for the Lite Designer word processor.

  txt_to_doc(text) -> QTextDocument   (load a slide into the editor)
  doc_to_txt(doc)  -> str             (serialize the editor back to txt)

Round-trip contract: doc_to_txt(txt_to_doc(t)) re-parses to the same runs
(verified in tests/test_lite_designer_serialize.py).

Editor-only representations (never hit the txt):
  - HR runs        → a centered "━━━━━" block tagged HR_BLOCK_PROP
  - Gap runs       → an empty block tagged GAP_BLOCK_PROP (+ optional size)
  - Outline runs   → OUTLINE_PROP color + translucent background tint cue
  - Literal bullets ("• ") / numbers ("1. ") → real QTextLists
  - Nominal sizes  → SIZE_PROP metadata (edit-pane glyphs stay fixed-size;
    preview still renders them — see display_text_px in slide_cards)

Known txt limits (inherited, not introduced here): no escape for `[`/`]`
that already look like runs, or for `\` (see docs/slide-format.md). Lines
that would parse as `#`/`%` title or `*` section markers are guarded with a
zero-width space so lyrics never silently become structure.
"""

from PyQt6.QtGui import (QTextDocument, QTextCursor, QTextCharFormat,
                         QTextBlockFormat, QTextFormat,
                         QFont, QColor, QBrush)
from PyQt6.QtCore import Qt

import re

from core.slide_parser import OUTLINE_NONE, _iter_inline_parts, _is_gap_text

HR_BLOCK_PROP = QTextFormat.Property.UserProperty + 1
GAP_BLOCK_PROP = QTextFormat.Property.UserProperty + 2
OUTLINE_PROP = QTextFormat.Property.UserProperty + 3
# Explicit "no outline" marker. A theme's `text_shadow` outlines text on the
# display, so simply removing OUTLINE_PROP would let the theme baseline win and
# the ribbon toggle would snap straight back on. Storing this sentinel is how a
# run overrides an inherited outline (the same trick QFont.Weight.Normal does
# for bold). Never serialized into the deck txt — an absent `outline=` param
# means "inherit".
OUTLINE_OFF = "off"
# Qt6's setFontUnderline only flips the underline *style*, never marking the
# bool property — so explicit underline true/false from txt is tracked here.
# (setFontStrikeOut marks its property natively; SO_PROP covers symmetry and
# the ribbon-clearing contract.) Ribbon handlers that apply direct underline /
# strike / outline formatting MUST set/clear these props (see docstring).
UL_PROP = QTextFormat.Property.UserProperty + 4
SO_PROP = QTextFormat.Property.UserProperty + 5
# Shadow lives in its own prop (not a Qt text-shadow, which cannot express a
# hard ring). Value is the canonical "8px 40% 3px #000000" string.
SHADOW_PROP = QTextFormat.Property.UserProperty + 6
SHADOW_OFF = "off"
# Nominal text size (px) likewise rides as metadata, never as a point size:
# edit-pane textboxes render one fixed size (see display_text_px), so size
# params must not touch glyph metrics — but they must survive editing and
# serialize back, and still render fully on preview. Ribbon size handlers
# MUST set this prop (and must NOT set a point size).
SIZE_PROP = QTextFormat.Property.UserProperty + 8
# Display-textbox rule, generalized: only bold/italics/underline/strike,
# super/sub and lists render in the pane. Every other param rides as
# metadata (lossless model + preview) and MUST NOT touch metrics:
# color/case/font as char props, align/dir/spacing as block props.
# Ribbon handlers for these MUST set the props, never the native formats.
COLOR_PROP = QTextFormat.Property.UserProperty + 9
CASE_PROP = QTextFormat.Property.UserProperty + 10
FONT_PROP = QTextFormat.Property.UserProperty + 11
ALIGN_PROP = QTextFormat.Property.UserProperty + 12
DIR_PROP = QTextFormat.Property.UserProperty + 13
SPACING_PROP = QTextFormat.Property.UserProperty + 14
# Mid-line gap/HR blocks glue to their same-line neighbors so the serializer
# can reproduce the original line exactly (no added/removed line breaks).
_GLUE_BEFORE_PROP = QTextFormat.Property.UserProperty + 6
_GLUE_AFTER_PROP = QTextFormat.Property.UserProperty + 7

_PT_PER_PX = 0.75  # editor points per format px (round-trips exactly)
# QTextBlockFormat.LineHeightTypes as raw ints: the PyQt6 setLineHeight
# binding rejects the enum itself. SingleHeight=0, ProportionalHeight=1.
_LINE_SINGLE = 0
_LINE_PROPORTIONAL = 1

_HR_GLYPH = "\u2501" * 24  # ━ box-drawing line for the editor HR block

_BULLET_PREFIX = "\u2022 "  # "• "

# Param order for emitted runs (mirrors format_to_line stability).
_RUN_KEY_ORDER = ("size", "bold", "color", "italics", "case", "underline",
                  "strike", "align", "spacing", "dir", "outline", "shadow",
                  "font",
                  "super", "sub", "hr")
_BLOCK_WRAP_KEYS = ("align", "spacing", "dir")


# ─── txt → QTextDocument ────────────────────────────────────────────────────

def _char_format_for(params: dict) -> QTextCharFormat:
    """QTextCharFormat for one parsed inline-run param dict.

    Renders bold/italics/underline/strike/super/sub natively (the
    display-textbox set); color/size/case/font ride as metadata props
    (inviolable pane, lossless model + preview).
    """
    fmt = QTextCharFormat()
    if params.get("bold") is True:
        fmt.setFontWeight(QFont.Weight.Bold)
    elif params.get("bold") is False:
        fmt.setFontWeight(QFont.Weight.Normal)
    if params.get("italics") is not None:
        fmt.setFontItalic(bool(params["italics"]))
    if params.get("underline") is not None:
        fmt.setFontUnderline(bool(params["underline"]))
        fmt.setProperty(UL_PROP, bool(params["underline"]))
    if params.get("strike") is not None:
        fmt.setFontStrikeOut(bool(params["strike"]))
        fmt.setProperty(SO_PROP, bool(params["strike"]))
    if params.get("color"):
        fmt.setProperty(COLOR_PROP, params["color"])
    if params.get("size_nominal") is not None:
        # Metadata only — never a point size (edit-pane text is fixed).
        fmt.setProperty(SIZE_PROP, int(params["size_nominal"]))
    case = params.get("case")
    if case in ("upper", "lower", "origin"):
        fmt.setProperty(CASE_PROP, case)
    if params.get("super") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif params.get("sub") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSubScript)
    if params.get("font"):
        fmt.setProperty(FONT_PROP, params["font"])
    if params.get("outline"):
        outline = params["outline"]
        fmt.setProperty(OUTLINE_PROP,
                        OUTLINE_OFF if outline == OUTLINE_NONE else outline)
    if params.get("shadow"):
        shadow = params["shadow"]
        fmt.setProperty(SHADOW_PROP,
                        SHADOW_OFF if shadow == OUTLINE_NONE else shadow)
    return fmt


def _apply_block_props(cursor: QTextCursor, props: dict):
    """Merge whole-line align/spacing/dir params as block metadata.

    Block keys are line-scoped: a run carrying them anywhere in the line
    aligns the whole line (last one wins). They ride as custom props —
    never native formats — so the edit pane stays inviolable; the
    serializer normalizes explicit values to whole-line wrap runs, so
    the round-trip is stable.
    """
    block_fmt = QTextBlockFormat()
    if props.get("align") in ("left", "center", "right", "justify"):
        block_fmt.setProperty(ALIGN_PROP, props["align"])
    if props.get("dir") in ("rtl", "ltr"):
        block_fmt.setProperty(DIR_PROP, props["dir"])
    if props.get("spacing") is not None:
        try:
            block_fmt.setProperty(SPACING_PROP, float(props["spacing"]))
        except (TypeError, ValueError):
            pass
    cursor.mergeBlockFormat(block_fmt)


def _place_block(cursor: QTextCursor, fresh: bool, fmt: QTextBlockFormat):
    """Use the current block (fresh line) or open a new one, then format it.

    Returns True (the line is now "used" — subsequent content appends).
    """
    if fresh and cursor.block().length() == 1:
        cursor.setBlockFormat(fmt)
    else:
        cursor.insertBlock(fmt)
    return True


def _insert_gap_block(cursor: QTextCursor, fresh: bool, size,
                      glue_before: bool = False, glue_after: bool = False):
    """Empty sized block standing in for a paragraph-gap run.

    Always leaves the cursor in a FRESH block after the gap, so text
    following a mid-line gap lands in its own block instead of being
    swallowed by the gap marker. glue_* record same-line adjacency for
    the serializer (see doc_to_txt).
    """
    block_fmt = QTextBlockFormat()
    block_fmt.setProperty(GAP_BLOCK_PROP, size if size is not None else True)
    if glue_before:
        block_fmt.setProperty(_GLUE_BEFORE_PROP, True)
    if glue_after:
        block_fmt.setProperty(_GLUE_AFTER_PROP, True)
    _place_block(cursor, fresh, block_fmt)
    if size is not None:
        # Empty block at the gap size → the gap *looks* its height.
        cue = QTextCharFormat()
        cue.setFontPointSize(size * _PT_PER_PX)
        cursor.setBlockCharFormat(cue)
    cursor.insertBlock()
    # insertBlock inherits the gap's format — scrub it so following text
    # lands in a genuinely fresh block.
    cursor.setBlockFormat(QTextBlockFormat())


def _split_block(cursor: QTextCursor, fresh: bool):
    """Plain block boundary (a bare break): new scrubbed block, cursor in it.

    No-op when the line hasn't placed anything yet — the cursor already
    sits on a fresh boundary.
    """
    if fresh:
        return
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())


def _insert_hr_block(cursor: QTextCursor, fresh: bool,
                     glue_before: bool = False, glue_after: bool = False):
    block_fmt = QTextBlockFormat()
    block_fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    block_fmt.setProperty(HR_BLOCK_PROP, True)
    if glue_before:
        block_fmt.setProperty(_GLUE_BEFORE_PROP, True)
    if glue_after:
        block_fmt.setProperty(_GLUE_AFTER_PROP, True)
    _place_block(cursor, fresh, block_fmt)
    cue = QTextCharFormat()
    cue.setForeground(QBrush(QColor("#64748b")))
    cursor.insertText(_HR_GLYPH, cue)
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())  # don't inherit the HR tag


_LIST_BULLET_RE = re.compile(r"^\u2022\s+(.*)$")
_LIST_NUMBER_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def _list_kind(line: str):
    """'bullet' | 'ordered' | None — literal prefixes stay literal in txt."""
    if _LIST_BULLET_RE.match(line):
        return "bullet"
    if _LIST_NUMBER_RE.match(line):
        return "ordered"
    return None


def txt_to_doc(text: str) -> QTextDocument:
    """Load one slide's raw txt into an editable document."""
    doc = QTextDocument()
    # Slim margins: the editor height-fits to content, and slim chrome keeps
    # the live editor visually identical to the static QLabel it replaces.
    doc.setDocumentMargin(2)
    cursor = QTextCursor(doc)
    first = True

    for line in (text or "").split("\n"):
        # A line that follows a gap/HR already sits in a fresh block.
        if not first and not fresh:
            cursor.insertBlock()
        first = False
        fresh = True  # current block untouched by this line so far

        # Literal list prefixes persist as text; the indent is editor-only.
        line = line.strip()
        if _list_kind(line):
            indent = QTextBlockFormat()
            indent.setIndent(1)
            cursor.mergeBlockFormat(indent)

        # Block keys are line-scoped (last wins); per-run application below.
        parts = list(_iter_inline_parts(line))

        for pi, (part, params) in enumerate(parts):
            followed = pi < len(parts) - 1  # more of this line still to come
            if params is not None and params.get("hr") is True:
                _insert_hr_block(cursor, fresh,
                                 glue_before=not fresh, glue_after=followed)
                fresh = True
            elif params is not None and _is_gap_text(part):
                size = params.get("size_nominal")
                if size is None and followed:
                    # Bare mid-line gap = one break = plain block split.
                    _split_block(cursor, fresh)
                else:
                    _insert_gap_block(cursor, fresh, size,
                                      glue_before=not fresh,
                                      glue_after=followed)
                fresh = True
            elif params is None:
                # Bare \n markers inside plain text are plain breaks.
                segs = part.split("\\n")
                for i, seg in enumerate(segs):
                    if i:
                        _split_block(cursor, fresh)
                        fresh = True
                    if seg:
                        # Explicit default format: the cursor otherwise keeps
                        # the previous run's char format (format leak).
                        cursor.insertText(seg, QTextCharFormat())
                        fresh = False
            else:
                cursor.insertText(part, _char_format_for(params))
                fresh = False
                block_keys = {k: params[k] for k in _BLOCK_WRAP_KEYS
                              if params.get(k) is not None}
                if block_keys:
                    _apply_block_props(cursor, block_keys)

    return doc


# ─── txt → restricted display document ──────────────────────────────────

def _subset_char_format(params: dict) -> QTextCharFormat:
    """Char format for card display: the display-textbox set ONLY.

    Renders bold, italics, underline, strikethrough, super/subscript.
    Every other param (color, size, case, align, spacing, outline, dir,
    font, hr) is ignored — the words render as normal text. The full
    styling still lives in the slide txt and renders on preview.
    Display-only: no UL_PROP/SO_PROP tracking (card documents are never
    serialized back).
    """
    fmt = QTextCharFormat()
    if params.get("bold") is True:
        fmt.setFontWeight(QFont.Weight.Bold)
    elif params.get("bold") is False:
        fmt.setFontWeight(QFont.Weight.Normal)
    if params.get("italics") is not None:
        fmt.setFontItalic(bool(params["italics"]))
    if params.get("underline") is True:
        fmt.setFontUnderline(True)
    if params.get("strike") is True:
        fmt.setFontStrikeOut(True)
    if params.get("super") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif params.get("sub") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSubScript)
    return fmt


def txt_to_display_doc(text: str) -> QTextDocument:
    """Restricted rich view of one slide's txt for the card display boxes.

    Renders the display-textbox set — bold, italics, underline,
    strikethrough, super/subscript, bullet and numbered lists (literal
    prefix + indent) — and only that set. Gap runs collapse to a plain
    break, HR runs are skipped (rule-only), block keys are ignored, and
    list prefixes stay literal text. The slide txt itself is untouched,
    so nothing is ever lost from the model.
    """
    from core.slide_parser import is_hr_run
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    cursor = QTextCursor(doc)
    first = True
    for line in (text or "").split("\n"):
        if not first:
            cursor.insertBlock()
        first = False
        stripped = line.strip()
        if _list_kind(stripped):
            indent = QTextBlockFormat()
            indent.setIndent(1)
            cursor.mergeBlockFormat(indent)
        for part, params in _iter_inline_parts(line):
            if params is not None and is_hr_run(params):
                continue  # rule-only: no words to show
            if params is not None and _is_gap_text(part):
                continue  # gap-only: the block break above is the break
            if params is None:
                segs = part.split("\\n")
                for i, seg in enumerate(segs):
                    if i:
                        cursor.insertBlock()
                    if seg:
                        cursor.insertText(seg, QTextCharFormat())
            else:
                words = (part or "").replace("\\n", "")
                if words:
                    cursor.insertText(words, _subset_char_format(params))
    return doc


# ─── QTextDocument → txt ────────────────────────────────────────────────────
def _params_for_fragment(fmt: QTextCharFormat) -> dict:
    """Sparse run params for one fragment's char format (None = inherit).

    Prop channels win (the edit pane's metadata); native formats are the
    legacy fallback (rich pastes not yet normalized).
    """
    params: dict = {}
    if fmt.hasProperty(QTextFormat.Property.FontWeight):
        params["bold"] = fmt.fontWeight() >= 600
    if fmt.hasProperty(QTextFormat.Property.FontItalic):
        params["italics"] = bool(fmt.fontItalic())
    if fmt.hasProperty(UL_PROP):
        params["underline"] = bool(fmt.property(UL_PROP))
    elif fmt.underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline:
        params["underline"] = True  # ribbon-applied, never loaded-false
    if fmt.hasProperty(SO_PROP):
        params["strike"] = bool(fmt.property(SO_PROP))
    elif fmt.hasProperty(QTextFormat.Property.FontStrikeOut):
        params["strike"] = bool(fmt.fontStrikeOut())
    if fmt.hasProperty(COLOR_PROP):
        color = fmt.property(COLOR_PROP)
        if color:
            params["color"] = color
    elif fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
        brush = fmt.foreground()
        if isinstance(brush, QBrush) and brush.color().isValid():
            params["color"] = brush.color().name()
    if fmt.hasProperty(SIZE_PROP):
        try:
            params["size"] = max(1, int(fmt.property(SIZE_PROP)))
        except (TypeError, ValueError):
            pass
    elif fmt.hasProperty(QTextFormat.Property.FontPointSize):
        # Legacy path: point sizes predate SIZE_PROP (e.g. rich pastes not
        # yet normalized) — still serialize rather than drop.
        params["size"] = max(1, round(fmt.fontPointSize() / _PT_PER_PX))
    if fmt.hasProperty(CASE_PROP):
        case = fmt.property(CASE_PROP)
        if case in ("upper", "lower", "origin"):
            params["case"] = case
    elif fmt.hasProperty(QTextFormat.Property.FontCapitalization):
        cap = fmt.fontCapitalization()
        if cap == QFont.Capitalization.AllUppercase:
            params["case"] = "upper"
        elif cap == QFont.Capitalization.AllLowercase:
            params["case"] = "lower"
        else:
            params["case"] = "origin"
    va = fmt.verticalAlignment()
    if va == QTextCharFormat.VerticalAlignment.AlignSuperScript:
        params["super"] = True
    elif va == QTextCharFormat.VerticalAlignment.AlignSubScript:
        params["sub"] = True
    if fmt.hasProperty(FONT_PROP):
        family = fmt.property(FONT_PROP)
        if family:
            params["font"] = family
    elif fmt.hasProperty(QTextFormat.Property.FontFamilies):
        family = fmt.fontFamily()
        if family:
            params["font"] = family
    if fmt.hasProperty(SHADOW_PROP):
        shadow = fmt.property(SHADOW_PROP)
        if shadow == SHADOW_OFF:
            params["shadow"] = OUTLINE_NONE
        elif shadow:
            params["shadow"] = shadow
    if fmt.hasProperty(OUTLINE_PROP):
        outline = fmt.property(OUTLINE_PROP)
        # OUTLINE_OFF is written out as `outline=none`: the deck must carry
        # the override, or the theme's outline reasserts itself on display.
        if outline == OUTLINE_OFF:
            params["outline"] = OUTLINE_NONE
        elif outline:
            params["outline"] = outline
    return params


def _emit_run(text: str, params: dict) -> str:
    """One [text (k=v; …)] run; surrounding whitespace stays outside."""
    lead = text[:len(text) - len(text.lstrip())]
    trail = text[len(text.rstrip()):]
    core = text.strip()
    if not core:
        return text
    keys = [k for k in _RUN_KEY_ORDER if params.get(k) is not None]
    if not keys:
        return text
    # Booleans serialize lowercase; numbers as-is.
    body = "; ".join(
        f"{k}={'true' if params[k] is True else 'false' if params[k] is False else params[k]}"
        for k in _RUN_KEY_ORDER if params.get(k) is not None)
    return f"{lead}[{core} ({body})]{trail}"


def insert_hr_at(cursor: QTextCursor):
    """Insert an editor HR block at the cursor (ribbon HR button).

    Same shape the loader builds, so it serializes back identically.
    """
    block_fmt = QTextBlockFormat()
    block_fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    block_fmt.setProperty(HR_BLOCK_PROP, True)
    if cursor.block().length() > 1:
        cursor.insertBlock(block_fmt)
    else:
        cursor.setBlockFormat(block_fmt)
    cue = QTextCharFormat()
    cue.setForeground(QBrush(QColor("#64748b")))
    cursor.insertText(_HR_GLYPH, cue)
    cursor.insertBlock()
    cursor.setBlockFormat(QTextBlockFormat())


def normalize_formatting(doc: QTextDocument, base_spacing=None):
    """Fold smuggled formatting into metadata props (visual fixed-size).

    Rich pastes can smuggle real point sizes, colors, capitalizations,
    families, alignments, directions and line heights into the document;
    the edit pane renders only bold/italics/underline/strike/super/sub
    and lists. Each smuggled value keeps its nominal form as a prop (so
    it still serializes and previews) while metrics return to defaults.
    Block indents (lists) are always preserved. Idempotent: a second
    pass finds nothing to fold.
    """
    cursor = QTextCursor(doc)
    # Collect first: rewriting formats can merge fragments, which would
    # invalidate a live iterator.
    char_ranges: list[tuple[int, int, QTextCharFormat]] = []
    default_family = doc.defaultFont().family()
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                fmt = frag.charFormat()
                fixed = QTextCharFormat(fmt)
                dirty = False
                if fmt.hasProperty(QTextFormat.Property.FontPointSize) \
                        and not fmt.hasProperty(SIZE_PROP):
                    fixed.clearProperty(QTextFormat.Property.FontPointSize)
                    try:
                        fixed.setProperty(
                            SIZE_PROP,
                            max(1, round(fmt.fontPointSize() / _PT_PER_PX)))
                    except (TypeError, ValueError):
                        pass
                    dirty = True
                if fmt.hasProperty(QTextFormat.Property.ForegroundBrush) \
                        and not fmt.hasProperty(COLOR_PROP):
                    brush = fmt.foreground()
                    if isinstance(brush, QBrush) and brush.color().isValid():
                        fixed.clearProperty(
                            QTextFormat.Property.ForegroundBrush)
                        fixed.setProperty(COLOR_PROP, brush.color().name())
                        dirty = True
                if fmt.hasProperty(
                        QTextFormat.Property.FontCapitalization) \
                        and not fmt.hasProperty(CASE_PROP):
                    cap = fmt.fontCapitalization()
                    fixed.clearProperty(
                        QTextFormat.Property.FontCapitalization)
                    if cap == QFont.Capitalization.AllUppercase:
                        fixed.setProperty(CASE_PROP, "upper")
                    elif cap == QFont.Capitalization.AllLowercase:
                        fixed.setProperty(CASE_PROP, "lower")
                    dirty = True
                if fmt.hasProperty(QTextFormat.Property.FontFamilies) \
                        and not fmt.hasProperty(FONT_PROP):
                    family = fmt.fontFamily()
                    fixed.clearProperty(QTextFormat.Property.FontFamilies)
                    if family and family != default_family:
                        fixed.setProperty(FONT_PROP, family)
                    dirty = True
                if fmt.hasProperty(QTextFormat.Property.BackgroundBrush):
                    fixed.clearProperty(QTextFormat.Property.BackgroundBrush)
                    dirty = True
                if dirty:
                    char_ranges.append(
                        (frag.position(), frag.length(), fixed))
            it += 1
    for pos, length, fixed in char_ranges:
        cursor.setPosition(pos)
        cursor.setPosition(pos + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fixed)
    # Blocks (skip structural HR/GAP blocks): fold alignment, direction
    # and non-deck line heights into props, then scrub metrics back to
    # defaults around the preserved indent.
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        bfmt = block.blockFormat()
        if bfmt.hasProperty(HR_BLOCK_PROP) or bfmt.hasProperty(GAP_BLOCK_PROP):
            continue
        props = QTextBlockFormat()
        fold = False
        align = bfmt.alignment()
        if align & Qt.AlignmentFlag.AlignCenter:
            key = "center"
        elif align & Qt.AlignmentFlag.AlignRight:
            key = "right"
        elif align & Qt.AlignmentFlag.AlignJustify:
            key = "justify"
        else:
            key = None
        if key is not None and not bfmt.hasProperty(ALIGN_PROP):
            props.setProperty(ALIGN_PROP, key)
            fold = True
        if bfmt.layoutDirection() == Qt.LayoutDirection.RightToLeft \
                and not bfmt.hasProperty(DIR_PROP):
            props.setProperty(DIR_PROP, "rtl")
            fold = True
        if bfmt.lineHeightType() == _LINE_PROPORTIONAL:
            lh = bfmt.lineHeight()
            if lh and lh != 100 and not bfmt.hasProperty(SPACING_PROP):
                spacing = round(lh / 100.0, 2)
                if base_spacing is None or spacing != round(base_spacing, 2):
                    props.setProperty(SPACING_PROP, spacing)
                    fold = True
        if not fold:
            continue
        scrub = QTextBlockFormat()
        scrub.setIndent(bfmt.indent())
        cursor.setPosition(block.position())
        cursor.setBlockFormat(scrub)
        cursor.mergeBlockFormat(props)


def normalize_sizes_to_props(doc: QTextDocument):
    """Legacy alias (sizes only) — prefer normalize_formatting."""
    normalize_formatting(doc)


def apply_spacing_to_doc(doc: QTextDocument, value: float | None):
    """Paint deck-level spacing onto every block (visual only).

    doc_to_txt(..., base_spacing=value) suppresses the redundant wraps, so
    this never spams per-block params — it just makes the editor WYSIWYG.
    """
    if value is None:
        return
    cursor = QTextCursor(doc)
    cursor.movePosition(QTextCursor.MoveOperation.Start)
    while True:
        fmt = QTextBlockFormat()
        fmt.setLineHeight(value * 100.0, _LINE_PROPORTIONAL)
        cursor.mergeBlockFormat(fmt)
        if not cursor.movePosition(QTextCursor.MoveOperation.NextBlock):
            break


def _guard_structure(line: str) -> str:
    """Keep lyric lines from parsing as title/section markers."""
    stripped = line.lstrip()
    if stripped[:1] in ("#", "%", "*"):
        return line.replace(stripped, "\u200b" + stripped, 1)
    return line


def _block_wrap_params(block, base_spacing=None) -> dict:
    """Non-default block alignment/direction/spacing → wrap-run params.

    Prop channels win (explicit line values, emitted verbatim — even
    "left"/"ltr", which override a deck-level value at render); native
    formats are the fallback (deck spacing paint, legacy data).
    base_spacing (the deck's spacing) suppresses redundant spacing wraps —
    the editor paints deck spacing onto blocks purely for WYSIWYG.
    """
    out: dict = {}
    bfmt = block.blockFormat()
    if bfmt.hasProperty(ALIGN_PROP):
        align = bfmt.property(ALIGN_PROP)
        if align in ("left", "center", "right", "justify"):
            out["align"] = align
    else:
        align = bfmt.alignment()
        if align & Qt.AlignmentFlag.AlignCenter:
            out["align"] = "center"
        elif align & Qt.AlignmentFlag.AlignRight:
            out["align"] = "right"
        elif align & Qt.AlignmentFlag.AlignJustify:
            out["align"] = "justify"
    if bfmt.hasProperty(DIR_PROP):
        direction = bfmt.property(DIR_PROP)
        if direction in ("rtl", "ltr"):
            out["dir"] = direction
    elif bfmt.layoutDirection() == Qt.LayoutDirection.RightToLeft:
        out["dir"] = "rtl"
    if bfmt.hasProperty(SPACING_PROP):
        try:
            spacing = round(float(bfmt.property(SPACING_PROP)), 2)
        except (TypeError, ValueError):
            spacing = None
        if spacing is not None and (base_spacing is None
                                    or spacing != round(base_spacing, 2)):
            out["spacing"] = spacing
    elif bfmt.lineHeightType() == _LINE_PROPORTIONAL:
        lh = bfmt.lineHeight()
        if lh and lh != 100:
            spacing = round(lh / 100.0, 2)
            if base_spacing is None or spacing != round(base_spacing, 2):
                out["spacing"] = spacing
    return out


def doc_to_txt(doc: QTextDocument, base_spacing=None) -> str:
    """Serialize an edited document back to one slide's raw txt.

    Blocks join with real newlines — except around mid-line gap/HR blocks,
    which glue to their same-line neighbors (no added/removed breaks).
    base_spacing suppresses wraps that merely echo the deck spacing.
    """
    # (text, glue_before, glue_after)
    rows: list[tuple[str, bool, bool]] = []
    for i in range(doc.blockCount()):
        block = doc.findBlockByNumber(i)
        bfmt = block.blockFormat()
        if bfmt.hasProperty(HR_BLOCK_PROP):
            rows.append(("[ (hr=true)]",
                         bool(bfmt.property(_GLUE_BEFORE_PROP)),
                         bool(bfmt.property(_GLUE_AFTER_PROP))))
            continue
        if bfmt.hasProperty(GAP_BLOCK_PROP):
            size = bfmt.property(GAP_BLOCK_PROP)
            marker = (f"[\\n (size={int(size)})]"
                      if size is not True else "[\\n]")
            rows.append((marker,
                         bool(bfmt.property(_GLUE_BEFORE_PROP)),
                         bool(bfmt.property(_GLUE_AFTER_PROP))))
            continue

        # Fragments → merged runs.
        chunks: list[str] = []
        pending_text: list[str] = []
        pending_params: dict | None = None

        def flush():
            if pending_text:
                text = "".join(pending_text)
                chunks.append(_emit_run(text, pending_params or {}))

        it = block.begin()
        while not it.atEnd():
            frag = it.fragment()
            if frag.isValid():
                ftext = frag.text()
                # Qt stores block breaks as U+2029 inside fragments — drop them.
                ftext = ftext.replace("\u2029", "")
                if ftext:
                    params = _params_for_fragment(frag.charFormat())
                    # Editor cue brushes (HR gray etc.) carry no meaning.
                    if pending_params == params:
                        pending_text.append(ftext)
                    else:
                        flush()
                        pending_text = [ftext]
                        pending_params = params
            it += 1
        flush()
        content = "".join(chunks)
        # List prefixes are plain text — they pass through untouched.

        wrap = _block_wrap_params(block, base_spacing)
        if wrap and content.strip():
            body = "; ".join(f"{k}={wrap[k]}" for k in _BLOCK_WRAP_KEYS if k in wrap)
            content = f"[{content.strip()} ({body})]"
        rows.append((_guard_structure(content) if content.strip() else "",
                     False, False))

    # Trailing empty blocks are cursor artifacts, not content.
    while rows and rows[-1][0] == "":
        rows.pop()
    out: list[str] = []
    for idx, (text, glue_before, _ga) in enumerate(rows):
        if idx == 0:
            out.append(text)
        elif rows[idx - 1][2] or glue_before:
            out[-1] += text  # same-line glue: no break either side
        else:
            out.append(text)
    return "\n".join(out)
