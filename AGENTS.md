# AGENTS.md — RhemaCast

## Project Overview

RhemaCast is a real-time sermon transcription system that captures live audio, transcribes it via GPU-accelerated STT (Faster-Whisper / Vosk fallback), searches a Bible index (BM25 + FAISS), and pushes verse suggestions to an HTML display over WebSocket. PyQt6 desktop UI for operator control.

## Quick Commands

```bash
# Run the app (must have venv activated or use venv/bin/python)
python debug.py

# Dev-only dialog/popup gallery (every dialog kind, combo, menu, tooltip)
python dev/ui_gallery.py

# Run all tests
python -m pytest tests/ -v

# Run a single test file
python -m pytest tests/test_phase2_core.py -v

# Run a single test
python -m pytest tests/test_service_manager.py::test_boot_sequence -v

# Rebuild Bible database from source files
./data/bible/convert.sh ~/Downloads/

# Rebuild DB only (JSON files already exist)
./data/bible/convert.sh --db-only

# Verify Bible DB integrity
python data/bible/verify_db.py
```

## Environment Setup

1. `python3 -m venv venv && source venv/bin/activate`
2. `pip install -r requirements.txt`
3. Copy `.env.example` → `.env` and fill in API keys (Gemini, Claude, Groq, OpenAI)
4. For Bible data: place source XML/XMM/CSV files in `~/Downloads/` and run `./data/bible/convert.sh`

The venv must be at project root (`venv/`). The `convert.sh` script hardcodes `venv/bin/python`.

## Architecture

6 threads coordinated via `core/service_manager.py`:

| Thread | Module | Role |
|--------|--------|------|
| Main | `core/ui.py` → `ui/main_window.py` | PyQt6 UI, hotkeys |
| T1 | `core/audio_capture.py` | PCM capture → Queue A |
| T2 | `core/stt_inference.py` | Faster-Whisper (GPU) → Queue B |
| T3 | `core/search_engine.py` | BM25 + FAISS → operator queue |
| T4 | `core/db_writer.py` | SQLite + flat file writes |
| T5 | `core/hardware_monitor.py` | GPU temp polling (pynvml) |
| WS | `core/websocket_server.py` | Push payloads to `display/display.html` |

Shutdown cascade: poison pills pushed through Queue A → B → DB queue.

## Key Directories

- `core/` — all backend modules (STT, search, DB, threading, config)
- `ui/` — PyQt6 UI (main window, panels, tabs, widgets, styles)
- `data/bible/` — Bible source conversion pipeline (`convert.sh`, `bible_to_json.py`, `build_db.py`)
- `data/indexes/` — BM25 pickle, FAISS index, verse lookup pickle
- `display/` — HTML/JS/CSS renderer served via WebSocket
- `cloud/` — Cloud extraction module (`extraction.py`)
- `tests/` — pytest files organized by phase

## Conventions

- **Constants** live in `core/constants.py` — never hardcode magic numbers elsewhere
- **App colors** live in `ui/app_theme.py` (roles: grey/black backgrounds, purple accent, purple selection) — new UI code must use the `ACCENT_*` / `SELECTION_*` / `BG_*` roles via `ui.styles` aliases, never hardcoded hex/rgba; add a theme by adding one dict entry
- **Config** schema + defaults in `core/config_schema.py` — auto-creates `config.json` on first run
- **Queues** defined in `core/queues.py` with `POISON_PILL` sentinel for shutdown
- **Splitter layouts** persist via `core/panel_layout.py` (`track_splitter` at build + `restore_splitter` on show; debounced saves to `layout.splitter.*` settings)
- **Events** are dataclasses in `core/events.py` (TranscriptChunk, SearchResult, etc.)
- **Errors** hierarchy in `core/errors.py` — Continue → Degrade → Failover → Shutdown
- **Intent classifier** is pure regex from `data/intent_triggers.json` (< 1ms, no ML)
- **Keyword (FTS) lane** ranks on keyword match only: coverage counted from the verse text (most distinct query words wins) → literal-phrase adjacency → FTS5 bm25. Recall is AND-first; a thin AND set adds one bounded OR sweep over the longest stems (`FTS_PARTIAL_*`), not per-word probes. No semantic blending, no BM25 postings rerank, no typo widening — a verse carrying 5 of 6 words must still beat a 1-of-6 single-word hit
- **Embedding model** loads with ONNX CPU backend: `backend="onnx", model_kwargs={"provider": "CPUExecutionProvider"}`

## Themes System

