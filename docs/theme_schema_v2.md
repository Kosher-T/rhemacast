# RhemaCast Theme Schema v2

Status: **Phase 1 specification (no code changed yet).**
Scope: theme file structure, Python loading/validation, display renderer.
Not in scope: Theme Designer restyling, deck/slide document format, media
themes, output routing.

This document is normative. Where it says MUST, the implementation is
expected to enforce it. Where the current code disagrees with this document,
the current code is the thing that changes in Phases 2–4.

---

## 0. Why this exists

Today a theme is mostly a bag of CSS custom properties for **one** box. The
renderer owns the box, the flex layout, the reference/translation line, the
verse-number styling, the autosize limits, and the placement rules. A theme
can restyle those things but cannot restructure them.

v2 makes the theme describe **what exists and where it is**:

- one or more containers, each with an id, a layer, a visibility flag,
  explicit geometry, and form/decoration;
- each container contains a subset of the content blocks (`body`, `text`,
  `reference`, `translation`, `verse_num`, and `title` for freeform);
- every block has the same typographic/spacing parameters;
- a small number of block-specific placement rules replace the hardcoded
  reference/translation/verse-number behavior;
- reusable borders, shadows, and named colors live in shared files.

Python resolves, validates, migrates, and fills defaults **once**. The
WebSocket payload carries a complete resolved v2 theme. `display.js` renders
that resolved theme and does not need to know v1 or fill defaults (it keeps a
defensive last-resort fallback only).

---

## 1. Findings: how the current system works

### 1.1 Discovery and loading

`core/theme_loader.py`:

- `_load_all()` walks `themes/**/*.json` with `Path.rglob`. The theme key is
  `theme["name"]` (falling back to the file stem). The kind is the first path
  part under `themes/` (`scripture`, `freeform`).
- `_paths` maps name → file; `_file_mtimes` powers `_check_for_changes()`,
  which reloads changed files.
- `get_theme(name)` returns the **raw JSON** (v1 today). The designer edits
  this raw dict.
- `resolve_theme(name, fallback)` returns `(name, raw_theme)`, with a per-kind
  fallback (`default` for scripture, `slides` for freeform). It is called on
  every payload build.
- `theme_container(theme_data, name=None)` returns the first container with
  nested blocks; it treats `containers` as a **dict** and returns `{}` for
  flat or legacy-absolute shapes.
- `save_theme()` writes the dict it is given, with no validation or
  normalization. `create_theme()` clones a raw theme.
- `slide_title_visible()` reads `theme["slide"]["show_title"]`.
- `theme_outline()` treats a hard `text_shadow` ring (8 offset copies, zero
  blur) as an outline, so old themes render an outline even though they only
  set `text_shadow`.
- `display_format_defaults()` maps the active container's `text` block onto
  the designer ribbon switches.

Consequence for `themes/_shared/`: because discovery is `rglob("*.json")` and
kind is the first path part, a `_shared` folder would be loaded as themes and
appear as a theme kind. Phase 2 MUST exclude any path part starting with `_`.

### 1.2 Resolution and the WebSocket payload

- `ui/tabs/presentation_tab.py::_build_payload` and
  `ui/tabs/slides_tab.py::_build_payload` call `resolve_theme()` and put the
  **raw theme dict** in `payload["theme_data"]`.
- `core/websocket_server.py::sanitize_payload()` HTML-escapes **top-level
  string fields only**. `theme_data` is a nested dict and is passed through
  untouched. Therefore the WS sanitizer is *not* a theme safety boundary.
- `core/display_state.py` stores the payload, restores it on reconnect and on
  tab switches, and requires `theme` + a dict `theme_data` for a stored payload
  to match. It deliberately does not compare theme identity.
- `core/outputs.py` / `core/output_router.py` decide which output ids receive
  a payload. They contain no theme logic.

So: **resolution happens in Python, but only to choose a dict; validation and
defaults do not happen at all today.** The renderer re-derives layout from
whatever JSON arrived.

### 1.3 Rendering and scaling

`display/display.html` + `display/display.js` + `display/themes.css`:

- `#container` is a single box. `applyTheme()` maps the first nested container
  onto global `--rc-*` custom properties on `:root`, so **only one container
  can render**.
- Geometry: `x`/`y` are numbers interpreted as CSS pixels from the **top-left**
  of the browser viewport (`container.style.left = x + "px"`,
  `top = y + "px"`). The shipped values confirm this: e.g. `default` has
  `x=38.5`, `width=1843`, and `38.5 + 1843 + 38.5 = 1920`.
- `width`/`height` reach CSS as strings (`"1843px"`) through custom
  properties. `min_width`/`max_width` likewise. There is no v1
  `min_height`/`max_height`.
- `display`/`flex_direction`/`justify_content`/`align_items` style the single
  box. `body.vertical_align` sets the page `<body>` flex `align-items`, i.e.
  it moves the whole box when the box is **not** absolutely positioned.
  Because every shipped theme sets `x`/`y`, `#container` is absolutely
  positioned and `body.vertical_align` has no visible effect on them.
  `body.padding_bottom` similarly pads the page, not the box.
- Internally, content is `#verse-content` (text `<h1>`, then a reference
  `<p>` containing the reference span and the translation span). There is no
  per-block box and no block ordering.
- `text` styling is applied to `#verse-text`; `reference` to `#verse-ref`;
  `translation` to the translation span inside the reference line;
  `verse_num` to a span prepended inside the text.
- Scaling: `display/display.html` uses `100vw/100vh` and no transform. OBS at
  a 1920×1080 browser source is 1:1. At any other source size the CSS pixel
  sizes stay fixed, so a 1843px box overflows a 1280px source. The **in-app
  preview** is different: `ui/widgets/display_view.py` has a fixed
  1920×1080 document and `resizeCanvas()` sets
  `document.body.style.transform = scale(min(w/1920, h/1080))`.
  So "design canvas" is nominal for OBS, real only in the preview.
- The legacy `_applyContainers()` path handles the oldest absolute-box shape
  (`containers: {text: {x, y, width, height}}`) with **center-based** x/y and
  hardcoded defaults (20px inner padding, 34px reference, 16px translation,
  `#ffffff`/`#cccccc`/`#999999`).

### 1.4 Autosize

`autoFitText()`:

- reads the container height from `--rc-height` (`parseInt`, so only `px`);
- binary-searches the text font size between `--rc-text-min-size` (default 4)
  and `--rc-text-max-size` (default 300);
- measures `verseText.offsetHeight + verseText.marginBottom +
  verseRef.offsetHeight` against that height;
- a deck's explicit `size_nominal` becomes both the initial size and the
  ceiling;
- after fitting, `fitOutlineLayers()` shrinks up to 8 more times (×0.9 per
  pass, floored at min) to compensate for outline padding.

Limits are theme parameters today; the algorithm is engine behavior. In v2
the same algorithm is applied **per text block, per container**, because
multiple containers can each show text with different available heights.

### 1.5 Reference, translation, verse number

- Reference and translation share one line: `<p id="verse-ref">` contains
  `#verse-ref-text` followed by `#verse-ref-translation`. Translation is
  separated by `margin-left` (default 8px, theme key `translation.margin_left`).
- There is no theme key for reference position; it is always below the text.
- If both reference and translation are empty, the whole line is
  `display:none` and the text's bottom margin is forced to 0 so centering is
  not skewed.
- The verse number is extracted from `data.reference` with `/(\d+:\d+)$/`
  (last number after the colon), then prepended inside the text as
  `<span class="verse-num">`. CSS: `0.6em`, weight 700, opacity 0.7,
  `vertical-align: top`, `margin-right: 0.15em`, line-height 1. A container
  path in `display.html` duplicates this with opacity 0.6 / margin 0.3em.

### 1.6 Animations and theme switching

- `payload.theme_data.animations` holds `display_enter`, `between_slides`
  (`out_type`, `in_type`, `duration_ms`, `easing`), and `display_exit`.
- `display.js` implements `fade_up`, `fade_in`, `fade_down`, `fade_out`,
  `scale_up`, `scale_down`, `slide_up`, `slide_down`, with an easing map.
- The designer also offers `typewriter`; **the renderer does not implement
  it**, so it currently no-ops.
- The switch contract (`docs/theme-switch-contract.md`) requires `theme_data`
  to be present and non-null in every display payload. Unknown names fall back
  per kind. That contract stays; only the *shape* of `theme_data` changes.

### 1.7 What the designer and other tabs read/write

`ui/widgets/theme_properties_panel.py`:

- `load_theme()` takes `theme["containers"]` as a dict and edits the **first**
  container. If `containers` is missing it synthesizes a legacy flat view from
  top-level `container`/`body`/`text`/... keys.
- It reads a fixed key set per block: text (color, font, size, weight,
  line-height, letter-spacing, shadow, min, max), reference (color, font,
  size, weight, transform, letter-spacing), translation (color, margin-left),
  verse_num (color, font). Container rows: x, y, width, height, background,
  border, radius, shadow, backdrop, padding, max/min width, flex direction,
  justify, align.
- `_collect_theme()` deep-copies `_source_theme` (so top-level keys and other
  containers survive), writes the active container's row values, **forces**
  `display:flex`, `flex_direction:column`, `justify_content:center`,
  `align_items:center`, and **replaces** each managed block dict wholesale with
  the legacy key set. That wholesale replacement is the v2 data-loss point:
  `visible`, `position`, `margin_*`, `text_outline`, `opacity`, `max_lines`,
  etc. inside those blocks are dropped on save.
- Toggling a block off omits it. There is no `visible:false` concept today.

`ui/tabs/theme_designer_tab.py`:

- `_working_theme` is the raw theme.
- `ThemePropertiesPanel.theme_changed` → `_on_theme_changed()` replaces
  `_working_theme` with the panel's collected dict.
- `ContainerEditor` edits **top-level `theme["container"]`**, a legacy branch
  that neither the v1 nested-container renderer nor v2 reads
  (`_on_container_changed` writes `_working_theme["container"]` and reloads
  the properties panel; the editor never touches `containers`).
- Previews receive `_working_theme` **unresolved** via
  `ThemePreview.apply_theme()` → `DisplayView.display_verse()` →
  `handlePayload()`. A v2 theme would currently be rendered by the v1 path.
- `_on_save()` calls `save_theme(name, _working_theme)` unmodified.
- The **animations panel is constructed but never connected**: nothing calls
  `load_animations()`, `get_animations()`, or connects
  `animations_changed`. The tab is dead UI. Themes with animations are
  hand-edited and render fine; the designer cannot edit them.
- `DraggableEditor` (`ui/widgets/draggable_editor.py`) is never instantiated
  anywhere; it is dead code. Its `DEFAULT_CONTAINERS` use center x/y and
  legacy keys, matching the oldest shape only.

`ui/widgets/theme_quick_editor.py` and
`ui/widgets/lite_designer/lite_designer.py` reuse `ThemePropertiesPanel` and
`ThemePreview`, so they inherit exactly the same round-trip behavior and the
same v2 data-loss risk.

`ui/tabs/presentation_tab.py` / `ui/tabs/slides_tab.py` only call
`resolve_theme()`, `slide_title_visible()`, and put `theme_data` in the
payload. `ui/panels/slide_grid_panel.py` calls `theme_container(theme)
.get("text", {})` to pick a card preview color.

`ui/widgets/display_view.py` embeds a **full duplicate** of the display HTML,
CSS, and JS for the operator preview. Every renderer change in Phase 3 MUST be
mirrored there; existing tests fail on divergence.

---

## 2. Design principles

1. **One resolution point.** Python owns v1→v2 migration, shared-file
   resolution, validation, clamping, defaults, and sanitization. `theme_data`
   on the wire is resolved v2.
2. **The theme describes structure, the engine describes algorithms.**
   Container count/geometry/decoration, block visibility/order-ish placement,
   and typography/spacing are theme data. Binary-search fitting, outline layer
   construction, animation keyframes, and payload handling are engine code.
3. **A theme file can be tiny.** Every field has a default. A theme with one
   container and one `text` block renders.
4. **Fail visible, never blank.** Field errors fall back to defaults; a broken
   theme falls back to a built-in safe theme. The display never crashes or
   goes transparent because of a theme.
5. **Preserve the operator's bytes.** Loading never rewrites a theme file.
   The designer's load→edit→save round trip preserves unknown keys.
6. **V1 renders exactly as before at 1920×1080.** Migration is deterministic
   and in memory.

---

