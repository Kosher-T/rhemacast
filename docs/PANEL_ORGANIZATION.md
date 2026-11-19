# Panel Organization — parameter tiers

How a Theme Designer panel is arranged so it reads as a short list of
parameters instead of a wall of fields: what counts as a parameter, what
belongs tucked under one, where its control sits, and how to refine the next
panel without changing a single stored value.

The Container panel is the worked example. It was reorganized first; every
other panel follows the same procedure (§4) before it is touched.

---

## 1. The test: parameter or subparameter

Ask one question of every control:

> Does this control mean anything without another control, or does it only
> refine that control?

If **yes**, it is a **subparameter**. If **no**, it is a **parameter**.

The test is about meaning, not about how the value is stored or how often it is
used. A control that is technically independent but meaningless on its own is a
subparameter; a control that looks small but stands alone is a parameter.

### The second test: does the control still change the render?

> If a control changes what the display paints, it is never disabled.

Disabling is reserved for a control whose only effect is already decided by
something else. A control that still affects the output stays live even when
the *other* thing it looks related to is off — "Border: none" removes an
outline stroke, not the border layer. Fill, Pad, Radius and Border shadow all
paint on that layer, so all four stay editable at every Border value. See §3,
decision 6.

### Container examples

| Control | Verdict | Why |
|---|---|---|
| `width` | Parameter | A size in its own right. |
| `min_width` | Subparameter of Width | Nothing to minimize until a width exists. |
| `max_width` | Subparameter of Width | Same. |
| `height`, `min_height`, `max_height` | Parameter + two subparameters | Same reasoning as Width. |
| `border` | Parameter | The border itself (style, width, colour, sides). |
| `background` ("Border fill") | Subparameter of Border | It is the paint inside the border shape. |
| `border_padding` ("Border pad") | Subparameter of Border | The gap between the edge and the border. |
| `border_radius` | Subparameter of Border | It shapes the border layer and nothing else; the container stays a rectangle — see decision 1. |
| `border_shadow` | Subparameter of Border | The shadow of the border layer's shape; meaningless without that shape. |
| `visible`, `layer`, `opacity` | Parameters | Each stands on its own. |
| `overflow`, `box_shadow`, `backdrop_filter` | Parameters | Independent effects. `box_shadow` shadows the container rectangle. |
| `position.mode` | Parameter | Which placement model the container uses; it stands alone. |
| `position.canvas` / `position.edge` | Parameters under Position | Two answers to the same question (where does the pin go), so they are two rows of one heading rather than two headings. Only the active mode's rows are shown; both payloads stay stored. |
| `container id` | **Parameter** (Identity) | The container's one name; edited through the selector's Rename. |
| `label` | Not a control | It only repeated the id; the field is kept in the document, the row is gone (§3). |

The trap is grouping by *topic* instead of by *dependency*. "Border padding"
lives near the border, but that is not why it is nested: it is nested because
it has no meaning without a border to pad.

---

## 2. The three tiers

| Tier | Widget | What it is | UI pattern |
|---|---|---|---|
| 1 | `PropertySection` | Group heading | A row with a chevron and a caption-cased title. Collapsible; open state remembered per panel. It is a label organizer, never a value. |
| 2 | `PropertyRow` | Parameter | Label + control, always visible once its heading is open. If the parameter has subparameters, it carries a disclosure chevron in the leading gutter. If it has none, it carries an empty gutter and no chevron. |
| 3 | `ParamGroup` body | Subparameters | Rows of the same height, in the same label/control grid, indented one step and hung from a hairline guide under the chevron. Revealed and hidden by the parameter's chevron. |

Implementation:

- `ui/theme_kit/property_row.py` — `PropertySection` (Tier 1), `PropertyRow`
  with `set_disclosure(enabled, expanded=..., reserve=...)` (Tier 2).
- `ui/theme_kit/param_group.py` — `ParamGroup` (Tier 2 row + Tier 3 body),
  `SUB_INDENT`, `GUIDE_X`.
