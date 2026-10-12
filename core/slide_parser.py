"""
core/slide_parser.py

Strict parser for slide/song txt files.

Format:
  # or % at line start = title (first occurrence wins, not displayed)
  * at line start = section marker (not displayed, spans slides until next *)
  a bare * alone on a line clears the current section (for section-less slides)
  plain lines = slide content (displayed)
  double blank line (\\n\\n\\n = two consecutive empty lines) = slide boundary
    single newline = line break within same slide; single blank line is ignored
    (not a boundary) to allow readable spacing without splitting slides

Output: {"title": str, "slides": [{"section": str|None, "text": str}]}
Each entry in slides = one displayable slide. Section may be None if none set.
"""

"""
core/slide_parser.py

Strict parser for slide/song txt files.

Format:
  Top-level format line (optional, before the title — overrides theme):
    size=35, 25, 35; bold=true; color=#66ff00; italics=false; case=origin
    size = nominal, min, max px for autoresize (missing parts inherit theme)
    case = upper | lower | origin (origin = text as written)
  # or % at line start = title (first occurrence wins, not displayed)
  * at line start = section marker (not displayed, spans slides until next *)
  a bare * alone on a line clears the current section (for section-less slides)
  plain lines = slide content (displayed)
  double blank line (\\n\\n\\n = two consecutive empty lines) = slide boundary
    single newline = line break within same slide; single blank line is ignored
    (not a boundary) to allow readable spacing without splitting slides
  Inline runs (override deck + theme for the bracketed words):
    [words (color=#ff6600; size=20; italics=true; bold=false; case=upper)]
    params must be the final (...) group; unknown/invalid params are skipped.
    Legacy [words: (#hex)] still parses as color-only.

  Cascade (ascending importance): theme → deck format line → inline run.

Output: {"title": str, "slides": [{"section": str|None, "text": str}],
          "format": {"size_nominal"|"size_min"|"size_max"|"bold"|"color"|"italics"|"case"}}
  Slide text keeps inline markers RAW; renderers convert at display time.
  Unset format values are None (= inherit). Full agent-editable spec lives in
  docs/slide-format.md.

  Sections: each slide also carries "marker": True when its own `*` marker
  line (or bare `*` clear) introduced it, False when it merely inherits the
  sticky section from above. slide_owns_marker() reads the flag with a
  value-change fallback for marker-less dicts (EasyWorship imports, old DB
  rows, hand-built tests) — so old data groups exactly as before.
"""

import html
import logging
import math
import re

logger = logging.getLogger(__name__)

_TITLE_RE = re.compile(r"^[#%]\s*(.+?)\s*$")
_SECTION_RE = re.compile(r"^\*\s*(.+?)\s*$")

# Inline run: [display text (k=v; k=v)] — text has no brackets; the params
# group holds no parens. Legacy [text: (#hex)] matches this shape too and is
# reinterpreted as color-only when the params don't parse as k=v pairs.
# Paragraph gap: a bare \n marker (typed backslash-n) is a line break whose
# size is controllable — [\n (size=14)] renders a 14px gap, [\n] a plain one.
_INLINE_RUN_RE = re.compile(r"\[([^\[\]]+?)(?:\s*\(([^()]*)\))?\]")
_LEGACY_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_LEGACY_TEXT_RE = re.compile(r"^(.*):\s*$")

_FORMAT_KEYS = ("size", "bold", "color", "italics", "case",
                 "underline", "strike", "align", "spacing",
                 "super", "sub", "outline", "shadow", "dir", "hr", "font")
_TRUE_SET = {"true", "1", "yes"}
_FALSE_SET = {"false", "0", "no"}
_CASE_SET = {"upper", "lower", "origin"}
_ALIGN_SET = {"left", "center", "right", "justify"}
_DIR_SET = {"rtl", "ltr"}


def blank_deck_format() -> dict:
    """All-None deck format (= inherit everything from the theme)."""
    return {"size_nominal": None, "size_min": None, "size_max": None,
            "bold": None, "color": None, "italics": None, "case": None,
            "underline": None, "strike": None, "align": None,
            "spacing": None, "super": None, "sub": None, "outline": None,
            "shadow": None, "dir": None, "hr": None, "font": None}


