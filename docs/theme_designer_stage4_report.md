# Theme Designer — Stage 4: container canvas and split

Stage 4 replaces the v1 geometry panel with the Stage 1 container workspace and
mounts the Stage 1 split editor on the Blocks page. The investigation note is
`docs/theme_designer_stage4_findings.md`; this report covers what shipped, what
deviates from the brief, and what still needs a Windows machine.

## What was built

### One selection model

`ThemeDesignerTab` owns `_selected_container_id`. The centre workspace and the
left property panel are views:

- `ThemePropertyEditor` gained `set_selected_container(id)` and
  `container_selected(id)`; its Container dropdown now only requests a change.
  `_prefix()` and `container_id()` derive from the tab's selection.
- `ContainerWorkspace` owns the canvas, strip and geometry fields, but not
  selection: it exposes `set_selected(id)` and emits `container_selected(id)`.
- The tab validates the id, stores it, then pushes it back to both views.
  Canvas click, strip row, Container dropdown, add, duplicate and delete all
  pass through that single path.

### Container workspace

`ui/widgets/theme_designer/container_workspace.py` mounts inside the existing
centre **Editor** page (canvas flex + a 240 px strip/field column). No new
outer panel, tab or native dialog was added.

- 1–16 containers: add, duplicate, delete, select, drag, resize, keyboard
  nudge, layer reorder, visibility.
- The strip is the Stage 1 `ContainerStrip`; reorder writes layers evenly
  `0…100`, top-first, because layer order is paint order.
- Exact fields for anchor, X, Y, width, height, layer and visibility use
  `schema.ANCHORS`, `schema.POSITION_LIMITS`, `CONTAINER_MAX_WIDTH/HEIGHT` and
  `MAX_CONTAINERS`. No ranges or defaults are reimplemented.
- `fill` containers paint full-canvas, are not draggable, and disable their
  geometry fields with the canvas's own "Fill anchor · not draggable" note.
- The canvas is a controlled widget: a drag emits preview continuously, and a
  release emits the final rect. The workspace converts that rect to the raw
  document, re-syncs the canvas/strip/fields, and emits the whole document.
- Add disables at 16; delete disables at 1; duplicate is disabled without a
  selection.

### Anchor ↔ canvas conversion

`ui/widgets/theme_designer/container_geometry.py` is the only converter:

- `container_rect()` maps `{anchor, x, y}` + length sizes to absolute design
  pixels for all ten anchors.
- `apply_rect()` maps a canvas rect back to anchor-relative values.
- `px` and `%` resolve against the design canvas. `auto` uses a 60% width /
  40% height fallback **for display only**; the document keeps `auto`.

The review pass fixed three fidelity defects here:

1. **Pure moves no longer pixelise sizes.** `apply_rect()` rewrites only axes
   whose resolved geometry changed. A horizontal move of a container with
   `width: "auto"`, `height: "50%"` keeps both forms, and keeps a `"25%"` Y
   offset untouched. A resize still writes concrete pixels for the axes it
   changed, and rebases an offset only when that offset is measured against
   the changed size (for example a centered container resized from one edge).
2. **Exact fields no longer keep a stale unit.** Loading `10%` and then a
   document with `24` used to display/commit `24%`; as soon as a bare number is
   adopted, `NumberField` now returns to its default unit. A later edit writes
   `24px`, not `24%`.
3. **`auto` now reads as one state.** The keyword is mirrored into the unit
   selector, so the field shows `auto` instead of `auto` beside a `px` badge.

### Split editor

`ThemePropertyEditor` appends a `PropertySection("Split")` to the Blocks page
only when the selected block is in `schema.SPLIT_BLOCKS` (`text`, `reference`,
`title`, `translation`). `body` and `verse_num` never mount it.

- The editor is the Stage 1 `SplitEditor`, configured with
  `schema.split_defaults()` and the theme/built-in animation libraries.
- Enabling writes `animation.split`; disabling removes only `split`, leaving
  `entry`, `transition_in/out`, `exit` and unknown block keys intact.
- Writes merge unknown split keys back (`future_split` survives a `by` change),
  so the raw-document rule also holds inside `split`.
- The section starts expanded only when the document already has a split.

### Property-panel defaults

