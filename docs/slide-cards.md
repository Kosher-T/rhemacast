# Slide Cards — Property Specification

Single shared design (`ui/widgets/lite_designer/slide_cards.py`, class
`SlideCard`). Every slide duplicates this look and behavior. Locked in by
`tests/test_slide_cards_layout.py` and the card-interaction tests in
`tests/test_lite_designer_select.py`.

> Display switching is governed by `docs/theme-switch-contract.md`;
> this file covers the editor card design only.

The screenshot reference: joined stack, flat seams, gaps only above
section-headed runs, full outline on the focused card.

## Layout

- **Row 1:** slide number | section textbox (flex) | controls pill.
- **Row 2:** display textbox, indented 26px (18px number column + 8px row
  spacing) so its text aligns under the section text.
- Card root margins: 12px left/right, 10px top, **2px bottom**.
- No horizontal scrolling anywhere; both textboxes wrap at widget width
  and grow vertically with content.

## Slide number

- Own 18px column, top-aligned, 11px bold.
- Colors: `#475569` idle, `#60a5fa` active, `#94a3b8` deck-selected.
- Strictly positional counting; section grouping never renumbers.

## Section textbox (`_SectionEdit`)

- Editable `QTextEdit`. Italic, 12px.
- Colors: `#64748b` (600) idle, `#38bdf8` (700) active,
  `#94a3b8` (600) deck-selected. Placeholder: `Section…`.
- Typing works: focus survives the activation cascade (card emits
  `activated` *before* taking focus; designer never rips focus back out
  of the box).
- **Enter** commits, **Shift+Enter** inserts a newline, focus-out commits.
  Commits flatten to one line and emit `section_changed`.
- Transparent background, no border, square corners. Viewport carries an
  explicit `QTextEdit QWidget` shield so ancestor bare-`QWidget` border
  rules cannot paint on it.
- I-beam cursor on hover. Auto-grows (`_fit_height`), scrollbars always
  off.

## Display textbox (`_DisplayBox`)

- Read-only `QTextEdit` showing the slide text that gets sent to display.
  13px, transparent background, no border, no rounding.
- Colors: `#64748b` idle, `#f8fafc` active, `#cbd5e1` deck-selected.
- Never takes keyboard focus (`NoFocus` — no focus rect, no caret), so it
  is chromeless by construction; viewport shielded like the section box.
- I-beam cursor on hover (parity with section; card background and
  buttons keep the hand pointer).
- Clicking it activates the card and hands focus to the hosted live
  editor, so slide text stays immediately typable.
- Auto-grows, wraps, scrollbars always off. Active card swaps this box
  for the shared live editor with zero card-size change.

## Controls pill

- Four 18px buttons in a rounded pill: **↑ ↓ + ×**
  (move up / move down / add slide below / delete slide).
- Edge buttons are **hidden, not disabled**: no ↑ on the first slide, no ↓
  on the last — the pill collapses. Visibility refreshes through the
  existing card-sync loop, so add/delete update edges for free.
- Move = content exchange with the neighbor above/below:
  - *Fast path* (section runs identical): values swap in place. Same card
    widgets, same editor document object, focus and undo preserved. No
    rebuild, no preview re-render (the active slide's bytes travel with
    it, so output would be identical). Active highlight follows content.
  - *Slow path* (runs merge/split): existing diff-based regroup +
    re-activation.
  - The O(n) marker-normalization scan always runs: swaps can orphan
    members, so section ownership is recomputed, never assumed.

## Card chrome and the joined stack

- 1px border; card background tints per state
  (idle slate wash, blue wash + blue border on focus, stronger slate wash
  on deck-select).
- Outer edges keep the 8px round; touching edges are square (90°).
  Position (`set_joined(first, last)`) flows through the card-sync loop;
  single-card decks render fully round.
- Idle non-last cards drop the bottom edge so stacked neighbors share one
  1px seam. Highlighted cards always draw the full outline, so focus
  still traces the whole card shape.
- Inter-card spacing is 0; run-break lines are gone; section envelopes
  are invisible grouping shells (zero paint, zero margins — structure and
  regroup logic untouched).
