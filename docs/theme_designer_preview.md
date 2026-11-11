# Theme Designer preview and animation replay

## Findings (M1-20 investigation)

These findings were established before the implementation.

1. **The preview is already a real QtWebEngine renderer.** `ThemePreview`
   owns one `DisplayView(live_mode=False)`, which loads the display HTML
   through `setHtml()` and contains the same renderer as
   `display/display.js`. A theme/payload is handed to the page with
   `DisplayView.display_verse()`. There is no separate preview renderer and
   no per-edit view.

2. **A theme edit does not re-trigger an animation.** The renderer's
   `handlePayload()` computes `phase` from the difference between the previous
   and next content: the first payload gets `entry`, later different content
   gets `in`, and identical content gets `null`. `ThemePreview.apply_theme()`
   always sends the same sample text, so every font/colour edit reaches the
   renderer as identical content and deliberately runs no entry. This is the
   correct behavior for style edits, but there was no explicit path for the
   Designer to ask for an entry, transition-in, transition-out or exit replay.
   In addition, `AnimationPanel` connected every phase card's `replay` signal
   to `lambda _v: None`, so the Stage 3 replay button never did anything.

3. **The sample injector changes state but not the preview.** The tab's
   `_on_sample_changed()` only calls `ThemePreview.set_verse()`. That method
   assigned `_verse_key` and returned; it never built a payload or called the
   renderer. Stage 2 proved the state changed, not that the screen changed.

4. **Style-only updates can be applied without a phase.** The renderer already
   has `applyTheme(theme)`; `DisplayView.apply_theme()` invokes it directly.
   The Designer preview did not use it. The manager uses a dedicated
   `ThemePreview.apply_theme_in_place()` for non-animation edits, which calls
   `DisplayView.apply_theme()` and therefore leaves the phase engine alone.
   This keeps the theme's unknown keys in the Designer document untouched:
   the preview receives a resolved copy to display and never writes back.

5. **The renderer exposed no test-visible animation state.** Animation was
   observable only through the Web Animations API from an external harness,
   which is awkward for a live QWebEngineView. The renderer now publishes
   `window.__rcPreviewState` and a `previewReplay(phase, current, alternate)`
   entry point. The state records the phase, whether it is running/finished,
   and how many element animations were started, so tests can prove a phase
   ran or was skipped without screenshots.

## What the manager does

`ui/theme_kit/preview_manager.py` is the single owner of replay decisions.
The tab forwards document changes to it and the preview remains a read-only
consumer.

- **Non-animation paths** (`font`, `size`, colour, spacing, geometry, …) call
  `ThemePreview.apply_theme_in_place()` immediately. No phase is requested.
- **Animation paths** call `apply_theme_in_place()` and schedule exactly one
  phase after the last change. The debounce is 300 ms.
- Path classification covers per-container animation slots and block slots
  (`containers[i].blocks.<block>.animation`), plus named animation-library
  edits by finding which slot uses the definition.
- **Split** edits map to the entry phase, because a split is an entry-keyframe
  concept.
- The phase-card replay button calls the same scheduler.

### Phase loop

When focus is inside the animation panel and the relevant phase was just
edited, the manager replays that phase every **3 seconds** until one of these
happens:

- focus leaves the animation panel,
- a non-animation property is edited,
- the tab is hidden,
- the window/application is inactive,
- the tab is closed.

Re-entering a field without editing it does not start a loop. The loop is
implemented with one `QTimer`; timers are stopped while invisible or inactive.

The loop is intentionally short and obvious:

- **Entry:** the current sample replays its entry on the current content.
- **Transition in:** the alternate sample is placed first, then the current
  sample animates in. The current sample is left on screen.
- **Transition out:** the current sample animates out to the alternate sample,
  then the selected sample is restored without an entry.
- **Exit:** the current sample plays its exit, then the selected sample is
  restored without an entry.

### Sample swaps

Choosing a sample calls `ThemePreview.show_sample()`, which sends a new
content payload through the normal renderer. The renderer's normal
content-change transition plays (if the theme defines one). The manager stops
the replay loop and cancels pending replay work first, so sample selection is
not mistaken for an animation edit. This is deliberate: it gives immediate
visual confirmation that the injector now changes the screen and matches what
the display does for a real verse change.

## Defaults and configuration

Both timings are constants in `core/constants.py`:

| Constant | Value | Purpose |
| --- | --- | --- |
| `THEME_PREVIEW_REPLAY_DEBOUNCE_MS` | `300` | Wait after the last animation edit before replaying. |
| `THEME_PREVIEW_REPLAY_LOOP_MS` | `3000` | Repeat interval while an animation field keeps focus. |

There is no new settings UI for these two values; they are Designer timing
constants next to the other preview/runtime constants.

## Verification and limits

- Manager state-machine tests use a fake preview and do not require
  WebEngine: debounce, phase mapping, focus loop, blur, hidden tab, inactive
  window, sample cancellation and shutdown. The block-target test writes
  `containers[0].blocks.text.animation` without touching the container slot.
- Renderer tests use the existing headless-Chrome harness and read
  `window.__rcPreviewState`; they prove entry, transition-in,
  transition-out and exit ran, and that a style-only update did not. The
  page state is the assertion, not screenshots.
- The nine relevant suites passed on this machine: **135 passed**, including
  the new preview manager, block-target and renderer tests.
- The real display was exercised with `DISPLAY=:1` and
  `QT_QPA_PLATFORM=xcb` using the shipped `fullscreen_rise` theme. The window
  was activated programmatically because this X session has no window
  manager; focus landed on a real animation `_ValueEdit`. A font-size edit
  left the phase token unchanged, entry/transition-in/transition-out/exit
  each reported the expected page phase, the focused entry field repeated
  while idle, blur stopped it, and all four samples rendered their own text
  (shortest, medium, longest and freeform).
- This real-display run used no `--disable-gpu` or harness-only Chromium
  flags. The WebEngine-heavy full-app smoke test remains excluded from
  headless runs because QtWebEngine aborts during teardown.
- **Windows was not run on this machine.** The implementation uses only the
  bundled QtWebEngine and renderer; it does not add `--disable-gpu` or any
  platform-specific flag. Windows therefore needs the same QtWebEngine
  runtime as the rest of the app, with GPU acceleration enabled. High-DPI
  scaling was not separately exercised; the renderer's existing viewport
  behaviour is unchanged.
