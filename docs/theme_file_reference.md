# RhemaCast Theme File Property Reference

**Schema version:** 2
**Authoritative code:** `core/theme_schema.py`
**Shared-file resolver:** `core/theme_shared.py`
**Renderer:** `display/display.js` and `ui/widgets/display_view.py`

This is the exhaustive key-by-key catalog of a RhemaCast theme JSON. It covers
the top-level document, canvas, animation library, containers, every block, and
the `themes/_shared/` reference files. `docs/theme_schema_v2.md` explains the
design and rationale; this file is the lookup table for implementing Lite and
Theme Designer.

> **Maintenance contract.** Any change that adds, removes, renames, changes the
> default of, or changes the validation of a theme property must update this
> file in the same change. A property that exists in `core/theme_schema.py` but
> not here is a documentation bug.

## Notation

- `px` means a JSON number or a string such as `"24px"`.
- `%` means a string such as `"50%"`; percentages resolve against the design
  canvas unless a row says otherwise.
- `em` means a string such as `"0.15em"`.
- Colors accept a named CSS color from the schema allowlist, hex
  (`#rgb`, `#rgba`, `#rrggbb`, `#rrggbbaa`), `rgb()/rgba()`, `hsl()/hsla()`,
  and `inherit` where noted. `@name` is a palette token.
- A **paint** is a color, `transparent`, `none`, or a validated
  `linear-gradient(...)` / `radial-gradient(...)`.
- A **length** is a number (px) or a string with an allowed unit.
- Unknown keys are ignored and reported as notes; the resolved theme contains
  only documented properties.

## 1. Theme document top level

| Property | Type | Default | Rules |
|---|---|---|---|
| `schema_version` | integer | `1` when absent | Current version is `2`. Absent or `1` runs v1 migration. A value above `2` is fatal and returns `SAFE_THEME`. Numeric strings are accepted. |
| `name` | string | filename stem | Max 64. Must match `^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$`. Loader supplies the filename stem when the key is absent. |
| `label` | string | `name` | Max 120. Human-facing theme name. |
| `description` | string | `""` | Max 500. |
| `author` | string | `""` | Max 120. |
| `kind` | enum | folder kind | `scripture` or `freeform`. The folder (or loader argument) is authoritative; a disagreeing value only warns. New themes must use the matching folder. |
| `canvas` | object | see §2 | Design surface and background. |
| `containers` | array | `[{"id":"main"}]` | 1–16 containers. An object map is repaired to an array. More than 16 are truncated. Duplicate IDs get an `_index` suffix. |
| `animations` | object | `{}` | Named animation definition library; see §3. Definitions are validated here and referenced by name from slots. |
| `slide` | object | absent | Freeform presentation switches; see §1.1. |

Any other top-level key is dropped from the resolved theme and reported as a
note. Save/round-trip the **raw** document if the designer must preserve
authoring-only metadata.

### 1.1 `slide`

| Property | Type | Default | Rules |
|---|---|---|---|
| `show_title` | boolean | `true` | Only meaningful for freeform themes. Read by `theme_show_title()`; scripture themes ignore it. The `title` block remains the data source. |

## 2. `canvas`

| Property | Type | Default | Rules |
|---|---|---|---|
| `width` | integer | `1920` | 320–7680. Design-space width. |
| `height` | integer | `1080` | 240–4320. Design-space height. |
| `background` | paint | `transparent` | Color or safe gradient. `@palette` tokens expand here. |
| `fit` | enum | `contain` | `contain` scales the design canvas into the output; `none` uses the output viewport without canvas scaling. |

## 3. Animation library (`animations`)

`animations` maps a definition name to a definition object. Names must match
`^[A-Za-z_][A-Za-z0-9_-]{0,63}$`. Names are resolved for slots in this order:
**local theme definitions → `themes/_shared/animations.json` → built-in
definitions**. Local wins.

### 3.1 Definition properties