A review fix outside the canvas: an absent `opacity` or `line_height` used to
display `0` in the property panel because the raw document has no key, even
though the schema renders `1` / `1.2`. `_float_default()` now reads
`schema.block_defaults()` for block rows (container opacity has an explicit
spec default), so the field matches the preview. The document still has no key
until the operator edits the row.

### Tests

`tests/test_theme_designer_stage4.py` — **30 tests**, all passing:

- anchor round-trip for every schema anchor, `fill` and `auto`;
- pure move keeps `auto`/`%` sizes and untouched `%` offsets;
- resize keeps a centered container's visual left edge;
- workspace with 1, 8 and 16 containers, limit enforcement, add/duplicate;
- canvas edits reach the document and preserve container/position unknown keys;
- selection is shared and fields follow it; structural ops announce selection;
- reorder layers, overlap picks the topmost, 12 px edge containers;
- duplicate/delete preserve unknown keys;
- save to disk and cold-reload keeps theme, container, position and block
  unknown keys;
- exact fields follow the loaded unit and the `auto` keyword;
- absent opacity / line height show the schema default, not `0`;
- split mounts only for text-bearing blocks;
- split write preserves `entry` and unknown keys; disable removes only split;
- the property panel requests selection instead of owning a second model.

## Deviations from the brief

- **Drag/resize writes concrete values.** The canvas works in design pixels, so
  an axis the operator actually moves or resizes becomes `px`/a bare number.
  Untouched axes keep `auto`, `%`, or their authored offset. This is deliberate
  and covered by tests; a future "preserve the unit on resize" mode would need
  a unit switch in the canvas interaction, not more widget chrome.
- **Selection lives in the tab**, not in the strip. The strip and property
  dropdown are requests/views, as proposed in the findings note.
- **The strip column is inside the existing Editor page.** The brief forbade
  new panels; this reuses the v1 editor's centre slot rather than adding one.
- **Reorder renumbers layers.** Drag order is the user's intent; exact layer
  numbers are not preserved across a reorder. Unknown container keys are.
- **`fill` geometry is read-only.** The schema ignores offsets/size for
  `fill`; the workspace disables the fields instead of writing values the
  validator would discard.

## Verification

### Automated

- `tests/test_theme_designer_stage4.py` — 30 passed, including a real
  `save_theme` → JSON on disk → cold-reload round-trip.
- Full theme/registry/display suite (`tests/test_theme*.py`,
  `tests/test_animation_registry.py`, `tests/test_display_js.py`) — **592
  passed, 6 warnings**; the six are the known unawaited-coroutine warnings in
  `core/output_router.py`.

### Real display (Linux, `DISPLAY=:1`, xcb)

`dev/stage4_check.py` boots the real `ThemeDesignerTab` (QtWebEngine included)
and drives it with real mouse events. Screenshots are in `dev/stage4_shots/`.
The final run confirmed:

- workspace 838 px (canvas 598×819 + a 240 px side column) at a 1400×900 tab;
- 1, 8 and 16 containers paint; at 16 the add button is disabled;
- clicking an overlap selects the topmost strip id (`check3`);
- a drag moved the document to
  `{'anchor': 'top_left', 'x': 255, 'y': 150}`; a corner resize produced
  500×283;
- a horizontal move of an `auto` / `50%` container kept `auto`, `50%`, the
  `"25%"` Y offset and the unknown `future_position` key; X became `384`;
- 12 px and bottom-right edge containers paint and select;
- JSON Apply kept a top-level unknown key, a container unknown key and block
  unknown keys, and the canvas rebuilt to the applied document;
- split mounted with `{'by': 'line', 'stagger_ms': 70}`; toggling off removed
  only `split` (entry stayed), toggling on restored it, changing to `word`
  kept `unknown_block_key` and `future_split`;
- the exact X field wrote `300px` and moved the box to x=300 (the stale-unit
  fix);
- add selected `container3` in the tab, workspace and property panel at once;
- the property panel showed the absent `opacity` as `1` (the schema default),
  not `0`;
- at a forced 240 px left column: viewport 218 px, no horizontal scrollbar (max
  0, hidden), visible split width 218 px, two-row block tab bar 53 px with the
  next row at y=59, and `FourSideField` placeholders read `Unset` at 33 px of
  text in a 38 px edit. At scroll 0 the five block labels render in two rows
  (`12_blocks_240_top.png`); at max scroll the bar is 479 px above the
  viewport, so the clipped field at the top of the scrolled shot is the
  Outline input, not the tab bar.