def _parse_bool(value: str):
    v = value.strip().lower()
    if v in _TRUE_SET:
        return True
    if v in _FALSE_SET:
        return False
    return None


def _outline_ring(value: str) -> str:
    """Convert a stored outline value into a CSS text-shadow LIST.

    The outline is a ring of hard text shadows, NOT -webkit-text-stroke:
    a stroke straddles the glyph outline, so half of it grows *inwards*
    and eats the letterform (at 25px the word stops being readable).
    Shadows only ever sit outside the glyph, and because every shadow is
    painted before any glyph fill, a letter's outline also ends up behind
    its neighbours' fills instead of smearing over them.

    The ring resolution scales with the thickness so the outer contour
    stays smooth instead of scalloped, capped at 48 shadows.
    """
    v = value.strip()
    m = re.match(r"^(\d+(?:\.\d+)?)px\s+(.+)$", v, re.IGNORECASE)
    if m:
        try:
            radius = int(round(float(m.group(1))))
        except ValueError:
            radius = 1
        color = _parse_hex_color(m.group(2).strip())
    else:
        radius = 1
        color = _parse_hex_color(v)
    if color is None:
        return ""
    # Same bound as OUTLINE_MAX_PX (kept in sync with the JS renderers by
    # test_outline_ring_agrees_across_renderers).
    from core.constants import OUTLINE_MIN_PX, OUTLINE_MAX_PX
    radius = max(OUTLINE_MIN_PX, min(OUTLINE_MAX_PX, radius))
    steps = min(48, max(12, round(radius * 1.9)))
    ring = []
    seen = set()
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        dx = int(round(math.cos(angle) * radius))
        dy = int(round(math.sin(angle) * radius))
        if not dx and not dy:
            continue  # a dead-centre shadow would be invisible
        if (dx, dy) in seen:
            continue  # at small radii several angles round to one offset
        seen.add((dx, dy))
        ring.append(f"{dx}px {dy}px 0 {color}")
    return ",".join(ring)


def _outline_to_css(value: str) -> str:
    """The outline as a text-shadow declaration for an inline span.

    The theme's own soft drop shadow rides along so an outlined run does not
    lose the depth the un-outlined runs keep.
    """
    ring = _outline_ring(value)
    if not ring:
        return ""
    return "text-shadow:" + ring + ",var(--rc-text-shadow,0 4px 12px rgba(0,0,0,0.4))"


# Canonical "no outline" value. The deck has to be able to SAY "off",
# otherwise an inherited (theme) outline reasserts itself on the display and
# the operator's toggle looks broken there while the button reads off.
OUTLINE_NONE = "none"


def _parse_outline(value: str):
    """Normalize an outline value for the format dict.

    Accepts the legacy bare color ("#ff0000"), the explicit form
    "2px #ff0000", and "none"/"off" for an explicit no-outline override.
    Returns the canonical string consumed by _span_style.
    """
    v = value.strip()
    if v.lower() in ("none", "off"):
        return OUTLINE_NONE
    m = re.match(r"^(\d+(?:\.\d+)?)px\s+(.+)$", v, re.IGNORECASE)
    if m:
        color = _parse_hex_color(m.group(2).strip())
        if color is not None:
            return f"{m.group(1)}px {color}"
        return None
    return _parse_hex_color(v)