| Property | Type | Default | Applies to | Rules |
|---|---|---|---|---|
| `type` | enum | required | all | `fade_in`, `fade_out`, `fade_up`, `fade_down`, `scale_up`, `scale_down`, `slide_up`, `slide_down`, `typewriter`, `custom`. Unknown types drop the definition. |
| `label` | string | definition name | all | Max 80. Designer-facing label. |
| `duration_ms` | integer | `600` | all | 0–5000. Required for authored definitions; omission warns and falls back to 600. Built-in typewriter is 900. |
| `delay_ms` | integer | `0` | all | 0–5000. |
| `easing` | enum / string | `ease-out` (`linear` for typewriter) | all | `ease-out`, `ease-in`, `ease-in-out`, `linear`, `spring`, `smooth`, or a `cubic-bezier(a,b,c,d)` string. |
| `origin` | enum | `center` | presets, custom | `center`, `top`, `bottom`, `left`, `right`, `top left`, `top right`, `bottom left`, `bottom right`. |
| `keyframes` | array | preset frames | custom only | 2–8 frames. Required for `custom`; presets with keyframes are dropped; typewriter ignores and warns. |
| `reveal` | enum | `char` | typewriter | `char` or `word`. |
| `cursor` | object / string | default cursor | typewriter | `"none"`, `"default"`, or a cursor object; see §3.3. |

Built-in names: `fade_in`, `fade_out`, `fade_up`, `fade_down`, `scale_up`,
`scale_down`, `slide_up`, `slide_down`, `typewriter`. Presets generate their
own keyframes. Preset definitions cannot be overridden by authoring keyframes.

`typewriter` is only meaningful on text-bearing blocks, never for an `out`
phase, and the renderer falls back to a fade when the target is outlined or
otherwise incompatible.

### 3.2 Keyframe properties (`keyframes[]`, custom only)

| Property | Type | Default | Rules |
|---|---|---|---|
| `at` | number | required | 0–100, strictly increasing; first must be `0`, last must be `100`. |
| `opacity` | number / `"base"` | omitted | 0–1. `"base"` uses the element's resting opacity. |
| `translate_x` | length | `0` | px or `%`, clamped to ±2000. |
| `translate_y` | length | `0` | px or `%`, clamped to ±2000. |
| `scale` | number | `1` | 0.01–4. |
| `rotate` | number | `0` | Degrees, −1080–1080. |
| `blur` | length / `"base"` | `0` | 0–60 px. `"base"` uses the element's resting blur. |

### 3.3 Typewriter cursor

`cursor: "none"` disables the cursor. `cursor: "default"` or an omitted cursor
uses the default object. An object supports:

| Property | Type | Default | Rules |
|---|---|---|---|
| `char` | string | `▌` | Max 2 characters; empty falls back to `▌`. |
| `color` | color | `currentColor` | `currentColor` or a validated color; `@palette` expands. |
| `blink_ms` | integer | `500` | 0–2000. |
| `hide_after_ms` | integer | `600` | 0–5000. |

## 4. Animation assignments

Container and block `animation` values use the same assignment grammar.

| Property | Type | Default | Rules |
|---|---|---|---|
| `animation` | object / `"none"` | absent | `"none"` or `{}` disables animation. A string other than `"none"` is invalid. |
| `entry` | slot | absent | Runs when the element first appears. |
| `transition` | object / slot | absent | `{"in": slot, "out": slot}`; a single slot is treated as `transition.in`. |
| `transition.in` | slot | absent | Runs when content changes while the element is visible. |
| `transition.out` | slot | absent | Runs before replacement content is shown. |
| `out` | slot | absent | Runs when the element is cleared/hidden. |

`transition` accepts the sub-keys `in` and `out`, both optional. A **slot** is one of:

1. A definition name string: `"fade_up"`.
2. An object `{ "use": "name", "duration_ms": ..., "delay_ms": ..., "easing": ... }`.
   Only those four keys are read; the three overrides are optional.
3. An inline definition object with a `type` and its definition properties.
4. `"none"` to disable that phase.

Unknown slot names fall back to `fade_in` (`fade_out` for out phases) with a
warning. `split` is only valid on block animations, not on a container or
`body` animation; those are dropped with a note.

The resolved theme's `animations` map contains **only definitions actually
referenced by slots** (and by split `first`/`rest` slots). It is not a copy of
the authored library. A Theme Designer round-trip must preserve the raw
document/library.

### 4.1 `split` — per-line and per-word units

`animation.split` recomputes units on every render, after autofit and wrapping.

