# Animation parameter registry

## Findings (before the build)

- **Definitions** lived in `core/theme_schema.py`: `BUILTIN_ANIMATIONS`, built
  by `_builtin_definitions()`/`_preset_keyframes()`. Instances live in a
  theme's `animations` map and `themes/_shared/animations.json`.
- **Slots** (`entry`, `out`, `transition.out/in`) hold a name, a name plus
  overrides, or an inline definition; `_normalize_slot` repeated the same
  duration/delay/easing bounds as the definition validator.
- **Ranges/enums** were duplicated: duration (0–5000, default 600/900), delay
  (0–5000), easing list, origin list, keyframe rules (2–8, 0–100), typewriter
  reveal and cursor bounds/defaults — plus cursor defaults in three branches.
- **Renderer**: `display/display.js` and the inline copy in
  `ui/widgets/display_view.py` both hardcoded `600`/`900`, their own easing
  fallback and cursor fallbacks.
- **UI**: `ThemeAnimationsPanel` is a v1 slot editor with its own type lists
  and easings. The kit already covers every parameter type (`NumberField`,
  `ChipSelect`, `CompactDropdown`, `Switch`, `ColorField`, `EasingPicker`,
  `TextInput`); only keyframes are deliberately left to the Stage 3 timeline.

**Format: Python dataclasses** in `core/animation_registry.py`. The people who
add an animation are developers: a new type also needs renderer semantics, so a
typed, importable module gives one load path and import-time errors instead of
a JSON file plus a second validation layer. Operators still reconfigure
instances in theme JSON. Tradeoff: adding a type is a code change, not a data
edit — which matches what it actually requires.

## What reads the registry

| Consumer | Uses |
|---|---|
| `core/theme_schema.py` | `ANIMATION_TYPES`, `PRESET_TYPES`, easing/origin enums, per-parameter defaults and bounds (definitions and slot overrides), cursor defaults, preset keyframes (`BUILTIN_ANIMATIONS` is generated) |
| `ui/widgets/theme_designer/param_form.py` | `ParamForm` builds controls, labels, help, groups, `visible_if`, advanced rows |
| `display/animation_defaults.js` | generated `RC_ANIM_DEFAULTS` (durations, easing names, cursor defaults) |
| `display/display.js`, `ui/widgets/display_view.py` | read `RC_ANIM_DEFAULTS` instead of literal fallbacks |
| `ui/widgets/theme_animations_panel.py` | type lists and default durations derived from the registry |

`themes/_shared/animations.json` and theme `animations` maps remain data (the
instances). They are not definitions.

## Add an animation

1. Add keyframes to `_PRESET_KEYFRAMES` (or a new `AnimationSpec` below it).
2. Give it params. Shared builders: `_duration`, `_delay`, `_easing`, `_origin`.
   Every `ParamSpec` requires `key`, `label`, `type`, `default`; optional
   `minimum`, `maximum`, `step`, `unit`, `options`, `help`, `visible_if`
   (`{"key": ..., "equals": ...}`), `group`, `advanced`, `max_length`.
3. Run the tests — `tests/test_animation_registry.py` proves every default
   validates, every bound clamps and the generated JS is current.
4. Regenerate the renderer defaults:
   `python -c "from core.animation_registry import js_constants; open('display/animation_defaults.js','w').write(js_constants())"`

The validator and `ParamForm` pick it up with no UI edit. The Designer can
offer it as soon as the animation appears in a theme's library.

### Worked example

```python
# core/animation_registry.py
_PRESET_KEYFRAMES["blur_in"] = (
    {"at": 0, "opacity": 0, "blur": 6},
    {"at": 100, "opacity": "base", "blur": 0},
)
```

That is enough for validation, the slot grammar and `ParamForm` (duration,
delay, easing, origin). If it needs its own knob, add a `ParamSpec`:

```python
ParamSpec("tint", "Tint", "color", "currentColor",
          help="Colour the block briefly while it resolves."),
```

A typewriter-style knob that only applies in one mode uses `visible_if`:

```python
ParamSpec("cursor.blink_ms", "Blink", "number", 500, 0, 2000, 50, "ms",
          visible_if={"key": "cursor.enabled", "equals": True},
          group="Cursor"),
```

Nested keys use a dot (`cursor.char`); `ParamForm` reads and writes the nested
schema shape and leaves `cursor: "none"` when the cursor is disabled.

## Reconfigure an animation (no code)

Edit the instance in the Designer (Stage 3 phase cards embed `ParamForm`) or in
the theme's `animations` entry. Unknown keys are preserved. Values outside the
registry bounds are clamped by `normalize_theme`; the Designer shows the
validator's message.

## UI consumers

`ui/widgets/theme_designer/animation_panel.py` builds one `ParamForm`
per animated phase from the registry spec, and derives the phase card's
duration/delay ranges, easing presets, origin options and inline types
from `SLOT_PARAMS`, `ANIMATION_EASINGS`, `ORIGIN_VALUES` and
`INLINE_TYPES`. The `custom` type also hosts a `Timeline` for keyframes.
The form is created with `exclude=("duration_ms", "delay_ms", "easing",
"origin", "keyframes")` because the phase card already edits those; a registry
parameter outside that set surfaces in the Designer with no UI edit. A
shared/built-in definition is read-only until `Copy into theme` writes it into
`theme["animations"]`.

## Not verified

- Windows rendering (no Windows machine).
- The v2 Designer animation panel has been reviewed on Linux/X11 at 300 px and
  240 px; Windows was not available.
