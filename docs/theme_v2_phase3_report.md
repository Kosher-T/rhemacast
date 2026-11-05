# Theme v2 Phase 3 — Renderer Rewrite Report

_Status: **COMPLETE** — all tests passing_

---

## Overview

Phase 3 rewrote the display renderer (`display/display.js` and the byte-identical embedded copy in `ui/widgets/display_view.py`) to natively consume **resolved v2 themes** produced by Phase 2's Python layer.  
Phase-2's `project_legacy()` bridge has been removed from every call-site; the renderer now handles both v2 and v1-migrated payloads without shims.

---

## Files Changed

| File | Change |
|------|--------|
| `display/display.js` | Full rewrite — v2 stage/container/block engine |
| `display/display.html` | Added `<div id="stage">` wrapper |
| `display/themes.css` | Added `#stage` rule, `.rc-cursor`, structural resets |
| `ui/widgets/display_view.py` | Regenerated — mirrors `display.js` byte-for-byte on shared functions |
| `ui/tabs/presentation_tab.py` | Removed `project_legacy()` bridge call |
| `ui/tabs/slides_tab.py` | Removed `project_legacy()` bridge call |
| `tests/jsdom_stub.js` | Added `insertBefore()`, pre-seeded stage/container DOM tree |
| `tests/test_display_js.py` | 8 new v2-specific test cases added |

---

## New Engine Functions (display.js)

| Function | Purpose |
|----------|---------|
| `_resolveLength(val, canvasExtent)` | Resolves `"50%"`, `"960px"`, or bare numbers to pixels on the 1920×1080 design canvas |
| `_computePosition(pos, w, h, cW, cH)` | Applies all 10 anchor keywords + explicit corner placement from spec §4.3 |
| `_isNewContainers(ct)` | Detects v2 array containers vs. v1 nested dict containers |
| `themeContainer(theme, name)` | Looks up a container by `id` from v2 `containers[]` array (falls back to dict for v1) |
| `_getContainerBlocks(c)` | Extracts `text/reference/translation/verse_num/body` from v2 `blocks` or v1 flat keys |
| `applyCanvasFit(canvas)` | Applies CSS `scale()` transform to `#stage` for `canvas.fit: "contain"` |
| `applyTheme(theme, slideFormat)` | Main entry — dispatches single-container or multi-container path, positions blocks, applies form/decoration |
| `resetTheme()` | Resets all container inline styles and restores canonical DOM child order |
| `_renderMultiContainers(data)` | Creates dynamic `.rc-dynamic-container` divs on `#stage` for ≥2-container themes |
| `_resolveSlotDef(slot, registry)` | Resolves an animation slot name → definition object |
| `_playElementAnimation(el, def)` | Runs WAAPI `element.animate()` with keyframe mapping |
| `_runAnimation(data, phase)` | Per-container animation dispatch using v2 structure |
| `_runExitAnimation(cb)` | Reads exit animation from containers and fires callback on completion |

---

## Architecture: Two Rendering Paths

### Path A — Single-container (v1 or v2 with one visible container)
Uses the original `#container → #verse-content → [#verse-text, #verse-ref]` DOM.  
`applyTheme()` applies CSS custom properties from the v2 block params and form params.

### Path B — Multi-container (v2 with ≥2 visible containers)
`_renderMultiContainers()` hides `#container` and creates `div#rc-cont-{id}` elements appended directly to `#stage`.  
Each container gets its own block stack rendered from `container.blocks`.  
Z-index is derived from `container.layer`.

---

## Block Position Rendering

| Block | Mechanism |
|-------|-----------|
| `reference.position: "above_verse"` | `insertBefore(vRef, vText)` — ref DOM node moves above text |
| `reference.position: "below_verse"` | `appendChild(vRef)` — ref stays below (default) |
| `translation.position: "left_of_reference"` | `insertBefore(vTr, vRefText)` inside `#verse-ref` |
| `translation.position: "right_of_reference"` | `appendChild(vTr)` after ref text (default) |
| `translation.position: "above_verse"` | `insertBefore(vTr, vText)` before the verse text node |
| `translation.position: "above_reference"` | `insertBefore(vTr, vRef)` just above the ref line |
| `translation.position: "below_reference"` | `appendChild(vTr)` after ref block |

---

## DOM Pre-seeding in jsdom Stub

The test stub (`tests/jsdom_stub.js`) now pre-seeds:

```
#stage
  └── #container
        └── #verse-content
              ├── #verse-text
              └── #verse-ref
                    ├── #verse-ref-text
                    └── #verse-ref-translation
```

Both `appendChild` and `insertBefore` are implemented and track `parentElement` correctly.

---

## Tests Added (test_display_js.py)

| Test | What it covers |
|------|----------------|
| `test_v2_position_anchors_and_keywords` | All 10 anchor keywords + 1 explicit corner |
| `test_v2_percentage_math` | `_resolveLength` with `%`, `px`, bare numbers |
| `test_v2_theme_container_and_blocks_resolution` | v2 `themeContainer` + `_getContainerBlocks` |
| `test_v2_reference_and_translation_placement` | DOM reordering via `r.position`/`tr.position` |
| `test_v2_block_visibility_toggles` | `visible: false` on text/reference/translation |
| `test_v2_multi_container_payload_rendering` | 2-container payload → `.rc-dynamic-container` with z-index/positions |
| `test_v2_canvas_fit_scaling` | `canvas.fit: "contain"` → `scale(0.5)` on `#stage` |
| `test_v2_animation_slot_resolution_and_keyframes` | `_resolveSlotDef` correctness |

---

## Phase 3 Gate Tests — Final Status

| Test file | Count | Result |
|-----------|-------|--------|
| `tests/test_display_js.py` | 38 | ✅ All pass |
| `tests/test_display_render_matrix.py` | 12 | ✅ All pass |
| `tests/test_display_deck_formats.py` | 7 | ✅ All pass |
| `tests/test_theme_switch.py` | 12 | ✅ All pass |
| `tests/test_theme_v2_animations.py` | — | ✅ All pass |
| `tests/test_theme_v2_designer_roundtrip.py` | — | ✅ All pass |
| `tests/test_theme_v2_migration.py` | — | ✅ All pass |
| `tests/test_theme_v2_positions.py` | — | ✅ All pass |
| `tests/test_theme_v2_schema.py` | — | ✅ All pass |
| `tests/test_theme_v2_security.py` | — | ✅ All pass |
| `tests/test_theme_v2_shared.py` | — | ✅ All pass |
| `tests/test_phase7_display.py` | 6 | ✅ All pass |
| **Total** | **453** | ✅ **All pass** |

---

## Bridge Removal

`project_legacy()` was the Phase-2 shim that projected v2 theme dicts into old CSS-var-only dicts for the renderer. It has been removed from:

- `ui/tabs/presentation_tab.py` (payload builder)
- `ui/tabs/slides_tab.py` (slide payload builder)
- `ui/widgets/display_view.py` `apply_theme()` (Python-side display widget)

The function still exists in `core/theme_compat.py` and its tests pass, but it is no longer called by any payload path.

---

## What Phase 4 Will Do

1. **Convert shipped themes to v2 on disk** — `themes/freeform/slides.json` and the 5 scripture themes under `themes/scripture/`
2. **Create `themes/_shared/` files** — `borders.json`, `shadows.json`, `palettes.json`, `animations.json`
3. **Equivalence test** — resolved v1-migrated dict deep-equals resolved v2 file for each shipped theme
4. **Doc updates** — `docs/theme-switch-contract.md`, `docs/theme_designer_spec.md`, `docs/display_and_broadcast.md`, `docs/outline-rendering.md`
5. **Screenshots** — `docs/screenshots/theme_v2/` per theme at 1920×1080

---

## Build Scripts (Canonical — Do Not Edit display_view.py Directly)

| Script | Purpose |
|--------|---------|
| `/home/itorousa/.gemini/antigravity/brain/74ff3fcb-7562-499e-8c18-69c7c3326bff/scratch/build_display_js.py` | Regenerates `display/display.js` from `top_block + shared_block + bottom_block` |
| `/home/itorousa/.gemini/antigravity/brain/74ff3fcb-7562-499e-8c18-69c7c3326bff/scratch/update_display_view.py` | Regenerates `ui/widgets/display_view.py` by inlining `display.js` into `_DISPLAY_HTML` |

> [!IMPORTANT]
> `display/display.js` and the embedded copy in `ui/widgets/display_view.py` must remain byte-identical on all shared functions. The test `test_renderer_copies_agree_on_reset_list` and `test_reset_covers_every_theme_variable` enforce this. Always run both scripts together.

