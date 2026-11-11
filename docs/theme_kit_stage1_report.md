# Theme kit — Stage 1 report

Stage 1 delivered the reusable UI building blocks for the Theme Designer rebuild.
The Designer, its panels, `core/theme_schema.py`, theme loading/saving and every
renderer are untouched. Nothing in `ui/theme_kit/` is imported by the app yet.

## 1. What existed and was reused

| Reused | How |
| --- | --- |
| `ui/tokens.py` | Palette (`BG_*`, `TEXT_*`, `ACCENT_*`, `SELECTION_*`, `BORDER_*`), radii, spacing, type sizes/weights and QSS helpers. No new colours were invented. |
| `ui/tokens.py` (added) | Kit metrics only: `CONTROL_HEIGHT=26`, `CONTROL_HEIGHT_SM=22`, `CONTROL_PAD_X`, `LABEL_COLUMN_WIDTH=88`, `CHANGED_DOT_SIZE=5`, `FOCUS_RING_WIDTH=1`, `CHECKER_LIGHT/DARK`, `POPUP_GUTTER=6`, `POPUP_MAX_HEIGHT=320`. |
| `ui/field_chrome.py` | Chevron convention and focus-ring drawing idioms. |
| `ui/popups.py` | Surface conventions (gutter, radius, edge, halo) reproduced in the kit's own `PopupSurface` so no native popup is used. |
| `core/theme_shared.py` | `load_family()` output is passed in by the caller as `shared_options`; the kit never resolves files itself. |
| `tools/` convention | The dev gallery lives beside the app and is not shipped. |

No third-party dependency was added.

## 2. Module layout (`ui/theme_kit/`)

`base.py` (option model, fonts, elision, painting) · `popup.py` (own popup
surface, tooltip manager, screen clamping) · `flow.py` (wrapping layout) ·
`property_row.py` · `dropdown.py` · `number_field.py` · `slider_field.py` ·
`switch.py` · `chip_select.py` · `segmented.py` · `color_field.py` ·
`paint_field.py` · `anchor_picker.py` · `four_side.py` · `easing_picker.py` ·
`timeline.py` · `shadow_editor.py` · `border_editor.py` ·
`animation_phase.py` · `split_editor.py` · `container_canvas.py` ·
`sample_injector.py` · `small.py` · `__init__.py` (exports the public names).

## 3. Public API

`ChoiceOption(value, label="", icon=None, muted=False, tooltip="",
disabled_reason="", font_family="", group="")` is the shared option shape;
`SampleState(id, label, icon="", group="", kind="content")` for the injector.
All widgets are property-agnostic: ranges, defaults, steps, units, options and
warning text come from the caller.

**Chrome**
- `PropertyRow(label, control=None, *, label_width=88, full_width=False, changed=False, warning="", disabled_reason="")` — `set_label`, `set_control`, `set_changed`, `set_warning`, `set_disabled_reason`, `set_reset_visible_mode`; signal `reset_requested`. Reset is an overlay button (hover / changed / focus), so it never steals label width.
- `PropertySection(title, *, state_key="", expanded=True)` — `add_row`, `add_widget`, `add_layout`, `set_expanded`, `set_changed_count`; signal `expanded_changed`.

**Numbers**
- `NumberField(value=0, *, minimum=None, maximum=None, step=1, coarse_step=None, fine_step=None, integer=False, decimals=None, unit="", units=None, suffix="", keywords=None, nullable=False, placeholder="Not set", unit_converter=None, label="")` — `value`, `set_value`, `set_range`, `set_step`, `set_units`, `set_suffix`, `set_warning`; signals `changed` (unit included in the value, e.g. `"24px"`), `preview`. Scrub with Shift/Alt steps, wheel only when focused, double-click to type.
- `SliderField(value, *, minimum, maximum, step, default=None, integer=False, decimals=None, label="", field_width=62)` — `set_value`, `set_range`, `set_step`, `set_default`; signals `changed`, `preview`, `dragging`.
- `FourSideField(value, *, base_key="padding", side_keys=("top","right","bottom","left"), side_template="{base}_{side}", linked=True, unit="px", units=None, minimum=0, maximum=400, step=1, integer=True, decimals=None, nullable=False, keywords=(), side_labels=None)` — `set_value`, `set_linked`, `set_range`, `set_warning`; signals `changed`, `preview`. Emits CSS strings: `{padding:"12px", padding_top:"…", …}` or flat `{top:"1px", …}` when `base_key=None`.

