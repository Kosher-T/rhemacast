# Slide TXT Format — Agent Editing Guide

RhemaCast songs/slides are plain `.txt` files (also openable via the deck
right-click menu → **Edit as Text…**; saving reloads the deck). This spec is
everything an agent needs to author or edit them correctly until the Lite
Designer lands. The normative parser is `core/slide_parser.py`.

> Display switching (deck → scripture → …) is governed by
> `docs/theme-switch-contract.md`; this file covers authoring only.

## Where the text lives

- Hand-authored decks: `data/slides/*.txt` (convention, not enforced —
  Import accepts any path; multi-song files split on 5+ blanks + title).
- EasyWorship-imported decks: **no source txt exists** (DB only). Edit via
  right-click → Edit as Text…, which writes a temp file in this exact format.
- Edit-as-Text export always writes the deck's format line first (if any),
  then `#Title`, then slides — so a re-exported file re-parses identically.

## File skeleton

```
size=35, 25, 35; bold=true; color=#66ff00; italics=false; case=origin
#Deck Title Here


*Section Name
Lyric line one
Lyric line two with a [colored run (color=#ff6600; bold=true)] inside

---

*Next Section
More lyrics
```

Blank lines, markers, dividers, and the format line are never displayed.

Paragraph example (gap renders at 12px instead of the text size):

```
First paragraph
[\n (size=12)]
Second paragraph after the gap
```

## Rules

- **Format line (optional):** `key=value` pairs separated by `;`, on leading
  line(s) **before the title**. Every segment must be `knownkey=value` —
  anything else (e.g. a lyric like `God = love`) is treated as a lyric.
  Later lines win per key. After the title, format-looking lines are lyrics.
- **Title:** first `#` or `%` line wins (`#My Song`). Not displayed
  (unless the active theme shows titles). Subsequent `#`/`%` lines ignored.
- **Section:** `*Name` starts a section spanning slides until the next `*`.
  A bare `*` alone on a line **clears** the section (section-less slides).
- **Ownership (chip rule):** a slide whose own `*` line precedes it *owns*
  its section (the Lite Designer shows its name in the chip); a slide with
  no marker line inherits (empty chip = member of the run above). Text in
  a chip = new section — even when identical to the section above (this
  persists as a repeated `*Name` line, which re-parses losslessly).
  Clearing a chip merges the slide into the run above (or section-less
  when nothing owns above). Dicts without the `marker` key (imports, old
  DB rows) fall back to the value-change rule and group as before.
- **Slides (v3, current):** slides are separated by a **divider line** —
  a line containing exactly `---`, blank-padded (a blank line before and
  after; start/end of file count as blank). Extra blank lines around the
  divider are fine and trimmed. Everything else — including any number of
  blank lines — is slide content and is preserved verbatim. A deck with a
  single slide ends with a trailing `\n\n---` end-marker so it still
  declares the v3 format (blank-line spacing round-trips losslessly);
  a trailing divider at EOF is a terminator, not an empty slide.
- **Slides (v2 legacy, read-only fallback):** applies only when the file
  has **no** divider. Single `\n` and single blank lines are preserved as
  content; **double blank line (`\n\n\n`) = slide boundary**; `*Name`
  starts a new slide. Old app-written decks therefore still load exactly
  as before; save them once through the Lite Designer to upgrade them to
  v3 (dividers). Five+ blanks + a title = NEW SONG split (multi-song
  file) — never emit 5+ consecutive newlines unintentionally.
- **Sections in v3:** `*Name` no longer splits a slide; it sets the
  section for the rest of that slide and stays sticky across dividers.
- **Empty slides:** allowed transiently in the editor (placeholder card);
  saving a deck drops all empty cards (`prune_empty_slides`).
- **Inline runs:** `[display text (param=value; param=value)]`. The params
  group must be the **final** `(...)` before `]`. Text may contain `(` `)`.
  `[brackets]` never nest. Unknown/invalid params are skipped; a bracket
  with zero valid params stays **literal** (brackets shown).
