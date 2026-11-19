# Theme Designer — Specification

> living document — update as design decisions are made

---

## 1. Two Modes

### Light (Quick Edit)
- **Trigger**: Right-click a theme card in the ThemesPanel
- **UI**: Floating popup panel, 1280×720 (720p), centered over the Presentation tab
- **Backdrop**: Semi-transparent overlay with blur, dimming the presentation behind it
- **Content**: Left column (properties) + Right column (single live preview)
- **Preview verse**: Psalm 100:4 KJV
- **"Edit in Full Designer" button** in the title bar — switches to the Full tab with the same theme loaded
- **Save/Reset** buttons persist to `themes/{name}.json`, hot-reload picks it up

### Full (Dedicated Tab)
- **Trigger**: "THEME DESIGNER" tab in the main tab bar
- **UI**: Three-column layout (Properties | Three Previews | Animations + JSON)
- **Preview layout**: Triangle formation — one on top, two below
  - **Top**: Matthew 3:11 (medium verse, centered)
  - **Bottom left**: John 11:35 (shortest verse)
  - **Bottom right**: Esther 8:9 (longest verse)
- **Viewport definition**: Identical to Live/Preview screens:
  - QFrame: `background: black`, `border: 1px solid rgba(255,255,255,0.08)`, `border-radius: 8px`
  - AspectRatioWidget: `aspect_ratio=16/9`, `min_width=320`, `max_width=840`
  - Contains DisplayView (QWebEngineView) rendering the same HTML/CSS/JS as OBS
- All three previews are KJV, hot-reload simultaneously
- **Everything in Light** plus:
  - Display start / between-slide / end animations
  - Direct JSON editor with syntax highlighting
  - Import/Export JSON

### Theme picker and external edits
- **Option text is the theme's `label`**; the option value is the ID (filename stem) and never changes when a label is edited. Missing label falls back to the prettified stem (`default_typewriter` → `Default Typewriter`).
- Duplicate labels are allowed; collisions append the ID in muted text (`Standard (default_2)`).
- Sort is case-insensitive A→Z by label, except entries with `sort_order`, which lead in ascending order (§9.1).
- `description`, when present, is a muted, single-line truncated second row (never wraps).
- The toolbar name field edits `label` inline. Each keystroke updates the picker from one in-memory store keyed by ID; selection is preserved by ID across re-sorts. An empty field shows the fallback in the picker but stays empty in the field and is not written to disk.
- The themes folder is watched (250 ms debounce). Files added, removed or edited outside the app refresh the picker without a restart. The app's own saves are ignored by content hash.
  - Open theme with unsaved edits: the in-editor edits win until the operator chooses **Reload** or **Keep editing** in the notice bar.
  - Invalid JSON: the last good version stays loaded, with a warning dot and tooltip on that option.
  - Deleting the selected theme: falls back to `default` and the notice says unsaved edits were discarded.

---

## 2. Container System

Every visual element lives inside its own **container** (a `div` in the display HTML). Containers are the unit of layout — they hold position, dimensions, and background independently.

### Schema v2 Array Containers
In Theme Schema v2 (`schema_version: 2`, see `docs/theme_schema_v2.md`), `containers` is an ordered array of container objects:
```json
"containers": [
  {
    "id": "main",
    "layer": 10,
    "visible": true,
    "position": { "anchor": "top_left", "x": 60, "y": 40 },
    "width": 1800,
    "height": 1000,
    "blocks": { ... }
  }
]
```
The Theme Designer currently targets the primary container (`main` or first container in the array) while preserving the full array structure.

### Round-Trip Guarantees
The Theme Designer guarantees lossless editing of v2 themes:
- Unknown, advanced, or unsupported keys (such as `layer`, secondary containers, `canvas.fit`, shared references, and custom animation keyframes) are preserved across load → edit → save cycles.
- When saving, `_merge_v2_designer_save` merges GUI edits into the active container while leaving secondary containers and shared bindings untouched.

### What the Designer Cannot Edit Yet (superseded)
The list that used to live here is out of date: multi-container authoring,
layer reordering, shared-reference selection, custom keyframes and semantic
anchors are all editable now. **§10 is the authoritative per-key coverage
matrix**; do not maintain a second hand-written list here.