**Choice**
- `CompactDropdown(options, value=None, *, placeholder="—", searchable=False, force_search=False, preview_font=False, variant="field", min_width=0, max_width=None, popup_width=None, popup_max_height=320, popup_align="left")` — `set_value`, `set_options`, `set_placeholder`, `set_searchable`, `set_preview_font`; signals `changed`, `opened`. Own popup: type-ahead, arrows/Enter/Esc, accent tick, per-item font preview, screen clamping.
- `ChipSelect(options, value=None, *, multi=False, allow_deselect=False, h_spacing=4, v_spacing=4)` — `set_value`, `set_values`, `set_options`; signal `changed`. Wraps; `muted` options paint as an outlined "no override" choice when selected.
- `ChoiceField(options, value=None, *, style="auto", multi=False, chip_limit=7, label_limit=14, searchable=False)` — chooses chips vs dropdown automatically; signal `changed`, `opened`.
- `SegmentedToggle(options, value=None, *, allow_empty=False, min_segment=26)` — `set_value`, `set_options`; signal `changed`.
- `ToggleButton(icon=None, text="", *, checked=False, tooltip="", accessible_name="")` — `set_value`, `set_icon`; signal `changed`.
- `Switch(checked=False, text="")` — `set_value`; signal `changed`.

**Colour and paint**
- `ColorField(value="#ffffff", *, palette=(), keywords=(), nullable=False, alpha=True, placeholder="Not set")` — `set_value`, `set_palette`, `set_keywords`, `set_warning`; signals `changed`, `preview`. Stores raw text (`@token`, `rgba(...)`, `currentColor`, …), shows checkerboard for alpha, own popover with palette strip and detach.
- `ColorEditor(value, *, palette=(), keywords=(), alpha=True)` — embedded editor; `current_color`, `set_value`; signals `preview`, `committed`.
- `PaintField(value, *, palette=(), keywords=(), allow_gradient=True, allow_none=True, nullable=False, max_stops=12)` — `set_value`, `set_palette`, `set_keywords`, `set_warning`; signals `changed`, `preview`. Solid/linear/radial/none; stops are literal-only by design; unparseable CSS stays in raw mode.
- `GradientEditor(value, *, palette=(), min_stops=2, max_stops=12)` — `set_gradient`, `set_palette`; signals `preview`, `changed`.

**Placement and effects**
- `AnchorPicker(value="center", *, allow_fill=True, cell=22)` — `set_value`; signal `changed`.
- `AnchorRow(value=None, *, show_offsets=False, x_key="x", y_key="y", x_range=..., y_range=...)` — `set_value`; signals `changed`, `preview`.
- `ShadowEditor(value="none", *, shared_options=(), palette=(), allow_shared=True, max_layers=12, show_spread=True)` / `ShadowField(...)` — `set_value`, `set_palette`, `set_shared_options`, `set_warning` (field); signals `changed`, `preview`. Custom edits emit a CSS shadow string; shared emits `{"shared": name}`.
- `BorderEditor(value="none", *, shared_options=(), palette=(), allow_shared=True, styles=BORDER_STYLES, width_range=(0,40), radius_range=(0,400), side_radius=True)` / `BorderField(...)` — `set_value`, `set_palette`, `set_shared_options`, `set_editing_side`, `set_warning` (field); signals `changed`, `preview`. Custom emits a dict `{width, style, color, radius}` plus `sides: {top: {changed keys}}`; shared emits `{"shared": name}`.
- `EasingPicker(value="ease-out", *, presets=None, allow_custom=True)` — `set_value`, `set_warning`; signals `changed`, `preview`, `opened`. Stores preset names or `cubic-bezier(...)` verbatim.
- `Timeline(frames=None, *, minimum=2, maximum=8, show_editor=True)` — `set_frames`, `add_frame`, `remove_frame`; signals `changed`, `preview`, `selected`. Frames keep unknown keys; endpoints pinned at 0/100.
- `KeyframeEditor(frame=None)` — `set_frame`; signals `edited`, `previewed`.

