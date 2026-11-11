# Stage 4 findings — container canvas and split

## 1. The v1 geometry panel

`ui/widgets/container_editor.py` is the only v1 geometry editor. It is a
`ContainerEditor` split into:

- `ContainerPreview`, a 1920×1080 canvas that reads `width`/`height` with
  `_parse_px`, so v2 object values (`border`, `shadow`, paint) become blanks;
- `ContainerPropertiesPanel`, which edits the v1 flat container shape and
  rebuilds it from a fixed key list.

It is used in exactly one place: `ui/tabs/theme_designer_tab.py` builds it as
the centre **Editor** page (`self._editor`). `_switch_center_view` calls
`load_container(self._active_container())`, and `_on_container_changed`
replaces `working_theme["containers"][0]` wholesale (or writes the legacy
top-level `"container"`). It always edits the first container, cannot add,
remove, reorder or select, and its `get_container()` drops unknown keys and
v2 blocks. There are no other callers; `windows_update/` and `mobile_version/`
are separate copies of the app and are not in this worktree's import graph.

## 2. What the schema says

`core/theme_schema.py` / `docs/theme_file_reference.md`:

- **Container count** — 1–16; more are truncated with a warning. ID pattern
  `^[a-z][a-z0-9_-]{0,31}$`, duplicates get an `_index` suffix.
- **Position** — `{anchor, x, y}`. `anchor` is one of `ANCHORS` (10 values,
  default `center`); `x`/`y` are px or `%` offsets, −10000…10000. Placement is
  anchor-relative (left/right/top/bottom/center or their pairs), not an absolute
  rect. `fill` spans the design canvas and ignores size and offsets with a
  warning.
- **Size** — `width`/`height` are px, `%`, or `"auto"`; min/max width/height
  are px or `%` with schema caps (7680×4320). `layer` is 0–100 and controls
  paint order; the renderer sorts by `(layer, id)`.
- **Split** — only `blocks.text`, `reference`/`title`, and `translation` may
  carry `animation.split`; containers, `body`, and `verse_num` may not. Shape:
  `by` `line|word` (default `line`), `stagger_ms` 0–2000 (default 70),
  `first`/`rest` phase assignments (nested split rejected), and optional
  `look.first`/`look.rest` styling. The validator drops split everywhere else
  with a note.

## 3. What the canvas widget represents

`ui/theme_kit/container_canvas.py` is controlled, not a document owner:

- `ContainerBox` carries a design-pixel absolute rect (`x`, `y`, `width`,
  `height`), `layer`, `visible`, `fill`;
- `ContainerCanvas.set_boxes(...)` paints 1–16 boxes, sorts by
  `(layer, id)`, picks the topmost overlapping box, drags/resizes with
  canvas-edge clamping (12 px minimum), and emits `changed(id,
  {x,y,width,height})`; `fill` boxes are not draggable;
- `ContainerStrip` is the slim layer list: select, add, duplicate, delete,
  visibility, keyboard up/down, drag reorder. Its `reordered(list)` is
  top/front-first; it only emits, the caller owns layers/order.

The Designer therefore has to (a) convert anchor-relative schema geometry to
absolute boxes and back, (b) resolve `auto`/`%` lengths against the design
canvas for display, (c) apply layer order, and (d) keep the raw document so
unknown keys survive.

## 4. Selection today, and the proposal

Today the left `ThemePropertyEditor` owns `_container_index` through its own
Container dropdown; the tab's `_active_container()` always returns
`containers[0]`. The v1 centre editor has no shared selection. That is two
selection models before a strip is even added.

Proposal — **one selection owned by the Designer tab**:

1. The tab stores `_selected_container_id` (defaults to the first container).
2. `ThemePropertyEditor` gains `set_selected_container(id)` and
   `container_selected(id)`. Its dropdown becomes a view of that id and emits
   the request; it no longer keeps an independent index.
3. The new centre `ContainerWorkspace` owns canvas + strip but not selection;
   it emits `container_selected(id)` and accepts `set_selected(id)`.
4. The tab is the only writer of `_selected_container_id`: both panels emit,
   the tab validates the id, then pushes it back to both panels. `_prefix()`
   and `_active_container()` derive from that id.

## 5. Integration shape

- Replace the centre **Editor** page's `ContainerEditor` with
  `ContainerWorkspace`: canvas (flex) + a 240 px field/strip column inside the
  existing centre page. No new outer panel or tab.
- Add/remove/duplicate/reorder/visibility are document operations in the
  workspace; layer values are reassigned top-first for reorder.
- Exact fields use `ANCHORS` and schema bounds; canvas drag writes anchor-
  relative offsets, preserving unknown `position` keys. `auto` displays as the
  keyword and uses a canvas fallback for the box.
- Append the Stage 1 `SplitEditor` to the existing Blocks page only for the
  schema's text-bearing blocks; write only `animation.split`, merging unknown
  split keys back.
- The tab reloads the property page/selection after canvas edits, and the
  workspace after property edits, without resetting the visible page.
