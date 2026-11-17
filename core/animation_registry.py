"""Animation parameter registry — the single source of truth.

Every animation type declares its parameters here: type, label, default,
bounds, step, unit, enum options, visibility rules, grouping and whether the
parameter is advanced. ``core.theme_schema`` validates with these definitions
and the Theme Designer's :class:`ParamForm` builds its controls from them, so
adding a parameter is a one-file change.

The animation *instances* (a theme's ``animations`` map and
``themes/_shared/animations.json``) stay data: operators reconfigure values,
they do not define new parameter shapes.

The Display renderer gets its fallback defaults from :func:`runtime_defaults`;
``display/animation_defaults.js`` is generated from it and a test fails if the
checked-in file drifts.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from core.constants import OVERLAP_IN_OFFSET_MS

__all__ = [
    "ANIMATION_EASINGS", "ANIMATION_SPECS", "ANIMATION_TYPES",
    "AnimationSpec", "ORIGIN_VALUES", "PRESET_TYPES", "ParamOption",
    "ParamSpec", "SLOT_PARAMS", "cursor_defaults", "default_definition",
    "default_definitions", "js_constants", "param_for", "runtime_defaults",
    "runtime_defaults_js", "spec_for",
]


# ─── value types ────────────────────────────────────────────────────────────

PARAM_TYPES = (
    "number", "enum", "bool", "color", "easing", "angle", "length",
    "text", "keyframes",
)


@dataclass(frozen=True)
class ParamOption:
    value: str
    label: str


@dataclass(frozen=True)
class ParamSpec:
    key: str
    label: str
    type: str
    default: Any = None
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    step: Optional[float] = None
    unit: str = ""
    options: tuple[ParamOption, ...] = ()
    help: str = ""
    visible_if: Optional[dict] = None
    group: str = ""
    advanced: bool = False
    max_length: Optional[int] = None

    def __post_init__(self) -> None:
        if self.type not in PARAM_TYPES:
            raise ValueError(f"param {self.key}: unknown type {self.type!r}")
        if self.type == "enum" and not self.options:
            raise ValueError(f"param {self.key}: enum needs options")
        if self.type in ("number", "angle", "length"):
            if self.minimum is not None and self.maximum is not None:
                if self.minimum > self.maximum:
                    raise ValueError(
                        f"param {self.key}: min {self.minimum} > max {self.maximum}")
            if self.default is not None and self.minimum is not None:
                if float(self.default) < float(self.minimum):
                    raise ValueError(f"param {self.key}: default below min")
            if self.default is not None and self.maximum is not None:
                if float(self.default) > float(self.maximum):
                    raise ValueError(f"param {self.key}: default above max")

    @property
    def option_values(self) -> tuple[str, ...]:
        return tuple(option.value for option in self.options)


@dataclass(frozen=True)
class AnimationSpec:
    type: str
    label: str
    category: str
    help: str
    params: tuple[ParamSpec, ...]
    keyframes: tuple[dict, ...] = ()

    def param(self, key: str) -> ParamSpec:
        for spec in self.params:
            if spec.key == key:
                return spec
        raise KeyError(f"animation {self.type!r} has no parameter {key!r}")

    def params_in_group(self, group: str) -> tuple[ParamSpec, ...]:
        return tuple(p for p in self.params if p.group == group)


# ─── shared enums ───────────────────────────────────────────────────────────

ANIMATION_EASINGS = (
    "ease-out", "ease-in", "ease-in-out", "linear", "spring", "smooth",
)

ORIGIN_VALUES = (
    "center", "top", "bottom", "left", "right",
    "top left", "top right", "bottom left", "bottom right",
)

_EASING_OPTIONS = tuple(
    ParamOption(value, value.replace("-", " ").title())
    for value in ANIMATION_EASINGS
)
_ORIGIN_OPTIONS = tuple(
    ParamOption(value, value.replace(" ", " ").title())
    for value in ORIGIN_VALUES
)


# ─── parameter builders ─────────────────────────────────────────────────────

def _duration(default: float, *, group: str = "") -> ParamSpec:
    return ParamSpec(
        "duration_ms", "Duration", "number", default, 0, 5000, 50, "ms",
        help="How long the animation runs. 0 = instant.", group=group)


def _delay(*, group: str = "") -> ParamSpec:
    return ParamSpec(
        "delay_ms", "Delay", "number", 0, 0, 5000, 50, "ms",
        help="Wait before the animation starts.", group=group)


def _easing(default: str, *, group: str = "") -> ParamSpec:
    return ParamSpec(
        "easing", "Easing", "easing", default,
        options=_EASING_OPTIONS, help="Curve of the motion.", group=group)


def _origin(*, group: str = "") -> ParamSpec:
    return ParamSpec(
        "origin", "Origin", "enum", "center", options=_ORIGIN_OPTIONS,
        help="Transform origin for scale and rotation.", group=group)


# ─── preset keyframes (renderer data, not ranges) ───────────────────────────

_PRESET_KEYFRAMES: dict[str, tuple[dict, ...]] = {
    "fade_in": ({"at": 0, "opacity": 0}, {"at": 100, "opacity": "base"}),
    "fade_out": ({"at": 0, "opacity": "base"}, {"at": 100, "opacity": 0}),
    "fade_up": (
        {"at": 0, "opacity": 0, "translate_y": 20},
        {"at": 100, "opacity": "base", "translate_y": 0},
    ),
    "fade_down": (
        {"at": 0, "opacity": "base", "translate_y": 0},
        {"at": 100, "opacity": 0, "translate_y": 20},
    ),
    "scale_up": (
        {"at": 0, "opacity": 0, "scale": 0.85},
        {"at": 100, "opacity": "base", "scale": 1},
    ),
    "scale_down": (
        {"at": 0, "opacity": "base", "scale": 1},
        {"at": 100, "opacity": 0, "scale": 0.85},
    ),
    "slide_up": (
        {"at": 0, "translate_y": "100%"}, {"at": 100, "translate_y": 0},
    ),
    "slide_down": (
        {"at": 0, "translate_y": 0}, {"at": 100, "translate_y": "100%"},
    ),
}

_PRESET_HELP = {
    "fade_in": "Fade the block in.",
    "fade_out": "Fade the block out.",
    "fade_up": "Fade in while rising into place.",
    "fade_down": "Fade out while dropping away.",
    "scale_up": "Fade in while growing.",
    "scale_down": "Fade out while shrinking.",
    "slide_up": "Slide up into place.",
    "slide_down": "Slide down out of place.",
}

_CURSOR_DEFAULTS = {
    "char": "\u258c", "color": "currentColor",
    "blink_ms": 500, "hide_after_ms": 600,
}


def _cursor_visible() -> dict:
    return {"key": "cursor.enabled", "equals": True}


def _typewriter_params() -> tuple[ParamSpec, ...]:
    return (
        _duration(900),
        _delay(),
        _easing("linear"),
        ParamSpec(
            "reveal", "Reveal", "enum", "char",
            options=(ParamOption("char", "Character"),
                     ParamOption("word", "Word")),
            help="Reveal one character or one word at a time."),
        ParamSpec("cursor.enabled", "Cursor", "bool", True, group="Cursor",
                  help="Show a caret while typing."),
        ParamSpec("cursor.char", "Character", "text", "\u258c",
                  visible_if=_cursor_visible(), group="Cursor",
                  max_length=2, help="Glyph used as the caret."),
        ParamSpec("cursor.color", "Color", "color", "currentColor",
                  visible_if=_cursor_visible(), group="Cursor",
                  help="Caret colour; currentColor follows the text."),
        ParamSpec("cursor.blink_ms", "Blink", "number", 500, 0, 2000, 50,
                  "ms", visible_if=_cursor_visible(), group="Cursor",
                  help="Blink period; 0 = steady."),
        ParamSpec("cursor.hide_after_ms", "Hide after", "number", 600, 0,
                  5000, 50, "ms", visible_if=_cursor_visible(), group="Cursor",
                  help="Keep the caret visible after typing ends."),
    )


def _custom_params() -> tuple[ParamSpec, ...]:
    return (
        _duration(600),
        _delay(),
        _easing("ease-out"),
        _origin(),
        ParamSpec(
            "keyframes", "Keyframes", "keyframes", (),
            advanced=True,
            help="Edited on the timeline (Stage 3)."),
    )


# ─── the registry ───────────────────────────────────────────────────────────

ANIMATION_SPECS: dict[str, AnimationSpec] = {}


def _add(spec: AnimationSpec) -> None:
    if spec.type in ANIMATION_SPECS:
        raise ValueError(f"duplicate animation type {spec.type!r}")
    ANIMATION_SPECS[spec.type] = spec


for _type, _frames in _PRESET_KEYFRAMES.items():
    _add(AnimationSpec(
        _type, _type.replace("_", " ").title(), "preset",
        _PRESET_HELP[_type],
        (_duration(600), _delay(), _easing("ease-out"), _origin()),
        _frames,
    ))

_add(AnimationSpec(
    "typewriter", "Typewriter", "typewriter",
    "Reveal the text character by character, with an optional caret.",
    _typewriter_params(),
))

_add(AnimationSpec(
    "custom", "Custom", "custom",
    "Author your own keyframes.",
    _custom_params(),
))

ANIMATION_TYPES = tuple(ANIMATION_SPECS)
PRESET_TYPES = tuple(
    name for name, spec in ANIMATION_SPECS.items() if spec.category == "preset")

#: Overrides a slot may carry on top of `{"use": name}`.
SLOT_PARAMS = {
    "duration_ms": _duration(600),
    "delay_ms": _delay(),
    "easing": _easing("ease-out"),
}


def spec_for(animation_type: str) -> AnimationSpec:
    try:
        return ANIMATION_SPECS[str(animation_type)]
    except KeyError as exc:
        raise KeyError(f"unknown animation type {animation_type!r}") from exc


def param_for(animation_type: str, key: str) -> ParamSpec:
    return spec_for(animation_type).param(key)


def cursor_defaults() -> dict:
    return dict(_CURSOR_DEFAULTS)


def default_definition(animation_type: str) -> dict:
    """The definition the schema's built-in library ships for a type."""
    spec = spec_for(animation_type)
    out: dict = {
        "type": spec.type,
        "label": spec.label,
        "duration_ms": spec.param("duration_ms").default,
        "delay_ms": spec.param("delay_ms").default,
        "easing": spec.param("easing").default,
    }
    if spec.category == "preset":
        # A preset is defined by its type: author keyframes are rejected by
        # the validator, so they are only added by default_definitions().
        out["origin"] = spec.param("origin").default
    elif spec.category == "typewriter":
        out["reveal"] = spec.param("reveal").default
        out["cursor"] = cursor_defaults()
    else:
        out["origin"] = spec.param("origin").default
        out["keyframes"] = [
            {"at": 0, "opacity": 0},
            {"at": 100, "opacity": "base"},
        ]
    return out


