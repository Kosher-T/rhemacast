# RhemaCast — Working Roadmap Checklist

_Created 2026-11-09. This is the working order, not a contract. Move whole
sections freely; keep the IDs with their tasks so links and notes never break._

_Order revised 2026-11-09: STT hardening moved to M3, a Windows-battery/UI
optimization milestone added as M4, and the later milestones renumbered._

## How to use this

- Work top to bottom inside the current milestone. The first unchecked box is
  the next thing to do.
- Each milestone ends with a **Done when** gate. Do not start the next
  milestone until that gate is true.
- Between milestones, take one **10-minute deviation** — a small, real fix that
  needs no design meeting. Then return to the main line.
- A milestone can be split or reordered. Keep the IDs (`M1-07`, `M4-05`, …) on
  the issue so the history survives the move.
- When a task reveals a new problem, add it under the milestone instead of
  silently expanding scope.

## Current order

| # | Milestone | ID | Depends on |
|---|---|---|---|
| 1 | Theme Designer — intuitive theme file GUI + preview | M1 | — |
| 2 | Scriptures tab UI improvements | M2 | — |
| 3 | STT flow hardening | M3 | current STT stack |
| 4 | Optimizations — Windows battery + UI snappiness | M4 | M1–M3 (measure the real app) |
| 5 | Segmentation into installable packs | M5 | M1, M2 stable |
| 6 | Image streaming as the third display tab | M6 | M5 (manifest), outputs 7–8 |
| 7 | Deck tab UI improvements | M7 | M2 patterns |
| 8 | Video + audio streaming as another display tab | M8 | M6 (media library), outputs 9–10 |
| 9 | More Deck tab UI improvements | M9 | M7, M8 |

> **Design rule for every milestone:** the operator should never have to guess
> whether an action changes the Preview or goes live to OBS. If a new control
> can do either, its label must say which.

---

## M1 — Theme Designer

**Goal:** The Theme Designer becomes the obvious, safe way to author every
theme file: no JSON required for normal work, no silent key loss, and a preview
that matches OBS exactly.

**Source docs:** `docs/theme_designer_spec.md`, `docs/theme_designer.md`,
`docs/theme_file_reference.md`, `docs/theme_schema_v2.md`,
`docs/lite-designer-plan.md`

**Done when:** every v2 property is either editable in the GUI or explicitly
marked “raw JSON only”; every shipped theme survives load → edit → save with
zero lost keys; the three previews match OBS at 1920×1080; and a new user can
change a theme color, size, border, and animation without opening the JSON
editor.

### Discover and decide

- [ ] **M1-01 — Property coverage matrix.** Walk every key in
      `docs/theme_file_reference.md` and mark it: editable now, needs a control,
      preserve-only, or intentionally raw. Store the matrix in
      `docs/theme_designer_spec.md` so it cannot rot.
- [ ] **M1-02 — Showcase audit.** Drive all eight showcase themes through the
      Full Designer and Quick Editor. Log every field that renders differently,
      refuses to save, or cannot be selected.
- [ ] **M1-03 — Scope decision.** Write down whether v1 of the revamp is “full
      GUI parity” or “90% GUI + raw JSON for advanced fields.” Put the answer
      in the spec before building controls.
- [x] **M1-04 — One property editor, three entry points.** All three mount
      `ThemePropertyEditor`; the Full Designer binds the tab-owned document,
      and Quick/Lite use standalone snapshots. The font-drift regression is in
      `tests/test_theme_quick_lite_shared_editor.py`.
- [ ] **M1-05 — Undo/redo + dirty model.** Decide what one undo step is (field,
      block, document), how unsaved changes are detected, and when a save is
      refused. Write the rule in the spec.
- [ ] **M1-06 — Fix the known key-loss risk.** The Lite Designer plan notes that
      `ThemePropertiesPanel` rebuilds can drop unmanaged keys
      (`text_transform` / `text_align` were lost from `fullscreen.json`).
      Reproduce it, fix it, and add a regression test using a theme with
      unknown + advanced keys.
- [ ] **M1-07 — Clear the inherited test debt.** Resolve the three pre-existing
      `tests/test_lite_designer_theme_awareness.py` failures by making the test
      and the Lite Designer agree on the real preview API. Do not skip them.

### Build the shell

- [ ] **M1-08 — Persistent three-pane shell.** Properties | previews |
      animation/JSON, resizable with `core/panel_layout.py` splitter
      persistence.
- [ ] **M1-09 — Container strip.** List every container; add, duplicate, delete,
      reorder, toggle visibility, and set `layer`. Show the active container
      clearly.
- [ ] **M1-10 — Block tabs.** Body / text / reference / translation / verse_num
      tabs with visible toggles and per-block reset.
- [ ] **M1-11 — Canvas panel.** Width, height, background, `fit`, plus a
      “reset to 1920×1080” action.
- [ ] **M1-12 — Property search and reset.** Filter the property list by name;
      show a “changed from default” marker and a per-field reset.
- [ ] **M1-13 — Validation panel.** Surface `ThemeReport` warnings/errors with
      click-to-field navigation. A save that would produce warnings must say so
      before it writes.
- [ ] **M1-14 — Shared definitions browser.** Pick borders/shadows from
      `themes/_shared/*.json`, insert `@palette` tokens, and preview the
      resolved value. Do not hide shared refs behind raw JSON.

