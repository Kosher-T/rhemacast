# Scrollbars that never move content

Date: 2026-11-13
Scope: every scrollable surface in the app, with the Theme Designer as the
first visible case.

## Decisions for you

1. **Reserved gutter, not an overlay fade, for the shared mechanism.** Every
   bar keeps its lane permanently, so the viewport width is the same before
   and after overflow. The lane is transparent and the thumb simply appears
   when there is something to drag. See the comparison below for the cost.
2. **Both axes are reserved, including editors and popups.** A vertical bar
   protects content width. A horizontal bar protects content height from
   jumping. The cost is an 8 px blank strip at the bottom of editors and combo
   popups that never scroll sideways. Confirm that is preferable to a bar that
   appears on demand.
3. **The slide strips keep their overlay.** `SlideGridPanel` already paints a
   fading overlay bar over an `AlwaysOff` scroll area. It satisfies the same
   invariant without a lane and is deliberate for strip previews. It was not
   converted.
4. **The app event filter is the default for new panels.** It covers widgets
   constructed later, including dialogs and combo popups, without every panel
   calling a helper. Panels that want no bar still opt out with
   `ScrollBarAlwaysOff`, and the filter respects that.
5. **Thickness and minimum handle stay at the token values.** 8 px wide with a
   32 px minimum handle. Raising either is a one-line change in
   `ui/tokens.py`, but it changes every panel's geometry.

## Safe to skip

* A fade timer per scroll area. Native bars already handle wheel, keyboard,
  drag and focus, and a permanent lane has no feedback loop to guard.
* Replacing the app stylesheet with per-panel QSS. The sheet is installed once
  in `RhemaCastApp`; `apply_minimal_scrollbar` remains only for widget-local
  contexts such as tests and previews.
* Converting the slide strip overlay, the browser panel's paging scroller or
  the Lite Designer's hidden-bar editors. None of them reflow on overflow.

## Comparison

| | (a) Reserved gutter | (b) Overlay with fade |
|---|---|---|
| Content width | Constant by construction: the lane is always laid out | Constant only if the native bar is hidden and the overlay never takes layout space |
| Grab target | The real bar, 8 px, native drag anywhere on the thumb | Custom hit testing; a wider invisible target is possible but easy to misplace |
| Wheel, keyboard, focus | Qt native, unchanged | Still native on the hidden bar, but the visible thumb must mirror it and stay in sync |
| Failure modes | None beyond the reserved space | Timers, fade animation, resize feedback loops, two orientations, hover-near-edge logic |
| Code | About 110 lines (`ui/scrollbars.py`) plus one install call | The existing `_FadeScrollBar` is ~150 lines for one vertical overlay on one panel; generalising it means attaching to every abstract scroll area and forwarding events |
| Look | A quiet empty lane when idle | Nothing visible until scrolling |

Approach (a) is implemented. It reuses the existing application QSS and the
existing policy that three lists already used.

## Inventory

Every scrollable surface is a `QAbstractScrollArea` subclass: `QScrollArea`,
`QTextEdit`, `QPlainTextEdit`, `QListView` or `QListWidget`. The shared
mechanism therefore covers all of them at the base class.

| Surface | File | Before | Now |
|---|---|---|---|
| Settings pages | `ui/tabs/settings_tab.py` | `QScrollArea`, AsNeeded | Reserved lane |
| Theme Designer left pages | `ui/widgets/theme_designer/property_editor.py` | AsNeeded | Reserved lane |
| Animation cards | `ui/widgets/theme_designer/animation_panel.py` | AsNeeded | Reserved lane |
| Container workspace pane | `ui/widgets/theme_designer/container_workspace.py` | AsNeeded | Reserved lane |
| Theme properties panel | `ui/widgets/theme_properties_panel.py` | AsNeeded | Reserved lane |
| Hotkey editor | `ui/widgets/hotkey_editor.py` | AsNeeded | Reserved lane |
| Container editor | `ui/widgets/container_editor.py` | AsNeeded | Reserved lane |
| Draggable editor properties | `ui/widgets/draggable_editor.py` | AsNeeded | Reserved lane |
| Container canvas | `ui/theme_kit/container_canvas.py` | AsNeeded | Reserved lane |
| Shadow editor | `ui/theme_kit/shadow_editor.py` | AsNeeded, own 8 px QSS copy | Reserved lane |
| Scripture history | `ui/panels/scripture_history_panel.py` | Vertical AsNeeded, horizontal Off | Reserved vertical lane |
| Queue themes, deck outputs | `ui/widgets/scrollable.py` | Vertical AsNeeded | Reserved vertical lane |
| Verse list | `ui/panels/browser_panel.py` | `apply_minimal_scrollbar` | Unchanged, already reserved |
| Schedule list | `ui/panels/schedule_panel.py` | `apply_minimal_scrollbar` | Unchanged |
| Deck list | `ui/panels/deck_list_panel.py` | `apply_minimal_scrollbar` | Unchanged |
| Transcript | `ui/panels/stt_panel.py` | AsNeeded | Reserved both axes |
| Build log | `ui/tabs/settings_tab.py` | AsNeeded | Reserved both axes |
| Theme JSON editor | `ui/tabs/theme_designer_tab.py` | AsNeeded | Reserved both axes |
| Dialog text body | `ui/dialogs/__init__.py` | AsNeeded | Reserved both axes |
| Queue list | `ui/panels/queue_panel.py` | AsNeeded | Reserved both axes |
| Kit dropdown popup | `ui/theme_kit/dropdown.py` | AsNeeded | Reserved both axes |
| Combo popup | `ui/popups.py` | AsNeeded | Reserved both axes |
| Slide strips | `ui/panels/slide_grid_panel.py` | `AlwaysOff` plus `_FadeScrollBar` overlay | Unchanged, deliberate |
| Browser paging scroller | `ui/panels/browser_panel.py` | `AlwaysOff` | Unchanged, deliberate |
| Lite Designer card list | `ui/widgets/lite_designer/lite_designer.py` | `AlwaysOn` | Unchanged |
| Lite editors, slide cards | `ui/widgets/lite_designer/` | `AlwaysOff` | Unchanged |

