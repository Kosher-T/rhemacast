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

from core.slide_parser import _iter_inline_parts, _is_gap_text

HR_BLOCK_PROP = QTextFormat.Property.UserProperty + 1
GAP_BLOCK_PROP = QTextFormat.Property.UserProperty + 2
OUTLINE_PROP = QTextFormat.Property.UserProperty + 3
# Qt6's setFontUnderline only flips the underline *style*, never marking the
# bool property — so explicit underline true/false from txt is tracked here.
# (setFontStrikeOut marks its property natively; SO_PROP covers symmetry and
# the ribbon-clearing contract.) Ribbon handlers that apply direct underline /
# strike / outline formatting MUST set/clear these props (see docstring).
UL_PROP = QTextFormat.Property.UserProperty + 4
SO_PROP = QTextFormat.Property.UserProperty + 5
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
                  "strike", "align", "spacing", "dir", "outline", "font",
                  "super", "sub", "hr")
_BLOCK_WRAP_KEYS = ("align", "spacing", "dir")


# ─── txt → QTextDocument ────────────────────────────────────────────────────

def _char_format_for(params: dict) -> QTextCharFormat:
    """QTextCharFormat for one parsed inline-run param dict."""
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
        fmt.setForeground(QBrush(QColor(params["color"])))
    if params.get("size_nominal") is not None:
        fmt.setFontPointSize(params["size_nominal"] * _PT_PER_PX)
    case = params.get("case")
    if case == "upper":
        fmt.setFontCapitalization(QFont.Capitalization.AllUppercase)
    elif case == "lower":
        fmt.setFontCapitalization(QFont.Capitalization.AllLowercase)
    elif case == "origin":
        fmt.setFontCapitalization(QFont.Capitalization.MixedCase)
    if params.get("super") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSuperScript)
    elif params.get("sub") is True:
        fmt.setVerticalAlignment(
            QTextCharFormat.VerticalAlignment.AlignSubScript)
    if params.get("font"):
        fmt.setFontFamily(params["font"])
    if params.get("outline"):
        color = QColor(params["outline"])
        fmt.setProperty(OUTLINE_PROP, params["outline"])
        # Editor-only cue: Qt cannot stroke text, so tint the background.
        cue = QColor(color)
        cue.setAlpha(38)
        fmt.setBackground(QBrush(cue))
    return fmt


def _apply_block_props(cursor: QTextCursor, props: dict):
    """Merge whole-line align/spacing/dir params as block formatting.

    Block keys are line-scoped: a run carrying them anywhere in the line
    aligns the whole line (last one wins). The serializer normalizes this
    to a whole-line wrap run, so the round-trip is stable.
    """
    block_fmt = QTextBlockFormat()
    if props.get("align") == "center":
        block_fmt.setAlignment(Qt.AlignmentFlag.AlignCenter)
    elif props.get("align") == "right":
        block_fmt.setAlignment(Qt.AlignmentFlag.AlignRight)
    elif props.get("align") == "justify":
        block_fmt.setAlignment(Qt.AlignmentFlag.AlignJustify)
    if props.get("dir") == "rtl":
        block_fmt.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    elif props.get("dir") == "ltr":
        block_fmt.setLayoutDirection(Qt.LayoutDirection.LeftToRight)
    if props.get("spacing") is not None:
        block_fmt.setLineHeight(props["spacing"] * 100.0, _LINE_PROPORTIONAL)
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


# ─── QTextDocument → txt ────────────────────────────────────────────────────

def _params_for_fragment(fmt: QTextCharFormat) -> dict:
    """Sparse run params for one fragment's char format (None = inherit)."""
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
    if fmt.hasProperty(QTextFormat.Property.ForegroundBrush):
        brush = fmt.foreground()
        if isinstance(brush, QBrush) and brush.color().isValid():
            # Skip brushes we added as editor cues (outline tint, HR gray).
            params["color"] = brush.color().name()
    if fmt.hasProperty(QTextFormat.Property.FontPointSize):
        params["size"] = max(1, round(fmt.fontPointSize() / _PT_PER_PX))
    if fmt.hasProperty(QTextFormat.Property.FontCapitalization):
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
    if fmt.hasProperty(QTextFormat.Property.FontFamilies):
        family = fmt.fontFamily()
        if family:
            params["font"] = family
    if fmt.hasProperty(OUTLINE_PROP):
        params["outline"] = fmt.property(OUTLINE_PROP)
        params.pop("color", None)  # cue brush was never real text color
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

    base_spacing (the deck's spacing) suppresses redundant spacing wraps —
    the editor paints deck spacing onto blocks purely for WYSIWYG.
    """
    out: dict = {}
    bfmt = block.blockFormat()
    align = bfmt.alignment()
    if align & Qt.AlignmentFlag.AlignCenter:
        out["align"] = "center"
    elif align & Qt.AlignmentFlag.AlignRight:
        out["align"] = "right"
    elif align & Qt.AlignmentFlag.AlignJustify:
        out["align"] = "justify"
    if bfmt.layoutDirection() == Qt.LayoutDirection.RightToLeft:
        out["dir"] = "rtl"
    if bfmt.lineHeightType() == _LINE_PROPORTIONAL:
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
