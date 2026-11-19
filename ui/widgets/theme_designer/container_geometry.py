"""Theme position model ↔ absolute canvas rectangles.

Two models live in ``containers[i].position``:

* the legacy one — ``{anchor, x, y}``, where x/y are offsets from the anchor
  and every anchor keyword (``center``, ``left``, ``fill``…) has its own
  arithmetic. Files that only carry these keys render exactly as they always
  did, and are never rewritten on load;
* the pin model (round 4) — ``{mode, canvas, edge}``. A container picks one of
  nine points of its own box (the pin) and says where on the canvas the pin
  goes. Resizing then grows the box around the pin.

:func:`resolve_origin` is the one resolver for the pin model; the renderers
(``display/display.js`` and its mirror in ``ui/widgets/display_view.py``) carry
the same function in JavaScript. The Stage 1 canvas works in absolute design
pixels, so these helpers are the only place that converts between the stored
form and a rectangle; the canvas, strip and exact fields cannot drift.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from core import theme_schema as schema

_PX_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*px$", re.I)
_PCT_RE = re.compile(r"^(-?\d+(?:\.\d+)?)\s*%$")

_AUTO_WIDTH = 0.6
_AUTO_HEIGHT = 0.4

#: Where each of the nine pin points sits in the box, as fractions.
FRACTIONS = {
    "top_left": (0.0, 0.0), "top": (0.5, 0.0), "top_right": (1.0, 0.0),
    "left": (0.0, 0.5), "center": (0.5, 0.5), "right": (1.0, 0.5),
    "bottom_left": (0.0, 1.0), "bottom": (0.5, 1.0),
    "bottom_right": (1.0, 1.0),
}

#: The nine pin points, row-major (docs/PANEL_ORGANIZATION.md §3).
POINTS = schema.POSITION_POINTS


def fractions(point: Any) -> tuple[float, float]:
    """``(ax, ay)`` for a pin point; unknown points pin the top-left."""
    return FRACTIONS.get(str(point or ""), (0.0, 0.0))


def position_model(position: Any) -> Optional[dict]:
    """The pin-model payload, or None for a legacy position.

    Presence of either mode payload is the marker: a legacy file only has
    ``anchor``/``x``/``y`` and keeps rendering through the old arithmetic.
    """
    if not isinstance(position, dict):
        return None
    if isinstance(position.get("canvas"), dict) \
            or isinstance(position.get("edge"), dict):
        return position
    return None


def _clamped(value: float, minimum: Any, maximum: Any,
             axis_total: float) -> float:
    """A size with Min/Max applied, the way the box is painted."""
    low = resolve_length(minimum, axis_total, 0.0)
    if low > value:
        value = low
    if maximum is not None:
        high = resolve_length(maximum, axis_total, value)
        if value > high:
            value = high
    return value


def _edge_distance(edge_payload: dict, canvas_size: tuple[float, float]) \
        -> float:
    """Resolve ``d`` to design pixels: px as-is, percent of the tied axis."""
    edge = str(edge_payload.get("edge") or "left")
    axis = 0 if edge in ("left", "right") else 1
    value = edge_payload.get("d")
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        number = resolve_length(value, canvas_size[axis], 0.0)
        return number
    if str(edge_payload.get("unit") or "px") == "percent":
        return canvas_size[axis] * number / 100.0
    return number


def resolve_origin(position: Any, width: float, height: float,
                   canvas_size: tuple[float, float]) \
        -> tuple[float, float]:
    """Top-left origin of the pin model, in design pixels.

    Canvas mode: the pin is the aligned canvas point, or the stored ``x``/``y``.
    Edge mode: one axis is a distance in from a canvas edge, the other follows
    the anchor. Floats throughout; the caller rounds at paint. Nothing is
    clamped, so off-canvas positions are valid.
    """
    width_total, height_total = float(canvas_size[0]), float(canvas_size[1])
    position = position if isinstance(position, dict) else {}
    canvas = position.get("canvas") if isinstance(position.get("canvas"),
                                                  dict) else {}
    edge = position.get("edge") if isinstance(position.get("edge"), dict) else {}
    if str(position.get("mode") or "canvas") == "edge" and edge:
        anchor = edge.get("anchor") or canvas.get("anchor") or "top_left"
        ax, ay = fractions(anchor)
        pinned_edge = str(edge.get("edge") or "left")
        distance = _edge_distance(edge, canvas_size)
        pin_x = distance if pinned_edge == "left" else (
            width_total - distance if pinned_edge == "right" else ax * width_total)
        pin_y = distance if pinned_edge == "top" else (
            height_total - distance if pinned_edge == "bottom" else ay * height_total)
        return pin_x - ax * width, pin_y - ay * height
    anchor = canvas.get("anchor") or "top_left"
    ax, ay = fractions(anchor)
    aligned = canvas.get("aligned")
    if aligned in FRACTIONS:
        alx, aly = fractions(aligned)
        pin_x, pin_y = alx * width_total, aly * height_total
    else:
        pin_x = float(canvas.get("x") or 0.0)
        pin_y = float(canvas.get("y") or 0.0)
    return pin_x - ax * width, pin_y - ay * height


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


def container_size(container: dict,
                   canvas_size: tuple[float, float]) -> tuple[float, float]:
    """The box the renderer paints: width/height after Min/Max.

    Position takes no part, which is what lets a tie read its target's size
    before its own origin is known (round 5).
    """
    width_total, height_total = float(canvas_size[0]), float(canvas_size[1])
    width = resolve_length(container.get("width"), width_total,
                           width_total * _AUTO_WIDTH)
    height = resolve_length(container.get("height"), height_total,
                            height_total * _AUTO_HEIGHT)
    if position_model(container.get("position")) is not None:
        # The pin places the box the renderer actually paints, so Min/Max are
        # applied before resolving (docs/theme_file_reference.md §5.1.1).
        width = _clamped(width, container.get("min_width"),
                         container.get("max_width"), width_total)
        height = _clamped(height, container.get("min_height"),
                          container.get("max_height"), height_total)
    return width, height


def container_rect(container: dict, canvas_size: tuple[float, float],
                   containers: Optional[list] = None) -> dict[str, Any]:
    """Absolute design-pixel box for one container.

    Pass the theme's whole ``containers`` list when a tie must be resolved
    against another container. Without it the container resolves against the
    canvas alone, which is the documented fallback for a dangling tie.
    """
    if containers is not None:
        scene = resolve_scene(containers, canvas_size)
        rect = scene.get(str(container.get("id", "")))
        if rect is not None:
            return rect
    return _canvas_rect(container, canvas_size)


def _canvas_rect(container: dict,
                 canvas_size: tuple[float, float]) -> dict[str, Any]:
    """The rect with no tie applied: the pin model or the legacy arithmetic.

    `auto` sizes have no intrinsic value without layout; they use a canvas
    fraction only for the canvas preview. The document keeps `auto`.
    """
    width_total, height_total = float(canvas_size[0]), float(canvas_size[1])
    width, height = container_size(container, canvas_size)
    position = container.get("position")
    if not isinstance(position, dict):
        position = {}
    if position_model(position) is not None:
        left, top = resolve_origin(position, width, height,
                                   (width_total, height_total))
        return {"x": left, "y": top, "width": width, "height": height,
                "fill": False}
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
               canvas_size: tuple[float, float],
               containers: Optional[list] = None) -> None:
    """Write an absolute canvas rect back as anchor-relative schema values.

    Only axes whose geometry actually changed are rewritten. A pure move keeps
    an authored ``auto``/percentage size, and a move along one axis keeps the
    other axis's authored offset, so round-tripping through the canvas does not
    silently pixelise the document. A resize writes concrete pixels for the
    axes it changed (and for an offset that is measured against that size).

    Pass ``containers`` when a tie has to be measured against its target. A
    tied box moves only along its tie axis: a drag rewrites ``d``, and the
    other axis stays where the tie puts it.

    Unknown keys inside `position` and the container survive. `fill` ignores
    geometry, matching the validator.
    """
    anchor = _anchor(container)
    if position_model(container.get("position")) is not None:
        # A drag/resize on the canvas is a manual pin: it clears `aligned` and
        # moves both axes together in canvas mode. Edge mode only rewrites the
        # distance on its tied axis; the other axis follows the anchor.
        position = container["position"]
        width = float(rect["width"])
        height = float(rect["height"])
        left = float(rect["x"])
        top = float(rect["y"])
        before = container_rect(container, canvas_size, containers)
        width_changed = _moved(before, rect, "width")
        height_changed = _moved(before, rect, "height")
        tied = tie_edge(position)
        if tied is not None and containers is not None:
            target = resolve_scene(containers, canvas_size).get(
                str(tied.get("target")))
            if target is not None:
                ax, ay = fractions(tied.get("anchor"))
                tx, ty = fractions(tied.get("targetPoint")
                                   or tied.get("anchor"))
                point_x = target["x"] + tx * target["width"]
                point_y = target["y"] + ty * target["height"]
                axis = str(tied.get("axis") or "x")
                extent = (target["width"] if axis == "x"
                          else target["height"])
                distance = ((left + ax * width) if axis == "x"
                            else (top + ay * height))
                distance -= point_x if axis == "x" else point_y
                if str(tied.get("unit") or "px") == "percent":
                    tied["d"] = _clean(distance / extent * 100.0 if extent
                                        else 0.0)
                else:
                    tied["d"] = _clean(distance)
                position["edge"] = tied
                if width_changed:
                    container["width"] = _clean(width)
                if height_changed:
                    container["height"] = _clean(height)
                return
        if str(position.get("mode") or "canvas") == "edge":
            edge = position.get("edge") if isinstance(position.get("edge"),
                                                       dict) else {}
            ax, ay = fractions(edge.get("anchor") or "top_left")
            pinned = str(edge.get("edge") or "left")
            width_total, height_total = (float(canvas_size[0]),
                                         float(canvas_size[1]))
            if pinned in ("left", "right"):
                pin = left + ax * width
                extent = width_total
                distance = pin if pinned == "left" else width_total - pin
            else:
                pin = top + ay * height
                extent = height_total
                distance = pin if pinned == "top" else height_total - pin
            if str(edge.get("unit") or "px") == "percent":
                edge["d"] = _clean(distance / extent * 100.0 if extent
                                   else 0.0)
            else:
                edge["d"] = _clean(distance)
            edge.setdefault("target", schema.POSITION_TARGET_DEFAULT)
            position["edge"] = edge
        else:
            canvas = position.get("canvas") if isinstance(
                position.get("canvas"), dict) else {}
            ax, ay = fractions(canvas.get("anchor") or "top_left")
            canvas["x"] = _clean(left + ax * width)
            canvas["y"] = _clean(top + ay * height)
            canvas["aligned"] = None
            position["canvas"] = canvas
        if width_changed:
            container["width"] = _clean(width)
        if height_changed:
            container["height"] = _clean(height)
        return
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


# ─── Ties between containers (round 5) ──────────────────────────────────────

#: Reasons a tie cannot be applied. Stored nowhere; read from `resolve_scene`.
TIE_MISSING = "Target container not found"
TIE_LOOP = "Tie would create a loop"


def tie_edge(position: Any) -> Optional[dict]:
    """The active tie payload, or None when this container is not tied.

    Only ``mode: "edge"`` can tie: the ``canvas`` payload has no target. A
    tie is an edge payload whose ``target`` names another container.
    """
    if not isinstance(position, dict):
        return None
    if str(position.get("mode") or "canvas") != "edge":
        return None
    edge = position.get("edge")
    if not isinstance(edge, dict):
        return None
    target = str(edge.get("target") or schema.POSITION_TARGET_DEFAULT)
    if target == schema.POSITION_TARGET_DEFAULT:
        return None
    return edge


def _distance(edge: dict, extent: float) -> float:
    """``d`` in pixels: px as-is, percent of the axis extent it measures."""
    value = edge.get("d")
    if isinstance(value, bool) or value is None:
        return 0.0
    if not isinstance(value, (int, float)):
        # A string length carries its own unit ("12px", "10%").
        return resolve_length(value, extent, 0.0)
    number = float(value)
    if str(edge.get("unit") or "px") == "percent":
        return extent * number / 100.0
    return number


def _tie_rect(target_rect: dict, width: float, height: float, edge: dict
              ) -> dict[str, Any]:
    """Stick this box to a point of ``target_rect``, then shift by ``d``.

    The point is a screen direction, not an inward distance: positive x moves
    right, positive y moves down. The axis that is not chosen gets no shift.
    """
    ax, ay = fractions(edge.get("anchor"))
    tx, ty = fractions(edge.get("targetPoint") or edge.get("anchor"))
    point_x = target_rect["x"] + tx * target_rect["width"]
    point_y = target_rect["y"] + ty * target_rect["height"]
    axis = str(edge.get("axis") or "x")
    extent = target_rect["width"] if axis == "x" else target_rect["height"]
    shift = _distance(edge, extent)
    left = point_x - ax * width + (shift if axis == "x" else 0.0)
    top = point_y - ay * height + (shift if axis == "y" else 0.0)
    return {"x": left, "y": top, "width": width, "height": height,
            "fill": False}


def resolve_scene(containers: list, canvas_size: tuple[float, float],
                  *, errors: Optional[dict] = None) -> dict[str, dict]:
    """Every container's rectangle, in one pass, ties resolved after targets.

    Each container is resolved once (memoised) and a tie reads its target's
    *resolved* rectangle, so chains and shared targets cost nothing extra. A
    tie that cannot be applied — a missing target, or a loop in the data —
    falls back to that container's own canvas arithmetic, exactly as it would
    render without the tie, and the reason lands in ``errors[id]``. The file is
    never rewritten here.
    """
    canvas = (float(canvas_size[0]), float(canvas_size[1]))
    by_id: dict[str, dict] = {}
    for container in containers or []:
        if isinstance(container, dict):
            by_id[str(container.get("id", ""))] = container
    ties = {cid: tie_edge(container.get("position"))
            for cid, container in by_id.items()}
    reasons: dict[str, str] = {}

    for cid, edge in ties.items():
        if edge is None:
            continue
        if str(edge.get("target")) not in by_id:
            reasons[cid] = TIE_MISSING

    # Loops: walk each target chain; every node from the repeated one on is a
    # member of the cycle and renders through the fallback.
    for cid in by_id:
        if cid in reasons or ties.get(cid) is None:
            continue
        seen: list[str] = []
        node: Optional[str] = cid
        while node is not None and node in by_id and node not in seen \
                and node not in reasons and ties.get(node) is not None:
            seen.append(node)
            node = str(ties[node].get("target"))
        if node is not None and node in seen:
            for member in seen[seen.index(node):]:
                if ties.get(member) is not None:
                    reasons.setdefault(member, TIE_LOOP)

    sizes = {cid: container_size(container, canvas)
             for cid, container in by_id.items()}
    rects: dict[str, dict] = {}

    def resolve(cid: str) -> dict:
        rect = rects.get(cid)
        if rect is not None:
            return rect
        container = by_id[cid]
        width, height = sizes[cid]
        edge = ties.get(cid)
        if edge is not None and cid not in reasons:
            target_rect = resolve(str(edge.get("target")))
            rect = _tie_rect(target_rect, width, height, edge)
        else:
            rect = _canvas_rect(container, canvas)
        rects[cid] = rect
        return rect

    for cid in by_id:
        resolve(cid)
    if errors is not None:
        errors.clear()
        errors.update(reasons)
    return rects


def tie_cycle_reason(containers: list, source: str, target: str) -> str:
    """Why ``source`` cannot tie to ``target``, or ``""`` when it can.

    Used by the target picker (greyed options) and by every document write, so
    the UI and the data can never disagree about what is allowed.
    """
    target = str(target or "")
    if not target or target == schema.POSITION_TARGET_DEFAULT:
        return ""
    ids = {str(c.get("id", "")) for c in containers or []
           if isinstance(c, dict)}
    if target not in ids:
        return TIE_MISSING
    if target == str(source or ""):
        return "would create a loop"
    by_id = {str(c.get("id", "")): c for c in containers or []
             if isinstance(c, dict)}
    seen: set[str] = set()
    node: Optional[str] = target
    while node and node not in seen:
        seen.add(node)
        edge = tie_edge((by_id.get(node) or {}).get("position"))
        if edge is None:
            return ""
        nxt = str(edge.get("target") or schema.POSITION_TARGET_DEFAULT)
        if nxt == str(source or ""):
            return "would create a loop"
        node = nxt if nxt in ids else None
    return ""