def _parse_shadow(value: str):
    """Normalize a shadow value: "<size>px <opacity>% <distance>px <#hex> <angle>".

    Opacity, distance and angle are optional, so the short forms "4px #000000"
    and "8px 40% #000000" work too (angle defaults to 45 = down-right).
    "none"/"off" is an explicit no-shadow.
    """
    v = value.strip()
    if v.lower() in ("none", "off"):
        return OUTLINE_NONE
    parts = v.split()
    # Trailing angle comes after the color ("... #hex 135"), so it is popped
    # first: a bare number (or Ndeg) that is not a color.
    angle = 45
    if parts and not parts[-1].startswith("#"):
        token = parts.pop().lower()
        if token.endswith("deg"):
            token = token[:-3]
        try:
            angle = int(round(float(token))) % 360
        except ValueError:
            return None
    color = None
    if parts and parts[-1].startswith("#"):
        color = _parse_hex_color(parts.pop())
        if color is None:
            return None
    size = None
    if parts:
        size = _px_int(parts.pop(0))
        if size is None:
            return None
    opacity = 100
    if parts:
        token = parts.pop(0)
        if not token.endswith("%"):
            return None
        try:
            opacity = int(round(float(token[:-1])))
        except ValueError:
            return None
    distance = 0
    if parts:
        distance = _px_int(parts.pop(0), default=0)
        if distance is None:
            return None
    if parts:
        return None  # trailing junk
    if color is None or (size is None and opacity == 100 and distance == 0):
        return None
    if size is None:
        size = 8
    from core.constants import (SHADOW_SIZE_MIN_PX, SHADOW_SIZE_MAX_PX,
                                SHADOW_DISTANCE_MIN_PX, SHADOW_DISTANCE_MAX_PX)
    return (f"{max(SHADOW_SIZE_MIN_PX, min(SHADOW_SIZE_MAX_PX, size))}px "
            f"{max(0, min(100, opacity))}% "
            f"{max(SHADOW_DISTANCE_MIN_PX, min(SHADOW_DISTANCE_MAX_PX, distance))}px "
            f"{color} {angle}")


def _px_int(token: str, default=None):
    """"12" / "12px" -> 12, else default (None means invalid)."""
    tok = token.strip()
    if tok.lower().endswith("px"):
        tok = tok[:-2].strip()
    try:
        return int(round(float(tok)))
    except ValueError:
        return default


def _shadow_ring(size: int, opacity: int, distance: int, color: str,
                 angle: int = 45) -> str:
    """One blurred, offset shadow (classic `text-shadow` look).

    The old ring stamped filled glyph copies around the text, so you could
    see the stacked letter shapes instead of a shadow. A real shadow is a
    single blurred copy displaced from the glyphs: `size` is the blur radius,
    `distance`/`angle` the offset (degrees, 0 = east, 90 = south). At
    distance 0 it reads as an outer glow. (Kept the historical name so the
    parser/renderer contract and tests keep referring to one builder.)
    """
    alpha = max(0, min(100, opacity)) / 100.0
    rad = math.radians(angle % 360)
    dx = int(round(distance * math.cos(rad)))
    dy = int(round(distance * math.sin(rad)))
    blur = max(0, size)
    a = round(alpha, 3)
    if a >= 1:
        paint = color
    else:
        paint = color_a(color, a)
    return f"{dx}px {dy}px {blur}px {paint}"


def color_a(color: str, alpha: float) -> str:
    """#rrggbb + alpha -> rgba(...) (kept separate: the theme path needs it)."""
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    # round() then int() so a whole alpha prints as "0", not "0.0" — the JS
    # renderer formats it the same way and the two must match byte for byte.
    a = int(round(alpha * 1000)) / 1000
    if a == int(a):
        a = int(a)
    return f"rgba({r}, {g}, {b}, {a})"


def _shadow_to_css(value: str) -> str:
    """A shadow value -> a text-shadow declaration, or"" if invalid."""
    parsed = _parse_shadow(value)
    if not parsed or parsed == OUTLINE_NONE:
        return ""
    size, rest = parsed.split(" ", 1)
    opacity, rest = rest.split(" ", 1)
    distance, rest = rest.split(" ", 1)
    color, _, angle = rest.rpartition(" ")
    ring = _shadow_ring(int(size[:-2]), int(opacity[:-1]),
                        int(distance[:-2]), color, int(angle))
    if not ring:
        return ""
    return "text-shadow:" + ring


def _parse_hex_color(value: str):
    """Normalize #rgb/#rrggbb → lowercase #rrggbb, or None if invalid."""
    m = re.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", value.strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.lower()


def _parse_int_list(value: str) -> list[int]:
    """Parse '35, 25, 35' (optional px suffixes) → ints, skipping junk."""
    out = []
    for part in value.split(","):
        part = part.strip()
        if part.lower().endswith("px"):
            part = part[:-2].strip()
        try:
            out.append(int(part))
        except ValueError:
            logger.warning(f"Ignoring unparsable size component: {part!r}")
    return out


