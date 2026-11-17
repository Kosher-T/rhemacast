# Theme parameter discrepancy fixes

## Decisions for you

1. **`fullscreen_pop` now renders the verse number at weight 800.** It authored
   800 while the stylesheet hardcoded 700. The renderer now honours the theme,
   so this one shipped theme changes. Accept the authored value, or change the
   theme back to 700 if the old look was intentional.
2. **A hand-authored shared `text_shadow` reference still paints no shadow.**
   `resolve_shared` does not expand block text shadows, and the Designer never
   offered shared text shadows. Expanding them belongs in core shared
   resolution, not in the renderer. The current behaviour is documented and
   tested; no UI path can create one.
3. **`verse_num.mode: block` remains unsupported.** It renders no number rather
   than a block number. A fix needs a separate number element outside the text
   run plus layout rules for above/below, so it is a medium change rather than
   part of this pass.
4. **Hidden controls stay hidden rather than disabled.** `containers[].kind`,
   `blocks.body.visible` and `verse_num.position` have inline notes and keep
   their stored values. Disabled rows would still imply the renderer reads
   them.
5. **The Windows and high-DPI appearance check is outstanding.** All new
   controls use the existing Qt widgets and no native popups were added, but
   the report cannot claim a visual pass on Windows from this machine.

## Safe to skip

- Pixel-level checking in OBS. The Node and Chrome harnesses verify DOM and
  style writes, not broadcast output.
- Expanding shared text shadows. No panel path writes one.
- `text_shadow.spread`. CSS `text-shadow` has no spread component; the
  converter drops it rather than emit an invalid declaration.
- Any change to `motion_state`, the Motion section, or content-kind pairing.

## What changed, with proof

### A. Verse number properties

Both renderer copies now build an inline style for the number span from
`size`, `weight`, `opacity`, `line_height`, `vertical_align` and
`margin_right`, plus `color`. The inline style wins over `themes.css`, so an
authored value is the effective source; the stylesheet values remain fallbacks
for keys a theme omits. This is applied at all three span creation sites: the
legacy container path, the single-container render, and the multi-container
block renderer.

`position` is unsupported. Its control is hidden with an inline note and the
stored value is preserved. `mode: block` is unchanged and documented as
partial.

Proof: `test_verse_num_authored_properties_reach_the_number_span` runs both
renderer copies and asserts every property in the rendered span. The
hidden-value test loads a theme with all three hidden keys, edits
`canvas.width`, normalizes, reloads, and asserts the keys are unchanged.

Shipped themes: 11 of 12 scripture themes render the same number because their
values match the CSS fallbacks. `themes/scripture/fullscreen_pop.json` authors
weight 800 and changes from 700 to 800.

### B. `containers[].kind`

The Container page control is replaced by a note: kind is authoring metadata
and rendering uses Visible. The key remains accepted, validated and preserved.
No renderer filtering was added.

Proof: `test_hidden_controls_keep_their_values_through_edit_and_reload` checks
the control is gone and the stored `freeform` value survives edit and reload.

### C. `blocks.body.visible`

The Body tab control is replaced by a note: the container Visible switch hides
the panel, and body visible is preserved but not rendered. The key remains
accepted and preserved.

Proof: the same hidden-value test.

### D. `text_shadow` object form

Both renderer copies now convert a structured shadow to CSS before assignment,
in the root text path, the legacy positioned-container path, and the
multi-container text block. String and `"none"` forms pass through unchanged.
A shared reference returns an empty shadow instead of the literal
`[object Object]`.

The panel already withholds shared options for text shadows, and
`resolve_shared` does not expand a block text shadow, so the panel and core
resolution need no change for the current UI. Supporting shared text shadows
would require expanding them in `core/theme_shared.py` first.

Proof: `test_text_shadow_object_string_none_and_shared` covers object, inset,
string, none and shared for both copies. `test_text_shadow_object_reaches_the_root_css_variable`
checks the rendered CSS custom property.

### E. `slide.show_title`

Freeform themes now get a "Freeform slide" section on the Canvas page with a
Show title switch. It reads the current value, defaults to on when absent, and
writes only `("slide", "show_title")` through the single `ThemeDocument`. A
load never writes the key.

Proof: `test_show_title_toggle_does_not_write_an_absent_key_until_changed`,
`test_show_title_toggle_reads_and_round_trips_a_stored_value`, and
`test_show_title_toggle_is_absent_for_scripture`.

## Leaf verdicts

| Verdict | Before | After |
|---|---:|---:|
| works | 305 | 317 |
| ignored | 136 | 124 |
| partial | 5 | 5 |

The 12 flipped leaves are six `verse_num` properties and six
`containers.*.blocks.text.text_shadow.*` leaves. Their matrix rows now record
the harness tests above. `containers.*.kind`, `body.visible` and
`verse_num.position` keep their verdicts and now record the hidden controls.
`slide.show_title` stays partial because the display page still does not read
it.

## Verification run

- Designer suites, including the 14-theme round-trip gate:
  `test_theme_designer_m1_batch1`, `stage2`, `stage3`, `stage4`,
  `test_theme_v2_designer_roundtrip`, and the new discrepancy tests:
  **85 passed**.
- Renderer and schema suites: `test_display_js`, `test_display_motion_state`,
  `test_display_render_matrix`, `test_theme_v2_schema`, `test_motion_state`:
  all passed. `test_display_js`: **72 passed**.
- `test_theme_v2_animation_runtime`: **26 passed, 4 failed**. The four failures
  are the real-Chrome reduced-motion cases. The same test passes on a clean
  HEAD worktree and still fails with this pass's renderer changes reverted, so
  the failure comes from the existing uncommitted motion work, not from these
  fixes. It is reported here as a pre-existing failure.

## Files touched

- `display/display.js`
- `ui/widgets/display_view.py`
- `ui/widgets/theme_designer/property_editor.py`
- `tests/test_display_js.py`
- `tests/test_theme_designer_discrepancy_fixes.py` (new)
- `docs/theme_effect_matrix.json`
- `docs/theme_parameter_atlas.json`
- `docs/theme_designer_spec.md`
- `docs/theme_designer_discrepancy_fixes.md` (new)

No schema keys were removed or renamed. No motion file, Motion section code or
kind-pairing code was touched. Nothing was committed.

## Not verified

- Windows rendering and high-DPI scaling.
- Real OBS output and painted pixels.
- A visual screenshot pass of the new Designer section and hidden-control notes.