### Container Properties
Each container has:
- Position (x, y offsets from canvas anchor)
- Dimensions (width, height — **fixed, never flex**)
- Container background (the full rectangle, square corners) and border fill
  (inside the border shape), border, border padding, border-radius,
  backdrop-filter, box-shadow
- Padding (content inset via `body.padding`)

### Transform Controls
Containers are directly manipulable in the preview viewport:

| Control | Location | Behavior |
|---------|----------|----------|
| Corner handles | 4 corners | Resize (width + height simultaneously) |
| Edge mid-points | 4 edges | Resize single axis (width or height) |
| Center handle | Center of container | Move (drag to reposition) |

All transform controls appear when a container is **selected/focused**.

**Value editing**: Every property editable via numeric inputs in the properties panel. Changes sync bidirectionally with the visual controls.

### Numeric Field Contract

Every numeric control in the Designer — Canvas, Container, Blocks, the right-panel Geometry panel and the animation forms — is the same `ui.theme_kit.NumberField` widget. It never carries its own range: bounds and steps come from `core/theme_schema.py`.

**Ranges.** `schema.FIELD_LIMITS` holds `(minimum, maximum, step)` per unit for canvas-independent parameters (`layer`, `border_radius`, `opacity`, `size`, `weight`, `line_height`, letter/word spacing, block padding and margins, the border/shadow layer editors). Canvas-dependent lengths are computed from the live canvas instead: `schema.size_limits(total)` gives `px: 0…canvas` and `%: 0…100`, `schema.offset_limits(total)` gives `px: −10000…10000` and `%: −100…100`. Changing the canvas dimensions re-applies those bounds to the open fields.

**Interaction rules.**
- Dragging stops exactly at the bound — no wrap, no overshoot.
- Typed or pasted values clamp when committed (Enter or focus loss), never mid-keystroke.
- Arrow keys, wheel and Shift/Alt coarse/fine steps all clamp the same way.
- Hitting a bound tints the field border for a moment; the tooltip always states the active range in the active unit.
- `min_width`/`min_height` and their `max_*` siblings cross-limit each other: the lower field cannot pass the upper one and vice versa. The comparison converts between the two fields' units through the live canvas. Clearing the max (nullable) releases that constraint.
- Switching px ↔ % converts through the canvas so the rendered size is unchanged, then clamps. A `0px` ↔ `0%` switch renders identically and does not mark the theme dirty.

**Units.** A parameter with one authored mode shows its unit as plain, non-interactive text where a dropdown would sit (no chevron, no hover state). A dropdown appears only when there is a real choice — `px`/`%` for lengths, `px`/`em` for typography, or a keyword such as `auto` alongside real units.

**Loading.** A stored value outside the current bounds is displayed as authored: loading never clamps, never rewrites the document and never sets the dirty flag. The first user edit applies the bound.

### Container Capabilities by Element

Not every element needs full container treatment. Some are content-only (position follows parent flow), others are fully transformable.

| Element | Move | Resize | Notes |
|---------|------|--------|-------|
| **Container** (outer wrapper) | Yes | Yes | The main box. Controls overall theme shape. |
| **Scripture Text** | Yes | Yes | Full transform. Text inside respects container bounds. |
| **Reference** | Yes | Yes | Full transform. Independent positioning. |
| **Translation** | Yes | No | Can be moved (e.g., reposition relative to reference), but not resized — it's just a label. |
| **Verse Number** | No | No | Follows parent flow (inside Scripture Text container). Only font/color edits. |

> **Decision**: Nerf verse number container. It's inline with the text, no independent positioning needed.

---

## 3. Element Focus System

When the user clicks an element's row in the properties panel (or clicks the container in the preview):

1. **Focused element** gets a blue left-border accent, full opacity
2. **All other elements** grey out (opacity ~0.35)
3. **Property sections** for unfocused elements collapse/hide
4. **Transform controls** in the preview show only for the focused element's container
5. Clicking another element switches focus
6. Clicking empty space in the preview deselects all (no focus)

This creates a clear "edit mode" per element without visual clutter.

---

## 4. Auto-Resize Text Toggle

Each text element (Scripture Text, Reference) has an **Auto Fit** toggle:

### When ON (default)
- Text font-size is dynamically calculated to fill the container
- Uses the existing `autoFitText()` binary search between `min_size` and `max_size`
- Container dimensions are the constraint; text scales to fit

### When OFF
- Text uses the manually set `font-size`
- **Text that overflows the container is clipped** — disappears behind the container boundary
- Container dimensions **never flex** to accommodate text
- The overflow is hidden, not scrolled — this is a display overlay, not a document

### Implementation
```css
/* Container always clips */
.container {
    overflow: hidden;
    /* width/height are fixed — never auto */
}

/* When auto-fit is OFF, text has explicit size and may overflow */
.container.auto-fit-off .verse-text {
    font-size: var(--rc-text-size);  /* user-set, fixed */
    overflow: hidden;
}
```

---

## 5. Theme JSON Schema (Current)

All 37 CSS custom properties map 1:1 to JSON keys:

```
{
  name, label, description, author,

  container: {
    background, border, border_radius, box_shadow, backdrop_filter,
    padding, max_width, min_width, width, height,
    display, flex_direction, justify_content, align_items
  },

  body: {
    vertical_align, padding_bottom
  },

  text: {
    color, font_family, size, min_size, max_size, weight,
    line_height, text_shadow, letter_spacing, margin_bottom
  },

  reference: {
    color, font_family, size, weight, text_transform, letter_spacing
  },

  translation: {
    color, margin_left
  },

  verse_num: {
    color, font_family
  }
}
```

### New keys for container positions (future)
```json
{
  "containers": {
    "text":      { "x": "50%", "y": "45%", "width": "1200px", "height": "400px" },
    "reference": { "x": "50%", "y": "75%", "width": "800px",  "height": "120px" },
    "translation": { "follows": "reference" }
  }
}
```

### New keys for animations
```json
{
  "animations": {
    "display_enter": { "type": "fade_up", "duration_ms": 600, "easing": "ease-out" },
    "between_slides": { "out_type": "fade_down", "in_type": "fade_up", "duration_ms": 400, "easing": "ease-in-out" },
    "display_exit": { "type": "fade_down", "duration_ms": 400, "easing": "ease-out" }
  }
}
```

---

## 6. Preview Verses (Hardcoded)

These are embedded directly in the designer widgets, not fetched from the Bible database.
All KJV. Viewports match Live/Preview screen definition (16:9, 320–840px width).

| Position | Verse | KJV Text |
|----------|-------|----------|
| Light popup | Psalm 100:4 | "Enter his gates with thanksgiving, and into his courts with praise." |
| Full top | Matthew 3:11 | "I indeed baptize you with water unto repentance..." |
| Full bottom-left | John 11:35 | "Jesus wept." |
| Full bottom-right | Esther 8:9 | (full text — longest verse) |

---

## 7. Data Flow (Staged Save)

```
User edits property in designer
    ↓
ThemePropertiesPanel._collect_theme() builds in-memory dict
    ↓
theme_changed(dict) signal emitted
    ↓
Designer holds _working_theme (deep copy)
    ↓
Preview.apply_theme(_working_theme) — live preview updates
    ↓
User clicks Save
    ↓
core.theme_loader.save_theme(name, _working_theme) → writes themes/{name}.json
    ↓
theme_loader._check_for_changes() detects mtime change
    ↓
Hot-reloads into _cache
    ↓
Next get_theme() call returns updated dict
```

---

## 8. Files

### New files
- `ui/tabs/theme_designer_tab.py` — Full Theme Designer tab (three-column layout)
- `ui/widgets/theme_quick_editor.py` — Light popup panel (1280×720, right-click on theme card)
- `ui/widgets/theme_preview.py` — Reusable preview widget (DisplayView + AspectRatioWidget, 16:9)
- `ui/widgets/theme_properties_panel.py` — Shared property editors (element tree, color/font/weight inputs)
- `ui/widgets/theme_animations_panel.py` — Animation cards (Display Enter, Between Slides, Display Exit)

### Modified files
- `core/theme_loader.py` — Added `save_theme()` and `create_theme()` functions
- `ui/main_window.py` — Replaced `_init_theme_designer` stub with real ThemeDesignerTab, added `_open_theme_quick_editor`
- `ui/panels/themes_panel.py` — Added `contextMenuEvent` to `ThemeCard`, `theme_edit_requested` signal chain
- `ui/panels/queue_panel.py` — Bridged `theme_edit_requested` signal from ThemesPanel
- `display/display.js` — Added animation CSS injection, keyframe definitions, enter/cycle/exit animation support

