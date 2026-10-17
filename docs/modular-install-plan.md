# RhemaCast Modular Install Plan

Users download only what they want. The installer offers packs; the app
boots exactly what was installed — structure is decided at install time,
never second-guessed at runtime.

> Status: PLAN ONLY. Nothing below is implemented.

## Pack map

**Core (always installed):** Settings, History, Library, Theme Designer
tabs · Schedule panel · display pipeline (`websocket_server`, `display/`,
slide-format parsing) · `database`, `schedule_model`, `theme_loader`,
`config`, queues/threading, startup.

**Packs (at least one required, default: Scriptures):**

| Pack | Contents |
|---|---|
| Scriptures | Bible service, FTS + fuzzy search, verse UI |
| Slides | Decks, slide service, EasyWorship import |
| STT | Speech-to-text, operator review queue, audio capture |
| Audio-Video | *Future slot* |
| Presentation | PPTX files, *future slot* |

## Design principles

- **`packs/manifest.json`** is the single source of truth: per pack, its
  id, name, default-on flag, requirements file, data dirs, tabs, threads,
  and settings sections.
- **Core knows packs only through the manifest.** Tab creation becomes
  `for tab in manifest.enabled_tabs(): registry.build(tab)`. Cross-pack
  calls check `packs.has("x")` and hide/no-op otherwise.
- **No pack imports another pack.** Shared contracts (slide-format
  payloads, schedule items) stay in core.
- **The installer is the only place structure is decided.** On boot the
  app reads the installed-pack list and builds exactly that. No
  "download missing pack?" prompts inside the app (v1).

## Pack-grouped sections inside core tabs

Library, Settings, and History stay core, but their *contents* are tagged
by the pack they serve (internal tags only, never shown in the UI):

- **Library** — translations management → `scriptures`; deck/song
  library → `slides`; verse-history views → `scriptures`; pack-agnostic
  browsers/lists stay unconditional.
- **Settings** — audio ingestion + STT → `stt`; FTS/fuzzy/search tuning
  → `scriptures`; deck/slide sizes, nav mode → `slides`; Interface font
  section stays core. Sections hide when their pack is absent.
- **History** — scripture-verse entries → `scriptures`; deck/slide
  entries → `slides`.
- A helper (`packs.visible("scriptures")`) resolves visibility at build
  time; sections register `(widget, pack)` pairs so install/uninstall can
  re-resolve without restart where cheap.
- A tab with zero visible sections still opens with an empty-state message
  naming the missing pack — core tabs never crash on exotic combinations.

## Queue panel → STT pack

The operator review queue (STT search hits awaiting push) belongs to STT:
`queue_panel.py` + its worker wiring loads only with the pack. The shared
display pipeline stays core — the queue produces payloads through it.
No STT pack → no queue UI anywhere.

## Bible data policy

- Ship **KJV + other public-domain/open translations only**, plus the
  indexing script. No prebuilt indexes containing copyrighted text, ever.
- The indexing script must be **cross-platform** (today's `convert.sh` +
  hardcoded `venv/bin/python` is Linux-only) — rewrite as Python so
  Windows/macOS run the identical path.
- Installer offers *"Download open translations"* (KJV default, others
  opt-in), then *"Build search index locally"* with progress. Users with
  licensed texts point the script at their own files, as today.

## Installer GPU probe + STT model picker

Shown only if STT is picked, between pack selection and download:

1. **Detect** — NVIDIA (NVML/`nvidia-smi`), Apple Silicon (MPS),
   AMD/DirectML note, else CPU-only; VRAM estimate where readable.
2. **Verdict screen** — plain language: GPU + enough VRAM → "STT will run
   well"; weak/none → "CPU only (slower, still usable)" or "below minimum
   — not recommended," with the option to unpick STT and continue. The
   verdict never blocks the rest of the install — it only gates STT.
3. **Model picker** — Faster-Whisper list (tiny → large, sizes + VRAM/RAM
   notes + recommendation badge from step 2); Vosk small as lightweight
   fallback. Weights download into the STT pack dir.
4. Persist `stt.model` / `stt.device` so first boot needs no configuration;
   later changeable in Settings.

## Known complications (from the tree)

1. Library imports `bible_service` in 4 places → degrade gracefully.
2. `STTPanel` is built by `presentation_tab.py`; STT thread by
   `service_manager` → both need extraction.
3. `main_window.py` hardcodes all tabs + cross-tab calls
   (History Ctrl+click → Scripture, queue workers, hotkeys) → registry +
   capability guards.
4. Heavy deps are global (`faster-whisper`, `vosk`) → split per pack:
   `requirements-core.txt`, `requirements-scriptures.txt`,
   `requirements-stt.txt`, `requirements-slides.txt` (+ future files).
5. `data/bible/` + `data/indexes/` ship with Scriptures; user data
   (`schedules/`, decks) stays local and pack-agnostic.
6. Deck `shadow=` doesn't survive `format_to_line` today — fixed on the
   road here; deck format round-trips through Save.

## Installer mechanics (MVP)

Python script first, native binary later: checkboxes (Scriptures
pre-checked, Next disabled until ≥1 checked) → `pip install -r` core +
chosen packs → GPU probe + model pick if STT → per-pack data builds
(translations download, local index build) → write the enabled-pack list
that `main_window` reads. Uninstall removes the pack dir + prunes the
manifest; user data untouched.

## Migration phases

0. **Manifest + tab registry**, all packs present — zero behavior change.
1. **Dependency hygiene** — lazy imports, `packs.has()` guards, section
   `packs:` tagging (Library/Settings/History), queue extraction prep.
2. **Split requirements + data**; per-pack venv install tested.
3. **Extract STT UI/boot** from the Scripture tab; pack-aware
   `service_manager` boot.
3b. **GPU probe + verdict + model picker**; cross-platform index script.
4. **Installer MVP** (pip-based).
5. **A/V + PPTX** fill their stub slots.
6. **Combination matrix in tests** — core-only, core+each-pack,
   all-packs (STT × GPU-verdict mocked) — a missing pack can never crash
   boot.

## Open questions

1. Library without Scriptures: hide just the translations UI, or does it
   lose import flows too?
2. Queue confirmed STT-side; anything else review-like living in core?
3. Installer: offer heavy Bible-index *build* only, or also indexed
   downloads for open texts?
