# Theme Designer — M1 batch 1

- **Date:** 11 November 2026
- **Scope:** M1-01, M1-02, M1-07, M1-25, M1-26, the WebEngine test split,
  and the single-owner document model follow-up.
- **State:** the worktree was already dirty when this pass started. Everything
  below describes the **local working tree**, not the last commit. No commit,
  reset or revert was made.
- **Platform:** Linux, offscreen Qt (`QT_QPA_PLATFORM=offscreen`) for the new
  gates; the showcase audit also ran offscreen with QtWebEngine enabled. See
  “Not verified” for Windows and high-DPI limits.

## Result in one line

M1-01, M1-02, M1-25 and M1-26 are complete. M1-07's three obsolete Lite preview
tests are marked “should not be run” and retained. The nine QtWebEngine-heavy
Lite suites are behind a marker and out of the default run. The ownership
investigation is now implemented: the tab owns one `ThemeDocument` and the
panels request edits.

| Item | Status | Proof |
| --- | --- | --- |
| M1-01 | Done | `docs/theme_designer_spec.md` §9 |
| M1-02 | Done | `dev/m1_batch1_audit.{py,json,md}` |
| M1-07 | Closed by skip | `tests/test_lite_designer_theme_awareness.py` |
| M1-25 | Done | `tests/test_theme_designer_m1_batch1.py` (14 themes) |
| M1-26 | Done | `tests/test_theme_designer_m1_batch1.py` (1 smoke) |
| Ownership | Implemented | §6 below; `ThemeDocument` + `bind_document` |
| WebEngine split | Done | `pytest.ini` + nine `pytestmark` lines |

---

## 1. M1-01 — per-key coverage matrix

The matrix is now **§9 of `docs/theme_designer_spec.md`**, “Property coverage
matrix (M1-01)”. It has one row per key in `docs/theme_file_reference.md`,
grouped by the reference's own sections: top level, `slide`, canvas, animation
library, animation assignments, `split`, containers, `position`, `border`,
`box_shadow`, blocks, and shared files.

Every row carries one of the four required marks:

- **editable** — a dedicated Designer control reads and writes it; the note
  names the control and calls out partial coverage.
- **needs control** — operator-facing, but reachable only through raw JSON.
- **preserve-only** — must survive load → edit → save, but is not a design
  property (identity, legacy shape, shared-file entry).
- **raw** — intentionally JSON-only for v1.

The matrix spot-check passes: every row-level key name in the reference tables
is represented in §9. Grouped paths such as `containers[].border` map to the
`border` section. The tokens that do not appear are values, enum members and
function names (`fade_up`, `uppercase`, `rgba`, `hue-rotate`, `px`, …), which
rows reference through their parent key.

The `needs control` rows (11 table rows, 10 distinct concerns;
`blocks.body.animation` appears in both §9.5 and §9.11) are the honest
remaining build list:

- `slide.show_title`;
- a named animation definition's own `duration_ms`, `delay_ms`, `easing` and
  `origin` (the phase card edits slot overrides, not the library entry);
- container animation on `containers[1..]`;
- `blocks.body.animation`;
- non-split block animation phases (`entry`/`out`/transition) for text-bearing
  blocks;
- the same non-split block animation row under the shared-block summary.

§9.13 points at those rows rather than maintaining a second list. The old
“What the Designer Cannot Edit Yet” paragraph in §2 now points at §9 and is
marked superseded, so there is one source of truth.

---

## 2. M1-02 — showcase audit

The audit is `dev/m1_batch1_audit.py`; its raw output is
`dev/m1_batch1_audit.json` and its readable log is
`dev/m1_batch1_audit.md`. It builds the **real** `ThemeDesignerTab` and the
**real** `ThemeQuickEditor` against a temporary copy of `themes/`, so no
repository theme is written.

The coverage map is built from the editor's own specs (`CANVAS_SPECS`,
`CONTAINER_SPECS`, `block_specs`, the workspace fields, the four phase cards
and the local animation definitions reachable from container 0). It is a
reachability map, not a mouse-driven click of every row; the widgets themselves
are real.

### Summary