`ui/tokens.scrollbar_qss()` is the single paint: installed once in
`core/ui.RhemaCastApp`, so there is no per-panel QSS to drift. The slide strip
overlay and the shadow editor's local copy were the only separate styles.

## Implementation

* **`ui/scrollbars.py`** (new) owns policy only. `reserve_scrollbar_lane`
  flips `ScrollBarAsNeeded` to `ScrollBarAlwaysOn` and leaves
  `ScrollBarAlwaysOff` alone. `ScrollbarLaneFilter` does that on `Polish` and
  `Show` for every `QAbstractScrollArea`. `install(app)` registers the filter
  once, keeps it alive on the application, and catches widgets that already
  existed.
* **`core/ui.py`** installs the filter before any widget is constructed.
  New panels and Qt-created views (combo popups, dialog editors) therefore get
  the lane without a call site.
* **`ui/widgets/scrollable.py`** reserves the vertical lane and keeps
  horizontal off unless the caller asked for horizontal scrolling.
* **`ui/styles.apply_minimal_scrollbar`** delegates its vertical policy to the
  shared helper and still appends the token QSS for widget-local use.
* **`ui/tokens.scrollbar_qss`** paints the lane transparent, idle handle in
  `BG_CARD_HOVER`, hover in   `ACCENT_BORDER`, drag in `ACCENT`. No arrows, no
  page area, 8 px thick, 32 px minimum handle, 4 px radius. The lane is
  transparent because an empty reserved strip must read as blank space. Qt
  would otherwise paint a full-length handle across an out-of-range bar, so
  `ui/scrollbars` marks each bar with a dynamic `rcLaneEmpty` property and
  the QSS makes that handle transparent until the bar has a range. The
  emitted `rangeChanged` values are used, not `maximum()`, because Qt can
  emit the signal before the new maximum is readable.
* **`tools/token_gallery.py`** gained a "Scrollbars" page with a vertical
  scroller and a horizontal one at the Designer's 300 px and 240 px widths.
  The gallery's own page scroller also reserves its lane now.

## Tests

New and updated tests in `tests/test_scrollbar.py` (12 tests) and
`tests/test_tokens.py` (26 tests):

* viewport width is identical before and after a `QScrollArea` becomes
  scrollable, with a widget that fills it;
* the same for `QListWidget` and `QTextEdit`;
* both viewport dimensions are identical before and after both bars appear;
* the `scrollable()` wrapper reserves the vertical lane and keeps horizontal
  off;
* `AlwaysOff` is never overridden, and opting out of horizontal leaves that
  policy alone;
* the application filter turns a newly created, newly shown `QTextEdit` into
  a reserved-lane editor;
* the QSS carries hover and pressed states in accent colours and both minimum
  handle dimensions;
* an empty reserved lane paints no handle at all, and the handle returns and
  disappears as overflow arrives and leaves (`rcLaneEmpty` property).

Commands and counts:

```
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_scrollbar.py tests/test_tokens.py -q
  # 38 passed

QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_columns.py tests/test_theme_designer_stage2.py \
  tests/test_theme_designer_stage3.py tests/test_slide_strips.py \
  tests/test_slide_cards_layout.py tests/test_lite_designer_select.py -q
# 78 passed
```

One pre-existing, order-dependent failure was reproduced while running a
wider batch:

`tests/test_panel_focus_ring.py::test_work_ring_paints_accent_on_its_edge`
fails when that file runs after several other UI modules, and passes when the
file runs alone (23 passed). It reproduces without the new scrollbar tests, so
it is shared offscreen focus and paint state between modules, not this change.
The same batch order also makes hover assertions in `test_settings_fields.py`
fail, which points at the same shared-state issue.

## Real-display checklist

1. Open Settings, then Theme Designer left pages, Animations and JSON. Scroll
   each. Content must not shift sideways when a thumb appears.
2. Drag a thumb. It turns solid accent while held; releasing returns it to
   the idle dark purple. Hover is the accent edge.
3. Make the JSON editor narrower and paste a long single line. The bottom
   lane is already reserved, so the editor does not change height when the
   horizontal bar becomes usable.
4. Open a combo with many items and a dialog with a long body. No sideways
   jump when they overflow.
5. Check the slide strips. They should keep the fading overlay and never show
   a reserved lane.
6. Try the wheel, Page Down and keyboard arrows in a long panel. Scrolling
   behaviour must match the previous build; only the layout is different.

## What could not be verified

* Windows paint, metrics and hover behaviour. This environment is Linux only.
* High DPI at 125, 150 and 200 percent. The lane is 8 device-independent
  pixels; scaling has not been seen on a real scaled display.
* Wheel, touchpad and kinetic scrolling feel. Native scroll bars are still in
  charge, but the reserved lane changes what the pointer can reach.
* RTL layouts.
* The full application boot through `RhemaCastApp` under WebEngine in this
  environment; the filter is covered directly in tests instead.

## Changed files

* `ui/scrollbars.py` (new)
* `ui/styles.py`
* `ui/widgets/scrollable.py`
* `ui/tokens.py`
* `core/ui.py`
* `tools/token_gallery.py`
* `tests/test_scrollbar.py`
* `tests/test_tokens.py`
* `docs/designer_scrollbars.md` (this file)
