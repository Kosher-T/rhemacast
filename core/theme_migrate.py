"""
core/theme_migrate.py

Deterministic v1 -> v2 theme migration.

`migrate_v1_to_v2(raw, kind=..., report=...)` returns a new dict shaped like a
v2 document. It is called by `core.theme_schema.normalize_theme` before
validation, so the validator only ever sees v2. It never mutates its input and
never writes to disk.

The tables implemented here are the ones in `docs/theme_schema_v2.md` §7.
Every conversion is deterministic: the same input produces the same output.
"""

from __future__ import annotations

import copy
import logging
import re
from typing import Any, Optional

from core.theme_schema import (
    FREEFORM,
    SCRIPTURE,
    ThemeReport,
    parse_number,
)

logger = logging.getLogger(__name__)

# `#container` CSS fallbacks in display/themes.css. A v1 theme that omits a
# form key rendered with these; carrying them into v2 keeps hand-written
# themes pixel-identical, not just the shipped ones (which set every key).
FORM_CSS_DEFAULTS = {
    "background": "rgba(15, 23, 42, 0.6)",
    "border": "1px solid rgba(255, 255, 255, 0.1)",
    "border_radius": 24,
    "box_shadow": (
        "0 25px 50px -12px rgba(0, 0, 0, 0.5), "
        "0 0 0 1px rgba(255, 255, 255, 0.05) inset"
    ),
    "backdrop_filter": "blur(16px)",
}

PAGE_PADDING_BOTTOM = 80

# A hard shadow: dx dy blur color, `px` suffix optional. Same contract as
# `core.theme_loader.theme_outline`, duplicated here so migration does not
# depend on the loader (which imports this module through the schema).
_HARD_SHADOW_RE = re.compile(
    r"^\s*(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+(-?[\d.]+)(?:px)?\s+"
    r"(#[0-9a-fA-F]{3,6})\s*$")

_V1_ANIMATION_KEYS = ("display_enter", "between_slides", "display_exit")
_ABS_BOX_TYPES = ("text", "reference", "translation", "verse_num")
_BLOCK_KEYS = ("text", "reference", "translation", "verse_num", "title")

_FLEX_START = ("flex-start", "start", "top", "left")
_FLEX_END = ("flex-end", "end", "bottom", "right")


# ─── Small helpers ──────────────────────────────────────────────────────────


def _number(value: Any) -> Optional[float]:
    return parse_number(value)


def _as_dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _has_nested_blocks(containers: dict) -> bool:
    for value in containers.values():
        if not isinstance(value, dict):
            continue
        if isinstance(value.get("text"), dict) or isinstance(value.get("body"), dict):
            return True
    return False


def _hard_shadow_to_outline(shadow: Any) -> Optional[str]:
    """A hand-rolled 8-direction `text_shadow` -> canonical outline string."""
    if not isinstance(shadow, str):
        return None
    text = shadow.strip()
    if not text or text.lower() in ("none", "off"):
        return None
    axis = 0.0
    diagonal = 0.0
    colors = set()
    for part in text.split(","):
        match = _HARD_SHADOW_RE.match(part)
        if not match or float(match.group(3)) != 0:
            return None
        dx, dy = float(match.group(1)), float(match.group(2))
        magnitude = (dx * dx + dy * dy) ** 0.5
        if dy == 0:
            axis = max(axis, abs(dx))
        elif dx == 0:
            axis = max(axis, abs(dy))
        else:
            diagonal = max(diagonal, magnitude)
        colors.add(match.group(4).lower())
    if len(colors) != 1:
        return None
    thickness = axis or diagonal
    if thickness <= 0:
        return None
    color = colors.pop()
    if len(color) == 4:  # #rgb -> #rrggbb
        color = "#" + "".join(ch * 2 for ch in color[1:])
    return f"{max(1, min(25, int(round(thickness))))}px {color}"