- A headed non-first run gets an **8px gap** (`_SECTION_GAP`) above it,
  so each section group reads as one block. Never before the first card.
  Slide numbers ignore grouping and count straight through.

## Focus contract

- Section box keeps focus across activation; typing always lands where
  the caret is.
- Display click → live editor focused. Ribbon/format actions return
  focus to the editor. Preview renders never steal focus.
- Highlighting/focusing a card never changes its dimensions.

## Panel scrollbar (`_cards_scroll`)

- Vertical lane permanently reserved (`AlwaysOn`): the bar never pops in
  on growth, so card buttons never shift sideways under the cursor
  mid-click. Horizontal bar permanently off.
- Minimal flat styling: 6px transparent groove, borderless slate thumb
  (brightens on hover), no arrow buttons, no page fill.
- Shared via `ui.styles.apply_minimal_scrollbar(view)` (policies +
  appended rules): schedule list (both tabs), deck list, bible verse
  list. Exception: preview/live strips use a mobile-style overlay
  instead (`_FadeScrollBar` in `slide_grid_panel.py`) — no reserved
  lane at all, thin thumb floats over content, visible on hover/scroll,
  fades out after 1.2s idle, never shown when nothing overflows.
## Performance contract
- Style re-polish is skipped when the visual state is unchanged
  (`_painted_state` guard — redundant polish measured ~5ms/call).
- Card rebuilds freeze paints (`setUpdatesEnabled`) for a single
  relayout at the end.
- Measured add-slide cost scales linearly (~7ms/slide; 30 slides ≈
  260ms offscreen, down from ~990ms). Model ops (renumber, normalize)
  time at ~0ms — there is nothing worth caching, so no cache layer.

## Editing behavior specification (both textboxes)

Shared helpers live in `slide_cards.py`; hooks exist per textbox
(`_SectionEdit` overrides + designer event filter for the shared
editor). To reproduce on another textbox, follow the hook checklist at
the end.

### Ctrl+Left — Qt default, verified by probe, do not reimplement

Stops at word beginnings, after separating spaces, and just before
trailing punctuation; punctuation clusters are crossed in one hop.
Probed table (`|` marks the cursor):

- `hello,| world` → `hello|, world` → `|hello, world`
- `word;| another,| without` → stops before each `;` / `,`, then word
  beginnings, one hop per cluster
- `''"He| is"''` → after the opening cluster, then before it
- `space before punctuation| !` → before `!`, then word beginnings
- Apostrophes segment like Qt's own words (key ≡ `PreviousWord` op on
  every probed position, so Ctrl+Backspace below mirrors by
  construction).

### Ctrl+Right — custom (`move_to_word_end_right`)

Only when the char right of the cursor starts a punctuation cluster
(Unicode `P*`): stop at the cluster end, before a following space
(`hello,| world` stops after the comma, not after the space).
Clusters without internal spaces count as one word (`''"`, `,;`).
Everything else (letters, spaces, block ends, newlines) falls through
to Qt default — including space-ahead, which stays native. Shift
extends the selection. Block-local; newline crossing stays Qt.

### Ctrl+Delete / Ctrl+Backspace

- **Ctrl+Delete is custom** (`word_ahead_stop`, pure string function
  delegating to the shared kernel): punctuation cluster immediately
  ahead is consumed up to before a following space; everything else is
  Qt default. Deletes cursor-to-stop.
- **Ctrl+Backspace stays Qt default**: probed identical to Ctrl+Left
  stops on every case (`hello, world`@12 → `hello, `; @7 →
  `helloworld`; quote/apostrophe cases included), so no code could
  improve it.

### Double-click — custom word (`select_word_at`)

Selects exactly `[\w]+('[\w]+)*` (letters/digits/underscore with
*internal* apostrophes): `don't` is one word; leading/trailing quotes
are excluded (`'tis` → `tis`). Returns False off-word (space,
punctuation) → Qt default applies. Replaces Qt's selection, which
splits contractions (`don`).