## 3. Top-level theme document

```json
{
  "schema_version": 2,
  "name": "default",
  "label": "Standard",
  "description": "...",
  "author": "RhemaCast",
  "kind": "scripture",
  "canvas": { "width": 1920, "height": 1080, "background": "transparent", "fit": "contain" },
  "containers": [ ... ],
  "animations": { ... }
}
```

| Field | Type | Allowed / range | Default | Notes |
|---|---|---|---|---|
| `schema_version` | integer | `1` or `2` | **1 when absent** | New files MUST write `2`. `>2` → safe theme + warning. |
| `name` | string | `^[A-Za-z0-9][A-Za-z0-9 _.-]{0,63}$` | file stem | Loader key and audit label. Not used in CSS/HTML. |
| `label` | string | free text ≤ 120 | `name` | UI label only. |
| `description` | string | free text ≤ 500 | `""` | UI label only. |
| `author` | string | free text ≤ 120 | `""` | Metadata only. |
| `kind` | enum | `scripture`, `freeform` | from folder | Folder wins on mismatch, with a warning. |
| `canvas` | object | see 3.1 | 1920×1080, transparent, `contain` | |
| `containers` | array | 1–16 entries, unique ids | one generated `main` container | Required in v2; absent/empty → synthesize `main` + warning. See 4. |
| `animations` | object | name → animation definition; see 4.9 | `{}` | **Local definition library**, not the v1 assignment object. Reusable definitions also live in `themes/_shared/animations.json`. |
| `slide` | object | `{ "show_title": bool }` | `{}` | Legacy freeform switch; v2 uses `title.visible`. Kept accepted. |
| any other key | any | — | — | Ignored by the renderer; **preserved** on save. |

### 3.1 `canvas`

| Field | Type | Allowed | Default | Notes |
|---|---|---|---|---|
| `width` | integer | 320–7680 | 1920 | Design width used to resolve percentages. |
| `height` | integer | 240–4320 | 1080 | Design height. |
| `background` | color / `none` / `transparent` | validated color | `transparent` | Painted behind all containers. OBS overlay default stays transparent. |
| `fit` | enum | `contain`, `none` | `contain` | `contain`: scale the 1920×1080 stage uniformly to fit the viewport, letterboxed/centered. `none`: today's raw CSS-pixel behavior. |

`fit: "contain"` is a new v2 default. V1 migration sets `"none"` so old
themes keep today's OBS behavior at every source size. New v2 themes get
resolution-independent output. The in-app preview owns its own scaling today;
Phase 3 moves that responsibility into the renderer so both paths use the same
`fit` logic (see §11, Phase 3).