def _form_value(container: dict, key: str) -> Any:
    value = container.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        return copy.deepcopy(FORM_CSS_DEFAULTS[key])
    return copy.deepcopy(value)


# ─── Blocks ─────────────────────────────────────────────────────────────────


def _migrate_text(raw: dict, *, report: ThemeReport, path: str) -> dict:
    out = copy.deepcopy(raw)
    out.setdefault("autosize", True)

    outline = out.get("text_outline")
    if isinstance(outline, str) and outline.strip().lower() not in ("", "none", "off"):
        # Explicit outline wins; the shadow stays a shadow.
        return out
    compiled = _hard_shadow_to_outline(out.get("text_shadow"))
    if compiled:
        report.warn(f"{path}.text_shadow",
                    "hard shadow ring migrated to text_outline",
                    out.get("text_shadow"), compiled)
        out["text_outline"] = compiled
        out["text_shadow"] = "none"
    return out


def _migrate_reference(raw: dict) -> dict:
    out = copy.deepcopy(raw)
    out.setdefault("position", "below_verse")
    return out


def _migrate_translation(raw: dict, reference: Optional[dict]) -> dict:
    out = copy.deepcopy(raw)
    out.setdefault("position", "right_of_reference")
    # v1 let the translation span inherit from #verse-ref via CSS. v2 has no
    # cascade, so the inherited typography is written down explicitly. When
    # the theme has no reference block, use the #verse-ref CSS defaults.
    base = reference if isinstance(reference, dict) else {
        "font_family": "'DM Sans', sans-serif",
        "size": 24,
        "weight": 500,
        "line_height": 1.2,
        "letter_spacing": "0.1em",
        "text_transform": "uppercase",
    }
    for key in ("font_family", "size", "weight", "line_height",
                "letter_spacing", "text_transform"):
        if key not in out and key in base:
            out[key] = copy.deepcopy(base[key])
    return out


def _migrate_verse_num(raw: dict) -> dict:
    out = {
        "mode": "inline",
        "size": "0.6em",
        "weight": 700,
        "opacity": 0.7,
        "vertical_align": "top",
        "margin_right": "0.15em",
        "line_height": 1,
    }
    out.update(copy.deepcopy(raw))
    return out


def _migrate_blocks(raw_blocks: dict, *, align: Optional[str], kind: str,
                    path: str, report: ThemeReport) -> dict:
    blocks: dict = {}
    for block_id in _BLOCK_KEYS:
        value = raw_blocks.get(block_id)
        if not isinstance(value, dict):
            continue
        if block_id == "text":
            migrated = _migrate_text(value, report=report, path=f"{path}.text")
        elif block_id == "reference":
            migrated = _migrate_reference(value)
        elif block_id == "translation":
            migrated = _migrate_translation(value, blocks.get("reference"))
        elif block_id == "verse_num":
            migrated = _migrate_verse_num(value)
        else:  # freeform title
            migrated = _migrate_reference(value)
        if align and "text_align" not in migrated:
            migrated["text_align"] = align
            if "text_align" in value and value["text_align"] != align:
                report.warn(f"{path}.{block_id}.text_align",
                            "v1 shrink-wrapped this block; v2 text aligns "
                            "across the container", value["text_align"], None)
        blocks[block_id] = migrated
    return blocks


# ─── Body / flex ────────────────────────────────────────────────────────────


def _valign_from_justify(container: dict, *, path: str,
                         report: ThemeReport) -> str:
    raw = str(container.get("justify_content") or "").strip().lower()
    if not raw:
        return "top"  # #container CSS fallback is flex-start
    if raw in _FLEX_START:
        return "top"
    if raw in _FLEX_END:
        return "bottom"
    if raw == "center":
        return "center"
    report.warn(f"{path}.justify_content", "unsupported flex value", raw, "center")
    return "center"


