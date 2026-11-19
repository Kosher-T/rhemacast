# Theme Designer — M1 reconciliation status

- **Date:** 11 November 2026
- **Scope:** M1-01 … M1-29 in `docs/ROADMAP_CHECKLIST.md`
- **Method:** read every M1 item, the four stage reports, and the implementing
  code/tests; closed the three named gaps on a real X display, then closed
  M1-01, M1-02, M1-25 and M1-26 in the batch-1 pass. M1-04 was closed in the
  follow-up pass (addenda at the end).
- **Platform:** Pop!OS, Xwayland `xcb` (`DISPLAY=:1`), 1400×900 app window,
  animation and property columns forced to 240 px for the real-display pass;
  batch-1 gates and the showcase audit ran offscreen. Screenshots in
  `dev/m1_shots/01…07`.

## Result in one line

11 items are done, 1 is closed by an explicit skip, 15 are partly done, and 2
are not done. Batch 1 closed M1-01, M1-02, M1-25 and M1-26; the M1-04 follow-up
moved Quick Editor and Lite Designer onto the shared property editor, and
M1-07's three obsolete Lite preview tests are marked “should not run” and
retained. The three gaps from the earlier pass remain verified on a real
display. Windows and high-DPI were **not** verified.

| Status | Count | Items |
| --- | --- | --- |
| Done | 11 | M1-01, M1-02, M1-04, M1-06, M1-09, M1-15, M1-16, M1-17, M1-18, M1-25, M1-26 |
| Closed by skip | 1 | M1-07 |
| Partly done | 15 | M1-05, M1-08, M1-10, M1-11, M1-12, M1-13, M1-14, M1-20, M1-21, M1-22, M1-23, M1-24, M1-27, M1-28, M1-29 |
| Not done | 2 | M1-03, M1-19 |

“Done” means the item's full text is satisfied and a named test or code path
proves it. “Partly” means the visible feature exists but at least one clause of
the item is missing. “Not done” means no implementation or no evidence.

## M1-01 … M1-29

Evidence paths are relative to the repository root.

### Discover and decide

| ID | Status | Evidence |
| --- | --- | --- |
| **M1-01** Property coverage matrix | **Done** | `docs/theme_designer_spec.md` §9 is the per-key matrix, grouped by `theme_file_reference.md` with editable / needs control / preserve-only / raw marks. §9.13 lists the remaining needs-control rows; the old “Cannot Edit Yet” paragraph points at §9. |
| **M1-02** Showcase audit | **Done** | `dev/m1_batch1_audit.{py,json,md}` drives all eight themes through the real Full Designer and Quick Editor on a temp theme tree: 0 key loss, 0 save refusals, 0 render diffs after M1-04, 75 animation slots logged (18 editable, 57 uneditable). The pre-M1-04 audit recorded one `default_quiet` Quick Editor font diff; it is now fixed and regression-tested. Findings in `docs/theme_designer_m1_batch1.md` §2. |
| **M1-03** Scope decision | **Not done** | `docs/theme_designer_spec.md` still describes the old Designer and has no “full parity vs 90 % + raw” decision. |
| **M1-04** One property editor, three entry points | **Done** | All three entry points mount the schema-driven `ThemePropertyEditor` (`ui/widgets/theme_designer/property_editor.py`). The Full Designer binds the tab-owned `ThemeDocument`; Quick Editor and Lite Designer mount it standalone, load their working snapshot with `load_theme`, and treat `theme_changed` as the new working snapshot, keeping their save-only contracts. `tests/test_theme_quick_lite_shared_editor.py` mounts both real popups (WebEngine preview stubbed), edits `default_quiet`, and proves its reference/translation fonts stay absent raw (resolving to `DM Sans`) instead of being rewritten to Nunito. The showcase audit reports 0 Quick render diffs. |
| **M1-05** Undo/redo + dirty model | **Partly** | Dirty model is real: `is_dirty()` / `can_unload()` and the unsaved-changes guard in `ui/tabs/theme_designer_tab.py`. No undo/redo stack anywhere, and no written definition of an undo step. |
| **M1-06** Fix the known key-loss risk | **Done** | `tests/test_theme_v2_designer_roundtrip.py` drives `ThemePropertiesPanel` over a v2 probe containing `future_engine_key`, `glow`, `text_transform` and sibling containers, and asserts unknown keys survive load → edit → save. A direct probe also confirms the historical pair (`text_transform: uppercase`, `text_align: center/left`) and an unknown block key survive `load_theme → get_theme`. Both keys have controls (`theme_properties_panel.py:840`, `:1084`). |
| **M1-07** Clear inherited test debt | **Closed by skip** | The three obsolete tests in `tests/test_lite_designer_theme_awareness.py` now carry `@pytest.mark.skip(reason="Should not run: …")`; they call the removed `LiteDesigner._render_theme_preview`. The feature each covered and the deletion proposal are in `docs/theme_designer_m1_batch1.md` §5. Tests retained, not deleted. |

