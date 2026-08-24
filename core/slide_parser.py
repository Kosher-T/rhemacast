"""
core/slide_parser.py

Strict parser for slide/song txt files.

Format:
  # or % at line start = title (first occurrence wins, not displayed)
  * at line start = section marker (not displayed, spans slides until next *)
  plain lines = slide content (displayed)
  blank line (\\n\\n) = slide boundary — single newline = line break within slide

Output: {"title": str, "slides": [{"section": str|None, "text": str}]}
Each entry in slides = one displayable slide. Section may be None if none set.
"""

import re

_TITLE_RE = re.compile(r"^[#%]\s*(.+?)\s*$")
_SECTION_RE = re.compile(r"^\*\s*(.+?)\s*$")


def parse_slide_txt(raw: str) -> dict:
    """
    Parse raw txt content into title + slides.

    Rules:
    - Title: first line matching ^[#%]\\s*(.+?)\\s*$ → title. Subsequent #/% lines ignored.
    - Section: line matching ^\\*\\s*(.+?)\\s*$ → sets current_section for following slides.
    - Slide: one or more non-empty, non-marker lines grouped until blank line or EOF.
      Single newlines within a contiguous block are joined with \\n preserved,
      but final slide text is stripped and normalized where empty lines are boundaries.
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

    for line in lines:
        stripped = line.strip()

        # Blank line = slide boundary
        if stripped == "":
            flush_slide()
            continue

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
