# Scripture switch frame trace

Investigation of the hidden sub-100 ms body fade on scripture change, and the
fix that removed it. All observations below are from the code in this working
tree, a real Chromium page running `display/display.js`, and the resolved
`default_typewriter` theme.

## Root cause

`themes/scripture/default_typewriter.json` authored

```json
"blocks": {
  "text": {
    "animation": {
      "transition": {}
    }
  }
}
```

The raw value is an empty transition object. `core/theme_schema.py` passed that
empty object to `_normalize_slot`, which treated it as an unknown inline
definition and returned the `fade_in` fallback. The resolved theme therefore
carried

```json
"text": {"animation": {"transition": {"in": {"use": "fade_in"}}}}
```

`display/display.js` did the same substitution independently in
`_resolveSlotDef`, and `_playTypewriter` also fell back to a fade when it could
not split. `#verse-text` owns both the body text and the verse number, so both
dimmed together. The reference is `#verse-ref-text`, a separate block with no
transition slot, so it stayed at full colour. That is the asymmetry in the
screenshots.

The fade was short because the generated `fade_in` definition uses the built-in
600 ms duration, and the first part of that curve is the visible part. The
measured opacity climbed 0, 0, 0, 0.165, 0.308, 0.430, 0.533, 0.617, 0.685,
0.750, 0.795 over the sampled frames.

The orange warning named `containers[0].animation.transition.type` because that
container path was the only unknown inline type left after the text slot was
dropped. A Body edit normalizes the whole document, which surfaced the warning
even though the Body panel wrote only `blocks.body.gap`. The warning itself did
not write a value; the normalizer already had one from the empty text
transition.

## Slot dump

Resolved `default_typewriter`, all phase paths on the five animated targets.
"none" means the key is absent after normalization.

| Target | entry | sustain | transition.in | transition.out | out |
|---|---|---|---|---|---|
| container `main` | `fade_in` 500 ms, delay 0, default easing | none | none | none | `fade_out` 300 ms, delay 0, default easing |
| body | none | none | none | none | none |
| text | none | none | none | none | none |
| reference | none | none | none | none | none |
| translation | none | none | none | none | none |
| verse_num | none | none | none | none | none |

The resolved `animations` map contains only `fade_in` and `fade_out`, both
referenced by the container entry/out slots. There is no active body, text,
reference, translation or verse number slot. The two active container slots are
editable in the Designer's Container motion controls. No non-editable slot holds
an active value in this theme, so the hidden fade did not come from one of the
unexposed slots.

## Body edit diff

Before and after one Body edit (`blocks.body.gap` 26 to 27) on
`default_typewriter`:

- Changed key: `containers[0].blocks.body.gap`, 26 to 27.
- Changed animation key: none.
- Raw `blocks.text.animation` before: `{"transition": {}}`.
- Raw `blocks.text.animation` after: `{"transition": {}}`.
- Normalization warnings before: none after the fix.
- Normalization warnings after: none after the fix.
- Resolved `blocks.text.animation` before and after: absent.

The same is true with every slot set to a canonical None form and an unknown
`future` key present: the animation subtree is byte-identical after a Body
edit, and unknown keys survive. That is pinned by
`test_body_edit_round_trips_a_none_animation_tree_byte_identically`.

## Frame trace, fixed renderer

Real Chromium, `default_typewriter`, seeded with John 11:35 then switched to
Esther 8:9 and back. Samples are one `requestAnimationFrame` apart. The first
row is the first frame after the update call.

| Frame | Body text | Body opacity | Verse number | Reference | Ref opacity | Translation opacity | Body animations |
|---|---|---|---|---|---|---|---|
| 1 | `9 Now it came to pass ... Esther the queen.` | 1 | `9` | `Esther 8:9` | 1 | 1 | 0 |
| 2 | same | 1 | `9` | same | 1 | 1 | 0 |
| 3 | same | 1 | `9` | same | 1 | 1 | 0 |
| 4 | same | 1 | `9` | same | 1 | 1 | 0 |
| 5 | same | 1 | `9` | same | 1 | 1 | 0 |

The long to short switch is identical in shape: the first frame already shows
`35 Jesus wept.` with body and reference opacity 1. No sampled frame had body
opacity below 1, `visibility: hidden`, a transform, a filter, a clip, or a
running animation on body, verse number, reference or translation. The verse
number's static `opacity: 0.7` comes from `blocks.verse_num.opacity` in the
theme file and is unchanged on every frame; it is styling, not a transition.
Slide Next/Prev and cloak/uncloak were also sampled. Cloak hides the container
immediately because the theme has no clear animation; uncloak restores the
content at opacity 1 with no animation on the content blocks.

The after-fix screenshot is `screenshots/scripture_switch_fade_after.png`. The
pre-fix captures are `screenshots/scripture_switch_fade_before.png` and
`screenshots/scripture_switch_fade_before_mid.png`.