- `ui/theme_kit/panel_state.py` — per-panel open state in the settings table
  under `ui.designer.panel.<panel>` as JSON `{"group": expanded}`. Missing
  entries fall back to the spec default, so a new group needs no migration.

> **Removed in round 2:** the `DISCLOSURE_GUTTER`/`SUB_INDENT`/`GUIDE_X` values
> quoted in the round-1 version of this document (16/28/14 px) no longer
> describe the layout. The grid is now the three constants below.

### The grid

Three numbers, defined once in `ui/theme_kit/panel_layout.py`:

| Constant | Value | Meaning |
|---|---|---|
| `PANEL_PAD` | 8 px | Left and right margin of the panel, outside every heading. |
| `TIER_STEP` | 12 px | How far each tier steps in from the one above it. |
| `GUTTER` | 12 px | The arrow slot at the left of every row; reserved even when the row has no arrow. |

A row's edge and its label's x follow from the tier alone:

```
edge(N)    = PANEL_PAD + (N - 1) * TIER_STEP
label_x(N) = edge(N) + GUTTER
```

With the defaults that is **Tier 1 label 20, Tier 2 label 32, Tier 3 label 44**
in panel coordinates (the scroll host starts at `PANEL_PAD`, so the same rows
measure 12 / 24 / 36 inside the host).

Every child label sits strictly right of its parent's label, and a Tier-3 row
reserves the gutter even though it has no arrow, so its label never collapses
back to the Tier-2 position.

How the builder produces it:

- The panel's root layout uses `PANEL_PAD` on both sides.
- A tiered `_SectionHeader` draws its chevron at x=0 and its text at `GUTTER`,
  so the heading text itself lands on `label_x(1)`.
- A tiered `PropertySection` body indents `TIER_STEP`.
- `PropertyRow` reserves `GUTTER` for the arrow and keeps its label after it.
- `param_group.SUB_INDENT == TIER_STEP`, `param_group.GUIDE_X == GUTTER // 2`.

**If the panel feels too narrow, change `TIER_STEP` and `GUTTER` here and
nothing else.** The row chrome, section body, parameter body and stacked-control
indent all read these three values; nothing else may hardcode a tier offset.

Width budget at the minimum panel width (240 px): 8 px inset on each side and a
permanently reserved 8 px scroll lane leave 216 px of content. The block page's
four-side rows need 214 px, so the properties panel reserves and styles its own
lane (`reserve_scrollbar_lane` + the token scrollbar QSS) instead of letting the
platform's 14 px bar appear the moment content overflows. Re-run
`tests/test_theme_designer_columns.py` after touching any of this.

### Controls: inline or stacked

Two placements, decided by the control, not by the page:

| Placement | Which controls | Where the control sits |
|---|---|---|
| **Inline** | Number fields and small toggles (switches, chips) | The shared value column: the same x on every row of the same tier. |
| **Stacked** | Dropdowns (`enum`), colour and paint boxes, text inputs, and the compound Border, Shadow and Backdrop editors — plus the Identity selector | Starts at **its label's left edge** and runs to the right margin. |

Why: at 240 px a dropdown or a colour box in the value column is narrower than
its own content, while the label above it already names the field. Stacking
gives the control the full row and keeps the reading order label → control.

The page builder decides placement in one place (`_stacked()` in
`property_editor.py`), from the control kind plus an explicit `"full": True` in
the spec. A panel does not get to choose per row by hand.

Measured rule (pinned by tests):

- Every stacked control's left edge equals its label's left edge.
- Every inline control shares one x per tier, and the Tier-3 inline column is
  exactly `TIER_STEP` right of the Tier-2 column.

### Size semantics: preferred, min, max

`width` / `height` are the **preferred** size; `min_*` / `max_*` bound them.

- **On edit, the bound moves — not the field.** Raising Min above Max raises
  Max; lowering Max below Min lowers Min. Never silently clamp the control the
  operator is dragging; the other bound follows.