---

## 9. Property coverage matrix (M1-01)

**As of 11 November 2026.** One row per key in
`docs/theme_file_reference.md`. This matrix is the single source of truth for
what the Designer can do; when a control is added, update its row in the same
change.

Status key:

- **editable** — a dedicated Designer control reads and writes the key today.
  The note says where; “container 0 only” or “split only” means the control is
  partial, not that the key is uneditable everywhere.
- **needs control** — operator-facing, but no dedicated control exists; it is
  reachable only by editing the JSON pane, and should get a control.
- **preserve-only** — must survive load → edit → save, but is not a
  Designer-editable design property (identity, authoring metadata handled
  elsewhere, legacy shapes, or shared-file entries).
- **raw** — intentionally JSON-only; a dedicated control is not planned for
  v1 of the revamp.

### 9.1 Top level

| Key | Status | Where / note |
|---|---|---|
| `schema_version` | preserve-only | Loader/migration owns it; Save writes the raw value. |
| `name` | preserve-only | Theme identity is the filename stem; Save writes the selected theme name. |
| `label` | editable | Toolbar name field (inline, styled as a heading). Typing updates the picker per keystroke and the file on Save. Empty stays empty in the field, shows the prettified ID in pickers, and is not written to disk. Duplicate labels are allowed. |
| `description` | raw | Toolbar shows it; pickers render it as a muted second line. Authoring metadata otherwise. |
| `author` | raw | Authoring metadata. |
| `kind` | preserve-only | Folder is authoritative; changing it is a file move, not a property edit. |
| `canvas` | editable | Canvas page. |
| `containers` | editable | Workspace + Container/Blocks pages; add, duplicate, delete, reorder. |
| `animations` | raw | Library management (add/rename/delete definitions) is JSON-only. Definition fields reached from a container-0 slot are covered in §9.4. |
| `slide` | editable | Only `show_title`; freeform themes expose it on the Canvas page. |
| `sort_order` | preserve-only | Authoring-only ordering hint; read from the raw document, dropped from the resolved theme. Not exposed in the UI. |
| unknown top-level keys | preserve-only | Raw round-trip; the resolved theme drops them with a note. |

### 9.2 `slide`

| Key | Status | Where / note |
|---|---|---|
| `show_title` | editable | Canvas page, Freeform slide section; defaults on when absent and is only written after an operator toggle. |

### 9.3 Canvas

| Key | Status | Where / note |
|---|---|---|
| `width` | editable | Canvas page, number field. |
| `height` | editable | Canvas page, number field. |
| `background` | editable | Canvas page, paint field (colour, gradient, palette token, transparent). |
| `fit` | editable | Canvas page, segmented chips (`contain` / `none`). |

### 9.4 Animation library (`animations`)

