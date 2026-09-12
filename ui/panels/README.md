# UI Architecture — Modular Panels

> **Design principle (adopted 2026): every workspace region is a modular panel.**
> This app is open source. A tech-savvy user must be able to define their own
> layouts, and profiles must be able to ship different layouts. Everything below
> exists to make that possible.

## The contract

1. **A panel is a self-contained `QWidget`.** It owns its UI, its data access
   (via `core/*_service.py`), and its dialogs. It never imports sibling panels.
2. **Panels communicate ONLY via Qt signals/slots.** No panel reaches into
   another panel's internals. Tabs wire panel signals to panel public methods.
3. **Panels are workspace-agnostic.** The same `SchedulePanel` instance class
   serves the SCRIPTURE tab and the SLIDES tab. Behavior differences belong in
   the tab's wiring, not in the panel.
4. **Panels degrade gracefully with no data.** Empty DB → empty state, never a
   crash. This keeps iteration snappy without a full library import.
5. **Heavy dependencies stay behind panel boundaries.** If a panel needs
   WebEngine/GPU (e.g. `LivePreviewPanel`), tabs and tests must be able to
   construct the *layout* without it — stub the panel module, never the tab.

## Current panel inventory

| Panel | File | Signals (out) | Public methods (in) |
|---|---|---|---|
| `SchedulePanel` | `schedule_panel.py` | `item_clicked(dict)`, `item_double_clicked(dict)`, `schedule_modified`, `schedule_loaded(str)` | `add_item(data)`, `get_schedule()`, `get_schedule_data()`, `load_schedule(path)`, `save_schedule(path)`, `clear_all()` |
| `DeckListPanel` | `deck_list_panel.py` | `deck_selected(dict)`, `add_to_schedule_requested(dict)`, `go_live_requested(int)`, `deck_deleted(int)`, `deck_text_updated(int)`, `deck_slide_updated(int,int)` | `refresh()`, `selected_deck()`, `decks()`, `open_slide_editor(deck_id,index)` |
| `SlideGridPanel` | `slide_grid_panel.py` | `slide_clicked(int)`, `slide_double_clicked(int)`, `slide_edit_requested(deck_id,index)` | `set_deck(deck\|None)`, `set_title(str)`, `set_selected_index(int)`, `selected_index`, `deck`, `update_slide_card(index,text)` |
| `LivePreviewPanel` | `live_preview_panel.py` | `clear_recall`, `prev_verse`, `next_verse`, `preview_double_clicked`, `preview_clicked`, `live_clicked` | `set_live_payload(dict)`, `set_preview_payload(dict)`, `clear_live()` |
| `HistoryPreviewPanel` | `history_preview_panel.py` | `navigate_verse_requested(book,chapter,verse,translation)` | `show_verse(ref,text,translation,theme)`, `show_search(query,top_refs,chosen)`, `show_slide(deck_id,ref,text,theme)`, `show_clear()`, `clear()` |
| `BrowserPanel` | `browser_panel.py` | `verse_clicked`, `broadcast_in_version`, `navigator_push`, `translation_changed` | `navigate_to_reference(...)`, `get_selected_verse()` |
| `QueuePanel` | `queue_panel.py` | `display_requested`, `theme_changed`, ... | `add_item(data)`, `set_translation(v)` |
| `STTPanel` | `stt_panel.py` | `transcription_started/stopped`, `recording_*` | `append_transcript(text)` |

## Slide strips: text only, by design

`SlideGridPanel` groups a deck's slides under section headers (consecutive
same-section runs; `SECTION · n` labels with a blue accent bar). Between
groups, a thick horizontal break (spacer + rule) reads thicker than the
vertical card gutters, so order reads left-to-right. Each card shows the
full multi-line slide text (word-wrapped, autosized — no elision) on slate
(never black) at the settings-configured strip size. Clicks anywhere on a
card select it. Showing a slide on an already-loaded strip updates selection
only (no rebuild), so scroll position survives stepping. Exact-screen
rendering belongs to the preview/live views; strips are navigation, and
must stay instant with zero extra dependencies.

## Scale notes (500-slide decks, 100k-deck libraries)

- `SlideGridPanel.set_deck` plans headers synchronously (cheap) but builds
  cards incrementally: the first screenful (and any requested selection)
  paints immediately, the rest streams in idle ~25-card slices. Stepping or
  selecting past the built frontier completes it synchronously on demand.
  A generation counter cancels superseded builds on rapid deck switches.
- `DeckListPanel` never builds per-deck widgets: a `QListView` +
  `DeckListModel` (summary rows only) + `DeckCardDelegate` paints visible
  rows on demand. Library queries use `list_deck_summaries()` (no
  `slides_json`); full slides load per-action via `get_deck()`. Font-size
  changes relayout with zero rebuilds.

## Forward-looking: user-defined layouts
The direction (not yet implemented):

- Panels register in a central registry: `{panel_id: PanelClass}`.
- Profiles ship JSON layouts, e.g. `profiles/default/slides_layout.json`:
  `{tab: "SLIDES", regions: [{panel: "schedule", area: "left"}, ...]}`.
- A layout loader instantiates panels from the registry and wires a
  **declared** signal→slot map. Tabs become thin layout hosts.
- Until the loader exists, the migration path is: keep the contract above.
  Any new UI MUST be a panel following it — no monolithic tab widgets.

## Known candidates for consolidation

- Display-broadcast helpers (`_build_payload` / `_broadcast_to_ws`) are currently
  duplicated per workspace tab. When a third workspace needs them, promote to a
  shared module (e.g. `core/display_broadcast.py`) and refactor call sites.
