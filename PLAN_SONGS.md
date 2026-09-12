# RhemaCast — Songs / Freeform Feature Plan

## Overview
Add a "SLIDES" tab for songs, announcements, and freeform/rolling text. Two display modes:
slide-by-slide (verse/chorus) and rolling/scrolling (single long paragraph, user-configurable speed).
Integrate with schedule panel and existing WebSocket/OBS pipeline.
**Deferred:** Lite Designer and Theme Designer — slide creation is txt-file based with hardcoded themes for now.

## Slide TXT Format (interim authoring, parser-driven)

Markdown-like, strict rules for clean parsing into a basic render. Text transforms (ALL CAPS, alignment) are theme-driven via `text.text_transform` / `text.text_align`. Deck-level overrides (top `size=/bold=/color=/italics=/case=` line) and inline `[words (k=v; …)]` runs cascade theme → deck → inline; legacy `[words: (#hex)]` still parses. Full agent-editable spec: `docs/slide-format.md`.

```
# or % at line start = title (first occurrence wins, not displayed)
#This is the title of this song/slide
%This is another way to title a song/slide

* at line start = section marker (not displayed, spans slides until next * marker)
*Section 1 (Verse)
*Chorus

plain lines = slide content (displayed)

inline color: this is [the text: (#ff0000)] I want to color
  bracketed run renders in the given hex color; 3- or 6-digit hex; rest uses theme color.
  Converted to <span style="color:#hex"> at payload build; FTS indexes stripped text.

double blank line (\n\n\n = two consecutive empty lines) = slide boundary
  single \n = line break within same slide; single blank (\n\n) is ignored (readable spacing only)

multi-song: a run of \n × 5 or more followed by a title line (#/%) starts a NEW song.
  One txt file → N distinct decks (keyed abspath#<index>; re-import updates in place,
  stale extras removed when a file shrinks). Gaps without a following title don't split.
  See data/slides/_sample_multi.txt
```

### Example (complete deck) — double blank = boundary
```
#This is my story


*Section 1 (Verse)
This is my story, this is my song


Praising the Lord all the day long


Won't have no trouble, no need to fear


I have my God always with me


*Section 2 (Chorus)
he's never failed me yet


he's never failed


he's never failed me yet


he's never failed


he's never failed me yet
```

### Parser rules
- Trim leading/trailing whitespace; ignore empty file header before first content.
- Title: first line matching `^[#%]\s*(.+)\s*$` → `title`. Subsequent `#`/`%` lines ignored (not displayed).
- Section: line matching `^\*\s*(.+)\s*$` → sets `current_section` for subsequent slides until next section marker. Not a slide by itself; flushes pending slide before switching.
- Slide: one or more non-empty, non-marker lines grouped until double blank line (`\n\n\n` = two consecutive empty lines) or EOF.
  Single `\n` = line break within same slide (`Line A\nLine B` → `Line A\nLine B`).
  Single blank (`\n\n`, one empty line) = ignored — just readable spacing, not a boundary.
  Triple+ blanks collapse to single boundary (no empty slides).
- Section can span multiple slides — section marker does NOT imply slide boundary.
- If user wants literal blank line *inside* a slide: not supported yet (open question — revisit for rolling output). For now, double blank = boundary.
- Rolling output: parse same slides, then join with separator (e.g. ` • ` or `\n\n`) into one scrollable block; speed from user config. Tailoring to owner's use first, generalize later.

### `slides_json` (parsed output)
```json
[
  {"section": "Section 1 (Verse)", "text": "This is my story, this is my song"},
  {"section": "Section 1 (Verse)", "text": "Praising the Lord all the day long"},
  {"section": "Section 1 (Verse)", "text": "Won't have no trouble, no need to fear"},
  {"section": "Section 2 (Chorus)", "text": "he's never failed me yet"}
]
```
Each entry = one displayable slide. `section` may be null if none set before first slide.

## Data Model (Phase 1)

### app.db schema
```sql
-- One row per txt file / deck. Author/year/ccli/tags nullable until Lite Designer exists;
-- title comes from parser, others filled later or via header convention.
CREATE TABLE slide_decks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    year INTEGER,
    ccli TEXT,               -- Christian Copyright Licensing International number
    tags TEXT,               -- comma-separated, kept even if UI doesn't expose yet (no clunk)
    source_path TEXT,        -- original .txt path for re-import
    raw_text TEXT NOT NULL,  -- original file content (re-parse on format change)
    slides_json TEXT NOT NULL, -- JSON array as above: [{"section":..., "text":...}]
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- FTS over deck title + concatenated slide texts (+ tags when present)
-- content='' because slide_text is derived from slides_json (not a real column)
CREATE VIRTUAL TABLE slides_fts USING fts5(
    title, slide_text, tags,
    content='', content_rowid='id',
    tokenize='porter unicode61'
);
-- FTS maintained explicitly by slide_service._fts_sync_deck (no triggers)
```

Alternative considered: normalized `slides` child table (deck_id, seq, section, text) — rejected for now in favor of JSON for simplicity; can normalize later if per-slide FTS/query needed.