### Build the shell

| ID | Status | Evidence |
| --- | --- | --- |
| **M1-08** Persistent three-pane shell | **Partly** | Three panes exist (left properties, centre workspace, right animation/JSON), but widths are hard-coded (`left_col.setFixedWidth(260)`, `right_col.setFixedWidth(300)`), `QSplitter` is imported and unused, and `core/panel_layout.py` persistence is not wired. |
| **M1-09** Container strip | **Done** | `ContainerStrip` + `ContainerWorkspace` implement add, duplicate, delete, reorder, visibility and layer, with one selection model. Covered by `tests/test_theme_designer_stage4.py` (`test_structural_selection_is_announced`, `test_duplicate_and_delete_round_trip_unknowns`, `test_reorder_sets_top_first_layers_and_keeps_ids`, `test_selection_is_shared_and_fields_follow_it`). |
| **M1-10** Block tabs | **Partly** | Body / text / reference / translation / verse_num tabs exist (`BlockTabBar`, `property_editor.py:_add_block_bar`) and each block page has a `Visible` row. Missing: visibility dots on the tabs (`BlockTabBar.visibility_toggled` is not connected) and a per-block reset. |
| **M1-11** Canvas panel | **Partly** | Width, height, background and `fit` are editable (`CANVAS_SPECS`). There is no “reset to 1920×1080” action. |
| **M1-12** Property search and reset | **Partly** | The “changed from default” marker and per-field reset glyph exist (`PropertyRow`). There is no name search/filter for the property list. |
| **M1-13** Validation panel | **Partly** | The property editor surfaces the first `ThemeReport` message in its note (`property_editor._after_edit`). Missing: a list of all warnings/errors, click-to-field navigation, and a save-time warning before writing. |
| **M1-14** Shared definitions browser | **Partly** | Border/shadow editors accept `shared_options` and palette tokens are accepted by colour fields, so shared refs are not raw-JSON-only. Missing: a dedicated browser over `themes/_shared/*.json` and a resolved-value preview. |

### Build the editors