- **Width/Height are kept between Min and Max on their own edit only.** Typing
  900 px into Width with a 400 px Max writes 400 px, visibly.
- **Only same units are compared.** px with px; a `%`, `auto` or unset bound is
  skipped, so a percent Max never bounds a pixel Width.
- **Loading never rewrites stored values.** If Min/Max push the preferred size
  somewhere else, the authored value stays and the row carries a warning marker
  — `Renders as 400px` (with a tooltip) — so the operator can see the
  difference without the document changing.
- The labels stay **Width** and **Height**; their tooltip reads
  *"Preferred size. Kept between Min and Max."*
- There is no dynamic-bound provider on these rows any more: a provider clamps
  the field being edited, which cannot express "raising Min raises Max".

---

## 3. Worked example: the Container panel

### Finished layout

```
Identity      Container (selector) + Rename   [parameter: identity control]
              · Kind note                      [note; describes Kind, not Label]
Visibility    Visible                          [parameter, inline]
              Layer                            [parameter, inline]
              Opacity                          [parameter, inline]
Size          Width                            [parameter, chevron, inline]
              └ Min                            [subparameter, default collapsed]
              └ Max                            [subparameter]
              Height                           [parameter, chevron, inline]
              └ Min                            [subparameter, default collapsed]
              └ Max                            [subparameter]
              Overflow                         [parameter, stacked]
Position      Mode                             [parameter, stacked: Canvas / Edge]
              Align                            [parameter, inline: 3×3 pin grid]
              Point                            [parameter, stacked: the nine points]
              Edge                             [parameter, stacked, edge mode only]
              X / Y                            [parameters, inline; X or Y is the
                                                edge distance in edge mode]
Fill          Container bg                     [parameter, stacked paint]
Border        Border (style)                   [parameter, chevron, stacked,
                                                default expanded]
              └ Fill                           [subparameter: border fill, stacked]
              └ Pad                            [subparameter, inline]
              └ Radius                         [subparameter, inline]
              └ Border shadow                  [subparameter, stacked]
Effects       Shadow                           [parameter, stacked; the container
                                                shadow — hidden while Container bg
                                                is None]
              Backdrop                         [parameter, stacked, blur px]
```

There is no Shape heading any more (round 3). Radius shapes the border layer,
which Border owns, so it lives there, after Pad, and keeps its stored key
(`border_radius`), its default, its px unit and its drag scrub.

The Border popup does not offer a radius of its own. It used to carry a base
and a per-side "Radius" that wrote `border.radius`, while the container's
`border_radius` wins in the renderer — so the popup control changed nothing on
screen. Both are gone (round 3b); a stored `border.radius` is preserved
untouched and is simply no longer editable there.

**Position (round 4).** The heading holds one pin per container: a point of the
container's own box, placed on the canvas. Nine points, so resizing grows the
box around the pin instead of moving it. Two modes — **Canvas** (pin on an
aligned canvas point or a free x/y) and **Edge** (a distance in from one canvas
edge) — and both payloads stay in the file so switching back restores them. The
canvas edges are the single source of the arithmetic
(`container_geometry.resolve_origin` and `_modelPosition` in both JS
renderers); the panel only seeds and displays it. A container with no payload
keeps the legacy anchor arithmetic and is never rewritten on load; its
rectangle is shown as a top-left pin and the first edit stores the model.

Only the active mode's rows are shown. The 3×3 grid is **dormant** (no
selection) whenever the pin is free: editing X, Y, the point, or dragging on
the canvas clears the alignment, and clicking a cell is what sets it again.
While aligned, X and Y show the derived canvas point and follow a canvas
resize.

### Old → new names

Renaming happened only where nesting made the old name redundant. Nothing else
changed.

