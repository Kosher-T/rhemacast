# Per-element animation in the Theme Designer

## Decisions for you

1. **Selection drives both directions.** The left Blocks tab selects the
   panel target; the panel's Edit dropdown selects the left block. A block
   chosen on either side is one selection, not two.
2. **Verse number is explained, not offered.** The renderer never reads
   `verse_num.animation`, so the panel shows a one-line reason and no phase
   cards. It stays in the target list so the left tab can be represented.
3. **Split editing moves into the Animations panel** for text, reference,
   title and translation. Body and container splits are schema-legal but
   produce no units, so the panel offers a note instead of dead controls.
4. **No schema_version bump for Part 3.** Property tracks are an optional
   `animation.properties` object. Old renderers ignore it and render the
   theme without the effect; only the normalizer must learn the key.
5. **Border and shadow stay parts of the container**, not new top-level
   blocks. They get their own targets inside the Animation panel once
   property tracks exist, addressed as `containers[i].animation.properties`.

## Safe to skip

Renaming blocks, adding a second animation document, moving SplitEditor off
the Blocks page, and animating verse number. None is needed for the owner's
request, and the first two would split the single selection model again.

## Part 1: what the code actually does

### The facts, checked

| Claim | Verdict |
| --- | --- |
| Animation assignments exist at container and block level, with entry, sustain, out, transition in/out and split | **True.** `normalize_animation_assignment` accepts exactly those keys; `SPLIT_BLOCKS` lists text, reference, title and translation. |
| Shipped themes use block slots and the renderer plays them | **True.** `_animationTargets` collects container, body, text, reference and translation assignments and `_runAnimation` plays them. |
| The panel edits only `containers[0]` and four phases; containers 1 and up have no editing | **Partly stale.** The panel already followed container selection through `set_container`, and its Edit dropdown already targeted every block. It did not follow the left Blocks tab, it offered verse number, and it had no split controls. The 57 "uneditable" slots came from a static audit rule that only credited container 0 and the Blocks-page split editor, not from the panel's real reach. |
| Keyframes only carry opacity, translate_x, translate_y, scale, rotate and blur | **True.** No colour, border, shadow, background or filter channel exists; `docs/theme_effect_matrix.json` records the same gap. |
| One selection model, one ThemeDocument, path edits only | **True.** The tab owns `_selected_container_id` and the document. The property editor had only `container_selected`; block selection was local to its own tab bar. |
| A per-object animation research report exists | **No.** The closest documents are `docs/animation_registry.md` (animation definitions and parameters) and `docs/theme_effect_matrix.json` (per-property reachability). |

### Phases the renderer plays, per element

| Element | entry | sustain | transition in | transition out | out | split |
| --- | --- | --- | --- | --- | --- | --- |
| Container | yes | yes | yes | yes | yes | no |
| Body | yes | yes | yes | yes | yes | no |
| Text | yes | yes | yes | yes | yes | entry and transition in |
| Reference (scripture) | yes | yes | yes | yes | yes | entry and transition in |
| Title (freeform, aliased to reference) | yes | yes | yes | yes | yes | entry and transition in |
| Translation | yes | yes | yes | yes | yes | entry and transition in |
| Verse number | no | no | no | no | no | no |

Two relevance rules sit behind the table:

- Container and body transitions fire on any content change (`changed.any`).
- Text, reference and translation transitions fire only when that block's
  text changed (`changed[kind]`), so a reference edit does not re-animate
  the verse body.
- Split is laid out only for text, reference and translation in
  `_layoutSplitUnits`. The schema accepts split on containers, body and
  title; the renderer never builds units for the first two.

Sustain loops with `iterations: Infinity` while shown and honours
`motion.sustain_when_cloaked`. It is already in the panel and in the schema,
so the panel offers it for every animatable element.

### How selection should work

The tab keeps one selection. A block selection is a second coordinate of the
same selection, not a separate model:

- `ThemePropertyEditor` emits `block_selected` when its Blocks tab changes.
- `ThemeDesignerTab` sends that to `AnimationPanel.set_block`.
- `AnimationPanel` emits `block_selected` when its Edit dropdown changes;
  the tab sends that to `ThemePropertyEditor.set_selected_block`, which
  switches the left page to Blocks.
- Container selection keeps its existing path: tab, property editor,
  workspace and animation panel all follow one id.