### Build the editors

- [ ] **M1-15 — Container geometry.** Semantic anchor + numeric offsets;
      drag/resize writes the numbers and the numbers move the box. Include
      `min_width` / `max_width` / `min_height` / `max_height`.
- [ ] **M1-16 — Border and shadow editors.** Base border, per-side
      `border.sides`, `border_radius` override, structured shadow, and shared
      references. Show the same result the renderer will paint.
- [ ] **M1-17 — Background editor.** Solid, gradient, transparent/none, and
      palette tokens with a live swatch.
- [ ] **M1-18 — Typography editor.** Family, size, `min_size`, `max_size`,
      `autosize`, weight, line-height, letter-spacing, alignment, transform,
      decoration, outline, shadow, margins, `max_lines`, and visible.
- [ ] **M1-19 — Animation library CRUD.** Create, duplicate, rename, delete;
      edit preset timing/easing/origin and custom keyframes; show which slots
      use a definition before deletion.
- [ ] **M1-20 — Slot assignment.** Entry, exit, and transition in/out for the
      container and every block, on a simple visual timeline. Include a
      “replay” button.
- [ ] **M1-21 — Split editor.** `by` line/word, `stagger_ms`, first/rest slot
      assignments, first/rest looks, and a live unit-count readout from the
      preview. Reject nested split with a clear message.
- [ ] **M1-22 — Raw JSON editor.** Syntax highlighting, validate, format,
      apply/revert, and two-way sync with the GUI. Never let an invalid apply
      destroy the last good document.
- [ ] **M1-23 — File lifecycle.** Import, export, duplicate, rename, delete,
      unsaved-changes guard, and hot reload after save.
- [ ] **M1-24 — Preview that is the renderer.** Use the real display engine,
      not a mock. Add short/medium/long verse samples, a freeform sample,
      blank-block states, play/replay, before/after compare, 16:9 and OBS-size
      zoom, and safe-area guides.

### Prove it

- [ ] **M1-25 — Round-trip gate.** For every shipped theme: load, touch a
      representative field in each group, save, re-resolve, and assert zero lost
      keys and zero new warnings.
- [ ] **M1-26 — Designer smoke test.** Headless or offscreen UI pass that
      opens every pane, switches every block tab, and saves without error.
- [ ] **M1-27 — Keyboard and accessibility pass.** Every control reachable by
      Tab, sensible focus order, accessible names on icon-only buttons.
- [ ] **M1-28 — Performance pass.** Dragging and resizing must not reflow the
      document; preview updates debounce; 60 fps on the target machine.
- [ ] **M1-29 — Spec refresh.** Update the “Cannot Edit Yet” list and the
      property coverage matrix; link the new doc anchors from tooltips.

### 10-minute deviations after M1

- [ ] Add “Copy theme name” and “Duplicate theme” to the theme context menu.
- [ ] Put a “Docs” link on each property group that jumps to the matching
      `theme_file_reference.md` anchor.
- [ ] Show a small validation badge on theme cards with warnings.
- [ ] Remember the last selected container and block per theme.
- [ ] Add “Reset this block” with a confirmation dialog.

---

## M2 — Scriptures tab UI improvements

**Goal:** The live-service surface becomes faster to read and harder to
mis-click: one clear path from reference to preview to live.

**Source docs:** `docs/display_and_broadcast.md`, `docs/search_engine.md`,
`docs/operator_guide.md`, `docs/design-principles.md`

**Done when:** the core flow (type a reference → see it in Preview → push it
Live) is fully keyboard-driven; no panel header or control clips at 1366×768;
and a first-time operator can tell Preview from Live without being told.

### Discover

- [ ] **M2-01 — Operator flow audit.** Walk the full service flow: find verse,
      preview, push, clear, recall, schedule, search, review queue. Write down
      every moment that needs a mouse or a guess.
- [ ] **M2-02 — Size audit.** Screenshot the tab at 1366×768, 1920×1080, and
      Windows 125%/150% scaling. Log clipped labels, overlapping splitters, and
      panels that collapse below usefulness.
- [ ] **M2-03 — Panel hierarchy review.** Schedule | Live Preview | STT/History
      rail | Browser | Queue/Themes/Search. Decide what always deserves space
      and what can collapse.
- [ ] **M2-04 — Primary-job rule.** Define the three jobs that must never be
      more than one click away, and remove or demote anything that competes
      with them.

### Build

- [ ] **M2-05 — Header and spacing pass.** Use the existing token scale and
      typography groups; unify panel headers, section labels, and inner
      padding so the tab reads as one surface.
- [ ] **M2-06 — Keyboard flow.** Book → chapter → verse → verse list → search
      box → queue, with visible focus and no focus traps. Keep the navigator’s
      tandem edit rule intact.
- [ ] **M2-07 — Click affordance.** Make single-click Preview vs double-click
      Live obvious: hover text, a small legend, and no accidental live pushes.
- [ ] **M2-08 — Queue card hierarchy.** Reference, confidence, verse snippet,
      Show/Reject. Add a compact mode and keep the 50-item cap responsive.
- [ ] **M2-09 — Search states.** Empty, loading, no-results, and error states
      for keyword and semantic search. Highlight the matching words and show a
      result count.