def default_definitions() -> dict:
    """The built-in library: presets plus typewriter (not `custom`)."""
    out = {}
    for name, spec in ANIMATION_SPECS.items():
        if spec.category == "custom":
            continue
        entry = default_definition(name)
        if spec.category == "preset":
            entry["keyframes"] = copy.deepcopy(list(spec.keyframes))
        out[name] = entry
    return out


# ─── runtime (Display renderer) ─────────────────────────────────────────────

def runtime_defaults() -> dict:
    """Fallback values the Display uses when a field is missing.

    A resolved theme always carries these fields; the renderer only needs them
    for raw v1 payloads and defensive reads.
    """
    return {
        "duration_ms": ANIMATION_SPECS["fade_in"].param("duration_ms").default,
        "typewriter_duration_ms":
            ANIMATION_SPECS["typewriter"].param("duration_ms").default,
        "overlap_in_offset_ms": OVERLAP_IN_OFFSET_MS,
        "delay_ms": 0,
        "easing": "ease-out",
        "typewriter_easing": "linear",
        "cursor": cursor_defaults(),
        "easings": list(ANIMATION_EASINGS),
        "types": list(ANIMATION_TYPES),
    }


def _js_json() -> str:
    return json.dumps(runtime_defaults(), ensure_ascii=False,
                      separators=(",", ":"))


def js_constants() -> str:
    """The generated `animation_defaults.js` body."""
    return (
        "// GENERATED by core/animation_registry.py — do not edit by hand.\n"
        "// Regenerate with: python -c \"from core.animation_registry import "
        "js_constants; open('display/animation_defaults.js','w').write("
        "js_constants())\"\n"
        f"const RC_ANIM_DEFAULTS = {_js_json()};\n"
    )


def runtime_defaults_js() -> str:
    """A script body that defines the same object on `window`."""
    return f"window.RC_ANIM_DEFAULTS = {_js_json()};"
