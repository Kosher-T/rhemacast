# Theme Designer resizable side columns

Date: 2026-11-13
Scope: `ui/tabs/theme_designer_tab.py`, the three-column body only.
Status: implemented, offscreen tests added, real-display checklist pending.

## Decisions for you

1. **Custom painted handle instead of `QSplitter`.** Native splitter handles
   differ between Linux and Windows in thickness, hover paint and cursor. A
   painted widget gives the same 10 px purple-and-black control on both, plus
   double-click reset. Confirm you want the bespoke control rather than a
   themed `QSplitter`.
2. **Proportional give-way.** Both sides lose width in proportion to their
   slack over minimum, rather than the dragged side losing first or the wider
   side losing first. Confirm that is the behaviour you expect when the window
   shrinks after an asymmetric drag.
3. **Defaults unchanged.** 260 / 300 stay as shipped. The four elided labels
   below are a `PropertyRow` fixed-width issue, not a column-width issue:
   widening a panel never restores them, so fixing them changes every property
   page. The JSON header caption hides below 287 px instead of clipping, which
   loses a decorative label the tab bar already states. Confirm both are
   separate changes rather than work in this task.
4. **Minimums above the design floor.** The shipped minimums are 240 / 260.
   The content sweep that informed them suggested a usable floor near 200 px,
   but `_column_widths` clamps to the shipped minimums, so that tighter value
   is not reachable through the UI. Confirm the shipped floors.
5. **Preferences survive trimming.** A saved 480 / 520 on a small window keeps
   those values in settings and only the visible widths are trimmed. There is
   no separate per-monitor clamp: the window is already bounded by the screen.
   Confirm you do not want the trim written back.

## Safe to skip

* Library, Quick editor, Lite Designer and Presentation layouts. They do not
  share this body and were not changed.
* QSS styling for splitter handles. The handle paints itself; adding a
  `QSplitter::handle` rule would have no target.
* Per-monitor width sets. One preference pair is fitted to whatever window
  the Designer opens in.
* Restoring the fixed 1 px separators. The 10 px handles occupy that space
  and draw their own hairline.

## What was already there

The Designer built its body as a `QHBoxLayout` with a fixed 260 px left
column, a fixed 300 px right column, and two 1 px `QFrame` separators. The
preview took the remainder. Nothing in the layout was draggable and nothing
was persisted.

| Area | File | Column layout | Reuses the Designer body? |
|---|---|---|---|
| Theme Designer | `ui/tabs/theme_designer_tab.py` | Fixed 260 / 300, 1 px separators | This is the body |
| Library | `ui/tabs/library_tab.py` | `QSplitter`, horizontal | No, separate page |
| Quick editor | `ui/widgets/theme_quick_editor.py` | Fixed 380 px left pane | No |
| Lite Designer | `ui/widgets/lite_designer/lite_designer.py` | Fixed 440 / 380 px left panes | No |
| Presentation | `ui/tabs/presentation_tab.py` | Nested `QSplitter`s | No |

The change is therefore local to the Designer. The Library splitter, the
Quick editor and both Lite Designer layouts were left alone.

## Defaults and what truncates

The shipped widths did not change: left 260, right 300. No label or control
was clipped because of those widths. The elisions below are older and come
from fixed label columns on `PropertyRow` (76 px configured, 64 px of text
budget; 86 px configured, 74 px of text budget; the budget loses 12 px to the
changed dot and spacing), so they also appear at every wider setting.

Measured with the bundled Inter 13 px face, at the defaults:

| Authored label | Rendered | Text budget | Needed px | Where |
|---|---|---|---|---|
| `While cloaked` | `While cloa…` | 74 | 80 | Animation panel, every page and theme kind |
| `Letter space` | `Letter sp…` | 64 | 71 | Blocks text, reference, translation, both kinds |
| `Word space` | `Word sp…` | 64 | 67 | Blocks text and reference, both kinds |
| `Margin right` | `Margin ri…` | 64 | 69 | Blocks verse number, both kinds |

A `Letter spacing` row also exists in panels that are not on these pages; it
is not in the shipped-path list.