- [ ] **M2-10 — Translation bar overflow.** Pinned “+ Add” after the stretch;
      a “more” menu when translations do not fit; no clipped names at narrow
      widths.
- [ ] **M2-11 — Schedule feedback.** Clear drag handle, drop target, reorder
      affordance, and empty state. Keep the schedule ring behavior intact.
- [ ] **M2-12 — STT/History rail.** A clear recording/STT state, audio level,
      last transcript, and an error/retry state that does not require a restart.
- [ ] **M2-13 — Preview vs Live labels.** Persistent labels and a selection
      ring; double-click Preview to push should be discoverable, not folklore.
- [ ] **M2-14 — Sub-tab row.** Themes/Search and STT/History active states,
      keyboard switching, and persistence of the last active page.
- [ ] **M2-15 — Focus mode (optional).** A toggle that hides the schedule and
      queue rails to give the browser and preview more room during a quiet
      stretch. Must restore the exact splitter layout on exit.
- [ ] **M2-16 — Guide refresh.** Update `docs/operator_guide.md` with the new
      keyboard flow and click rules.

### Prove it

- [ ] **M2-17 — Three-size smoke.** No clipped text or dead controls at the
      three audit sizes.
- [ ] **M2-18 — Keyboard-only pass.** Complete find → preview → live → clear →
      recall without touching the mouse.
- [ ] **M2-19 — Layout golden.** Capture the default layout for regression
      comparison after future UI work.

### 10-minute deviations after M2

- [ ] Add a “No matches yet” empty state to the review queue.
- [ ] Add `Ctrl+F` to focus the active search box.
- [ ] Add a tooltip that explains single-click vs double-click on a verse.
- [ ] Remember the last selected translation per tab.
- [ ] Add a “Clear search” button to both search panels.

---

## M3 — STT flow hardening

**Goal:** A live service can lose the audio device, hit a thermal event, or
drop the WebSocket without losing audio or requiring an app restart.

**Source docs:** `docs/threading_and_lifecycle.md`,
`docs/audio_ingestion.md`, `docs/gpu_and_hardware.md`,
`docs/search_engine.md`, `AGENTS.md`

**Done when:** a two-hour simulated service with device loss, a thermal event,
and a WebSocket reconnect loses no audio, recovers automatically, and shows the
operator an actionable status the whole time.

> **Why now:** STT is the part most likely to fail during a live service.
> Harden it before the pack split, so segmentation moves a subsystem you
> already trust.

### Map the failure modes

- [ ] **M3-01 — Failure inventory.** Audio device lost, model missing, CUDA
      OOM, thermal throttle/critical, Queue A overflow, WebSocket drop, clock
      drift, and disk-full during recording.
- [ ] **M3-02 — Define recovery policy.** For each failure: retry, degrade,
      failover, or stop — and what the operator sees. Put it next to the error
      hierarchy in `core/errors.py`.
- [ ] **M3-03 — Health surface.** Queue depths, model state, last transcript
      age, inference latency, GPU temperature, and recording state in one
      place the UI can read.

### Harden

- [ ] **M3-04 — Queue A backpressure.** Prove the “never drop audio” rule at
      depth > 400 and make the failover path observable.
- [ ] **M3-05 — Model load and fallback.** Faster-Whisper → Vosk/CPU with a
      clear status, a bounded retry, and no silent dead air.
- [ ] **M3-06 — Device hotplug.** Handle device removal/reappearance, sample
      rate changes, and a muted/clipped input without restarting the app.
- [ ] **M3-07 — Thermal integration.** Mock NVML thresholds at 70°C safe /
      82°C critical; verify throttling, recovery, and the operator warning.
- [ ] **M3-08 — Restart and shutdown.** Bounded backoff, poison-pill shutdown,
      and no orphaned threads after a failed restart.
- [ ] **M3-09 — Dedupe and sliding window.** Re-run the TTL/LRU and 15-word /
      6-word overlap tests under burst load; fix any duplicate queue entries.
- [ ] **M3-10 — End-to-end latency budget.** Instrument capture → STT → search
      → queue → display; document the budget and alert when it is exceeded.
- [ ] **M3-11 — Operator status.** STT panel shows state, last transcript,
      error, and a Retry/Restart action that explains what will happen.
- [ ] **M3-12 — Forensics.** Rotate logs, keep the append-only transcript
      fail-safe, and make the log path easy to find after a service.

### Prove it

- [ ] **M3-13 — Fault-injection suite.** Device loss, model missing, thermal
      event, queue overflow, WS drop, and disk-full.
- [ ] **M3-14 — Soak test.** Two-hour simulated service with injected faults;
      zero lost audio, automatic recovery, readable status.
- [ ] **M3-15 — Recovery runbook.** One page: symptom → check → action, for
      the operator and for future-you at 7 a.m.

### 10-minute deviations after M3

- [ ] Add an STT status pill to the top bar.
- [ ] Add “Copy last transcript” to the STT panel.
- [ ] Add a queue-depth tooltip to the status pill.
- [ ] Add a “Restart STT” button with a confirmation dialog.
- [ ] Add a “Open log folder” shortcut.

---

## M4 — Optimizations: Windows battery + UI snappiness