| Key | Status | Where / note |
|---|---|---|
| `animations.<name>` (map entry) | raw | Creating, renaming, reordering or deleting a definition is JSON-only. |
| `animations.<name>.type` | raw | Changing an existing definition's type is library surgery; JSON-only. |
| `animations.<name>.label` | raw | Designer-facing label; no field. |
| `animations.<name>.duration_ms` | needs control | The phase-card rows write slot overrides, and `ParamForm` excludes `CARD_OWNED_PARAMS`; a named definition's own duration is JSON-only. |
| `animations.<name>.delay_ms` | needs control | Same as duration. |
| `animations.<name>.easing` | needs control | Same as duration. |
| `animations.<name>.origin` | needs control | Same as duration. |
| `animations.<name>.keyframes` | editable | Timeline, for a local `custom` definition reached from a slot. Preset keyframes are not authorable. |
| `animations.<name>.reveal` | editable | `ParamForm` for a typewriter definition reached from a slot. |
| `animations.<name>.cursor` | editable | `ParamForm` for a typewriter definition reached from a slot; `"none"`/`"default"` and the object form. |
| `animations.<name>.keyframes[].at` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].opacity` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].translate_x` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].translate_y` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].scale` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].rotate` | editable | Timeline frame row. |
| `animations.<name>.keyframes[].blur` | editable | Timeline frame row. |
| `animations.<name>.cursor.char` | editable | `ParamForm` cursor group. |
| `animations.<name>.cursor.color` | editable | `ParamForm` cursor group. |
| `animations.<name>.cursor.blink_ms` | editable | `ParamForm` cursor group. |
| `animations.<name>.cursor.hide_after_ms` | editable | `ParamForm` cursor group. |
| unreferenced `animations.*` | preserve-only | Not present in the resolved theme; raw Save keeps them. |

### 9.5 Animation assignments

| Key | Status | Where / note |
|---|---|---|
| `animation` (container/block) | editable | Full four-phase control on `containers[0]` only. |
| `animation.entry` | editable | Entry card, container 0; also `split.first/rest` entry cards. Other containers, body and blocks need a control. |
| `animation.transition` | editable | Transition cards, container 0. |
| `animation.transition.in` | editable | Transition-in card, container 0; also `split.first/rest`. |
| `animation.transition.out` | editable | Transition-out card, container 0. |
| `animation.out` | editable | Exit card, container 0. |
| `animation` on `containers[1..]` | needs control | `AnimationPanel` hardcodes `containers[0]`. |
| `blocks.body.animation` | needs control | No body animation UI (and `split` is invalid there). |
| `blocks.<text\|reference\|title\|translation>.animation` (non-split phases) | needs control | Only `split` is exposed; entry/out/transition slots for blocks have no UI. |
| `animation` slot: name string | editable | Phase-card selector. |
| `animation` slot: `{"use": name, ...}` | editable | Phase-card selector plus the four override rows. |
| `animation` slot: inline definition | editable | Phase-card inline type picker plus `ParamForm`. |
| slot override `duration_ms` | editable | Phase-card Duration row (writes an override on the slot). |
| slot override `delay_ms` | editable | Phase-card Delay row. |
| slot override `easing` | editable | Phase-card Easing row. |
| slot override `origin` | editable | Phase-card Origin row. |

### 9.6 `split`

| Key | Status | Where / note |
|---|---|---|
| `split` | editable | Split editor on the Blocks page for `text`, `reference`/`title`, `translation`. |
| `split.by` | editable | Split editor, Line/Word chips. |
| `split.stagger_ms` | editable | Split editor, number field. |
| `split.first` | editable | Split editor, first-unit entry and transition-in cards. |
| `split.rest` | editable | Split editor, rest-unit entry and transition-in cards. |
| `split.look` | editable | Split editor, Look sections. |
| `split.look.first` | editable | Split editor, Look · first. |
| `split.look.rest` | editable | Split editor, Look · rest. |
| `look.*.color` | editable | Split editor look row. |
| `look.*.weight` | editable | Split editor look row. |
| `look.*.font_style` | editable | Split editor look row (Italic). |
| `look.*.text_decoration` | editable | Split editor look row. |
| `look.*.opacity` | editable | Split editor look row. |
| `look.*.letter_spacing` | editable | Split editor look row. |

### 9.7 Containers

| Key | Status | Where / note |
|---|---|---|
| `id` | preserve-only | Permanent container key; not shown as a field. Auto-generated for new containers. Renaming is not supported. |
| `label` | editable | Container page. |
| `kind` | preserve-only | Authoring metadata; the renderer does not filter by it, so the control is hidden and the value is kept. |
| `layer` | editable | Container page and workspace. |
| `visible` | editable | Container page and workspace. |
| `position` | editable | Workspace anchor + X/Y fields and canvas drag. |
| `width` | editable | Workspace geometry field and canvas resize. |
| `height` | editable | Workspace geometry field and canvas resize. |
| `min_width` | editable | Container page. |
| `max_width` | editable | Container page, nullable. |
| `min_height` | editable | Container page. |
| `max_height` | editable | Container page, nullable. |
| `container_background` | editable | Container page, paint field. Fills the whole assigned rectangle with square corners, painted under the border fill. |
| `background` | editable | Container page, paint field ("Border fill"). Painted inside the border shape, following `border_radius` and `border_padding`. |
| `border` | editable | Container page, border editor (none / structured / shared reference). |
| `border_padding` | editable | Container page, px length 0–400 (default 0). Gap between the container edge and the border's outer edge; never changes the container's size. |
| `border_radius` | editable | Container page, nullable length; wins over `border.radius`. Rounds the border shape only, never the container rectangle. |
| `box_shadow` | editable | Container page, shadow editor (layers, shared reference). |
| `backdrop_filter` | editable | Container page, free-text field. The function list and ranges are raw CSS grammar; there is no per-function UI. |
| `opacity` | editable | Container page. |
| `overflow` | editable | Container page, chips. |
| `animation` | editable | Container 0 only; see §9.5. |
| `blocks` | editable | Blocks page. |
| legacy `padding` / `display` / `flex_direction` / `justify_content` / `align_items` | preserve-only | Not v2 parameters; the editor never writes them and the validator ignores them. |
| legacy container `x` / `y` | preserve-only | v1 shape; migration moves them into `position`. |

### 9.8 `position`

| Key | Status | Where / note |
|---|---|---|
| `anchor` | editable | Workspace anchor dropdown. |
| `x` | editable | Workspace X field / canvas drag. |
| `y` | editable | Workspace Y field / canvas drag. |
| legacy corner booleans (`top_left`, `top_right`, `bottom_left`, `bottom_right`) | preserve-only | Accepted by the validators for v1 files; migration owns them. |

### 9.9 `border`

| Key | Status | Where / note |
|---|---|---|
| `border` (`"none"` / CSS-like string / object / shared) | editable | Border editor; structured values are normalised on commit. |
| `border.width` | editable | Border editor. |
| `border.style` | editable | Border editor. |
| `border.color` | editable | Border editor (palette aware). |
| `border.radius` | editable | Border editor. |
| `border.sides` | editable | Border editor, per-side overrides. |
| `border.sides.<top\|right\|bottom\|left>.width` | editable | Border editor. |
| `border.sides.<top\|right\|bottom\|left>.style` | editable | Border editor. |
| `border.sides.<top\|right\|bottom\|left>.color` | editable | Border editor. |
| `border.sides.<top\|right\|bottom\|left>.radius` | editable | Border editor. |
| `{"shared": "name"}` border reference | editable | Border editor, Shared mode; the shared entry itself is preserve-only (§9.12). |

### 9.10 `box_shadow`

| Key | Status | Where / note |
|---|---|---|
| `box_shadow` (`"none"` / CSS string / object / shared) | editable | Shadow editor; CSS strings are parsed into layers. |
| `box_shadow.x` | editable | Shadow editor. |
| `box_shadow.y` | editable | Shadow editor. |
| `box_shadow.blur` | editable | Shadow editor. |
| `box_shadow.spread` | editable | Shadow editor. |
| `box_shadow.color` | editable | Shadow editor (palette aware). |
| `box_shadow.inset` | editable | Shadow editor, In toggle. |
| `{"shared": "name"}` shadow reference | editable | Shadow editor, Shared mode; the shared entry itself is preserve-only (§9.12). |

### 9.11 Blocks

| Key | Status | Where / note |
|---|---|---|
| `blocks.body.visible` | preserve-only | Accepted and preserved; the renderer does not read it and the container `visible` switch is the supported control. |
| `blocks.body.valign` | editable | Body tab, chips. |
| `blocks.body.gap` | editable | Body tab. |
| `blocks.body.padding` | editable | Body tab, linked four-side field. |
| `blocks.body.padding_top` | editable | Body tab, four-side field. |
| `blocks.body.padding_right` | editable | Body tab. |
| `blocks.body.padding_bottom` | editable | Body tab. |
| `blocks.body.padding_left` | editable | Body tab. |
| `blocks.body.animation` | needs control | No body animation UI. |
| shared `visible` | editable | Every content block tab. |
| shared `color` | editable | Every content block tab, palette aware. |
| shared `font_family` | editable | Every content block tab, text field. |
| shared `size` | editable | Every content block tab, length field. |
| shared `min_size` | editable | Text/reference/title tabs. |
| shared `max_size` | editable | Text/reference/title tabs. |
| shared `weight` | editable | Every content block tab. |
| shared `line_height` | editable | Every content block tab. |
| shared `letter_spacing` | editable | Every content block tab. |
| shared `word_spacing` | editable | Text/reference/title tabs. |
| shared `text_shadow` | editable | Text/reference/title tabs, shadow editor (literal shadows only; no shared reference, and a hand-authored shared reference paints no shadow on a block). |
| shared `text_outline` | editable | Text/reference/title tabs, free-text field. |
| shared `text_transform` | editable | Every content block tab, chips. |
| shared `text_align` | editable | Every content block tab, chips. |
| shared `font_style` | editable | Every content block tab, chips. |
| shared `text_decoration` | editable | Text/reference/title tabs, dropdown. |
| shared `opacity` | editable | Every content block tab. |
| shared `max_lines` | editable | Text/reference/title tabs, nullable integer. |
| shared `direction` | editable | Text/reference/title tabs, chips. |
| shared `margin_top` | editable | Margins four-side field. |
| shared `margin_right` | editable | Margins four-side field. |
| shared `margin_bottom` | editable | Margins four-side field. |
| shared `margin_left` | editable | Margins four-side field. |
| shared `padding` | editable | Padding four-side field (linked). |
| shared `padding_top` | editable | Padding four-side field. |
| shared `padding_right` | editable | Padding four-side field. |
| shared `padding_bottom` | editable | Padding four-side field. |
| shared `padding_left` | editable | Padding four-side field. |
| shared `animation` (non-split) | needs control | Only `split` is exposed for text-bearing blocks. |
| `blocks.text.autosize` | editable | Text tab. |
| `blocks.text.margin_bottom` | editable | Text tab, Margins group. |
| `blocks.text.text_shadow` | editable | Text tab, shadow editor. |
| `blocks.reference.position` / `blocks.title.position` | editable | Reference/title tab. |
| `blocks.reference.color` / `blocks.title.color` | editable | Reference/title tab. |
| `blocks.reference.font_family` / `blocks.title.font_family` | editable | Reference/title tab. |
| `blocks.reference.size` / `blocks.title.size` | editable | Reference/title tab. |
| `blocks.reference.weight` / `blocks.title.weight` | editable | Reference/title tab. |
| `blocks.reference.letter_spacing` / `blocks.title.letter_spacing` | editable | Reference/title tab. |
| `blocks.reference.text_transform` / `blocks.title.text_transform` | editable | Reference/title tab. |
| `blocks.translation.position` | editable | Translation tab. |
| `blocks.translation.color` | editable | Translation tab. |
| `blocks.translation.margin_left` | editable | Translation tab. |
| `blocks.verse_num.mode` | editable | Verse # tab. |
| `blocks.verse_num.position` | preserve-only | Unsupported by the renderer; the control is hidden with a note and the stored value is kept. |
| `blocks.verse_num.vertical_align` | editable | Verse # tab. |
| `blocks.verse_num.margin_right` | editable | Verse # tab. |
| `blocks.verse_num.size` | editable | Verse # tab. |
| `blocks.verse_num.weight` | editable | Verse # tab. |
| `blocks.verse_num.opacity` | editable | Verse # tab. |
| `blocks.verse_num.line_height` | editable | Verse # tab. |
| `blocks.verse_num.color` | editable | Verse # tab. |
| `blocks.verse_num.font_family` | editable | Verse # tab. |

### 9.12 Shared files (`themes/_shared/`)

| Key | Status | Where / note |
|---|---|---|
| `borders.<name>` | preserve-only | Edited in `borders.json`; the Designer can select the reference but not author the entry. |
| `shadows.<name>` | preserve-only | Edited in `shadows.json`; reference selection only. |
| `palettes.colors.<name>` | preserve-only | Edited in `palettes.json`; `@name` tokens are selectable in colour fields. |
| `animations.<name>` | preserve-only | Edited in `animations.json`; **Copy into theme** makes an editable local copy. |

### 9.13 What remains after M1-01

The `needs control` rows are the complete M1 build list that is not yet a
control: library-level definition timing/label/type; animation phases for
containers `1..n`, `body` and blocks; and `body.animation`.
Everything else is either editable now or explicitly preserve-only/raw.

---

## 10. Open Questions

- [ ] Container drag: snap to grid? pixel-nudge with arrow keys?
- [ ] Undo/redo support?
- [ ] Theme versioning / history?
- [ ] Animation preview: play/pause/scrub in the designer?
- [ ] Should "Edit in Full Designer" pass unsaved changes, or require save first?