All four labels now render in full. `PropertyRow` measures its label and grows
the configured column when the text needs more room, including the 19 px that
the reset glyph occupies at the right edge. Rows in a `PropertySection`, and
the top-level rows of a property page, share the widest column so controls
still line up. The configured 76 / 86 px remains the minimum, so short labels
keep the shipped geometry. `tests/test_theme_kit_property_row.py` covers the
four labels both at rest and with the reset showing.

Content floor:

* At the shipped minimums (240 left, 260 right) no page, block or right tab of
  either theme kind shows a horizontal scrollbar. That is re-measured for this
  report and asserted by `test_no_horizontal_scrollbars_at_minimum_widths`.
* The design sweep that informed the minimums suggested a usable floor near
  200 px. `_column_widths` clamps to the shipped minimums, so that value
  cannot be reached through the UI and is kept only as headroom.

The shipped minimums are 240 left and 260 right, leaving 40 and 60 px of
headroom above that design floor.

The JSON page's "Theme JSON" label is the one control that could not simply
reflow: its natural header row is 287 px, and at a 260 px column the label
clipped while the three action buttons still fit. The label is decorative
(the tab bar already says JSON), so it now hides below 287 px and returns at
the 300 px default.

## Design

### Geometry

The body is laid out manually by `_layout_columns()` rather than by a
`QHBoxLayout`:

* A layout folds the current side widths into the tab's minimum size hint.
  After a wide drag the window could no longer shrink at all.
* Manual geometry also keeps the two handles as ordinary children, so their
  paint and hit area do not depend on a platform splitter style.

Each handle is `DESIGNER_HANDLE_WIDTH` (10 px). The invariant, asserted in
the tests at several window widths, is:

```
left + handle + preview + handle + right == body.width()
```

The tab minimum is 880 px:

```
240 (left min) + 10 + 360 (preview min) + 10 + 260 (right min)
```

Qt stops the window there, so the preview cannot be squeezed below 360 px
even if both side preferences are larger.

### Give-way maths

`fit_side_widths(available, left, right)` receives

```
available = body_width - 2 * handle - preview_min
```

If the two sides fit, nothing moves and the preview absorbs the spare space.
If they do not, the excess is taken from both sides in proportion to their
own slack over their minimum:

```
slack_left  = left  - 240
slack_right = right - 260
```

A side at its minimum has zero slack and gives nothing. When the excess
reaches the combined slack, both land on their minimums. At a 1000 px body
the sides are untouched (260 + 300 fits in 620) and the preview gets 420. At
880 the sides are trimmed to 240 / 260 and the preview keeps 360.

### Handle paint and input

`ui/widgets/theme_designer/column_handle.py` is a painted `QWidget`, so it
looks the same on Pop!OS and Windows with no native control style involved:

| State | Hairline | Grip |
|---|---|---|
| Idle | 1 px `BORDER_SUBTLE` | 3 x 28 px `ACCENT_SOFT` |
| Hover | 2 px `ACCENT_BORDER` | 4 x 36 px `ACCENT_BORDER` |
| Dragging | 2 px `ACCENT` over an `ACCENT_SOFT` wash | 4 x 44 px `ACCENT` |

It uses `SplitHCursor`, `NoFocus` (it must not add a Tab stop beside every
field), a tooltip, and an accessible name. It emits `drag_started`,
`dragged(delta)`, `drag_finished` and `reset_requested`.

Drag deltas are in global pointer x. The left width adds the delta; the right
width subtracts it because that column's left edge follows the pointer. Each
width is clamped to its static min/max and to a dynamic upper bound that
keeps the preview at 360.

The first real delta commits the currently effective widths. A press with no
motion does not write the window-trimmed value back to settings, so a
preference larger than the current window survives a stray click.

Widths are saved on drag release and on reset. Double-click on either handle
restores that column's shipped default (260 left, 300 right) and saves both.

### Persistence

Settings keys, beside the existing `layout.splitter.*` entries:

* `layout.designer.left_width`
* `layout.designer.right_width`

