"""
core/theme_schema.py

Theme schema v2: validation, defaults, sanitisation, animation registry and
the safe fallback theme.

This module is the single authoritative gate for theme data that reaches the
display renderer. It never writes to disk and never mutates its input.

Public API:
    SCHEMA_VERSION
    ThemeReport
    SAFE_THEME
    BUILTIN_ANIMATIONS
    normalize_theme(raw, kind=None, name=None) -> (resolved, report)

The resolved dict is complete: every documented default is filled, shared
references are expanded, v1 themes are migrated, and every value is safe to
hand to CSS. Unknown keys are dropped with a warning; the raw theme keeps
them for the designer round trip.
"""

from __future__ import annotations

import copy
import logging
import math
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

KINDS = ("scripture", "freeform")
SCRIPTURE = "scripture"
FREEFORM = "freeform"

ANCHORS = (
    "top_left", "top_right", "bottom_left", "bottom_right",
    "center", "left", "right", "top", "bottom", "fill",
)
CORNER_KEYS = ("top_left", "top_right", "bottom_left", "bottom_right")
BORDER_STYLES = (
    "none", "solid", "dashed", "dotted", "double",
    "groove", "ridge", "inset", "outset",
)
EASINGS = ("ease-out", "ease-in", "ease-in-out", "linear", "spring", "smooth")
ORIGINS = (
    "center", "top", "bottom", "left", "right",
    "top left", "top right", "bottom left", "bottom right",
)
FILTER_FUNCS = {
    "blur": (0, 60), "brightness": (0, 4), "contrast": (0, 4),
    "saturate": (0, 8), "grayscale": (0, 1), "sepia": (0, 1),
    "hue-rotate": (-1080, 1080), "opacity": (0, 1),
}
ANIMATION_TYPES = (
    "fade_in", "fade_out", "fade_up", "fade_down",
    "scale_up", "scale_down", "slide_up", "slide_down",
    "typewriter", "custom",
)
PRESET_TYPES = tuple(t for t in ANIMATION_TYPES if t not in ("typewriter", "custom"))

BLOCK_IDS = {
    SCRIPTURE: ("body", "text", "reference", "translation", "verse_num"),
    FREEFORM: ("body", "title", "text", "translation", "verse_num"),
}
# `reference` is accepted as an alias for `title` in freeform themes.
BLOCK_ALIASES = {FREEFORM: {"reference": "title"}}

INHERITABLE_TRANSLATION_FIELDS = (
    "font_family", "size", "weight", "line_height", "letter_spacing",
    "text_transform", "font_style",
)

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$")
_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")
_ANIM_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{0,63}$")
_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)px$", re.I)
_PCT_RE = re.compile(r"^(-?\d+(?:\.\d+)?)%$")
_EM_RE = re.compile(r"^(-?\d+(?:\.\d+)?)em$", re.I)
_CUBIC_RE = re.compile(
    r"^cubic-bezier\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,"
    r"\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)$")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FUNC_COLOR_RE = re.compile(
    r"^(rgba?|hsla?)\(\s*[0-9.%\s,/+-]+\)$", re.I)
_GRADIENT_RE = re.compile(r"^(linear|radial)-gradient\((.+)\)$", re.I)
_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'\"._\-]+$")
_BAD_CSS = ("url(", "expression", "javascript:", "@import", "var(", ";", "{", "}",
            "</", "<!--", "\\")

NAMED_COLORS = {
    "transparent", "currentcolor", "inherit", "initial", "unset",
    "black", "white", "red", "green", "blue", "yellow", "orange", "purple",
    "pink", "gray", "grey", "silver", "gold", "lime", "navy", "teal",
    "aqua", "cyan", "magenta", "fuchsia", "maroon", "olive", "brown",
}


@dataclass
class ThemeReport:
    """Warnings, errors, and notes produced while normalising one theme."""

    theme: str = ""
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def warn(self, path: str, message: str, value: Any = None,
             fallback: Any = None) -> None:
        entry = f"theme={self.theme or '?'} path={path} {message}"
        if value is not None:
            entry += f" value={value!r}"
        if fallback is not None:
            entry += f" fallback={fallback!r}"
        self.warnings.append(entry)
        logger.warning(entry)

    def error(self, path: str, message: str, value: Any = None) -> None:
        entry = f"theme={self.theme or '?'} path={path} {message}"
        if value is not None:
            entry += f" value={value!r}"
        self.errors.append(entry)
        logger.error(entry)

    def note(self, path: str, message: str, value: Any = None) -> None:
        """Report an expected, harmless repair (unknown key) at DEBUG.

        Spec §6.2: unknown keys are ignored and reported once per path at
        DEBUG, because hand-written themes routinely carry designer-only or
        future fields and must not spam the log.
        """
        entry = f"theme={self.theme or '?'} path={path} {message}"
        if value is not None:
            entry += f" value={value!r}"
        self.notes.append(entry)
        logger.debug(entry)

    @property
    def ok(self) -> bool:
        return not self.errors