### Slide themes (done)
- `themes/freeform/slides.json` ("Slides"): 35px nominal / 25–35px autosize, uppercase, centered, weight 800, black outline with no drop shadow, `slide.show_title: false`. SLIDES tab uses its own per-output theme namespace (`display.slides_output_{n}_theme`), independent of scripture output themes.
- Show-title is a theme option (`slide.show_title`, default true) honored per-output when building slide payloads; scripture themes are unaffected.

## Phases (revised)

### Phase 1: Parser + Data Model & Service — DONE
- [x] `core/slide_parser.py` — `parse_slide_txt(raw: str) -> {title, slides: [{section, text}]}` strict rules + edge cases (no title, no section, trailing blanks, multiple blanks, BOM) + `slides_to_text()` for rolling mode
- [x] `core/slide_service.py` — CRUD for `slide_decks`, FTS (porter), `import_txt(path)`, `import_all_txts()`, `reparse_all()`, `search_decks()` with bm25 weighting title>slide_text>tags
- [x] Migration in `core/database.py` — `slide_decks` + `slides_fts` (content='', porter unicode61), bump `CURRENT_SCHEMA_VERSION` to 2, fix legacy FTS, init_db fresh path
- [x] Storage dir: `data/slides/` created + `_sample.txt` example (9 slides parsed correctly)