def _text_align_from_items(container: dict, *, path: str,
                           report: ThemeReport) -> Optional[str]:
    raw = str(container.get("align_items") or "").strip().lower()
    if not raw:
        return None
    if raw in _FLEX_START:
        return "left"
    if raw in _FLEX_END:
        return "right"
    if raw == "center":
        return "center"
    if raw in ("stretch", "baseline"):
        report.warn(f"{path}.align_items",
                    "v1 alignment cannot be expressed per block", raw,
                    "block default")
        return None
    report.warn(f"{path}.align_items", "unsupported flex value", raw,
                "block default")
    return None


def _warn_flex_direction(container: dict, *, path: str,
                         report: ThemeReport) -> None:
    raw = str(container.get("flex_direction") or "").strip().lower()
    if raw in ("row", "row-reverse"):
        # The v2 content stack is always a column.
        report.warn(f"{path}.flex_direction",
                    "v1 row layout cannot be expressed; using a column",
                    raw, "column")


def _migrate_body(container: dict, *, path: str, report: ThemeReport) -> dict:
    raw_body = _as_dict(container.get("body"))
    out: dict = {}
    for key, value in raw_body.items():
        # Page placement, not content inset: consumed by position synthesis.
        if key in ("vertical_align", "padding_bottom"):
            continue
        out[key] = copy.deepcopy(value)
    out["valign"] = _valign_from_justify(container, path=path, report=report)

    padding = _number(container.get("padding"))
    if padding is None:
        padding = 40  # #container CSS fallback
    out["padding"] = padding
    return out


# ─── Position ───────────────────────────────────────────────────────────────


def _synthesized_position(container: dict, *, path: str,
                          report: ThemeReport) -> dict:
    body = _as_dict(container.get("body"))
    pb = _number(body.get("padding_bottom"))
    if pb is None:
        pb = PAGE_PADDING_BOTTOM
    align = str(body.get("vertical_align") or "").strip().lower()
    if align in _FLEX_START:
        anchor, y = "top", 0
    elif align == "center":
        anchor, y = "center", -pb / 2
    else:
        # v1 page CSS fallback is flex-end.
        anchor, y = "bottom", pb
    report.warn(path, "position synthesized from v1 page flex", align or "absent",
                f"{anchor} y={y}")
    return {"anchor": anchor, "x": 0, "y": y}


def _migrate_position(container: dict, *, path: str,
                      report: ThemeReport) -> dict:
    x = _number(container.get("x"))
    y = _number(container.get("y"))
    if x is not None and y is not None:
        return {"anchor": "top_left", "x": x, "y": y}
    return _synthesized_position(container, path=path, report=report)


# ─── Animations ─────────────────────────────────────────────────────────────


def _take_v1_animations(data: dict) -> Optional[dict]:
    raw = data.get("animations")
    if not isinstance(raw, dict):
        return None
    if not any(key in raw for key in _V1_ANIMATION_KEYS):
        return None  # already a v2 definition library
    data.pop("animations", None)
    return raw


def _v1_slot(section: dict, type_key: str, default_duration: float,
             default_easing: str) -> Optional[dict]:
    typ = section.get(type_key)
    if not isinstance(typ, str):
        return None
    typ = typ.strip()
    if not typ or typ.lower() == "none":
        return None
    duration = _number(section.get("duration_ms"))
    slot = {
        "use": typ,
        "duration_ms": int(round(duration)) if duration is not None
        else int(default_duration),
        "easing": section.get("easing") or default_easing,
    }
    return slot


def _build_v1_animation(raw: Optional[dict]) -> Optional[dict]:
    if not raw:
        return None
    animation: dict = {}
    enter = _v1_slot(_as_dict(raw.get("display_enter")), "type", 600, "ease-out")
    if enter:
        animation["entry"] = enter
    transition = _v1_slot(_as_dict(raw.get("between_slides")), "in_type",
                          600, "ease-out")
    if transition:
        animation["transition"] = {"in": transition}
    exit_slot = _v1_slot(_as_dict(raw.get("display_exit")), "type", 400,
                         "ease-out")
    if exit_slot:
        animation["out"] = exit_slot
    return animation or None