Screenshot list:

| File | Check |
|---|---|
| `01_one_container.png` | single container, workspace layout |
| `02_eight_containers.png` | eight containers |
| `03_sixteen_containers.png` | sixteen boxes, add disabled |
| `04_overlap_topmost.png` | overlapping boxes, topmost selection |
| `05_drag_resize.png` | drag and corner resize |
| `06_move_preserves_forms.png` | `auto` / `%` survive a pure move |
| `07_edge_small.png` | 12 px box and bottom-right edge box |
| `08_json_apply.png` | JSON Apply with unknown keys |
| `09_split_editor.png` | Split section mounted on a text block |
| `10_split_expanded.png` | split on, `by: word`, unknown keys kept |
| `11_split_240.png` | Blocks page, Split and fields at 240 px |
| `12_blocks_240_top.png` | block tabs and fields at 240 px, scroll 0 |

## Not verified

- **Windows rendering was not checked.** There was no Windows machine in this
  worktree. Every real-display observation above is Linux/xcb. Font metrics,
  the 240 px column, dropdowns, tooltips, and high-DPI scaling on the church PC
  still need the checklist below.
- High-DPI (`devicePixelRatio` ≠ 1) canvas hit-testing: the canvas maps through
  widget coordinates and should scale, but it was only exercised at 1×.
- Touch/stylus drag and resize.
- Canvases at the schema maximum (7680×4320) and animation playback while
  dragging; the harness used 1920×1080.
- Save is verified at the loader boundary (`save_theme` → JSON on disk → cold
  reload, including unknown keys) in
  `test_save_and_reload_keeps_unknown_keys`. The toolbar **Save** button itself
  was not clicked in the real-display harness, and Export/Import were not
  exercised; the button is a two-line wrapper around `save_theme`.
- Stage 4 does not add a split preview animation; the split is proven in the
  JSON/document, not by watching the OBS display split words. That remains a
  renderer/display concern.

## Windows checklist for the church PC

1. Open the Theme Designer and load a theme with one container, then one with
   sixteen. Confirm sixteen boxes, the strip count, and that **+** is disabled
   at sixteen.
2. Drag a container and resize it from a corner. Confirm the Preview and the
   JSON tab update, and that the geometry fields show the new X/Y/W/H.
3. Move a container with `width: "auto"` or a `%` size on one axis only.
   Confirm Width/Height still show `auto`/`%` afterwards, and the untouched
   offset still shows its authored form.
4. Click overlapping containers on the canvas, then in the strip, then choose
   one in the left **Container** dropdown. All three must agree; the canvas
   must highlight the same box.
5. Set a container to 12×12 px at the top-left and another at the
   bottom-right. Confirm both are visible, selectable, and resizable.
6. Delete until one container remains; confirm delete is disabled. Duplicate
   at sixteen; confirm duplicate/add are disabled.
7. Drag a strip row to reorder. Confirm the canvas paint order and the JSON
   `layer` values change together.
8. Add unknown keys at theme, container and block level in the JSON tab, press
   **Apply**, then drag a box and edit a field. Confirm the unknown keys are
   still present in the JSON, then **Save**, reopen the theme, and confirm they
   survived the file round-trip.
9. On the Blocks page, select `text`, `reference` and `translation`: the Split
   section must appear. Select `body` and `verse_num`: it must not. Toggle split
   off/on and switch `by` between Line and Word; confirm `entry` and unknown
   block/split keys remain.
10. Narrow the left column to about 240 px. Confirm there is no horizontal
    scrollbar, the block tabs wrap without overlapping the first row, the Split
    section fits, and the four-side fields read `Unset` rather than a clipped
    `Not ...`.
11. Repeat at 100%, 125% and 150% Windows display scaling. Check that canvas
    handles remain grabbable, dropdowns open fully inside the window, and no
    native-looking dialogs appear.
12. Save and reload the theme; confirm geometry, layer order, visibility and
    split persist. Then check the same theme in OBS: the boxes must land on the
    same pixels as the Preview.

If a geometry value looks wrong, the first thing to capture is the theme JSON
(`position`, `width`, `height`) and the canvas field values together; the
converter is the only place that maps between them.
