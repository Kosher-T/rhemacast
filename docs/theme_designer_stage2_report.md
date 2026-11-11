# Theme Designer — Stage 2 report

## What was built

**`ui/widgets/theme_designer/property_editor.py`** — `ThemePropertyEditor`,
a schema-driven replacement for `ThemePropertiesPanel` in the Designer tab.
Every row is described by a small spec (`key path`, `label`, widget kind); the
widgets are Stage 1 kit families (`PropertyRow`, `NumberField`, `ColorField`,
`PaintField`, `BorderField`, `ShadowField`, `FourSideField`, `ChipSelect`,
`CompactDropdown`, `SegmentedToggle`, `Switch`, `TextInput`, `BlockTabBar`).
No per-property UI code and no native dialogs.

Pages: **Canvas**, **Container** (all keys except `position`/`width`/`height`),
**Blocks** (`body`, `text`, `reference`/`title`, `translation`, `verse_num`,
filtered by theme kind the way the validator filters them).

**Raw-document editing.** The editor deep-copies the document it is given and
writes only touched leaves. Unknown top-level, container and block keys,
sibling containers, the animation library and `themes/_shared` references all
survive load → edit → save. This is the M1-06 fix: the old panel rebuilt
managed blocks from scratch; the new editor never replaces a dict it did not
edit.

**Validation.** Defaults are never declared in the UI. Each edit calls
`normalize_theme` and shows the validator's own message for the edited key in
the panel footer. Numeric limits are therefore enforced in one place; the raw
document keeps what was typed until the schema normalises it.

**Designer tab** (`ui/tabs/theme_designer_tab.py`):

- left column now uses `ThemePropertyEditor` (260 px, tolerant down to ~240);
- the three-screen multi preview is replaced by **one** `ThemePreview` plus the
  Stage 1 `SampleInjector` (Shortest / Medium / Longest);
- preview updates are debounced (80 ms) so dragging a value does not reflow the
  document on every change;
- the JSON panel is editable again with an **Apply** button; JSON is the whole
  raw document, so applying it keeps every key, and the GUI reloads from it.
  Invalid JSON is ignored rather than destroying the last good document;
- animations panel and container canvas editor are untouched, marked
  `# STAGE 3` where they meet this work.

**Schema constants.** `core/theme_schema.py` now exports the enum tuples it
already enforced (`FIT_MODES`, `OVERFLOWS`, `VALIGNS`, `TEXT_ALIGNS`,
`TEXT_TRANSFORMS`, `FONT_STYLES`, `TEXT_DECORATIONS`, `DIRECTIONS`,
`VERTICAL_ALIGNS`, `REFERENCE_POSITIONS`, `TRANSLATION_POSITIONS`,
`VERSE_MODES`). The validator's inline literals were replaced with them, so the
UI imports the same lists instead of copying them.

## Stage 1 answers, reconciled with the schema

1. **Shadow structured shape — partially possible.** `core/theme_schema.py`
   stores a *single* shadow as an object `{x, y, blur, spread, color, inset}`,
   but it has **no array shape**: a multi-shadow value is only accepted as a
   CSS string. `ShadowField(..., structured=True)` therefore emits the object
   for one layer and falls back to the validator-accepted CSS string for two or
   more layers. This differs from "structured layer list" in your answer; the
   schema won.
2. **Border sides** already use partial side objects (`{width}` etc.), matching
   the validator; unchanged.
3. **FourSideField / padding** — the schema stores *flat* keys (`padding`,
   `padding_top`, `padding_right`, `padding_bottom`, `padding_left`), not a
   nested object, so flat emission is the schema shape. Nested would have been
   wrong.
4. **Block tabs** — five blocks wrap to two rows via `BlockTabBar`; no scroll,
   no overflow menu.
5. **AnimationPhaseCard** — not touched here; it is a Stage 3 hook.

## Deviations

- **`backdrop_filter`** is a text field showing the validator's message rather
  than a per-function argument editor. The Stage 1 kit has no widget for
  function arguments; chips alone would lose them. This is the smallest
  addition and is listed in the mapping doc.
- **`border.sides`** is edited through `BorderField`'s side editor; the mapping
  does not add a second row for it.
- **`id`** is read-only in the container page (renaming would orphan blocks).
- The old `ThemePropertiesPanel` still exists for callers outside this tab
  (Quick/Lite Designer); only the Theme Designer tab was rewired.
- The single-preview toggle still says "Preview" instead of "Multi Preview";
  the layout (left / centre / right) is unchanged.

## Verification

- `tests/test_theme_designer_stage2.py` — 7 tests: untouched round-trip,
  canvas+container group edits, every block group, structured shadow objects,
  validator-message surfacing, group reachability, clean normalisation.
- `py_compile` over the editor, tab and schema; the tab module imports under
  `QT_QPA_PLATFORM=offscreen`.
- Full theme suite: **491 passed, 6 failed**. All six reproduce with the
  unmodified HEAD schema (verified by swapping it in and re-running): three
  Lite Designer preview tests (the M1-07 backlog) and three `test_slides_theme`
  tests that read theme JSON fixtures missing v2 keys (`min_size`,
  `text_transform`, `containers`). None are caused by this work.
- Stage 0: the Stage 1 popover close bug was reproduced and fixed on a real
  Xwayland display — constructor-time window flags (transient parent survives)
  plus one-event press suppression, then verified open / inside click /
  second-click close / Esc / reopen / outside press.
- Existing `tests/test_theme_v2_designer_roundtrip.py` still targets the old
  panel and is untouched.

- Real-display check at a forced 240 px left column found and fixed three
  defects: old page rows stayed parented and painted over the new page
  after a rebuild; 8 px side margins caused a horizontal scrollbar
  (now 4 px); and block enum chips clipped their labels (block enums now
  use the compact dropdown, canvas Fit keeps chips). The v1 container
  geometry panel also crashed on v2 object values and now blanks them
  until Stage 3 replaces it.

**Not verified:** Windows rendering (no Windows machine); the Designer tab was
not booted headlessly because its preview embeds QtWebEngine, which aborts in
the offscreen platform (documented in AGENTS.md). The editor widget itself is
exercised headlessly by the tests. Real-display behaviour of the new panel was
not visually reviewed.

## What Stage 3 needs

- `ThemePropertyEditor` exposes `set_field(dotted_path, value)` and
  `field_paths()`, so the animation/split UI can drive the same raw document.
- Animation slots, `split`, container geometry and the animation library are
  untouched; the tab marks the three hook points with `# STAGE 3`.
- The preview is a single `ThemePreview` with `set_verse(sample_id)`;
  Stage 3 can add a replay control next to the sample injector without new
  panels.
- Shadow multi-layer values remain CSS strings because the schema has no list
  shape; if Stage 3 wants structured multi-layer shadows, the schema must grow
  that shape first.
