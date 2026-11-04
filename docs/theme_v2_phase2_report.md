# Theme Schema v2 — Phase 2 Report

**Scope:** Python schema, migration, shared definitions, loader, designer
adapter, and the temporary v1 rendering bridge. The renderer rewrite
(`display/display.js`), shipped theme conversion, and `themes/_shared/` content
are Phase 3/4 work.

**Status:** Complete. All Phase 2 gate tests pass when run file-by-file. No
test was weakened or deleted, and the pre-existing Settings-cleanup work in the
tree is untouched.

---

## 1. What was built

| Module | Lines | Role |
|---|---:|---|
| `core/theme_schema.py` | 1795 | Enums/ranges, coercers, sanitizers, block defaults, `BUILTIN_ANIMATIONS`, `normalize_theme()`, `ThemeReport`, `SAFE_THEME` |
| `core/theme_migrate.py` | 578 | Deterministic, in-memory `migrate_v1_to_v2()` for all six shipped themes |
| `core/theme_shared.py` | 359 | `themes/_shared/{borders,shadows,palettes,animations}.json`: validation, palette expansion, `@name` resolution, mtime caching |
| `core/theme_compat.py` | 366 | Temporary resolved-v2 → v1 projection so the current renderer is byte-compatible until Phase 3 |
| `core/theme_loader.py` | 625 | Raw + resolved caches, `_shared` exclusion, array-aware `theme_container()` / `container_block()`, `slide_title_visible()`, raw `save_theme()` |
| `ui/widgets/theme_properties_panel.py` | — | v2 adapter: `_is_v2`, `_collect_theme_v2()`, position/body-padding writes, `visible:false` toggles, structured-value guard |
| `ui/widgets/theme_preview.py` | — | Resolves raw v2 before previewing; `display_view` projects |
| `ui/tabs/presentation_tab.py`, `ui/tabs/slides_tab.py`, `ui/widgets/display_view.py` | — | Bridge call sites (`project_legacy`) |

### Safety properties verified by tests

- Typed enums, numeric clamping, documented defaults, invalid-value fallback.
- Unknown keys are dropped from the resolved dict and reported at DEBUG in
  `ThemeReport.notes`; they never become warnings.
- CSS/HTML injection is blocked in every paint, border, shadow, outline, filter,
  font and animation field (including keyframe values and cursor text).
- `schema_version`: absent = v1, `2` = v2, `> 2` = safe theme fallback.
- `SAFE_THEME` matches today's `themes/scripture/fullscreen.json` look and is
  returned for every fatal input.
- Loading never rewrites user files; `save_theme()` writes exactly what it is
  given.
- `themes/_shared` is invisible to the theme list at any depth.

---

## 2. Test evidence

Every command was run individually with `timeout 120` and
`./venv/bin/python -m pytest <file> -q -p no:cacheprovider`.

### New Phase 2 suites — **396 passed**

| File | Tests | Result |
|---|---:|---|
| `tests/test_theme_v2_schema.py` | 31 | passed |
| `tests/test_theme_v2_security.py` | 118 | passed |
| `tests/test_theme_v2_migration.py` | 44 | passed |
| `tests/test_theme_v2_shared.py` | 56 | passed |
| `tests/test_theme_v2_animations.py` | 86 | passed |
| `tests/test_theme_v2_positions.py` | 47 | passed |
| `tests/test_theme_v2_designer_roundtrip.py` | 14 | passed |

Raw tail of the final run:

```
== schema                31 passed in 0.14s
== security             118 passed in 0.23s
== migration             44 passed in 0.14s
== shared                56 passed in 0.21s
== animations            86 passed in 0.44s
== positions             47 passed in 0.23s
== designer_roundtrip    14 passed in 4.55s
```

Coverage highlights:

- **Schema:** defaults, block synthesis, clamping, determinism, container
  repair/rename/cap, freeform alias rules, safe-theme fallback.
- **Security:** CSS/HTML smuggling attempts through colors, gradients, borders,
  shadows, filters, fonts, outlines, animation keyframes and cursor chars;
  Unicode control-character stripping.
- **Migration:** all six shipped themes migrate warning-free; v1 animation,
  flex, absolute-box, shadow/outline and freeform alias rules.
- **Shared:** family loading, malformed-entry degradation, mtime cache with
  palette invalidation and directory scoping, `{shared}` own/cross-family
  lookup, `@name` recursion/depth/cycle handling, `_shared` exclusion.
