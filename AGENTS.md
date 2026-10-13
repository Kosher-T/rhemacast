# AGENTS.md — RhemaCast

## Project Overview

RhemaCast is a real-time sermon transcription system that captures live audio, transcribes it via GPU-accelerated STT (Faster-Whisper / Vosk fallback), searches a Bible index (BM25 + FAISS), and pushes verse suggestions to an HTML display over WebSocket. PyQt6 desktop UI for operator control.

## Quick Commands

```bash
# Run the app (must have venv activated or use venv/bin/python)
python debug.py

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