Border and shadow live on the Container page because they are container
properties, not renderer blocks. The clean way to make them selectable is to
add them as **targets inside the Animation panel**, not as new entries in the
Blocks list:

```
Target: [Container] [Border] [Shadow] [Body] [Text] [Reference] [Translation]
```

Each target maps to a path on the container (`containers[i].border`,
`containers[i].box_shadow`) and later to a property track under
`containers[i].animation.properties`. They stay part of the container element,
so the single document and the existing Container page remain the source of
truth for their static values.

## Part 2: what was built

### Changes

- `ui/widgets/theme_designer/animation_panel.py`
  - `set_block` and a `block_selected` request signal.
  - Target list filtered to nothing (it still lists verse number so the left
    tab is representable), but verse number now renders a reason note and no
    phase cards.
  - Split section with `SplitEditor` for text, reference, title and
    translation; a note for container and body. Writes go to
    `containers[i].blocks.<block>.animation.split` and preserve unknown split
    keys.
  - Five phase cards for every supported element (entry, sustain, transition
    in, transition out, out).
- `ui/widgets/theme_designer/property_editor.py`
  - `block_selected` signal, `selected_block()`, `set_selected_block()`.
  - `_on_block` emits after the real tab click, not during programmatic sync.
- `ui/tabs/theme_designer_tab.py`
  - Two-way wiring between the left Blocks tab and the right Animations panel.
- `tests/test_per_element_animation.py` (new)
  - Selection in both directions, five phases per supported block, container
    1 paths, verse number note, split write/clear with unknown keys, split not
    offered on container/body, unknown-key preservation, and a 14-theme
    normalize gate.
- `tests/test_theme_designer_m1_batch1.py`
  - A tab-level selection test.
  - The existing 14-theme save/reload gate now selects every container, adds
    a sustain slot where absent, and writes a split on that container's text
    block, so the new paths are inside the round-trip proof.

Container 0 behaviour, Copy into theme, the Timeline for custom keyframes and
all path requests through `ThemeDocument` are unchanged.

### Editable slot count on the eight showcase themes

The count uses the audit's slot definition: every authored assignment at
container or block level (entry, sustain, out, transition in/out) plus one
slot for a split. A slot is editable when a Designer control can reach its
path for the selected element.

| Theme | Total | Before (audit rule) | After |
| --- | --- | --- | --- |
| fullscreen_rise | 11 | 2 | 11 |
| fullscreen_pop | 12 | 3 | 12 |
| fullscreen_split | 6 | 3 | 6 |
| default_typewriter | 10 | 2 | 10 |
| default_quiet | 10 | 2 | 10 |
| reference_frames | 10 | 2 | 10 |
| reference_letterbox | 10 | 2 | 10 |
| slides_motion | 6 | 2 | 6 |
| **Total** | **75** | **18** | **75** |

No showcase theme carries a sustain slot. The panel offers sustain anyway
because the renderer plays it. The old 57 figure was the static audit's
undercount, not 57 slots with no control: the panel's Edit dropdown could
already reach block paths, but nothing in the left column selected them.

### Tests run

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_per_element_animation.py -q
# 22 passed

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_m1_batch1.py tests/test_theme_designer_stage3.py \
  tests/test_theme_designer_m1.py -q -m "not webengine"
# 44 passed (includes both 14-theme gates and the 240 px animation cards)

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_stage2.py tests/test_theme_designer_stage4.py \
  tests/test_theme_v2_designer_roundtrip.py -q -m "not webengine"