# ─── Containers ─────────────────────────────────────────────────────────────


def _container_shell(cid: str, index: int) -> dict:
    return {
        "id": cid,
        "layer": index * 10,
        "visible": True,
    }


def _apply_form(out: dict, source: dict) -> None:
    out["background"] = _form_value(source, "background")
    out["border"] = _form_value(source, "border")
    out["border_radius"] = _form_value(source, "border_radius")
    out["box_shadow"] = _form_value(source, "box_shadow")
    out["backdrop_filter"] = _form_value(source, "backdrop_filter")
    if "width" in source and source.get("width") is not None:
        out["width"] = source["width"]
    else:
        out["width"] = "auto"
    if "height" in source and source.get("height") is not None:
        out["height"] = source["height"]
    if "min_width" in source and source.get("min_width") is not None:
        out["min_width"] = source["min_width"]
    else:
        out["min_width"] = "60%"
    if "max_width" in source and source.get("max_width") is not None:
        out["max_width"] = source["max_width"]
    else:
        out["max_width"] = "80%"
    out["min_height"] = 0
    out["max_height"] = None


def _migrate_nested_container(cid: str, container: dict, index: int, *,
                              path: str, report: ThemeReport) -> dict:
    out = _container_shell(cid, index)
    out["position"] = _migrate_position(container, path=path, report=report)
    _apply_form(out, container)
    _warn_flex_direction(container, path=path, report=report)
    out["blocks"] = _migrate_blocks(
        container, align=_text_align_from_items(container, path=path, report=report),
        kind=SCRIPTURE, path=path, report=report)
    out["blocks"]["body"] = _migrate_body(container, path=path, report=report)
    return out


def _flat_blocks(data: dict) -> dict:
    return {key: data[key] for key in _BLOCK_KEYS
            if isinstance(data.get(key), dict)}


def _migrate_flat(data: dict, *, path: str, report: ThemeReport) -> dict:
    """`{text:{...}, reference:{...}, container:{...}}` -> one container."""
    form = _as_dict(data.get("container"))
    out = _container_shell("main", 0)
    out["position"] = {"anchor": "center", "x": 0, "y": 0}
    _apply_form(out, form)
    _warn_flex_direction(form, path="container", report=report)

    body: dict = {}
    raw_body = _as_dict(data.get("body"))
    for key, value in raw_body.items():
        if key in ("vertical_align", "padding_bottom"):
            continue
        body[key] = copy.deepcopy(value)
    padding = _number(form.get("padding"))
    body["padding"] = 40 if padding is None else padding
    body["valign"] = _valign_from_justify(form, path=path, report=report)

    out["blocks"] = _migrate_blocks(
        _flat_blocks(data),
        align=_text_align_from_items(form, path=path, report=report),
        kind=SCRIPTURE, path=path, report=report)
    out["blocks"]["body"] = body
    return out


def _migrate_absolute_boxes(containers: dict, *, report: ThemeReport) -> list:
    """Oldest shape: one centered box per block, x/y are box centers."""
    migrated: list = []
    for index, (cid, box) in enumerate(
            (k, v) for k, v in containers.items() if isinstance(v, dict)):
        path = f"containers.{cid}"
        out = _container_shell(str(cid), index)
        width = _number(box.get("width")) or 0.0
        height = _number(box.get("height")) or 0.0
        x = _number(box.get("x")) or 0.0
        y = _number(box.get("y")) or 0.0
        out["position"] = {
            "anchor": "top_left",
            "x": x - width / 2,
            "y": y - height / 2,
        }
        _apply_form(out, box)
        if width:
            out["width"] = width
        if height:
            out["height"] = height
        block = copy.deepcopy(box)
        for form_key in ("x", "y", "width", "height", "follows", "visible"):
            block.pop(form_key, None)
        if cid == "reference":
            block.setdefault("size", 34)
            block.setdefault("font_family", "'DM Sans', sans-serif")
            block.setdefault("weight", 500)
            block.setdefault("text_transform", "uppercase")
        elif cid == "translation":
            block.setdefault("size", 16)
        body = _migrate_body(box, path=path, report=report)
        # The oldest shape hardcoded a 20px inset around every box.
        body["padding"] = 20
        blocks = _migrate_blocks({cid: block}, align=None, kind=SCRIPTURE,
                                 path=path, report=report)
        blocks["body"] = body
        out["blocks"] = blocks
        migrated.append(out)
        report.warn(path, "legacy centered box migrated", (x, y),
                    (x - width / 2, y - height / 2))
    return migrated


