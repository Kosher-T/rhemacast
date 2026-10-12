# Lite Designer — Plan

> BUILD STATUS (2026-09-11): v1 implemented and green (183 passed + 1 xpassed,
> `test_phase9_ui` excluded per repo convention). Format Tier 0/1/1.5 live in
> parser + both JS renderers + `themes.css`; `ui/widgets/lite_designer/`
> ships shell + ribbon + cards + converters; deck menu → Edit… and theme
> Quick Edit → LiteDesigner wired; tab rules (§9) implemented. Cut per
> decisions: table/shapes pickers, links. Known inherited issue found en
> route: theme files can lose unmanaged keys on designer save
> (`fullscreen.json` lost `text_transform`/`text_align` — restored by hand;
> the shared `ThemePropertiesPanel` rebuild is the suspect, still open).

One popup form, two TABS (decided — see §9). Built on top of the current
quick-editor shell (`ui/widgets/theme_quick_editor.py`: 1280×720 frameless
dark rounded popup, ✨ title bar + name badge, Reset / Save / ×, body below
the title bar). Nothing about that shell changes — only what lives inside the
body changes per tab.

- **Theme tab** (default when opened from a theme context menu / Quick Edit):
  exactly today's look. Properties panel left, live preview right.
- **Freeform tab** (default when opened from a deck context menu, later also
  from schedule items): word processor. Ribbon toolbar on top, slide texts in
  the middle, live preview right. This plan is mostly about the Freeform tab.

## 1. Layout (Freeform tab)

Tab bar sits directly under the title bar: `[ Freeform | Theme ]`.
Entry point sets the default tab and availability (full rules in §9).

```
┌ Title bar (existing): ✨ Lite Designer [Deck Title badge]   Reset Save × ┐
├ Tab bar: [ Freeform | Theme ] ──────────────────────────────────────────┤
├ Ribbon toolbar (word-processor strip, ~64px, two rows max) ─────────────┤
│ Row 1 (always visible): font combo · size combo · B I S (strikethrough) │
│         · U · outline toggle · color swatch · clear-formatting · undo redo│
│ Row 2 (collapsible "¶" section): alignment · spacing · bullets · numbers │
│         super/sub · case · RTL/LTR · hr                                  │
│         (NO table/shapes pickers — cut until image-payload rendering, §3)│
├ Body ───────────────────────────────────────────────────────────────────┤
│ Slide column (scroll, ~420px)          │ Preview (flex, existing widget) │
│ ┌ slide card ─────────────────────┐    │                                 │
│ │ [Section chip  ] [title…      ] │    │   ThemePreview (reuse as-is)    │
│ │ rich text editor                │    │   re-rendered debounced 150ms   │
│ └───────────────────────────────┘    │                                 │
│ ┌ slide card (inactive = static) ┐    │                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

- **Slide card = section chip + title field + rich editor.** Section chip is a
  small pill (`*Verse 1`); clicking it cycles Renames via inline edit — it maps
  to the `*Section` marker. Title field is a single-line input mapping to the
  deck `#Title` (shown once, on the first card, collapsed to a subtitle line on
  the rest). Body maps to slide lines; single Enter = intra-slide break,
  double Enter = split slide here at save time.
- **Only ONE card is a live editor at a time.** The focused card hosts the
  single shared `QTextEdit`; all other cards render static rich text
  (`QLabel` with HTML or `QTextDocument` painted, read-only). Clicking a card
  moves the editor into it, preserving cursor/scroll. This is the core
  lag-free guarantee: N slides cost N labels + 1 editor, not N editors.
- Preview reuses `ThemePreview` unchanged; re-render debounced 150ms after
  the last keystroke, and only the *active* slide re-parses on each keystroke
  (full-deck serialize happens on save / slide-switch only).

## 2. Ribbon details

- **Row 1 always visible (your must-haves):** font family combo, size combo
  with −/+ steppers, **B** **I** **S** (strikethrough), outline toggle,
  text-color swatch (+ hex field), clear-formatting (eraser), undo/redo.