| Measure | Result |
| --- | --- |
| Showcase themes driven | 8 |
| Full Designer save key loss | **0** |
| Full Designer render differences after load → save (no operator edit) | **0** |
| Full Designer save refusals / exceptions | **none** |
| Quick Editor collect key loss | **0** |
| Quick Editor save key loss | **0** |
| Quick Editor save refusals / exceptions | **none** |
| Themes with a Quick Editor render difference | **0** after M1-04 (was **1**, `default_quiet`) |
| Animation slots | **75 total: 18 editable, 57 uneditable** |

### Per theme

| Theme | Containers | Slots editable / uneditable | Full save loss | Full render diffs | Quick key loss | Quick render diffs | Uncovered leaves | Save error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `fullscreen_rise` | 1 | 2 / 9 | 0 | 0 | 0 | 0 | 59 | none |
| `fullscreen_pop` | 1 | 3 / 9 | 0 | 0 | 0 | 0 | 61 | none |
| `fullscreen_split` | 2 | 3 / 3 | 0 | 0 | 0 | 0 | 16 | none |
| `default_typewriter` | 1 | 2 / 8 | 0 | 0 | 0 | 0 | 37 | none |
| `default_quiet` | 1 | 2 / 8 | 0 | 0 | 0 | 0 (was 2) | 53 | none |
| `reference_frames` | 1 | 2 / 8 | 0 | 0 | 0 | 0 | 35 | none |
| `reference_letterbox` | 1 | 2 / 8 | 0 | 0 | 0 | 0 | 39 | none |
| `slides_motion` | 1 | 2 / 4 | 0 | 0 | 0 | 0 | 47 | none |

### Animation slots per theme

`E` = entry, `O` = out, `TI` = transition in, `TO` = transition out. A bare
name is a theme-local definition; `use:name` is a shared/built-in reference.

| Theme | Container slots | Block slots |
| --- | --- | --- |
| `fullscreen_rise` | main: `E=use:fade_in`, `O=use:fade_out` | text: `E=rise_soft`, `O=sink_soft`, `TI=rise_soft`, `TO=sink_soft`; reference: `E=use:fade_up`, `O=use:fade_out`, `TI=use:fade_up`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `fullscreen_pop` | main: `E=use:scale_up`, `O=use:fade_out`, `TO=use:scale_down` | body: `E=use:fade_in`; text: `E=pop_in`, `O=pop_out`, `TI=pop_in`, `TO=pop_out`; reference: `E=use:pop_in`, `O=use:fade_out`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `fullscreen_split` | verse: `E=use:slide_up`, `O=use:slide_down`, `TI=use:slide_up`; cite: `E=use:fade_up`, `O=use:fade_down`, `TI=use:fade_up` | none |
| `default_typewriter` | main: `E=use:fade_in`, `O=use:fade_out` | text: `E=type_gold`, `O=fade_down`, `TI=type_gold`, `TO=fade_out`; reference: `E=use:type_cite`, `O=use:fade_out`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `default_quiet` | main: `E=use:fade_in`, `O=use:fade_out` | text: `E=quiet_in`, `O=quiet_out`, `TI=quiet_in`, `TO=quiet_out`; reference: `E=use:fade_in`, `O=use:fade_out`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `reference_frames` | main: `E=frame_in`, `O=frame_out` | text: `E=use:fade_up`, `O=fade_out`, `TI=fade_up`, `TO=fade_out`; reference: `E=use:fade_in`, `O=use:fade_out`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `reference_letterbox` | main: `E=use:slide_up`, `O=use:slide_down` | text: `E=letterbox_settle`, `O=fade_out`, `TI=letterbox_settle`, `TO=fade_out`; reference: `E=use:fade_up`, `O=use:fade_out`; translation: `E=use:fade_in`, `O=use:fade_out` |
| `slides_motion` | main: `E=use:fade_in`, `O=use:fade_out` | text: `E=lyric_pop`, `O=lyric_out`, `TI=lyric_pop`, `TO=lyric_out` |

The Designer can edit **only container 0's four phases** (18 of 75 slots).
All 57 block-level slots are uneditable; the `cite` container in
`fullscreen_split` is also uneditable because `AnimationPanel` hardcodes
`containers[0]`. This is the largest parity gap and is already recorded as
M1-20 (block-level slots) and M1-20's container coverage.

### Render differences

The original batch-1 run observed one difference, only through the **Quick
Editor**:

