"""
core/theme_compat.py

Temporary bridge: project a resolved v2 theme back into the v1 shape that
today's `display/display.js` understands.

Phase 2 resolves themes to v2 and stores that in `theme_data`, but the
renderer rewrite lands in Phase 3. Until then every payload builder and
preview pushes this projection, so the screen is byte-for-byte what the
current renderer produced. The bridge is one file on purpose: Phase 3 deletes
it (and the call sites) in a single change.

`project_legacy()` never mutates its input. A v1 raw theme passes through
untouched — there is nothing to project.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Optional

from core.theme_schema import SCHEMA_VERSION

logger = logging.getLogger(__name__)

_VALIGN_TO_FLEX = {"top": "flex-start", "center": "center", "bottom": "flex-end"}
_FLEX_TO_VALIGN = {"flex-start": "top", "center": "center", "flex-end": "bottom"}


def looks_v2(theme: Any) -> bool:
    """True for a resolved/near-resolved v2 theme (array containers + blocks)."""
    if not isinstance(theme, dict):
        return False
    if theme.get("schema_version") == SCHEMA_VERSION:
        return True
    containers = theme.get("containers")
    if isinstance(containers, list):
        return True
    if isinstance(containers, dict):
        return any(isinstance(v, dict) and isinstance(v.get("blocks"), dict)
                   for v in containers.values())
    return False


def _px(value: Any) -> Optional[str]:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        text = str(int(number)) if number.is_integer() else f"{number:g}"
        return f"{text}px"
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if re.fullmatch(r"-?\d+(?:\.\d+)?", text):
            return f"{text}px"
        return text
    return None


def _numeric(value: Any, fallback: float = 0.0) -> float:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(-?\d+(?:\.\d+)?)(?:px)?\s*", value)
        if match:
            return float(match.group(1))
    return fallback


def _resolve_length(value: Any, total: float) -> float:
    """Best-effort px resolution for the v1 geometry the bridge emits."""
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("%"):
            return total * _numeric(text[:-1]) / 100.0
        return _numeric(text)
    return _numeric(value)


def _shadow_css(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        parts = [
            _px(value.get("x", 0)) or "0",
            _px(value.get("y", 0)) or "0",
            _px(value.get("blur", 0)) or "0",
        ]
        spread = _numeric(value.get("spread", 0))
        if spread:
            parts.append(_px(spread) or "0")
        parts.append(str(value.get("color", "rgba(0,0,0,0.5)")))
        if value.get("inset"):
            parts.append("inset")
        return " ".join(parts)
    return "none"


def _border_css(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        width = value.get("width", 0)
        style = value.get("style", "solid")
        color = value.get("color", "currentColor")
        if not width or style == "none":
            return "none"
        return f"{_px(width) or '0'} {style} {color}"
    return "none"


def _padding_shorthand(block: dict) -> str:
    sides = [_numeric(block.get(f"padding_{side}", block.get("padding", 0)))
             for side in ("top", "right", "bottom", "left")]
    return " ".join(f"{int(n) if float(n).is_integer() else n}px" for n in sides)


def _v1_block(block: dict, block_id: str) -> dict:
    out: dict = {}
    for key in (
        "color", "font_family", "weight", "text_transform", "text_align",
        "font_style", "text_decoration", "letter_spacing", "word_spacing",
        "text_shadow", "text_outline", "opacity", "position", "mode",
        "vertical_align",
    ):
        if key in block:
            out[key] = copy.deepcopy(block[key])
    if "text_shadow" in out:
        out["text_shadow"] = _shadow_css(out["text_shadow"])
    for key in ("line_height",):
        if key in block and block[key] is not None:
            out[key] = str(block[key])
    for key in ("size", "min_size", "max_size", "margin_top", "margin_right",
                "margin_bottom", "margin_left", "letter_spacing", "word_spacing"):
        if key in block and block[key] is not None:
            converted = _px(block[key])
            if converted is not None:
                out[key] = converted
    if block.get("autosize") is False:
        out["autosize"] = False
    return out


def _position_to_v1(position: dict, width: float, height: float, *,
                    canvas_w: float, canvas_h: float) -> tuple[float, float]:
    """Resolved v2 position -> absolute top-left for the v1 renderer.

    Per §4.3: the unconstrained axis is centered unless its coordinate is
    given; an edge keyword with a coordinate puts that edge at the
    coordinate (top/left distance), never an offset from center.
    """
    anchor = position.get("anchor", "top_left")
    has_x = position.get("x") is not None
    has_y = position.get("y") is not None
    x = _resolve_length(position.get("x", 0), canvas_w)
    y = _resolve_length(position.get("y", 0), canvas_h)
    centered_x = (canvas_w - width) / 2
    centered_y = (canvas_h - height) / 2

    if anchor == "top_left":
        return x, y
    if anchor == "top_right":
        return canvas_w - width - x, y
    if anchor == "bottom_left":
        return x, canvas_h - height - y
    if anchor == "bottom_right":
        return canvas_w - width - x, canvas_h - height - y
    if anchor == "center":
        return centered_x + x, centered_y + y
    if anchor == "top":
        return (x if has_x else centered_x), y
    if anchor == "bottom":
        return (x if has_x else centered_x), canvas_h - height - y
    if anchor == "left":
        return x, (y if has_y else centered_y)
    if anchor == "right":
        return canvas_w - width - x, (y if has_y else centered_y)
    if anchor == "fill":
        return 0.0, 0.0
    return x, y


def _animation_to_v1(theme: dict) -> Optional[dict]:
    registry = theme.get("animations")
    containers = theme.get("containers")
    if not isinstance(registry, dict) or not isinstance(containers, list):
        return None
    first = next((c for c in containers if isinstance(c, dict)), None)
    if first is None:
        return None
    animation = first.get("animation")
    if not isinstance(animation, dict):
        return None

    def definition(slot: Any) -> tuple[Optional[dict], str]:
        if not isinstance(slot, dict):
            return None, ""
        name = slot.get("use")
        base = registry.get(name) if isinstance(name, str) else None
        if base is None and "type" in slot:
            base = slot
        if base is None:
            # Inline definition: type/duration are in the slot itself.
            base = slot
        typ = base.get("type")
        if not isinstance(typ, str):
            return None, ""
        out = {"type": typ}
        if "duration_ms" in slot:
            out["duration_ms"] = slot["duration_ms"]
        elif "duration_ms" in base:
            out["duration_ms"] = base["duration_ms"]
        if "easing" in slot:
            out["easing"] = slot["easing"]
        elif "easing" in base:
            out["easing"] = base["easing"]
        return out, name or ""

    v1: dict = {}
    entry, _ = definition(animation.get("entry"))
    if entry:
        v1["display_enter"] = entry
    transition = animation.get("transition")
    if isinstance(transition, dict):
        incoming, _ = definition(transition.get("in"))
        if incoming:
            v1["between_slides"] = {
                "in_type": incoming["type"],
                "duration_ms": incoming.get("duration_ms", 600),
                "easing": incoming.get("easing", "ease-out"),
            }
    outgoing, _ = definition(animation.get("out"))
    if outgoing:
        v1["display_exit"] = outgoing
    return v1 or None


def project_legacy(theme: Any) -> Any:
    """Resolved v2 theme -> the v1 dict today's renderer consumes.

    Raw v1 themes (and anything unrecognised) pass through unchanged, so a
    hand-written legacy theme keeps rendering exactly as before.
    """
    if not looks_v2(theme):
        return theme
    if not isinstance(theme, dict):
        return theme

    containers = theme.get("containers")
    if not isinstance(containers, list) or not containers:
        return theme
    visible = [c for c in containers if isinstance(c, dict)
               and c.get("visible", True) is not False]
    if len(visible) > 1:
        logger.warning("Legacy renderer bridge shows the first of %d containers",
                       len(visible))
    if not visible:
        visible = [c for c in containers if isinstance(c, dict)]
    if not visible:
        return theme
    first = visible[0]

    canvas = theme.get("canvas") if isinstance(theme.get("canvas"), dict) else {}
    canvas_w = _numeric(canvas.get("width", 1920), 1920)
    canvas_h = _numeric(canvas.get("height", 1080), 1080)

    blocks = first.get("blocks") if isinstance(first.get("blocks"), dict) else {}
    body = blocks.get("body") if isinstance(blocks.get("body"), dict) else {}

    def resolved_dimension(key: str, min_key: str, max_key: str,
                           canvas: float) -> float:
        value = _resolve_length(first.get(key, "auto"), canvas)
        if value:
            return value
        lo = _resolve_length(first.get(min_key, 0), canvas)
        hi_raw = first.get(max_key)
        hi = _resolve_length(hi_raw, canvas) if hi_raw is not None else 0.0
        # v1's `#container` auto width with min-width:60%/max-width:80% is
        # content-sized between the bounds. When both bounds agree (the
        # shipped pattern) that value is exact; otherwise start from the
        # upper bound so autosize can shrink the text.
        if lo and hi and lo == hi:
            return lo
        if hi:
            return hi
        if lo:
            return lo
        return 0.0

    width = resolved_dimension("width", "min_width", "max_width", canvas_w)
    height = resolved_dimension("height", "min_height", "max_height", canvas_h)
    position = first.get("position") if isinstance(first.get("position"), dict) else {}
    x_value = _resolve_length(position.get("x", 0), canvas_w)
    y_value = _resolve_length(position.get("y", 0), canvas_h)
    if not width:
        width = canvas_w - 2 * x_value
    if not height:
        height = canvas_h - 2 * y_value
    left, top = _position_to_v1(
        position, width, height, canvas_w=canvas_w, canvas_h=canvas_h)
    if position.get("anchor") == "fill":
        # §4.3: `fill` is the only anchor that overrides explicit size.
        width, height = canvas_w, canvas_h
        left, top = 0.0, 0.0

    container: dict = {
        "x": left,
        "y": top,
        "width": _px(width),
        "height": _px(height),
        "display": "flex",
        "flex_direction": "column",
        "justify_content": _VALIGN_TO_FLEX.get(body.get("valign", "center"),
                                               "center"),
        "align_items": "center",
    }
    for key in ("min_width", "max_width"):
        if first.get(key) is not None:
            converted = _px(_resolve_length(first[key], canvas_w))
            if converted:
                container[key] = converted
    padding = _padding_shorthand(body)
    container["padding"] = padding
    for key in ("background", "border", "box_shadow", "backdrop_filter"):
        if key in first:
            value = first[key]
            if key == "border":
                value = _border_css(value)
            elif key == "box_shadow":
                value = _shadow_css(value)
            container[key] = value
    if first.get("border_radius") is not None:
        container["border_radius"] = _px(first["border_radius"])
    else:
        container["border_radius"] = "0"

    body_out: dict = {}
    if body.get("valign"):
        body_out["vertical_align"] = _VALIGN_TO_FLEX.get(body["valign"],
                                                         "flex-start")
    body_out["padding_bottom"] = "0"
    container["body"] = body_out

    for block_id in ("text", "reference", "translation", "verse_num", "title"):
        block = blocks.get(block_id)
        if isinstance(block, dict):
            container[block_id] = _v1_block(block, block_id)

    out: dict = {
        "name": theme.get("name", ""),
        "label": theme.get("label", ""),
        "containers": {first.get("id", "main"): container},
    }
    for key in ("description", "author", "slide"):
        if key in theme and theme[key] is not None:
            out[key] = copy.deepcopy(theme[key])
    animations = _animation_to_v1(theme)
    if animations:
        out["animations"] = animations
    return out