def _apply_format_pair(fmt: dict, key: str, value: str, inline: bool):
    """Apply one k=v pair into a deck-format dict. Unknown/invalid → warn+skip."""
    key = key.strip().lower()
    if key not in _FORMAT_KEYS:
        logger.warning(f"Ignoring unknown format parameter: {key!r}")
        return
    if key == "size":
        nums = _parse_int_list(value)
        if inline:
            if nums:
                fmt["size_nominal"] = nums[0]  # spans take absolute px only
        else:
            # Positional: nominal, min, max — missing parts inherit the theme.
            for dest, num in zip(("size_nominal", "size_min", "size_max"), nums):
                fmt[dest] = num
    elif key in ("bold", "italics", "underline", "strike",
                   "super", "sub", "hr"):
        parsed = _parse_bool(value)
        if parsed is None:
            logger.warning(f"Ignoring invalid {key} value: {value!r} (want true/false)")
        else:
            fmt[key] = parsed
    elif key == "color":
        parsed = _parse_hex_color(value)
        if parsed is None:
            logger.warning(f"Ignoring invalid color value: {value!r} (want #rgb/#rrggbb)")
        else:
            fmt[key] = parsed
    elif key == "outline":
        parsed = _parse_outline(value)
        if parsed is None:
            logger.warning("Ignoring invalid outline value: "
                           f"{value!r} (want #rgb/#rrggbb, Npx #rgb/#rrggbb "
                           "or none)")
        else:
            fmt[key] = parsed
    elif key == "shadow":
        parsed = _parse_shadow(value)
        if parsed is None:
            logger.warning("Ignoring invalid shadow value: "
                           f"{value!r} (want Npx [P% [Dpx [A]]] "
                           "#rgb/#rrggbb, or none)")
        else:
            fmt[key] = parsed
    elif key == "case":
        v = value.strip().lower()
        if v not in _CASE_SET:
            logger.warning(f"Ignoring invalid case value: {value!r} (want upper/lower/origin)")
        else:
            fmt[key] = v
    elif key == "align":
        v = value.strip().lower()
        if v not in _ALIGN_SET:
            logger.warning(f"Ignoring invalid align value: {value!r} (want left/center/right/justify)")
        else:
            fmt[key] = v
    elif key == "dir":
        v = value.strip().lower()
        if v not in _DIR_SET:
            logger.warning(f"Ignoring invalid dir value: {value!r} (want rtl/ltr)")
        else:
            fmt[key] = v
    elif key == "spacing":
        try:
            num = float(value.strip())
        except ValueError:
            num = None
        if num is None or not 0.5 <= num <= 3.0:
            logger.warning(f"Ignoring invalid spacing value: {value!r} (want 0.5–3.0)")
        else:
            fmt[key] = num
    elif key == "font":
        name = value.strip().strip("\"'").strip()
        # Keep the txt shape safe: no structural characters inside a font name.
        name = re.sub(r"[;()\[\]]", "", name).strip()
        if not name or len(name) > 60:
            logger.warning(f"Ignoring invalid font value: {value!r}")
        else:
            fmt[key] = name


def parse_format_segments(segments: list[str], inline: bool) -> dict | None:
    """Parse ['k=v', ...] into a sparse format dict, or None if nothing valid."""
    fmt = blank_deck_format()
    found = False
    for seg in segments:
        seg = seg.strip()
        if not seg or "=" not in seg:
            continue
        key, _, value = seg.partition("=")
        before = dict(fmt)
        _apply_format_pair(fmt, key, value, inline)
        if fmt != before:
            found = True
    return fmt if found else None


def parse_format_line(line: str) -> dict | None:
    """Parse a top-level 'k=v; k=v' line → format dict, or None if not shaped so.

    Shape = every ';'-separated segment is k=v with a known key. Values are
    validated leniently (bad ones warn + skip); a shaped line with zero valid
    values still counts as a format line (all-None) so it never leaks on
    screen as a lyric.
    """
    segments = [s for s in line.split(";")]
    if not segments:
        return None
    pairs = []
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if "=" not in seg:
            return None
        key, _, _ = seg.partition("=")
        if key.strip().lower() not in _FORMAT_KEYS:
            return None
        pairs.append(seg)
    if not pairs:
        return None
    return parse_format_segments(pairs, inline=False) or blank_deck_format()


