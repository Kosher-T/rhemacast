# Theme Designer — Stage 2 property mapping

Scope: every v2 property **except** animations, `animation.split` and the
container canvas geometry editor (`position`, `width`, `height`), which remain
Stage 3. Canvas width/height are included because they are document data.

Implementation: `ui/widgets/theme_designer/property_editor.py`
(`ThemePropertyEditor`), wired into `ui/tabs/theme_designer_tab.py`.

## How ranges, options and defaults are sourced

- **Options (enums)** come from `core/theme_schema.py`, which now exports the
  tuples its validator uses: `FIT_MODES`, `OVERFLOWS`, `VALIGNS`,
  `TEXT_ALIGNS`, `TEXT_TRANSFORMS`, `FONT_STYLES`, `TEXT_DECORATIONS`,
  `DIRECTIONS`, `VERTICAL_ALIGNS`, `REFERENCE_POSITIONS`,
  `TRANSLATION_POSITIONS`, `VERSE_MODES`, plus `KINDS`, `BLOCK_IDS`.
- **Defaults** are never declared in the UI. The raw document is shown as
  authored; empty fields mean “inherit the schema default”, and
  `normalize_theme` supplies it.
- **Numeric limits** stay inside the schema's coercion calls. The editor does
  not clamp; after each edit it calls `normalize_theme` and shows the
  validator's message for that key. One limit, one place.

## 1. Canvas

| Key | Type | Source | Widget | Notes |
|---|---|---|---|---|
| `canvas.width` | integer 320–7680 | `coerce_number` | `NumberField(integer)` | |
| `canvas.height` | integer 240–4320 | `coerce_number` | `NumberField(integer)` | |
| `canvas.background` | paint | `_coerce_paint` | `PaintField` | `@palette` stays literal (`@name`), expanded only by the validator |

## 2. Container (except `position`, `width`, `height`)

| Key | Type | Source | Widget | Notes |
|---|---|---|---|---|
| `id` | string | `_ID_RE` | `TextInput` (read-only) | renaming would orphan blocks |
| `label` | ≤80 chars | `clean_text` | `TextInput` | |
| `kind` | enum | `KINDS` (+`any`) | `CompactDropdown` | |
| `layer` | int 0–100 | `coerce_number` | `NumberField` | |
| `visible` | bool | `coerce_bool` | `Switch` | |
| `min_width`, `min_height` | length | `coerce_length` | `NumberField(units=["px","%"])` | |
| `max_width`, `max_height` | length \| null | `coerce_length` | same, nullable | empty = `null` |
| `background` | paint | `_coerce_paint` | `PaintField` | |
| `border` | string/object/shared | `_coerce_border` | `BorderField` | shared names from `themes/_shared/borders.json`; sides are partial objects |
| `border_radius` | length \| null | `coerce_length` | `NumberField` | wins over `border.radius` |
| `box_shadow` | string/object/shared | `_coerce_shadow` | `ShadowField(structured=True)` | one layer → object `{x,y,blur,spread,color,inset}`; ≥2 layers → CSS string (schema has no list shape) |
| `backdrop_filter` | string | `FILTER_FUNCS` | `TextInput` | the validator is the only parser of function arguments |
| `opacity` | number 0–1 | `coerce_number` | `NumberField(step=0.05)` | |
| `overflow` | enum | `OVERFLOWS` | `SegmentedToggle` | |

Legacy `padding`, `display`, `flex_*`, `justify_content`, `align_items` are
never written.

## 3. Blocks

Block list comes from `BLOCK_IDS[kind]`; freeform uses `title` (with
`reference` as the validator alias).

### 3.1 `body`

| Key | Widget |
|---|---|
| `visible` | `Switch` |
| `valign` | `SegmentedToggle` (`VALIGNS`) |
| `gap` | `NumberField` px |
| `padding` + 4 sides | `FourSideField(linked)` → **flat** keys (`padding`, `padding_top`, …) because that is the schema's stored shape |

### 3.2 `text`

| Key | Widget |
|---|---|
| `visible` | `Switch` |
| `color` | `ColorField` (`@palette`, `inherit`, `currentColor` kept as text) |
| `font_family` | `TextInput` |
| `size`, `min_size`, `max_size` | `NumberField` px/em |
| `autosize` | `Switch` |
| `weight` | `NumberField(step=100)` |
| `line_height` | `NumberField(step=0.05)` |
| `letter_spacing`, `word_spacing` | `NumberField` px/em |
| `text_shadow` | `ShadowField(allow_shared=False, structured=True)` — shared refs are not expanded on block shadows |
| `text_outline` | `TextInput` |
| `text_transform`, `font_style`, `text_decoration`, `direction` | enum widgets (`TEXT_TRANSFORMS`, `FONT_STYLES`, `TEXT_DECORATIONS`, `DIRECTIONS`) |
| `text_align` | `SegmentedToggle` (`TEXT_ALIGNS`) |
| `opacity` | `NumberField(step=0.05)` |
| `max_lines` | nullable `NumberField` |
| `margin_*` | `FourSideField(unlinked)` → `margin`, `margin_top`, … |
| padding | `FourSideField(linked)` |

### 3.3 `reference` / `title`

Shared typography rows plus `position` (`REFERENCE_POSITIONS`,
`SegmentedToggle`).

### 3.4 `translation`

`position` (`TRANSLATION_POSITIONS`, `CompactDropdown`), `color`,
`margin_left`, plus the inheritable typography rows the schema lists in
`INHERITABLE_TRANSLATION_FIELDS`.

### 3.5 `verse_num`

`mode` (`VERSE_MODES`), `position`, `vertical_align` (`VERTICAL_ALIGNS`),
`margin_right`, `size`, `weight`, `opacity`, `line_height`, `color`,
`font_family`.

## 4. `themes/_shared/`

| File | Use |
|---|---|
| `borders.json` | `BorderField.shared_options` → `{"shared": name}` (not expanded in the document) |
| `shadows.json` | `ShadowField.shared_options` |
| `palettes.json` | `ColorField` / `PaintField` palette swatches; values stay `@name` |
| `animations.json` | Stage 3 hook (animation library untouched) |

## 5. Properties with no widget (smallest addition)

| Property | Gap | Addition |
|---|---|---|
| `backdrop_filter` arguments | one argument per function | `TextInput`, validator message; a per-function editor would be a new composite |
| `text_outline` | width + colour in one string | `TextInput`; a split editor would be a new widget |
| multi-layer `box_shadow` | schema has no structured list | CSS string (validator-accepted); structured list needs a schema change |
| `border.sides` | already covered by `BorderField` | none |
| animation slots / `split` / canvas geometry | Stage 3 | marked `# STAGE 3` in the tab |

## 6. Your Stage 1 answers vs the schema

1. **Structured shadow** — implemented per the schema: object for one layer;
   multi-layer stays a CSS string because the schema has no array form. The
   schema won.
2. **Partial side objects** — already the shape `BorderEditor` emits.
3. **FourSideField** — the schema stores flat `padding*` keys, so flat is the
   schema shape; no nesting exists to preserve.
4. **Block tabs** — five tabs wrap to two 26 px rows via `BlockTabBar`.
5. **AnimationPhaseCard** — untouched; it is a Stage 3 hook, and keyframes stay
   in the document, not the card.
