# Transition pairing bug: scripture to scripture played OUT/IN

Date: 2026-11-13
Scope: live display pairing for scripture to scripture, both renderer copies,
the WebSocket boundary and the Python motion model.
Status: fixed, regression tests added, real-page reproduction and post-fix
check completed.

## Decisions for you

1. **Keep the strict label contract.** Every live sender must set `kind`. The
   server stamps `other` and logs a warning when one is missing. The
   alternative is inferring kind from `content` inside `sanitize_payload()`,
   which would hide sender bugs again. Confirm strict labelling is the
   contract you want.
2. **Accept `kind_missing` on the wire.** An unlabelled display payload now
   carries `kind="other"` plus `kind_missing: true`. The flag is diagnostic
   only and is ignored for rendering. Confirm an extra boolean in the OBS
   payload is acceptable.
3. **Accept the visible legacy behaviour.** An unlabelled payload now plays
   OUT/IN and shows `UNLABELLED` in the `?debug=1` readout. Any third-party
   sender that relied on the old silent scripture default will change
   behaviour. Confirm there is no such sender.
4. **Keep zero animation for slotless themes.** A scripture pair on a theme
   with no transition slots swaps instantly. No fallback to OUT/IN was added.
   Confirm this is the intended authoring contract.
5. **Decide whether the real-page harness should be checked in.** The harness
   used here lives in `/tmp/opencode/rc_e2e/` and is not part of the repo. A
   checked-in version would catch this class of boundary bug earlier.

## Safe to skip

- The two renderer copies are intentionally identical in behaviour. If you
  review one, you can skip the other.
- `windows_update/` and `mobile_version/` contain gitignored build outputs.
  They were not changed.
- `test_fts_search` is a known unrelated failure.
- The `default` theme has no animation slots at all, so its zero-animation
  result is expected, not a missing assertion.
- Most of the push paths share one renderer path. If you accept the renderer
  pairing proof, the per-path table can be skimmed for the kind column only.

## Symptom

Two consecutive scripture pushes played OUT then IN. The expected behaviour is
the transition pair, `transition_out` followed by `transition_in`, which is the
pairing rule for scripture to scripture. The operator saw the container, text,
reference and translation all exit and re-enter instead of the quieter
transition authored by the theme.

## Root cause

Every live sender omitted `kind` from its display payload. At the WebSocket
boundary, `core/websocket_server.py:sanitize_payload()` stamped the missing
label with `kind="other"` so legacy senders would keep rendering. The page then
compared the previous content kind (`other`) with the incoming kind (`other`).
`MotionState._pair_actions()` returns the transition pair only for
`scripture -> scripture`; every other pairing returns OUT/IN. The renderer
executed OUT/IN.

The page's old default, `_currentKind = data.kind || "scripture"`, never helped
on the live path because the boundary had already made `kind` explicit. It was
still wrong for any path that bypasses that boundary, and it contradicted the
settled rule that unlabelled content counts as `other`, so it was corrected to
`"other"` in both renderer copies.

The bug was therefore not in the pairing table. It was in the payloads feeding
that table: no live sender declared what it was sending.

## Reproduction

### Real app path

The harness at `/tmp/opencode/rc_e2e/harness.py` runs the real
`core.websocket_server` handlers, the real `PresentationTab` and `SlidesTab`
methods, the real `DisplayState`, and the real `display/display.html` plus
`display/display.js` in Chrome. It listens on IPv6 `[::1]:8765` (WebSocket) and
`[::1]:8766` (HTTP), because the operator's running app owns the IPv4 ports.

Pre-fix, the queue Show path pushed scripture without a label and the page
planned `out -> in`. Post-fix, the same path pushes `kind="scripture"` and
plans `transition_out -> transition_in`.

Post-fix run, theme `default_quiet`:

| Step | Wire kind | Kinds compared | Plan | Phases actually run |
| --- | --- | --- | --- | --- |
| Prime: queue Show, "Prime verse.", John 3:16 | `scripture` | entry, no pairing | none (entry) | container `entry` (fade_in 1300 ms), text `entry` (quiet_in, 1600 ms), reference `entry` (1000 ms), translation `entry` (900 ms) |
| Push: queue Show, "Alpha beta gamma.", John 11:35 | `scripture` | `scripture -> scripture` | `transition_out`, `transition_in` | text `out` (quiet_out, 700 ms), text `in` (quiet_in, 1600 ms). No container, reference or translation animation |
| Push: unlabelled raw broadcast, "Kindless push.", John 12:1 | `other` (`kind_missing`) | `scripture -> other` | `out`, `in` | container `out` 600 ms, text `out` 700 ms, reference `out` 600 ms, translation `out` 500 ms, then `entry` for the same four elements |