def parse_deck_format(raw: str) -> dict:
    """Scan only the header zone (leading lines before title/section/content).

    Cheap enough to call per deck row; the full parse reuses it.
    """
    fmt = blank_deck_format()
    for line in (raw or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if stripped == "":
            continue
        if _TITLE_RE.match(line) or _SECTION_RE.match(line) or stripped == "*":
            break
        parsed = parse_format_line(line)
        if parsed is None:
            break  # first content line ends the header zone
        for key, value in parsed.items():
            if value is not None:
                fmt[key] = value
    return fmt


def _iter_inline_parts(text: str):
    """Yield (display_text, params|None) for plain text and formatted runs.

    A bracket matches as a run when its final (...) group parses to ≥1 valid
    k=v pair; legacy [text: (#hex)] falls back to color-only; a bracket
    holding only a \\n marker (with or without params) is a paragraph gap;
    anything else stays literal (brackets preserved). A bare \\n outside
    brackets passes through as display text for the renderers to convert.
    """
    pos = 0
    for m in _INLINE_RUN_RE.finditer(text or ""):
        start, end = m.span()
        if start > pos:
            yield (text[pos:start], None)
        raw_text, raw_params = m.group(1), m.group(2)
        if raw_params is None:
            if raw_text.strip() == "\\n":
                yield ("", blank_deck_format())  # bare [\n] gap, inherited size
            else:
                yield (m.group(0), None)  # literal — keep brackets as typed
            pos = end
            continue
        params = parse_format_segments(raw_params.split(";"), inline=True)
        if params is None:
            text_part = _LEGACY_TEXT_RE.match(raw_text)
            hex_part = _LEGACY_HEX_RE.match(raw_params.strip())
            if text_part and hex_part:
                legacy = blank_deck_format()
                legacy["color"] = _parse_hex_color(raw_params)
                yield (text_part.group(1), legacy)
            else:
                yield (m.group(0), None)  # literal — keep brackets as typed
        else:
            yield (raw_text.strip(), params)
        pos = end
    if pos < len(text or ""):
        yield (text[pos:], None)


def _span_style(params: dict, allow: frozenset | None = None) -> str:
    """CSS for one inline run (shared contract with display renderers).

    allow restricts which params render — navigation surfaces pass only
    ("color", "italics"): display-only sizing/weight/case must never leak
    into strips. None renders everything (real displays).
    """
    styles = []
    if allow is None or "color" in allow:
        if params.get("color"):
            styles.append(f"color:{params['color']}")
    if allow is None or "size" in allow:
        if params.get("size_nominal") is not None:
            styles.append(f"font-size:{params['size_nominal']}px")
    if allow is None or "bold" in allow:
        if params.get("bold") is True:
            styles.append("font-weight:700")
        elif params.get("bold") is False:
            styles.append("font-weight:400")
    if allow is None or "italics" in allow:
        if params.get("italics") is True:
            styles.append("font-style:italic")
        elif params.get("italics") is False:
            styles.append("font-style:normal")
    if allow is None or "case" in allow:
        case = params.get("case")
        if case == "upper":
            styles.append("text-transform:uppercase")
        elif case == "lower":
            styles.append("text-transform:lowercase")
        elif case == "origin":
            styles.append("text-transform:none")
    if allow is None or "underline" in allow or "strike" in allow:
        deco = []
        if (allow is None or "underline" in allow) and params.get("underline") is True:
            deco.append("underline")
        if (allow is None or "strike" in allow) and params.get("strike") is True:
            deco.append("line-through")
        if deco:
            styles.append(f"text-decoration:{' '.join(deco)}")
        elif allow is None and (params.get("underline") is False
                                or params.get("strike") is False):
            styles.append("text-decoration:none")
    if allow is None or "align" in allow:
        if params.get("align"):
            # Inline runs are spans: full-width block span so alignment lands.
            styles.append(f"display:inline-block;width:100%;text-align:{params['align']}")
    if allow is None or "spacing" in allow:
        if params.get("spacing") is not None:
            styles.append(f"line-height:{params['spacing']}")
    if allow is None or "outline" in allow:
        outline = params.get("outline")
        if outline == OUTLINE_NONE:
            # Explicit off: kill the inherited outline/shadow for this run.
            styles.append("text-shadow:none")
        # A real outline is NOT a style: -webkit-text-stroke straddles the
        # glyph path and eats the letterform. It needs a duplicated stroke
        # layer behind the opaque fill, which the JS renderers emit (class
        # .rc-oc) and these non-display surfaces simply do without.
    if allow is None or "shadow" in allow:
        shadow = params.get("shadow")
        if shadow == OUTLINE_NONE:
            styles.append("text-shadow:none")
        elif shadow:
            shadow_css = _shadow_to_css(shadow)
            if shadow_css:
                styles.append(shadow_css)
    if allow is None or "dir" in allow:
        if params.get("dir"):
            styles.append(f"direction:{params['dir']};unicode-bidi:embed")
    if allow is None or "font" in allow:
        if params.get("font"):
            styles.append(f"font-family:'{params['font']}'")
    return ";".join(styles)


def _run_wrapper(params: dict) -> str | None:
    """Structural wrapper tag for a run: 'sup' / 'sub' / None.

    Vertical script has no CSS equivalent — renderers wrap the run text.
    """
    if params.get("super") is True:
        return "sup"
    if params.get("sub") is True:
        return "sub"
    return None


def is_hr_run(params: dict | None) -> bool:
    """An hr=true run renders as a horizontal rule, whatever its text."""
    return bool(params and params.get("hr") is True)


def hr_html() -> str:
    """Horizontal-rule markup shared by the Python renderers."""
    return '<div style="border-top:2px solid currentColor;margin:8px 0"></div>'


def _is_gap_text(part: str) -> bool:
    """Display text that renders as a paragraph gap, not words."""
    return part == "" or part == "\\n"


def strip_inline_markup(text: str) -> str:
    """Remove inline runs/legacy markup, keeping display text (for FTS indexing).

    Gap markers (bare \\n, [\\n], [\\n (size=N)]) become real newlines so
    surrounding words stay separated and searchable.
    """
    out = []
    for part, params in _iter_inline_parts(text):
        if params is not None and _is_gap_text(part):
            out.append("\n")
        elif params is None:
            out.append(part.replace("\\n", "\n"))
        else:
            out.append(part)
    return "".join(out)


def inline_markup_to_html(text: str, allow: frozenset | None = None) -> str:
    """Convert inline runs to HTML spans; everything else escaped.

    Single newlines become <br/> (a \\n is a line break within a slide).
    Paragraph gaps (bare \\n marker, [\\n], [\\n (size=N)]) become a sized
    <br/> — the gap height follows the given size, else the current size.
    allow restricts rendered params (strips pass color+italics only).
    """
    if not text:
        return ""
    out = []
    for part, params in _iter_inline_parts(text):
        if params is None:
            # Escape first (escape leaves backslashes alone), then convert
            # bare markers to real newlines for the <br/> pass below.
            out.append(html.escape(part).replace("\\n", "\n"))
        elif is_hr_run(params):
            out.append(hr_html())
        elif _is_gap_text(part):
            out.append(f'<span style="{_span_style(params, allow)}"><br/></span>')
        else:
            tag = _run_wrapper(params)
            inner = html.escape(part)
            if tag:
                inner = f"<{tag}>{inner}</{tag}>"
            out.append(f'<span style="{_span_style(params, allow)}">{inner}</span>')
    return "".join(out).replace("\r\n", "<br/>").replace("\n", "<br/>").replace("\r", "<br/>")


def has_inline_markup(text: str) -> bool:
    return any(params is not None for _, params in _iter_inline_parts(text or ""))


# ── Multi-song splitting ─────────────────────────────────────────────────────
# A run of 5+ consecutive \n characters followed (after optional spaces/tabs)
# by a title marker line (# or %) starts a NEW song within the same txt file.
_MULTISONG_SPLIT_RE = re.compile(r"\n{5,}[ \t]*(?=[#%])")


def slide_owns_marker(slides: list[dict], i: int) -> bool:
    """Does slide i start its own section (chip shows text)?

    Explicit "marker" flag wins; marker-less dicts (imports, old DB rows,
    hand-built data) fall back to the value-change rule, which groups them
    exactly as the pre-flag parser did. Rule of the UI: text in the chip =
    new section (even when identical to the section above); empty chip =
    member of the run above.
    """
    s = slides[i]
    if s.get("marker") is not None:
        return bool(s["marker"])
    if i == 0:
        return (s.get("section") or None) is not None
    return (s.get("section") or None) != (slides[i - 1].get("section") or None)


def format_to_line(fmt: dict | None) -> str | None:
    """Serialize a deck-format dict to a top-level format line (or None if empty).

    Stable key order (size, bold, color, italics, case, underline, strike,
    align, spacing, dir, outline, font). Size emits the longest valid prefix
    (nominal[, min[, max]]) — the only shapes the parser produces. super/sub
    are run-only concepts but round-trip harmlessly if present.
    """
    if not fmt:
        return None
    parts = []
    sizes = [fmt.get("size_nominal"), fmt.get("size_min"), fmt.get("size_max")]
    while sizes and sizes[-1] is None:
        sizes.pop()
    if sizes and all(isinstance(n, int) for n in sizes):
        parts.append("size=" + ", ".join(str(n) for n in sizes))
    if fmt.get("bold") is not None:
        parts.append(f"bold={'true' if fmt['bold'] else 'false'}")
    if fmt.get("color"):
        parts.append(f"color={fmt['color']}")
    if fmt.get("italics") is not None:
        parts.append(f"italics={'true' if fmt['italics'] else 'false'}")
    if fmt.get("case"):
        parts.append(f"case={fmt['case']}")
    if fmt.get("underline") is not None:
        parts.append(f"underline={'true' if fmt['underline'] else 'false'}")
    if fmt.get("strike") is not None:
        parts.append(f"strike={'true' if fmt['strike'] else 'false'}")
    if fmt.get("align"):
        parts.append(f"align={fmt['align']}")
    if fmt.get("spacing") is not None:
        parts.append(f"spacing={fmt['spacing']}")
    if fmt.get("dir"):
        parts.append(f"dir={fmt['dir']}")
    if fmt.get("outline"):
        parts.append(f"outline={fmt['outline']}")
    if fmt.get("font"):
        parts.append(f"font={fmt['font']}")
    return "; ".join(parts) or None


def _slide_block(slides: list[dict], idx: int) -> str:
    """Raw txt block for one slide: optional `*section` line + text lines.

    Marker lines follow ownership, not value changes: a slide that owns
    its section always emits, so same-name splits persist as repeated
    `*Name` lines (read back losslessly by the parser — section syntax
    is never merged). Section-less slides after a valued one keep the
    bare `*` clear so re-parse does not inherit.
    """
    slide = slides[idx]
    lines: list[str] = []
    section = (slide.get("section") or "").strip() or None
    prev = ((slides[idx - 1].get("section") or "").strip() or None
            if idx > 0 else None)
    if section is None and idx > 0 and prev is not None:
        # Preserve section-lessness: without the bare `*` this slide
        # would inherit the value above on re-parse.
        lines.append("*")
    elif slide_owns_marker(slides, idx) and section:
        lines.append(f"*{section}")
    text = slide.get("text", "") or ""
    lines.append(text.strip())
    return "\n".join(lines)


def slides_body_to_txt(slides: list[dict]) -> str:
    """Serialize slide blocks only — no title, no format line.

    Used for tier-scoped copy (a section run, a single slide block): the
    subset carries its own `*` markers via ownership flags, so it
    re-parses with identical section structure.
    """
    return "\n\n\n".join(
        _slide_block(slides, i) for i in range(len(slides or [])))


def deck_to_txt(title: str, slides: list[dict], format: dict | None = None) -> str:
    """Serialize a deck back to raw txt format (round-trips parse_slide_txt).

    Emits an optional format line, then `# title`, then per slide an optional
    `*section` marker plus text lines with real line breaks. Slide blocks are
    joined by TWO blank lines — the parser ignores a single blank, so one
    blank would merge everything back into a single slide. Two blanks stay
    well clear of the multi-song split (5+ blanks + title).
    """
    blocks = []
    header = format_to_line(format)
    if header:
        blocks.append(header)
    blocks.append(f"# {(title or '').strip() or '(untitled)'}")
    for idx in range(len(slides or [])):
        blocks.append(_slide_block(slides, idx))
    return "\n\n\n".join(blocks) + "\n"


def split_multisong(raw: str) -> list[str]:
    """Split a txt file containing several songs into per-song chunks.

    Boundary: \\n × 5 or more immediately followed by a title line (#/%).
    Gaps without a following title marker do NOT split. A file with no
    boundaries returns [raw] (single chunk).
    """
    if not raw:
        return []
    normalized = raw.replace("\r\n", "\n").replace("\r", "\n")
    chunks = _MULTISONG_SPLIT_RE.split(normalized)
    return [c for c in chunks if c.strip() != ""] or []


def parse_slide_txt(raw: str) -> dict:
    """
    Parse raw txt content into title + slides + deck format overrides.

    Rules:
    - Deck format: leading 'k=v; k=v' line(s) before the title (size, bold,
      color, italics, case) → format dict; later lines win per key.
    - Title: first line matching ^[#%]\\s*(.+?)\\s*$ → title. Subsequent #/% lines ignored.
    - Section: line matching ^\\*\\s*(.+?)\\s*$ → sets current_section for following slides.
      A bare `*` clears the section.
    - Slide: one or more non-empty, non-marker lines grouped until double blank line or EOF.
      Single newline = line break within same slide ("Line A\\nLine B").
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

    fmt = parse_deck_format(raw)

    title: str | None = None
    current_section: str | None = None

    # We'll collect blocks: split by blank lines (one or more empty lines)
    # But we need to handle section markers and title markers which are not content.
    # Approach: iterate lines, building current slide buffer.

    slides: list[dict] = []
    # Buffer for lines in current slide
    current_lines: list[str] = []
    # A `*` marker (or bare `*` clear) since the last flush means the next
    # emitted slide owns its section; otherwise it inherits (sticky).
    marker_pending = False

    def flush_slide():
        nonlocal current_lines, marker_pending
        if not current_lines:
            return
        # Join with newline to preserve intra-slide line breaks, then strip
        text = "\n".join(current_lines).strip()
        # Collapse trailing/leading blank artifacts but keep internal single newlines
        # Also collapse multiple internal blank artefacts that slipped through (shouldn't)
        if text:
            slides.append({"section": current_section, "text": text,
                           "marker": marker_pending})
            marker_pending = False
        current_lines = []

    lines = raw.split("\n")

    consecutive_blank = 0
    in_header = True  # format lines only count before title/section/content

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

        # Deck format line — only in the header zone; elsewhere it's a lyric
        if in_header and parse_format_line(line) is not None:
            continue

        # Title marker — only first occurrence wins
        if _TITLE_RE.match(line):
            in_header = False
            if title is None:
                m = _TITLE_RE.match(line)
                title = m.group(1).strip() if m else ""
                # Don't treat as content
                continue
            else:
                # Subsequent title-like lines are ignored per spec (not displayed)
                continue

        # Section marker — `*name` sets it, a bare `*` clears it
        if stripped == "*":
            in_header = False
            flush_slide()
            current_section = None
            marker_pending = True
            continue

        if _SECTION_RE.match(line):
            in_header = False
            # Flush any pending slide before switching section
            flush_slide()
            m = _SECTION_RE.match(line)
            current_section = m.group(1).strip() if m else None
            marker_pending = True
            continue

        # Plain content line — part of current slide
        in_header = False
        # Preserve as-is trimmed? Keep original leading/trailing stripped but internal intact
        # Use stripped version for display (user typed content, trim edges)
        current_lines.append(stripped)

    # Flush trailing slide
    flush_slide()

    if title is None:
        title = ""

    return {"title": title, "slides": slides, "format": fmt}


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