| Old label | New label | Where |
|---|---|---|
| Border fill | **Fill** | Border ▸ subparameter |
| Border pad | **Pad** | Border ▸ subparameter |
| Min width | **Min** | Size ▸ Width ▸ subparameter |
| Max width | **Max** | Size ▸ Width ▸ subparameter |
| Min height | **Min** | Size ▸ Height ▸ subparameter |
| Max height | **Max** | Size ▸ Height ▸ subparameter |
| **Label** | **removed** (row only) | Identity; the stored `label` field survives — see decision 4 |
| Radius | **Radius**, moved | From the Shape heading to Border ▸ subparameter, after Pad |
| — | **Position** heading | New in round 4, between Size and Fill (`position.mode` / `canvas` / `edge`) |
| Corner radius (in the Border popup) | **removed** | Duplicate of Radius; it wrote `border.radius`, which the container's `border_radius` overrides — see decision 1 |
| Container bg, Layer, Visible, Opacity, Overflow, Shadow, Backdrop, Border | unchanged | — |
| — | **Border shadow** | New Border ▸ subparameter (`border_shadow`) |

### Behaviour that did not change

- Every existing value, schema default, "Inherit" state and drag-scrub
  behaviour is identical; the document round-trips byte-identically through
  load → snapshot.
- Width and Height were added as *editable parameters* on this page. They were
  previously editable only in the workspace geometry panel. Min/Max cannot be
  nested under a parent that the page does not show, so the parent had to be
  present. Both write the same keys the workspace writes.
- Min/Max no longer clamp each other through limit providers; they cross-clamp
  on edit (§2, size semantics).

### The decisions, as resolved

**1. Radius sits under Border, after Pad.** *Resolved (round 3): a Tier-3
subparameter of Border. The Shape heading is gone.*

Round 2 put Radius in its own Shape heading because it looked independent.
It is not: the renderer applies `border_radius` to `.rc-border-layer` only and
sets the container's own radius to `0`, so a radius is a property of the
border shape. It therefore belongs to Border, hangs from it like Pad, and
keeps its stored key, its default and its scrub. Nothing about the stored
document changed — only where the row sits.

**2. Border ▸ Fill and Pad are never disabled.** *Resolved (round 3): the
"Border is none" gate is removed; so is its reason text.*

The border layer always exists. `Border = none` means "no outline stroke" and
nothing else: the fill, the pad, the radius and the border shadow all still
change what the display paints. Round 2 disabled Fill and Pad in that state,
which made two working controls unreachable, and the disable also explained
the dead-drag bug: the mounted `NumberField` was disabled after the first
edit while the row label kept its scrub cursor, and `_begin_label_scrub`
silently returns for a disabled control. See decision 6.

**3. Headings are collapsible and remember their open state.** *Resolved: yes,
per panel.*

State is stored per panel in the settings table, keyed by the heading's
`state_key` and the disclosure group's `state_key` (`"border"`,
`"size.width"`). New groups open to their spec default, so no migration is
needed when a group is added.

**4. The Label row is gone; the selector is the identity surface.**
*Resolved: one name for the id, renamed in place.*

A container had two names — `id` and `label` — and the Label row edited the
second one. Renaming the id was impossible in the Designer, and the label
usually just repeated the id. Now:

- The selector dropdown picks the container; **Rename** beside it starts an
  inline edit of the selected container's id. Enter commits, Esc cancels, and
  the button becomes Cancel while editing.
- Validation is the schema's: trimmed, non-empty, unique among containers, and
  matching `^[a-z][a-z0-9_-]{0,31}$` (`theme_schema.valid_container_id`,
  `CONTAINER_ID_MAX_LENGTH = 32`). A rejected id shows its reason inline and
  keeps the edit open. The Designer validates *before* writing because
  `normalize_theme` silently renames an invalid id to `containerN` at render
  time — a theme that rendered fine could otherwise be saved under a different
  id than the one on screen.
- A rename rewrites `containers[i].id` and every reference to the old id in one
  step. The document stores the id only on the container itself, but the rewrite
  also walks `container` / `container_id` / `containerId` keys anywhere in the
  document (typed targets, nested lists) so an older or hand-edited file cannot
  keep a dangling reference.