| Property | Type | Default | Rules |
|---|---|---|---|
| `by` | enum | `line` | `line` groups the browser's rendered line boxes; `word` wraps whitespace tokens. |
| `stagger_ms` | integer | `70` | 0–2000. Unit *i* starts at the slot's delay + `i * stagger_ms`; total delay is capped at 5000 ms. |
| `first` | assignment | absent | Partial assignment for unit 0. Omitted phases inherit from the parent assignment. Nested `split` is rejected. |
| `rest` | assignment | absent | Partial assignment for units 1..n. Omitted phases inherit from the parent assignment. |
| `look` | object | absent | Resting per-unit style; see below. |
| `look.first` | object | absent | Look for unit 0. |
| `look.rest` | object | absent | Look for units 1..n. |

`look.first` / `look.rest` fields:

| Property | Type | Default | Rules |
|---|---|---|---|
| `color` | color | block color | `@palette` expands. |
| `weight` | integer | block weight | 100–900. |
| `font_style` | enum | `normal` | `normal` or `italic`. |
| `text_decoration` | enum | `none` | `none`, `underline`, `line-through`. |
| `opacity` | number | `1` | 0–1. This is the resting style; a running animation owns `opacity` until it finishes. |
| `letter_spacing` | length | `0` | px or `em`, −20–40. |

Split applies to `text`, `reference` (and freeform `title`), and `translation`.
It is dropped from containers and `body`; `verse_num` is not a split target.
`entry` and `transition.in` run per unit; `out`/`transition.out` always run on
the whole block. Split is skipped, falling back to the whole-block assignment,
when the block has `text_outline`, `max_lines`, `<br>`/`<sup>`/`<sub>`, a
typewriter phase, or more than 160 units.

Line grouping uses the real rendered line boxes; the first rendered line is
always unit 0. Word units are whitespace tokens. The verse number is folded
into the first line rather than becoming its own unit.

## 5. Containers (`containers[]`)

| Property | Type | Default | Rules |
|---|---|---|---|
| `id` | string | `container{index}` | `^[a-z][a-z0-9_-]{0,31}$`. Must be unique; duplicates get `_index`. |
| `label` | string | `id` | Max 80. Designer-facing layer name. |
| `kind` | enum | theme kind | `scripture`, `freeform`, or `any`. Which blocks are legal is decided by the **theme** kind. |
| `layer` | integer | `index * 10` | 0–100. Paint/render order. |
| `visible` | boolean | `true` | Hidden containers are not painted. Freeform renders only its first visible container; later visible containers are forced hidden. |
| `position` | object | `{anchor:"center"}` | See §5.1. |
| `width` | length | `"auto"` | px, `%`, or `"auto"`. |
| `height` | length | `"auto"` | px, `%`, or `"auto"`. |
| `min_width` | length | `0` | px or `%`, 0–7680. |
| `max_width` | length / null | `null` | px or `%`, 0–7680. |
| `min_height` | length | `0` | px or `%`, 0–4320. |
| `max_height` | length / null | `null` | px or `%`, 0–4320. |
| `background` | paint | `transparent` | Color, gradient, `transparent`, or `none`. `@palette` expands. |
| `border` | string / object / shared | `"none"` | See §5.2. |
| `border_radius` | length | `null` | px or `%`, 0–400. When set, it wins over `border.radius`. |
| `box_shadow` | string / object / shared | `"none"` | See §5.3. |
| `backdrop_filter` | string | `"none"` | `"none"`, `"off"`, or a validated function list; see §5.4. |
| `opacity` | number | `1` | 0–1 for the whole container. |
| `overflow` | enum | `hidden` | `hidden` or `visible`. |
| `animation` | assignment | absent | Container-level phases; see §4. A container split is dropped. |
| `blocks` | object | `{}` | Map of block ID → block object; see §6. Missing `body` is injected with defaults. |

Container `padding`, `display`, `flex_direction`, `justify_content`, and
`align_items` are not v2 parameters. Padding belongs on `blocks.body`; the
legacy flex keys are ignored with a warning.

### 5.1 `position`

