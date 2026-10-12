# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

**Primary:** Live service operators (media techs, pastors, worship leaders) running the broadcast during a church service.

**Situation:** Standing/sitting at a workstation during a live service, managing real-time transcription and verse display. High cognitive load — listening to the sermon, watching transcription, selecting verses, pushing to OBS. Cannot afford errors or hesitation.

**Job:** Capture live audio → transcribe in real-time → AI suggests relevant Bible verses → operator reviews/approves → broadcasts verse to OBS overlay for congregation display.

## Product Purpose

RhemaCast replaces the manual workflow of a media operator frantically searching for Bible verses during a sermon. It listens, transcribes, understands the sermon context, and serves up the exact verse the pastor is quoting — so the operator just clicks "Show" and the verse appears on the screen behind the speaker.

**Success means:** The verse is on screen before the pastor finishes the sentence. The operator never types a reference. The congregation sees the Word, not a blank slide.

## Positioning

The only sermon transcription system that couples GPU-accelerated STT with a dual-search engine (BM25+FAISS semantic + FTS5 exact-match) and an operator review queue — all in a single desktop app that outputs a clean OBS browser source. No cloud dependency for core loop. No monthly subscription. Runs on the operator's machine.

## Operating Context

- **Environment:** Windows 10/11 or Linux (Ubuntu/Fedora), desktop app (PyQt6)
- **Hardware:** NVIDIA GPU required for STT (RTX 3060 12GB+ recommended). 16GB+ RAM. 
- **Audio input:** Any Windows/Linux audio device (USB interface, virtual cable, loopback).
- **Output:** OBS Browser Source pointed at `ws://localhost:8765` (WebSocket) serving `display.html`
- **Bible data:** Local SQLite (bible.db) + prebuilt indexes (BM25, FAISS, FTS5). Six translations built-in (KJV, NKJV, ESV, NLT, AMP, BSB). User can import more.
- **Service workflow:** Operator launches app → starts transcription → verses auto-populate queue → single-click "Show" → verse pushes to OBS. Hotkeys for everything (F6 clear/recall, arrows for schedule, D for double-click).

## Capabilities and Constraints

**Core loop (6 threads coordinated by ServiceManager):**
1. Audio capture (PCM → Queue A)
2. STT inference (Faster-Whisper GPU → Queue B) 
3. Search (BM25 + FAISS hybrid → operator queue)
4. DB write (SQLite + flat files)
5. Hardware monitor (GPU temp via pynvml, thermal throttling at 82°C)
6. WebSocket server (pushes verse payloads to display.html)

**Operator UI (PyQt6):**
- Three-panel layout: Schedule | Live Preview | STT (top), Bible Browser (bottom)
- Bible browser: full chapter view, translation bar, predictive input (Book|Chapter:Verse), navigator highlight
- Queue panel with tabs: Review Queue / Themes / FTS Search / Fuzzy Search
- Live preview mirrors OBS output; double-click preview → pushes to live
- Theme system: 3 built-in themes (Standard/Fullscreen/Reference), JSON-defined CSS variables

**Search:**
- **Fuzzy (FAISS+BM25):** Semantic search across all verses, all 6 translations. Natural language queries. "God's love never fails" → Romans 8:38-39.
- **FTS (exact match):** FTS5 + BM25 per translation. Exact phrase "harvest is plenteous" → Matthew 9:37 (KJV). Results ordered by relevance (RRF fusion), auto-scroll to top match.

**Themes:** JSON files with 20 CSS custom properties (`--rc-*`) controlling container, text, reference, translation styling. Applied to both operator preview and OBS display via WebSocket payload.

**Hotkeys:** User-configurable in Settings. Default: F6 clear/recall, ←/→ prev/next verse, D simulate double-click, Ctrl+Shift+F FTS search, Ctrl+Shift+S fuzzy search.

**Constraints:**
- No cloud required for core loop (STT runs locally via CTranslate2)
- Bible text licensing: KJV public domain; NKJV/NIV/ESV/NLT/AMP/BSB require user-provided source files
- Queue max 50 items (virtual scrolling)
- GPU thermal limits: critical 82°C, safe 70°C (auto-pauses STT)
- Config auto-generated at `config.json` (gitignored)

## Brand Commitments

- **Name:** RhemaCast (fixed)
- **Voice:** Technical but accessible. "Sermon transcription that keeps up."
- **Assets:** App icon (cross + soundwave), OBS browser source (display.html)
- **Identity constraint:** Transparent background for OBS overlay is non-negotiable

## Evidence on Hand

- Working desktop app (PyQt6) with 6-thread service manager
- Display output: `display/display.html` + `themes.css` + `display.js`
- 3 themes: Standard (default.json), Fullscreen (fullscreen.json), Reference (reference.json)
- Bible pipeline: `data/bible/convert.sh` → SQLite + FTS5 + BM25 + FAISS indexes
- Tests: `tests/test_phase*.py` (7 phases)
- Documentation: `docs/*.md` (architecture, threading, search, GPU, display, operator guide)

## Product Principles

1. **Operator never types a reference** — predictive input, search, schedule, queue all feed navigation
2. **Verse on screen before pastor finishes** — sub-second STT + search pipeline, hotkeys for everything
3. **Transparent OBS overlay** — display.html has no background; themes control text only
4. **Local-first, no subscription** — all indexes, STT models, Bible data on disk
5. **Thermal safety is not optional** — GPU monitor pauses STT before hardware throttles
6. **Single source of truth for themes** — JSON → CSS variables → both preview and OBS
7. **Schedule is references only** — fast, lightweight, versioned separately from Bible data