# ─── Primitive coercers ──────────────────────────────────────────────────────


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def parse_number(value: Any) -> Optional[float]:
    """JSON number or numeric string ("42", "42px"). No percentages."""
    if _is_number(value):
        return float(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text.endswith("px"):
            text = text[:-2].strip()
        if _NUM_RE.match(text):
            try:
                return float(text)
            except ValueError:
                return None
    return None


def _fmt_number(value: float) -> Any:
    return int(value) if float(value).is_integer() else value


def coerce_number(value: Any, default: float, lo: float, hi: float, *,
                  path: str, report: ThemeReport, integer: bool = False,
                  label: str = "") -> Any:
    number = parse_number(value)
    if number is None:
        report.warn(path, f"{label or 'value'} is not numeric", value, default)
        return default
    clamped = min(hi, max(lo, number))
    if clamped != number:
        report.warn(path, f"{label or 'value'} out of range {lo}..{hi}",
                    value, _fmt_number(clamped))
    if integer:
        return int(round(clamped))
    return _fmt_number(clamped)


def parse_length(value: Any, *, percent: bool = False, em: bool = False,
                 auto: bool = False, inherit: bool = False) -> Optional[Any]:
    """Length -> number (px), "N%" / "Nem" string, or "auto"/"inherit"."""
    if value is None:
        return None
    if _is_number(value):
        return _fmt_number(float(value))
    if not isinstance(value, str):
        return None
    text = value.strip()
    low = text.lower()
    if px := _PX_RE.match(text):
        return _fmt_number(float(px.group(1)))
    if _NUM_RE.match(text):
        return _fmt_number(float(text))
    if percent and (m := _PCT_RE.match(text)):
        return f"{_fmt_number(float(m.group(1)))}%"
    if em and (m := _EM_RE.match(text)):
        return f"{_fmt_number(float(m.group(1)))}em"
    if auto and low == "auto":
        return "auto"
    if inherit and low == "inherit":
        return "inherit"
    return None


def coerce_length(value: Any, default: Any, *, path: str, report: ThemeReport,
                  minimum: float = -400, maximum: float = 4000,
                  percent: bool = False, em: bool = False,
                  auto: bool = False, inherit: bool = False,
                  integer: bool = False, label: str = "") -> Any:
    parsed = parse_length(value, percent=percent, em=em, auto=auto,
                          inherit=inherit)
    if parsed is None:
        report.warn(path, f"{label or 'length'} is invalid", value, default)
        return default
    if isinstance(parsed, str):
        return parsed
    clamped = min(maximum, max(minimum, float(parsed)))
    if clamped != float(parsed):
        report.warn(path, f"{label or 'length'} out of range",
                    value, _fmt_number(clamped))
    return int(round(clamped)) if integer else _fmt_number(clamped)


def coerce_bool(value: Any, default: bool, *, path: str,
                report: ThemeReport) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().lower() in ("true", "false"):
        report.warn(path, "boolean written as a string", value, default)
        return value.strip().lower() == "true"
    report.warn(path, "not a boolean", value, default)
    return default


def coerce_enum(value: Any, allowed: tuple, default: str, *, path: str,
                report: ThemeReport) -> str:
    # Absent (or explicit null) means "take the documented default"; only a
    # present-but-invalid value is worth a warning.
    if value is None:
        return default
    if isinstance(value, str) and value in allowed:
        return value
    report.warn(path, "invalid enum value", value, default)
    return default


def clean_text(value: Any, limit: int, *, path: str, report: ThemeReport,
               default: str = "") -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        report.warn(path, "not a string", value, default)
        return default
    kept: list[str] = []
    for char in value:
        category = unicodedata.category(char)
        if category in ("Cf", "Cs", "Co", "Cn"):
            continue                    # bidi/format, surrogates, private use
        if category == "Cc" and char not in "\t\n":
            continue                    # NUL, ESC, DEL, ...
        kept.append(char)
    text = "".join(kept).strip()
    if len(text) > limit:
        report.warn(path, f"string longer than {limit}", len(text), limit)
        text = text[:limit]
    return text


def _has_bad_css(text: str) -> bool:
    low = text.lower()
    return any(token in low for token in _BAD_CSS)


def sanitize_color(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    low = text.lower()
    if low in NAMED_COLORS:
        return low if low in ("transparent", "currentcolor", "inherit") else text
    if _HEX_RE.match(text):
        return text
    if _FUNC_COLOR_RE.match(text) and not _has_bad_css(text):
        return text
    return None


def sanitize_font_family(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or _has_bad_css(text) or not _FAMILY_RE.match(text):
        return None
    return text


def sanitize_outline(value: Any) -> Optional[Any]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in ("none", "off"):
        return "none"
    m = re.match(r"^(\d+(?:\.\d+)?)(px|em)\s+(.+)$", text, re.I)
    if not m:
        return None
    color = sanitize_color(m.group(3).strip())
    if not color:
        return None
    return f"{_fmt_number(float(m.group(1)))}{m.group(2).lower()} {color}"


def _split_css_tokens(text: str) -> list[str]:
    """Split on whitespace that is outside parentheses.

    `rgba(0, 0, 0, 0.6)` is one token; naive `str.split()` would shred it.
    """
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def sanitize_shadow(value: Any) -> Optional[str]:
    """Validate a CSS box/text shadow (1-12 comma-separated shadows).

    Each shadow is 2-4 lengths (x, y, optional blur/spread), at most one
    `inset`, and one color. Rejecting a color-only or length-less part keeps
    values that browsers silently ignore out of the resolved theme. The upper
    bound is 12 because a v1 hard ring is eight offset copies plus the soft
    drop shadow it shipped with; such a mixed value must survive verbatim.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in ("none", "off"):
        return "none"
    if _has_bad_css(text):
        return None
    parts = [p.strip() for p in re.split(r",(?![^()]*\))", text) if p.strip()]
    if not 1 <= len(parts) <= 12:
        return None
    length_re = re.compile(r"^-?\d+(?:\.\d+)?(?:px)?$", re.I)
    for part in parts:
        tokens = _split_css_tokens(part)
        if not 2 <= len(tokens) <= 6:
            return None
        lengths = insets = colors = 0
        for token in tokens:
            if token.lower() == "inset":
                insets += 1
            elif length_re.match(token):
                lengths += 1
            elif sanitize_color(token) is not None:
                colors += 1
            else:
                return None
        if not 2 <= lengths <= 4 or insets > 1 or colors != 1:
            return None
    return text


def sanitize_backdrop_filter(value: Any) -> Optional[str]:
    """Validate a `backdrop-filter` list: allowlisted functions only.

    `%` is normalized for the multiplier functions (`brightness`, `contrast`,
    `saturate`, `grayscale`, `sepia`, `opacity`), where `100%` == `1`, so both
    `saturate(1.15)` and `saturate(115%)` are accepted and range-checked the
    same way. `blur` takes px, `hue-rotate` takes deg.
    """
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in ("none", "off"):
        return "none"
    if _has_bad_css(text):
        return None
    if not re.fullmatch(r"(?:\s*[a-z-]+\([^()]*\))+\s*", text, re.I):
        return None
    for match in re.finditer(r"([a-z-]+)\(([^)]*)\)", text, re.I):
        fn = match.group(1).lower()
        if fn not in FILTER_FUNCS:
            return None
        args = match.group(2).strip()
        number = args
        unit = ""
        for suffix in ("deg", "px", "%"):
            if number.lower().endswith(suffix):
                number, unit = number[:-len(suffix)].strip(), suffix
                break
        if not _NUM_RE.match(number):
            return None
        allowed_units = {
            "blur": ("", "px"),
            "hue-rotate": ("", "deg"),
        }.get(fn, ("", "%"))
        if unit.lower() not in allowed_units:
            return None
        # A unitless multiplier is already a factor; a percentage is /100.
        numeric = float(number) / (100.0 if unit == "%" else 1.0)
        lo, hi = FILTER_FUNCS[fn]
        if not lo <= numeric <= hi:
            return None
    return text


def sanitize_border_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if text.lower() in ("none", "off"):
        return "none"
    if _has_bad_css(text):
        return None
    # width style color, any order; color optional
    tokens = _split_css_tokens(text)
    if not 2 <= len(tokens) <= 4:
        return None
    width = None
    style = None
    color = None
    for token in tokens:
        low = token.lower()
        if low in BORDER_STYLES:
            style = low
        elif width is None and re.match(r"^\d+(?:\.\d+)?(px)?$", low):
            width = low
        else:
            parsed = sanitize_color(token)
            if parsed is None:
                return None
            color = parsed
    if width is None or style is None:
        return None
    return text


def sanitize_gradient(value: str) -> Optional[str]:
    match = _GRADIENT_RE.match(value.strip())
    if not match:
        return None
    body = match.group(2)
    if _has_bad_css(body):
        return None
    if not re.fullmatch(r"[\sa-z0-9().,#%+-]+", body, re.I):
        return None
    return value.strip()


def _coerce_color(value: Any, default: Any, *, path: str,
                  report: ThemeReport) -> Any:
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() == "inherit":
        return "inherit"
    color = sanitize_color(value)
    if color is None:
        report.warn(path, "invalid color", value, default)
        return default
    return color


def _coerce_paint(value: Any, default: Any, *, path: str,
                  report: ThemeReport) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        low = text.lower()
        if low in ("transparent", "none"):
            return low
        color = sanitize_color(text)
        if color:
            return color
        gradient = sanitize_gradient(text)
        if gradient:
            return gradient
    report.warn(path, "invalid paint", value, default)
    return default


def _coerce_family(value: Any, default: Any, *, path: str,
                   report: ThemeReport) -> Any:
    if value is None:
        return default
    if isinstance(value, str) and value.strip().lower() == "inherit":
        return "inherit"
    family = sanitize_font_family(value)
    if family is None:
        report.warn(path, "invalid font family", value, default)
        return default
    return family


def _coerce_shared_ref(value: Any, default: Any, *, path: str,
                       report: ThemeReport) -> Any:
    """Return a validated `{"shared": name}` reference or `default`.

    Anything that is not a shared reference returns `default`, so the caller
    falls through to its own string/dict handling. Returning the value
    unchanged here would let a plain CSS string skip validation entirely.
    """
    if isinstance(value, dict) and set(value) == {"shared"}:
        name = value.get("shared")
        if isinstance(name, str) and _ANIM_NAME_RE.match(name):
            return {"shared": name}
        report.warn(path, "invalid shared reference", name, default)
        return default
    return default


def _coerce_border(value: Any, default: Any, *, path: str,
                   report: ThemeReport) -> Any:
    ref = _coerce_shared_ref(value, None, path=path, report=report)
    if ref is not None:
        return ref
    if isinstance(value, str):
        parsed = sanitize_border_string(value)
        if parsed is not None:
            return parsed
        report.warn(path, "invalid border", value, default)
        return default
    if isinstance(value, dict):
        out: dict = {}
        if "width" in value:
            out["width"] = coerce_number(value["width"], 0, 0, 40, path=f"{path}.width",
                                         report=report, label="width")
        out["style"] = coerce_enum(value.get("style", "solid"), BORDER_STYLES,
                                   "solid", path=f"{path}.style", report=report)
        if "color" in value:
            out["color"] = _coerce_color(value["color"], "currentColor",
                                         path=f"{path}.color", report=report)
        if "radius" in value:
            out["radius"] = coerce_length(value["radius"], 0, path=f"{path}.radius",
                                          report=report, minimum=0, maximum=400)
        sides = value.get("sides")
        if isinstance(sides, dict):
            clean_sides = {}
            for side in ("top", "right", "bottom", "left"):
                raw_side = sides.get(side)
                if not isinstance(raw_side, dict):
                    continue
                side_out = {}
                if "width" in raw_side:
                    side_out["width"] = coerce_number(
                        raw_side["width"], 0, 0, 40, path=f"{path}.sides.{side}.width",
                        report=report, label="width")
                if "style" in raw_side:
                    side_out["style"] = coerce_enum(
                        raw_side["style"], BORDER_STYLES, "solid",
                        path=f"{path}.sides.{side}.style", report=report)
                if "color" in raw_side:
                    side_out["color"] = _coerce_color(
                        raw_side["color"], "currentColor",
                        path=f"{path}.sides.{side}.color", report=report)
                if "radius" in raw_side:
                    side_out["radius"] = coerce_length(
                        raw_side["radius"], 0, path=f"{path}.sides.{side}.radius",
                        report=report, minimum=0, maximum=400)
                clean_sides[side] = side_out
            if clean_sides:
                out["sides"] = clean_sides
        return out
    report.warn(path, "invalid border", value, default)
    return default


def _coerce_shadow(value: Any, default: Any, *, path: str,
                   report: ThemeReport) -> Any:
    ref = _coerce_shared_ref(value, None, path=path, report=report)
    if ref is not None:
        return ref
    if isinstance(value, str):
        parsed = sanitize_shadow(value)
        if parsed is not None:
            return parsed
        report.warn(path, "invalid shadow", value, default)
        return default
    if isinstance(value, dict):
        out = {
            "x": coerce_number(value.get("x", 0), 0, -500, 500,
                               path=f"{path}.x", report=report),
            "y": coerce_number(value.get("y", 0), 0, -500, 500,
                               path=f"{path}.y", report=report),
            "blur": coerce_number(value.get("blur", 0), 0, 0, 500,
                                  path=f"{path}.blur", report=report),
            "spread": coerce_number(value.get("spread", 0), 0, -500, 500,
                                    path=f"{path}.spread", report=report),
            "color": _coerce_color(value.get("color", "rgba(0,0,0,0.5)"),
                                   "rgba(0,0,0,0.5)", path=f"{path}.color",
                                   report=report),
            "inset": coerce_bool(value.get("inset", False), False,
                                 path=f"{path}.inset", report=report),
        }
        return out
    report.warn(path, "invalid shadow", value, default)
    return default


def _coerce_filter(value: Any, default: Any, *, path: str,
                   report: ThemeReport) -> Any:
    if value is None:
        return default
    parsed = sanitize_backdrop_filter(value)
    if parsed is None:
        report.warn(path, "invalid filter", value, default)
        return default
    return parsed


# ─── Block defaults ──────────────────────────────────────────────────────────


def _shared_block_defaults() -> dict:
    return {
        "visible": True,
        "color": "#f8fafc",
        "font_family": "'Nunito', sans-serif",
        "size": 40,
        "min_size": 4,
        "max_size": 300,
        "weight": 700,
        "line_height": 1.2,
        "letter_spacing": "-0.01em",
        "word_spacing": 0,
        "text_shadow": "none",
        "text_outline": "none",
        "text_transform": "none",
        "text_align": "center",
        "font_style": "normal",
        "text_decoration": "none",
        "opacity": 1.0,
        "max_lines": None,
        "direction": "ltr",
        "margin_top": 0,
        "margin_right": 0,
        "margin_bottom": 0,
        "margin_left": 0,
        "padding": 0,
        "padding_top": 0,
        "padding_right": 0,
        "padding_bottom": 0,
        "padding_left": 0,
    }


def _text_defaults() -> dict:
    out = _shared_block_defaults()
    out.update({
        "size": 40,
        "letter_spacing": "-0.01em",
        "margin_bottom": 24,
        "text_shadow": "0 4px 12px rgba(0,0,0,0.4)",
        "autosize": True,
    })
    return out


def _reference_defaults() -> dict:
    out = _shared_block_defaults()
    out.update({
        "position": "below_verse",
        "color": "#94a3b8",
        "font_family": "'DM Sans', sans-serif",
        "size": 24,
        "weight": 500,
        "letter_spacing": "0.1em",
        "text_transform": "uppercase",
    })
    return out


def _translation_defaults() -> dict:
    out = _shared_block_defaults()
    out.update({
        "position": "right_of_reference",
        "color": "#64748b",
        "margin_left": 8,
    })
    return out


def _verse_num_defaults() -> dict:
    out = _shared_block_defaults()
    out.update({
        "mode": "inline",
        "position": "above_verse",
        "vertical_align": "top",
        "margin_right": "0.15em",
        "size": "0.6em",
        "weight": 700,
        "opacity": 0.7,
        "line_height": 1,
        "color": "inherit",
        "font_family": "inherit",
    })
    return out


def _body_defaults() -> dict:
    return {
        "visible": True,
        "valign": "center",
        "gap": 0,
        "padding": 0,
        "padding_top": 0,
        "padding_right": 0,
        "padding_bottom": 0,
        "padding_left": 0,
    }


def block_defaults(block_id: str) -> dict:
    if block_id == "text":
        return _text_defaults()
    if block_id in ("reference", "title"):
        return _reference_defaults()
    if block_id == "translation":
        return _translation_defaults()
    if block_id == "verse_num":
        return _verse_num_defaults()
    return _body_defaults()


# ─── Animations ──────────────────────────────────────────────────────────────


def _preset_keyframes(typ: str) -> list:
    if typ == "fade_in":
        return [{"at": 0, "opacity": 0}, {"at": 100, "opacity": "base"}]
    if typ == "fade_out":
        return [{"at": 0, "opacity": "base"}, {"at": 100, "opacity": 0}]
    if typ == "fade_up":
        return [{"at": 0, "opacity": 0, "translate_y": 20},
                {"at": 100, "opacity": "base", "translate_y": 0}]
    if typ == "fade_down":
        return [{"at": 0, "opacity": "base", "translate_y": 0},
                {"at": 100, "opacity": 0, "translate_y": 20}]
    if typ == "scale_up":
        return [{"at": 0, "opacity": 0, "scale": 0.85},
                {"at": 100, "opacity": "base", "scale": 1}]
    if typ == "scale_down":
        return [{"at": 0, "opacity": "base", "scale": 1},
                {"at": 100, "opacity": 0, "scale": 0.85}]
    if typ == "slide_up":
        return [{"at": 0, "translate_y": "100%"}, {"at": 100, "translate_y": 0}]
    if typ == "slide_down":
        return [{"at": 0, "translate_y": 0}, {"at": 100, "translate_y": "100%"}]
    return []


def _builtin_definitions() -> dict:
    out = {}
    for typ in PRESET_TYPES:
        out[typ] = {
            "type": typ,
            "label": typ.replace("_", " ").title(),
            "duration_ms": 600,
            "delay_ms": 0,
            "easing": "ease-out",
            "origin": "center",
            "keyframes": _preset_keyframes(typ),
        }
    out["typewriter"] = {
        "type": "typewriter",
        "label": "Typewriter",
        "duration_ms": 900,
        "delay_ms": 0,
        "easing": "linear",
        "reveal": "char",
        "cursor": {
            "char": "\u258c",
            "color": "currentColor",
            "blink_ms": 500,
            "hide_after_ms": 600,
        },
    }
    return out


BUILTIN_ANIMATIONS = _builtin_definitions()


def _coerce_easing(value: Any, default: str, *, path: str,
                   report: ThemeReport) -> str:
    if isinstance(value, str):
        text = value.strip()
        if text in EASINGS:
            return text
        if _CUBIC_RE.match(text):
            return text
    report.warn(path, "invalid easing", value, default)
    return default


def _validate_keyframes(raw: Any, *, path: str,
                        report: ThemeReport) -> Optional[list]:
    if not isinstance(raw, list) or not 2 <= len(raw) <= 8:
        report.warn(path, "keyframes must be an array of 2-8 frames", type(raw).__name__)
        return None
    frames = []
    last_at = -1.0
    for index, frame in enumerate(raw):
        fpath = f"{path}[{index}]"
        if not isinstance(frame, dict):
            report.warn(fpath, "keyframe is not an object", type(frame).__name__)
            return None
        at = parse_number(frame.get("at"))
        if at is None or not 0 <= at <= 100 or at <= last_at:
            report.warn(fpath, "keyframe `at` must increase within 0..100",
                        frame.get("at"))
            return None
        last_at = at
        out: dict = {"at": _fmt_number(at)}
        if "opacity" in frame:
            if frame["opacity"] == "base":
                out["opacity"] = "base"
            else:
                out["opacity"] = coerce_number(frame["opacity"], 1.0, 0, 1,
                                               path=f"{fpath}.opacity",
                                               report=report, label="opacity")
        for key in ("translate_x", "translate_y"):
            if key in frame:
                parsed = parse_length(frame[key], percent=True)
                if parsed is None:
                    report.warn(f"{fpath}.{key}", "invalid translate", frame[key], 0)
                    parsed = 0
                if not isinstance(parsed, str):
                    parsed = min(2000, max(-2000, float(parsed)))
                    parsed = _fmt_number(parsed)
                out[key] = parsed
        if "scale" in frame:
            out["scale"] = coerce_number(frame["scale"], 1, 0.01, 4,
                                         path=f"{fpath}.scale", report=report,
                                         label="scale")
        if "rotate" in frame:
            out["rotate"] = coerce_number(frame["rotate"], 0, -1080, 1080,
                                          path=f"{fpath}.rotate", report=report,
                                          label="rotate")
        if "blur" in frame:
            if frame["blur"] == "base":
                out["blur"] = "base"
            else:
                out["blur"] = coerce_length(frame["blur"], 0, path=f"{fpath}.blur",
                                            report=report, minimum=0, maximum=60)
        frames.append(out)
    if frames[0]["at"] != 0 or frames[-1]["at"] != 100:
        report.warn(path, "keyframes must start at 0 and end at 100",
                    (frames[0]["at"], frames[-1]["at"]))
        return None
    return frames


def validate_animation_definition(raw: Any, name: str, *, path: str,
                                  report: ThemeReport) -> Optional[dict]:
    """Validate one animation definition; None if it must be dropped."""
    if not isinstance(raw, dict):
        report.warn(path, "animation definition is not an object",
                    type(raw).__name__)
        return None
    typ = raw.get("type")
    if typ not in ANIMATION_TYPES:
        report.warn(f"{path}.type", "unknown animation type", typ,
                    "fade_in")
        return None
    out: dict = {"type": typ}
    out["label"] = clean_text(raw.get("label"), 80, path=f"{path}.label",
                              report=report, default=name)
    duration = raw.get("duration_ms")
    if duration is None:
        report.warn(f"{path}.duration_ms", "duration is required", None, 600)
        out["duration_ms"] = 600
    else:
        out["duration_ms"] = coerce_number(duration, 600, 0, 5000,
                                           path=f"{path}.duration_ms",
                                           report=report, integer=True,
                                           label="duration_ms")
    out["delay_ms"] = coerce_number(raw.get("delay_ms", 0), 0, 0, 5000,
                                    path=f"{path}.delay_ms", report=report,
                                    integer=True, label="delay_ms")
    out["easing"] = _coerce_easing(raw.get("easing", "ease-out" if typ != "typewriter" else "linear"),
                                   "ease-out" if typ != "typewriter" else "linear",
                                   path=f"{path}.easing", report=report)

    if typ == "custom":
        frames = _validate_keyframes(raw.get("keyframes"), path=f"{path}.keyframes",
                                     report=report)
        if frames is None:
            return None
        out["keyframes"] = frames
        out["origin"] = coerce_enum(raw.get("origin", "center"), ORIGINS, "center",
                                    path=f"{path}.origin", report=report)
        return out

    if typ == "typewriter":
        if "keyframes" in raw:
            report.warn(f"{path}.keyframes", "typewriter takes no keyframes")
        out["reveal"] = coerce_enum(raw.get("reveal", "char"), ("char", "word"),
                                    "char", path=f"{path}.reveal", report=report)
        cursor = raw.get("cursor", "default")
        if cursor == "none":
            out["cursor"] = "none"
        elif cursor in ("default", None):
            out["cursor"] = {
                "char": "\u258c", "color": "currentColor",
                "blink_ms": 500, "hide_after_ms": 600,
            }
        elif isinstance(cursor, dict):
            char = clean_text(cursor.get("char"), 2, path=f"{path}.cursor.char",
                              report=report, default="\u258c")
            if not char:
                char = "\u258c"
            color_raw = cursor.get("color", "currentColor")
            if color_raw == "currentColor":
                color = "currentColor"
            else:
                color = sanitize_color(color_raw)
                if color is None:
                    report.warn(f"{path}.cursor.color", "invalid color",
                                color_raw, "currentColor")
                    color = "currentColor"
            out["cursor"] = {
                "char": char,
                "color": color,
                "blink_ms": coerce_number(cursor.get("blink_ms", 500), 500, 0, 2000,
                                          path=f"{path}.cursor.blink_ms",
                                          report=report, integer=True,
                                          label="blink_ms"),
                "hide_after_ms": coerce_number(
                    cursor.get("hide_after_ms", 600), 600, 0, 5000,
                    path=f"{path}.cursor.hide_after_ms", report=report,
                    integer=True, label="hide_after_ms"),
            }
        else:
            report.warn(f"{path}.cursor", "invalid cursor", cursor, "default")
            out["cursor"] = {
                "char": "\u258c", "color": "currentColor",
                "blink_ms": 500, "hide_after_ms": 600,
            }
        return out

    # Preset
    if "keyframes" in raw:
        # §4.9.4: a preset is defined by its type; authoring keyframes on one
        # is a mistake, not an override. Drop so the slot falls back per phase.
        report.warn(f"{path}.keyframes",
                    "only type=custom accepts keyframes", None,
                    "definition dropped")
        return None
    out["origin"] = coerce_enum(raw.get("origin", "center"), ORIGINS, "center",
                                path=f"{path}.origin", report=report)
    out["keyframes"] = copy.deepcopy(BUILTIN_ANIMATIONS[typ]["keyframes"])
    return out


def _validate_animation_library(raw: Any, *, path: str,
                                report: ThemeReport) -> dict:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        report.warn(path, "animations must be an object", type(raw).__name__)
        return {}
    out = {}
    for name, definition in raw.items():
        if not isinstance(name, str) or not _ANIM_NAME_RE.match(name):
            report.warn(f"{path}.{name}", "invalid animation name", name)
            continue
        validated = validate_animation_definition(
            definition, name, path=f"{path}.{name}", report=report)
        if validated is not None:
            out[name] = validated
    return out


def _normalize_slot(raw: Any, *, path: str, phase: str,
                    report: ThemeReport) -> Optional[dict]:
    """One phase value -> None, {"use": name, ...}, or an inline definition."""
    if raw is None or raw == "none":
        return None
    if isinstance(raw, str):
        if _ANIM_NAME_RE.match(raw):
            return {"use": raw}
        report.warn(path, "invalid animation name", raw, phase and "fade_in")
        return {"use": "fade_in" if phase != "out" else "fade_out"}
    if not isinstance(raw, dict):
        report.warn(path, "invalid animation slot", type(raw).__name__,
                    "fade_in" if phase != "out" else "fade_out")
        return {"use": "fade_in" if phase != "out" else "fade_out"}
    if "use" in raw:
        name = raw.get("use")
        if not isinstance(name, str) or not _ANIM_NAME_RE.match(name):
            report.warn(f"{path}.use", "invalid animation name", name,
                        "fade_in" if phase != "out" else "fade_out")
            return {"use": "fade_in" if phase != "out" else "fade_out"}
        out = {"use": name}
        if "duration_ms" in raw:
            out["duration_ms"] = coerce_number(
                raw["duration_ms"], 600, 0, 5000, path=f"{path}.duration_ms",
                report=report, integer=True, label="duration_ms")
        if "delay_ms" in raw:
            out["delay_ms"] = coerce_number(
                raw["delay_ms"], 0, 0, 5000, path=f"{path}.delay_ms",
                report=report, integer=True, label="delay_ms")
        if "easing" in raw:
            out["easing"] = _coerce_easing(raw["easing"], "ease-out",
                                           path=f"{path}.easing", report=report)
        extra = set(raw) - {"use", "duration_ms", "delay_ms", "easing"}
        if extra:
            report.note(path, "ignoring unknown slot keys", sorted(extra))
        return out
    # Inline definition
    inline = validate_animation_definition(raw, "inline", path=path,
                                           report=report)
    if inline is None:
        return {"use": "fade_in" if phase != "out" else "fade_out"}
    return inline


def normalize_animation_assignment(raw: Any, *, path: str,
                                   report: ThemeReport) -> dict:
    if raw is None:
        return {}
    if raw == "none":
        return {}
    if not isinstance(raw, dict):
        report.warn(path, "animation assignment must be an object",
                    type(raw).__name__)
        return {}
    out: dict = {}
    if "entry" in raw:
        slot = _normalize_slot(raw["entry"], path=f"{path}.entry", phase="entry",
                               report=report)
        if slot is not None:
            out["entry"] = slot
    if "out" in raw:
        slot = _normalize_slot(raw["out"], path=f"{path}.out", phase="out",
                               report=report)
        if slot is not None:
            out["out"] = slot
    if "transition" in raw:
        value = raw["transition"]
        if isinstance(value, dict) and ("out" in value or "in" in value):
            trans: dict = {}
            if "out" in value:
                slot = _normalize_slot(value["out"], path=f"{path}.transition.out",
                                       phase="out", report=report)
                if slot is not None:
                    trans["out"] = slot
            if "in" in value:
                slot = _normalize_slot(value["in"], path=f"{path}.transition.in",
                                       phase="in", report=report)
                if slot is not None:
                    trans["in"] = slot
            if trans:
                out["transition"] = trans
        else:
            slot = _normalize_slot(value, path=f"{path}.transition", phase="in",
                                   report=report)
            if slot is not None:
                out["transition"] = {"in": slot}
    extra = set(raw) - {"entry", "out", "transition"}
    if extra:
        report.note(path, "ignoring unknown animation keys", sorted(extra))
    return out


# ─── Canvas, containers, blocks ─────────────────────────────────────────────


def _validate_canvas(raw: Any, *, report: ThemeReport) -> dict:
    path = "canvas"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        report.warn(path, "canvas must be an object", type(raw).__name__)
        raw = {}
    return {
        "width": coerce_number(raw.get("width", 1920), 1920, 320, 7680,
                               path=f"{path}.width", report=report,
                               integer=True, label="width"),
        "height": coerce_number(raw.get("height", 1080), 1080, 240, 4320,
                                path=f"{path}.height", report=report,
                                integer=True, label="height"),
        "background": _coerce_paint(raw.get("background", "transparent"),
                                    "transparent", path=f"{path}.background",
                                    report=report),
        "fit": coerce_enum(raw.get("fit", "contain"), ("contain", "none"),
                           "contain", path=f"{path}.fit", report=report),
    }


def _validate_position(raw: Any, *, path: str, report: ThemeReport) -> dict:
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        report.warn(path, "position must be an object", type(raw).__name__)
        raw = {}
    anchor = raw.get("anchor")
    if anchor is None:
        corners = [key for key in CORNER_KEYS if raw.get(key) is True]
        if corners:
            anchor = corners[0]
            report.warn(path, "corner boolean position is legacy", anchor, anchor)
            # §4.3: the fixed corner order picks the winner; extras are ignored
            # loudly so a file with two corners is not silently misread.
            for extra_corner in corners[1:]:
                report.warn(path, "extra corner key ignored", extra_corner, anchor)
    else:
        for key in CORNER_KEYS:
            if raw.get(key) is True:
                report.note(path, f"corner key ignored because anchor is set: {key}")
    anchor = coerce_enum(anchor, ANCHORS, "center", path=f"{path}.anchor",
                         report=report)
    out: dict = {"anchor": anchor}
    for axis in ("x", "y"):
        if axis in raw and raw[axis] is not None:
            out[axis] = coerce_length(
                raw[axis], 0, path=f"{path}.{axis}", report=report,
                minimum=-10000, maximum=10000, percent=True, label=axis)
    extra = set(raw) - {"anchor", "x", "y"} - set(CORNER_KEYS)
    if extra:
        report.note(path, "ignoring unknown position keys", sorted(extra))
    return out


def _validate_block(block_id: str, raw: Any, *, path: str,
                    report: ThemeReport, inherit_from: Optional[dict] = None) -> dict:
    if block_id == "body":
        if not isinstance(raw, dict):
            report.warn(path, "body must be an object", type(raw).__name__)
            raw = {}
        out = _body_defaults()
        for key in ("visible",):
            if key in raw:
                out[key] = coerce_bool(raw[key], out[key],
                                       path=f"{path}.{key}", report=report)
        out["valign"] = coerce_enum(raw.get("valign", "center"),
                                    ("top", "center", "bottom"), "center",
                                    path=f"{path}.valign", report=report)
        out["gap"] = coerce_length(raw.get("gap", 0), 0, path=f"{path}.gap",
                                   report=report, minimum=0, maximum=200)
        base_pad = coerce_length(raw.get("padding", 0), 0,
                                 path=f"{path}.padding", report=report,
                                 minimum=0, maximum=400)
        out["padding"] = base_pad
        for side in ("top", "right", "bottom", "left"):
            key = f"padding_{side}"
            out[key] = coerce_length(raw.get(key, base_pad), base_pad,
                                     path=f"{path}.{key}", report=report,
                                     minimum=0, maximum=400)
        if "animation" in raw:
            anim = normalize_animation_assignment(
                raw["animation"], path=f"{path}.animation", report=report)
            if anim:
                out["animation"] = anim
        inert = set(raw) - {"visible", "valign", "gap", "padding", "padding_top",
                            "padding_right", "padding_bottom", "padding_left",
                            "animation"}
        if inert:
            report.warn(path, "body typography/layout keys are inert",
                        sorted(inert))
        return out

    if not isinstance(raw, dict):
        report.warn(path, "block must be an object", type(raw).__name__)
        raw = {}
    defaults = block_defaults(block_id)
    out = copy.deepcopy(defaults)

    # Translation typography inherits from its anchor unless set explicitly.
    if block_id == "translation" and inherit_from:
        for key in INHERITABLE_TRANSLATION_FIELDS:
            if key not in raw and key in inherit_from:
                out[key] = copy.deepcopy(inherit_from[key])

    def put(key, value):
        out[key] = value

    if "visible" in raw:
        put("visible", coerce_bool(raw["visible"], True,
                                   path=f"{path}.visible", report=report))
    if "color" in raw:
        put("color", _coerce_color(raw["color"], out["color"],
                                   path=f"{path}.color", report=report))
    if "font_family" in raw:
        put("font_family", _coerce_family(raw["font_family"], out["font_family"],
                                          path=f"{path}.font_family",
                                          report=report))
    if "size" in raw:
        put("size", coerce_length(raw["size"], out["size"],
                                  path=f"{path}.size", report=report,
                                  minimum=1, maximum=400, em=True,
                                  inherit=True, label="size"))
    if "min_size" in raw:
        put("min_size", coerce_length(raw["min_size"], out["min_size"],
                                      path=f"{path}.min_size", report=report,
                                      minimum=1, maximum=400, label="min_size"))
    if "max_size" in raw:
        put("max_size", coerce_length(raw["max_size"], out["max_size"],
                                      path=f"{path}.max_size", report=report,
                                      minimum=1, maximum=400, label="max_size"))
    if "weight" in raw:
        put("weight", coerce_number(raw["weight"], out["weight"], 100, 900,
                                    path=f"{path}.weight", report=report,
                                    integer=True, label="weight"))
    if "line_height" in raw:
        put("line_height", coerce_number(raw["line_height"], out["line_height"],
                                         0.5, 3, path=f"{path}.line_height",
                                         report=report, label="line_height"))
    if "letter_spacing" in raw:
        put("letter_spacing", coerce_length(
            raw["letter_spacing"], out["letter_spacing"],
            path=f"{path}.letter_spacing", report=report,
            minimum=-20, maximum=40, em=True, label="letter_spacing"))
    if "word_spacing" in raw:
        put("word_spacing", coerce_length(
            raw["word_spacing"], out.get("word_spacing", 0),
            path=f"{path}.word_spacing", report=report,
            minimum=-20, maximum=40, em=True, label="word_spacing"))
    if "text_shadow" in raw:
        put("text_shadow", _coerce_shadow(raw["text_shadow"], out["text_shadow"],
                                          path=f"{path}.text_shadow",
                                          report=report))
    if "text_outline" in raw:
        value = raw["text_outline"]
        if isinstance(value, str) and value.strip().lower() in ("none", "off"):
            put("text_outline", "none")
        else:
            parsed = sanitize_outline(value)
            if parsed is None:
                report.warn(f"{path}.text_outline", "invalid outline", value,
                            "none")
                parsed = "none"
            put("text_outline", parsed)
    if "text_transform" in raw:
        put("text_transform", coerce_enum(
            raw["text_transform"],
            ("none", "uppercase", "lowercase", "capitalize"),
            out["text_transform"], path=f"{path}.text_transform",
            report=report))
    if "text_align" in raw:
        put("text_align", coerce_enum(
            raw["text_align"], ("left", "center", "right", "justify"),
            out["text_align"], path=f"{path}.text_align", report=report))
    if "font_style" in raw:
        put("font_style", coerce_enum(raw["font_style"], ("normal", "italic"),
                                      out["font_style"],
                                      path=f"{path}.font_style", report=report))
    if "text_decoration" in raw:
        put("text_decoration", coerce_enum(
            raw["text_decoration"], ("none", "underline", "line-through"),
            out["text_decoration"], path=f"{path}.text_decoration",
            report=report))
    if "opacity" in raw:
        put("opacity", coerce_number(raw["opacity"], out["opacity"], 0, 1,
                                     path=f"{path}.opacity", report=report,
                                     label="opacity"))
    if "max_lines" in raw:
        value = raw["max_lines"]
        if value is None:
            put("max_lines", None)
        else:
            put("max_lines", coerce_number(value, 1, 1, 20,
                                           path=f"{path}.max_lines",
                                           report=report, integer=True,
                                           label="max_lines"))
    if "direction" in raw:
        put("direction", coerce_enum(raw["direction"], ("ltr", "rtl"),
                                     out["direction"], path=f"{path}.direction",
                                     report=report))
    for side in ("top", "right", "bottom", "left"):
        key = f"margin_{side}"
        if key in raw:
            put(key, coerce_length(raw[key], out[key], path=f"{path}.{key}",
                                   report=report, minimum=-400, maximum=400,
                                   em=True))
    base_pad = coerce_length(raw.get("padding", 0), 0, path=f"{path}.padding",
                             report=report, minimum=0, maximum=400)
    put("padding", base_pad)
    for side in ("top", "right", "bottom", "left"):
        key = f"padding_{side}"
        put(key, coerce_length(raw.get(key, base_pad), base_pad,
                               path=f"{path}.{key}", report=report,
                               minimum=0, maximum=400))

    if block_id == "text":
        if "autosize" in raw:
            put("autosize", coerce_bool(raw["autosize"], True,
                                        path=f"{path}.autosize", report=report))
    if block_id in ("reference", "title"):
        if "position" in raw:
            put("position", coerce_enum(
                raw["position"], ("above_verse", "below_verse"), "below_verse",
                path=f"{path}.position", report=report))
    if block_id == "translation":
        if "position" in raw:
            put("position", coerce_enum(
                raw["position"],
                ("above_verse", "below_verse", "above_reference",
                 "below_reference", "left_of_reference", "right_of_reference"),
                "right_of_reference", path=f"{path}.position", report=report))
    if block_id == "verse_num":
        if "mode" in raw:
            put("mode", coerce_enum(raw["mode"], ("inline", "block"), "inline",
                                    path=f"{path}.mode", report=report))
        if "position" in raw:
            put("position", coerce_enum(
                raw["position"], ("above_verse", "below_verse"), "above_verse",
                path=f"{path}.position", report=report))
        if "vertical_align" in raw:
            put("vertical_align", coerce_enum(
                raw["vertical_align"],
                ("top", "middle", "baseline", "bottom"), "top",
                path=f"{path}.vertical_align", report=report))
        if "margin_right" in raw:
            put("margin_right", coerce_length(
                raw["margin_right"], out["margin_right"],
                path=f"{path}.margin_right", report=report,
                minimum=0, maximum=40, em=True, label="margin_right"))

    if "animation" in raw:
        anim = normalize_animation_assignment(
            raw["animation"], path=f"{path}.animation", report=report)
        if anim:
            put("animation", anim)

    known = set(out)
    extra = set(raw) - known
    if extra:
        report.note(path, "ignoring unknown block keys", sorted(extra))
    return out


def _block_order(block_id: str) -> int:
    return {
        "verse_num": 0, "title": 1, "reference": 2, "translation": 3,
        "text": 4, "body": 5,
    }.get(block_id, 9)


def _validate_container(raw: Any, index: int, *, theme_kind: str,
                        report: ThemeReport) -> Optional[dict]:
    path = f"containers[{index}]"
    if not isinstance(raw, dict):
        report.warn(path, "container is not an object", type(raw).__name__)
        return None
    cid = raw.get("id")
    if not isinstance(cid, str) or not _ID_RE.match(cid):
        cid = f"container{index}"
        report.warn(f"{path}.id", "invalid container id", raw.get("id"), cid)
    out: dict = {
        "id": cid,
        "label": clean_text(raw.get("label"), 80, path=f"{path}.label",
                            report=report, default=cid),
        "kind": coerce_enum(raw.get("kind", theme_kind),
                            ("scripture", "freeform", "any"), theme_kind,
                            path=f"{path}.kind", report=report),
        "layer": coerce_number(raw.get("layer", index * 10), index * 10, 0, 100,
                               path=f"{path}.layer", report=report,
                               integer=True, label="layer"),
        "visible": coerce_bool(raw.get("visible", True), True,
                               path=f"{path}.visible", report=report),
        "position": _validate_position(raw.get("position"),
                                       path=f"{path}.position", report=report),
        "width": coerce_length(raw.get("width", "auto"), "auto",
                               path=f"{path}.width", report=report, percent=True,
                               auto=True, label="width"),
        "height": coerce_length(raw.get("height", "auto"), "auto",
                                path=f"{path}.height", report=report, percent=True,
                                auto=True, label="height"),
        "min_width": coerce_length(raw.get("min_width", 0), 0,
                                   path=f"{path}.min_width", report=report,
                                   minimum=0, maximum=7680, percent=True,
                                   label="min_width"),
        "max_width": (None if raw.get("max_width") is None else
                      coerce_length(raw.get("max_width"), None,
                                    path=f"{path}.max_width", report=report,
                                    minimum=0, maximum=7680, percent=True,
                                    label="max_width")),
        "min_height": coerce_length(raw.get("min_height", 0), 0,
                                    path=f"{path}.min_height", report=report,
                                    minimum=0, maximum=4320, percent=True,
                                    label="min_height"),
        "max_height": (None if raw.get("max_height") is None else
                       coerce_length(raw.get("max_height"), None,
                                     path=f"{path}.max_height", report=report,
                                     minimum=0, maximum=4320, percent=True,
                                     label="max_height")),
        "background": _coerce_paint(raw.get("background", "transparent"),
                                    "transparent", path=f"{path}.background",
                                    report=report),
        "border": _coerce_border(raw.get("border", "none"), "none",
                                 path=f"{path}.border", report=report),
        "border_radius": (None if raw.get("border_radius") is None else
                          coerce_length(raw.get("border_radius"), 0,
                                        path=f"{path}.border_radius",
                                        report=report, minimum=0, maximum=400,
                                        percent=True, label="border_radius")),
        "box_shadow": _coerce_shadow(raw.get("box_shadow", "none"), "none",
                                     path=f"{path}.box_shadow", report=report),
        "backdrop_filter": _coerce_filter(raw.get("backdrop_filter", "none"),
                                          "none", path=f"{path}.backdrop_filter",
                                          report=report),
        "opacity": coerce_number(raw.get("opacity", 1.0), 1.0, 0, 1,
                                 path=f"{path}.opacity", report=report,
                                 label="opacity"),
        "overflow": coerce_enum(raw.get("overflow", "hidden"),
                                ("hidden", "visible"), "hidden",
                                path=f"{path}.overflow", report=report),
    }
    if "animation" in raw:
        anim = normalize_animation_assignment(
            raw["animation"], path=f"{path}.animation", report=report)
        if anim:
            out["animation"] = anim
    if out["position"]["anchor"] == "fill":
        # §4.3: `fill` is the only keyword that overrides explicit size, so
        # anything that claims to change the box is ignored with a warning.
        ignored = [key for key in ("width", "height") if raw.get(key) is not None]
        ignored += [axis for axis in ("x", "y")
                    if out["position"].get(axis) is not None]
        if ignored:
            report.warn(path, "fill ignores size and offset", sorted(ignored),
                        "canvas size at 0,0")
    if any(key.startswith("padding") for key in raw):
        report.warn(path, "container padding is not a v2 parameter",
                    sorted(k for k in raw if k.startswith("padding")))
    for key in ("display", "flex_direction", "justify_content", "align_items"):
        if key in raw:
            report.warn(f"{path}.{key}", "legacy flex key is ignored", raw[key])
    known = {
        "id", "label", "kind", "layer", "visible", "position", "width",
        "height", "min_width", "max_width", "min_height", "max_height",
        "background", "border", "border_radius", "box_shadow",
        "backdrop_filter", "opacity", "overflow", "animation", "blocks",
        "display", "flex_direction", "justify_content", "align_items",
    }
    unknown = {key for key in raw
               if key not in known and not key.startswith("padding")}
    if unknown:
        report.note(path, "ignoring unknown container keys", sorted(unknown))

    # Blocks
    raw_blocks = raw.get("blocks")
    if raw_blocks is None:
        raw_blocks = {}
    if not isinstance(raw_blocks, dict):
        report.warn(f"{path}.blocks", "blocks must be an object",
                    type(raw_blocks).__name__)
        raw_blocks = {}
    allowed = BLOCK_IDS[theme_kind]
    aliases = BLOCK_ALIASES.get(theme_kind, {})
    blocks: dict = {}
    for block_id, block_raw in raw_blocks.items():
        canonical = aliases.get(block_id, block_id)
        if canonical not in allowed:
            report.warn(f"{path}.blocks.{block_id}", "unknown block for this kind",
                        block_id, "ignored")
            continue
        if canonical in blocks:
            report.warn(f"{path}.blocks.{block_id}",
                        "duplicate block; first occurrence wins", block_id)
            continue
        blocks[canonical] = (block_raw, block_id)
    out_blocks: dict = {}
    # Validate in render order so translation inheritance sees its anchor.
    ordered = sorted(blocks, key=_block_order)
    for block_id in ordered:
        block_raw, original_key = blocks[block_id]
        inherit = None
        if block_id == "translation":
            pos = block_raw.get("position", "right_of_reference") if isinstance(block_raw, dict) else "right_of_reference"
            if pos in ("above_reference", "below_reference", "left_of_reference",
                       "right_of_reference"):
                inherit = out_blocks.get("reference") or out_blocks.get("title")
            else:
                inherit = out_blocks.get("text")
        out_blocks[block_id] = _validate_block(
            block_id, block_raw, path=f"{path}.blocks.{original_key}",
            report=report, inherit_from=inherit)
    if "body" not in out_blocks:
        out_blocks["body"] = _body_defaults()
    out["blocks"] = out_blocks
    return out


def _resolve_animation_refs(theme: dict, local: dict,
                            shared_defs: dict, report: ThemeReport) -> None:
    """Replace/validate `use` names and emit the referenced definition map."""
    available = {}
    available.update(BUILTIN_ANIMATIONS)
    available.update(shared_defs)
    available.update(local)

    referenced: dict = {}

    def resolve_slot(slot: dict, path: str, phase: str) -> dict:
        if "use" not in slot:
            return slot
        name = slot["use"]
        definition = available.get(name)
        if definition is None:
            fallback = "fade_out" if phase == "out" else "fade_in"
            report.warn(path, "unknown animation name", name, fallback)
            name = fallback
            definition = BUILTIN_ANIMATIONS[fallback]
        referenced[name] = copy.deepcopy(definition)
        return {"use": name, **{k: v for k, v in slot.items() if k != "use"}}

    def walk(owner: dict, path: str) -> None:
        anim = owner.get("animation")
        if not isinstance(anim, dict):
            return
        if "entry" in anim:
            anim["entry"] = resolve_slot(anim["entry"], f"{path}.animation.entry",
                                         "entry")
        if "out" in anim:
            anim["out"] = resolve_slot(anim["out"], f"{path}.animation.out", "out")
        trans = anim.get("transition")
        if isinstance(trans, dict):
            if "out" in trans:
                trans["out"] = resolve_slot(
                    trans["out"], f"{path}.animation.transition.out", "out")
            if "in" in trans:
                trans["in"] = resolve_slot(
                    trans["in"], f"{path}.animation.transition.in", "in")

    for index, container in enumerate(theme.get("containers", [])):
        walk(container, f"containers[{index}]")
        for block_id, block in container.get("blocks", {}).items():
            walk(block, f"containers[{index}].blocks.{block_id}")
    theme["animations"] = referenced


def _validate_top(raw: dict, *, kind: str, name: str,
                  report: ThemeReport) -> dict:
    out: dict = {"schema_version": SCHEMA_VERSION}
    out["name"] = clean_text(raw.get("name"), 64, path="name", report=report,
                             default=name)
    if not _NAME_RE.match(out["name"]):
        report.warn("name", "invalid theme name", out["name"], name)
        out["name"] = name if _NAME_RE.match(name or "") else "theme"
    out["label"] = clean_text(raw.get("label"), 120, path="label",
                              report=report, default=out["name"])
    out["description"] = clean_text(raw.get("description"), 500,
                                    path="description", report=report)
    out["author"] = clean_text(raw.get("author"), 120, path="author",
                               report=report)
    theme_kind = raw.get("kind")
    if theme_kind is not None:
        theme_kind = coerce_enum(theme_kind, KINDS, kind, path="kind",
                                 report=report)
        if theme_kind != kind:
            report.warn("kind", "theme kind disagrees with its folder", theme_kind,
                        kind)
    out["kind"] = kind
    out["canvas"] = _validate_canvas(raw.get("canvas"), report=report)

    raw_containers = raw.get("containers")
    if isinstance(raw_containers, dict):
        report.warn("containers", "v2 containers must be an array; repaired",
                    "object", "array")
        raw_containers = [dict(value, id=key) for key, value in raw_containers.items()
                          if isinstance(value, dict)]
    if not isinstance(raw_containers, list) or not raw_containers:
        report.warn("containers", "no containers; generating `main`",
                    None, "main")
        raw_containers = [{"id": "main"}]
    if len(raw_containers) > 16:
        report.warn("containers", "more than 16 containers; excess dropped",
                    len(raw_containers), 16)
        raw_containers = raw_containers[:16]

    containers = []
    seen_ids = set()
    for index, raw_container in enumerate(raw_containers):
        validated = _validate_container(raw_container, index, theme_kind=kind,
                                        report=report)
        if validated is None:
            continue
        if validated["id"] in seen_ids:
            new_id = f"{validated['id']}_{index}"
            report.warn(f"containers[{index}].id", "duplicate container id",
                        validated["id"], new_id)
            validated["id"] = new_id
        seen_ids.add(validated["id"])
        containers.append(validated)
    if not containers:
        report.error("containers", "no valid container survives")
        return {}
    out["containers"] = containers

    if kind == FREEFORM:
        # Freeform is single-container for now: later containers must be hidden.
        for index, container in enumerate(containers[1:], start=1):
            if container.get("visible", True):
                report.warn(f"containers[{index}].visible",
                            "freeform themes render only the first visible container",
                            True, False)
                container["visible"] = False

    local_animations = _validate_animation_library(
        raw.get("animations"), path="animations", report=report)
    out["_local_animations"] = local_animations  # stripped after resolution

    slide = raw.get("slide")
    if isinstance(slide, dict):
        out["slide"] = {
            "show_title": coerce_bool(slide.get("show_title", True), True,
                                      path="slide.show_title", report=report)
        }
    unknown = set(raw) - {
        "schema_version", "name", "label", "description", "author", "kind",
        "canvas", "containers", "animations", "slide",
    }
    if unknown:
        report.note("", "ignoring unknown top-level keys", sorted(unknown))
    return out


def normalize_theme(raw: Any, kind: Optional[str] = None,
                    name: Optional[str] = None) -> tuple[dict, ThemeReport]:
    """Migrate/validate any theme document into a complete v2 dict.

    Never mutates `raw` and never writes to disk. Returns (resolved, report);
    on a fatal error the resolved dict is a deep copy of SAFE_THEME.
    """
    report = ThemeReport()
    if not isinstance(raw, dict):
        report.theme = name or "?"
        report.error("", "theme root is not an object", type(raw).__name__)
        return _safe_copy(), report

    theme_name = name or raw.get("name") or "theme"
    report.theme = str(theme_name)
    if not isinstance(kind, str) or kind not in KINDS:
        kind = raw.get("kind") if raw.get("kind") in KINDS else SCRIPTURE

    version = raw.get("schema_version", 1)
    if isinstance(version, str) and _NUM_RE.match(version.strip()):
        version = int(float(version))
    if not isinstance(version, int) or isinstance(version, bool):
        report.warn("schema_version", "invalid schema version", version, 1)
        version = 1
    if version > SCHEMA_VERSION:
        report.error("schema_version", "future schema version", version)
        return _safe_copy(), report

    data = copy.deepcopy(raw)
    if version <= 1:
        from core.theme_migrate import migrate_v1_to_v2
        data = migrate_v1_to_v2(data, kind=kind, report=report)

    shared_defs: dict = {}
    try:
        from core.theme_shared import resolve_shared
        shared_defs = resolve_shared(data, report=report)
    except Exception as exc:  # shared files must never break a theme
        logger.error("Shared theme resolution failed: %s", exc)
        report.warn("_shared", "shared file resolution failed", str(exc), "none")
        shared_defs = {}

    resolved = _validate_top(data, kind=kind, name=report.theme,
                             report=report)
    if not resolved:
        return _safe_copy(), report
    local = resolved.pop("_local_animations", {})
    _resolve_animation_refs(resolved, local, shared_defs, report)
    return resolved, report


def _safe_copy() -> dict:
    return copy.deepcopy(SAFE_THEME)


# ─── Safe fallback (current fullscreen.json look) ───────────────────────────


def _safe_theme() -> dict:
    text = _text_defaults()
    text.update({
        "color": "#ffffff",
        "font_family": "'Nunito', sans-serif",
        "size": 80,
        "min_size": 60,
        "max_size": 96,
        "weight": 700,
        "line_height": 1.08,
        "letter_spacing": "-0.02em",
        "text_shadow": "none",
        "text_outline": "none",
        "text_transform": "none",
        "text_align": "center",
        "margin_bottom": 24,
    })
    reference = _reference_defaults()
    reference.update({
        "color": "#D4AF37",
        "font_family": "'Nunito', sans-serif",
        "size": 48,
        "weight": 800,
        "line_height": 1.2,
        "letter_spacing": "0.1em",
        "text_transform": "uppercase",
        "text_align": "center",
        "text_shadow": "none",
    })
    translation = _translation_defaults()
    translation.update({
        "color": "#AAFF00",
        "margin_left": 8,
        # Inherited from the reference line at resolve time; explicit here
        # so SAFE_THEME renders without a cascade.
        "font_family": reference["font_family"],
        "size": reference["size"],
        "weight": reference["weight"],
        "line_height": reference["line_height"],
        "letter_spacing": reference["letter_spacing"],
        "text_transform": reference["text_transform"],
    })
    verse_num = _verse_num_defaults()
    verse_num.update({
        "color": "#D4AF37",
        "font_family": "'Nunito', sans-serif",
    })
    body = _body_defaults()
    return {
        "schema_version": 2,
        "name": "SAFE_THEME",
        "label": "Safe fallback",
        "description": "Built-in fallback matching the shipped fullscreen theme.",
        "author": "RhemaCast",
        "kind": "scripture",
        "canvas": {"width": 1920, "height": 1080,
                   "background": "transparent", "fit": "contain"},
        "containers": [{
            "id": "main",
            "label": "Verse",
            "kind": "scripture",
            "layer": 10,
            "visible": True,
            "position": {"anchor": "top_left", "x": 60, "y": 40},
            "width": 1800,
            "height": 1000,
            "min_width": 1800,
            "max_width": 1800,
            "min_height": 0,
            "max_height": None,
            "background": "transparent",
            "border": "none",
            "border_radius": 0,
            "box_shadow": "none",
            "backdrop_filter": "none",
            "opacity": 1.0,
            "overflow": "hidden",
            "blocks": {
                "body": body,
                "text": text,
                "reference": reference,
                "translation": translation,
                "verse_num": verse_num,
            },
        }],
        "animations": {},
    }


SAFE_THEME = _safe_theme()