| Property | Type | Default | Rules |
|---|---|---|---|
| `anchor` | enum | `center` | `top_left`, `top_right`, `bottom_left`, `bottom_right`, `center`, `left`, `right`, `top`, `bottom`, `fill`. |
| `x` | length | see table | px or `%`, −10000–10000. |
| `y` | length | see table | px or `%`, −10000–10000. |

For v1-style files, boolean corner keys (`top_left`, `top_right`,
`bottom_left`, `bottom_right`) are accepted; the first in that fixed order wins
when `anchor` is absent, and extras warn. `anchor` always wins over corner
booleans.

Anchor placement, with canvas `W×H` and container `w×h`:

| Anchor | Horizontal | Vertical |
|---|---|---|
| `top_left` | `left = x` (default 0) | `top = y` (default 0) |
| `top_right` | `right = x` (default 0) | `top = y` (default 0) |
| `bottom_left` | `left = x` (default 0) | `bottom = y` (default 0) |
| `bottom_right` | `right = x` (default 0) | `bottom = y` (default 0) |
| `center` | `left = (W - w)/2 + x` | `top = (H - h)/2 + y` |
| `left` | `left = x` (default 0) | `y` given → `top = y`; else centered |
| `right` | `right = x` (default 0) | `y` given → `top = y`; else centered |
| `top` | `x` given → `left = x`; else centered | `top = y` (default 0) |
| `bottom` | `x` given → `left = x`; else centered | `bottom = y` (default 0) |
| `fill` | `left = 0`, `width = W` | `top = 0`, `height = H` |

`fill` ignores `width`, `height`, `x`, and `y` with a warning. Percentages use
the design canvas (`canvas.width` / `canvas.height`). “Given” means the key is
present and not `null`; an explicit `0` counts.

### 5.2 `border`

Accepted forms:

1. `"none"` (or `"off"`).
2. A CSS-like string with 2–4 tokens: width, style, and optional color.
3. An object:

| Property | Type | Default | Rules |
|---|---|---|---|
| `width` | number | `1` | 0–40 px. Omitted base width paints `1px`; an explicit `0` disables the base while `sides` may still set their own. |
| `style` | enum | `solid` | `none`, `solid`, `dashed`, `dotted`, `double`, `groove`, `ridge`, `inset`, `outset`. |
| `color` | color | `currentColor` | Supports `@palette`. |
| `radius` | length | `0` | 0–400 px. No percent. |
| `sides` | object | absent | Per-side overrides; see below. |

4. A shared reference: `{ "shared": "gold_frame" }`.

`sides` may contain `top`, `right`, `bottom`, and `left`. Each is an object with
any subset of `width` (0–40), `style` (same enum), `color` (same rules), and
`radius` (0–400). Unspecified sides fall back to the base border.

### 5.3 `box_shadow`

Accepted forms: `"none"`, a CSS shadow string, a shared reference
`{ "shared": "soft" }`, or an object:

| Property | Type | Default | Rules |
|---|---|---|---|
| `x` | number | `0` | −500–500 px. |
| `y` | number | `0` | −500–500 px. |
| `blur` | number | `0` | 0–500 px. |
| `spread` | number | `0` | −500–500 px. |
| `color` | color | `rgba(0,0,0,0.5)` | Supports `@palette`. |
| `inset` | boolean | `false` | Inner shadow. |

A shadow string may contain 1–12 comma-separated shadows. Each needs 2–4
lengths, at most one `inset`, and exactly one color; invalid shadows are
rejected.

### 5.4 `backdrop_filter`

`"none"`, `"off"`, or a space-separated list of allowlisted functions. Only
these are accepted:

| Function | Argument | Range |
|---|---|---|
| `blur` | px | 0–60 |
| `brightness` | number or `%` | 0–4 |
| `contrast` | number or `%` | 0–4 |
| `saturate` | number or `%` | 0–8 |
| `grayscale` | number or `%` | 0–1 |
| `sepia` | number or `%` | 0–1 |
| `opacity` | number or `%` | 0–1 |
| `hue-rotate` | number or `deg` | −1080–1080 |

For percentage arguments on multiplier functions, `100%` equals `1`.

## 6. Blocks

Allowed blocks depend on the **theme** kind:

| Kind | Allowed blocks |
|---|---|
| `scripture` | `body`, `text`, `reference`, `translation`, `verse_num` |
| `freeform` | `body`, `title`, `text`, `translation`, `verse_num`; `reference` is accepted as an alias for `title` |

Blocks are validated in render order: `verse_num`, `title`, `reference`,
`translation`, `text`, `body`. This matters because `translation` inherits
typography from its anchor block. Unknown blocks warn and are ignored;
duplicate canonical blocks keep the first. Missing `body` is added with
defaults.

### 6.1 `body`

| Property | Type | Default | Rules |
|---|---|---|---|
| `visible` | boolean | `true` |  |
| `valign` | enum | `center` | `top`, `center`, `bottom`. |
| `gap` | length | `0` | 0–200 px between body children. |
| `padding` | length | `0` | 0–400 px; all sides. |
| `padding_top` | length | inherits `padding` | 0–400 px. |
| `padding_right` | length | inherits `padding` | 0–400 px. |
| `padding_bottom` | length | inherits `padding` | 0–400 px. |
| `padding_left` | length | inherits `padding` | 0–400 px. |
| `animation` | assignment | absent | Body-level phases; split is dropped. |

Typography or layout keys on `body` are inert and warned.

### 6.2 Shared block properties

These apply to `text`, `reference`/`title`, `translation`, and `verse_num`
unless a block-specific table below overrides the default.

| Property | Type | Default | Rules |
|---|---|---|---|
| `visible` | boolean | `true` |  |
| `color` | color | `#f8fafc` | Supports `inherit` and `@palette`. |
| `font_family` | string | `'Nunito', sans-serif` | Supports `inherit`; safe family list only. |
| `size` | length | `40` | 1–400; px, `em`, or `inherit`. |
| `min_size` | length | `4` | 1–400; px only. Autofit floor. |
| `max_size` | length | `300` | 1–400; px only. Autofit ceiling. |
| `weight` | integer | `700` | 100–900. |
| `line_height` | number | `1.2` | 0.5–3. Unitless multiplier. |
| `letter_spacing` | length | `-0.01em` | px or `em`, −20–40. |
| `word_spacing` | length | `0` | px or `em`, −20–40. |
| `text_shadow` | string / object | `none` | Same parser as box shadow. Shared references are not expanded on block text shadows; use a literal shadow. |
| `text_outline` | string | `none` | `"none"`, `"off"`, or a width (`px` or `em`) followed by a color. Color supports `@palette`. |
| `text_transform` | enum | `none` | `none`, `uppercase`, `lowercase`, `capitalize`. |
| `text_align` | enum | `center` | `left`, `center`, `right`, `justify`. |
| `font_style` | enum | `normal` | `normal`, `italic`. |
| `text_decoration` | enum | `none` | `none`, `underline`, `line-through`. |
| `opacity` | number | `1` | 0–1. |
| `max_lines` | integer / null | `null` | 1–20. Renderer clamp; split falls back to whole-block when set. |
| `direction` | enum | `ltr` | `ltr`, `rtl`. |
| `margin_top` | length | `0` | px or `em`, −400–400. |
| `margin_right` | length | `0` | px or `em`, −400–400. |
| `margin_bottom` | length | `0` | px or `em`, −400–400. |
| `margin_left` | length | `0` | px or `em`, −400–400. |
| `padding` | length | `0` | 0–400 px; all sides. |
| `padding_top` | length | inherits `padding` | 0–400 px. |
| `padding_right` | length | inherits `padding` | 0–400 px. |
| `padding_bottom` | length | inherits `padding` | 0–400 px. |
| `padding_left` | length | inherits `padding` | 0–400 px. |
| `animation` | assignment | absent | Text-bearing blocks accept `split`; see §4.1. |

### 6.3 `text`

`text` uses the shared defaults plus:

| Property | Type | Default | Rules |
|---|---|---|---|
| `autosize` | boolean | `true` | Shrinks/grows between `min_size` and `max_size` to fit the body content box. |
| `margin_bottom` | length | `24` | px or `em`. |
| `text_shadow` | string / object | `0 4px 12px rgba(0,0,0,0.4)` |  |

`min_size` is the floor autofit may not cross. A long verse still clips if the
container cannot fit that floor; size the container for the tested worst case.

