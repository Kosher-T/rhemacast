# Outline Rendering — Approach

How RhemaCast draws text outlines on the display (OBS `display/display.js`)
and the in-app preview (embedded copy in `ui/widgets/display_view.py`).
The two renderers carry duplicated logic by design; `tests/test_display_js.py`
evaluates both under node and asserts they behave identically, and
`tests/test_slide_edit.py::test_outline_renderers_agree` asserts the Python
parser agrees with them.

## Why outlines are hard in HTML/CSS/JS

CSS offers no outward-only stroke primitive for HTML text:

- `-webkit-text-stroke: Npx` straddles the glyph path — half grows **inward**
  and eats the letterform (past ~3px on body text the word is unreadable),
  and Chromium ignores `stroke-linejoin` for HTML text, so miter joins spike
  at acute angles (A/M/N apexes, commas). Verified: miter/round/bevel render
  identically spiky.
- `paint-order: stroke fill` (stroke first, fill over the inner half =
  outward-only outline) is **SVG-only**. It does not apply to HTML text.
  Note: Chromium applies paint-order *per tspan*, so one `<text>` with many
  tspans still buries earlier words under later strokes at high thickness —
  hence the two `<text>` layers below, not one.
- A ring of hard `text-shadow`s grows outward, but it is offset *copies of
  the filled glyph*, not a band around the path — at high thickness it forms
  a slab that fills counters instead of tracing contours. (Kept as the
  separate `shadow=` feature.)
- Past ~100px stroke widths Chromium's rasterizer itself degrades (arcs,
  spikes, unpainted tiles — worse under SwiftShader than real GPUs). The
  renderer is correct; the pixels are a platform limit. Moderate widths
  (the 1–200px ribbon range) are exact.

Professional tools (Illustrator, Photoshop) convert glyphs to paths first and
stroke the paths with round joins — sidestepping font layout entirely. In a
browser we must keep text as text (wrapping, auto-fit, selection), so the
approach below re-derives paths at render time instead.

## The approach: per-line inline SVG, measured from layout

For every outlined scope (an inline `[text (outline=Npx #hex)]` run, or the
whole verse for a deck/theme-level outline), after layout:

1. **Walk** all descendant text nodes with a `TreeWalker`.
2. **Split into rendered lines** with per-character `Range.getBoundingClientRect()`
   (1px tolerance for subpixel jitter). The browser did the wrapping, so the
   split is correct by construction — including `break-word` splits.
3. **Measure** each line fragment with canvas ink metrics
   (`actualBoundingBoxAscent/Descent`) in the fragment's own computed font.
   Spacing rides explicit x positions, one `<tspan>` per word (spaces become
   pure advances, never painted glyphs): negative `letter-spacing` on SVG
   text collapses spaces outright, so the attribute is never set there.
   Letter-spacing folds into the advance math instead (per-character sums
   when nonzero, matching how layout breaks shaping; whole-word shaped
   measurement when zero, keeping kerning/ligatures).
4. **Rebuild** the scope as one inline `<svg>` per rendered line: **two**
   `<text>` layers — all strokes first (`fill="none"`), then all fills
   (`stroke="none"`) — with `stroke-width = 2 × N`, `stroke-linejoin/linecap
   round`. Half the stroke hides under the fill; the visible N px grow
   strictly outward with rounded corners, and each letter's outline ends up
   behind its neighbours' fills.
5. Each line SVG viewport is **padded by N px on every side** with a tight
   ink-height box dropped by the descent, so the stroke is never clipped into
   a box and the drawn baseline lands exactly on the parent baseline
   (verified pixel-identical layout with and without outline). A positive
   `vertical-align` would grow every line; the drop keeps line rhythm intact.
   As belt and braces the line SVGs also carry `overflow: visible`: the
   viewport sizes layout, but paint must never clip — a few px of raster
   reality (hinting, rounding, font-metric gaps) can exceed the measured ink
   box, and without this the glyph tops slice flat (visible even at 2px).

Width/color travel as `data-rc-oc-w/c` attributes (no cross-file contract);
conversion is cached per scope and re-runs after auto-fit, on
`document.fonts.ready` (webfonts change metrics), on resize, and on theme
changes. Without layout (tests, print) scopes are left as readable HTML and
no outline paints — the function returns false before touching the DOM, and
callers retry on the next pass.