The post-fix page readout after the scripture pair was:

```
state shown | kind scripture
scripture -> scripture
transition_out -> transition_in
```

The final text was `35 Alpha beta gamma.` and there were no console warnings.
The unlabelled push produced the expected warning:

```
RhemaCast display payload has no kind; treating it as other (OUT/IN): [KJV] John 12:1
```

and the readout showed `kind other | UNLABELLED`. The old text bug
`3535reference_framesfirs` (duplicated verse number text on
`reference_frames`) was visible again and is unrelated to pairing. It was not
fixed here.

The real-page slide push was not completed. The harness had no active SLIDES
outputs configured, so `broadcast_tab_payload("SLIDES", ...)` scoped the slide
out and `cloak_other_tabs("SLIDES")` sent `clear` to the scripture output. That
is a harness configuration limit, not a product failure. Slide pairing is
covered by the renderer and push-path tests listed below.

### Per push path

`tests/display_push_paths.py` drives each real tab method with a real
`DisplayState`, captures the per-output payload at
`core.output_router.broadcast_tab_payload`, and records the kind and actions
fed to `DisplayState.motion.push()`. Every path is primed with a live
scripture push, so the compared kinds are `scripture -> scripture` unless the
pushed content is a slide.

| # | Push path | Kind on wire | Pairing | Plan |
| --- | --- | --- | --- | --- |
| 1 | `PresentationTab._on_display_verse` (Queue Show) | `scripture` | scripture -> scripture | transition pair |
| 2 | `PresentationTab._on_browser_broadcast` | `scripture` | scripture -> scripture | transition pair |
| 3 | `PresentationTab._on_translation_broadcast` (lookup) | `scripture` | scripture -> scripture | transition pair |
| 4 | `PresentationTab._on_translation_broadcast` (browser fallback) | `scripture` | scripture -> scripture | transition pair |
| 5 | `PresentationTab._on_navigator_push` | `scripture` | scripture -> scripture | transition pair |
| 6 | `PresentationTab._on_search_to_live` | `scripture` | scripture -> scripture | transition pair |
| 7 | `PresentationTab._on_trans_badge_to_live` | `scripture` | scripture -> scripture | transition pair |
| 8 | `PresentationTab._on_history_verse_double_clicked` | `scripture` | scripture -> scripture | transition pair |
| 9 | `PresentationTab._on_preview_double_click` (rebuild) | `scripture` | scripture -> scripture | transition pair |
| 10 | `PresentationTab._on_preview_double_click` (stored replay) | `scripture` | scripture -> scripture | transition pair |
| 11 | `PresentationTab._on_theme_double_click` | `scripture` | scripture -> scripture | transition pair |
| 12 | `PresentationTab._navigate_to_bible_verse` | `scripture` | scripture -> scripture | transition pair |
| 13 | `PresentationTab._display_schedule_item` | `scripture` | scripture -> scripture | transition pair |
| 14 | `PresentationTab._on_schedule_double_click` | `scripture` | scripture -> scripture | transition pair |
| 15 | `PresentationTab.refresh_display_names` | `scripture` | scripture -> scripture | transition pair |
| 16 | `PresentationTab._uncloak_now` | `scripture` | reveal, no pairing | none |
| 17 | `PresentationTab._apply_slide_display` | `freeform` | scripture -> freeform | OUT/IN |
| 18 | `SlidesTab._show_slide` | `freeform` | scripture -> freeform | OUT/IN |
| 19 | `SlidesTab._show_verse` | `scripture` | scripture -> scripture | transition pair |
| 20 | `SlidesTab._on_preview_double_click` (slide) | `freeform` | scripture -> freeform | OUT/IN |
| 21 | `SlidesTab._on_preview_double_click` (verse rebuild) | `scripture` | scripture -> scripture | transition pair |
| 22 | `SlidesTab._on_preview_double_click` (stored verse replay) | `scripture` | scripture -> scripture | transition pair |
| 23 | `SlidesTab._on_output_theme_double_click` (slide live) | `freeform` | scripture -> freeform | OUT/IN |
| 24 | `SlidesTab._on_output_theme_double_click` (verse live) | `scripture` | scripture -> scripture | transition pair |
| 25 | `SlidesTab.refresh_display_names` (slide live) | `freeform` | scripture -> freeform | OUT/IN |
| 26 | `SlidesTab._uncloak_now` | `scripture` | reveal, no pairing | none |