- **Row 2 ("¶ More"):** alignment (left/center/right/justify segmented),
  spacing menu (Single / 1.15 / 1.5 / Double / Custom… → small dialog),
  bullets, numbered list, superscript, subscript, UPPERCASE / lowercase,
  RTL / LTR block direction, horizontal line, Table ▾, Shapes ▾.
- **Table ▾ / Shapes ▾: CUT from v1 entirely** (decided — no pickers, no
  placeholders). They return with Phase-2 image-payload rendering, which is
  the only honest way to persist them. Row 2 ends at the hr button.
- **Shortcuts:** Ctrl+Z undo, Ctrl+Shift+Z redo (QTextDocument default stack —
  just don't fight it), Ctrl+B/I/U. Links skipped entirely in v1.
- **Outline/shadow color picker (decided):** a color swatch for
  outline/shadow color that is VISIBLE ONLY while outline or shadow state is
  on. No outline/shadow → no picker. Toggling outline off hides the picker
  but the last color is remembered; toggling back on restores it. Outline
  on/off + color are per-deck persisted state (see §3 cascade rule).
- Toolbar buttons reflect the text cursor (`cursorPositionChanged` →
  `QTextCharFormat` probe, throttled to cursor moves, not keystrokes).

## 3. The storage problem (read this before anything else)

DECIDED: extend the format. Theme is the base layer applied to new raw
decks; any edit made in the Lite or Full designer supersedes the theme and
is persisted per-deck (deck format line / inline runs win over theme per the
existing cascade — this plan only adds the params the ribbon needs).

The save pipeline speaks exactly five inline properties —
`size / bold / color / italics / case` — plus deck-level format line, and two
renderers implement them (`display/display.js::spanStyle`, Python
`renderInlineColors` twin). Every toolbar feature falls into one tier:

- **Tier 0 — persists today, zero parser work:** bold, italics, font family,
  font size, color, case, alignment→(`text_align` is theme-level; per-slide
  alignment needs Tier 1), paragraph spacing→line-height (same caveat).
- **Tier 1 — small spec extension (`docs/slide-format.md` + parser + BOTH
  renderers + tests):** `underline`, `strike`, per-slide `align`, per-slide
  `spacing` (line-height), superscript/subscript (render as `<sup>`/`<sub>`;
  parser params `super=true` / `sub=true`). All render trivially in HTML/CSS
  on both targets. **Do these in v1.**
- **Tier 2 — no clean text representation, needs a real decision:**
  - *Bullets / numbered lists:* representable as literal `• `/`1. ` prefixes
    on lines (dumb but renders everywhere, zero parser change). Recommended.
  - *Horizontal line:* representable as a sized gap marker (`[\n (size=8)]` +
    CSS top-border via a new `hr=true` param, or just an em-dash line).
    Recommend `hr` param in Tier 1.5.
  - *Tables / shapes / images:* CUT until Phase-2 image payloads (decided).
    No pickers, no placeholders in v1. When image payloads land (new payload
    type, OBS-side `<img>`, operator preview label), the Table ▾ hover-grid
    picker (per the reference screenshot: hover-expand from 1×1 with
    "N × M" caption, lazy-built on first open) and Shapes ▾ return.
  - *Outline:* per-run outline = new `outline=#000` param → CSS
    `-webkit-text-stroke` / layered text-shadow spans. Both renderers can do
    it — Tier 1.5. Ribbon toggle defaults to the theme's outline color;
    color picker visible only while outline/shadow is on (§2); per-deck
    persisted, supersedes theme once touched.
  - *RTL/LTR:* block-level `dir` — representable as a per-slide param
    (`dir=rtl`), renders as `direction:rtl` span/div. Tier 1.5.
- **Rule: the editor NEVER silently drops formatting.** Every shipped ribbon
  control has a Tier 0/1/1.5 persistence story before it ships.

## 4. Data flow (edit → save → screen)

```
deck dict (slide_service) ──load──▶ per-slide QTextDocuments (lazy: active
  slide fully, others parsed to HTML on first scroll-into-view, cached)
        │ user edits (single shared QTextEdit, cursor-format probing)
        ▼ switch slide / Save
serialize: QTextDocument → slide-format txt (char-format runs → [text (k=v)]
  runs; blocks → lines/gaps/lists; slide splits on double-Enter)
        ▼
parse_slide_txt (normative re-parse — round-trip is the validator)
        ▼
slide_service.update path (existing) → preview strip refresh ONLY;
  live keeps old deck until preview slide double-clicked (existing contract,
  unchanged). Editing a live deck warns in the title bar ("LIVE — preview only").
  DECIDED: Freeform-tab Save is STRICTLY preview — no "Go Live" offer, same
  as Edit-as-Text today.
```

- **Dirty tracking:** per-slide checksum; Save writes only what changed.
- **Undo:** QTextDocument's stack per slide (kept alive with the cached
  document, so undo survives slide-switching within the session; cleared on
  Save — standard word-processor behavior, and matches Edit-as-Text today).