### Phase 2: Basic UI (txt-driven, no Lite Designer yet) — DONE → REWORKED (modular layout)
- [x] New SLIDES layout: **Schedule (left, same SchedulePanel as SCRIPTURE) | LivePreview + PREVIEW/LIVE slide strips (middle) | Deck library (right)**
- [x] `ui/panels/README.md` — **modular panels principle**: self-contained QWidgets, signals-only communication, workspace-agnostic reuse, path to user-defined JSON layouts per profile
- [x] `ui/panels/slide_grid_panel.py` — reusable SlideGridPanel (themed 16:9 cards, selection, single/double-click disambiguation, empty states)
- [x] `ui/panels/deck_list_panel.py` — DeckListPanel (search, cards, Import .txt / Import EasyWorship / +Schedule / Go Live / Delete, all self-contained)
- [x] `ui/tabs/slides_tab.py` — pure composition: wires panel signals only, owns preview/live display state, schedule stepping (slide decks + verses), clear/recall, WS broadcast
- [x] Removed obsolete main_window slides→SCRIPTURE bridge (each workspace now self-sufficient)
- [x] Multi-song txt files, sample: `data/slides/_sample_multi.txt`
- [x] **Shared truth**: `core/schedule_model.py` (single schedule — both tabs' panels render identical items by construction) + `core/display_state.py` (single preview/live payload — every screen in every tab renders it). Tabs publish gestures (`publish_live/preview/clear`); panels subscribe. OBS broadcast stays with the originating gesture (no double-send). Clear preserves the schedule anchor so recall → prev/next continues the sequence.
- [x] Custom white drop line drawn by shared SchedulePanel (native indicator proved style-dependent); sub-toolbar (View|Schedule|Remote|LiveSync + Start Service) shown in SLIDES exactly as in SCRIPTURE.

### Phase 3: Display & Schedule Integration — DONE (rolling mode deferred)
- [x] Slide-by-slide display via existing WebSocket/OBS payload (`_apply_slide_display` in `presentation_tab.py`; ref = "Title · Section"; theme applied per-output)
- [x] Schedule integration: `item_type: "slide"` items render as "♪ Title · N slides" in `ScheduleItem`; `_sched_uid` stamped on add (Qt UserRole copies dicts — identity unusable); slides embedded in item data so schedules are self-contained JSON
- [x] Prev/Next sequencing: schedule-origin tracking; steps through deck slides, crosses into adjacent verse/deck items (skips empty decks); re-enters decks at first/last slide; falls back to Bible-verse neighbors when display didn't originate from schedule
- [x] SlidesTab actions: "+ Schedule" adds whole deck to schedule; slide-card click selects + auto-previews; "Go Live" pushes selected slide live (switches to SCRIPTURE tab)
- [x] Clear/Recall and per-output theme double-click are slide-aware (`_payload_for_display`)
- [ ] Rolling/scrolling mode: joined slide text + separator, speed from `config.json` (deferred until slide-by-slide proven)

### Phase 4: EasyWorship Import — DONE (v2 library live, colors supported)
- [x] Schema mapped: `Songs.db: song.rowid` ↔ `SongWords.db: word.song_id` (1:1, zero orphans); `SongKeys.db` = EW's own keyword index (ignored — we build FTS5); `SongHistory.db` = usage log (ignored). Custom `UTF8_U_CI` collation registered when opening.
- [x] `core/easyworship_import.py` — two RTF dialects parsed:
  - Old (`\fntnamaut`): blank `\li0` blocks = boundaries, regex section headers
  - EW2 (`\sdfsauto` + `\sdslidemarker`): explicit slide markers; `\sdparawysiwghidden` lines are section labels if header-shaped, else dropped (matches EW WYSIWYG)
  - Handles `\'hh` cp1252 + `\uN?` unicode escapes; chorus-spanning-multiple-slides inherits section
- [x] **Color support**: `\colortbl` palette parsed; `\cfN … \cf0` runs converted to our `[text: (#hex)]` markup mid-line and whole-line; stray EW control words (`\sdnotstroke`, `\shad0`, `{\*\sdfsreal…}`) stripped
- [x] **source_path = `easyworship://song/<song_uid>`** — stable across library versions (v1→v2 rowids shift; uids don't). Re-import updates in place.
- [x] `slide_service.create_deck_from_slides()` — inserts pre-parsed slides without the txt parser; `reparse_all()` skips `easyworship://` decks
- [x] Slides tab "Import EasyWorship" button → directory picker → summary dialog
- [x] **version_2 imported: 1212 songs (+7 skipped non-songs), ~7s**, dedup verified, lyric search markup-safe

### Inline color pipeline — DONE
- `core/slide_parser.py`: `_INLINE_COLOR_RE`, `strip_inline_markup()`, `inline_markup_to_html()` (HTML-escaped, 3/6-digit hex normalized; used by Qt preview labels)
- FTS (`slides_fts`) indexes stripped text; search hits colored slides
- **Render architecture**: payload carries RAW marker text; `display.js renderInlineColors()` AND `display_view.py` inline copy convert markers→spans at render time (both copies kept in sync — Qt screens had shown raw markers until fixed). Server-side pre-conversion was REMOVED — `sanitize_payload()` would double-escape spans into visible text. Verified in node: markers colorize, plain verses untouched, XSS stays escaped, Yoruba Unicode intact.
- **Exact strip thumbnails**: REVERTED per operator decision — strips are pure
  text (one line per slide, ` / ` joins internal newlines, elided; sections get
  a blue accent-bar header). No extra WebEngine, instant, zero dependencies.
  `ui/widgets/slide_thumbnailer.py` + `data/thumbnails/` cache removed.
- **Schema v3**: `slides_fts` recreated with `contentless_delete=1` — true rowid DELETE now works (previous contentless fallback was lossy on update/delete)
- **Special-char fix (post-import)**: `_rtf_unescape()` reordered — `\'hh`/`\uN?` decoding now runs BEFORE control-word stripping (previously `\u8287` was eaten and its `?` fallback orphaned into lyrics, e.g. "reason?why?I'm"). Exotic spaces (nbsp/thin/medium) normalized to ASCII space. Covers Yoruba dotted chars (ọ/ẹ/ṣ/ụ/ị), Latin accents (é/è/à/ñ/ó), curly quotes — all stored as `\uN?` escapes (69 distinct codepoints, 5125 occurrences in v2). All 1212 decks wiped; awaiting user go-ahead to re-import version_2.

### Phase 5: Search (FTS + optional BM25) — DONE via Phase 1/4
- [x] FTS5 instant search over `slides_fts` with porter stemming (`search_decks`)
- [x] Ranking: bm25 weights title(3.0) > slide_text(1.0) > tags(0.5); date fallback ordering available
- [x] Lexical only, no semantic lane

### Deferred (Lite Designer + Theme Designer)
- Lite Designer: per-slide text transforms (ALL CAPS, bullets, font/typeface, size, color, shadow/outline intensity/size), bg image/video via webhook
- Temporary song editing (done): right-click a deck → "Edit as Text…" opens the deck as raw txt (`#`, `*` on change only, real line breaks) in the system editor; saving auto-reloads via file watcher + 1s poll + tab-show check (`deck_to_txt` round-trips `parse_slide_txt`, incl. bare-`*` section clear). Preview strip/screen refresh instantly; live keeps the old deck until a preview slide is double-clicked (live strip force-rebuilds then). Per-deck actions (Edit / Go Live / Add to Schedule / Delete) live in the deck context menu. Schedule items keep their copies.
- Theme Designer: visual editor for slide themes (attributes now hardcoded)
- Text transforms move from hardcoded themes to per-deck overrides when Lite Designer lands

## Integration Points
- **Schedule panel** (`ui/panels/schedule_panel.py`): `item_type` field, `ScheduleItem` renders title for slides vs ref for verses
- **Display/OBS** (`core/websocket_server.py`, `display/`): same payload shape — `ref` becomes deck title + section, `text` is slide `text`
- **Search**: FTS5 (`slides_fts`) — separate from Bible BM25/FAISS/topical lanes
- **Config** (`core/config_schema.py`): `slides_dir`, `rolling_speed`, `rolling_separator` when rolling mode added
- **File ingest**: `data/slides/*.txt` + import dialog; watcher optional

## Open Questions
- Author/year/CCLI in txt header? For now nullable; propose optional header lines like `Author: ...` / `CCLI: ...` above first section if needed before Lite Designer.
- Literal blank inside a slide vs slide boundary — resolved: double blank (`\n\n\n`) = boundary, single blank ignored.
- `#`/`%` after title set: ignore (current), revisit if users title mid-deck.