### 6.4 `reference` / `title`

`title` is freeform-only and uses the same shape and defaults as `reference`;
in freeform, `reference` is an alias for `title`.

| Property | Type | Default | Rules |
|---|---|---|---|
| `position` | enum | `below_verse` | `above_verse` or `below_verse`. |
| `color` | color | `#94a3b8` |  |
| `font_family` | string | `'DM Sans', sans-serif` |  |
| `size` | length | `24` |  |
| `weight` | integer | `500` |  |
| `letter_spacing` | length | `0.1em` |  |
| `text_transform` | enum | `uppercase` |  |

### 6.5 `translation`

| Property | Type | Default | Rules |
|---|---|---|---|
| `position` | enum | `right_of_reference` | `above_verse`, `below_verse`, `above_reference`, `below_reference`, `left_of_reference`, `right_of_reference`. |
| `color` | color | `#64748b` |  |
| `margin_left` | length | `8` | px or `em`. |

Typography inheritance: when `position` is one of the four `*_reference`
values, `font_family`, `size`, `weight`, `line_height`, `letter_spacing`,
`text_transform`, and `font_style` inherit from `reference`/`title`. For
`above_verse` / `below_verse`, they inherit from `text`. Explicit block values
always win. Color, shadows, opacity, and margins are not inherited.

### 6.6 `verse_num`

| Property | Type | Default | Rules |
|---|---|---|---|
| `mode` | enum | `inline` | `inline` or `block`. |
| `position` | enum | `above_verse` | `above_verse` or `below_verse`; meaningful for block mode. |
| `vertical_align` | enum | `top` | `top`, `middle`, `baseline`, `bottom`. |
| `margin_right` | length | `0.15em` | 0–40; px or `em`. |
| `size` | length | `0.6em` |  |
| `weight` | integer | `700` |  |
| `opacity` | number | `0.7` |  |
| `line_height` | number | `1` |  |
| `color` | color | `inherit` |  |
| `font_family` | string | `inherit` |  |

### 6.7 Block default matrix

Values are the resolved defaults; **inherited** means the translation block takes that value from `reference`/`title` at its default position.

| Property | `text` | `reference` / `title` | `translation` | `verse_num` |
|---|---|---|---|---|
| `color` | `#f8fafc` | `#94a3b8` | `#64748b` (or inherited) | `inherit` |
| `font_family` | `'Nunito', sans-serif` | `'DM Sans', sans-serif` | inherited | `inherit` |
| `size` | `40` | `24` | inherited | `0.6em` |
| `min_size` | `4` | `4` | `4` | `4` |
| `max_size` | `300` | `300` | `300` | `300` |
| `weight` | `700` | `500` | inherited | `700` |
| `line_height` | `1.2` | `1.2` | inherited | `1` |
| `letter_spacing` | `-0.01em` | `0.1em` | inherited | `-0.01em` |
| `word_spacing` | `0` | `0` | `0` | `0` |
| `text_shadow` | `0 4px 12px rgba(0,0,0,0.4)` | `none` | `none` | `none` |
| `text_outline` | `none` | `none` | `none` | `none` |
| `text_transform` | `none` | `uppercase` | inherited | `none` |
| `text_align` | `center` | `center` | `center` | `center` |
| `font_style` | `normal` | `normal` | inherited | `normal` |
| `text_decoration` | `none` | `none` | `none` | `none` |
| `opacity` | `1` | `1` | `1` | `0.7` |
| `max_lines` | `null` | `null` | `null` | `null` |
| `direction` | `ltr` | `ltr` | `ltr` | `ltr` |
| `margin_bottom` | `24` | `0` | `0` | `0` |
| `margin_left` | `0` | `0` | `8` | `0` |
| `padding` | `0` | `0` | `0` | `0` |
| `position` | — | `below_verse` | `right_of_reference` | `above_verse` |
| `mode` | — | — | — | `inline` |
| `vertical_align` | — | — | — | `top` |
| `margin_right` | — | — | — | `0.15em` |
| `autosize` | `true` | — | — | — |

## 7. Shared files (`themes/_shared/`)

Shared files are never listed as themes. They use `schema_version: 2` and are
validated by the same rules as inline values.