| ID | Status | Evidence |
| --- | --- | --- |
| **M1-15** Container geometry | **Done** | Semantic anchor + numeric offsets; canvas drag/resize writes the numbers and the fields move the box; `min/max_width/height` are in `CONTAINER_SPECS`. Covered by the geometry cases in `tests/test_theme_designer_stage4.py` (`test_anchor_rect_round_trip`, `test_percentage_offset_and_size_resolve_against_canvas`, `test_canvas_edit_preserves_unknown_keys_and_reaches_document`, `test_canvas_move_keeps_auto_and_percent_forms`). |
| **M1-16** Border and shadow editors | **Done** | `BorderEditor` (base, per-side width/style/colour/radius, shared refs) and `ShadowEditor` (structured single layer, CSS multi-layer, shared refs, spread toggle) write the document. `tests/test_theme_designer_stage2.py::test_structured_shadow_shape_round_trips` plus the M1 inline-label tests. |
| **M1-17** Background editor | **Done** | `PaintField` covers solid, linear/radial gradient, transparent/none and `@palette` tokens with a live swatch. `tests/test_theme_designer_stage2.py::test_canvas_and_container_groups` writes `@accent`. |
| **M1-18** Typography editor | **Done** | `_COMMON_BLOCK` covers family, size, `min_size`, `max_size`, weight, line-height, letter/word spacing, alignment, transform, style, decoration, outline, shadow, margins, padding, `max_lines`, direction, opacity and visible; `autosize` is added for the text block. `tests/test_theme_designer_stage2.py::test_block_groups` writes transform and friends across every block. |
| **M1-19** Animation library CRUD | **Not done** | Only “Copy into theme” exists (`animation_panel.py`). There is no create, duplicate, rename, delete, or “which slots use this” list. A copied definition cannot be removed from the saved theme through the GUI. |
| **M1-20** Slot assignment | **Partly** | Entry/transition-in/transition-out/out for the **container** are editable through four registry-driven phase cards. Block slots are absent, and the card's replay signal is connected to a no-op (`card.replay.connect(lambda _v: None)`, `animation_panel.py:222`). |
| **M1-21** Split editor | **Partly** | `SplitEditor` is mounted on the Blocks page and writes `by`, `stagger_ms`, first/rest assignments and looks. `set_readout()` is never called, so there is no live unit count; `disabled_reason` is not passed, so nested split is not explained. |
| **M1-22** Raw JSON editor | **Partly** | Plain `QTextEdit` with Format / Copy / Apply and two-way refresh. Missing: syntax highlighting, validate, revert, and a visible error path — an invalid Apply is silently ignored (`_on_apply_json` returns), which does protect the last good document but tells the user nothing. |
| **M1-23** File lifecycle | **Partly** | Save, Export, Import and the unsaved-changes guard work (verified with real clicks; see below). Missing: theme duplicate/rename/delete UI, and hot reload after save — `theme_saved` only reloads the themes list in the presentation tab (`main_window._on_theme_saved`), it does not re-push the live theme to OBS. |
| **M1-24** Preview that is the renderer | **Partly** | `ThemePreview` embeds the real `DisplayView` renderer (not a mock) and offers four verse samples. Missing: freeform sample, blank-block states, play/replay, before/after compare, 16:9/OBS-size zoom, safe-area guides. |

### Prove it