**Animation and text composition**
- `AnimationDefinition(name, type, label="", duration_ms=0, delay_ms=0, easing="ease-out", origin="center", source="", reveal="", cursor=None, raw={})`.
- `AnimationPhaseCard(title, value=None, *, phase="entry", library=(), builtins=(), inline_types=..., disabled_types=(), disabled_library=(), duration_range=(0,5000), delay_range=(0,5000), easing_presets=None, origin_options=..., palette=(), allow_none=True, off_value="none", off_label="None", typewriter=True, slot_defaults=None, light=False, expanded=False)` — `value`, `effective`, `set_value`, `set_library`, `set_expanded`, `set_replay_available`, `set_warning`; signals `changed`, `preview`, `replay`. Unknown override keys (typewriter reveal/cursor) round-trip.
- `SplitEditor(value=None, *, library=(), builtins=(), inline_types=..., palette=(), phases=(("entry","Entry"),("transition_in","Transition In")), defaults=None, disabled_reason="", unit_labels=("First unit","Rest"))` — `value`, `set_value`, `set_readout`, `set_note`, `set_disabled_reason`; signals `changed`, `preview`, `replay`.

**Canvas and samples**
- `ContainerBox(id, label="", x=0, y=0, width=320, height=180, layer=0, visible=True, fill=False)`; `ContainerCanvas(canvas_size=(1920,1080), *, safe_area=0.05, show_readout=True, background="transparent", palette=())` — `set_boxes`, `set_selected`, `set_canvas_size`, `set_zoom`, `set_safe_area_visible`, `set_background`, `set_palette`; signals `selected`, `changed`, `preview`, `zoom_changed`. Geometry is caller-owned; fill boxes are not draggable.
- `ContainerStrip(boxes=(), selected="", *, max_visible_rows=6)` — slim list (not chips; 16 containers do not fit as chips at 300 px); signals `selected`, `add_requested`, `duplicate_requested`, `delete_requested`, `visibility_toggled`, `reordered`.
- `SampleInjector(states=(), current="", *, label="Sample")` — `current`, `current_state`, `set_states`, `set_current`, `set_custom_value`, `set_arrows_visible`; signals `changed(str, bool)` (id, re-roll), `custom_requested(str, str)`.

**Small pieces**
`IconButton(icon=None, *, glyph="", text="", tooltip="", accessible_name="", checkable=False, checked=False, variant="normal", compact=True)` · `Badge` · `Divider` · `EmptyState` · `SectionLabel` · `SearchField(placeholder, *, delay_ms=250)` (`changed`, `submitted`) · `TextInput(text="", *, placeholder="", max_length=32767)` (`set_state`, `set_message`; `changed`, `text_changed`) · `ValidationItem(severity, message, path="")` (`activated`) · `ValidationBadge(text, *, severity="warning")` (`clicked`) · `BlockTabBar(tabs, current="")` (`selected`, `visibility_toggled`; wraps to multiple 26 px rows rather than eliding names).

## 4. Deviations from the brief (and why)

1. **Shadow custom values are CSS strings, border custom values are dicts.** The
   shadow reference itself is a CSS list, so a string round-trips exactly; the
   border reference is an object, so a dict preserves width/style/colour/radius
   and per-side overrides without string parsing. Shared refs stay
   `{"shared": name}` in both.
2. **`NumberField` includes the unit in `value`** (`"24px"`); `suffix` is
   display-only. Unit switching uses a caller-supplied `unit_converter`; without
   one the visual value is never silently reinterpreted.