- **Sections:** chip edit renames the `*` marker; empty chip = bare `*` clear.
  New-slide button appends; drag handle reorders (reorder = txt block move,
  reuse existing index logic).

## 5. Performance budget (snappy / light / lag-free)

- Open target < 200 ms on a 100-slide deck: build cards lazily (first ~15
  real, rest height-estimated placeholders filled on scroll — same chunking
  idiom as the strip builder: 30 first paint, +25 per idle tick).
- Typing: one `QTextEdit`, no per-keystroke full parse (active-slide
  incremental re-parse only, preview debounced 150 ms, cursor-format probe on
  cursor moves).
- Heavy UI lazy: table grid popup, shapes panel, custom-spacing dialog, font
  list (system fonts enumerated once, cached) — all constructed on first use.
- No WebEngine inside the designer; preview stays the existing lightweight
  `ThemePreview`. Memory: cached QTextDocuments capped (~30, LRU unload to
  serialized txt — cheap, it's already the save format).

## 6. Files (new + touched)

- NEW `ui/widgets/lite_designer/` package:
  - `lite_designer.py` — the one popup form; `mode="theme"|"slides"`;
    theme mode embeds today's two columns verbatim.
  - `format_ribbon.py` — Row 1 + collapsible Row 2, cursor-probe slots.
  - `slide_card.py` — chip + title + editor-host/static label swap.
  - (table/shapes pickers CUT from v1 — return with image payloads, §3.)
  - `rich_to_txt.py` — QTextDocument → slide-format serializer (the heart;
    pure functions, fully unit-testable without Qt).
  - `txt_to_rich.py` — slide-format → QTextDocument/HTML loader.
- TOUCHED: `core/slide_parser.py` + `display/display.js` +
  `ui/widgets/display_view.py` (Tier 1/1.5 params only); `docs/slide-format.md`
  (spec first, code second); `ui/tabs/slides_tab.py` (deck context menu:
  "Edit…" opens Lite Designer; "Edit as Text…" stays as the raw escape hatch);
  `ui/widgets/theme_quick_editor.py` (thin wrapper → `LiteDesigner(mode="theme")`
  once stable; not day one).
- TESTS: `tests/test_lite_designer_serialize.py` — round-trip matrix
  (every Tier 0/1 feature through `rich→txt→parse→render` incl. both
  renderers' span output); fuzz with EW-imported decks (weirdest real input).

## 7. Phasing (ship in slices, designer usable after each)

1. **Shell + cards + Tier 0** (open deck, edit B/I/font/size/color/case text,
   section chips, save → preview refreshes). No ribbon Row 2 yet.
2. **Row 2 + Tier 1/1.5 parser extensions** (underline, strike, align,
   spacing, super/sub, outline param, dir, hr) with spec updated first.
3. **Lists via literal prefixes;** table/shapes stay cut (image payloads are
   their own later project, not part of this phasing).
4. **Perf pass** (virtualized cards, LRU docs, measured open/typing budgets)
   + `ThemeQuickEditor` consolidation into the shared shell.

## 8. Open questions for you (refinement round)

RESOLVED (locked in, no longer open):
1. ~~Per-slide alignment/spacing: extend the format or theme-only?~~ → EXTEND.
   Theme is the base for new raw decks; designer edits supersede per-deck.
2. ~~Tables/shapes placeholders in v1 vs. cut?~~ → CUT entirely until
   image-payload rendering (no pickers, no placeholders).
3. ~~Outline default color?~~ → Theme's outline color as default; dedicated
   outline/shadow color picker visible only while outline/shadow is on;
   on/off + color persist per-deck once touched.
4. ~~Save with "Go Live" or preview-only?~~ → STRICTLY preview-only.

Still genuinely open: none — refinement round is yours.

## 9. Tabbing spec (from user — NOT YET BUILT, spec only)

The Lite Designer window carries two tabs under the title bar:
`[ Freeform | Theme ]`. One form, both editors, shared shell
(title bar, badge, Reset/Save/×, preview widget).

- **Opened from a deck context menu** (Slides tab → deck → Edit…;
  later also from schedule items): **Freeform tab defaulted to**,
  Theme tab still available (operator may tweak the deck's theme without
  leaving the window; theme edits save to the theme, freeform edits to
  the deck — two save targets, one shell; Save applies whichever tab is
  dirty, or both with a combined confirm — exact dirty/save semantics to
  be nailed in refinement).
- **Opened from a theme context menu** (Themes panel → Quick Edit):
  **Theme tab defaulted to, Freeform tab GREYED OUT** (disabled). Reason:
  BIS (bold/italic/strikethrough) application differs between theme text
  and freeform text — theme-tab formatting capabilities will expand later,
  and until they do there is no meaningful freeform target in a
  theme-initiated session (no deck in context).
- Theme tab keeps today's ThemeQuickEditor look verbatim (properties left,
  preview right); expansion of its capabilities is a later phase, not v1.
- Tab state (which tab is active, freeform disabled or not) is set once at
  construction from the entry point; no mid-session switching of the
  disabled state.

## 10. Build log — done vs left (v1, 2026-09-11, suite 183 passed + 1 xpassed)

### DONE
- **Format Tier 0/1/1.5** (§3): `underline, strike, align, spacing, super/sub,
  outline, dir, hr, font` in `core/slide_parser.py` (parse + `_span_style` +
  `format_to_line`), `display/display.js`, `ui/widgets/display_view.py` JS
  twin, `display/themes.css` (`--rc-text-decoration/direction/outline`);
  spec table in `docs/slide-format.md`; tests in `tests/test_slide_edit.py`.
  Strips keep `allow=("color","italics")` — nothing new leaks into operator
  views. Deck line carries `spacing/align/dir/outline/font`; per-deck values
  supersede theme once touched (locked decision 1).
- **Converters** (`lite_designer/rich_txt.py` + `tests/test_lite_designer_serialize.py`):
  txt↔QTextDocument round-trips exact/stable incl. mid-line gaps (glue flags),
  HR blocks, literal `• `/`N. ` lists, U/S props (Qt6 marks no bool for
  underline), structure guards (`\u200b` vs `#`/`%`/`*`), per-block align/
  dir/spacing wrap runs, `base_spacing` suppression for WYSIWYG paint.
- **Shell** (`lite_designer.py`): shared chrome, `[Freeform|Theme]` tabs,
  entry-point defaults + freeform grey-out (§9 as specced). Save stays open
  + status flash; × confirms when dirty; Reset reloads.
- **Ribbon** (`format_ribbon.py`): Row 1 always visible (font, size −/+,
  B I S U, outline toggle + color picker visible-only-when-on, text color,
  clear, undo/redo); collapsible ¶ row (alignment, spacing menu incl.
  custom, bullets, numbers, super/sub, case, RTL/LTR, HR); cursor probing;
  `Ctrl+Z / Ctrl+Shift+Z` via document stack.
- **Cards** (`slide_cards.py`): index badge, inline section chip (empty =
  clear), ↑/↓/+/×, single shared live editor moved between cards (undo
  stacks live per-document), double-Enter splits the slide, new slides
  inherit section. Static cards render via `inline_markup_to_html`.
- **Save contract** (locked decision 4): strictly preview — `update_deck`
  → library refresh + `_on_deck_text_updated`; live untouched; LIVE badge
  warns when the deck is live.
- **Wiring**: deck menu `Edit…` (+ `deck_edit_requested` signal; `Edit as
  Text…` stays); theme Quick Edit opens LiteDesigner theme mode;
  `Edit in Full Designer` routes to the Theme Designer tab.
- **Decisions 2–3**: table/shapes pickers CUT (no placeholders); outline/
  shadow color picker gated on outline state. Links skipped entirely.

### LEFT (deferred / phase 2+ / refinement fuel)
- **Tables/shapes/image payloads**: new payload type + OBS `<img>` + preview
  label; hover-grid Table picker per reference screenshot returns then.
- **Links** (`Ctrl+K` was cut; display side has no link concept).
- **Perf pass** (§7.4): card virtualization (all labels built today — fine
  to ~100 slides, unmeasured beyond), LRU cap on cached docs (unbounded
  today), measured open <200ms / typing-jank budgets.
- **Drag reorder** of cards (↑/↓ buttons ship instead).
- **Dual-tab save semantics**: Save applies the ACTIVE tab only; combined
  dirty confirm still open (§9 caveat stands).
- **Schedule-item entry** (deck menu ships; schedule items later per §9).
- **Theme tab expansion**: BIS-for-themes + richer theme editing (locked as
  later phase); `ThemeQuickEditor.py` still in tree, now unused — delete on
  your call.
- **Prune-on-save bug** (found during build, OPEN): something round-tripping
  a theme through the shared `ThemePropertiesPanel` drops unmanaged keys —
  `fullscreen.json` lost `text_transform`/`text_align` in the working tree
  (restored by hand). Repro + fix before heavy theme editing.
- **EW fuzz**: round-trip tests over real EasyWorship-imported decks
  (weirdest real input) not yet written.
- **Refinement queue #1**: slide-card screenshot received, undescribed —
  say the word and it goes under the knife first.
- **Card-style pass (done)**: index demoted to dim 9px text, no box; section
  chip is a borderless rectangle on a shared header canvas (chip hugs text
  width, buttons stretch-pinned right); body wash `rgba(255,255,255,0.04–0.05)`,
  no borders, matched padding.
- **Vertical hug (done)**: section chip is now a wrapping `_SectionField`
  (width-hugs short names, wraps + grows vertically past the cap, commits
  flattened on Enter/focus-loss since `*` markers can't hold newlines);
  live editor height-fits to its document (scrolls past 480px) so active
  and static states match within ~2px — no jump on activation.
- **Editor wrap-width collapse (done, FIXED)**: the height-fit's
  `doc.adjustSize()` pinned `textWidth` to content width, narrowing the
  editor with every keystroke (384→111px proven headless). Now reset to
  `-1` (viewport-driven) immediately after measuring, in both the slide
  editor and the section field. Pure layout bug — no bad txt was ever
  written.
- **Measure-without-mutation (done, FIXED the fix)**: `adjustSize()` also
  corrupts the page width (measured 4px!) and `setTextWidth(-1)` wipes the
  page entirely — together they killed wrapping (h-scrollbar, no vertical
  growth). Height fitting is now READ-ONLY: a `documentSizeChanged`
  connection re-invokes the fit with a fresh size after every relayout;
  the only mutation left is a page-width self-heal toward the live
  viewport. Verified:   spaced text 84px no-hbar, unbroken word wraps to
  102px no-hbar, section chip wraps at cap.
- **Column width feedback loop (done, FIXED)**: unwrapped size hints
  (labels' ideal widths, editor hints) stretched the scroll host, which
  widened viewports, which unwrapped everything further — wide cards,
  sideways-scrolling editor, non-wrapping chip. Fix is structural, not
  measured: labels + editor vote `Ignored` horizontally (take the column
  width, wrap, grow down),   scroll area h-bar off. Verified with
  pathological content: host 418px, cards 402px, editor 66px no-hbar.
- **Envelope header blowout (done, FIXED)**: the new section headers voted
  their unwrapped ideal width into the layout minimum (host 709px in a
  440px column — cards poking past their envelopes). Headers now wrap +
  vote Ignored like card bodies. Containment re-verified: host 418,
  envelopes 414, cards inside.
- **Chip-owns-section model (done)**: only run-starting slides show chip
  text; members show empty chips and inherit the run above. Text in a chip
  = new section even when identical (persists as repeated `*Name`,
  re-parses losslessly); clearing merges into the run above (or
  section-less). Parser records `marker` per slide + `slide_owns_marker()`
  with value-change fallback (old DB/EW data groups as before — no
  migration); `deck_to_txt` emits from ownership; `update_slide` carries
  flags; spec updated. Suite 190 + 1 xpassed.
- **Ownership hardening (done)**: `_normalize_markers` after every
  move/delete/add (a member shuffled where values differ must adopt
  ownership or its value dies on save); deck-top insert starts
  section-less (was inheriting the LAST slide via wraparound); delete
  promotion kept. Caught live: chip-clear crashed on unbound `old_runs`.
  Test teardown closes designers (accumulated WebEngine views abort the
  suite). Suite 200 + 1 xpassed.
- **Section envelopes (done)**: column groups consecutive same-section
  runs with the strips' rule (`_section_runs` mirrors SlideGridPanel:
  break + `SECTION · n` header, section-less runs bare with a break).
  Look: tinted borderless envelope + strip-style header (blue, left accent
  bar). Renames regroup live (merge/split) while editing continues;
  `_clear_column` releases the shared editor before cards die.
- **Ctrl+A promote (done)**: first Ctrl+A is native slide select-all;
  second (whole slide already selected) paints a GREY deck ring on all
  cards (blue active ring keeps precedence as cursor marker); third
  toggles off. Ctrl+C in deck mode copies full deck txt; Esc clears; any
  edit/navigate collapses. Event filter on the shared editor.
  Tests: `tests/test_lite_designer_select.py`.
- **First-activation data-loss (done, FIXED — check saved decks!)**: the
  ghost-fix refactor made deck open serialize the placeholder empty doc
  over slide 1's text (Save would persist the wipe). Guarded + regression
  test `test_opening_designer_preserves_slides`. IF YOU SAVED A DECK WITH
  THE AFFECTED BUILD, VERIFY ITS FIRST SLIDE.
- **Test infra lesson**: one QApplication per pytest process
  (`QApplication.instance()` reuse) — a second instance core-dumps the
  suite; plus WebEngine-first import ordering (see serialize/select
  module headers).
- **Backend-is-txt (done)**: the slides list + title + format IS the txt
  model; docs are projections. Deck selection (Ctrl+A twice) now supports
  real ops: ribbon char formats fan out to every slide (`fan_out` hook,
  per-doc undo, selection preserved for chains); Delete collapses to one
  card (see below); Ctrl+X cuts
  the deck; Ctrl+C copies full deck txt. Structural paste: clipboard txt
  with sections/multi-slides REPLACES the active slide with the parsed
  sequence (unmarked head adopts current run; deck title kept); anything
  else falls through to native rich paste. `_store_active` now stores ALL
  cached docs (fan-out edits to inactive docs were silently lost before).
  Ribbon strike/underline toggles RECORD instead of clearing, so loaded
  `false` runs flip correctly. Suite 197 + 1 xpassed.
- **Highlight-all verbs (done)**: Delete collapses the deck to ONE empty
  card (title + format kept, flag clears); deck-selected paste replaces
  the WHOLE deck (parsed slides/sections, pasted format keys merge in,
  title kept, selection stays on for immediate BIS); BIS verified
  line-by-line in the backend (`[line one (bold=true)]` per line — the
  serializer already emits per block). Suite 203 + 1 xpassed.
- **Churn bug returns (done, FIXED for real)**: the early return never
  fired — `addWidget` reparents the editor to the card's body container,
  never the card, so the parent check was always true and every same-card
  click re-hosted. Now tracked explicitly (`_hosted` index, reset on
  column clear): same-card clicks cost literally zero (0 setText/polish/
  host/setDocument measured). Setter guards (`set_static_html`,
  `set_active`, `set_index`, `set_deck_selected` no-op on same value) make
  refresh passes free; redundant `setDocument` skipped (also preserves
  cursor across rebuilds).
- **Ghost-window on canvas click (done, FIXED)**: clicking the active card's
  header strip showed a phantom untitled (`debug.py`) surface with raw slide
  text. No Qt window was ever created (proven headless) — compositor
  mishandling of popup layout churn. Fixed by early-returning same-card
  activation (no teardown/re-host) + explicit `setWindowTitle("Lite Designer")`
  as tracer. Card-click repro scripts lived in `/tmp/opencode` (not in repo).