`tests/test_display_payload_kind.py` asserts the wire kind, the absence of
`kind_missing`, the content type (`verse` or `slide`) and the exact motion
actions for every row. The tests run against the `default` theme, which has no
animation slots, so the phase-level result for all rows on that theme is zero
animations. The renderer phase proof for a theme that does have slots comes
from the real-page run above and from the renderer suites.

## Theme animation inventory

For `themes/scripture/default_quiet.json`, which is the discriminating theme:

| Element | Entry slot | Transition slots | Out slot |
| --- | --- | --- | --- |
| container `main` | `fade_in` 1300 ms, smooth | none | `fade_out` 600 ms |
| block `text` | `quiet_in` | `quiet_out` (out), `quiet_in` (in) | `quiet_out` |
| block `reference` | `fade_in` 1000 ms, delay 320 ms | none | `fade_out` 600 ms |
| block `translation` | `fade_in` 900 ms, delay 520 ms | none | `fade_out` 500 ms |
| block `body` | none | none | none |
| block `verse_num` | none | none | none |

On a verse switch, the transition pair animates only `text`. OUT/IN animates
container, text, reference and translation, which is exactly what the operator
saw. `themes/scripture/default.json` declares no animation slots at all, so
every pairing on that theme is instant.

There is no implicit or default element animation in the renderer:

- `_collectTransitionOut()` returns an empty plan unless a target has
  `animation.transition.out`.
- `_runAnimation("in")` reads only `animation.transition.in`.
- `_collectExit()` and `_runAnimation("entry")` read only `animation.out` and
  `animation.entry`.
- Missing slots return nothing. OUT/IN is never substituted for a transition,
  or the reverse.

The theme's `motion` object only changes ordering (`sequential` or `overlap`),
sustain behaviour and deck steps. It does not change which element animates.

## Candidate causes

| Candidate | How it was tested | Verdict |
| --- | --- | --- |
| Unlabelled payload treated as `other` | Wire capture after `sanitize_payload()`, real-page push, per-path tests | Confirmed root cause. A missing label becomes `other`; `other -> other` is OUT/IN. |
| A push path bypassing the state machine | Enumerated every `"action": "display"` producer and every `publish_live()` call in both tabs; drove each one through its real method | No bypass. All 26 paths route through one of the two `_build_payload` implementations and `DisplayState.publish_live()`. |
| Split or typewriter re-entry | `_runAnimation("in")` only reads `transition.in`; Node no-transition test; Chrome no-transition test | No re-entry. A transition pair on a theme without transition slots runs zero animations. |
| Stale renderer copy or caching | Both renderer copies parametrized in Node and Chrome; `_no_cache_middleware` sets `Cache-Control: no-store` for `.js`, `.css`, `.html`; page reloaded | No stale copy. Both copies carry the same fix and pass the same tests. |
| Theme or container kind interference | `default` (no slots) and `default_quiet` (transition on text only) on the real page; pairing reads payload kind only | No interference. A separate real mismatch was found: `SlidesTab._on_output_theme_double_click` re-broadcast without its display data, so a live slide was relabelled `scripture` on the way to OBS. Fixed. |
| Other | Reviewed `MotionState._pair_actions()`, `DisplayState.publish_live()`, the page display handler and all theme slots used here | No other cause. |

## Fix

1. Both `_build_payload()` implementations label every payload:
   `ui/tabs/presentation_tab.py` uses `scripture`, `freeform` or `other`;
   `ui/tabs/slides_tab.py` uses `scripture` or `freeform`.
2. The Lite Designer preview payload is labelled `freeform`. It renders
   through the same motion model and was the last unlabelled local sender.
3. `core/display_state.py:publish_live()` passes `payload.get("kind") or
   "other"` into `MotionState.push()`.
4. `core/websocket_server.py:sanitize_payload()` keeps stamping `other` for a
   missing or blank kind, adds `kind_missing: true`, and logs a warning with
   the reference. The payload is never dropped.