3. **`FourSideField` flattens overrides** into `padding` + `padding_top` style
   keys (strings with units) rather than a nested object, matching the settings
   keys Stage 2 will write. `base_key=None` emits a flat side dict.
4. **`BlockTabBar` wraps** instead of truncating: five tabs with visibility dots
   and badges cannot fit legibly in 240–300 px on one row.
5. **`ContainerStrip` is a slim list**, not a chip row — the brief allowed either,
   and 16 containers at 300 px do not fit as chips.
6. **`SplitEditor`'s inherited phase chip reads "Inherit"** (the full phrase
   elided to "Inherit from ..." even at 300 px).
7. **`AnimationPhaseCard` keeps override keys it has no row for** (typewriter
   `reveal`/`cursor`, custom origin data) instead of dropping them on edit; the
   rows it owns are duration, delay, easing and origin.
8. **Spring/smooth easings are drawn with representative curves** while storing
   the preset name verbatim (no spring simulation in a thumbnail).
9. **All previews are painted manually** (including shadow swatches), never with
   `QGraphicsDropShadowEffect`, so Windows and Linux agree.
10. **Muted "Auto/None/Inherit" chips are outlined, not accent-filled**, so a
    selected *absence* never reads like a real value.

## 5. Schema shapes no widget expresses yet

- `calc()`, `clamp()`, `var()` and other length expressions: `NumberField` can
  keep a keyword/nullable string, but there is no expression editor.
- Gradient stops containing `@palette` tokens: deliberately refused, because the
  renderer does not expand tokens inside gradient strings; the stop picker says
  so.
- Full inline animation definitions with `keyframes`: the phase card edits the
  named/common fields and preserves unknown keys, but authoring the keyframe
  array is the separate `Timeline`; Stage 2 must compose the two into one slot.
- `backdrop_filter` function arguments: `ChipSelect` (multi) selects the
  functions; the per-function argument rows are Stage 2 composition.
- Border radius shorthand that combines two radii per corner (`x/y` slash
  syntax) is not modelled; `BorderEditor` edits one radius value per side.
- Per-property ranges/defaults are never derived from the schema by the widgets
  (intentional); the caller must pass them, so a Stage 2 mapping table is
  required for every property.

## 6. Verification and limitations

- `python -m py_compile ui/theme_kit/*.py tools/token_gallery.py` passes.
- `python tools/token_gallery.py --shots DIR` renders 13 pages and exits 0
  (headless, `QT_QPA_PLATFORM=offscreen`); every page was inspected and layout,
  elision, wrapping, disabled/muted states and the 240 px column were corrected.
- Round-trips checked: `"24px"`, units, border custom/shared/side overrides,
  shadow custom/shared, split with look, phase card bare/override/inline with
  typewriter extras, timeline unknown-key preservation, four-side base/flat.
- Popups: `CompactDropdown`, `ColorField`, `PaintField`, `EasingPicker` and the
  sample list open and close cleanly (Esc, re-open).
- **Real display (Pop!OS, Xwayland `xcb` platform):** both editor popovers
  open, stay open after an inside click, close on a second click on the field,
  on Esc and on an outside press, and reopen with a fresh editor after being
  dismissed. The gallery renders all 13 pages there too (exit 0).
- The earlier "closes immediately" behaviour was a real bug, not an offscreen
  artifact: one click delivered the press to the field twice once the popup
  grabbed the mouse, so the replay hit the toggle-close branch. `ShadowField`
  and `BorderField` now ignore presses for one event cycle after opening, and a
  dismissed popover is discarded and rebuilt instead of blocking reopening.
  Setting the popup's window flags after construction also dropped the
  transient parent, which Wayland needs for a grabbing popup; flags are now
  passed into the constructor.