- **Animations:** registry completeness, required `type`, `duration_ms`
  defaults (600/900), preset keyframe rejection, custom frame rules,
  typewriter defaults/cursor, slot grammar/overrides/fallbacks, JSON safety.
- **Positions:** exact §4.3 anchor table, unconstrained-axis centering,
  percentages against the declared canvas, `fill` size override, corner-boolean
  legacy order, invalid-anchor fallback, projection geometry.
- **Designer round trip:** unknown top-level/container/block keys, sibling
  containers, structured borders/shadows and animation assignments survive;
  geometry goes to `position`, padding to `blocks.body`; toggles write
  `visible:false`; collected output re-resolves with zero warnings; v1 themes
  stay v1.

### Existing gates — all green when run individually

| File | Result |
|---|---|
| `tests/test_slides_theme.py` | 8 passed |
| `tests/test_lite_designer_ribbon_state.py` | 55 passed |
| `tests/test_theme_switch.py` | 12 passed (all `PASSED` in `-v`), then QtWebEngine teardown dump, exit 139 |
| `tests/test_slide_edit.py` | 34 passed |
| `tests/test_display_js.py` | 22 passed |
| `tests/test_display_render_matrix.py` | 12 passed |
| `tests/test_display_deck_formats.py` | 7 passed |
| `tests/test_slide_strips.py` | 6 passed |
| `tests/test_phase7_display.py` (alone) | 6 passed |
| `tests/test_output_sets.py` (alone) | 25 passed (exit 0 in the latest run) |
| `tests/test_display_step_and_push.py` (extra theme consumer) | 29 passed, 1 skipped |

The `test_theme_switch.py` exit 139 is the known QtWebEngine teardown message
(`Release of profile requested but WebEnginePage still not deleted`); every
test had already reported `PASSED`. `test_output_sets.py` has previously dumped
core at teardown after reporting 25 passed; the latest run exited cleanly.

---

## 3. Known pre-existing failure (not caused by this work)

`tests/test_lite_designer_theme_awareness.py` — **3 failed, 2 passed**, then the
same QtWebEngine teardown dump:

```
FAILED test_theme_preview_renders_active_slide_for_deck
FAILED test_working_theme_change_rerenders_slide
FAILED test_quick_edit_without_deck_keeps_sample_verse
AttributeError: 'LiteDesigner' object has no attribute '_render_theme_preview'
```

`ui/widgets/lite_designer/lite_designer.py` is unmodified in this work and the
method exists neither at `HEAD` nor in the worktree. The test file is also
unmodified. This is a pre-existing feature/test mismatch and is left untouched.

---

## 4. Deliberately deferred to Phase 3

These are spec behaviours that need the renderer, so Phase 2 documents them
rather than implementing them in Python:

1. **Typewriter target restriction.** §4.9 restricts `typewriter` to leaf text
   blocks. Python accepts it anywhere today; Phase 3 will coerce an invalid
   target (container / `body` / `out`) to `fade_in` / `fade_out` with a
   warning at render time.
2. **Outline-conflict warning.** When a block sets both `text_outline` and a
   hard-ring `text_shadow`, the renderer decides priority. Phase 3 will emit
   the documented warning once.
3. **`display.js` rewrite** and golden-fixture capture at 1920×1080; the v1
   bridge is removed in the same change.
4. **Shipped themes → v2** on disk and the real `themes/_shared/` content
   (Phase 4).

---

## 5. Compatibility notes

- `get_theme()` remains raw (v1 or v2) for the designer; `resolve_theme()`
  returns a deep-copied resolved v2 theme.
- Every payload builder, the preview widgets and the Lite Designer preview
  project through `core/theme_compat.project_legacy()` until Phase 3.
- Shipped v1 themes resolve with `canvas.fit:"none"` and zero warnings. The
  projection materializes the documented block defaults and CSS shorthands
  that the current renderer previously supplied itself (`border_radius: "0"`
  → `"0px"`, `padding: "0"` → `"0px 0px 0px 0px"`); rendered CSS is unchanged,
  which the display gates above verify. `_px()` prints integral floats without
  a trailing `.0`, so no numeric formatting difference reaches the renderer.
- Structured border/shadow objects are preserved by the designer when the
  operator does not edit their row; previously a load-edit-save cycle could
  stringify them into invalid CSS.