**Goal:** The app feels instant on the operator's Windows laptop, on battery as
well as on AC, without weakening the live output. Measure first, then remove
hidden work, fix UI-thread stalls, and make the expensive paths power-aware.

**Source docs:** `docs/architecture.md`, `docs/threading_and_lifecycle.md`,
`docs/display_and_broadcast.md`, `docs/random_notes.md`, `AGENTS.md`

**Done when:** `docs/perf_budget.md` exists with AC and battery budgets; the
target laptop meets those budgets on battery; a before/after report shows the
improvement; live OBS output and STT capture cadence are unchanged; and the
full suite plus the M2 three-size smoke still pass.

> **Rule:** do not tune by feel and do not disable features to win a benchmark.
> Every change is justified by a measurement, and the live path (capture → STT
> → output) keeps its current guarantees.

### Measure first — do not tune blind

- [ ] **M4-01 — Baseline capture script.** Add a small probe that records cold
      start, first switch to each tab, verse push → preview/live paint, idle
      CPU/RSS/GPU, and UI-thread stalls. Log JSON so runs are comparable.
      Run it on AC and on battery, at 100% and 125% Windows scaling.
- [ ] **M4-02 — Boot-path profile.** Time imports (`faster_whisper`, `faiss`,
      `onnxruntime`, `PyQt6.QtWebEngine`), index loads, DB init, and widget
      construction. List the top ten costs and mark which are needed before the
      first interaction.
- [ ] **M4-03 — Live-interaction profile.** Profile tab switches, verse
      double-click, theme change, queue Show, schedule drag, and splitter drag.
      Record every main-thread call over 16 ms, and flag anything over 50 ms as
      a stall to fix.
- [ ] **M4-04 — Write the budgets.** Put concrete numbers in
      `docs/perf_budget.md`: cold start, tab switch, preview paint,
      show-to-live, idle CPU, idle battery drain, and maximum UI stall. Those
      numbers become the acceptance gate for the rest of the milestone.
- [ ] **M4-05 — Power-state probe.** Detect AC / battery / battery-saver on
      Windows (`GetSystemPowerStatus` via `ctypes`, `powercfg` fallback), show
      it in a diagnostics line, and log transitions. Detect it before changing
      any behavior.
- [ ] **M4-06 — Timer and repaint census.** List every `QTimer`, polling loop,
      WebEngine load, animation, and repaint source: interval, owner, and
      whether it still runs when its tab or panel is hidden. This is the
      worklist for the next section.

### Kill hidden work

- [ ] **M4-07 — Hidden-tab lifecycle.** Audit lazy loading and unloading in
      `ui/main_window.py`. When a tab is not visible, its timers, WebEngine
      pages, polling, animations, and file watchers must pause — and resume
      without a reload flash when it returns.
- [ ] **M4-08 — Display-preview lifecycle.** `LivePreviewPanel` creates a
      Preview and a Live `DisplayView`; the Theme Designer adds three more.
      Suspend offscreen/obscured views, stop their JS animations, and avoid
      repainting payloads nobody can see. Measure before choosing a heavier
      redesign.
- [ ] **M4-09 — Timer consolidation.** Deck list polling is 1000 ms, plus the
      connection monitor, hardware monitor, search debounce, and fade timers.
      Merge what can share one heartbeat; stop hidden timers; back off
      nonessential polls on battery. Keep STT/WebSocket health checks at a safe
      rate — never at the cost of a silent failure.
- [ ] **M4-10 — Splitter and layout saves.** `core/panel_layout.py` already
      debounces persistence — verify it does not write during a drag and does
      not fire per child move. Keep the persistence; remove the per-pixel work.
- [ ] **M4-11 — Widget churn.** Stop clearing and rebuilding lists on every
      update (queue, deck list, theme cards, history). Patch single items in
      place, keep the 50-item queue cap, and measure the rebuild cost before and
      after.
- [ ] **M4-12 — Per-widget stylesheets.** Per-item `setStyleSheet` calls force
      style recalculation (queue cards are one example). Move repeated rules to
      shared QSS or paint them; check the focus-ring overlay and hover repaints
      for the same problem.
- [ ] **M4-13 — WebEngine cost.** Measure CPU/GPU per live view. Try Chromium
      flag and frame-rate tuning for operator previews only, never for the OBS
      output. Document what each flag changes; ship nothing you cannot explain.

### Make the common paths fast

- [ ] **M4-14 — Boot to first interaction.** Defer everything not needed before
      the operator can preview a verse: heavy imports, index warmup, model
      load, and non-visible tabs. Show progress instead of freezing.
- [ ] **M4-15 — Tab switching.** First switch to each tab must stay inside the
      M4-04 budget. Build heavy widgets in chunks or after the first paint, and
      keep the existing loading state visible.
- [ ] **M4-16 — Verse → Preview → Live.** Instrument the hot path and remove
      full-document reloads when only text or theme changed. Reuse the existing
      WebEngine page and stop re-serializing the whole theme per keystroke.
- [ ] **M4-17 — Search responsiveness.** Manual search and navigator input must
      stay responsive while FTS/FAISS work runs. Debounce, cancel stale queries,
      and never block the event loop; the STT queue path stays independent.
- [ ] **M4-18 — Theme apply.** A theme change re-broadcasts the full theme.
      Measure serialization and JS apply cost; cache the resolved theme and
      skip payloads identical to the current one.
