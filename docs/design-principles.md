# RhemaCast Design Principles

Normative law for all future work. A patch is done only when it satisfies
these principles by construction — never by "works on my machine".

## P1 — Every visible change is a theme switch

Switching from deck to scripture to image to video to pptx is **one
primitive**: `switch(content, theme)`. Tabs, panels, queues, and menus are
frontend organization only — they **own no transition logic**. All
transition logic lives in the single switch choke point defined by
`docs/theme-switch-contract.md`.

Consequences:

- No tab builds its own display payload. Tabs supply *content + theme
  selection*; the choke point builds the payload.
- No tab keeps a private theme namespace that another tab must know
  about. Per-output theme resolution lives in exactly one place.
- Adding a media kind (image, video, pptx) means registering a content
  renderer under the existing three-step switch — never a new broadcast
  path, never a new tab-owned payload builder.

## P2 — Absolute method

Correctness must derive from construction, never from timing, machine
state, or platform behavior:

1. **Platform branches live in exactly one module** (`core/platform.py`).
   No `sys.platform` / `os.name` checks anywhere else. Ever.
2. **No silent `None` crosses a boundary.** Every lookup miss falls back
   to a known-good default *and* warns loudly (log + startup report).
   A missing theme, font, device, or GPU degrades visibly, never
   invisibly.
3. **No duplicated logic copies.** One source of truth per behavior; any
   second copy is generated from the first or deleted. (Known violation
   in force: the two `resetTheme`/`applyTheme` JS copies — see contract.)
4. **Timing never determines state.** Animations, throttles, and async
   round-trips may delay *presentation*; the *state* after a switch is a
   pure function of the payload. Re-applying a payload is idempotent;
   A→B→A converges exactly (see contract § Convergence).
5. **Metric-driven, not pixel-driven.** No hardcoded px/pt conversions
   (e.g. 96dpi assumptions), no `+2px` fudge factors without a named
   reason, no fixed row heights that ignore DPI. Sizes derive from
   `QFontMetrics` + device metrics with explicit margins.

## Same-theme vs theme-to-theme switching

Both go through the identical three-step switch (reset → apply →
render); there is no fast path that skips the reset:

- **Same-theme switch** (verse → verse, slide → slide): full payload,
  full reset, full apply. The cost is one redundant style write —
  negligible next to a WebEngine round-trip — and it buys freedom from
  an entire class of "sometimes stale" bugs. Optimization here means
  making the three steps *cheap*, never skipping one.
- **Theme-to-theme switch** (deck → scripture, etc.): same three steps
  with different `theme_data`. Because the reset is unconditional, the
  previous theme cannot leak by construction.

## Environment expectations + robust fallback

Reliability is 100% **provided the environment is as expected**. The
application therefore verifies its expectations at startup and degrades
in the open when they are not met:

- Expected: configured theme names resolve, theme files parse, fonts
  registered, displays reachable. Verified by `core/startup_checks.py`.
- Not as expected: fall back to known-good defaults (`"default"` theme,
  system fonts, CPU paths) **and say so** — log error + startup report
  + operator-visible notice where the degradation affects output.
- Rule of thumb: if a fallback fired silently, that is a bug in the
  fallback, not good robustness.

## Patch checklist (review gate)

Every patch must answer yes to all of these:

- [ ] Does the visible change go through the switch choke point, or add
  a second path? (Second path: reject.)
- [ ] Does it add a `sys.platform` branch outside `core/platform.py`?
  (Yes: reject.)
- [ ] Can any value be `None`/missing at a boundary without fallback +
  warning? (Yes: reject.)
- [ ] Does correctness depend on timing, focus state, animation order,
  or message arrival order? (Yes: reject — make the payload
  self-contained instead.)
- [ ] Does it duplicate logic that exists elsewhere? (Yes: unify or
  generate.)
- [ ] Does it hardcode pixels, DPI, font names, or paths? (Yes: derive
  or centralize.)
- [ ] Is there a test pinning the contract it touches? (No: add one.)