- Theme JSON files live in `themes/scripture/` (verse themes) and `themes/freeform/` (song/slide themes) — never mixed; `get_themes_by_kind()` filters, schedule menus group by kind
- Each theme defines 20 CSS custom properties (`--rc-*`) for container, text, reference, and translation styling
- `core/theme_loader.py` lazy-loads and caches themes by name; `get_theme(name)` returns the full dict
- Operator selects themes via `ThemesPanel` (inside QueuePanel's tab bar)
- `PresentationTab._on_theme_changed(name)` stores theme and re-broadcasts current verse with `theme_data`
- **Panel focus rings** — `ui/focus_ring.py` `install_focus_ring(panel)` lights a themed accent overlay while the panel (or any descendant) holds focus; used by the bible (`BrowserPanel`) and `SchedulePanel` panels. It is a painted overlay child, NOT a QSS border: a QWidget subclass ignores QSS background/border without `WA_StyledBackground`, and an overlay can neither reflow the panel's contents nor swallow clicks (`WA_TransparentForMouseEvents`). Focus tracking uses the app-wide `focusChanged` signal (a panel counts as focused when any descendant holds focus)
- WebSocket payload includes `"theme_data": get_theme(name)` — the full theme dict
- `display/display.js` applies themes via `applyTheme()` which sets CSS custom properties on `:root`
- `display/themes.css` uses `var(--rc-*, fallback)` for all styling — transparent background for OBS overlay

## App Typography

- `ui/typography.py` `install(app)` runs in `RhemaCastApp.__init__` (after `QApplication`, before any widget): registers the bundled Inter faces in `ui/assets/fonts/` (Regular/Medium/SemiBold/Bold + `OFL.txt`) and sets the app `QFont` — 13px, weight 500, `PreferAntialias` + full hinting. Never `QApplication.setFont` anywhere else
- `RHEMA_TEXT_MODE` A/B switch: `full` (default, full hinting), `none` (no hinting), `legacy` (pre-typography: system font, Qt defaults)
- `install()` verifies the family Qt actually reports (`applicationFontFamilies`) instead of assuming the file name; a missing/corrupt bundle falls back to Inter → Noto → DejaVu → Sans Serif
- Sizes in code are **defaults, never enforcement**. Per-area type is settings-backed in Settings → Interface; the operator's saved value is used as-is, at whatever size they picked — do not clamp it on read. The 12/13px choices are simply today's defaults
- Ten font groups, each with `<prefix>.font_family` / `_weight` / `_size` settings keys and a Settings → Interface card: `bible.verse` (13/400), `bible.ref` (12/700), `slides.strip` (13/400), `slides.deck` (13/400), `slides.editor` (13/400), `search.result` (13/400), `search.ref` (12/700), `tabs.names` (12/600 top bar, 12/700 sub-page row), `panel.labels` (13/600; SlideGrid captions default 12/700, LIVE 13/700), `schedule.cards` (ref 12/600, theme 12/400, rename 13/400). Consumers call `area_font(prefix, size_default, weight_default, size_min=..., size_max=...)` + `font_qss()` — never hardcode a size
- Search/translation/navigator chrome joins the same groups: the translation bar reads `panel.labels` (buttons 12/700, + Add 12/600, and the Add button is not a translation — sorts must leave it pinned after the stretch), the Bible navigator (book/chapter/verse + colon) reads `bible.verse` (fields 13/600, colon 14/500), Keyword/Semantic query boxes and the book filter read `search.result` (13/500), and the Deck List search box reads `slides.deck` (13/500); their placeholders inherit the box font
- **Navigator numbering is a tandem**: chapter and verse share one fitted lane (`_fit_numeric_fields`, three digits reserved, 48px at the default font) and centre their digits; editing the book resets chapter+verse to 1, editing the chapter resets verse to 1 — on the edit itself, not on the next Space/arrow commit. Programmatic writes (`set_values`, `reset`) hold the rule off via `_tandem_suppressed`, and one edit must produce one `navigate_requested`
- Chrome that is always on screen (top tab names, text-tab rows, panel headers, schedule rows) re-reads its group live: `subscribe_interface_font_changed(cb)` / `notify_interface_font_changed(prefix)` in `ui/app_theme.py` (lazy QObject bus; Settings saves emit it). New always-visible text should join this path instead of needing an app restart
- Slide/deck *content* is authored separately in points (`rich_txt.py`, painters) — UI size defaults do not apply there
- Only three weights are in use: 500 body (the app font default), 600 section labels/emphasis, 700 headings. `accent_text` (not `accent`) is the accent-coloured *text* role; `accent` stays a fill/border
- Do not re-add `WA_TranslucentBackground` to `MainWindow`: an RGBA top-level surface forces grayscale glyph antialiasing for the whole window

## Operator Display Behavior

- **Single-click verse** → updates Preview screen only (like navigator highlight)
- **Double-click verse** → updates both Live + Preview screens, broadcasts to OBS via WebSocket
- **Double-click Preview screen** → pushes Preview content to Live screen
- **Queue "Show" button** → updates both Live + Preview, broadcasts to OBS
- **Prev/Next buttons** → navigate schedule, update both Live + Preview
- **Clear/Recall (Esc)** → clears both screens; recall shows last cleared verse
- **Theme change** → re-broadcasts current verse with new theme to OBS
- Live and Preview screens render with the selected theme so the operator sees what OBS will display

## Testing

- Tests are phase-organized: `test_phase1_indexes.py` through `test_phase10_cloud.py`
- `test_service_manager.py` tests the state machine / restart / failover logic
- Service manager tests use `autouse` fixture to reset global `threading.Event` state
- No CI pipeline — tests run locally only
- Fuzzy BM25 + FAISS must be rebuilt together from `FUZZY_TRANSLATIONS` or fingerprint tests fail: `python data/bible/build_bm25.py --fuzzy --translations NLT,BIBLE_ENGLISH_MSG,BSB,AMP,NIV` then `python data/bible/build_faiss.py` (needs HF cache for MiniLM; ~17 min encode)
- `test_phase9_ui.py` boots the full app and aborts headless (native QtWebEngine crash) — excluded from local runs

## Gotchas

- `sqlite3` and `unittest.mock` are stdlib — do NOT pip install them
- `faster-whisper` uses CTranslate2, not PyTorch directly — verify CUDA with `python -c "import ctranslate2; print(ctranslate2.get_cuda_device_count())"`
- Bible translations (NKJV, NIV, ESV, NLT, AMP) are copyrighted — only KJV is public domain. Do not commit copyrighted texts.
- `config.json` is gitignored — it self-generates from `DEFAULT_CONFIG` in `config_schema.py`
- Queue A backpressure: never drop audio; failover triggers if depth > 400
- GPU thermal limits: critical at 82°C, safe at 70°C — defined in `core/constants.py`
- `data/schedules/` is gitignored — it holds the operator's live service plans, not source

## Settings Field Chrome — handover (2026-10-30)

`ui/field_chrome.py` now owns every Settings tab combo and spin box (the
font row, the seven standard combos, both standard spins, and the four
compact Database/Keywords combos). The shared `COMBO_STYLE` / `SPIN_STYLE`
remain in `settings_tab.py` for other tabs but must not be applied to
Settings fields again.

Non-negotiables, learned from the reverted attempt:

- **One stylesheet, replacing not appending.** `COMBO_STYLE` and
  `SPIN_STYLE` both declare `::down-arrow`. QStyleSheetStyle paints every
  matching subcontrol rule, so keeping the old sheet while adding the new
  one paints two marks. `field_chrome.apply_combo/apply_spin` set the
  widget stylesheet; never append a second arrow rule.
- **State selectors go on the subcontrol.** `QComboBox:hover::down-arrow`,
  `:disabled::down-arrow` and `QSpinBox:hover::up-arrow` do not brighten
  the image and position a second copy at the widget centre. Use
  `::down-arrow:hover`, `::down-arrow:disabled`, `::up-arrow:hover` and
  repeat `subcontrol-origin` / `subcontrol-position` in every arrow rule.
  This is the exact cause of the old "chevron mid-field plus chevron at
  the right edge" symptom.
- **QSS heights are content-box heights.** `COMBO_HEIGHT` is the outer
  height (28); the helper subtracts the 2px border. Compact is 27px
  (17 content + 8 padding + 2 border). Never feed outer heights straight
  to `min-height` / `max-height`.
- **Spin buttons live inside the inner rect.** `subcontrol-origin:
  padding`, width `SPIN_BUTTON_WIDTH`, height half the inner height,
  top/bottom right, no gap. No fill (it would poke through the rounded
  corners). `padding-right` is derived from the button width.
- **Chevrons are generated PNGs.** Lazy QImage/QPainter files under
  `<tempdir>/rhemacast-field-arrows-<hash>/`, 12×12 plus @2x 24×24,
  written tmp-file + `os.replace`, referenced with a plain
  `Path.as_posix()` URL. QPixmap before QGuiApplication crashes. Never
  install an application stylesheet after the bundled Inter font;
  `core/ui.py`'s order (Fusion → sheet → typography → palette) holds.
  No `core/ui.py` change is needed for this chrome.

Verification:

- `tests/harness/field_chrome.py` renders textless fields, excludes the
  border, and counts connected components. Expected: 1 per combo, 2 per
  spin, in normal/hover/focus/disabled. Do not weaken this to "an arrow
  is visible".
- `tests/test_settings_fields.py` (39), `tests/test_tokens.py` (26),
  `tests/test_style_dialogs.py` (13), each run separately with
  `QT_QPA_PLATFORM=offscreen` and `timeout 120`.
- `tests/test_interface_font.py` (13) and `tests/test_search_auto_delay.py`
  (6) also construct SettingsTab and pass.
- `tests/test_output_sets.py` passes its 25 tests, then the interpreter
  segfaults during headless QtWebEngine teardown. That is a process-exit
  issue, not a test failure; do not chase it as a styling regression.

Known state:

- Focus paints the accent border only; the chevron stays at normal
  brightness. Hover brightens it; disabled dims it.
- Pressed spin buttons deliberately have no fill.
- Compact combos keep their measured 27px height, 120px min-width, no
  max-width and 12px type; radius moved from 4 to the shared 6.
- The restyle is commit `1772879` on local `master`. Phase patches and
  screenshots were in `/tmp` and are not versioned.