- **Paragraph gaps:** a literal `\n` typed in the text (backslash + n) is an
  explicit line break — it survives where blank lines are eaten by the
  parser. `[\n (size=14)]` renders the break at 14px instead of the current
  size, so gap height is controllable per gap. A bare `[\n]` equals a plain
  break. (Caveat: `\` starts a marker — Windows paths like `C:\new` will
  break mid-word. There is no escape; rephrase instead.)
- **Legacy:** `[words: (#hex)]` still parses as color-only. Prefer the new
  syntax for new edits; never mix both styles in one run.

## Parameters (deck line AND inline runs)

| Key | Values | Deck line | Inline run |
|-----|--------|-----------|------------|
| `size` | numbers, `px` suffix ok | `size=nominal, min, max` — missing parts inherit theme; the **set nominal renders exactly as set** — auto-fit never grows past it and only shrinks inside the box when it truly overflows | `size=##` — single absolute px, first number wins |
| `bold` | `true` / `false` | → weight 800 / 400 | → `font-weight:700` / `400` || `color` | `#rgb` / `#rrggbb` | text color | span color |
| `italics` | `true` / `false` | `font-style:italic` / `normal` | same, per span |
| `case` | `upper` / `lower` / `origin` | `text-transform` (`origin` = as written) | same, per span (`origin` resets to none) |
| `underline` | `true` / `false` | deck-wide underline / none | span underline / none |
| `strike` | `true` / `false` | deck-wide line-through / none | span line-through / none |
| `align` | `left` / `center` / `right` / `justify` | deck text alignment (overrides theme `text_align`) | full-width block span for that run |
| `spacing` | `0.5`–`3.0` | deck `line-height` (overrides theme `line_height`) | span `line-height` |
| `super` / `sub` | `true` / `false` | accepted, ignored for rendering (run-only concept) | wraps run in `<sup>` / `<sub>` |
| `outline` | `#rgb` / `#rrggbb` | deck-wide 1px text stroke (overrides theme shadow stack visually) | span `-webkit-text-stroke:1px` |
| `dir` | `rtl` / `ltr` | deck base direction | span `direction` + bidi embed |
| `hr` | `true` / `false` | accepted, ignored for rendering | `[ (hr=true)]` renders a horizontal rule |
| `font` | family name (no `;()[]`) | deck `font-family` (overrides theme) | span `font-family` |

Booleans also accept `1/0/yes/no` (any case). Unknown keys are ignored
with a logged warning — check the console if formatting silently vanishes.
Spacing and key case are free (`SIZE = 35 , 25 , 35 ; Bold = True` parses
identically); sizes accept an optional `px` suffix (`size=35px`).

Note: the deck title line and `slide.show_title` are different things — the
title marker above is file metadata, while whether any title renders on
screen is a *theme* option (`slide.show_title` in `themes/freeform/*.json`).

## Cascade (ascending importance)

1. **Theme** (`themes/freeform/*.json`, `themes/scripture/*.json`)
2. **Deck format line** — overrides theme for the whole deck
3. **Inline run** — overrides deck + theme for the bracketed words only

Unset = inherit from the level below. Example: theme normal + deck
`case=upper` renders everything uppercase except an inline
`[whisper (case=origin)]` run, which shows as written.

## Editing checklist for agents

1. Keep the format line (if any) as the **first non-blank line(s)**.
2. Preserve `#` title, `*` section markers (one per section — repeat only
   on change), and blank-padded `---` slide dividers (v3); legacy files
   without dividers keep double-blank boundaries.
3. Never emit 5+ consecutive newlines unless splitting songs.
4. Inline params last in brackets; verify every `[` has a matching `]`.
5. After editing, re-parse mentally: title correct? sections sticky as
   intended? (a marker-less slide inherits the previous section — add a
   bare `*` to clear it).
6. Saving the file reloads the deck: preview strip refreshes instantly,
   live keeps the old deck until a preview slide is double-clicked.
7. Verify mechanically when possible (from the repo root):
   `python -c "from core.slide_parser import parse_slide_txt;
   d=parse_slide_txt(open('data/slides/my_song.txt').read());
   print(d['title'], len(d['slides']), d['format'])"`
   — title right, slide count as expected, format dict as intended, and no
   `Ignoring invalid …` warnings above it on the console.

## Section rule (v2 standing rule)

If a slide has section syntax at all, it starts a new section — even when
the name is identical to the section above. Equivalent `*Name` lines are
never merged into one section: each owns its slide (the Lite Designer
shows each name in its chip), the serializer re-emits every marker as a
repeated `*Name` line, and re-parse reproduces the split losslessly.

## Slide format v3 (implemented)

v3 is the current format; there is no opt-in flag. A file is treated as v3
when it contains at least one divider: a line that is exactly `---` with a
blank line before and after (start/end of file count as blank). Everything
from v2 carries forward **except** slide boundaries:

- Dividers are the only slide boundaries. Multiple consecutive newlines
  inside a slide are content and are preserved. `*Name` sets the section
  for the remainder of that slide (sticky across dividers) and does not
  split.
- A file with no divider is parsed with the v2 fallback above (old decks
  keep working). Saving through the Lite Designer writes v3.
- In the Lite Designer: **Ctrl+Enter** inserts `\n\n---\n\n` at the
  caret (a new card below); **Ctrl+Ins** / **Ctrl+Down** add a card and
  continue editing there; Enter / Shift+Enter are soft line breaks; Tab
  indents a paragraph. Empty cards are pruned on save.
- Future element syntax (tables and friends) will borrow from markdown
  syntax. Table rendering does not exist yet; do not author tables
  expecting them to display.