- `label` follows the new id **only when it was empty or equal to the old id**;
  a custom label is the operator's and is preserved.
- **One undo.** The Designer has no undo stack. "One undo" is implemented as one
  atomic `ThemeDocument` revision with a single `changed` emission, so a save, a
  preview refresh or a JSON export can never observe a half-renamed document.
- `main` is **not** reserved. Only `SAFE_THEME` and the migration defaults use
  it; the renderer builds `rc-cont-<id>` DOM ids and `theme_compat` falls back
  to the first container id, then `"main"`. Renaming away from, or back to,
  `main` is safe.
- The stored `label` field stays in the document even though it has no row: the
  canvas badge and its accessible name read it (`ContainerBox.title()`), and
  dropping it would rewrite files. The Kind note stays too — it describes Kind,
  not Label.

**5. Adding a container starts with a name.** *Resolved: ask first, then slug.*

**6. Never disable a control that still changes the render.** *Resolved
(round 3): the one gating rule for every panel.*

A control is disabled only when its effect is already decided by another
control (nothing it can write would change the output). "Looks related to X,
and X is off" is not enough. Round 3's bug was exactly that mistake: Border
was `none`, so Fill and Pad were disabled, but the renderer still painted the
border fill and still inset the layer by the pad. A rule of thumb: read the
renderer before adding `set_disabled_reason`. If the renderer reads the value
unconditionally, the row must stay live.

The mirror rule for the UI's *visibility*: a control whose value only matters
in one state may be hidden in the other, but the value is kept. The two
shadows follow this: `box_shadow` is shown only while `container_background`
paints, `border_shadow` only while it does not (decision 7).

**7. Exactly one shadow paints, and the UI shows that one.** *Resolved
(round 3).*

- `container_background` has a paint → the container is a rectangle, so the
  **Container shadow** (`box_shadow`, Effects) paints and the Border shadow
  row is hidden.
- `container_background` is None → the shape is the border layer, so the
  **Border shadow** (`border_shadow`, Border ▸ subparameter) paints and the
  Container shadow row is hidden.
- Hiding a row never clears its value, and the renderer only ever paints the
  shadow whose row is visible.
- The border shadow is drawn by a host element that is a *sibling* of the
  container on `#stage`, at the border layer's rect (inset by Pad, shaped by
  Radius). A child would be clipped by the container's `overflow: hidden` and
  by its bounds; the whole point is that the shadow reaches the canvas.
- "Container bg is None" means the paint field's **None** option. The editor
  and the renderer share one rule: absent, `none`, `transparent`, and a colour
  with alpha 0 all count as no paint.

**8. Position is a pin, and the panel edits exactly one pin.** *Resolved
(round 4): nine pin points, two modes, one resolver.*

A container had an anchor plus offsets whose meaning changed per keyword: with
`center` the offsets were measured from the box's centre, with `top_right` from
its right edge, and `fill` overrode the size entirely. There was no way to say
"keep this corner where it is" that survived a resize, which is what the 1920×
1080 clipping bug was really about — position and size disagreeing.

The model is a pin: pick one of nine points of the box, then say where on the
canvas that point goes. Resizing grows the box around the pin, so a centred
container stays centred and a flush one stays flush, by construction.

- **Storage is additive.** `position.mode` / `canvas` / `edge` join the legacy
  `anchor`/`x`/`y`, which are never removed, so no format bump is needed and an
  older renderer still reads the file. Both mode payloads stay in the file;
  only `mode` decides what renders.
- **Legacy files are not rewritten.** With no payload the old anchor
  arithmetic still runs (a legacy centred panel keeps tracking a resize). The
  panel shows that rectangle as a top-left pin and stores the model on the
  first position edit.
- **One resolver.** `container_geometry.resolve_origin` for the Designer and
  the canvas, `_modelPosition` in `display/display.js` and in the mirror in
  `ui/widgets/display_view.py` for the renderers; one case table in
  `tests/test_theme_designer_position.py` runs through all three.