## Ordering contract (hard-won)

Conversion must run **only post-theme, post-layout, post-unhide**:

- Converting before the theme applies measures stale metrics, and the
  success path strips markers — so a later correct pass can never redo it.
  The premature call after `innerHTML` was removed for exactly this reason;
  conversion lives at the end of `autoFitText` (which always follows, once
  visible), on `fonts.ready`, and after theme changes.
- `autoFitText` measures **pristine** text: `invalidateOutlines()` restores
  pre-conversion markup first, otherwise it would fit the padded SVGs and
  over-shrink. Conversion stashes pristine HTML per scope (markers included)
  so theme-only changes (which carry no fresh text) can restore and rebuild.
 - Fidelity guard: per-line rebuilt advance must agree with laid-out ink
  within tolerance, or conversion bails leaving readable HTML. Conversion
  must never render worse than plain text.
- Post-conversion fit: auto-fit measures pristine text, so a thick outline's
  padding would overflow the container (clipping tops first under
  bottom-anchored flex). After converting, `fitOutlineLayers` shrinks
  geometrically to the theme min size (bounded iterations, always
  terminates) until the padded content fits.
- Scale normalization: the preview scales its DOM to fit the panel, so
  `getBoundingClientRect` speaks scaled px while canvas and computed styles
  speak unscaled px. Rects are divided by the measured scale
  (`getBoundingClientRect().width / offsetWidth` of the block) before any
  comparison — without this the fidelity guard trips permanently in the
  preview and nothing ever converts there.

## Contracts

- Stored value: `"Npx #rrggbb"` (deck format line, inline run, theme
  `text_outline`), legacy bare `"#rrggbb"` (= 1px), `"none"`/`"off"` for an
  explicit off that beats an inherited outline. Case-insensitive everywhere
  (Python `re.IGNORECASE`, JS `/i`); 3-digit hex normalizes to 6-digit.
  Bounds `OUTLINE_MIN_PX..OUTLINE_MAX_PX` (1..12) and the shadow size/distance
  bounds live in `core/constants.py`; the JS literal bounds are pinned to
  them by `test_outline_width_bounds_match_core_constants`. Over-max stored
  values **clamp** to the max (old decks keep rendering); the ribbon spins
  cannot enter more than the max.
 - `outline=` (uniform band, follows the path) vs `shadow=` (one blurred,
  offset copy: `shadow=<size> <opacity> <distance> <color> <angle>`, e.g.
  `shadow=10px 45% 8px #ff3366 135`, degrees with 0 = east, 90 = south;
  `size` is the blur radius, distance 0 reads as an outer glow). An older
  build stamped a ring of filled glyph copies, which read as stacked
  letter shapes instead of a shadow; the single-shadow form replaced it.
  Opacity maps linearly for now (an s-curve pass is parked until the new
  implementation beds in). Separate ribbon controls for each. The ribbon exposes
  exactly two outline knobs (thickness spin + color) and five shadow knobs
  (size, opacity, distance, angle spins + color); colors come from an inline
  swatch grid + hex field, never a modal dialog (the designer is a Popup and
  a modal `QColorDialog` deactivates + closes it on every click).
- Theme `text_outline` and deck `outline=` are the same knob: the deck
  broadens/overrides, `outline=none` switches the theme's off. A legacy hard
  `text_shadow` (zero blur, one color) converts to an outline value; real
  drop shadows (blur, mixed colors) stay shadows.
- Outline and shadow compose: a run may carry both.

## Known limitations (honest)

 - The max is 12px because past it every renderer degrades: counters close,
  neighbours merge, and past ~100px stroke widths Chromium's rasterizer adds
  its own arcs and spikes (verified in isolation; worse under SwiftShader
  than real GPUs). Shape-following is exact through the whole 1-12 range,
  verified per value with vertical extents logged.
- `<sup>`/`<sub>` inside an outlined scope skip conversion (flattening would
  drop the raise); exotic (non-inline) boxes bail out the same way.
- Webfont arrival changes metrics: conversion re-runs on `fonts.ready`, so
  the first paint may briefly show un-outlined text.
- SVG `<text>` selection/copy across tspan boundaries is clumsier than HTML
  text selection. Acceptable for a display overlay.