- `default_quiet`
  - `containers[0].blocks.reference.font_family`:
    `'DM Sans', sans-serif` → `'Nunito', sans-serif`
  - `containers[0].blocks.translation.font_family`:
    `'DM Sans', sans-serif` → `'Nunito', sans-serif`

The Full Designer produced no resolved-theme difference on any theme. The Quick
Editor's legacy `ThemePropertiesPanel._collect_theme()` rebuilt those block
fonts from its own defaults, so a load → collect → save changed what OBS would
render even with no operator edit. It was not key loss, but it was a real
fidelity defect of the legacy panel.

**Fixed by M1-04.** Quick Editor and Lite Designer now mount the shared
`ThemePropertyEditor`; the legacy collect path is no longer used. The audit was
regenerated after the swap and reports **0 Quick render diffs** for all eight
themes. `tests/test_theme_quick_lite_shared_editor.py` is the regression gate.

### Fields that cannot be selected

**Full Designer.** No ordinary canvas, container or block property was
uncovered. The unselectable leaves are:

- every block-level animation slot (57 leaves across the eight themes);
- container animation on `containers[1..]` (`fullscreen_split`: 8 leaves);
- animation-library definition fields that are not slot overrides — a named
  definition's own `type`, `label`, timing/easing/origin, and preset
  `keyframes`/`reveal`/`cursor` when the definition is not local and reached
  from a container-0 slot;
- `slide.show_title` (freeform switch);
- metadata (`label`, `description`, `author`) and container `id`
  (intentionally raw/preserve-only).

**Quick Editor.** By design it exposes only the four managed elements and a
subset of their typography. It cannot select: canvas (`width`, `height`,
`background`, `fit`); container add/duplicate/delete/reorder; container
`kind`/`layer`/`visible`/min/max/opacity/overflow; position/anchor and canvas
drag; the body block (`valign`, `gap`, `padding`); the freeform title block;
non-text block styling outside the four managed elements; split; any animation
phase or animation library entry; `slide.show_title`; or metadata.

**Save refusals.** None. All eight Full Designer and all eight Quick Editor
saves completed without an exception, and a cold reload lost zero keys.

The readable per-theme log is `dev/m1_batch1_audit.md`; every uncovered leaf
path (the Markdown log truncates long lists) is in
`dev/m1_batch1_audit.json`.

---

## 3. M1-25 — shipped-theme round-trip gate

**Test:** `tests/test_theme_designer_m1_batch1.py::test_every_shipped_theme_survives_designer_edit_save_reload`

The test is parametrized over **every** shipped theme file:

`themes/scripture/*.json` (12) + `themes/freeform/*.json` (2) = **14 themes**.

For each theme it:

1. loads the raw file into a real `ThemeDesignerTab`;
2. edits one representative field in every property group through the real
   panel APIs:

   | Group | Edit |
   | --- | --- |
   | Canvas | `background = #123456`, `fit = contain` |
   | Container | `opacity = 0.9`, `border_radius = 9` |
   | Container effects | a leaf inside a structured `border` (`radius` or `width`), a leaf inside `box_shadow` (`blur` or `x`), and `backdrop_filter` where present — sibling keys are left intact |
   | Freeform slide | `slide.show_title = true` where `slide` exists |
   | Body | `gap = 11` (when the block exists) |
   | Text | `size = 43`, `line_height = 1.25` |
   | Reference / title | `color = #a1b2c3` |
   | Translation | `margin_left = 9` |
   | Verse number | `opacity = 0.8` |
   | Split | `by = word`, `stagger_ms = 120` on the first split-capable block |
   | Geometry | workspace X field emits `37` (the same signal as an operator edit) |
   | Animation | first unused container-0 phase gets `fade_up`; if all four are used, `duration_ms = 777` is written as an override |

3. saves through the tab's real `_on_save()` → `theme_loader.save_theme`;
4. reloads from disk with `theme_loader.reload_themes()` and a cold
   `get_theme()`;
5. resolves with `core.theme_schema.normalize_theme`;
6. asserts **no source leaf key was lost**, the saved/reloaded key set equals
   the tab's working document, and the resolve has no errors and no more
   warnings than the untouched source;
7. asserts the edits actually landed (`canvas.background`, `position.x == 37`,
   a split with `by == "word"`), so a silently no-op editor cannot make the
   gate pass.