- **No clamping anywhere.** Negative and off-canvas pins are valid positions;
  the operator can hang a panel half off the canvas on purpose.
- **One edit, one change.** Every edit, including the mode switch, writes the
  whole `position` object at one path (the same "one undo" rule as decision 4).
- **Nothing is disabled.** X, Y and the pin point stay live while the grid is
  aligned; they simply detach the alignment (decision 6).
- **The workspace follows.** A container with the model shows the pin in its
  X/Y fields and is moved by the canvas drag through the same writer; selecting
  Fill in the workspace anchor drops the model so the legacy stretch applies.

The strip's **+** opens a validated one-field dialog. The typed name becomes the
label; `container_id_from_name` derives the id (lowercase; runs of unsupported
characters become one `-`; leading/trailing `-`/`_` stripped; a `c-` prefix when
it does not start with a letter; truncated to 32). A name that slugs to nothing
or collides with an existing id is refused with the reason inline and the dialog
stays open. Programmatic `add_container()` keeps the old generated
`containerN` behaviour.

---

## 4. Refining another panel

Do these in order. Do not skip step 1; every later mistake is a control that
was classified before it was understood.

1. **Inventory every control.** List every row the panel builds, with its
   path, label, control kind, default, and whether it is nullable/inheritable.
   Sources: the panel's spec list (for example `CONTAINER_SPECS` / the layout
   tree in `ui/widgets/theme_designer/property_editor.py`), the schema in
   `core/theme_schema.py`, and the matching rows in §9 of
   `docs/theme_designer_spec.md`.
2. **Classify each control with the test in §1.** Write the verdict down next
   to the control. "It belongs with X" is not a classification; "it has no
   meaning without X" is.
3. **Group the parameters into Tier-1 headings.** A heading is a promise about
   what kind of question the controls answer (identity, visibility, size,
   fill, border, shape, effects). Do not create a heading for a single
   parameter unless that parameter genuinely starts a new topic.
4. **Nest the subparameters under their parameter.** Every subparameter must sit
   under exactly one parameter. If a control refines two things, it is a
   parameter of its own.
5. **Place each control: inline or stacked.**
   - Number fields and small toggles are inline: they join the tier's shared
     value column.
   - Dropdowns, colour/paint boxes, text inputs and compound editors are
     stacked: `"full": True` in the spec, or their kind is in `_STACKED_KINDS`.
   - Never nudge a single row by hand; the placement rule is shared.
6. **Apply the behaviour rules.**
   - Values, defaults, Inherit states and scrub/commit behaviour stay exactly
     as they are. This is a layout change.
   - If two controls bound each other, decide which one moves on an edit and
     write that down (see §2, size semantics). Never let a load rewrite stored
     values; show a marker instead.
   - Rename only to drop redundancy once nested ("Border fill" → "Fill").
     Record every rename in an old → new table in this document.
   - Subparameters are indented one step and keep the same row height.
   - A parameter with subparameters gets a chevron and a declared default open
     state; a parameter without them gets the reserved gutter and no chevron.
   - If a field's editor becomes a row of its own (like `id`/`label`), keep the
     stored field so files round-trip; remove only the control.
7. **Build it from the spec tree, not by hand.** Declare the layout as nested
   data (`<PANEL>_LAYOUT`), flatten it for path/validation consumers
   (`_flatten_layout`), and let the builder place rows into
   `PropertySection` / `ParamGroup`. Keep the flat list as the source for
   `field_paths()` so reachability tests keep working.
8. **Gate dependent controls honestly — and rarely.** A control that still
   changes the render is never disabled, whatever its neighbours are set to
   (§3, decision 6). A subparameter whose effect is genuinely decided by
   another control may be disabled with a reason the operator can read, but
   only after checking the renderer: if the renderer reads the value
   unconditionally, the row stays live. If the two disagree, fix the gate —
   never just document the conflict.
