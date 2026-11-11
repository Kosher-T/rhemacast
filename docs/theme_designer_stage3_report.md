# Theme Designer — Stage 3: phase cards with embedded editors

## Scope

Stage 3 edits the four animation slots of the first v2 container through the
existing `AnimationPhaseCard`. Each card hosts a registry-driven editor below
its built-in rows:

- inline slot definition → `ParamForm` edits the slot object in place;
- named theme definition (`entry: "gold"` or `{"use": "gold", ...}`) →
  `ParamForm` edits `theme["animations"]["gold"]`, preserving keys the registry
  does not know;
- shared/built-in definition → read-only note with a **Copy into theme**
  action that writes the definition into `theme["animations"]` and keeps the
  slot (including its overrides);
- `type == "custom"` → a `Timeline` edits the definition's `keyframes`.

No per-animation UI code exists: types, controls, ranges, easing presets,
origin options and default labels come from `core/animation_registry.py`.
The card's duration/delay/easing/origin rows are configured from
`SLOT_PARAMS` and `ANIMATION_EASINGS` / `ORIGIN_VALUES`. The embedded form
excludes the rows the card already owns (`duration_ms`, `delay_ms`, `easing`,
`origin`) and keyframes; a custom definition therefore shows the Timeline and
no duplicate timing grid.

## Files

- `ui/widgets/theme_designer/animation_panel.py` — `AnimationPanel` (four
  cards, document read/write, `theme_changed(dict)`).
- `ui/theme_kit/animation_phase.py` — `set_editor_widget()` /
  `editor_widget()` insertion point, header/label-width fixes, cursor-row
  visibility.
- `ui/widgets/theme_designer/param_form.py` — `set_value(..., emit=True)` and
  `exclude=` for host-owned parameters.
- `ui/theme_kit/chip_select.py`, `ui/theme_kit/property_row.py`,
  `ui/theme_kit/timeline.py` — label/chip measurement and reset-glyph fixes
  found on the real display.
- `ui/tabs/theme_designer_tab.py` — replaces the v1 animations panel; loads the
  working theme on theme open/import/JSON apply and routes panel edits to the
  previews and JSON view.
- `tests/test_theme_designer_stage3.py` — 11 offscreen tests.

## Behaviour notes

- Slot grammar is normalized on write: `none` removes the key, an empty
  `transition` object is dropped, and unrelated animation keys are untouched.
- Unknown top-level theme keys and unknown definition keys survive edits.
- Switching a slot rebuilds only that card's editor; the built-in rows keep
  handling overrides for named entries.
- A copied preset has no unique registry parameters, so after the copy the card
  shows a short “Stored in theme animations; the rows above edit this slot.”
  note instead of an empty form. Typewriter/custom copies gain the reveal,
  cursor or Timeline editors.
- Read-only built-in names keep their typewriter/cursor block visible only when
  it has editable fields; empty Char/Color/Blink/Hide rows are not drawn.

## Real-display check

Run at 1400×900 with `DISPLAY=:1 QT_QPA_PLATFORM=xcb`, the left column forced
to 240 px and the animation column at its real 300 px (286 px viewport, 270 px
card); the panel was also mounted standalone at 240 px (210 px card).
`default_typewriter` and `reference_frames` (entry/out use custom definitions
with keyframes) were loaded, all four cards expanded, and every slot kind
switched repeatedly. Frames were inspected before fixing.

Defects found and fixed:

1. **No copy action.** The read-only note told the operator to copy the
   animation but offered nothing. Added `Copy into theme`, which deep-copies
   the definition, preserves slot overrides, creates `animations` when absent,
   and immediately rebuilds the editor.
2. **Duplicate parameter rows.** The embedded form repeated Duration, Delay,
   Easing and Origin below the card's own rows (and exposed an Advanced toggle
   that only hid keyframes help). `ParamForm(exclude=...)` plus
   `CARD_OWNED_PARAMS` removes them; no empty form is created.
3. **Empty labelled rows.** A read-only typewriter showed Char, Color, Blink
   and Hide labels above blank controls. The rows now hide with their controls.
4. **Clipped text at 240 px.** “Transition in” elided in the card header
   (title now gets 62% before the chip/bar), “Duration” was overlapped by the
   reset glyph (`PropertyRow` now hides the glyph initially and reserves its
   width), reveal/cursor chips elided “Default”/“Word” (chip hints now use the
   painted weight and 22 px padding), and nullable keyframe fields clipped
   “Not set” (Timeline uses “Unset”).
5. **Kit sizing.** `AnimationPhaseCard` label column widened to 84 px so
   changed/override rows keep their full label beside the reset glyph.

Checks that passed on the real display:

- all four cards expanded at 300 px and 240 px: no horizontal scrollbar, no
  overlapping rows, no clipped visible label/chip after the fixes;
- builtin → theme → inline → custom → theme → builtin → inline switches:
  at most one visible form/Timeline per card, no stale widget left painted;
- Timeline at 240 px: Add button, drag of the middle marker (32.5 → 46.6) and
  Remove button with real mouse events; the injected unknown keyframe key
  survived add/move/delete in both the card document and the emitted theme;
- edits appeared in the JSON view; JSON Apply reloaded the cards, kept an
  unknown top-level key and the applied `entry` value;
- `Copy into theme` moved `fade_up` into `animations` on the real tab.

## Verification

## Verification

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_stage3.py -q          # 11 passed
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme*.py tests/test_animation_registry.py tests/test_display_js.py -q
# 562 passed
```

Windows was not available, so identical Windows/Linux rendering of the panel
was not checked. The panel uses only the Stage 1 Qt widgets and registry
metadata, is scrollable at 240 px, and has no native dialogs or network use.
The temporary real-display harness and screenshots were removed after the
check.