Pixel check: a Chromium tab recording of the all-forms no-animation theme was
sampled from its WebM frames with `signalstats` over the body and reference
regions. The body region rose from a 34.92 background mean to 39.51 on the
Esther frame while the reference rose from 38.25 to 38.68. No frame had a
falling body mean with an unchanged reference mean, which is the pixel shape of
a body-only fade. The recording runs at about 2.6 fps, so it cannot resolve a
sub-100 ms fade on its own; the per-frame style trace above is the timing proof,
and the recording is the pixel corroboration.

## Gating and animation sources

| Source | File and line | What it does | Verdict |
|---|---|---|---|
| Empty transition normalization | `core/theme_schema.py`, `_normalize_slot` | Returned `fade_in` for `{}` and unknown inline definitions | HARDCODED, removed |
| Unknown slot name normalization | `core/theme_schema.py`, `_normalize_slot` | Returned `fade_in` / `fade_out` for an unknown name | HARDCODED, removed |
| Unknown `use` reference | `core/theme_schema.py`, `_resolve_animation_refs` | Dropped the slot after warning | FUNCTIONAL-NEEDED, kept as no animation |
| Renderer slot resolution | `display/display.js`, `_resolveSlotDef` | Same `fade_in` fallback for empty or unknown values | HARDCODED, removed |
| Typewriter split failure | `display/display.js`, `_playTypewriter` | Fell back to `fade_in` when the text could not be split | HARDCODED, removed |
| Typewriter invalid context | `display/display.js`, `_playTypewriter` | Fell back to a fade on a bad context | HARDCODED, removed |
| Autofit | `display/display.js`, `autoFitText` | Measures text synchronously and refits after the first frame for `min_height` panels | FUNCTIONAL-NEEDED. It changes font size, not opacity or visibility; the refit is after the swap and never hides content. |
| Container entry/out | `themes/scripture/default_typewriter.json` | Theme-authored `fade_in` 500 ms and `fade_out` 300 ms | THEME-DRIVEN |
| Cloak/out class | `display/themes.css`, `#container.hidden` | Hard hide for clear/cloak when no out slot is active | FUNCTIONAL-NEEDED, current semantics kept |
| Reduced motion | `display/display.js`, `_reducedMotion` | Skips plans when the OS asks for reduced motion | FUNCTIONAL-NEEDED. It does not add or mask a fade. |
| Renderer `transition: none` | `display/themes.css` | Disables CSS transitions on the container | THEME-DRIVEN/static, no reveal timer |

## Why the reference differed

`_renderDisplay` writes the verse text plus the `.verse-num` span into
`#verse-text`. The reference is written separately into `#verse-ref-text` and
the translation into `#verse-ref-translation`. The transition slot lived on the
`text` block, so `_collectTransitionIn` targeted `#verse-text` only. The
reference block had no slot, so it was never in the incoming plan and painted
at its final opacity immediately.

## Fix

- `core/theme_schema.py`: blank, null, empty object, `"none"` and invalid slot
  forms now resolve to no slot. Unknown inline types warn and are dropped, not
  replaced. Empty transition maps disappear. Unknown assignment keys are
  preserved instead of being dropped.
- `display/display.js`: `_resolveSlotDef` returns null for unknown names,
  unknown `use`, empty objects and invalid forms. Typewriter split failures and
  invalid contexts return without starting an animation. No fade is invented.
- `ui/widgets/display_view.py`: the inline renderer is regenerated from
  `display/display.js`; the non-empty script lines are identical.
- `docs/theme_file_reference.md`: documents that absent, empty, null, `"none"`
  and unknown slots mean no animation, and that unknown assignment keys survive
  a round-trip.

No theme file was rewritten. `default_typewriter.json` still contains the empty
`text.animation.transition` object; it now resolves to no animation.

## Tests

- `test_theme_v2_animations.py`: empty transition, invalid inline definition,
  invalid slot names and unknown assignment keys.
- `test_theme_v2_security.py`: injection-shaped unknown names disable the slot.
- `test_display_js.py`: `_resolveSlotDef` unknown forms, plus a static guard that
  `_resolveSlotDef`, `_playTypewriter`, `_collectTransitionIn` and
  `_collectTransitionOut` contain no `fade_in` / `fade_out` fallback.
- `test_theme_v2_animation_runtime.py`: real Chrome switch across short/long,
  long/short, slide Next/Prev, slide to scripture, clear and uncloak, with every
  frame asserted per element. It covers `null`, `""`, `"none"`, `{}`, an unknown
  string and an unknown inline type.
- `test_per_element_animation.py`: all-None animation tree plus a Body edit;
  animation subtree byte-identical and unknown keys preserved.

## Not verified

- Windows, high DPI scaling, and OBS capture were not available on this host.
- The Designer preview was driven through the same renderer code, but the live
  operator UI and the Designer window were not screen-recorded here. The probe
  uses the real `display/display.js` in Chromium with the resolved theme.
- `test_v2_min_height_panel_autosizes_long_text` still fails in this working
  tree because the uncommitted theme geometry sets the panel to 1920 x 1080
  instead of the committed 1660 px wide / auto height. The autofit block is
  unchanged from `HEAD`; the failure predates this fix and is listed under
  "Found but not touched".
