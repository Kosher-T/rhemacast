# RhemaCast — Songs / Freeform Feature Plan

## Overview
Add a "SLIDES" tab for songs, announcements, and freeform/rolling text. Two display modes:
slide-by-slide (verse/chorus) and rolling/scrolling (single long paragraph, user-configurable speed).
Integrate with schedule panel and existing WebSocket/OBS pipeline.
**Deferred:** Lite Designer and Theme Designer — slide creation is txt-file based with hardcoded themes for now.

## Slide TXT Format (interim authoring, parser-driven)

Markdown-like, strict rules for clean parsing into a basic render. Deferred text transforms (ALL CAPS, bullets, font, shadow/outline, bg media) will be theme-driven later.

```
# or % at line start = title (first occurrence wins, not displayed)
#This is the title of this song/slide
%This is another way to title a song/slide

* at line start = section marker (not displayed, spans slides until next * marker)
*Section 1 (Verse)
*Chorus

plain lines = slide content (displayed)

blank line (\n\n double spacing) = slide boundary
```

### Example (complete deck)
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
- Title: first line matching `^[#%]\s*(.+)\s*$` → `title`. Subsequent `#`/`%` lines treated as plain text if title already set (or ignored — TBD, default: ignore).
- Section: line matching `^\*\s*(.+)\s*$` → sets `current_section` for subsequent slides until next section marker. Not a slide by itself.
- Slide: one or more non-empty, non-marker lines grouped until `\n\n` (one or more blank lines) or EOF. Single newlines within a slide = line breaks in that slide. Double newline = new slide.
- Section can span multiple slides — section marker does NOT imply slide boundary.
- If user wants literal blank line *inside* a slide: not supported yet (open question — revisit for rolling output). For now, blank = boundary.
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
CREATE VIRTUAL TABLE slides_fts USING fts5(
    title, slide_text, tags,
    content='slide_decks', content_rowid='id',
    tokenize='porter unicode61'
);
-- Triggers to keep FTS in sync on INSERT/UPDATE/DELETE (or rebuild on import)
```

Alternative considered: normalized `slides` child table (deck_id, seq, section, text) — rejected for now in favor of JSON for simplicity; can normalize later if per-slide FTS/query needed.

### Hardcoded themes
- Reuse existing scripture theme pipeline; hardcode 2-3 slide themes in `themes/` (e.g. `slide_default.json`) — no new theme UI until Lite/Theme Designer phase.

## Phases (revised)

### Phase 1: Parser + Data Model & Service
- [ ] `core/slide_parser.py` — `parse_slide_txt(raw: str) -> {title, slides: [{section, text}]}` with strict rules above + unit tests for edge cases (no title, no section, trailing blanks, multiple blank lines)
- [ ] `core/song_service.py` (or `core/slide_service.py`) — CRUD for `slide_decks`, FTS indexing, `import_txt(path)`, `reparse_all()`
- [ ] Migration in `core/database.py` — `slide_decks` + `slides_fts` + triggers, bump `CURRENT_SCHEMA_VERSION`
- [ ] Storage dir convention: `data/slides/*.txt` (import via file picker; optional watcher later)

### Phase 2: Basic UI (txt-driven, no Lite Designer yet)
- [ ] `ui/tabs/slides_tab.py` — deck list (title, slide count, updated_at), import txt button, delete, basic search bar
- [ ] Add "SLIDES" tab to `main_window.py` (lazy-loaded like others)
- [ ] Slide preview: click deck → show ordered slide cards (section label muted, text rendered with hardcoded theme)

### Phase 3: Display & Schedule Integration
- [ ] Slide-by-slide display via existing WebSocket/OBS payload (one slide = one payload, theme applied)
- [ ] Schedule integration: `item_type` on schedule items (`"verse"` | `"slide"`), multi-slide sequencing (shared `deck_id` + `slide_index`), Prev/Next steps through slides
- [ ] Rolling/scrolling mode: joined slide text + separator, speed from `config.json` (defer until slide-by-slide solid)

### Phase 4: EasyWorship Import (after txt flow works)
- [ ] DB schema analysis (user provides DB file)
- [ ] Field mapping → `slide_decks` (title/author/year/ccli → columns, lyrics → `slides_json` via section inference)
- [ ] Batch import with dedup (title+author or CCLI)

### Phase 5: Search (FTS + optional BM25)
- [ ] FTS5 instant search over `slides_fts` (porter stemming — "basic stemming" per spec)
- [ ] Ranking: title match > slide_text match > tags match; tie-break by `created_at` or `updated_at` (or explicit relevance toggle)
- [ ] No semantic/indirect search — lexical only, must handle millions of lines "in a jiffy"
- [ ] Optional: per-deck BM25 via `rank-bm25` if FTS ranking insufficient

### Deferred (Lite Designer + Theme Designer)
- Lite Designer: per-slide text transforms (ALL CAPS, bullets, font/typeface, size, color, shadow/outline intensity/size), bg image/video via webhook
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
- Literal double-space inside a slide vs slide boundary — unsolved; leaning blank=boundary for now.
- `#`/`%` after title set: ignore vs treat as text — default ignore, revisit if users title mid-deck.