5. Both renderers now use `_currentKind = data.kind || "other"`. A missing
   label emits `console.warn()`, sets `window.__rcMotionState.unlabelled`, and
   appends `UNLABELLED` to the `?debug=1` readout. A clear resets the flag.
6. `SlidesTab._on_output_theme_double_click()` now passes
   `self._current_display` to `_broadcast_to_ws()`, so a slide stays
   `freeform` when its output theme is changed.
7. No fallback animation was added. No theme is special-cased.

## Tests added

- `tests/display_push_paths.py`: shared stubs, real `DisplayState` capture and
  wire assertions.
- `tests/test_display_payload_kind.py`: 26 push paths plus 2 pairing helpers,
  28 tests. Asserts the wire kind, no `kind_missing`, the content type, and
  the exact model actions. The theme used has no animation slots, so a
  scripture pair has zero renderer work.
- `tests/test_display_js.py`: 3 new tests (6 parametrized cases) covering a
  theme with entry/out but no transition slots: scripture to scripture plays
  nothing, scripture to slide still plays OUT then IN, and an unlabelled
  payload warns and is treated as `other`.
- `tests/test_theme_v2_animation_runtime.py`: a synthetic `no_transition`
  theme driven in headless Chrome. It asserts the transition plan with zero
  authored animations for a scripture pair, then OUT followed by entry for a
  kind change.
- `tests/test_phase7_display.py`: `sanitize_payload()` now also asserts
  `kind_missing` is present for unlabelled display payloads and absent for
  labelled display and clear payloads.
- Existing Chrome runtime driver payloads were labelled `scripture` so they do
  not exercise the unlabelled path by accident.

## Commands and results

All tests:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest tests/ -q
```

Result: see the final counts below.

Targeted suites:

```bash
QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest \
  tests/test_motion_state.py \
  tests/test_display_motion_state.py \
  tests/test_display_js.py \
  tests/test_display_payload_kind.py \
  tests/test_display_render_matrix.py \
  tests/test_display_step_and_push.py \
  tests/test_display_deck_formats.py \
  tests/test_phase7_display.py \
  tests/test_theme_v2_schema.py \
  tests/test_theme_v2_animations.py \
  tests/test_theme_designer_*.py \
  tests/test_lite_designer_*.py -q
```

Result: `419 passed, 1 skipped, 168 deselected` (the skips and deselections
come from the default `-m "not webengine"` marker).

Per file:

- `tests/test_display_payload_kind.py`: 28 passed.
- `tests/test_display_js.py`: 78 passed.
- `tests/test_theme_v2_animation_runtime.py`: 32 passed.

The bare `pytest -q` from the repo root fails during collection because
`mobile_version/tests/conftest.py` and `windows_update/tests/conftest.py`
collide with `tests/conftest.py` under the same `tests` module name. Those
trees are gitignored build outputs. The documented `pytest tests/` scope avoids
them.

Full suite result: `PENDING`

## Changed files

Fix files:

- `core/websocket_server.py`
- `core/display_state.py` (kind passed into `MotionState.push()`)
- `display/display.js`
- `ui/widgets/display_view.py`
- `ui/tabs/presentation_tab.py`
- `ui/tabs/slides_tab.py`
- `ui/widgets/lite_designer/lite_designer.py`
- `tests/display_push_paths.py` (new)
- `tests/test_display_payload_kind.py` (new)
- `tests/test_display_js.py`
- `tests/test_theme_v2_animation_runtime.py`
- `tests/test_phase7_display.py`
- `docs/transition_pairing_bug.md` (new)

The worktree also contains the uncommitted motion-system work that this fix
builds on, including the rest of `core/motion_state.py`,
`core/display_state.py`, `ui/tabs/presentation_tab.py`,
`ui/tabs/slides_tab.py`, the panels and the Designer. Those changes were not
authored by this fix and were left in place. `windows_update/` and
`mobile_version/` were not changed.

## Unverified

- Real OBS Browser Source. The real-page check used Chrome against the real
  server, not an OBS scene.
- Windows.
- High DPI.
- The slide push on a real page. The harness had no active SLIDES outputs, so
  the router cleared the scripture output instead of delivering the slide.
  The slide pairing is covered by the Node and Chrome runtime tests and by the
  wire/model test for `SlidesTab._show_slide`.
- The operator's currently running app process (PID 74507) was not restarted.
  It still has the old Python modules loaded; the fix takes effect after an
  app restart.