**Percentages always resolve against `canvas.width` / `canvas.height`**
(1920×1080 by default), never against the browser viewport, the OBS source
size, or the current output's pixel dimensions. A theme therefore lays out
identically on every output: `fit: "contain"` scales the finished 1920×1080
stage uniformly; `fit: "none"` leaves it at 1:1 and may overflow a smaller
source (today's behavior, retained for migrated v1 themes). Percentage
resolution does not change when `fit` changes.

---

## 4. Containers

`containers` is an **ordered array**. Order is part of the format and is used
to break layer ties. Object-keyed containers were rejected because JSON object
ordering is an implementation detail in some editors and because an array
states the intent once.

```json
{
  "id": "verse",
  "label": "Verse text",
  "kind": "scripture",
  "layer": 10,
  "visible": true,
  "position": { "anchor": "top_left", "x": 60, "y": 40 },
  "width": 1800,
  "height": 760,
  "min_width": 0,
  "max_width": null,
  "min_height": 0,
  "max_height": null,
  "background": "transparent",
  "border": { "shared": "gold_frame" },
  "border_radius": 24,
  "box_shadow": "none",
  "backdrop_filter": "none",
  "opacity": 1.0,
  "overflow": "hidden",
  "animation": {
    "entry": "fade_up",
    "transition": { "out": "fade_down", "in": "fade_up" },
    "out": "fade_down"
  },
  "blocks": { ... }
}
```

### 4.1 Container identity and layering

| Field | Type | Allowed / range | Default | Notes |
|---|---|---|---|---|
| `id` | string | `^[a-z][a-z0-9_-]{0,31}$`, unique | required | Used for diagnostics and lookup, never as raw HTML. |
| `label` | string | ≤ 80 | `id` | Designer/debug label. |
| `kind` | enum | `scripture`, `freeform`, `any` | theme kind | A container that only makes sense for one kind. `any` is allowed in both. |
| `layer` | integer | 0–100 | 0 | Higher is in front. |
| `visible` | boolean | — | `true` | `false` renders nothing for this container. |

**Layer rules.** Containers are sorted by `layer` ascending, then by their
array index ascending. They are appended to the stage in that order; the
renderer also sets `z-index: layer`. Therefore:

- different layers: higher `layer` paints in front, always;
- equal layers: the container defined **later in the array** paints in front;
- a hidden container consumes its position in the order but draws nothing.

Layers are per theme, not per output. Negative layers are rejected (clamped to
0) to avoid disappearing behind the canvas.

### 4.2 Form parameters

| Field | Type | Allowed / range | Default | Notes |
|---|---|---|---|---|
| `width` | length | px number, `"Npx"`, `"N%"`, `"auto"` | `"auto"` | `%` of canvas width. `auto` = content-sized, clamped by min/max. |
| `height` | length | px number, `"Npx"`, `"N%"`, `"auto"` | `"auto"` | `%` of canvas height. |
| `min_width` | length | px / `%`, ≥ 0 | 0 | |
| `max_width` | length | px / `%` / `null` | `null` | |
| `min_height` | length | px / `%`, ≥ 0 | 0 | New in v2. |
| `max_height` | length | px / `%` / `null` | `null` | New in v2. |
| `background` | paint | color, `transparent`, `none`, validated gradient | `transparent` | No `url()`, no `var()`. |
| `border` | border | shared ref, structured border, or validated CSS string | `"none"` | See 4.2.1. |
| `border_radius` | length / `null` | 0–400 px / `%` / `null` | `null` | `null` = use `border.radius` if the border defines one, else 0. Explicit value wins over the border's radius. |
| `box_shadow` | shadow | shared ref, structured shadow, or validated CSS string | `"none"` | See 4.2.1. |
| `backdrop_filter` | filter | `none` or validated filter list | `"none"` | Allowlisted functions only (`blur`, `brightness`, `contrast`, `saturate`, `grayscale`, `sepia`, `hue-rotate`, `opacity`). |
| `opacity` | number | 0.0–1.0 | 1.0 | Applies to the whole container. |
| `overflow` | enum | `hidden`, `visible` | `hidden` | `hidden` is today's behavior and clips text at the edge. `visible` lets shadows/outlines escape but not text beyond the box (text still wraps). |
| `animation` | animation | see 4.9 | `{}` | Entry / transition / out assignments for the container box itself. |

Engine-fixed: `box-sizing: border-box`, `position: absolute` (computed from
`position`), `display: flex`, stack direction **column**. `flex_direction` and
`justify_content` are **removed** from the format; a v2 file that contains them
is warned about and the keys are ignored. `align_items` is also removed: block
text alignment lives on each block's `text_align`.

**There is no container padding.** Position and size are absolute and
discrete: `x`, `y`, `width`, and `height` always describe the box's outer
geometry, and no inset, border, or margin shifts it. (Borders are drawn inside
the border-box and do not grow it.) Padding is strictly a content parameter:
`body.padding_*` insets the content stack inside the fixed box, and each block
may carry its own `padding_*`. See §4.4 and §4.6. A v2 file that contains
container-level `padding*` keys is warned about and those keys are ignored.

#### 4.2.1 Border and shadow forms

A border field accepts exactly one of:

```json
"none"
"2px solid #D4AF37"                          // validated CSS string (v1 form)
{ "shared": "gold_frame" }                   // named shared border
{ "width": 2, "style": "solid", "color": "#D4AF37", "radius": 12,
  "sides": { "top": { "width": 4, "color": "#ffffff" } } }
```

Structured border fields: `width` 0–40 px, `style` enum
`none|solid|dashed|dotted|double|groove|ridge|inset|outset`, `color` validated
color, `radius` 0–400 px, `sides` optional map of `top|right|bottom|left` to
`{width, style, color, radius}`. `sides` compiles to per-side declarations; a
side without a value inherits the base. Inline `radius` compiles to
`border-radius` only when the container's `border_radius` is `null`; an
explicit `border_radius` (including `0`) wins. Per-side corner radii are out of
scope for v2.

A shadow field accepts `"none"`, a validated CSS shadow string (1–12
comma-separated shadows — 12 because a v1 hard ring expands to eight offset
copies plus the soft drop shadow it shipped with), `{ "shared": "soft" }`, or a
structured shadow:

```json
{ "x": 0, "y": 24, "blur": 48, "spread": -12, "color": "rgba(0,0,0,0.55)",
  "inset": false }
```

`x`/`y`/`blur`/`spread` are -500..500 px, `color` validated, `inset` bool.

### 4.3 Positioning

```json
"position": { "anchor": "top_left", "x": 60, "y": 40 }
```

| Field | Type | Allowed | Default |
|---|---|---|---|
| `anchor` | enum | `top_left`, `top_right`, `bottom_left`, `bottom_right`, `center`, `left`, `right`, `top`, `bottom`, `fill` | `center` |
| `x` | length | number px or `"N%"` | see below |
| `y` | length | number px or `"N%"` | see below |

`x`/`y` are **not** uniformly "offsets from the anchor". The edge keywords
follow one rule:

> **The unconstrained axis is centered unless its coordinate is given.**
> `left`/`right` center vertically unless `y` is given; `top`/`bottom` center
> horizontally unless `x` is given. When the coordinate *is* given, it is the
> distance from the canvas edge on that axis (top or left), not an offset from
> the centered position.

"Given" means the key is present and not `null`. An explicit `0` counts as
given, so `left` with `y: 0` pins the top edge while `left` with no `y`
centers.

Exact placement, with canvas `W×H` and resolved container size `w×h`:

| Anchor | horizontal | vertical |
|---|---|---|
| `top_left` | `left = x` (default 0) | `top = y` (default 0) |
| `top_right` | `right = x` (default 0) | `top = y` (default 0) |
| `bottom_left` | `left = x` (default 0) | `bottom = y` (default 0) |
| `bottom_right` | `right = x` (default 0) | `bottom = y` (default 0) |
| `center` | `left = (W - w)/2 + x` (default 0) | `top = (H - h)/2 + y` (default 0) |
| `left` | `left = x` (default 0) | `y` given → `top = y`; else `top = (H - h)/2` |
| `right` | `right = x` (default 0) | `y` given → `top = y`; else `top = (H - h)/2` |
| `top` | `x` given → `left = x`; else `left = (W - w)/2` | `top = y` (default 0) |
| `bottom` | `x` given → `left = x`; else `left = (W - w)/2` | `bottom = y` (default 0) |
| `fill` | `left = 0`, `width = W` | `top = 0`, `height = H` |

Equivalent corner forms (useful when checking intent):

- `left` + `y` is exactly `top_left` (with `x` as its left distance).
- `right` + `y` is exactly `top_right`.
- `top` + `x` is exactly `top_left` (with `y` as its top distance).
- `bottom` + `x` is exactly `bottom_left`.

Rules:

- `fill` **ignores** `width`, `height`, `x`, `y` (a warning is logged if any
  are set). It is the only keyword that overrides explicit size.
- `right`/`bottom` offsets are distances **inward** from the canvas edge.
- `top_left` etc. honor only their two named edges; the other two are
  determined by `w`/`h`. If `width` is `auto`, the box grows away from the
  anchored edge (rightward for `*_left`, leftward for `*_right`).
- `center` is the only anchor where `x`/`y` are offsets (from the centered
  position). Everywhere else a given coordinate is an absolute edge distance.
- **Percentages.** `x: "N%"` resolves to `N/100 × W`; `y: "N%"` resolves to
  `N/100 × H`. Percentages always use the design canvas (`canvas.width` /
  `canvas.height`), never the viewport or output size (§3.1).
- Percentages are accepted only in `position.x/y`,
  `width`/`height`/`min_*`/`max_*`, and `canvas.width/height`; they are
  rejected for padding, margins, font sizes, radii, and shadows (use px/em
  there).
- **Auto size resolution order.** Resolve explicit widths first; lay out the
  content; measure `auto` heights; clamp by `min`/`max`; then compute the
  position. This makes `center` + `height:"auto"` deterministic.
- **Extra corner keys.** For compatibility with hand-written v1-ish files, the
  position object may instead carry boolean corner keys
  (`"top_left": true`, ...). If `anchor` is present it wins. Otherwise the
  first present corner in the fixed order `top_left`, `top_right`,
  `bottom_left`, `bottom_right` is used and **every extra corner is ignored
  with a warning**. No corner keys → `center`.
- An invalid `anchor` → `center` + warning.


### 4.4 The content stack (`body`)

`body` is a **pseudo-block** that represents the container's internal stack.
It lives at `blocks.body`, like any other block. It is optional; when absent
the engine behaves as if
`{ "visible": true, "valign": "center", "gap": 0, "padding": 0 }`.

```json
"blocks": {
  "body": {
    "visible": true,
    "valign": "center",
    "gap": 12,
    "padding": 0,
    "padding_top": 0,
    "padding_right": 0,
    "padding_bottom": 0,
    "padding_left": 0
  }
}
```

| Field | Type | Allowed | Default |
|---|---|---|---|
| `visible` | boolean | — | `true` |
| `valign` | enum | `top`, `center`, `bottom` | `center` |
| `gap` | length | 0–200 px | 0 |
| `padding` | length | 0–400 px | 0 |
| `padding_top/right/bottom/left` | length | 0–400 px | `padding` |

`body` owns vertical alignment and the gap between blocks. It is where
`body.vertical_align` and `body.padding_bottom` from v1 migrate. **`body` is
also the container-level content inset:** because containers have no padding,
its `padding_*` is the space between the container's fixed outer box and the
content stack. Individual blocks may add their own padding inside that. Neither
changes the container's position or size. Autosize measures the **content area
that remains after `body.padding_*`**, and block padding is part of each
block's measured box (§4.6).

`body` accepts the shared block parameters too (so the "every block has the
same set" rule is literal), but typography fields on `body` have no effect and
are warned about once per theme.

Blocks other than `body` are laid out in the stack relative to `text`:

1. `verse_num` when `mode: "block"` and `position: "above_verse"`;
2. `title` (freeform) / `reference` (scripture) when its position resolves to
   `above_verse`;
3. `translation` when its position resolves to `above_reference`;
4. `translation` when its position resolves to `above_verse` (closest to the
   verse);
5. `text`;
6. `translation` when its position resolves to `below_verse` (closest to the
   verse);
7. `reference` / `title` when its position resolves to `below_verse`;
8. `translation` when its position resolves to `below_reference`;
9. `verse_num` when `mode: "block"` and `position: "below_verse"`.

`left_of_reference` / `right_of_reference` are **not** stack items: the
translation renders inside the reference/title row on the same line, on the
chosen side. `gap` is inserted between adjacent stack items. The stack is
`display:flex; flex-direction:column; align-items:stretch;
justify-content:flex-start|center|flex-end` per `valign`. Each block's own
`text_align` controls its text alignment inside its full-width row.

### 4.5 Blocks

`blocks` is an object keyed by block id. A block that is absent is not
rendered. A block that is present is rendered when `visible` is not `false`.

| Theme kind | Allowed block ids |
|---|---|
| `scripture` | `body`, `text`, `reference`, `translation`, `verse_num` |
| `freeform` | `body`, `title`, `text`, `translation`, `verse_num` (`reference` is an accepted alias for `title`) |
| `any` | all of the above; `title` and `reference` share one slot and `title` wins if both are present |

**Duplicate blocks across containers are allowed.** A verse and its reference
may live in two containers, or the same text may appear in two containers with
different typography. Each occurrence is independent: its own block parameters,
its own autosize result, its own visibility. No content is consumed by the
first occurrence.

**Duplicate blocks inside one container are invalid.** The validator keeps the
first occurrence in the order in which the block would render, drops the rest,
and logs a warning. There is exactly one `text`/`reference`/`translation`/
`verse_num`/`title` per container.

### 4.6 Shared block parameters

Every block (including `body`, where typography is inert) accepts this full
set. The defaults below are the **text** defaults; per-block overrides are in
§4.7.

| Field | Type | Allowed / range | Default (text) | Notes |
|---|---|---|---|---|
| `visible` | boolean | — | `true` | |
| `color` | color | validated color / `inherit` | `#f8fafc` | `inherit` = inherit from container. |
| `font_family` | string | validated family list, `inherit` | `'Nunito', sans-serif` | No `url()`. |
| `size` | length | 1–400 px / em / `inherit` | 40 | For `text`, the starting/nominal autosize size (v1 `2.5rem`). |
| `min_size` | length | 1–400 px | 4 | Autosize floor; ignored outside `text`. |
| `max_size` | length | 1–400 px | 300 | Autosize ceiling; ignored outside `text`. |
| `weight` | integer | 100–900, step 100 | 700 | |
| `line_height` | number | 0.5–3.0 (unitless) | 1.2 | |
| `letter_spacing` | length | -20–40 px or em | -0.01em | v1 `#verse-text` default. |
| `word_spacing` | length | -20–40 px or em | 0 | |
| `text_shadow` | shadow | `none` or validated shadow | `0 4px 12px rgba(0,0,0,0.4)` | Never auto-converted to outline in v2. |
| `text_outline` | outline | `none` or `<length> <color>` | `none` | `<length>` 0–20 px or em; color validated. |
| `text_transform` | enum | `none`, `uppercase`, `lowercase`, `capitalize` | `none` | |
| `text_align` | enum | `left`, `center`, `right`, `justify` | `center` | |
| `font_style` | enum | `normal`, `italic` | `normal` | |
| `text_decoration` | enum | `none`, `underline`, `line-through` | `none` | |
| `opacity` | number | 0.0–1.0 | 1.0 | |
| `max_lines` | integer / null | 1–20 / `null` | `null` | `null` = unlimited. Implemented with `-webkit-line-clamp` after autosize. |
| `direction` | enum | `ltr`, `rtl` | `ltr` | |
| `margin_top` | length | -400–400 px | 0 | |
| `margin_right` | length | -400–400 px | 0 | |
| `margin_bottom` | length | -400–400 px | 24 (text), 0 others | Today's text margin. |
| `margin_left` | length | -400–400 px | 0 | |
| `padding` | length | 0–400 px | 0 | Content inset inside this block's row. |
| `padding_top/right/bottom/left` | length | 0–400 px | `padding` | |
| `animation` | animation | see 4.9 | `{}` | Entry / transition / out assignments for this block. |

Block padding is a content parameter, like `body` padding. It insets the
block's text inside its own row and never moves the container. Autosize
measures the text box **including block padding**, so a padded text block is
fitted to the space it actually occupies.

Why this list stops here: `font_family`, `size`, `weight`, `style`,
`line_height`, `letter_spacing`, `word_spacing`, `transform`, `decoration`,
`align`, `direction`, `color`, `shadow`, `outline`, `opacity`, `max_lines`
cover the CSS text surface without opening a raw-CSS escape hatch. Layout
(width/height/position) belongs to the container, not the block; inset belongs
to content (`body`/block padding).

### 4.7 Block-specific parameters and defaults

#### `text`

| Field | Type | Allowed | Default |
|---|---|---|---|
| `autosize` | boolean | — | `true` |
| `position` | — | not allowed | — |

`text` is the autosize anchor. It always occupies its row in the stack.
`size` is the size used before fitting; `min_size`/`max_size` bound the fit. If
`autosize` is false, `size` is used verbatim and overflow is clipped by the
container.

A deck's `slide_format.size_nominal` remains the fit ceiling (today's
behavior), applied only to the `text` block.

#### `reference`

| Field | Type | Allowed | Default |
|---|---|---|---|
| `position` | enum | `above_verse`, `below_verse` | `below_verse` |
| `color` | color | validated / `inherit` | `#94a3b8` |
| `font_family` | string | validated / `inherit` | `'DM Sans', sans-serif` |
| `size` | length | px / em / `inherit` | 24 |
| `weight` | integer | 100–900 / `inherit` | 500 |
| `line_height` | number | 0.5–3 / `inherit` | 1.2 |
| `letter_spacing` | length | px / em / `inherit` | `0.1em` |
| `text_transform` | enum | `none`/`uppercase`/`lowercase`/`capitalize`/`inherit` | `uppercase` |
| `text_align` | enum | `left`/`center`/`right`/`justify` | `center` |
| `margin_*` | length | -400–400 px | 0 |

These are today's `#verse-ref` values. `above_verse` renders the reference
above the text; `below_verse` renders it below (today). If the container has
no `text`, both positions mean "the only flow item" and the block is centered
by `body.valign`.

#### `translation`

| Field | Type | Allowed | Default |
|---|---|---|---|
| `position` | enum | `above_verse`, `below_verse`, `above_reference`, `below_reference`, `left_of_reference`, `right_of_reference` | `right_of_reference` |
| `color` | color | validated / `inherit` | `#64748b` |
| `margin_left` | length | -400–400 px | 8 |
| `margin_right` | length | -400–400 px | 0 |

- `left_of_reference` / `right_of_reference` place the translation on the same
  visual line as the reference, separated by `margin_left`/`margin_right`
  (today's inline span behavior).
- `above_reference` / `below_reference` stack it directly above/below the
  reference, separated by margins.
- `above_verse` / `below_verse` are relative to the text.
- **Typography inheritance.** Unless the translation block sets them
  explicitly, `font_family`, `size`, `weight`, `line_height`,
  `letter_spacing`, `text_transform`, and `font_style` are copied from its
  anchor block at resolution time: `reference` for the four `*_reference`
  positions, `text` for the two `*_verse` positions. This is exactly today's
  behavior — the translation span inherits the reference line's typography and
  only overrides color and the left margin — so **migrated v1 themes do not
  move**. Python writes the inherited values explicitly into the resolved
  theme; the renderer performs no cascade.
- **Missing anchor rule.** If the referenced block (`reference`, or `text` for
  the `*_verse` forms) is absent or `visible:false` in this container:
  - `left_of_reference` / `right_of_reference` / `above_reference` /
    `below_reference` fall back to `below_verse`;
  - `above_verse` / `below_verse` fall back to the block simply taking its
    normal stack position (there is no verse to be relative to);
  - typography inheritance falls back to the `text` block if present, then to
    the shared text defaults.
  A warning is logged once per resolution, not per frame.

#### `verse_num`

| Field | Type | Allowed | Default |
|---|---|---|---|
| `mode` | enum | `inline`, `block` | `inline` |
| `position` | enum | `above_verse`, `below_verse` | `above_verse` |
| `vertical_align` | enum | `top`, `middle`, `baseline`, `bottom` | `top` |
| `margin_right` | length | 0–40 px | `0.15em` |
| `size` | length | 0.1–4 em / px | `0.6em` |
| `weight` | integer | 100–900 | 700 |
| `opacity` | number | 0–1 | 0.7 |
| `line_height` | number | 0.5–3 | 1 |
| `color` | color | validated / `inherit` | `inherit` |
| `font_family` | string | validated / `inherit` | `inherit` |

For an inline verse number, `inherit` means the containing `text` block's
resolved color/font. For a block-mode number it means the container's content
stack. Python resolves both into explicit values in the payload.

**Today's behavior (the default).** The number is extracted from the reference
with `/(\d+:\d+)$/`, taking the digits after the colon. It is prepended inside
the text as `<span class="verse-num">N</span> ` with `font-size:0.6em`,
`weight:700`, `opacity:0.7`, `vertical-align:top`, `margin-right:0.15em`,
`line-height:1`. `mode:"inline"` reproduces exactly that. It requires a
`text` block in the same container; if there is none, the validator keeps the
block but it renders nothing (warning). In `block` mode the same extracted
number (not the whole reference) becomes its own line above or below the text.

#### `title` (freeform)

| Field | Type | Allowed | Default |
|---|---|---|---|
| `position` | enum | `above_verse`, `below_verse` | `below_verse` |

`title` is today's slide title line, which rides the `reference` payload field
(`data.reference`). Its typography defaults to the `reference` values above
(same size, weight, color, transform, and spacing), and it uses the same
`above_verse`/`below_verse` placement. For freeform, `reference` is an alias
for `title`; if both exist, `title` wins and a warning is logged.
`slide.show_title:false` migrates to `title.visible:false`.
`slide_title_visible()` in Python is updated to consult the resolved v2 title
block first, then the legacy `slide.show_title`, so payloads stay clean.

### 4.8 Freeform

Freeform themes stay **single-container** for now. The validator accepts more
than one container only if every container after the first is `visible:false`
(so a future multi-container editor does not have to re-migrate); otherwise it
keeps the first and warns. The container parameter model, block parameters,
position, layers, and shared files are identical to scripture. The only
differences are the canonical `title` block and the legacy `slide` section.

A freeform theme with `text` + `title` maps to today's `#verse-text` +
`#verse-ref` line. A freeform theme without `title` is exactly today's
`slides` theme (title hidden).

### 4.9 Animations

Animation is a **content parameter**, not a global stage setting. A container,
the `body` stack, or an individual block may carry an `animation` assignment.
The assignment names reusable definitions, and definitions live in the theme,
in `themes/_shared/animations.json`, or in the engine's built-in registry.

This replaces v1's single top-level `animations` object that animated the one
`#container` box. It is what makes staggered layouts possible: two containers
can enter independently, a citation can arrive after the verse, and a block can
typewrite while its container fades in.

#### 4.9.1 Model

- A **definition** is a recipe: a required `type`, a `duration_ms` (600 when
  omitted, with a warning), plus delay, easing, and type-specific parameters
  (keyframes for `custom`, reveal/cursor for `typewriter`). Definitions are
  pure data.
- An **assignment** has three phases: `entry`, `transition`, and `out`.
  `transition` has an `out` half (old content leaving) and an `in` half (new
  content arriving).
- A **slot** is one phase value: `"none"`, a definition name, a named
  reference with per-use overrides, or an inline definition.
- **Targets.** `animation` is legal on a container (the whole box, including
  background and border), on `body` (the content stack), and on every block.
  A container animation moves all of its descendants as one group; a block
  animation moves only that block.
- **No inheritance.** A block does not animate just because its container
  does. The container already moves it. Both may run at once and compose.
- Definitions are self-contained: a definition cannot reference another
  definition. Only slots reference definitions. There are no cycles.

#### 4.9.2 Assignment grammar

```json
"animation": {
  "entry": "verse_rise",
  "transition": { "out": "fade_down", "in": "verse_rise" },
  "out": "fade_down"
}
```

| Field | Type | Default | Notes |
|---|---|---|---|
| `entry` | slot | absent | Plays when the element first becomes visible with content. |
| `transition` | object or slot | absent | `{ "out": slot, "in": slot }`; a bare slot is shorthand for `{ "in": slot }`. |
| `out` | slot | absent | Plays when the element is cleared/hidden. |

Slot forms:

```json
"none"                                             // no animation
"fade_up"                                          // named definition
{ "use": "fade_up", "duration_ms": 800,
  "easing": "ease-in-out", "delay_ms": 120 }       // named + overrides
{ "type": "fade_in", "duration_ms": 500 }           // inline preset
{ "type": "custom", "duration_ms": 500,
  "easing": "ease-out", "keyframes": [ ... ] }      // inline keyframes
{ "type": "typewriter", "duration_ms": 1200 }       // inline typewriter
```

- **Every definition carries `type` and `duration_ms`.** `type` selects the
  shape: one of the eight presets, `typewriter`, or `custom` for keyframes.
  After normalization a definition always has both; a source that omits
  `duration_ms` gets 600 with a warning.
- Overrides on a named reference are only `duration_ms`, `delay_ms`, and
  `easing`. `type` cannot override a name — a slot object containing `type`
  is an inline definition instead.
- A missing phase means no animation for that phase.
- An unknown name falls back per phase: entry / transition-in → `fade_in`;
  transition-out / out → `fade_out`; plus one warning.
- `"none"` is explicit silence; it does not fall back.
- A slot inside `transition` is independent: `{ "out": "fade_down" }` plays
  the old content out, swaps, and shows the new content with no entrance.

#### 4.9.3 Phases and triggers

**`entry`** — the element goes from not visible to visible with content:

- the first payload after page load or after a silent resync;
- content arriving after a clear / Esc;
- a container becoming visible because the theme changed? **No.** Theme-only
  changes never play entry. Animations follow content, not re-broadcasts.

**`transition`** — the element is visible and its content changes:

- the new source text is compared with the currently rendered source per
  block; only elements whose source changed animate;
- a container or `body` transition runs when **any descendant block source
  changed**; the container/`body` animates as one group, and individual block
  transitions still run for the blocks that changed;
- `out` plays on the old content, then the content is swapped, re-fitted, and
  `in` plays on the new content;
- unchanged blocks do not re-animate (a theme restyle with the same verse is
  silent);
- if only `in` exists (v1's behavior), the swap happens immediately and `in`
  plays;
- if only `out` exists, the swap happens after `out` and there is no entrance.

**`out`** — the element is cleared, hidden, or removed:

- clear / Esc and the theme's clear primitive;
- the animation completes, then the element is hidden/removed;
- a block that becomes empty because the payload has no reference/translation
  hides immediately (today's empty-line rule) and does not play `out`.
  `out` is for explicit clear/hide, not for an empty string.

The `out` slot is read from the theme **currently applied to the element**
(the last payload that carried `theme_data`), not from the incoming clear
payload. Today's clear payload is `{"action":"clear"}` with no theme, and v1
already reads `display_exit` from `_prevPayload`; this preserves that behavior
when theme and clear race.

Rapid updates coalesce: an in-flight animation is cancelled, the latest
content is rendered, and the newest phase starts. Exit is never queued behind
an entrance.

#### 4.9.4 Definition grammar — presets and keyframes

```json
{
  "type": "custom",
  "label": "Verse rise",
  "duration_ms": 700,
  "delay_ms": 0,
  "easing": "ease-out",
  "origin": "center",
  "keyframes": [
    { "at": 0,   "opacity": 0,      "translate_y": 36, "scale": 0.98, "blur": 6 },
    { "at": 70,  "opacity": 0.85,   "translate_y": 6,  "scale": 1.0,  "blur": 0 },
    { "at": 100, "opacity": "base", "translate_y": 0,  "scale": 1,    "blur": 0 }
  ]
}
```

| Field | Type | Allowed / range | Default |
|---|---|---|---|
| `type` | enum | `fade_in`, `fade_out`, `fade_up`, `fade_down`, `scale_up`, `scale_down`, `slide_up`, `slide_down`, `typewriter`, `custom` | **required** |
| `label` | string | ≤ 80 | name |
| `duration_ms` | integer | 0–5000 (0 = instant) | 600 |
| `delay_ms` | integer | 0–5000 | 0 |
| `easing` | enum or function | `ease-out`, `ease-in`, `ease-in-out`, `linear`, `spring`, `smooth`, `cubic-bezier(x1,y1,x2,y2)` | `ease-out` |
| `origin` | enum | `center`, `top`, `bottom`, `left`, `right`, `top left`, `top right`, `bottom left`, `bottom right` | `center` |
| `keyframes` | array | 2–8 frames | **required when `type:"custom"`; invalid on any other type** |

- A definition with one of the eight preset types needs no keyframes: the
  engine supplies that preset's keyframes (§4.9.6). `duration_ms` is still the
  authored value, so `{ "type": "fade_in", "duration_ms": 450 }` is a complete
  animation.
- `type: "custom"` is the only shape that accepts `keyframes`; a preset with
  keyframes is rejected (drop + warning, fall back per phase).
- `type: "typewriter"` takes the fields in §4.9.5 instead of keyframes.

Keyframe fields:

| Field | Type | Allowed / range |
|---|---|---|
| `at` | number | 0–100, strictly increasing; first must be 0, last must be 100 |
| `opacity` | number / `"base"` | 0.0–1.0, or the element's resting opacity |
| `translate_x` | length | -2000–2000 px, or -200–200 `%` of the element's own width |
| `translate_y` | length | -2000–2000 px, or -200–200 `%` of the element's own height |
| `scale` | number | 0.01–4.0 (uniform) |
| `rotate` | number | -1080–1080 degrees |
| `blur` | length / `"base"` | 0–60 px, or the element's resting blur |

Rules:

- A property is animated only between the frames that define it. A frame that
  omits `opacity` is not an opacity keyframe; the value is interpolated
  between the nearest frames that do define it, and falls back to the
  element's base outside them. This is CSS keyframe semantics, applied per
  property.
- `"base"` resolves at play time from the element's **resting** computed style
  (animations cancelled first). Use it on the final frame when the block's own
  `opacity` is not 1, so a 0.7-opacity block fades back to 0.7 rather than
  snapping to 1.
- Transform components compose in the order `translate → rotate → scale`,
  around `origin`. There is no raw `transform`, `filter`, or CSS string field.
- The engine always clears the animation after it finishes and restores the
  resting style. An entry/`in` definition whose final frame is not the resting
  state gets a validation warning (it will visibly snap); `out` definitions
  are expected to end hidden.
- `duration_ms: 0` renders the end state immediately.

#### 4.9.5 Definition grammar — `typewriter`

```json
{
  "type": "typewriter",
  "label": "Typewriter",
  "duration_ms": 1400,
  "delay_ms": 0,
  "easing": "linear",
  "reveal": "char",
  "cursor": {
    "char": "▌",
    "color": "currentColor",
    "blink_ms": 500,
    "hide_after_ms": 600
  }
}
```

| Field | Type | Allowed / range | Default |
|---|---|---|---|
| `type` | enum | `typewriter` | required |
| `duration_ms` | integer | 0–5000 | 900 |
| `delay_ms` | integer | 0–5000 | 0 |
| `easing` | enum or function | as above; `linear` recommended | `linear` |
| `reveal` | enum | `char`, `word` | `char` |
| `cursor` | object or `"none"` | see below | default cursor |
| `cursor.char` | string | 1–2 visible characters | `▌` |
| `cursor.color` | color / `currentColor` | validated | `currentColor` |
| `cursor.blink_ms` | integer | 0–2000 (0 = no blink) | 500 |
| `cursor.hide_after_ms` | integer | 0–5000 | 600 |

Implementation contract:

- Text is split into grapheme clusters (`Intl.Segmenter` when available,
  `Array.from` fallback) or words for `reveal:"word"`. Whitespace is revealed
  with the preceding segment so line breaks appear at the right moment.
- Reveal uses `visibility:hidden` on per-segment spans, not `display:none`, so
  the full text reserves its layout from the first frame. Centered text does
  not jump as characters appear.
- Existing inline run markup is preserved: the splitter walks text nodes and
  never rebuilds HTML from a string, never uses `innerHTML` for theme or
  content.
- Autosize runs **before** the split. If the split measurably changes wrapping
  (it should not; spans are inline), autosize runs again on the split DOM.
- On completion or cancellation the spans are unwrapped and the original text
  nodes restored, so later renders, outline conversion, and re-fits see normal
  text.
- `typewriter` is legal only on text-bearing blocks (`text`, `title`,
  `reference`, `translation`, and `verse_num` in `block` mode). On a container
  or `body` it is invalid: fall back to `fade_in` + warning. As an `out` slot
  it is invalid: fall back to `fade_out` + warning.
- **Outline conflict.** The true-outline path rebuilds a block's text as
  per-line inline SVG, which destroys per-character spans. A block with a
  block-level `text_outline` therefore cannot typewrite: the engine plays
  `fade_in` instead and Python logs a warning at normalization. The same
  runtime fallback applies when the rendered content contains an outlined
  inline run (`.rc-oc`), which Python cannot see. This is a documented
  limitation, not a silent no-op.

#### 4.9.6 Built-in definitions

The engine ships these names. They are ordinary definitions (same schema) and
can be shadowed by a theme or shared definition of the same name. Each
built-in's `type` equals its name; `none` is a reserved slot value, not a
definition.

| Name | `type` | Phases | Shape |
|---|---|---|---|
| `fade_in` | `fade_in` | entry / in | opacity 0 → base. |
| `fade_out` | `fade_out` | out / transition-out | opacity base → 0. |
| `fade_up` | `fade_up` | entry / in | opacity 0, translateY 20px → resting. |
| `fade_down` | `fade_down` | out / transition-out | resting → opacity 0, translateY 20px. |
| `scale_up` | `scale_up` | entry / in | opacity 0, scale 0.85 → resting. |
| `scale_down` | `scale_down` | out / transition-out | resting → opacity 0, scale 0.85. |
| `slide_up` | `slide_up` | entry / in | translateY 100% → 0 (no opacity change). |
| `slide_down` | `slide_down` | out / transition-out | translateY 0 → 100% (no opacity change). |
| `typewriter` | `typewriter` | entry / in | The primitive in §4.9.5. |

Every built-in definition carries `duration_ms` (600 ms, `typewriter` 900 ms),
so a bare name is complete and the resolved payload is self-describing.

The resolved payload carries every **named** definition the theme references,
including built-ins, so the renderer never needs its own copy. Inline
definitions stay inline in their slot. The built-in table in Python is the
single source of truth; `display.js` keeps only a minimal v1 converter for raw
payloads that bypass Python (tests, hand injection).

#### 4.9.7 Safety and failure behavior

- No `@keyframes`, no raw CSS, no `animation` shorthand strings, no arbitrary
  properties. Names are identifiers, never interpolated into CSS.
- Values are validated and clamped; an invalid frame drops the definition and
  falls back per phase.
- Animation is decoration, never a visibility gate. If `element.animate` is
  missing, throws, or the definition is invalid, the element is shown
  immediately in its resting state.
- `prefers-reduced-motion: reduce` skips all animation and renders the end
  state immediately.
- Autosize and outline conversion always run on resting styles; a transform
  animation must not be measured.

#### 4.9.8 Freeform

The same model applies. Only the first container may be visible (§4.8), but
its blocks may animate independently, and a freeform `title` may typewrite
while the lyrics fade.


---

## 5. Shared files

### 5.1 Location and discovery

`themes/_shared/` holds shared definitions:

```
themes/_shared/borders.json
themes/_shared/shadows.json
themes/_shared/palettes.json
themes/_shared/animations.json
```

The loader MUST skip every path whose relative parts contain a segment
starting with `_`. This keeps shared files out of `_cache`, `get_theme_names()`,
`get_themes_by_kind()`, and the theme menus. It also means a theme named
`_foo.json` is not loadable; that is intentional and documented.

Why one file per family instead of one `shared.json`: separate files keep
merge conflicts and hand-editing small, let the loader watch mtimes
independently, and let a missing/corrupt file degrade one family only.

### 5.2 `borders.json`

```json
{
  "schema_version": 2,
  "borders": {
    "gold_frame": {
      "width": 2, "style": "solid", "color": "@gold", "radius": 12,
      "sides": {
        "top": { "width": 4, "color": "#ffffff" }
      }
    },
    "hairline": { "width": 1, "style": "solid", "color": "rgba(255,255,255,0.18)" }
  }
}
```

Same structured fields as §4.2.1. A border entry may use `@name` colors from
`palettes.json`.

### 5.3 `shadows.json`

```json
{
  "schema_version": 2,
  "shadows": {
    "soft": { "x": 0, "y": 24, "blur": 48, "spread": -12,
              "color": "rgba(0,0,0,0.55)" },
    "ring": { "x": 0, "y": 0, "blur": 0, "spread": 1,
              "color": "rgba(255,255,255,0.08)", "inset": true }
  }
}
```

### 5.4 `palettes.json`

```json
{
  "schema_version": 2,
  "colors": {
    "gold": "#D4AF37",
    "lime": "#AAFF00",
    "ink": "rgba(0,0,0,0.6)",
    "white": "#ffffff"
  }
}
```

### 5.5 `animations.json`

```json
{
  "schema_version": 2,
  "animations": {
    "verse_rise": {
      "type": "custom",
      "label": "Verse rise",
      "duration_ms": 700,
      "easing": "ease-out",
      "keyframes": [
        { "at": 0,   "opacity": 0,      "translate_y": 36, "blur": 6 },
        { "at": 70,  "opacity": 0.85,   "translate_y": 6,  "blur": 0 },
        { "at": 100, "opacity": "base", "translate_y": 0,  "blur": 0 }
      ]
    },
    "lyric_typewriter": {
      "type": "typewriter",
      "label": "Lyric typewriter",
      "duration_ms": 1400,
      "easing": "linear",
      "reveal": "char",
      "cursor": { "char": "▌", "color": "@gold", "blink_ms": 500, "hide_after_ms": 600 }
    }
  }
}
```

- The same definition grammar as §4.9.4/§4.9.5. A shared definition may use
  `@color` in `cursor.color`; keyframe values are numbers and have no shared
  refs.
- **Name resolution:** theme-local `animations` overrides `_shared`, which
  overrides the built-in registry. Shadowing logs at DEBUG.
- A definition is self-contained. A `use` or shared reference inside a
  definition body is invalid (no cross-definition cycles).
- A malformed entry is dropped with a warning; a slot referencing it falls
  back per phase (§4.9.2).

### 5.6 Reference syntax and resolution

- Object-valued fields (`border`, `box_shadow`, and a shared entry's own
  nested fields) use `{ "shared": "<name>" }`.
- String-valued color and paint fields accept `"@<name>"`: `color`,
  `background` (as a solid paint), structured `border.color`/`box_shadow.color`,
  and the color component of a `text_outline` string. Colors inside a gradient
  stop remain literal; `@name` is not expanded inside gradient strings or
  shadow strings.
- Lookup namespace is determined by the field: `border` searches
  `borders.json`, `box_shadow` searches `shadows.json`. A name is also looked
  up in the other family only if it is unambiguous; if two families define the
  same name, the field's own family wins and a warning is logged.
- Animation slots look up `animations.json` by name; there is no cross-family
  fallback for animations (a border name never resolves as an animation).
- Shared definitions may reference `@colors`; resolution is recursive with a
  depth limit of 4 and cycle detection (a cycle → field default + warning).
- Missing name → field default + warning. A malformed shared file is logged
  and treated as empty; references to it fail the same way.
- Shared files are loaded once and refreshed by mtime, like themes.

### 5.7 Why not reusable text styles

Named text styles were evaluated and **deferred**. They overlap with the block
parameter set and introduce a second cascade (`shared style < block < deck
slide_format`) that the designer cannot represent today. Borders and shadows
are structural, reused across containers, and have no existing cascade;
palettes are a one-line indirection with no ambiguity. Text styles can be
added in a later schema version without breaking v2 if a real need appears.

---

## 6. Validation, sanitization, and fallback

### 6.1 Pipeline

```
raw JSON (disk)
  → _load_all()                    # untouched, cache for designer
  → normalize_theme(raw, kind)     # migrate v1, resolve shared, validate
       ├─ ThemeReport(warnings, errors)
       ├─ resolved v2 dict (complete, defaults filled)
       └─ or SAFE_THEME on fatal error
  → resolve_theme() returns (name, resolved)
  → payload["theme_data"] = resolved
  → display.js renders resolved (with a last-resort JS guard)
```

`normalize_theme` is pure: it never writes to disk, never mutates `raw`, and
is safe to call on every payload build. Phase 2 caches the result keyed by
`(theme name, file mtime, raw object id)` so per-payload cost stays negligible.

### 6.2 Types and coercion

- Integers/floats accept JSON numbers and numeric strings (`"42"`, `"42px"`).
  A unitless string for a length is px. Anything else is invalid.
- Booleans accept `true`/`false` only. `"true"`/`"false"` are accepted with a
  warning (hand-edited files); other values fall back.
- Enums are case-sensitive; an invalid value falls back to the documented
  default and logs `theme=<name> path=<json.path> value=<v> fallback=<d>`.
- Numbers outside a range are **clamped**, with a warning. NaN/Infinity are
  invalid and fall back.
- Unknown keys are ignored by the renderer and **preserved** by the designer's
  round trip. The normalizer reports them once per path at DEBUG (not WARNING)
  so hand-written themes do not spam logs.

### 6.3 CSS and HTML safety

Every string that reaches CSS is validated by `sanitize_css_value(value, kind)`:

- max length 300 (shadow/gradient 600); reject control characters;
- reject `;`, `{`, `}`, `<`, `>`, backslash, `/*`, `*/`;
- reject `url(`, `expression(`, `@import`, `javascript:`, `behavior:`,
  `-moz-binding`, `var(`;
- kind-specific allowlists:
  - `color`: `#rgb/#rgba/#rrggbb/#rrggbbaa`, `rgb()/rgba()/hsl()/hsla()` with
    numeric args, `transparent`, `currentColor`, CSS named colors from a fixed
    list;
  - `paint`: color or `linear-gradient()/radial-gradient()` with numeric/
    color stops (no `url`, no nested functions outside the allowlist);
  - `shadow`: 1–12 comma-separated shadows of 2–4 lengths + color;
  - `filter`: allowlisted filter functions with bounded numeric args;
  - `outline`: `<length> <color>`;
  - `font_family`: `^[A-Za-z0-9 ,'"_-]+$`, ≤ 120 chars;
  - `length`: number + optional unit, bounded per field.
- Invalid → documented default + warning.

HTML safety: theme strings never enter `innerHTML`. The renderer creates
elements and sets `textContent` for content; theme values go through
`style.setProperty` or validated attributes. Block/container ids are used as
`class`/`data-*` only after the id regex passes. The payload's `text`,
`reference`, and `translation` remain escaped as they are today (top-level
strings pass through `sanitize_payload`; the preview path must escape at
render time — a pre-existing gap that Phase 3 closes by using `textContent`
wherever HTML is not the documented inline-markup path).

The WS sanitizer is shallow. **Theme safety therefore lives in
`normalize_theme`, not in `sanitize_payload`.** Phase 2 may additionally
deep-normalize `theme_data` in `broadcast_display()` as defense in depth, but
the authoritative gate is the normalizer.

### 6.4 Fallback ladder

1. Invalid field → default (clamp first for range errors).
2. Missing required container/block structure → synthesize defaults; if no
   container survives, go to 3.
3. Theme fails normalization (wrong root type, `schema_version > 2`, no valid
   container after repair) → **built-in `SAFE_THEME`**, log an error with the
   theme name. (Excess containers beyond 16 are dropped with a warning; that
   alone is not a normalization failure.) `SAFE_THEME` is not a bare screen:
   it is the exact visual contract of today's
   `themes/scripture/fullscreen.json`, expressed as a v2 theme and named
   `SAFE_THEME` in `core/theme_schema.py`:

```json
{
  "schema_version": 2,
  "name": "safe_fallback",
  "label": "Safe fallback",
  "kind": "scripture",
  "canvas": { "width": 1920, "height": 1080, "background": "transparent", "fit": "contain" },
  "containers": [{
    "id": "main",
    "layer": 0,
    "visible": true,
    "position": { "anchor": "top_left", "x": 60, "y": 40 },
    "width": 1800, "height": 1000,
    "min_width": 1800, "max_width": 1800,
    "min_height": 0, "max_height": null,
    "background": "transparent", "border": "none", "border_radius": 0,
    "box_shadow": "none", "backdrop_filter": "none",
    "opacity": 1.0, "overflow": "hidden",
    "blocks": {
      "body": { "visible": true, "valign": "center", "gap": 0, "padding": 0 },
      "text": {
        "visible": true, "autosize": true,
        "color": "#ffffff", "font_family": "'Nunito', sans-serif",
        "size": 80, "min_size": 60, "max_size": 96, "weight": 700,
        "line_height": 1.08, "letter_spacing": "-0.02em",
        "text_shadow": "none", "text_outline": "none",
        "text_transform": "none", "text_align": "center",
        "margin_top": 0, "margin_right": 0, "margin_bottom": 24, "margin_left": 0
      },
      "reference": {
        "visible": true, "position": "below_verse",
        "color": "#D4AF37", "font_family": "'Nunito', sans-serif",
        "size": 48, "weight": 800, "line_height": 1.2,
        "letter_spacing": "0.1em", "text_transform": "uppercase",
        "text_align": "center", "text_shadow": "none", "text_outline": "none"
      },
      "translation": {
        "visible": true, "position": "right_of_reference",
        "color": "#AAFF00", "margin_left": 8
      },
      "verse_num": {
        "visible": true, "mode": "inline",
        "color": "#D4AF37", "font_family": "'Nunito', sans-serif",
        "size": "0.6em", "weight": 700, "opacity": 0.7,
        "vertical_align": "top", "margin_right": "0.15em", "line_height": 1
      }
    }
  }]
}
```

   At 1920×1080 this is pixel-identical to today's `fullscreen`: box at
   60,40 sized 1800×1000; 80px white text fitted between 60 and 96, weight
   700, line-height 1.08, letter-spacing -0.02em; gold 48px/800 uppercase
   reference with 0.1em tracking; lime translation to its right with an 8px
   gap; gold inline verse number; content vertically centered.
   `canvas.fit: "contain"` only changes behavior on outputs that are not
   1920×1080: the safe theme scales instead of overflowing. It renders
   freeform content through the same `text`/`reference` payload fields, so a
   broken freeform theme still shows its lyrics and title.
4. Renderer receives `theme_data` that is missing or not a v2 object → render
   the JS-side safe fallback (same visual contract), never a blank screen.


A theme that is *valid but empty* (one visible container with no visible
blocks) is allowed; it renders nothing. It is not a normalization failure.

### 6.5 `schema_version`

`schema_version` selects the parser; it is never guessed from shape once
present.

- absent → v1 → migrate;
- integer `1` → migrate (a file may explicitly declare 1);
- integer `2` → validate as v2;
- numeric string `"1"`/`"2"` or float `1.0`/`2.0` → accepted as that integer
  with a warning (hand-edited files);
- anything else — including `>2`, `0`, negative, non-numeric, or `null` — →
  **`SAFE_THEME` + error**. There is no best-effort parse of a newer format:
  a half-rendered screen on a live Sunday is worse than the known-good
  fullscreen fallback.

Migration never rewrites the file. `save_theme()` writes exactly what the
designer gives it. A v2 theme saved by the designer keeps `schema_version: 2`.
A v1 theme edited by the designer stays v1 (the file is not silently
upgraded); it is migrated in memory on every load.

---

## 7. V1 → V2 migration

Migration is deterministic: same input bytes → same output dict. It runs in
`normalize_theme`, before validation (so the validator only ever sees v2).

### 7.1 Top level

| V1 | V2 | Notes |
|---|---|---|
| *(no `schema_version`)* | `schema_version: 2` | |
| `name`, `label`, `description`, `author` | same | |
| `animations` (v1 assignment object) | assignments on the first container's `animation` | See 7.6. |
| `slide.show_title` | `title.visible` (freeform) | Also kept in `slide` for old readers. |
| *(no `canvas`)* | `canvas: {width:1920, height:1080, background:"transparent", fit:"none"}` | V1 had no canvas. `fit:"none"` preserves today's raw-pixel OBS behavior; only new hand-written v2 themes default to `contain`. |
| `containers` (dict, nested blocks) | `containers` (array) | Each entry gets `id`, `layer = index * 10`, `visible: true`. |
| unknown top-level keys | preserved | Not copied into the resolved dict; kept in raw. |

### 7.2 Container

| V1 | V2 | Notes |
|---|---|---|
| dict key | `id` | |
| *(new)* | `layer = index * 10` | Definition order. |
| *(new)* | `visible: true` | |
| `x`, `y` numbers | `position: {anchor:"top_left", x, y}` | Today `left = x`, `top = y`, so top-left. |
| no `x`/`y` | synthesized position from page flex | See 7.3. |
| `width`, `height`, `min_width`, `max_width` | same (coerced to px numbers) | `"1843px"` → `1843`. |
| *(new)* | `min_height: 0`, `max_height: null` | |
| `background`, `border`, `border_radius`, `box_shadow`, `backdrop_filter` | same strings | Validated; v1 values are preserved verbatim when they pass. |
| `padding` | `body.padding` + four side fields | Container padding is content inset in v2; `"0"` → 0. No container padding keys survive. |
| `display`, `flex_direction`, `justify_content`, `align_items` | converted or dropped | See 7.4. |
| `body.vertical_align` | consumed into the synthesized position when the container has no `x`/`y`; otherwise dropped | In v1 this aligns the whole box on the page, not content inside it. It is **not** `body.valign`. See 7.3. |
| `body.padding_bottom` | used as the page inset `pb` in §7.3 when there is no `x`/`y`; otherwise dropped | This is page padding, not content inset. It never becomes `body.padding_bottom` in v2. |
| `body` (other keys) | preserved under `body` | |
| `text`, `reference`, `translation`, `verse_num` | same keys in `blocks` | See 7.5. |
| *(new)* | `animation` on the first container | v1 animated the single `#container` box; see 7.6. |

**Padding precedence.** Container `padding*` initializes `body.padding*`.
A v1 `body.padding_bottom` is a **page** inset used only to synthesize the
position in §7.3; it is never merged into the content inset. This keeps
shipped themes (container padding `"0"`, body bottom `"0"`) and flat or
hand-written themes (40px container pad, optional page bottom) both exact.

### 7.3 No-explicit-position v1 themes

When a v1 container has no numeric `x`/`y`, the page centers it horizontally
and aligns it vertically per `<body>`'s `align-items: var(--rc-vertical-align,
flex-end)` with `padding-bottom`. V2 has no page flex, so migration
synthesizes:

- horizontal: `anchor` is one of `center`/`left`/`right` only if width is
  fixed; v1 always centers horizontally, so use `center` and `x = 0`.
- vertical, with page `padding_bottom` = `pb` (default 80 if absent):
  - `vertical_align: flex-start|top` → `anchor: "top"`, `y = 0`;
  - `vertical_align: center` → `anchor: "center"`, `y = -pb / 2` (the content
    box is `pb` shorter at the bottom, so its center sits `pb/2` above the
    canvas center);
  - anything else, **including absent** → `anchor: "bottom"`, `y = pb`
    (the v1 CSS fallback is `flex-end`).
- width/height stay as written; absent width uses the v1 CSS defaults
  (`min-width:60%`, `max-width:80%`, `width:auto`) → v2 `width:"auto"`,
  `min_width:"60%"`, `max_width:"80%"`.
- The page `padding_bottom` is **not** copied into `body.padding_bottom`;
  the container's own `padding` (if any) already initialized the content
  inset. Only position synthesis consumes `pb`.

Position synthesis is the only migration step that consumes v1 page-flex
values instead of copying them. It is deterministic and documented here.

### 7.4 Removed flex keys

Shipped v1 themes all use `display:flex`, `flex_direction:column`,
`justify_content:center`, `align_items:center`, so dropping them is exact.

For hand-written variants:

- `justify_content:flex-start|flex-end|center` → `body.valign:
  top|bottom|center`. Absent → `top` (the v1 `#container` CSS fallback is
  `flex-start`). Other values (`space-between`, etc.) → `center` + warning.
- `align_items:flex-start|flex-end|center` → each present block's
  `text_align: left|right|center` **only if the block does not already set
  `text_align`**. `stretch`/`baseline` → leave the block default + warning.
- `flex_direction:row|row-reverse` cannot be represented in the v2 column
  stack → `column` + warning. (No shipped theme uses it.)
- `body.vertical_align` is **not** an internal-stack value; §7.3 consumes it
  into the position only when `x`/`y` are absent. When `x`/`y` exist it had no
  visible effect in v1 and is dropped, not copied to `body.valign`.

### 7.5 Blocks

| V1 key | V2 key | Notes |
|---|---|---|
| `text.color/font_family/size/weight/line_height/letter_spacing/text_shadow/text_transform/text_align` | same | |
| `text.min_size`, `text.max_size` | same | Absent → v1 renderer defaults `4` / `300`. |
| `text.margin_bottom` | `margin_bottom` | |
| `text.text_outline` | same | Freeform already uses it. |
| *(new)* | `autosize: true` | |
| `reference.*` | same | Absent values take the v1 `#verse-ref` defaults (24px/500/`#94a3b8`/DM Sans/uppercase/0.1em). |
| *(new)* | `reference.position: "below_verse"` | Today's line is below text. |
| `translation.color`, `translation.margin_left` | same | |
| *(new)* | `translation.position: "right_of_reference"` | Today's inline span after the reference. |
| *(new)* | translation typography | Resolved from the reference block: font, size, weight, line-height, letter-spacing, transform. This is what CSS inheritance does today, so the line does not move. |
| `verse_num.color`, `verse_num.font_family` | same | |
| *(new)* | `verse_num.mode: "inline"` | |
| *(new)* | `verse_num.size:"0.6em"`, `weight:700`, `opacity:0.7`, `vertical_align:"top"`, `margin_right:"0.15em"`, `line_height:1` | Explicit so v2 rendering does not depend on engine defaults. |
| hard `text_shadow` ring | `text_outline` = compiled ring, `text_shadow: "none"` | Matches today's `theme_outline()` behavior. A soft shadow stays a shadow. |
| `body` block | pseudo-block, same key set | `vertical_align` → `valign`. Container `padding` → `body.padding`. |

### 7.6 Animations

V1 stored one assignment object at the top level and applied it to the single
`#container` box. Migration converts it to a per-container `animation`
assignment and leaves the rest of the theme untouched:

| V1 | V2 | Notes |
|---|---|---|
| `animations.display_enter.type` | first container `animation.entry.use` | |
| `animations.display_enter.duration_ms` / `.easing` | same slot's `duration_ms` / `easing` | Absent → `600` / `ease-out`, the v1 renderer defaults. |
| `animations.between_slides.in_type` | first container `animation.transition.in.use` | |
| `animations.between_slides.duration_ms` / `.easing` | `transition.in` overrides | Absent → `600` / `ease-out`. |
| `animations.between_slides.out_type` | **not mapped** | Today's renderer never plays it (`_runAnimation` uses only `in_type`). It stays in the raw file; mapping it would add an exit phase v1 never showed. |
| `animations.display_exit.type` | first container `animation.out.use` | |
| `animations.display_exit.duration_ms` / `.easing` | `out` overrides | Absent → `400` / `ease-out`, the v1 exit defaults. |
| `type: "none"` / missing | no slot | |
| `type: "typewriter"` | `typewriter` | v1's renderer never implemented it, so it was a no-op; v2 honors the author's original intent. This is the one animation behavior that intentionally becomes more than v1. |

Only the **first** container receives the assignment. V1 rendered only the
first container; hand-written extra containers were invisible, so animating
them in v2 would be new behavior. The resolved `animations` registry contains
the definitions those slots reference.

### 7.7 Legacy and flat shapes

- **Flat theme** (`{text:{...}, reference:{...}, container:{...}}`):
  synthesize one container `main` with the flat `container` form, blocks from
  the top-level blocks, `position: center`, and v1 CSS defaults for any form
  value that is absent (`background: rgba(15,23,42,0.6)`, `border_radius:
  24px`, etc. — the `themes.css` defaults). The old `#container` 40px padding
  becomes `container.blocks.body.padding: 40`, because containers have no
  padding in v2.
- **Oldest absolute boxes** (`containers: {text:{x,y,width,height,...},
  reference:{...}, translation:{...}}`): create one container per box, id =
  the key. Those x/y are **center** coordinates today
  (`left = x - width/2`), so `position = {anchor:"center", x: box.x - W/2,
  y: box.y - H/2}` in canvas coordinates, or equivalently compute the
  top-left once and use `top_left`. Carry the hardcoded defaults from
  `_positionContainer` (20px inset → `blocks.body.padding: 20`, 34px
  reference, 16px translation) into the block params. Each box is a separate container; they
  do not share a stack.
- Mixed shapes: a `containers` dict that contains any nested `text`/`body`
  object uses the normal v1 path; otherwise the absolute-box path.

### 7.8 What migration cannot represent

- arbitrary row layouts, grids, and per-block absolute boxes inside one
  container (v1 could not express these either, except the oldest shape);
- raw CSS values that fail the v2 sanitizer (they fall back with a warning);
- more than 16 containers (the excess is dropped with an error to safe theme
  if no container survives);
- **flat themes with non-zero container padding under autosize.** V1's
  `autoFitText` compares text height with the container's outer height, even
  though CSS padding shrinks the content box; v2 measures the content area
  after `body.padding`. Shipped themes use `padding:0`, so they are exact.
  A hand-written flat theme with 40px padding may fit text slightly smaller.
  This is a deliberate correctness fix, recorded here rather than hidden;
- **`align_items:center` with non-center `text_align`.** V1 shrink-wraps the
  flex item, then applies `text_align` inside that width; v2 stretches each
  block row to the container and applies `text_align` across the full width.
  With `text_align:center` (all shipped themes) the result is identical; with
  `left`/`right` the v2 text moves to the container edge. The migration
  preserves the explicit `text_align` and logs a warning when this
  combination is detected.

---

## 8. Hardcoded inventory and classification

Legend: **T** = becomes a theme parameter; **E** = stays engine behavior
(reason). File paths are the current locations.

### 8.1 `display/themes.css`

| Current hardcode | Class | v2 home / reason |
|---|---|---|
| `@font-face` Nunito local + Google fallback | E | Bundled asset/loading strategy. |
| `*` reset (margin/padding/box-sizing) | E | Engine reset. |
| `body,html` `100vw/100vh`, transparent background | E | Viewport/stage; `canvas.background` overrides paint. |
| `body` flex center + `align-items: var(--rc-vertical-align, flex-end)` + `padding-bottom: var(--rc-padding-bottom, 80px)` | T | `position` synthesis (§7.3); this is page placement, not `body.valign`. |
| `#container` `max-width:80%`, `min-width:60%`, `width:auto`, `height:auto` | T | Container `width/height/min_*/max_*` defaults. |
| `#container` `padding:40px` | T | `body.padding` — padding is content, never container geometry. |
| `#container` `border-radius:24px` | T | Container form. |
| `#container` glass background, `backdrop-filter:blur(16px)`, border, shadow | T | Container form. |
| `#container` `display:block` + flex props | E | Engine stack (flex column). |
| `#container` `opacity:1`, `transform:none`, transition none | E/T | Opacity is a form param; transform is engine animation state. |
| `#container.hidden` opacity/translate/scale | E | Clear/exit animation primitive. |
| `.rc-oc` outline construction, `isolation`, pseudo-element | E | Algorithm; `text_outline` supplies the value. |
| `#verse-text` font family/size/weight/style/line-height/color/align/transform/decoration/direction/shadow/margin-bottom/letter-spacing | T | `text` block shared params. |
| `#verse-text` min/max font size | T | `text.min_size/max_size` (algorithm stays). |
| `.verse-num` 0.6em/700/0.7/top/0.15em/line-height 1 | T | `verse_num` block defaults. |
| `#verse-ref` DM Sans/1.5rem/500/#94a3b8/center/uppercase/0.1em | T | `reference` block defaults. |
| `#verse-ref-translation` #64748b/margin-left 8px | T | `translation` block defaults. |
| `.rc-container` hidden/absolute/overflow hidden | E | Legacy absolute path; v2 containers use container form. |

### 8.2 `display/display.html`

| Current hardcode | Class | v2 home / reason |
|---|---|---|
| Single `#container` with `#verse-content` and fixed ids | E | DOM skeleton; v2 builds one node per container/block. |
| `#ct-text/#ct-reference/#ct-translation` legacy nodes | E | Legacy absolute path; kept only as a v1 renderer fallback if JS coercion is used. |
| Inline `.rc-container` display/overflow and duplicated `.verse-num` 0.6/0.3em | E/T | Structural rule is engine; number metrics are `verse_num` params. |
| Google Fonts `<link>` | E | Asset loading; families are theme data. |

### 8.3 `display/display.js`

| Current hardcode | Class | v2 home / reason |
|---|---|---|
| `resetTheme()` variable list | E | Reset must enumerate engine-owned variables. |
| `_isNewContainers` / `themeContainer` first-container choice | E | Replaced by resolved `containers` array + `theme_container` semantics. |
| `applyTheme` mapping of every `--rc-*` var | E | The mapping itself is engine; values are theme params. |
| Only `x`/`y` top-left absolute placement | T | `position` anchors/keywords. |
| No `width`/`height` application except CSS vars | T | Container form width/height applied directly. |
| `body.vertical_align`, `body.padding_bottom` | T | Page-level positioning only; consumed by §7.3 when `x`/`y` are absent, never mapped to `body.valign`/content padding. |
| Text/ref/translation/verse_num var mapping | E | Values are block params; mapping is engine. |
| Deck `slide_format` cascade (color, size, min/max, bold, italics, case, underline/strike, align, spacing, dir, outline, shadow, font) | E | Deck-level author intent overrides theme; protocol unchanged. |
| `extractVerseNumber` regex | E | Content behavior; `verse_num.mode` controls rendering. |
| `autoFitText` binary search / deck ceiling / outline refit | E | Algorithm. `size/min/max/autosize` are params. |
| `_applyContainers` legacy absolute boxes | E | Legacy v1 path; v2 uses resolved containers. |
| `_positionContainer` hardcoded colors/fonts/sizes/20px padding/center | T | 20px inset → `body.padding`; block params carry the rest. |
| `ANIM_KEYFRAMES`/`ANIM_EASINGS` | T/E | Built-in definition registry plus user keyframes in Python; `display.js` plays data. |
| `_runAnimation` display_enter/between_slides/display_exit | E | Application and sequencing are engine; phase selection and definitions are theme data. |
| `typewriter` offered by the designer, unimplemented | T/E | New engine primitive in §4.9.5; outline conflict falls back to `fade_in`. |
| `renderInlineColors`/`spanStyle` inline markup | E | Content protocol, not theme. Block params are the base style. |
| `handlePayload` reference/translation updates, empty-ref hiding, verse-num prepend | E | Content behavior; v2 `visible`/positions override placement, not the empty-ref rule. |
| `document.body.className = "theme-" + data.theme` fallback | E | Legacy name-only fallback; no CSS theme classes are defined, so it is a no-op today. |
| `resizeCanvas` (only in `display_view.py`) | E | Moved into the shared renderer as `canvas.fit`; see Phase 3. |

### 8.4 Python

| Current hardcode | Class | v2 home / reason |
|---|---|---|
| `theme_loader._load_all` kind = folder name | E/T | Kind is metadata; `kind` field is validated against folder. |
| `theme_loader.theme_container` first dict entry | E | v2 array; helper returns first container. |
| `resolve_theme` per-kind fallback names | E | Contract (`docs/theme-switch-contract.md`). |
| `slide_title_visible` reads `slide.show_title` | T | `title.visible`, legacy fallback. |
| `theme_outline` hard-shadow regex | E | Migration converts hard rings to explicit `text_outline`; helper kept for v1 callers. |
| `display_format_defaults` maps theme text to ribbon | E | Reads resolved/v1 block; no new parameter. |
| `websocket_server.sanitize_payload` shallow escape | E | Theme safety is the normalizer; content escaping stays. |
| `display_state` payload matching ignores theme identity | E | Theme switch must not invalidate content identity. |
| `display_view` duplicated renderer and preview `resizeCanvas` | E | Must mirror the main renderer; preview scaling moves into the renderer. |
| `theme_properties_panel` legacy key set / forced flex keys | E (compat) | Phase 2 adapter; the UI is not redesigned. |
| `container_editor` top-level `theme["container"]` model | E (compat) | Legacy branch; v2 themes ignore it. |
| `theme_animations_panel` dead connection | E (compat) | Panel remains unwired; v2 `animation` fields round-trip untouched, editing is out of scope. |
| `draggable_editor` defaults | E | Dead code, not instantiated. |

---

## 9. Compatibility

### 9.1 WebSocket payload

No new top-level payload fields. Changes:

- `theme_data` is now a **resolved v2 dict** (`schema_version: 2`,
  `containers` is an **array**, all defaults filled, shared refs resolved).
- `theme_data.containers` changes type from object to array. Any external
  client that reads `theme_data.containers` must adapt; clients that only run
  the bundled `display.js` need no change.
- `theme_data.animations` changes meaning: v1 held one assignment object
  (`display_enter` / `between_slides` / `display_exit`); v2 holds a map of
  **resolved definitions** (`name → definition`) referenced by the theme.
  Assignments live on `container.animation` and `block.animation`. External
  clients that read the v1 keys must adapt; `display.js` reads the new shape.
- Container `padding*` keys no longer exist in `theme_data`; content inset is
  `container.blocks.body.padding*` / `container.blocks.<id>.padding*`.
- `theme` remains the theme name. `reference`, `translation`, `text`, `ref`,
  `book`, `chapter`, `verse`, `slide_format`, `content`, `deck_id` unchanged.
- `display_state` continues to store/restore the payload as-is. Stored v2
  payloads restore correctly; a stored v1 payload from before an upgrade
  restores as v1 and renders through the JS coercion path (or is replaced by
  the next live payload).
- `sanitize_payload` behavior is unchanged (top-level strings only), but
  `theme_data` is now safe by construction.

`docs/theme-switch-contract.md` gets a "theme_data shape" section and a note
that `theme_data` is resolved v2, never raw v1. The switch primitive's
guarantees (non-null, per-kind fallback) are unchanged.

### 9.2 Theme Designer round trip

What is preserved by Phase 2's adapter:

- top-level unknown keys and other containers (already preserved by the deep
  copy);
- v2 `containers` array (converted to a dict view for the widgets, converted
  back without losing order or fields);
- unknown keys inside the active container;
- unknown keys inside managed blocks (merge instead of replace);
- `body`, `position`, `layer`, `visible`, shared refs, and block params the
  panel cannot edit.

What still cannot be edited (reported, not fixed in this task):

- more than the first container;
- container `layer`, `visible`, `position` keywords/anchors,
  `min_height`/`max_height`, `overflow`, `opacity`;
- content padding (`body.padding*`, block `padding*`) — the designer's old
  container-padding widgets must not write container `padding*`;
- block `visible` (toggles remove the block for v1 themes; for v2 themes the
  adapter writes `visible:false` instead), block `position` (reference/
  translation/verse_num), margins other than `translation.margin_left`,
  `text_outline`, `font_style`, `text_decoration`, `word_spacing`, `opacity`,
  `max_lines`, `direction`;
- animations (the panel is still not wired; assignment editing is out of
  scope for this task, but the fields must round-trip untouched);
- top-level `canvas`, `kind`, `schema_version` (shown in JSON, not editable as
  widgets);
- the legacy `container` editor branch (writes top-level `container`, which v2
  ignores).

The designer MUST not crash on a v2 theme. `load_theme()` must accept an array
or a dict; `_collect_theme()` must operate on the active container in place.

### 9.3 Preview paths

`ThemePreview.apply_theme()` and
`ThemeDesignerTab._apply_to_previews()` currently send raw `_working_theme`.
Phase 2 resolves it before calling `DisplayView.display_verse()` (and/or
`DisplayView.apply_theme()` resolves defensively). `ThemePreview` is used by
the designer, quick editor, and lite designer, so one fix covers all three.

---

## 10. Decisions and resolved ambiguities

These are the choices the format makes. Items marked **confirmed** were
explicitly decided during Phase 1 review; the rest are implementation policy
for Phases 2–4.

1. **`containers` is an array. (confirmed)** Order is explicit and stable
   across editors; equal-layer ties use it. The designer gets a narrow
   array↔dict adapter.
2. **Equal layers.** Definition order; later array entries paint in front.
   `z-index` mirrors `layer`.
3. **Duplicate blocks across containers.** Allowed and independent. Each
   occurrence has its own params and autosize; no ownership.
4. **Duplicate blocks inside one container.** Invalid. The first in render
   order wins, the rest are dropped with a warning.
5. **Block relative to a missing block.** Documented fallback in §4.7, one
   warning per resolution.
6. **`body` is a pseudo-block. (confirmed)** It owns visibility, vertical
   alignment, gap, and padding; its typography is inert.
7. **Container padding is removed. (confirmed)** Position and size are
   absolute and discrete. Padding is a content parameter only: `body.padding*`
   and block `padding*`. Container `padding*` keys are ignored with a warning.
8. **Freeform is single-visible-container. (confirmed)** Extra containers must
   be `visible:false`; otherwise they are dropped with a warning. This avoids
   hidden state the designer cannot show or fix.
9. **Translation default. (confirmed)** `right_of_reference`, matching today's
   inline span, so migrated themes do not move. Its typography is resolved
   from the reference block unless explicitly overridden; `margin_left`
   defaults to 8px.
10. **Reference default.** `below_verse`, matching today. Reference defaults
    are today's `#verse-ref` values (24px/500/`#94a3b8`/DM Sans/uppercase/
    0.1em).
11. **`verse_num` default.** `inline`, reproducing today's span exactly
    (0.6em/700/0.7/top/0.15em/1), including extraction from the reference's
    trailing `N:N`.
12. **Position semantics. (confirmed)** The unconstrained axis is centered
    unless its coordinate is given. A given `x`/`y` is an absolute edge
    distance, except for `center`, where it is an offset from the centered
    position. `left`+`y` ≡ `top_left`; `top`+`x` ≡ `top_left`.
13. **Percentage scope. (confirmed)** Percentages resolve against the
    1920×1080 design canvas — `canvas.width`/`canvas.height` — never the
    output or viewport size. Allowed only for position offsets and container
    width/height/min/max; other lengths are px/em.
14. **`fill` and explicit size.** `fill` wins, ignores width/height/x/y, and
    logs a warning if any were set.
15. **Auto size resolution.** Resolve widths, lay out, measure auto heights,
    clamp, then position. `center` + `height:auto` is therefore deterministic.
16. **Future schema versions. (confirmed)** `>2` → `SAFE_THEME` + error. No
    best-effort parse of a newer format.
17. **Safe fallback. (confirmed)** `SAFE_THEME` is the current
    `themes/scripture/fullscreen.json` look, explicitly defined in §6.4 — not
    a bare black screen. At 1920×1080 it is pixel-identical; `fit:contain`
    only changes non-1920 outputs.
18. **Canvas scaling. (confirmed)** `canvas.fit: "contain"` for v2;
    migrated v1 sets `"none"` so shipped themes stay pixel-identical (and may
    still overflow non-1920 OBS sources, as they do today). The preview's
    outer scale moves into the renderer so there is one implementation.
19. **`typewriter`. (confirmed)** Implemented as a definition `type`
    (§4.9.5). It works on text-bearing blocks; block-level or inline outlines
    force `fade_in` because the outline path converts text to SVG. This is
    documented, not silent.
20. **Animation is a content parameter. (confirmed)** Containers, `body`, and
    blocks carry `animation` with `entry`, `transition` (`out`/`in`), and
    `out`. Definitions are reusable data, not global stage settings.
21. **Animation definitions. (confirmed)** Named definitions live in the
    theme, `themes/_shared/animations.json`, and a built-in registry; local
    overrides shared overrides built-in. Definitions are self-contained; slots
    may reference them with per-use overrides or inline them. Every definition
    has a required `type` (`fade_*`/`scale_*`/`slide_*`/`typewriter`/`custom`)
    and a `duration_ms`; `custom` is the only type that carries keyframes.
22. **Animation payload shape.** `theme_data.animations` is the resolved
    definition map for referenced names, not the v1 assignment object. Built-
    ins are emitted too, so the renderer has one source of truth.
23. **Freeform `title` vs `reference`.** `title` is canonical for freeform;
    `reference` is an alias. Both map to the same payload field.
24. **`slide.show_title` vs `title.visible`.** The resolved v2 title block
    wins; `slide.show_title` is the v1 fallback. Payload blanking stays in
    `slide_title_visible()`.
25. **Multiple text blocks per container.** Invalid; first in render order
    wins, rest dropped with a warning. Across containers, duplicates are fine.
26. **`text_shadow` that is really a hard ring.** V1 migration converts it to
    explicit `text_outline` + `text_shadow:none`, matching today's
    `theme_outline()`. V2 never auto-converts; authors choose `text_outline`.
27. **Validation on save.** Do not normalize on save. Validate on
    load/resolve and log; preserving unknown keys is more important than
    rejecting a save.
28. **Theme `kind` mismatch.** Folder kind wins, with a warning.
29. **Negative layers.** Clamp to 0.
30. **Overflow.** Default `hidden` (today); `visible` allowed so
    shadows/outlines can escape. Text still wraps and can clip at the box.
31. **Old absolute-box x/y.** Center-based (today's `_positionContainer`),
    converted to a top-left v2 position. Nested-container x/y stay top-left.
32. **Normalizer fills defaults.** Yes, completely. The renderer must not need
    to know defaults, which removes a whole class of v1/v2 drift.
33. **Missing/duplicate theme `name`.** Filename stem if absent; duplicate
    names keep today's last-file-wins behavior plus a warning.
34. **Shared-name lookup.** Field-family namespace first, then the other
    family if unambiguous; missing → field default + warning. `@name` is
    colors-only. Animation names do not cross families.
35. **Designer round trip.** Array containers are adapted; managed blocks are
    merged, not replaced; unknown/v2 fields survive; the designer never writes
    container `padding*` or legacy flex keys into a v2 container.
36. **Transition trigger is content diff.** V1 replays `between_slides` on any
    `action:"display"` payload, so a theme-only re-broadcast can replay the
    animation. V2 compares the rendered source per block: unchanged blocks do
    not re-animate. This is a deliberate animation-behavior difference (theme
    restyles become silent); it does not change layout or still-frame
    rendering. Phase 4's equivalence test compares post-animation frames.
37. **`out` comes from the applied theme.** A theme-less clear payload cannot
    supply an exit definition, so the renderer reads `out` from the last theme
    applied to the element — the same source v1 uses (`_prevPayload`).

---

## 11. Implementation plan (Phases 2–4)

### Phase 2 — Python schema, migration, loader, display state

New files:

- `core/theme_schema.py` — enums, ranges, defaults, field validators,
  `sanitize_css_value`, `normalize_theme`, `ThemeReport`, `SAFE_THEME`, the
  built-in animation registry, and animation definition/assignment validation.
- `core/theme_migrate.py` — `migrate_v1_to_v2` with the tables in §7,
  including padding→`body` and v1 animations→container assignments.
- `core/theme_shared.py` — load/validate `themes/_shared/*.json`, resolve
  `{shared:...}`, `@color`, and animation names, mtime refresh, cycle
  detection.

Changed:

- `core/theme_loader.py` — skip `_`-prefixed path segments; cache raw and
  resolved; `resolve_theme()` returns resolved v2; `theme_container()` is
  array-aware; `slide_title_visible()` reads v2 first;
  `display_format_defaults()` works on both shapes; `save_theme()` unchanged
  (raw). Keep `get_theme()` raw for the designer.
- `ui/widgets/theme_properties_panel.py` — array/dict adapter; merge managed
  blocks instead of replacing; `visible:false` for v2 toggles; never write
  legacy flex keys or container `padding*` into a v2 container; retarget any
  padding widget to `body.padding*` or leave it read-only.
- `ui/tabs/theme_designer_tab.py` — resolve before previews; leave the legacy
  top-level container branch alone.
- `ui/widgets/theme_preview.py` — resolve before display (covers quick editor
  and lite designer).
- `ui/widgets/lite_designer/lite_designer.py` — preview resolve if it calls
  `DisplayView` directly (it uses `ThemePreview`, so mostly covered).
- `ui/panels/slide_grid_panel.py` — verify `theme_container()` compatibility.
- `core/websocket_server.py` — optional defense-in-depth normalization of
  `theme_data`; otherwise no change.

New tests (each run separately, `timeout 120`):

- `tests/test_theme_v2_schema.py` — defaults, enums, clamps, unknown keys,
  schema version, safe theme (including the exact fullscreen values).
- `tests/test_theme_v2_security.py` — injection strings in every CSS field,
  HTML in ids/labels, `url()`, `;`, `}`, `var()`, control chars, animation
  names and keyframe values.
- `tests/test_theme_v2_migration.py` — every shipped theme migrates,
  validates, and is deterministic; no files written; padding lands in `body`;
  translation typography matches the reference.
- `tests/test_theme_v2_shared.py` — borders/shadows/palettes/animations,
  missing names, cycles, malformed files, local→shared→built-in precedence.
- `tests/test_theme_v2_animations.py` — definition schema, keyframe ordering,
  per-property interpolation, `"base"`, unknown-name fallback, typewriter
  constraints and outline fallback, v1 phase mapping.
- `tests/test_theme_v2_positions.py` — every anchor, centered-unless-given,
  `left`+`y` ≡ `top_left`, percentage math against 1920×1080 (not viewport).
- `tests/test_theme_v2_designer_roundtrip.py` — load/edit/save preserves v2
  fields, unknown keys, other containers, array order, animations, and content
  padding; no container `padding*` is ever written.

Gate: new tests pass; existing theme/display tests pass individually:
`test_slides_theme.py`, `test_theme_switch.py`, `test_display_js.py`,
`test_display_render_matrix.py`, `test_display_deck_formats.py`,
`test_slide_edit.py`, `test_slide_strips.py`,
`test_lite_designer_theme_awareness.py`, `test_phase7_display.py` (alone),
`test_output_sets.py` (alone). Do not run `test_phase9_ui.py`.

Server-side risk: `resolve_theme()` is on every payload build. Cache normalized
results by `(name, mtime, id(raw))`; measure a full broadcast in the report.

### Phase 3 — Renderer

Changed:

- `display/display.js` — render a resolved v2 theme: stage + containers,
  layers, anchors/keywords, form/decoration, content padding, block stack,
  block visibility, reference/translation positions, verse_num modes, shared
  text params, `text_outline`, per-container autosize, `canvas.fit`. Keep a
  small `coerceTheme()` that accepts v1 for defensive compatibility and for
  callers that bypass Python (tests, hand-injected JS), delegating to the same
  v2 renderer.
- `display/display.js` animation engine — WAAPI playback of resolved
  definitions, per-element `entry`/`transition`/`out`, content-change
  comparison, coalescing, `prefers-reduced-motion`, and the typewriter
  splitter/unwrapper with the `.rc-oc` outline fallback. No `@keyframes`
  injection and no raw CSS values.
- `display/display.html` — stage root and dynamic container/block DOM; retain
  legacy nodes only for the coercion path.
- `display/themes.css` — engine structural rules, v2 defaults, removed
  hardcoded per-theme styling; outline machinery unchanged.
- `ui/widgets/display_view.py` — mirror every change exactly; remove the
  duplicate `resizeCanvas` once the renderer owns `canvas.fit`.
- Existing tests `test_display_js.py`, `test_display_render_matrix.py`,
  `test_display_deck_formats.py` — update payloads to v2 and add cases for
  translation in each position, reference above/below, layers, each position
  keyword, each anchor corner, visible toggles, two containers, content
  padding, percentage math, animations (including typewriter and the outline
  fallback), and bad values falling back.

Before changing the renderer, capture a golden fixture from the current
renderer (Phase 2): computed styles and bounding boxes for each shipped theme
at 1920×1080, for a short and a long verse, with animations disabled or after
they settle. Phase 4 uses it to prove "same as before".

Gate: new and existing display tests pass. Screenshots in Phase 4.

### Phase 4 — Shipped themes and docs

- Convert `themes/freeform/slides.json` and the five scripture themes to v2,
  preserving their look. Add `themes/_shared/borders.json`,
  `shadows.json`, `palettes.json` (the gold/lime/white palette is already
  duplicated across three themes), and `animations.json` (the built-in names
  plus at least one reusable custom definition and `lyric_typewriter`).
- Add explicit animation assignments to the shipped themes where they had v1
  `animations`; shipped themes without animations stay static. Verify that a
  migrated v1 dict with `display_enter`/`between_slides`/`display_exit` and
  the converted v2 file produce the same phase selection and timings.
- Equivalence test: resolved v1-migrated dict deep-equals the resolved v2 file
  for every theme; render test compares key computed styles/positions against
  the Phase 2 golden, with animations disabled.
- Update `docs/theme-switch-contract.md` (`theme_data` v2 shape),
  `docs/theme_designer_spec.md` (array containers, round-trip guarantees,
  cannot-edit list), `docs/theme_designer.md` (schema references, remove the
  dead top-level `container` claims or mark them legacy),
  `docs/display_and_broadcast.md` (renderer/stage/scale), and
  `docs/outline-rendering.md` (`text_outline` now explicit).
- Capture screenshots of the two-container scripture example in the operator
  preview to `docs/screenshots/theme_v2/` (headless Chrome render of the same
  `display.html`; if QtWebEngine can run offscreen, use `DisplayView.grab()`
  and label it as the operator preview).

Gate: all relevant tests pass; `git status` shows no changes outside
`core/`, `display/`, `themes/`, `docs/`, `tests/`, and the narrow designer
compatibility fixes reported.

---

## 12. Example themes

See `docs/theme_schema_examples/`:

- `fullscreen_single.json` — the v2 reference for `SAFE_THEME`: one
  60,40/1800×1000 transparent container, 80px text fitted 60–96, gold 48px
  reference below, lime translation to its right. No container padding.
- `two_container_scripture.json` — verse in one container (layer 10),
  reference + translation in a decorated second container (layer 20), with
  `body.padding`, shared border/shadow/palette refs, and independent entry
  animations (the citation is delayed).
- `song_slides.json` — freeform single container, uppercase outlined lyrics,
  title hidden, block-level animation.
- `shared/borders.json`, `shared/shadows.json`, `shared/palettes.json`,
  `shared/animations.json` — the shared files those examples reference,
  including a reusable `verse_rise` and a `lyric_typewriter` definition.

These live outside `themes/` so the loader never lists them. Copy them into
`themes/scripture/` or `themes/freeform/` to try them; copy `shared/*` to
`themes/_shared/` first (the examples assume that namespace).