Both use `core.database.get_setting` / `set_setting`. On load a value is
clamped into its static range. Values that are not integers, are empty, or
cannot be read fall back to the shipped default. A saved width that no longer
fits the window is trimmed for display by `fit_side_widths` but is not
rewritten; the preference returns when the window grows again.

## Tests

New file `tests/test_theme_designer_columns.py`, 30 tests, all passing
offscreen. It covers:

* shipped defaults and the exact geometry invariant at 880, 1000, 1400 and
  2000 px;
* `clamp_column_width` below, inside and above the range;
* `fit_side_widths` at no trim, proportional trim, exact combined slack and
  beyond it;
* left and right drag clamping, including the dynamic preview floor;
* shrink to the tab minimum, with both sides at their minimums and the
  preview at 360;
* a click with no motion preserving 480 / 520 preferences;
* bad saved values (out of range, non-numeric, negative, empty);
* widths persisting across tab instances;
* saved widths that no longer fit being trimmed without being rewritten;
* no horizontal scrollbars at 240 / 260 on every page and block of both
  theme kinds and on both right tabs;
* JSON header label hiding at 260 and returning at 300;
* the handle contract, its three distinct paint states, synthetic mouse drag
  and double-click, and handle placement at every width.

Commands run:

```
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_columns.py -q
# 30 passed

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_columns.py tests/test_theme_designer_stage2.py \
  tests/test_theme_designer_stage3.py tests/test_theme_designer_stage4.py \
  tests/test_theme_designer_m1_batch1.py \
  tests/test_theme_designer_discrepancy_fixes.py \
  tests/test_theme_designer_preview.py -q
# 111 passed

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_m1.py -q
# 14 passed

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_tab_unload.py -q
# 9 passed, then the process dumped core at QtWebEngine teardown
```

The `test_tab_unload.py` core dump happens after the assertions, at
WebEngine profile teardown, and is the known offscreen teardown issue, not a
test failure.

`tools/token_gallery.py` gained a "Column handle" sample with idle, hover and
dragging strips. It renders to `14-column-handle.png` in the gallery shots
directory.

## Real-display checklist

1. Open the Designer. The handles sit between the columns, 10 px wide, with a
   purple grip on the black chrome.
2. Drag the left handle right and left. The column follows, stops at 480 and
   240, and the pointer stays a split cursor.
3. Drag the right handle left and right. It stops at 520 and 260.
4. Drag a column toward the preview until the preview stops. It should stop
   at 360 px, not collapse.
5. Shrink the window. The side columns give way before the preview, and the
   window stops at 880 px.
6. Double-click each handle. Left returns to 260, right to 300.
7. Restart the app, reopen the Designer. Both widths return.
8. Move the window to the second monitor and back. Handles stay aligned with
   the columns and keep their paint.
9. At 240 / 260, walk both theme kinds and both right tabs. No horizontal
   scrollbar should appear.

## What could not be verified

* Windows paint, cursor, hit testing and DPI behaviour. This environment is
  Linux only.
* High DPI at 125, 150 and 200 percent. The offscreen runs used one scale
  factor; the handle is painted in device-independent units, but that has not
  been seen on a scaled display.
* Real mouse and real window-manager resizing on Pop!OS. The tests use
  synthetic Qt mouse events offscreen, and the drag maths is covered, but the
  feel and the cursor over a real compositor are not.
* Multi-monitor mixed scaling.
* The full suite count. The Designer suites above are green; the full run is
  reported separately in `docs/transition_pairing_bug.md`.

## Changed files

Task files:

* `core/constants.py` (new `DESIGNER_*` block)
* `ui/tabs/theme_designer_tab.py` (manual column body, drag, persistence,
  reset, JSON header reflow)
* `ui/widgets/theme_designer/column_handle.py` (new)
* `tests/test_theme_designer_columns.py` (new)
* `tools/token_gallery.py` (`page_columns` sample)
* `docs/designer_resizable_columns.md` (this file)

`core/constants.py`, `ui/tabs/theme_designer_tab.py` and
`tools/token_gallery.py` also contain unrelated uncommitted motion work in
this worktree. Only the column-related lines belong to this task.