| File | Entry key | Entry type | Referenced by |
|---|---|---|---|
| `borders.json` | `borders` | border value (object or CSS string) | `containers[].border` as `{ "shared": "name" }` |
| `shadows.json` | `shadows` | shadow value (object or CSS string) | `containers[].box_shadow` as `{ "shared": "name" }` |
| `palettes.json` | `colors` | color string or `@other` | `@name` in color/paint fields |
| `animations.json` | `animations` | animation definition | Slot names (`use` or a bare name string) |

Rules:

- Shared names use `^[A-Za-z_][A-Za-z0-9_-]{0,63}$`.
- A shared border/shadow cannot reference another shared entry of its own
  family; palette entries may chain, up to depth 4, with cycle detection.
- Border/shadow references search their own family first. If the name is not
  there, the other family is checked; a cross-family hit warns.
- Animation names have **no** cross-family fallback. Resolution order is local
  theme → shared animations → built-in.
- `@name` expands in block `color`, canvas/container `background`,
  `border.color`, `box_shadow.color`, the color component of `text_outline`,
  and animation cursor colors. It is **not** expanded inside gradient strings or shadow
  strings.
- Missing/broken shared files are treated as empty; unresolved references fall
  back to the field default with a warning.
- Shared files are cached by mtime and invalidated by palette edits.

## 8. Validation and resolution

`normalize_theme(raw, kind=None, name=None)` returns `(resolved, report)` and
never mutates the input.

1. If `schema_version` is absent or `1`, `core.theme_migrate.migrate_v1_to_v2`
   converts legacy shapes. Version `2` is validated as-is; a future version is
   fatal.
2. Shared references and palette tokens are expanded on a deep copy.
3. The top level, canvas, containers, blocks, and animation definitions are
   validated, defaulted, clamped, and sanitized.
4. Animation slot names are resolved; only referenced definitions remain in the
   resolved `animations` map.
5. The resolved dict is safe to hand to the renderer. On a fatal error the
   result is `SAFE_THEME`.

Coercion behavior:

- Numeric fields accept JSON numbers and numeric strings; values ending in
  `px` are accepted where a length is expected. Out-of-range values clamp and
  warn.
- Booleans written as `"true"`/`"false"` are accepted with a warning.
- Invalid enum values fall back to the documented default and warn.
- Strings are stripped, control/format characters removed, and truncated at
  their field limit.
- Colors and CSS values are allowlisted. `url(`, `var(`, `expression`,
  `javascript:`, `@import`, braces, semicolons, and HTML are rejected.
- Unknown keys are dropped from the resolved theme and reported as notes;
  unknown block/container/top-level shapes never reach the renderer.

Current limits: name 64, label 120, description 500, author 120, container
label 80, animation label 80, 16 containers, 2–8 keyframes, 12 shadows per
shadow value.

### 8.1 V1 files

A missing/`1` `schema_version` is migrated automatically. New themes must be
written in the v2 shape in §1–§7. The migration supports legacy flat
top-level/block shapes; see `docs/theme_schema_v2.md` §7 for the full v1
mapping. Do not add new code paths that write v1.

## 9. Lite and Theme Designer checklist

- Persist and round-trip the **raw** theme document. The resolved document
  drops unknown keys and unreferenced animation definitions.
- Write `schema_version: 2` and put the file in the folder matching `kind`
  (`themes/scripture/` or `themes/freeform/`).
- Treat `core/theme_schema.py` as the validator. Do not reimplement defaults or
  ranges in the UI; call `normalize_theme` and display its `ThemeReport`
  warnings/notes.
- Keep animation libraries in the raw document. The resolved `animations` map
  only contains definitions used by slots.
- Offer `split` only on text-bearing block animations. Units are recomputed at
  render time, so line counts are content-dependent; design must not assume a
  fixed count.
- Use shared references for borders/shadows and `@palette` tokens for colors.
  Do not use `{ "shared": ... }` for block `text_shadow`; it is not expanded
  there.
- Freeform: only the first visible container renders; `slide.show_title`
  controls the title toggle; `reference` is an alias for `title`.
- Verify any new property against `display/display.js` **and**
  `ui/widgets/display_view.py`; both renderers must agree.