| ID | Status | Evidence |
| --- | --- | --- |
| **M1-25** Round-trip gate | **Done** | `tests/test_theme_designer_m1_batch1.py::test_every_shipped_theme_survives_designer_edit_save_reload` is parametrized over all 14 shipped themes. Each loads, edits one field per property group (canvas, container, body, text, reference/title, translation, verse #, split, geometry, animation), saves through the tab, cold-reloads, resolves, and asserts zero lost keys. **14 passed.** |
| **M1-26** Designer smoke test | **Done** | `tests/test_theme_designer_m1_batch1.py::test_designer_opens_every_pane_every_block_tab_and_saves` shows the real tab offscreen, opens Canvas/Container/Blocks, every block tab, Preview/Editor, Animations/JSON, saves and cold-reloads. **1 passed.** The preview widget is stubbed to avoid the offscreen WebEngine abort. |
| **M1-27** Keyboard and accessibility pass | **Partly** | Many controls carry accessible names and focus rings, and the kit was built keyboard-first. There is no systematic Tab-order/accessible-name sweep or recorded result. |
| **M1-28** Performance pass | **Partly** | Preview updates debounce at 80 ms (`_preview_timer`), and property edits do not rebuild the document. No 60 fps measurement, and no proof that drag/resize avoids reflow. |
| **M1-29** Spec refresh | **Partly** | The §2 “Cannot Edit Yet” list now points at the §9 coverage matrix, and the matrix landed. Remaining: link the new doc anchors from tooltips. |

## The three gaps closed in this pass

### 1. Animation panel at 240 px, shared/built-in copy, no stale editors

- All four phase cards measure **210 px** in a 240 px column, with no child
  crossing the card bounds (`dev/m1_shots/01_animation_240.png`,
  `02_animation_cards_240.png`).
- Selecting built-in `fade_up` and clicking **Copy into theme** creates
  `theme["animations"]["fade_up"]` while preserving the slot
  (`03_animation_copy.png`).
- Switching a slot through `fade_up → typewriter → custom → fade_up →
  fade_in → none` leaves **at most one visible `ParamForm`** and no overflowing
  child at every step (`04_animation_switches.png`).
- Tests: `test_animation_cards_fit_a_240px_column`,
  `test_builtin_animation_copies_into_theme_at_240px`,
  `test_switching_slot_types_leaves_no_stale_editor_at_240px` in
  `tests/test_theme_designer_m1.py`; stage-3 equivalents already existed.

### 2. Inline labels inside numeric fields at 240 px

`NumberField` gained `inline_label=`: a short muted label drawn inside the
field, with the accessibility/tooltip name still taken from `label`. The label
itself scrubs the value, exactly like a `PropertyRow` label.

Measured on the real display, 240 px popover (212 px editor):

| Field | Label width | Field width | Result |
| --- | --- | --- | --- |
| Shadow X | 8 px | 104 px | inside bounds |
| Shadow Y | 7 px | 104 px | inside bounds |
| Shadow Blur | 24 px | 104 px | inside bounds |
| Shadow Spread | 40 px | 104 px | inside bounds |
| Border radius (base) | 38 px | 212 px | inside bounds |
| Border radius (side) | 38 px | 212 px | inside bounds |

Screenshots `05_shadow_inline_240.png` and `06_border_inline_240.png`. The
shadow fields dropped their `PropertyRow` wrappers and live in the existing
2×2 grid; base and side border radius are full-width inline-labelled fields.
The kit rule is recorded in `docs/theme_kit_stage1_report.md` and the
`NumberField` docstring: a numeric field mounted without a row label must pass
`inline_label`; a field already inside a row-labelled `PropertyRow` must not,
or the label appears twice.

Tests: the six inline-label cases in `tests/test_theme_designer_m1.py`
(visibility, fit at 240 px, no label when unset, no double label, multi-layer
shadow, base + side radius).

Round 3 removed the base and side radius fields from the Border popup: the
container's Radius (Border ▸ subparameter) is the only radius control, because
`border_radius` wins over `border.radius` in the renderer and the duplicate
looked dead. That test now asserts the fields are absent and that a stored
`border.radius` survives an edit.

### 3. Real Save, Export, Import with unknown keys

Run with a redirected themes directory (a temp copy of `themes/`, never the
repo files), real toolbar buttons, and a cold reload after Save:

- **Save** wrote `…/themes/scripture/m1_live.json` and the reload preserved
  `unknown_top`, `unknown_container_key`, `unknown_block_key` and
  `animations.fade_up`.
- **Export** put **4415 bytes** of document JSON on the clipboard; the unknown
  keys were present in the exported text.
- **Import** read the clipboard back and preserved `unknown_imported` plus the
  container unknown keys (`07_toolbar_import.png`).

## Bug found while proving Save

The first real Save lost `theme["animations"]` entirely. Cause: the properties
and workspace editors keep their own document copies. Whichever panel emitted
last replaced the working copy wholesale, so a border edit reverted the
animation library and the container `animation` slots (and an animation edit
could revert a container move). This was invisible in unit tests because each
panel was tested alone.

Fix (follow-up): the single-owner `ThemeDocument`. `ThemeDesignerTab` owns
the one mutable document; the property, workspace and animation panels render
snapshots and request path edits (`bind_document`). The tab no longer merges
whole-document emits, and `document_sync.py` / `merge_animation_state` were
deleted.

Regression tests in `tests/test_theme_designer_m1.py`:
`test_properties_and_animation_views_share_one_document`,
`test_an_animation_edit_does_not_revert_workspace_geometry`,
`test_a_removed_animation_library_does_not_leave_a_stale_key`,
`test_containers_are_matched_by_id_not_index`. The tab-level identity check is
`tests/test_theme_designer_m1_batch1.py::test_panels_share_the_tab_owned_document`.

The real-display harness now also asserts, after the border edit, that the
slot state last written by the animation panel is still present
(`{'out': {'type': 'fade_in', 'duration_ms': 400}}`).

## Remaining M1 work, size and release impact

Sizes are engineering effort for the item as written: **Small** ≤ half a day,
**Medium** ≈ 1–2 days, **Large** > 2 days.

| ID | Remaining work | Size | Blocks release? |
| --- | --- | --- | --- |
| M1-03 | Write the v1 scope decision (full parity vs 90 % + raw) | Small | **Yes** — every other scope call depends on it |
| M1-05 | Undo/redo stack and the written undo-step rule | Medium | No — dirty/save guard exists; add post-M1 |
| M1-08 | Replace fixed columns with a persisted `QSplitter` | Small | No |
| M1-10 | Per-block reset and tab visibility dots | Small | No |
| M1-11 | “Reset canvas to 1920×1080” action | Small | No |
| M1-12 | Property search/filter | Medium | No — changed marker and per-field reset exist |
| M1-13 | Full validation list, click-to-field, save-time warning | Medium | **Yes** — a save that writes warnings must say so first |
| M1-14 | Shared-definition browser and resolved preview | Medium | No — shared refs are selectable today |
| M1-19 | Animation create/duplicate/rename/delete + usage list | Medium | **Yes** — copied definitions currently accumulate with no GUI cleanup |
| M1-20 | Block-level slots and a working replay | Large | **Conditional** — container slots satisfy the basic “change an animation” flow; block animation is the largest parity gap |
| M1-21 | Wire the unit-count readout and nested-split rejection message | Small | No |
| M1-22 | Syntax highlighting, validate, revert, visible error on invalid Apply | Medium | **Yes** — raw editing is the escape hatch for advanced fields, so its failure mode must be legible |
| M1-23 | Theme duplicate/rename/delete and OBS hot reload after save | Medium | **Yes** — hot reload is the difference between “saved” and “live” |
| M1-24 | Freeform/blank samples, replay, before/after, zoom, safe-area guides | Medium | No — the real renderer and verse samples are already there |
| M1-27 | Recorded Tab-order / accessible-name sweep and fixes | Medium | **Yes** (verification) — cheap, and it can expose a keyboard trap |
| M1-28 | Measure drag/resize and preview at 60 fps | Small | No — debounce exists; measure before claiming the clause |
| M1-29 | Link the §9 matrix doc anchors from tooltips (the matrix and the superseded pointer landed) | Small | No — the spec now states the coverage; anchors are polish |

## What was verified, and what was not

**Verified**

- `tests/test_theme_designer_m1.py` (13 tests),
  `tests/test_theme_designer_stage3.py` (11),
  `tests/test_theme_designer_stage4.py` (21 functions, parametrized):
  **54 passed**.
- Real display (`DISPLAY=:1`, `QT_QPA_PLATFORM=xcb`, WebEngine with
  `--no-sandbox --disable-gpu`): `dev/m1_check.py` prints **M1 CHECK PASS** and
  writes `dev/m1_shots/01…07`.
- Save/Export/Import were clicked through the real toolbar, against a temporary
  themes directory, with a cold reload.

**Not verified**

- **Windows rendering.** No Windows machine was available. The kit paints its
  own previews and avoids platform-specific effects, but that is an argument,
  not a measurement.
- **High-DPI hit-testing.** All measurements were at 1× on a 1400×900 window.
  Popover clamping, inline-label widths and the 240 px column were not checked
  at 150 %/200 % scaling.
- **Touch/stylus and large canvases.** Not exercised.
- **Full offscreen suite: not completed.** The run was stopped after ~15
  minutes at ~100 % CPU. The measured cause is the Lite Designer/WebEngine
  group, which builds a `LiteDesigner` → `ThemePreview` → `QWebEngineView` per
  test: `tests/test_lite_editing_scenarios.py` alone is 64 s and 1.67 GB peak,
  and all nine Lite Designer files in one process are 157 s and **3.97 GB
  peak RSS**, ending in the known WebEngine teardown segfault
  (`Release of profile requested but WebEnginePage still not deleted`). The
  three known M1-07 tests are now explicit skips, and `pytest.ini` excludes the
  whole webengine group from the default run (`-m "not webengine"`). The M1
  gate above does not depend on these UI tests.

## Files changed for this pass

- `ui/theme_kit/number_field.py` — `inline_label` (visible label, scrub
  behaviour, accessibility name unchanged).
- `ui/theme_kit/shadow_editor.py` — inline-labelled X/Y/Blur/Spread; removed
  the `PropertyRow` wrappers.
- `ui/theme_kit/border_editor.py` — inline-labelled base and side radius.
- `ui/widgets/theme_designer/document.py` — **new**: the single-owner
  `ThemeDocument`.
- `ui/widgets/theme_designer/property_editor.py`,
  `container_workspace.py`, `animation_panel.py` — snapshot views and path
  edit requests.
- `ui/tabs/theme_designer_tab.py` — tab-owned document; merge handlers removed.
- `ui/widgets/theme_designer/document_sync.py` — deleted.
- `tests/test_theme_designer_m1.py` — new: inline labels, 240 px animation
  cards, single-owner regressions.
- `tests/test_theme_designer_m1_batch1.py` — tab-ownership regression added.
- `dev/m1_check.py` + `dev/m1_shots/` — real-display evidence harness.
- `docs/theme_kit_stage1_report.md` — kit rule for inline labels.

### M1-04 follow-up files

- `ui/widgets/theme_quick_editor.py` — mounts `ThemePropertyEditor`.
- `ui/widgets/lite_designer/lite_designer.py` — mounts `ThemePropertyEditor`.
- `tests/test_theme_quick_lite_shared_editor.py` — **new**: real Quick/Lite
  snapshots and the `default_quiet` font regression.
- `dev/m1_batch1_audit.py` — Quick collection now reads `get_theme()`; the
  unselectable list reflects the shared editor.
- Regenerated `dev/m1_batch1_audit.json` and `.md`.

M1-04 was implemented after this pass; its close-out is below. The remaining
work above is reported, not implemented.

## Reproduce

```bash
# Designer suites (offscreen)
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_m1.py tests/test_theme_designer_stage3.py \
  tests/test_theme_designer_stage4.py -q

# Real display: 240 px cards, inline labels, Save/Export/Import
DISPLAY=:1 QT_QPA_PLATFORM=xcb PYTHONPATH=. \
  QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu" \
  venv/bin/python dev/m1_check.py

# The three M1-07 tests are explicit skips, not failures
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest -m webengine \
  tests/test_lite_designer_theme_awareness.py::test_theme_preview_renders_active_slide_for_deck \
  tests/test_lite_designer_theme_awareness.py::test_working_theme_change_rerenders_slide \
  tests/test_lite_designer_theme_awareness.py::test_quick_edit_without_deck_keeps_sample_verse -q

# Batch 1 gates: every shipped theme, plus the offscreen smoke
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_m1_batch1.py -q
```

## Batch 1 close-out (11 November 2026)

M1-01, M1-02, M1-25 and M1-26 are **done**; M1-07 is **closed by skip**.
The full findings, the implemented single-owner document model and the
not-verified limits are in `docs/theme_designer_m1_batch1.md`. The worktree
was left uncommitted, as requested.

- All six Designer suites together: **93 passed**.
- Showcase audit: **M1 BATCH1 AUDIT PASS** — 0 Full Designer key loss, 0 Quick
  collect/save key loss, 0 save errors. The process segfaulted at interpreter
  teardown after writing its results, the known WebEngine teardown defect.
- M1-07: **3 skipped in 0.05 s** when selected.
- Default collection of `tests/test_lite_designer_theme_awareness.py`:
  **5 deselected**; `-m webengine` collects all five.
- **Not verified:** Windows, high-DPI, and the real QtWebEngine preview inside
  the new M1-25/M1-26 gates (preview stubbed offscreen).

## M1-04 close-out (11 November 2026)

Quick Editor and Lite Designer no longer mount `ThemePropertiesPanel`; both use
`ThemePropertyEditor`, the same widget as the Full Designer. The sharing rule is:

- **Full Designer** binds its single tab-owned `ThemeDocument`
  (`bind_document`), so property, workspace and animation panels all request
  edits against one model.
- **Quick Editor / Lite Designer** mount the editor standalone. Its internal
  `ThemeDocument` is the edit model; `theme_changed` emits the full snapshot,
  which each popup stores as `_working_theme` and applies to its preview. Save,
  Reset and Cancel keep their existing save-only flows.

This removes the legacy collect path that rebuilt reference/translation fonts
from `ThemePropertiesPanel`'s own defaults. On `default_quiet`, those keys are
absent in the file and normalize to `DM Sans`; the shared editor leaves them
absent, so a load → edit → save no longer switches them to Nunito.

Verification:

- `tests/test_theme_quick_lite_shared_editor.py`: **2 passed** (real Quick
  Editor and Lite theme page, previews stubbed).
- New test plus the Designer suites: **95 passed**.
- Regenerated showcase audit: **M1 BATCH1 AUDIT PASS**, 0 Quick key loss, 0
  render diffs. It still segfaults at interpreter teardown after writing its
  results (known WebEngine teardown defect).
- `tests/test_lite_designer_theme_awareness.py -m webengine`: **2 passed, 3
  skipped**; the process segfaulted at teardown after the assertions.

**Not verified:** the 380 px Quick/Lite property column was not visually
inspected on a real display after the swap; the tests assert wiring, snapshots
and font fidelity only.
