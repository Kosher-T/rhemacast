"""Anchor-relative theme geometry ↔ absolute canvas rectangles.

The schema stores `position: {anchor, x, y}` plus length sizes. The Stage 1
canvas works in absolute design pixels. These helpers are the only place that
converts between the two, so the canvas, strip and exact fields cannot drift.
"""

from __future__ import annotations

import re
from typing import Any

from core import theme_schema as schema

_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*px$", re.I)
_PCT_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*%$")

_AUTO_WIDTH = 0.6
_AUTO_HEIGHT = 0.4


def resolve_length(value: Any, total: float, fallback: float) -> float:
    """Resolve a schema length against the design canvas for display."""
    if isinstance(value, bool) or value is None:
        return float(fallback)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().lower()
    if not text or text == "auto":
        return float(fallback)
    match = _PX_RE.match(text)
    if match:
        return float(match.group(1))
    match = _PCT_RE.match(text)
    if match:
        return total * float(match.group(1)) / 100.0
    return float(fallback)


def _anchor(container: dict) -> str:
    position = container.get("position")
    value = position.get("anchor") if isinstance(position, dict) else None
    return value if value in schema.ANCHORS else "center"


def _offset(position: dict, key: str, total: float) -> float:
    value = position.get(key)
    return resolve_length(value, total, 0.0)


def container_rect(container: dict,
                   canvas_size: tuple[float, float]) -> dict[str, Any]:
    """Absolute design-pixel box for one container.

    `auto` sizes have no intrinsic value without layout; they use a canvas
    fraction only for the canvas preview. The document keeps `auto`.
    """
    width_total, height_total = float(canvas_size[0]), float(canvas_size[1])
    width = resolve_length(container.get("width"), width_total,
                           width_total * _AUTO_WIDTH)
    height = resolve_length(container.get("height"), height_total,
                            height_total * _AUTO_HEIGHT)
    position = container.get("position")
    if not isinstance(position, dict):
        position = {}
    anchor = _anchor(container)
    if anchor == "fill":
        return {"x": 0.0, "y": 0.0, "width": width_total,
                "height": height_total, "fill": True}

    x = _offset(position, "x", width_total)
    y = _offset(position, "y", height_total)
    has_x = position.get("x") is not None
    has_y = position.get("y") is not None

    if anchor == "top_left":
        left, top = x, y
    elif anchor == "top_right":
        left, top = width_total - width - x, y
    elif anchor == "bottom_left":
        left, top = x, height_total - height - y
    elif anchor == "bottom_right":
        left = width_total - width - x
        top = height_total - height - y
    elif anchor == "left":
        left = x
        top = y if has_y else (height_total - height) / 2.0
    elif anchor == "right":
        left = width_total - width - x
        top = y if has_y else (height_total - height) / 2.0
    elif anchor == "top":
        left = x if has_x else (width_total - width) / 2.0
        top = y
    elif anchor == "bottom":
        left = x if has_x else (width_total - width) / 2.0
        top = height_total - height - y
    else:  # center
        left = (width_total - width) / 2.0 + x
        top = (height_total - height) / 2.0 + y
    return {"x": left, "y": top, "width": width, "height": height,
            "fill": False}


def _clean(value: float) -> int | float:
    rounded = round(float(value), 2)
    return int(rounded) if float(rounded).is_integer() else rounded


def _offsets(rect: dict[str, Any], anchor: str,
             canvas_size: tuple[float, float],
             position: dict) -> tuple[float, float]:
    width_total, height_total = float(canvas_size[0]), float(canvas_size[1])
    left = float(rect["x"])
    top = float(rect["y"])
    width = float(rect["width"])
    height = float(rect["height"])
    if anchor == "top_left":
        return left, top
    if anchor == "top_right":
        return width_total - width - left, top
    if anchor == "bottom_left":
        return left, height_total - height - top
    if anchor == "bottom_right":
        return (width_total - width - left,
                height_total - height - top)
    if anchor in ("left", "right"):
        x_offset = left if anchor == "left" else width_total - width - left
        # `left`/`right` centre vertically unless y was authored.
        y_offset = (top if position.get("y") is not None
                    else top - (height_total - height) / 2.0)
        return x_offset, y_offset
    if anchor in ("top", "bottom"):
        # `top`/`bottom` centre horizontally unless x was authored.
        x_offset = (left if position.get("x") is not None
                    else left - (width_total - width) / 2.0)
        y_offset = top if anchor == "top" else height_total - height - top
        return x_offset, y_offset
    return (left - (width_total - width) / 2.0,
            top - (height_total - height) / 2.0)


def _x_follows_width(anchor: str, position: dict) -> bool:
    """True when the x offset is measured against the container's width."""
    if anchor in ("top_right", "bottom_right", "right", "center"):
        return True
    return anchor in ("top", "bottom") and position.get("x") is None


def _y_follows_height(anchor: str, position: dict) -> bool:
    """True when the y offset is measured against the container's height."""
    if anchor in ("bottom_left", "bottom_right", "bottom", "center"):
        return True
    return anchor in ("left", "right") and position.get("y") is None


# The canvas emits integer geometry (ContainerBox.geometry rounds), so half a
# design pixel is display rounding, not an edit.
_EPS = 0.51


def _moved(before: dict[str, Any], rect: dict[str, Any], key: str) -> bool:
    return abs(float(rect[key]) - float(before[key])) > _EPS


def apply_rect(container: dict, rect: dict[str, Any],
               canvas_size: tuple[float, float]) -> None:
    """Write an absolute canvas rect back as anchor-relative schema values.

    Only axes whose geometry actually changed are rewritten. A pure move keeps
    an authored ``auto``/percentage size, and a move along one axis keeps the
    other axis's authored offset, so round-tripping through the canvas does not
    silently pixelise the document. A resize writes concrete pixels for the
    axes it changed (and for an offset that is measured against that size).

    Unknown keys inside `position` and the container survive. `fill` ignores
    geometry, matching the validator.
    """
    anchor = _anchor(container)
    if anchor == "fill":
        return
    before = container_rect(container, canvas_size)
    position = container.get("position")
    if not isinstance(position, dict):
        position = {"anchor": anchor}
    x, y = _offsets(rect, anchor, canvas_size, position)
    width_changed = _moved(before, rect, "width")
    height_changed = _moved(before, rect, "height")
    if _moved(before, rect, "x") or (
            width_changed and _x_follows_width(anchor, position)):
        position["x"] = _clean(x)
    if _moved(before, rect, "y") or (
            height_changed and _y_follows_height(anchor, position)):
        position["y"] = _clean(y)
    container["position"] = position
    if width_changed:
        container["width"] = _clean(float(rect["width"]))
    if height_changed:
        container["height"] = _clean(float(rect["height"]))


def offset_value(container: dict, key: str) -> Any:
    position = container.get("position")
    if not isinstance(position, dict):
        return 0
    value = position.get(key)
    return 0 if value is None else value


def size_value(container: dict, key: str) -> Any:
    value = container.get(key)
    return "auto" if value is None else value