- [ ] **M4-19 — Large deck lists.** Keep card builds lazy and verify scrolling,
      selection, and editing stay smooth at 500+ slides (final proof lands in
      M7/M9).
- [ ] **M4-20 — Windows platform audit.** High-DPI scaling, hybrid GPU
      (iGPU vs dGPU), RHI backend, Defender scanning of the venv and data
      folders, process priority, and a `powercfg /energy` idle report. Change
      one variable at a time and record what actually helped.

### Power-aware behavior

- [ ] **M4-21 — Define the profiles.** AC/Quality (today's behavior),
      Battery/Balanced (default on battery), and Battery saver (manual). Each
      profile is a table of concrete settings, not a mood.
- [ ] **M4-22 — What changes on battery.** Shorten or disable decorative
      animation, lower operator-preview refresh, back off background polls, and
      defer noncritical warmups. Never lower live OBS quality or STT capture
      cadence.
- [ ] **M4-23 — Battery-saver UX.** Show a small status chip when a reduced
      profile is active, with one click back to Quality, and remember the
      per-machine choice. No surprise mode switch mid-service.
- [ ] **M4-24 — Thermal and CPU guard.** Respect Windows power throttling and
      the existing 70 °C safe / 82 °C critical thresholds. Prefer event-driven
      work over polling and never busy-wait.
- [ ] **M4-25 — Battery-drain measurement.** Run the same scripted service on
      battery for 30–60 minutes per profile; record %/hour and responsiveness.
      Pick the defaults from the data.

### Prove it

- [ ] **M4-26 — Before/after report.** One table per budget: AC baseline,
      battery baseline, and after. Include the laptop model, Windows build,
      scaling, and active profile. Store it under `docs/perf/`.
- [ ] **M4-27 — Regression gate.** One command re-runs the probe and fails when
      a budget regresses by more than 10% (or prints a clear comparison table).
      Document it next to the test commands.
- [ ] **M4-28 — Two-hour battery soak.** Live-service simulation on battery: UI
      stays responsive, no unexpected thermal throttle, no memory growth, OBS
      output stays smooth.
- [ ] **M4-29 — No functional regressions.** Full test suite (with the usual
      headless `test_phase9_ui` exclusion) plus the M2 three-size UI smoke.
- [ ] **M4-30 — Main-thread I/O.** Keep SQLite writes, transcript archiving,
      log flushes, and file scans off the UI thread. Look for synchronous
      `open`, `exec`, and `json.load` calls in update and paint paths.

### 10-minute deviations after M4

- [ ] Add a status-bar line showing the active profile and battery state.
- [ ] Add “Copy diagnostics” (versions, GPU, power state, budgets) to Settings.
- [ ] Remember the last profile per machine.
- [ ] Add a one-click “Reload preview” for a stuck WebEngine view.
- [ ] Log the startup timing breakdown on every boot.

---

## M5 — Segmentation into installable packs

**Goal:** Users install only what they need. Core stays useful alone; each pack
owns its UI, threads, requirements, and data, and a missing pack can never
crash boot.

**Source docs:** `docs/modular-install-plan.md` (the detailed plan — this
milestone is the execution checklist for it), `docs/architecture.md`,
`AGENTS.md`

**Done when:** a core-only install boots to a usable app; every pack installs
and uninstalls cleanly; and the test matrix (core, core+each pack, all packs)
passes with no import errors or hidden tabs.

> **Scope guard:** v1 is installer-level segmentation, not an in-app plugin
> marketplace. The enabled-pack list is written at install time and read at
> boot; the app does not download missing packs later.

> **Sequencing note:** STT hardening (M3) lands first, so the STT extraction
> below moves a subsystem with a tested failure and recovery path.

### Decide and scaffold

- [ ] **M5-01 — Resolve the three open questions** in
      `docs/modular-install-plan.md`: Library without Scriptures, review-like
      items outside STT, and whether the installer offers indexed downloads
      for open texts.
- [ ] **M5-02 — Pack manifest.** Write `packs/manifest.json` with id, name,
      default-on flag, requirements file, data dirs, tabs, threads, settings
      sections, and version. Add schema validation.
- [ ] **M5-03 — Pack API.** Add `core/packs.py` with `has`, `enabled`,
      `visible`, `enabled_tabs`, and `requirements`. Core imports only this.
- [ ] **M5-04 — Tab registry.** `main_window` builds tabs from the manifest
      instead of the hardcoded list. With all packs installed, behavior is
      byte-for-byte the same.
- [ ] **M5-05 — Section tagging.** Tag Library, Settings, and History sections
      with their pack. Hidden sections disappear cleanly; a tab with no visible
      sections opens an empty state naming the missing pack.
- [ ] **M5-06 — Capability guards.** Replace cross-tab hard calls with
      `packs.has(...)` checks: History → Scripture, queue workers, hotkeys,
      theme quick edit, schedule handoffs.

### Extract and split

- [ ] **M5-07 — STT UI extraction.** Move `STTPanel`, the review queue, and
      their wiring out of the Scripture tab into the STT pack, preserving the
      M3 health and recovery surfaces. Scripture keeps its display pipeline.
- [ ] **M5-08 — Pack-aware boot.** `service_manager` starts only the threads
      belonging to installed packs; missing STT means no audio threads, no
      model load, and no queue panel.
- [ ] **M5-09 — Requirements split.** `requirements-core.txt`,
      `requirements-scriptures.txt`, `requirements-stt.txt`,
      `requirements-slides.txt`; test a per-pack venv install.
- [ ] **M5-10 — Data split.** Bible data/indexes belong to Scriptures; deck
      data belongs to Slides; user schedules stay local and pack-agnostic.
- [ ] **M5-11 — Cross-platform index script.** Replace `convert.sh` with a
      Python entry point that works on Windows/macOS/Linux and does not
      hardcode `venv/bin/python`.
- [ ] **M5-12 — GPU probe + STT model picker.** Detect NVIDIA/MPS/CPU, show a
      plain-language verdict, offer the Faster-Whisper model list, persist
      `stt.model` / `stt.device`. Never block the rest of the install.
- [ ] **M5-13 — Installer MVP.** Checkboxes (Scriptures pre-checked, Next
      disabled until at least one pack), `pip install -r` per pack, data builds,
      and the enabled-pack list written for boot.
- [ ] **M5-14 — Uninstall path.** Remove the pack dir, prune the manifest, and
      leave user data untouched.
- [ ] **M5-15 — Matrix tests.** Core-only, core+each pack, all packs, and
      STT × mocked GPU verdict. Boot must never raise on a missing pack.

### Prove it

- [ ] **M5-16 — Clean-machine dry run.** In a fresh venv, install core only,
      boot, then add one pack at a time and verify the UI changes only where
      expected.
- [ ] **M5-17 — Docs and AGENTS refresh.** Document the manifest contract and
      the “no pack imports another pack” rule.

### 10-minute deviations after M5

- [ ] Add a `packs.has()` no-op test for an absent pack.
- [ ] Add a read-only “Installed packs” line to Settings.
- [ ] Add a `manifest_version` field and reject unknown future versions.
- [ ] Update the output roster’s “reserved” labels to match the real pack map.
- [ ] Add a `requirements-core.txt` skeleton as soon as the split starts.

---

## M6 — Image streaming as the third display tab

**Goal:** Images become a first-class display source: import, preview, push to
the Media outputs (7–8), clear, and recover from reconnect without touching
OBS.

**Source docs:** `docs/display_and_broadcast.md`, `core/outputs.py`,
`docs/theme_file_reference.md` (for image/background interaction later)

**Done when:** an operator can import an image, preview it, push it to a Media
output, clear it, and survive a WebSocket reconnect; a path outside the allowed
roots can never be read; and both renderers produce the same result.

### Decide

- [ ] **M6-01 — Pack ownership.** Decide whether images belong to a `media`
      pack or the planned Audio-Video pack. Update `packs/manifest.json`.
- [ ] **M6-02 — Payload contract.** Define the action name, source type (local
      path vs URL), fit mode, background, duration, transition, loop, and clear
      semantics. Keep it additive to the existing payload.
- [ ] **M6-03 — Security policy.** Allowed roots, path traversal rejection,
      MIME sniffing, max file size, remote URL policy, and what happens when a
      file disappears mid-service.

### Build

- [ ] **M6-04 — Media library.** Import, dedupe, thumbnail, metadata, rename,
      delete, and a stable on-disk location under user data.
- [ ] **M6-05 — Media service and routing.** Resolve images, cache decoded
      data, and route to `MEDIA_OUTPUTS` through the existing output router.
- [ ] **M6-06 — Preload and memory cap.** Preload the next image, decode off
      the UI thread, and cap the cache so a 50 MB PNG cannot stall a service.
- [ ] **M6-07 — Renderer support.** Image element, `object-fit`, background,
      fade/slide in/out, clear, and reconnect resync in both `display.js` and
      the embedded preview copy.
- [ ] **M6-08 — Media tab.** The third display workspace: library grid,
      preview/live screens, push/clear, output selector, and an empty state.
- [ ] **M6-09 — Schedule integration.** Decide whether an image can be a
      schedule item; if yes, give it a clear card and a run-of-show order.
- [ ] **M6-10 — Hotkeys.** Push, clear, next, previous; never collide with the
      Scripture and Deck bindings.
- [ ] **M6-11 — Settings.** Default fit, default transition, media folder,
      supported formats, and enable the currently disabled “Media Background
      While Blank” control.
- [ ] **M6-12 — Library integration.** A Media section in the Library tab that
      is pack-aware and can be hidden when the pack is absent.

### Prove it

- [ ] **M6-13 — Contract tests.** Payload shape, clear, reconnect, and
      prioritized vs simultaneous output routing.
- [ ] **M6-14 — Security tests.** Traversal, symlink escape, MIME mismatch,
      oversized file, and missing file.
- [ ] **M6-15 — Render matrix.** Both renderers, PNG/JPEG/WebP/GIF, portrait
      and landscape, transparent PNG, and a very large image.
- [ ] **M6-16 — Reconnect test.** Kill and restore the WebSocket mid-display;
      the image returns without operator action.

### 10-minute deviations after M6

- [ ] Add a broken-image placeholder with a retry button.
- [ ] Add “Reveal in file manager” to the image context menu.
- [ ] Add a drag-over highlight on the media grid.
- [ ] Remember the last import folder.
- [ ] Show dimensions and file size on the selected image.

---

## M7 — Deck tab UI improvements

**Goal:** The Deck flow (create/import → edit → schedule → live) becomes as
direct as the Scripture flow, and deck/slide edits stop losing formatting.

**Source docs:** `docs/slide-format.md`, `docs/slide-cards.md`,
`docs/lite-designer-plan.md`, `docs/display_and_broadcast.md`

**Done when:** a deck can be created, edited, scheduled, and pushed without a
mouse-only step; `shadow=` survives save; and no deck control clips at
1366×768.

### Discover

- [ ] **M7-01 — Deck flow audit.** Create/import → edit → schedule → live.
      Log every modal, dead end, and formatting loss.
- [ ] **M7-02 — Panel inventory.** Schedule, deck list, preview/live strips,
      slide grid, search, and the Lite Designer entry points.
- [ ] **M7-03 — Format round-trip review.** Compare `format_to_line` output
      with the saved deck for every Tier 0/1/1.5 property; confirm the known
      `shadow=` loss and any siblings.

### Build

- [ ] **M7-04 — Fix `shadow=` round-trip.** Make `format_to_line` preserve the
      shadow parameter through save/load and add a regression test.
- [ ] **M7-05 — Deck list.** Search/filter/sort, section counts, modified
      badge, and a context menu that matches the theme cards.
- [ ] **M7-06 — Slide grid.** Clear card hierarchy, selection, multi-select,
      drag reorder, duplicate/delete, and a visible “LIVE” state.
- [ ] **M7-07 — Preview/live strips.** Persistent labels, push affordance,
      and a section-hop indicator that is readable at a glance.
- [ ] **M7-08 — Editor entry.** Double-click edits in Lite Designer; unsaved
      changes are guarded; saving returns to the same slide and scroll position.
- [ ] **M7-09 — Schedule drag/drop.** Drag decks or slides into the schedule;
      show a drop preview and keep the schedule order stable.
- [ ] **M7-10 — Import flow.** EasyWorship import with progress, duplicate
      handling, and an error state that names the file.
- [ ] **M7-11 — Empty states.** First-run deck list, empty search, empty
      schedule, and no-selection preview each get a useful next action.
- [ ] **M7-12 — Keyboard and focus.** New deck, search, next/previous slide,
      push, and edit with visible focus.
- [ ] **M7-13 — Large-deck performance.** Lazy card build, no UI freeze on
      open, and a measured budget for 500+ slides.

### Prove it

- [ ] **M7-14 — Format gate.** Every deck format round-trips with Tier 0/1/1.5
      properties intact, including `shadow=`.
- [ ] **M7-15 — Three-size smoke.** No clipped labels or unreachable controls
      at 1366×768 / 1920×1080 / 150% scaling.
- [ ] **M7-16 — Guide refresh.** Update the Deck section of the operator guide.

### 10-minute deviations after M7

- [ ] Add “Duplicate deck” to the deck context menu.
- [ ] Show a selection count when multiple slides are selected.
- [ ] Add `Ctrl+N` for a new deck.
- [ ] Add an empty-state “Create your first deck” button.
- [ ] Remember the last selected deck across tab switches.

---

## M8 — Video + audio streaming as another display tab

**Goal:** Local video and audio become a controlled display source with
transport, playlist, and clean OBS output — not a browser tab pointed at a
file.

**Source docs:** `docs/display_and_broadcast.md`, `docs/audio_ingestion.md`,
`core/outputs.py`, `docs/architecture.md`

**Done when:** an operator can play/pause/seek a video or audio item, send it
to the new display output (ids 9–10 are reserved), clear it, and recover from
reconnect; audio-only items show something intentional; and a missing codec
produces a clear error, not a black screen.

> **Naming is a decision, not an assumption.** The reserved `PRESENTATION`
> outputs may become this tab, or a separate `STREAM` key may own 9–10. Decide
> before writing the manifest entry.

### Decide

- [ ] **M8-01 — Tab key, name, and pack.** Pick the internal key, label, and
      pack owner. Update `core/outputs.py` and `packs/manifest.json`.
- [ ] **M8-02 — Playback contract.** Play, pause, seek, volume, mute, loop,
      stop, next/previous, and state resync after reconnect.
- [ ] **M8-03 — Source policy.** Local files only, or URLs too? Define codecs,
      HLS/RTSP support, and the OBS Browser Source limits.

### Build

- [ ] **M8-04 — Media library.** Video/audio import, thumbnail/poster,
      duration, metadata, and dedupe alongside images.
- [ ] **M8-05 — Playback service.** One active item per output set, a queue or
      playlist, and a state machine that survives renderer reloads.
- [ ] **M8-06 — Output routing.** `STREAM_OUTPUTS` (or `PRESENTATION_OUTPUTS`)
      through the existing router, with prioritized/simultaneous behavior.
- [ ] **M8-07 — Renderer.** `<video>` / `<audio>` in both renderer copies;
      poster, object-fit, background, autoplay/mute policy, and clean teardown.
- [ ] **M8-08 — New display tab.** Library/playlist, transport, preview/live,
      output selector, volume, and a clear “what is playing” header.
- [ ] **M8-09 — Hotkeys.** Play/pause, stop/clear, next/previous, volume;
      document every binding and keep it out of the text-entry path.
- [ ] **M8-10 — Schedule integration.** Video/audio items as run-of-show
      entries, with duration and a visible “playing now” state.
- [ ] **M8-11 — Settings.** Default volume, loop, autoplay behavior, and a
      note about hardware decode where relevant.

### Prove it

- [ ] **M8-12 — Transport tests.** Play/pause/seek/volume/loop and reconnect
      resync on both renderers.
- [ ] **M8-13 — Failure tests.** Missing file, unsupported codec, audio-only
      file, long stream, and a file deleted mid-play.
- [ ] **M8-14 — Output tests.** Prioritized and simultaneous routing; clearing
      one tab never blanks another tab’s output.
- [ ] **M8-15 — Resource check.** CPU/GPU cost of a 1080p video on the target
      machine; document the safe limit.

### 10-minute deviations after M8

- [ ] Remember the last volume per output set.
- [ ] Add a global Stop/Clear hotkey with a confirmation for live use.
- [ ] Show a readable codec error instead of a black frame.
- [ ] Show current time and duration on the transport bar.
- [ ] Add “Reveal in file manager” for the playing item.

---

## M9 — More Deck tab UI improvements

**Goal:** After Media and Streaming exist, make Decks share one interaction
language with them instead of growing a second set of ad-hoc panels.

**Source docs:** `docs/slide-format.md`, `docs/slide-cards.md`,
`docs/lite-designer-plan.md`

**Done when:** decks, images, and playable media use the same library,
selection, preview, and transport patterns; bulk actions are undoable; and the
Deck tab still passes its three-size and format gates.

- [ ] **M9-01 — Post-media audit.** Re-walk the Deck flow now that Media and
      Streaming exist. List every duplicate widget or inconsistent gesture.
- [ ] **M9-02 — Shared media browser.** Extract the library grid/picker so
      Decks, Media, and Streaming use one component with pack-aware sections.
- [ ] **M9-03 — Cross-tab drag/drop.** Drag an image or video into a deck or
      schedule where that makes sense; show a drop preview and a clear failure
      state where it does not.
- [ ] **M9-04 — Deck/slide thumbnails.** Real rendered thumbnails, not text
      placeholders, with a fallback for missing assets.
- [ ] **M9-05 — Bulk actions.** Multi-select, duplicate, delete, and move with
      an undo path and a selection count.
- [ ] **M9-06 — Per-deck theme override.** A visible control that says whether
      the deck follows the global theme or overrides it.
- [ ] **M9-07 — Section navigation polish.** Section chips, next/previous
      section, and a readable “current section” state.
- [ ] **M9-08 — Search across decks and slides.** One search field with
      results grouped by deck, plus keyboard navigation.
- [ ] **M9-09 — Accessibility.** Focus order, accessible names, and no
      color-only status.
- [ ] **M9-10 — Performance.** Re-measure large-deck open/edit at 500+ slides
      after the shared components land.
- [ ] **M9-11 — Deck guide refresh.** Final pass on the operator guide and
      Lite Designer docs.

### 10-minute deviations after M9

- [ ] Add “Collapse all sections”.
- [ ] Add “Recent decks” to the empty state.
- [ ] Add a bulk “Duplicate slides” action.
- [ ] Add a “modified since last service” badge to deck cards.
- [ ] Add a “Copy deck title” action.

---
## Parking lot — decisions to make when you get there

These are not scheduled. They are the questions that will otherwise derail a
milestone halfway through.

- [ ] Does `media` own only images, or do images + video + audio share one
      Audio-Video pack? (M5/M6/M8)
- [ ] Does the image payload accept remote URLs, or local files only? (M6)
- [ ] Does the new stream tab become `PRESENTATION` (outputs 9–10), or does
      Presentation stay reserved for PPTX? (M8)
- [ ] Can images/videos be schedule items, or are they manual-only? (M6/M8)
- [ ] Does the Full Designer replace the Quick Editor, or do both stay? (M1)
- [ ] Does the installer offer prebuilt open-Bible indexes, or only a local
      build? (M5)
- [ ] Is there any review-like item outside STT that belongs in core? (M5)
- [ ] Which profile is the default on battery, and does the operator get a
      visible override? (M4)
- [ ] What is the performance floor for live OBS output — what may never be
      traded for operator-side snappiness? (M4)

## Known issues to slot in

- [ ] Theme Designer can lose unmanaged keys on save — `ThemePropertiesPanel`
      rebuild is the suspect (`docs/lite-designer-plan.md`).
- [ ] `tests/test_lite_designer_theme_awareness.py` has 3 pre-existing
      failures caused by a test/code API mismatch.
- [ ] Deck `shadow=` does not survive `format_to_line`
      (`docs/modular-install-plan.md`, known complications #6).
- [ ] “Media Background While Blank” is a disabled placeholder in Settings
      until image/video streaming lands (`ui/tabs/settings_tab.py`, M6/M8).
- [ ] Windows battery performance has no baseline, budget, or regression
      gate yet (M4).
- [ ] `MEDIA` and `PRESENTATION` output ids are reserved but show “reserved”
      in the roster; update the label when each tab becomes real (M6/M8).

---

_When a milestone is done, move its section to the bottom under a `## Done`
heading instead of deleting it. The history is useful, and the IDs stay
searchable._
