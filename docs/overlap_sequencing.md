# Overlap sequencing for motion.in_out and motion.transition

> Update (13 November 2026): the offset is now a per-theme setting,
> `motion.overlap_in_offset_ms` (0 to 2000 ms, default 200), with a Designer
> field. `OVERLAP_IN_OFFSET_MS` remains the default and the renderer fallback.
> See `docs/theme_file_reference.md` §3.4.

## Decisions for you

1. **Timing source.** The incoming start offset is one platform constant,
   `OVERLAP_IN_OFFSET_MS = 200` in `core/constants.py`, generated into
   `display/animation_defaults.js` as `RC_ANIM_DEFAULTS.overlap_in_offset_ms`.
   It is not a theme property. A per-theme value later is a validator field
   plus one read in `_overlapOffset()`, not a new plan shape.
2. **Layer mechanism.** The outgoing content is a frozen deep clone of
   `#stage`, appended inside `#stage` with `z-index: -1` and removed at the
   end of the pair. I chose this over retargeting the live nodes because the
   incoming content must occupy the same containers and would otherwise
   overwrite the outgoing text before it finished leaving.
3. **Hidden until the offset.** The incoming content renders immediately but
   its containers stay hidden until the offset, then it animates live. This
   avoids depending on each animation's first keyframe to hide the incoming
   content (a slide preset has no opacity keyframe).
4. **Sequential fallback.** Missing outgoing slots, v1 themes and reduced
   motion all take the existing sequential path, so the stage never blanks
   and no fallback animation is invented.
5. **Debug readout is display-only plus preview parity.** `?debug=1` prints
   the offset and both layers. Nothing renders without the query string.

## Safe to skip

- Real OBS output, Windows rendering, high DPI scaling and pixel-level frames
  are unverified. The headless Chrome harness asserts plan, timing and layer
  state, not painted pixels.
- The full-suite count in `docs/transition_pairing_bug.md` (line 290) is still
  PENDING; this report includes only the suites named under Tests.

## What the code does now

**State machine (`core/motion_state.py`).** Overlap is one action for the
pair, so renderers that do not implement layering still have one ordered
decision to consume:

```json
{"action": "pair", "first": "transition_out", "second": "transition_in",
 "order": "overlap", "offset_ms": 200}
```

`first` starts at t=0, `second` starts `offset_ms` later. Sequential still
returns two actions, `{"action": first}` then `{"action": second}`, exactly as
before. The pairing table is unchanged: scripture to scripture reads
`motion.transition`, every other pairing reads `motion.in_out`, and an
unlabelled payload is `other`.

**Renderer (`display/display.js` and the embedded copy in
`ui/widgets/display_view.py`, kept in step).** On a content change whose
pairing mode is `overlap`:

1. Resolve the outgoing plan from the old theme (`_collectTransitionOut` or
   `_collectExit`, unchanged).
2. Snapshot the root `--rc-*` custom properties, mark the outgoing targets,
   deep-clone `#stage`, then remove the markers from the live DOM. The clone
   stays detached so `resetTheme()` cannot drop it.
3. Render the incoming content silently: no sustain, no `shown` state, and no
   animation yet. `_prevPayload` and `_currentKind` are set here, so a push
   during the overlap diffs against what is already on screen.
4. Attach the clone inside `#stage`: `position: absolute` at 0,0,
   `transform: none` (the live stage's canvas-fit transform already applies to
   the ancestor), `pointer-events: none`, `z-index: -1`, plus the frozen
   `--rc-*` values. `#stage` uses `isolation: isolate` so the clone paints
   above the stage background and below the incoming content.
5. Play the outgoing plan on the clone targets at t=0, then hide the live
   containers.
6. At the offset, show the live containers and run the incoming phase through
   the existing `_runAnimation` (so split and typewriter behave exactly as in
   sequential). Cleanup runs at
   `max(outgoing duration, offset + incoming duration)`, removes the clone,
   settles to `shown`, and starts sustain.

The sequential branch is untouched apart from the plan gaining `order` and
`offset_ms` fields.

**Offset choice.** 200 ms is one third of the 600 ms default animation. The
outgoing move reads as a distinct start before the incoming begins, and a
default pair completes in about 800 ms instead of the 1200 ms sequential sum.
It is carried in the plan, so tests and the debug readout use the same value
the renderer uses.