9. **Validate before you write.** Anything that becomes an id, a filename or a
   DOM id is checked against the schema pattern in the Designer, with the
   reason shown inline — never left to `normalize_theme`'s silent repair.
10. **Update the docs in the same change.** Add the panel's finished layout and
    old → new map to §3 of this document, update the rows in
    `docs/theme_designer_spec.md`, and — if any theme property, default, range
    or renderer behaviour changed — update `docs/theme_file_reference.md`.
11. **Add tests, then run the neighbours.** A refined panel needs tests for
    section order, nesting, disclosure defaults, open-state persistence, the
    disabled states, field-path reachability, stacked/inline alignment, any
    cross-clamp, and any id validation. Then run the existing designer suites
    (§5).

---

## 5. Verification checklist

A refined panel is done when every line is true.

- [ ] **No value or default changed.** Loading a theme and snapshotting it
      without edits is byte-identical to the input; absent keys still show
      their schema meaning (opacity 1, empty nullable length, Inherit).
- [ ] **Nothing is orphaned.** Every row is inside a Tier-1 heading (directly
      or through one `ParamGroup`), and every subparameter is inside a group.
- [ ] **Every control is reachable.** `field_paths()` still lists every path the
      page had before the change, and every listed path has a mounted control.
      A removed row (like Label) leaves its stored field untouched.
- [ ] **One grid.** `edge()`/`label_x()` increase strictly with the tier; the
      measured heading text, Tier-2 label and Tier-3 label sit on
      `label_x(1..3)`; no module hardcodes a tier offset.
- [ ] **Stacked controls start at their label's left edge**, and inline
      controls share one column per tier, with the Tier-3 column exactly
      `TIER_STEP` further right.
- [ ] **Chevrons only where they belong.** A row with subparameters has a
      chevron; a row without them has none but reserves the gutter, so labels
      stay on one grid.
- [ ] **Subparameters are indented one step** and keep the row height; their
      controls remain usable at the panel's minimum width.
- [ ] **Bounded sizes behave.** Raising Min raises Max; lowering Max lowers Min;
      Width/Height clamp only on their own edit; mixed units and `auto`/unset
      are never compared; loading shows `Renders as …` without rewriting the
      stored value.
- [ ] **Ids are validated before writing.** Rejected and duplicate names show a
      reason inline and leave the document unchanged; a rename rewrites every
      reference in one revision; `main` is treated like any other id.
- [ ] **Open state persists.** Collapse a heading or a disclosure group, switch
      pages or reopen the Designer, and it comes back the same way. A group
      with no saved state opens to its declared default.
- [ ] **Nothing that renders is disabled.** Every row's control still changes
      the output in the row's current state, and nothing is disabled merely
      because a neighbouring property is off (§3, decisions 2 and 6).
- [ ] **Any disabled state is accurate and explained.** A control that truly
      cannot apply is disabled with a reason the operator can read, and that
      reason matches what the renderer actually does.
- [ ] **Hidden rows keep their value.** A row hidden by a state rule (the two
      shadows, the inactive position mode) round-trips its stored value
      untouched, and the renderer paints only what the visible row describes.
- [ ] **Position is one pin.** The panel shows only the active mode's rows, the
      grid goes dormant the moment the pin is free, X/Y keep showing the
      derived point while aligned, a mode switch does not jump on its tied
      axis, and every position edit is one document revision. A legacy
      container renders through the old arithmetic until it is edited.
- [ ] **Renames are documented.** The old → new table matches the finished
      labels, and no control was renamed beyond dropping redundancy.
- [ ] **Suites are green:**       `tests/test_theme_designer_panel_tiers.py`,
      `test_theme_designer_panel_layout.py`,
      `test_theme_designer_position.py`,
      `test_theme_designer_number_fields.py`,
      `test_theme_designer_columns.py`,
      `test_theme_designer_discrepancy_fixes.py`,
      `test_theme_designer_stage2.py`, `test_theme_designer_stage4.py`,
      `test_theme_designer_m1.py`, and the preview suites.