### Triple-click — custom paragraph (`select_block` + `TripleTracker`)

- Counter per textbox: same-spot left presses within the platform
  `doubleClickInterval` and `startDragDistance` count 1-2-3 (the
  double-click press counts as 2); any other button, timeout, or
  distance resets; reaching 3 resets to 0.
- Paragraph shape: whole block plus one trailing newline when one
  exists; last block selects text only.

### Smart Delete/Backspace (`smart_delete_extend`, then fall through)

Caller extends the selection and lets default deletion remove it, so
undo granularity matches normal deletion. With a selection present:

| Selection | Delete | Backspace |
|---|---|---|
| Spans block separator(s), or covers exactly one whole block (triple-click shape) | + one following newline if present | + one preceding newline if present |
| Exactly one word (`[\w'\u2019]+`, no spaces) | + one following space if present | + one preceding space if present |
| Anything else adjacent (punctuation, newline, doc edge) | word only | word only |
| Non-matching selection | Qt default | Qt default |

Shift+Delete (cut) and Alt/Meta combinations bypass all of the above —
Shift held means pure Qt, always.

### Hook checklist for a new textbox

1. **Keys**: intercept Delete/Backspace (no Shift/Alt/Meta) → extend via
   `smart_delete_extend`, then fall through to default deletion.
   Intercept Ctrl+Delete with no selection → `word_ahead_stop`, select
   the range, fall through. Leave Ctrl+Backspace and Ctrl+Left on Qt.
   Intercept Ctrl+Right → `move_to_word_end_right`, honoring Shift.
2. **Mouse**: install the filter on the viewport (not the widget) for
   `MouseButtonPress` (triple counter → `select_block` on 3, swallow)
   and `MouseButtonDblClick` (register as press 2 → `select_word_at`,
   swallow on success). Subclass overrides work identically.
3. **Platform facts**: `QTextDocument.characterAt` returns `str`;
   block separators report as U+2029 (never `\n`) in both
   `characterAt` and `selectedText` — compare against `chr(0x2029)`,
   never a newline literal. Invisible-character literals garble
   easily; prefer escapes or `chr()`.

Covered by `test_word_ahead_stop`, `test_select_word_at_contractions`,
`test_select_block_includes_newline`, `test_smart_delete_word_rule`,
`test_smart_delete_paragraph_rule`, `test_triple_tracker_counts`
(widget-free) plus real-event integration: custom Ctrl+Delete both
boxes, Backspace mirror pin, contraction double-click + smart delete,
triple-click paragraph + delete.

## Shared text module (`ui/widgets/text_nav.py`)

Single source of truth for word behavior in every other textbox:

- Pure kernels (no widgets): `word_end_right_stop(text, offset)`,
  `word_span_at(text, pos)`. The slide-card cursor wrappers delegate
  to these; only one implementation of each rule exists.
- `install_line_edit_nav(edit)` (idempotent): Ctrl+Right/Delete
  punctuation stops, contraction double-click, triple-click select-all,
  and focus-select-all latch on any `QLineEdit`. Everything else falls
  through to Qt (Ctrl+Left, space-ahead, Shift variants, plain
  Delete/Backspace, Alt combos).
- `SearchField` (single-line `QTextEdit`): `returnPressed` on any Enter
  with no newline ever inserted, word/paragraph smart Delete/Backspace
  like the cards, focus-select-all latch, triple-click select all,
  newline-flattening paste, ShortcutOverride claims so app shortcuts
  never fire mid-edit, I-beam cursor. Used by the Scripture FTS +
  fuzzy panels and the Slides deck search bar. (`QLineEdit` fields
  keep plain Delete/Backspace.)
- Covered by `tests/test_text_nav.py` (kernels, lineedit behavior,
  SearchField behavior, panel wiring).

## Search fields (`SearchField` in `text_nav.py`)

The Scripture-tab FTS/fuzzy query inputs and the Slides-tab deck
search are single-line `QTextEdit` boxes (not `QLineEdit`), so they
share the card-grade key paths provably working on desktop:

- Drop-in `QLineEdit` surface (`text()`, `clear()`, `selectAll()`,
  cursor/selection accessors, `returnPressed` on plain Enter, all
  Enter variants swallowed, pasted newlines become spaces, Tab moves
  focus, no scrollbars, fixed single-line height).
- Scoped behavior: ctrl+arrows (explicit word hops + custom punct-R),
  ctrl+delete/backspace (custom ahead, Qt mirror behind), contraction
  double-click, triple-click select-all, focus select-all. Plain
  Delete/Backspace removes exactly the selection (no smart spacing).
- Stylesheets converted to `QTextEdit` selectors; `.text()` reads
  became `.toPlainText()`. Covered by `SearchField` tests in
  `tests/test_text_nav.py` plus panel wiring tests.
- `SearchField.event()` claims `ShortcutOverride` for every handled
  key (arrows/Home/End/Delete/Backspace/Enter, never Alt/Meta), so app
  shortcuts such as verse prev/next on plain arrows never fire
  mid-edit. `QLineEdit` did this natively; `QTextEdit` needs it
  spelled out.
- SearchField mouse logic lives in a viewport filter (not overrides):
  viewport-targeted events deliver faithfully everywhere, including
  headless runs where widget-level synthetic presses never arrive.
- Focus-select fires once per focus gain (`_focus_selected` latch,
  re-armed on focus-out): no refire while focused, refires after
  blur + refocus.
- Fuzzy search restores field focus after its in-flight disable cycle
  (disabling blurs; the restore hands focus back only if the field
  owned it).

## Add-and-continue (Ctrl+Enter)

- Ctrl+Enter in the editor or the section box adds a slide after the
  current one (same as the add button), scrolls it into view, and
  focuses its editor so typing continues with no mouse round-trip.
- Section text commits *before* the insert so shifting indices cannot
  strand it on the wrong slide.
- A deferred settle tail (`_settle_after_add`) drains the auto-fit
  cascade, then scrolls to final geometry and refocuses: a synchronous
  `setFocus` alone is swallowed by deferred focus-clear events from the
  rebuild's hide/show churn.
- The preview surface is `NoFocus` and can never steal keys mid-flow.

## Preview refresh pacing
- Typing bursts drive renders: keypresses within 200ms
  (`_BURST_WINDOW_MS`) of each other are one burst.
- Mid-burst, renders run at most every 300ms
  (`_PREVIEW_THROTTLE_MS`, via the pure gate `_burst_render_due`).
- The event list always ends with an update: every keypress re-arms a
  300ms trailing single-shot render.
- Idle renders nothing: no periodic timer, only card-switch (instant),
  burst-throttle, and trailing renders.
- `_activate` renders instantly on card focus change and resets burst
  state.

## Cloak (shared live-screen blank state — replaces clear)

- Cloaking drops an invisibility cloak over OBS output: pushes keep
  updating the model exactly as uncloaked — the congregation sees
  blank. State lives on `DisplayState.cloaked`, shared across tabs by
  construction; there is no per-tab flag and no clear/recall memory.
- Gate lives in each tab's `_broadcast_to_ws` (`_obs_gated` predicate):
  content payloads are suppressed while cloaked (history still logged);
  the blank action always flows.
- Exits: double-click pushes (`uncloak=True`) and the cloak toggle.
  Toggle-off broadcasts whatever is underneath NOW — single clicks,
  arrows, and section-hop never touch the flag.
- The operator live screen taps the OBS feed, not the model: cloak-on
  blanks it once (shared `cleared` emission reaches every tab's views),
  pushes behind the cloak render nothing anywhere
  (`DisplayState.set_live_muted` suppresses `live_changed`; zero
  screen updates means no flash is possible), uncloak re-renders
  current — all with the model untouched.
- All cloak transitions go through `DisplayState.set_cloaked`, and both
  tabs' buttons mirror it via the `cloak_changed` subscription — the
  button (amber `cloaked` style + tooltip) can never drift, whichever
  tab toggles.

- Single-slide edits patch the preview strip regardless of what the
  preview screen is showing; the screen refresh stays gated on a deck
  match.