**Missing slots.** No outgoing animation means the incoming phase starts at 0
and the old content is replaced immediately, which is the authored meaning of
a missing phase. No incoming animation means the new content appears at the
offset and the outgoing clone holds its final keyframe until cleanup.

## Preserved interactions

- **Cloak** is still instant: `_cancelAllAnimations()` removes the clone and
  its timers, then the stage and containers are hidden. Cloak mid-overlap
  remembers `shown`.
- **Push during an overlap** cancels the clone and both timers, restores the
  live containers, and starts a fresh pair from what is on screen.
- **Out** holds its final keyframe as before; an Out during an overlap
  cancels the layer first.
- **In while cloaked** is a no-op in both the state machine and the renderer.
- **Missing slots** stay instant with no cross-slot fallback.
- **prefers-reduced-motion** reports `order: "sequential"`, `offset_ms: 0` and
  swaps instantly with no layer.
- **Sustain** starts only after the pair's full duration, never at the
  incoming animation start.

## Files changed

- `core/constants.py`: `OVERLAP_IN_OFFSET_MS = 200` (carried from the earlier
  pass on this task).
- `core/animation_registry.py`: `runtime_defaults()` carries
  `overlap_in_offset_ms` (carried from the earlier pass).
- `display/animation_defaults.js`: regenerated from the registry.
- `core/motion_state.py`: overlap docstring and `offset_ms` in the pair action
  (carried from the earlier pass).
- `core/theme_schema.py`: removed the "not supported yet" warning.
- `display/display.js`: overlap layer, offset timers, plan fields,
  `?debug=1` readout, `.rc-overlap-layer` exclusion from container hiding.
- `ui/widgets/display_view.py`: the same renderer changes plus CSS isolation
  for the preview copy.
- `display/themes.css`: `isolation: isolate` on `#stage`.
- `ui/widgets/theme_designer/animation_panel.py`: Overlap labels and the
  informational note naming the 200 ms offset.
- `tests/test_motion_state.py`: every pairing in both modes, interrupted
  overlap, cloak and out mid-overlap, offset constant, no schema warning.
- `tests/test_display_js.py`: plan shape and offset in both renderer copies.
- `tests/test_theme_v2_animation_runtime.py`: headless Chrome overlap offsets,
  layer presence and removal, debug readout, reduced motion, and proof the
  sequential plan and timings are unchanged.
- `tests/test_theme_designer_stage3.py`: Motion note assertions.
- `docs/theme_file_reference.md`, `docs/theme_designer_preview.md`: motion
  contract and Designer copy.

## Tests run

Command: `QT_QPA_PLATFORM=offscreen PYTHONPATH=. venv/bin/python -m pytest`
with `-m "not webengine"`.

| Suite | Result |
|---|---|
| `tests/test_motion_state.py` | 52 passed |
| `tests/test_display_motion_state.py` | 5 passed |
| `tests/test_display_payload_kind.py` | 28 passed, 2 unrelated warnings |
| `tests/test_theme_v2_schema.py` | 35 passed |
| `tests/test_theme_v2_animations.py` | 86 passed |
| `tests/test_display_js.py` | 80 passed |
| `tests/test_theme_designer_stage3.py` | 13 passed |
| `tests/test_theme_designer_preview_renderer.py` | 2 passed |
| `tests/test_theme_v2_animation_runtime.py` | 38 passed |

Total: 339 passed, 0 failed.

The Chrome harness now inlines `display/animation_defaults.js` into its temp
page. The temp page could not resolve the relative script src, so
`RC_ANIM_DEFAULTS` was undefined in every earlier headless run; tests passed
only because they used explicit durations. The offset read needs the real
defaults, so the harness now matches the shipped OBS page.

The overlap tests assert: the outgoing animation starts under 150 ms on the
clone; the incoming animation starts within 50 ms of the 200 ms offset on the
live DOM; the clone is absent in sequential mode; sequential still starts the
incoming phase only after the 300 ms outgoing phase in the test theme; and
`prefers-reduced-motion` produces no layer and no animations.

The known unrelated failure `test_fts_search` was not part of these suites and
was not run. No other failures appeared in the suites above.

## Unverified

- Real OBS browser source output.
- Windows rendering and high DPI.
- Pixel output at any stage of the overlap (the harness reads plan, DOM layer
  state and animation start times, not frames).
- Interrupting an overlap mid-incoming animation freezes the clone from the
  resting styles, not the interpolated frame, because WAAPI frames are not
  reflected in inline styles. The visual jump is not measured.