# 52 passed
```

## Part 3: design for properties no animation can reach

### Additive schema shape

Add one optional object to an animation assignment. It sits beside entry,
sustain, out, transition and split, so it inherits the same element and the
same document path:

```json
"animation": {
  "entry": {"use": "fade_up"},
  "properties": {
    "border.draw": {
      "phase": "entry",
      "duration_ms": 900,
      "delay_ms": 0,
      "easing": "ease-out",
      "direction": "clockwise",
      "from": 0,
      "to": 1
    },
    "text.letter_spacing": {
      "phase": "entry",
      "duration_ms": 600,
      "easing": "ease-out",
      "from": "0.3em",
      "to": "0em"
    },
    "shadow.bloom": {
      "phase": "entry",
      "duration_ms": 700,
      "delay_ms": 120,
      "easing": "ease-out",
      "from": {"x": 0, "y": 12, "blur": 0, "spread": 0, "color": "#00000000"},
      "to": {"x": 0, "y": 18, "blur": 40, "spread": 2, "color": "#00000066"}
    }
  }
}
```

Rules:

- Track ids are `area.property`, for example `border.draw`, `shadow.bloom`,
  `background.fade`, `backdrop.blur`, `text.outline`,
  `text.letter_spacing`, `text.color`, `layout.gap`. The prefix selects the
  interpolation domain; the suffix selects the animator.
- Every track names exactly one phase and has `duration_ms`, `delay_ms`,
  `easing`, `from`, `to`. Optional keys are `iterations` (sustain),
  `direction`, `speed`, `unit` and `look` overrides for split units.
- Unknown track ids and unknown keys inside a track are preserved, not
  dropped. A renderer that does not know `background.fade` ignores that one
  track and still plays the rest.
- Track `from` and `to` use the same value grammar as the static property:
  colours for colour tracks, CSS lengths for length tracks, a shadow object
  for shadow tracks and a number for draw progress.

**No schema_version bump.** The addition is optional, does not change the
meaning of any existing key, and degrades to the current render. A bump would
be justified only if a theme could require property animation (for example a
`requires` capability flag) or if keyframe semantics changed. Neither is
planned. The normalizer gains a `properties` branch, and
`normalize_theme` keeps returning v2.

### Animation types per element

| Element | Tracks worth adding |
| --- | --- |
| Container | `border.draw` (direction, speed), `shadow.bloom`, `background.fade` (solid colour or gradient stops), `backdrop.blur` / `backdrop.saturate` |
| Body | `layout.gap`, `layout.padding`, `background.fade` if the body paints |
| Text | `text.outline` (width and colour), `text.letter_spacing`, `text.word_spacing`, `text.color`, `text.shadow` |
| Reference | the text set, without layout tracks that would move the verse |
| Title (freeform) | the text set |
| Translation | the text set, plus `text.color` if it inherits |
| Verse number | the text set, only after the renderer starts reading its animation slots |

Font family and font style are discrete and should stay out: step them at
the phase boundary or not at all. Font size and letter spacing reflow text,
so they are legitimate but expensive; cache the final values and re-run the
fit once when the phase ends.

### What the renderer engine needs

A small typed-track registry, not more keyframe channels:

- Extend keyframes would force every custom animation to carry border,
  shadow, colour and filter channels, and each channel has a different
  interpolation domain. A shadow is a tuple, a gradient is a list of stops, a
  border draw is a geometry sweep.
- Add `PROPERTY_ANIMATORS` in display.js keyed by track id. Each entry
  declares `domain` (`number`, `color`, `length`, `shadow`, `paint`,
  `discrete`) and `play(el, track, context)`.
- `_runAnimation`, `_collectExit`, `_sustainTargets` and `previewReplay` call
  `_playPropertyTracks(target, phase)` beside the keyframe path.
- `_phaseDuration` returns the maximum of the keyframe duration and every
  track's `delay + duration`, so preview state and overlap timing stay
  correct.
- `_cancelAllAnimations` must cancel property animators as well, and
  `_setContainersHidden` must not leave a running track painting.
- The overlap layer capture must freeze animated values by writing the
  current computed values onto the clone, not only the static theme values.
- Reduced motion jumps every track to `to` with no delay.

Three animator families cover almost everything:

1. **CSS custom property tracks**: write `--rc-<property>` each frame, or use
   the Web Animations API on a custom property where Chromium supports it.
   Covers background, backdrop filter, colour, opacity and shadow.
2. **Geometry tracks**: SVG overlay for border draw, `stroke-dashoffset` for
   outline draw. Covers border and text outline.
3. **Layout tracks**: letter and word spacing, gap, padding. Covers the text
   and body spacing family; always end with one refit.

### Interaction with split and the motion machine

- A track on the element assignment runs once on the element.
- A track on `split.first` or `split.rest` runs per unit with
  `delay + index * stagger_ms`, matching the phase cards.
- Split never duplicates a border or shadow track: those belong to the
  container, which has no units.
- `text.outline` and `text.letter_spacing` on a split text block run per
  unit; letter spacing must re-measure lines after the phase, otherwise the
  line groups from before the animation stay in place.
- Phase ownership is the same as today: entry on show, sustain while shown
  (gated by `motion.sustain_when_cloaked`), transition in/out on content
  change, out on hide. A track without a phase is invalid.
- Split's existing limits still apply: no split when the text has an SVG
  outline, a line clamp, `<br>`, `<sup>` or `<sub>`, or a typewriter slot.

### Cost per element and build order

Estimates are engineering days for one developer, including tests.

| Work | Cost |
| --- | --- |
| Schema branch, validation, preservation, Designer round-trip | 1 to 1.5 |
| Renderer registry, colour and length animators, phase duration and cancel | 2 |
| Border draw animator (SVG path, four sides, direction, speed) | 2 |
| Shadow and background tracks | 2 to 3 |
| Text outline and spacing tracks, with refit | 1.5 to 2 |
| Backdrop filter track | 1 |
| Designer rows, preview/replay, timeline integration | 3 |
| Split and overlap integration | 1.5 |
| Renderer and Designer tests across elements | 2 |

Per element: border draw on a container 2 days; shadow 1 day; background 1
day; text outline 1.5 days; letter spacing 0.5 day plus refit. The schema and
registry are shared, so the second element is much cheaper than the first.

Recommended order:

1. `animation.properties` schema, preservation, registry, and `border.draw`
   on containers, with a Designer row and replay.
2. `text.outline` and `text.letter_spacing` on text-bearing blocks.
3. `shadow.bloom`.
4. `background.fade`, solid first, gradients second.
5. `backdrop.blur`.
6. `text.color`, then font metrics last, because they reflow.

Border draw is the worked example because it is the owner's named case, it
needs no colour interpolation, and it proves the phase, split and cancel
paths without touching layout.

### Border draw, worked example

Schema: a `border.draw` track with `direction` (`clockwise`,
`counterclockwise`, or `start: top|right|bottom|left` plus a direction),
`duration_ms` 0 to 5000, optional `speed` in px per second (10 to 5000) that
overrides duration, `from` and `to` in 0 to 1.

Renderer: one absolutely positioned SVG per container, inset by half the
border width, with a rounded rect path built from the resolved per-side
width, style and radius. Set `pathLength="1"`, `stroke-dasharray="1"`, and
animate `stroke-dashoffset` from 1 to 0. Reverse the offset for
counterclockwise, or rotate the path start for `start`. Dashed and dotted
styles multiply the dash array; `linecap` follows the border style. When the
four sides differ, build four paths and stagger or run them together. Speed
mode computes `duration = perimeter / px_per_s`, clamped to the registry
range. The SVG is pointer-transparent and sits inside the container, so it
does not change layout or hit testing.

The static border remains the final state, so a theme without support still
paints its border normally.

### Cheapest alternative

One optional `"draw": "clockwise 900"` string on the container, parsed by the
renderer, and a CSS-only sweep using a `clip-path` inset or a conic-gradient
mask on an `::after` pseudo-element. It costs about a day, needs no schema
tracks, no Designer controls and no property registry. It cannot do per-side
colours, rounded corners, speed in px per second, split units or phase
scheduling without becoming the full design. Use it only as a visual
experiment; it is not the foundation.

### Designer targets

The Animations panel now offers **Border** and **Shadow** as targets while
**Container** is selected. Border edits the container's `border.draw` track;
Shadow edits `shadow.bloom`. Both targets write under
`containers[i].animation.properties`, keep the container's phase slots and
the other property tracks, and offer phase, duration, delay and easing.
Border adds direction, speed and draw range. Shadow adds `from` and `to`
shadow fields and states in the panel that the renderer does not play that
track yet.

## What was not verified

- Windows rendering and font metrics. No Windows machine was available.
- High-DPI at 125, 150 and 200 percent.
- A real-display click-through of the new split section at 240 px and 300 px.
  The offscreen tests assert wiring, paths and heights, not painted pixels.
- The renderer was read, not run with a new property track when Part 3 was
  written. `border.draw` is now implemented in both renderer copies and
  covered by `tests/test_theme_v2_border_draw.py` and
  `tests/test_theme_v2_property_tracks.py`.
- OBS output and QtWebEngine preview inside the Designer. The shipped-theme
  gates stub the preview, as the existing M1 gates do.