- **Wayland-native plugin not verified:** automated `QTest` input carries no
  seat serial, so the compositor refuses popup grabs ("Failed to create
  grabbing popup … parent window has received input") and every kit popup
  hides. That is a harness limitation, not app behaviour; a real click on the
  Wayland session could not be scripted without `xdotool`. Verification used
  the `xcb` platform on the same physical display.
- **Not verified: Windows rendering.** No Windows machine was available.
- Test note: leaving a popup open when the interpreter exits can segfault under
  both platforms; close popovers before tearing the test down.

## 7. Open questions for Stage 2

1. Should the shadow editor emit a structured layer list instead of CSS, to
   avoid the caller re-parsing what the widget just formatted?
2. Is `sides: {top: {width: 6}}` the shape the writer expects for per-side
   border overrides, or should each side be a full border object?
3. Should `FourSideField` emit nested `{base, sides}` instead of flattened keys?
4. At what width should the block tab bar switch from two rows to a scrolling
   row (or a "+N" overflow menu)?
5. Do Stage 2 writers want `AnimationPhaseCard` to own keyframes, or will the
   card hand its slot to `Timeline` explicitly?

## Stage 2 API update

- `ShadowField`, `ShadowEditor` and `_ShadowPopover` accept `structured: bool`
  (default `False`). Structured mode emits the schema's single-shadow object
  `{x, y, blur, spread, color, inset}`; with two or more layers it emits the
  validator-accepted CSS string, because `core/theme_schema.py` has no array
  shadow shape. Non-structured mode is unchanged.
- `AnimationPhaseCard.set_editor_widget(widget)` / `editor_widget()` add a
  caller-owned editor (Stage 3 `ParamForm`/`Timeline`) inside the expanded
  body, below the built-in rows. Nothing else in the card is re-owned.
- `ShadowField(..., allow_shared=False)` suppresses shared shadow refs; the
  Designer uses it for block `text_shadow`, where shared refs do not apply.
- Shadow X/Y/Blur/Spread and the border Radius now carry visible labels. (M1
  later moved these from `PropertyRow` wrappers to `NumberField(inline_label=)`
  so the label lives inside the field — see the last section.) The spread row
  hides with `show_spread`. No other widget API changed.

## M1 reconciliation — inline numeric labels

`NumberField` gained `inline_label: str = ""`. It paints a short muted label
inside the field, left of the number, and the label itself scrubs the value
(the same drag/Shift/Alt behaviour as the number area). `label` stays the
accessibility and tooltip name; callers may pass both (`label="Shadow blur"`,
`inline_label="Blur"`). An inline-labelled field keeps its reset/clear glyphs
and its editable value; nothing about the emitted value changes.

**Kit rule:** a `NumberField` mounted without a visible row label must pass
`inline_label`, so no numeric control is ever nameless. That covers paired
two-up rows and grid cells such as shadow X/Y/Blur/Spread, base and per-side
border radius, keyframe cells and easing controls. A field that already sits
in a row-labelled `PropertyRow` must not pass one — the label would appear
twice.

The label is sized to its text and the number keeps the remaining width; at
240 px the existing labels (X, Y, Blur, Spread, Radius) fit without the field
clipping the value. `Tests`: `tests/test_theme_designer_m1.py` covers
visibility, fit at 240 px, the no-double-label rule, multi-layer shadows and
the border radius pair; `dev/m1_check.py` repeats it on the real display.

## Stage 3 real-display kit fixes

These are behaviour fixes, not new APIs; they were found while embedding the
panel at 300 px and 240 px.

- `_ResetButton.set_shown(False)` now actually hides the glyph on construction.
  Previously the overlay started visible (painting nothing) and reserved label
  space, which elided labels in rows with no reset.
- `PropertyRow` reserves the reset glyph's 16 px when eliding its label, using
  the real label-column budget; the label no longer runs under the glyph.
- `_Chip.sizeHint()` measures with the medium weight used for painting and adds
  22 px, so “Default”/“Word” are not elided at the control's natural width.
- `AnimationPhaseCard` gives the phase title 62% of the header before the type
  chip and timing bar, widens its label column to 84 px, and hides the
  cursor Char/Color/Blink/Hide rows together with their controls.
- `KeyframeEditor` uses the short “Unset” placeholder for nullable fields; the
  clear glyph leaves ~38 px of text at a 240 px panel, where “Not set” elided.