**Result:** 14/14 themes passed, zero lost keys, zero new warnings. The gate
also exercises the tab's single-owner document: property edits, workspace
geometry and animation-slot edits all pass through `ThemeDesignerTab` before
Save.

The theme loader is redirected to a temporary copy of `themes/`; the gate never
writes the repository files.

---

## 4. M1-26 — offscreen Designer smoke

**Test:** `tests/test_theme_designer_m1_batch1.py::test_designer_opens_every_pane_every_block_tab_and_saves`

A real `ThemeDesignerTab` is shown offscreen and driven through:

- the left **Canvas**, **Container** and **Blocks** pages;
- **every block tab** the theme offers (Body, Text, Reference, Translation,
  Verse # for `default_quiet`);
- the centre **Preview** and **Editor** views (the Editor mounts the real
  container workspace);
- the right **Animations** and **JSON** tabs;
- **Save**, a cold reload, and the dirty/unload contract
  (`is_dirty() == False`, `can_unload()[0] is True`, saved key set equals the
  working document).

**Result:** 1/1 passed. The preview widget is a lightweight QWidget stub because
constructing the real `QWebEngineView` aborts the offscreen Qt platform (the
known Lite-Designer/WebEngine teardown issue). The pane wiring, every panel,
every block tab and the whole Save path are real. The real QtWebEngine preview
is exercised by `dev/m1_batch1_audit.py` instead.

---

## 5. M1-07 — the three Lite preview tests

The three failing tests called `LiteDesigner._render_theme_preview` and asserted
its old “Theme tab preview follows the deck” behaviour. That method was removed
when the freeform preview (follows the deck) and the Theme preview (sample
verse) were deliberately split. They cannot pass against the current API.

Per the operator decision, they are **marked “should not be run”** with
`@pytest.mark.skip(reason="Should not run: …")`, not deleted:

| Test | Feature it covered | Current replacement |
| --- | --- | --- |
| `test_theme_preview_renders_active_slide_for_deck` | Theme tab preview renders the active deck slide with `theme_data` | `test_freeform_preview_carries_slide_and_theme` (freeform preview) |
| `test_working_theme_change_rerenders_slide` | A live theme change re-renders the deck into the Theme tab preview | None; the current Theme preview keeps its sample verse |
| `test_quick_edit_without_deck_keeps_sample_verse` | Theme tab preview without a deck keeps the sample verse | No direct test; the current preview is sample-verse based, but this test calls the removed method |

**Proposal:** keep the skips until the operator confirms the product behaviour
is no longer wanted, then delete the three tests in a dedicated cleanup. If the
“theme change refreshes the deck preview” behaviour is still wanted, write a new
test against the current `_refresh_preview()` rather than resurrecting
`_render_theme_preview`. **Nothing was deleted in this pass.**

Verification: `pytest -m webengine` selects all five tests in the file; the
three obsolete ones report **3 skipped in 0.05 s** when selected directly.

---

## 6. Single-owner document (implemented)

The follow-up requested after batch 1 replaces the merge workaround. One
`ThemeDocument` is the only mutable copy; every panel renders a snapshot and
requests path edits. No panel emits a whole document into the tab.

### Owner and views

| Component | Holds | Writes | Emits |
| --- | --- | --- | --- |
| `ThemeDesignerTab` | one `_document: ThemeDocument`, plus `_original_theme` | `set_theme`, Save, Cancel, Import, JSON Apply and the `_working_theme` compatibility setter | `theme_saved` |
| `ThemeDocument` | the single mutable document and a revision counter | path `set` / `set_many`, `replace`, `add/duplicate/delete/reorder`, `set_container_rect` | `changed(paths, source)` and `replaced(source)` |
| `ThemePropertyEditor` | `_doc` read-model snapshot | canvas, container, block and split edits through the document | compatibility `theme_changed(full snapshot)` for standalone tests |
| `ContainerWorkspace` | `_theme` read-model snapshot | geometry, layer, visibility and structural operations through the document | compatibility `theme_changed`, `preview_changed`, `container_selected` |
| `AnimationPanel` | `_theme` read-model snapshot | container-0 slots, animation library, parameters and keyframes through the document | compatibility `theme_changed` |

Panels call `bind_document(document)` and ignore `changed` signals whose
`source` is themselves (the document already updated their snapshot through the
write helper). Other panels refresh from a fresh snapshot. The tab connects
`document.changed` / `document.replaced` to preview, JSON and toolbar updates
and never consumes the compatibility `theme_changed` signals.

`_working_theme` remains a property for dev harnesses and older tests: the
getter returns `document.snapshot()` and the setter calls `document.replace`,
so there is still exactly one document. Selection stays tab-owned
(`_selected_container_id`); panels only request selection changes.

### What changed

- `ui/widgets/theme_designer/document.py` — new `ThemeDocument`: deep-copy
  snapshots, path-based `set` / `set_many` (a `None` leaf deletes), whole-document
  `replace`, structural container operations and geometry writes. Emits one
  `changed` per batch.
- `ui/widgets/theme_designer/property_editor.py` — `bind_document`, snapshot
  read model, `_write` / `_write_split` and four-side writes request document
  edits; `get_theme()` reads the document snapshot.
- `ui/widgets/theme_designer/container_workspace.py` — `bind_document`;
  geometry, visibility, layer and add/duplicate/delete/reorder go through the
  document. Canvas drag preview still uses `preview_changed` and only the final
  release writes the document.
- `ui/widgets/theme_designer/animation_panel.py` — `bind_document`; slot,
  library, parameter and keyframe edits go through the document. The local
  `theme()` remains a compatibility read.
- `ui/tabs/theme_designer_tab.py` — owns the document, binds the three panels,
  removes `_on_theme_changed` / `_on_workspace_changed` /
  `_on_animations_changed`, and routes load/cancel/import/JSON through
  `replace`. Save writes the document snapshot.
- `ui/widgets/theme_designer/document_sync.py` — deleted; `merge_animation_state`
  is no longer part of the runtime path.

### Regression coverage

`tests/test_theme_designer_m1.py`:
`test_properties_and_animation_views_share_one_document`,
`test_an_animation_edit_does_not_revert_workspace_geometry`,
`test_a_removed_animation_library_does_not_leave_a_stale_key`,
`test_containers_are_matched_by_id_not_index`.

`tests/test_theme_designer_m1_batch1.py`:
`test_panels_share_the_tab_owned_document` asserts the tab, property editor,
workspace and animation panel all hold the same document object and that edits
from two panels survive together.

The Quick Editor and Lite Designer still use their legacy property panel; that
is the separate M1-04 item. Undo/redo is still M1-05.

---

## 7. WebEngine-heavy Lite tests behind a marker

`pytest.ini` now defines:

```ini
markers =
    webengine: heavy QtWebEngine Lite Designer suite (excluded by default)
addopts = -m "not webengine"
```

Nine Lite files carry `pytestmark = pytest.mark.webengine`:

- `test_lite_designer_cards.py`
- `test_lite_designer_effective_state.py`
- `test_lite_designer_no_tab_bar.py`
- `test_lite_designer_ribbon_state.py`
- `test_lite_designer_select.py`
- `test_lite_designer_serialize.py`
- `test_lite_designer_theme_awareness.py`
- `test_lite_designer_tier_format.py`
- `test_lite_editing_scenarios.py`

Verified: `pytest tests/test_lite_designer_theme_awareness.py --collect-only`
reports **“no tests collected (5 deselected)”**; adding `-m webengine` collects
all five. The Designer and unit suites therefore run without building a
`QWebEngineView`.

This is a test-run split, not a feature removal: the files and tests remain in
the repository and can be run explicitly with `pytest -m webengine`.

---

## 8. Verification

Run in the local worktree:

```bash
# New gates + every Designer suite
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_theme_designer_m1_batch1.py \
  tests/test_theme_designer_m1.py \
  tests/test_theme_designer_stage2.py \
  tests/test_theme_designer_stage3.py \
  tests/test_theme_designer_stage4.py \
  tests/test_theme_v2_designer_roundtrip.py \
  tests/test_theme_quick_lite_shared_editor.py -q
# 95 passed

# Showcase audit (real tab + real Quick Editor, temp theme tree)
QT_QPA_PLATFORM=offscreen PYTHONPATH=. \
  QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu" \
  venv/bin/python dev/m1_batch1_audit.py
# M1 BATCH1 AUDIT PASS
# 0 Full Designer key loss, 0 Quick collect/save key loss, 0 save errors

# The three obsolete Lite tests are skipped, not run
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest -m webengine \
  tests/test_lite_designer_theme_awareness.py::test_theme_preview_renders_active_slide_for_deck \
  tests/test_lite_designer_theme_awareness.py::test_working_theme_change_rerenders_slide \
  tests/test_lite_designer_theme_awareness.py::test_quick_edit_without_deck_keeps_sample_verse -q
# 3 skipped in 0.05s
```

The audit process printed `M1 BATCH1 AUDIT PASS` and then segfaulted **at
interpreter teardown** with the known
`Release of profile requested but WebEnginePage still not deleted` message,
after writing both result files. The audit itself completed; this is the same
QtWebEngine teardown defect documented in the M1 status report.

---

## 9. What was **not** verified

- **Windows rendering.** No Windows machine is available in this worktree.
  Every measurement is Linux/offscreen.
- **High-DPI (125 % / 150 % / 200 %).** The new gates ran at devicePixelRatio 1.
  Popover clamping, canvas hit-testing and the 240 px column at scaled sizes
  were not re-checked.
- **Real QtWebEngine preview inside M1-25/M1-26.** Both new gates stub
  `ThemePreview` to avoid the offscreen WebEngine abort. The pane wiring, block
  tabs, property/workspace/animation panels and Save path are real; the actual
  rendered preview is not.
- **Visual appearance of the new gates.** They are offscreen assertions, not
  screenshots. No real-display click-through was performed in this batch.
- **Quick/Lite visual layout after M1-04.** The shared editor now occupies the
  380 px column, but the swapped popups were not inspected on a real display;
  the regression is an offscreen wiring/snapshot check.
- **Full test suite.** Only the seven Designer files above were run together
  after M1-04 (**95 passed**). The nine WebEngine Lite files were collected
  with markers; `test_lite_designer_theme_awareness.py -m webengine` was run
  separately after M1-04 (**2 passed, 3 skipped**, then the known teardown
  segfault). No complete suite run was made.
- **Root-level collection.** `pytest --collect-only` from the repository root
  still reports two pre-existing `ImportPathMismatchError`s from
  `mobile_version/tests` and `windows_update/tests` (duplicate `tests` package
  basenames). `pytest tests --collect-only` is clean: 1450 collected, 206
  deselected by the webengine marker. Those subprojects were not touched.

## 10. Files changed / added in this pass

- `ui/widgets/theme_designer/document.py` — **new**: the single-owner
  `ThemeDocument`.
- `ui/widgets/theme_designer/property_editor.py`,
  `ui/widgets/theme_designer/container_workspace.py`,
  `ui/widgets/theme_designer/animation_panel.py` — `bind_document` and path
  edit requests.
- `ui/tabs/theme_designer_tab.py` — tab-owned document; merge handlers removed.
- `ui/widgets/theme_designer/document_sync.py` — deleted.
- `tests/test_theme_designer_m1_batch1.py` — M1-25 gate (14 shipped themes),
  M1-26 offscreen smoke, and the tab-ownership regression.
- `tests/test_theme_designer_m1.py` — the four merge regressions replaced with
  single-owner regressions.
- `tests/test_tab_unload.py` — dirty edits now go through `_document`.
- `dev/m1_batch1_audit.py` — temp directory no longer hardcodes
  `/tmp/opencode`; regenerated `dev/m1_batch1_audit.json` and
  `dev/m1_batch1_audit.md`.
- `docs/theme_designer_m1_batch1.md` — this report.
- `docs/theme_designer_m1_status.md` — M1-01, M1-02, M1-25 and M1-26 marked
  done; M1-07 closed by skip; M1-29 marked partly done. M1-04 was added after
  this batch and is recorded in the status addendum.
- **M1-04 follow-up:** `ui/widgets/theme_quick_editor.py` and
  `ui/widgets/lite_designer/lite_designer.py` now mount
  `ThemePropertyEditor`; `tests/test_theme_quick_lite_shared_editor.py` is the
  new regression gate.

Pre-existing local work confirmed, not re-authored here: the §9 coverage matrix
in `docs/theme_designer_spec.md`, `pytest.ini`, the nine `webengine` markers,
and the three M1-07 skip reasons.
