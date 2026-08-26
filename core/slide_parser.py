"""
core/slide_parser.py

Strict parser for slide/song txt files.

Format:
  # or % at line start = title (first occurrence wins, not displayed)
  * at line start = section marker (not displayed, spans slides until next *)
  plain lines = slide content (displayed)
  double blank line (\\n\\n\\n = two consecutive empty lines) = slide boundary
    single newline = line break within same slide; single blank line is ignored
    (not a boundary) to allow readable spacing without splitting slides

Output: {"title": str, "slides": [{"section": str|None, "text": str}]}
Each entry in slides = one displayable slide. Section may be None if none set.
"""

import html
import re

_TITLE_RE = re.compile(r"^[#%]\s*(.+?)\s*$")
_SECTION_RE = re.compile(r"^\*\s*(.+?)\s*$")

# Inline color markup:  this is [the text: (#ff0000)] I want to color
# The bracketed run is displayed in the given hex color; rest uses theme color.
_INLINE_COLOR_RE = re.compile(r"\[([^\[\]:]+):\s*\(#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\)\]")


def strip_inline_markup(text: str) -> str:
    """Remove inline color markup, keeping the inner text (for FTS indexing)."""
    return _INLINE_COLOR_RE.sub(lambda m: m.group(1), text or "")


def inline_markup_to_html(text: str) -> str:
    """Convert inline color markup to HTML spans; everything else escaped.

    'this is [the text: (#ff0000)] I want' →
    'this is &lt;...&gt;<span style="color:#ff0000">the text</span>...'
    """
    if not text:
        return ""
    out = []
    pos = 0
    for m in _INLINE_COLOR_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        color = m.group(2)
        # Normalize 3-digit hex (#f00 → #ff0000)
        if len(color) == 3:
            color = "".join(c * 2 for c in color)
        out.append(f'<span style="color:#{color.lower()}">{html.escape(m.group(1))}</span>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def has_inline_markup(text: str) -> bool:
    return bool(_INLINE_COLOR_RE.search(text or ""))


def parse_slide_txt(raw: str) -> dict:
    """
    Parse raw txt content into title + slides.

    Rules:
    - Title: first line matching ^[#%]\\s*(.+?)\\s*$ → title. Subsequent #/% lines ignored.
    - Section: line matching ^\\*\\s*(.+?)\\s*$ → sets current_section for following slides.
    - Slide: one or more non-empty, non-marker lines grouped until double blank line or EOF.
      Single newline = line break within same slide (\"Line A\\nLine B\").
      Single blank line (\\n\\n) is ignored — not a boundary, just readable spacing.
      Double blank line (\\n\\n\\n, i.e. two consecutive empty lines) = slide boundary.
    - Empty/whitespace-only raw → title "" and no slides.
    """
    if raw is None:
        raw = ""

    # Normalize line endings and strip BOM if present
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if raw.startswith("\ufeff"):
        raw = raw.lstrip("\ufeff")

    title: str | None = None
    current_section: str | None = None

    # We'll collect blocks: split by blank lines (one or more empty lines)
    # But we need to handle section markers and title markers which are not content.
    # Approach: iterate lines, building current slide buffer.

    slides: list[dict] = []
    # Buffer for lines in current slide
    current_lines: list[str] = []

    def flush_slide():
        nonlocal current_lines
        if not current_lines:
            return
        # Join with newline to preserve intra-slide line breaks, then strip
        text = "\n".join(current_lines).strip()
        # Collapse trailing/leading blank artifacts but keep internal single newlines
        # Also collapse multiple internal blank artefacts that slipped through (shouldn't)
        if text:
            slides.append({"section": current_section, "text": text})
        current_lines = []

    lines = raw.split("\n")

    consecutive_blank = 0

    for line in lines:
        stripped = line.strip()

        # Blank line handling: double blank (two consecutive empty lines) = slide boundary
        # Single blank is ignored (allows readable spacing without splitting)
        if stripped == "":
            consecutive_blank += 1
            if consecutive_blank == 2:
                flush_slide()
            # For 1 or >2 consecutive blanks, do not flush again — already bounded
            continue

        # Non-blank resets blank streak
        consecutive_blank = 0

        # Title marker — only first occurrence wins
        if _TITLE_RE.match(line):
            if title is None:
                m = _TITLE_RE.match(line)
                title = m.group(1).strip() if m else ""
                # Don't treat as content
                continue
            else:
                # Subsequent title-like lines are ignored per spec (not displayed)
                continue

        # Section marker
        if _SECTION_RE.match(line):
            # Flush any pending slide before switching section
            flush_slide()
            m = _SECTION_RE.match(line)
            current_section = m.group(1).strip() if m else None
            continue

        # Plain content line — part of current slide
        # Preserve as-is trimmed? Keep original leading/trailing stripped but internal intact
        # Use stripped version for display (user typed content, trim edges)
        current_lines.append(stripped)

    # Flush trailing slide
    flush_slide()

    if title is None:
        title = ""

    return {"title": title, "slides": slides}


def slides_to_text(slides: list[dict], separator: str = " \u2022 ") -> str:
    """
    Join slides into a single rolling/scrolling block with separator.
    Used for rolling display mode later. Each slide's internal newlines become spaces.
    """
    parts = []
    for s in slides:
        t = s.get("text", "").replace("\n", " ").strip()
        if t:
            parts.append(t)
    return separator.join(parts)