def _migrate_containers(data: dict, *, kind: str, report: ThemeReport,
                        animation: Optional[dict]) -> list:
    containers = data.get("containers")

    if isinstance(containers, list):
        # A v1-versioned file already using the array shape: trust the order,
        # fill identity, leave the rest to the validator.
        migrated = []
        for index, container in enumerate(containers):
            if not isinstance(container, dict):
                report.warn(f"containers[{index}]", "container is not an object",
                            type(container).__name__, "dropped")
                continue
            out = copy.deepcopy(container)
            out.setdefault("id", f"container{index}")
            out.setdefault("layer", index * 10)
            out.setdefault("visible", True)
            migrated.append(out)
        if migrated:
            return migrated

    if isinstance(containers, dict) and containers:
        if _has_nested_blocks(containers):
            migrated = []
            for index, (cid, container) in enumerate(containers.items()):
                if not isinstance(container, dict):
                    report.warn(f"containers.{cid}", "container is not an object",
                                type(container).__name__, "dropped")
                    continue
                migrated.append(_migrate_nested_container(
                    str(cid), container, index,
                    path=f"containers.{cid}", report=report))
            return migrated
        return _migrate_absolute_boxes(containers, report=report)

    if any(isinstance(data.get(key), dict) for key in _BLOCK_KEYS):
        return [_migrate_flat(data, path="container", report=report)]

    report.warn("containers", "v1 theme has no containers", None, "main")
    return [_migrate_nested_container("main", {}, 0, path="containers.main",
                                     report=report)]


# ─── Freeform title ─────────────────────────────────────────────────────────


def _apply_freeform_title(data: dict, containers: list,
                          report: ThemeReport) -> None:
    slide = data.get("slide")
    if not isinstance(slide, dict) or "show_title" not in slide:
        return
    visible = slide.get("show_title")
    if not isinstance(visible, bool):
        return
    for container in containers:
        blocks = container.get("blocks")
        if isinstance(blocks, dict) and isinstance(blocks.get("title"), dict):
            blocks["title"]["visible"] = visible
            return


# ─── Entry point ────────────────────────────────────────────────────────────


def migrate_v1_to_v2(raw: Any, *, kind: str = SCRIPTURE,
                     report: Optional[ThemeReport] = None) -> dict:
    """Migrate a v1 theme document into the v2 shape (unvalidated)."""
    if report is None:
        report = ThemeReport()
    if not isinstance(raw, dict):
        report.warn("", "v1 theme root is not an object", type(raw).__name__, "{}")
        raw = {}
    if kind not in (SCRIPTURE, FREEFORM):
        kind = SCRIPTURE

    data = copy.deepcopy(raw)
    version = data.get("schema_version")
    if version is not None:
        report.warn("schema_version", "migrating a v1 theme", version, 2)
    data["schema_version"] = 2
    data["kind"] = kind
    data.setdefault("canvas", {
        "width": 1920,
        "height": 1080,
        "background": "transparent",
        "fit": "none",  # v1 had no canvas: keep raw 1:1 pixel behavior
    })

    animation = _build_v1_animation(_take_v1_animations(data))
    containers = _migrate_containers(data, kind=kind, report=report,
                                     animation=animation)
    data["containers"] = containers

    if animation and containers:
        containers[0]["animation"] = animation

    _apply_freeform_title(data, containers, report)
    return data
