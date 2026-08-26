"""
ui/tabs/presentation_tab.py

The main workspace: nested QSplitter layout matching the HTML draft.
  Top: Schedule (L) | Live Output + Controls (C) | STT + Preview (R)
  Bottom: Manual Browser (L) | Queue (R)

Wires all panel signals to backend actions:
  - Queue Show → WebSocket broadcast + operator preview update
  - Clear/Prev/Next macro buttons → display state management
  - Transcribe toggle → start/stop Thread 1 + Thread 2
"""

import os
import logging
import asyncio
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QPushButton, QFrame
)
from PyQt6.QtGui import QIcon
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.panels.schedule_panel import SchedulePanel
from ui.panels.queue_panel import QueuePanel
from ui.panels.browser_panel import BrowserPanel
from ui.panels.stt_panel import STTPanel
from ui.panels.live_preview_panel import LivePreviewPanel
from core.bible_service import get_display_name
from ui.styles import (
    MACRO_BTN_AMBER, MACRO_BTN_CLEAR,
    RED_500, WHITE, SLATE_950, BORDER_SUBTLE
)

logger = logging.getLogger(__name__)


class PresentationTab(QWidget):
    """The main Presentation workspace tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Display state
        self._current_display = None      # Currently displayed verse dict (live)
        self._current_preview = None      # Currently previewed verse dict
        self._last_cleared_display = None  # Last verse before clear (for recall)
        self._is_cleared = True
        self._prev_verse_data = None      # Previous verse (for Prev button)
        self._next_verse_data = None      # Next verse (for Next button)

        # Schedule-origin tracking: when current display came from the schedule,
        # Prev/Next walks schedule items (stepping through deck slides) instead
        # of Bible verse neighbors.
        self._current_sched_data = None   # Identity of the schedule item dict
        self._current_from_schedule = False

        # Per-output themes: {"1": "default", "2": "default", ...}
        from core.database import get_setting
        output_count = int(get_setting("display.output_count", 1))
        self._themes_by_output: dict[str, str] = {}
        for i in range(1, output_count + 1):
            oid = str(i)
            self._themes_by_output[oid] = get_setting(f"display.output_{oid}_theme", "default")

        # Legacy single-theme property (always = output 1 theme)
        self._current_theme = self._themes_by_output.get("1", "default")

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(4, 4, 4, 4)
        root_layout.setSpacing(0)
        
        def wrap_panel(panel: QWidget) -> QWidget:
            """Wraps a panel in a container with a 4px margin (m-1 in Tailwind)"""
            wrapper = QWidget()
            l = QVBoxLayout(wrapper)
            l.setContentsMargins(4, 4, 4, 4)
            l.setSpacing(0)
            panel.setProperty("class", "MainPanel")
            l.addWidget(panel)
            return wrapper

        # ── Main Vertical Splitter: Top / Bottom ──
        main_splitter = QSplitter(Qt.Orientation.Vertical)
        main_splitter.setChildrenCollapsible(False)

        # ──── Top Section (Horizontal Splitter) ────
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setChildrenCollapsible(False)

        self.schedule_panel = SchedulePanel()
        self.live_preview = LivePreviewPanel()
        self.stt_panel = STTPanel()

        top_splitter.addWidget(wrap_panel(self.schedule_panel))
        top_splitter.addWidget(self.live_preview) # Center panel has its own padding/wrapper logic
        top_splitter.addWidget(wrap_panel(self.stt_panel))

        # Center panel gets the most space and cannot be collapsed completely
        top_splitter.setStretchFactor(0, 0)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setStretchFactor(2, 0)
        top_splitter.setCollapsible(1, False)
        
        # Default widths: 25% | 50% | 25%
        top_splitter.setSizes([300, 600, 300])

        main_splitter.addWidget(top_splitter)

        # ──── Bottom Section (Horizontal Splitter) ────
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.setChildrenCollapsible(False)

        self.browser_panel = BrowserPanel()
        self.queue_panel = QueuePanel()

        bottom_splitter.addWidget(wrap_panel(self.browser_panel))
        bottom_splitter.addWidget(wrap_panel(self.queue_panel))

        # Default widths: 60% | 40%
        bottom_splitter.setSizes([600, 400])

        main_splitter.addWidget(bottom_splitter)

        # Default heights: 65% top | 35% bottom
        main_splitter.setSizes([650, 350])

        root_layout.addWidget(main_splitter)

        # ── Wire all signals ──
        self._connect_signals()

    def _connect_signals(self):
        """Connect all panel signals to their backend actions."""
        
        # Queue panel: "Show" button → broadcast verse to display
        self.queue_panel.display_requested.connect(self._on_display_verse)
        
        # Queue panel: theme selection → update preview only
        self.queue_panel.theme_changed.connect(self._on_theme_changed)
        
        # Queue panel: theme double-click → push preview to live with that theme
        self.queue_panel.theme_double_clicked.connect(self._on_theme_double_click)
        
        # Live output: clear/recall toggle
        self.live_preview.clear_recall.connect(self._on_clear_recall)
        
        # Live output: prev/next verse navigation (uses schedule)
        self.live_preview.prev_verse.connect(self._on_prev_verse)
        self.live_preview.next_verse.connect(self._on_next_verse)
        
        # STT panel: transcription start/stop → control Thread 1 + Thread 2
        self.stt_panel.transcription_started.connect(self._on_start_transcription)
        self.stt_panel.transcription_stopped.connect(self._on_stop_transcription)

        # STT panel: recording start/stop/pause
        self.stt_panel.recording_started.connect(self._toggle_recording)
        self.stt_panel.recording_stopped.connect(self._toggle_recording)
        self.stt_panel.recording_paused.connect(self._toggle_pause_recording)
        
        # Browser panel: single-click → update preview only
        self.browser_panel.verse_clicked.connect(self._on_verse_single_click)
        
        # Browser panel: double-click → update live + preview
        self.browser_panel.broadcast_in_version.connect(self._on_browser_broadcast)

        # Browser panel: Enter in navigator → push to live
        self.browser_panel.navigator_push.connect(self._on_navigator_push)

        # Browser panel: translation changed → update FTS search panel
        self.browser_panel.translation_changed.connect(self._on_translation_changed)

        # Search panel: send verse to schedule
        self.queue_panel.verse_to_schedule.connect(self._on_search_to_schedule)

        # Search panel: single-click result → navigate to reference in current translation
        self.queue_panel.verse_to_navigator.connect(self._on_search_to_navigator)

        # Search panel: double-click result → send to live in current translation
        self.queue_panel.verse_to_live.connect(self._on_search_to_live)

        # Search panel: single-click translation badge → navigate in result's translation
        self.queue_panel.trans_badge_to_navigator.connect(self._on_trans_badge_to_navigator)

        # Search panel: double-click translation badge → send to live in result's translation
        self.queue_panel.trans_badge_to_live.connect(self._on_trans_badge_to_live)
        
        # Preview screen: double-click → push to live
        self.live_preview.preview_double_clicked.connect(self._on_preview_double_click)
        self.live_preview.preview_clicked.connect(self._on_preview_clicked)
        self.live_preview.live_clicked.connect(self._on_live_clicked)
        
        # Schedule panel: single-click → preview, double-click → live
        self.schedule_panel.item_clicked.connect(self._on_schedule_click)
        self.schedule_panel.item_double_clicked.connect(self._on_schedule_double_click)

        # Schedule filing: prompt save on modification, restore last schedule
        self.schedule_panel.schedule_modified.connect(self._on_schedule_modified)
        self.schedule_panel.schedule_loaded.connect(self._on_schedule_loaded)

        # Restore last schedule on startup
        self._restore_last_schedule()

    def _build_payload(self, text: str, ref: str, version: str, book: str = "",
                       chapter: str = "", verse: str = "", output_id: str = "1") -> dict:
        """Build a display payload matching the WS broadcast format.

        Slide text may carry inline color markup ([words: (#rrggbb)]) which is
        converted to HTML spans here — display.js renders text via innerHTML.
        Plain verse text is escaped unchanged (no markers → identity).
        """
        from core.theme_loader import get_theme
        from core.slide_parser import inline_markup_to_html, has_inline_markup
        theme_name = self._themes_by_output.get(output_id, "default")
        theme_data = get_theme(theme_name)
        if has_inline_markup(text):
            display_text = inline_markup_to_html(text)
        else:
            display_text = text
        return {
            "action": "display",
            "text": display_text,
            "ref": ref,
            "reference": f"{book} {chapter}:{verse}" if book else ref,
            "translation": get_display_name(version) if version else "",
            "book": book,
            "chapter": str(chapter),
            "verse": str(verse),
            "theme": theme_name,
            "theme_data": theme_data,
        }

    def _payload_for_display(self, data: dict, output_id: str = "1") -> dict:
        """Build a display payload from a stored display dict (verse or slide)."""
        if data.get("item_type") == "slide":
            return self._build_payload(
                data.get("text", ""), data.get("ref", ""), "",
                output_id=output_id,
            )
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"
        return self._build_payload(data.get("text", ""), ref, version, book, chapter, verse_num, output_id=output_id)

    def _apply_slide_display(self, sched_data: dict | None, deck_title: str,
                             slides: list, index: int):
        """Display a single slide of a deck on live + broadcast.

        Stores enough state (slides list + index + schedule identity) for
        Prev/Next to step through slides and on into adjacent schedule items.
        """
        if not slides:
            return
        index = max(0, min(index, len(slides) - 1))
        slide = slides[index]
        section = slide.get("section")
        text = slide.get("text", "")
        title = deck_title or "(untitled)"
        ref = f"{title} \u00b7 {section}" if section else title

        self._current_sched_data = sched_data
        self._current_from_schedule = sched_data is not None
        self._current_display = {
            "item_type": "slide",
            "text": text,
            "ref": ref,
            "book": "", "chapter": "", "verse_num": "", "version": "",
            "deck_title": title,
            "section": section,
            "slides": slides,
            "slide_index": index,
        }
        self._is_cleared = False

        payload = self._build_payload(text, ref, "")
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)
        logger.info(f"Slide display: {ref} ({index + 1}/{len(slides)})")

    def _step_schedule(self, delta: int):
        """Step forward/backward through schedule items from the current one.

        Slide decks are entered at their first (delta>0) or last (delta<0)
        slide; empty decks are skipped. Items are matched by their _sched_uid
        because Qt's UserRole round-trips dicts by copy.
        """
        items = self.schedule_panel.get_schedule()
        if not items or self._current_sched_data is None:
            return
        uid = self._current_sched_data.get("_sched_uid") if isinstance(self._current_sched_data, dict) else None
        if not uid:
            return
        row = next((i for i, d in enumerate(items) if d.get("_sched_uid") == uid), None)
        if row is None:
            return

        target = row + delta
        while 0 <= target < len(items):
            d = items[target]
            if d.get("item_type") == "slide":
                slides = d.get("slides", [])
                if slides:
                    idx = 0 if delta > 0 else len(slides) - 1
                    self._apply_slide_display(d, d.get("name") or d.get("ref", ""), slides, idx)
                    return
                target += delta
                continue
            # Verse item
            self._current_sched_data = d
            self._current_from_schedule = True
            self._display_schedule_item(d)
            return

    def _on_display_verse(self, data: dict):
        """
        Called when operator clicks 'Show' on a queue item.
        Updates live output only and broadcasts via WebSocket.
        """
        verse_text = data.get("text", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        self._current_sched_data = None
        self._current_from_schedule = False
        self._current_display = data
        self._is_cleared = False

        payload = self._build_payload(verse_text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)

        self._broadcast_to_ws(payload)

        if book and chapter and verse_num and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse_num))

        logger.info(f"Displaying: {ref}")

    def _on_browser_broadcast(self, version: str):
        """Called when operator double-clicks a verse in the browser panel. Updates live + preview."""
        verse_data = self.browser_panel.get_selected_verse()
        if not verse_data:
            return

        book = self.browser_panel._current_book or ""
        ref = f"[{get_display_name(version)}] {book} {verse_data['chapter']}:{verse_data['verse']}"
        text = verse_data.get("text", "")

        verse_dict = {
            "text": text,
            "book": book,
            "chapter": verse_data["chapter"],
            "verse_num": verse_data["verse"],
            "version": version
        }
        self._current_display = verse_dict
        self._current_preview = verse_dict
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, verse_data["chapter"], verse_data["verse"])
        self.live_preview.set_live_payload(payload)
        self.live_preview.set_preview_payload(payload)

        self._broadcast_to_ws(payload)

        if book and version:
            ch = verse_data.get("chapter", "")
            vs = verse_data.get("verse", "")
            if ch and vs:
                self._update_verse_neighbors(version, book, int(ch), int(vs))

        logger.info(f"Browser broadcast: {ref}")

    def _on_navigator_push(self, book: str, chapter: str, verse: str):
        """Enter in navigator → fetch verse and push to live."""
        from core.bible_service import get_verse
        version = self.browser_panel._current_translation
        verse_data = get_verse(version, book, int(chapter), int(verse))
        if not verse_data:
            return

        text = verse_data.get("text", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse}"

        verse_dict = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version
        }
        self._current_display = verse_dict
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self.live_preview.set_live_payload(payload)
        self.live_preview.set_preview_payload(payload)
        self._broadcast_to_ws(payload)
        self._update_verse_neighbors(version, book, int(chapter), int(verse))
        logger.info(f"Navigator push: {ref}")

    def _on_translation_changed(self, version: str):
        """Browser panel translation changed → update FTS search panel."""
        self.queue_panel.set_translation(version)

    def _on_search_to_schedule(self, data: dict):
        """Add a search result verse to the schedule."""
        item_data = {
            "ref": f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}".strip(),
            "book": data.get("book", ""),
            "chapter": data.get("chapter", ""),
            "verse": data.get("verse_num", ""),
            "text": data.get("text", ""),
            "translation": data.get("version", ""),
            "theme": self._current_theme,
        }
        self.schedule_panel.add_item(item_data)
        logger.info(f"Search result sent to schedule: {item_data['ref']}")

    def _on_search_to_navigator(self, data: dict):
        """Single-click search result → navigate browser to that reference in current translation + update preview."""
        book = data.get("book", "")
        chapter = str(data.get("chapter", ""))
        verse = str(data.get("verse_num", ""))
        version = self.browser_panel._current_translation
        self.browser_panel.navigate_to_reference(book, chapter, verse)

        # Fetch verse text from the CURRENT browser translation
        from core.bible_service import get_verse
        verse_data = get_verse(version, book, int(chapter), int(verse))
        text = verse_data.get("text", "") if verse_data else ""

        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse}"
        self._current_preview = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version,
        }
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self.live_preview.set_preview_payload(payload)
        logger.info(f"Search → navigator + preview: {book} {chapter}:{verse} [{version}]")

    def _on_search_to_live(self, data: dict):
        """Double-click search result → send to live in current browser translation (navigator's translation)."""
        book = data.get("book", "")
        chapter = str(data.get("chapter", ""))
        verse_num = str(data.get("verse_num", ""))
        # Use current browser translation, not the search result's version
        version = self.browser_panel._current_translation
        
        # Fetch verse text from the CURRENT browser translation (navigator's translation)
        from core.bible_service import get_verse
        verse_data = get_verse(version, book, int(chapter), int(verse_num))
        text = verse_data.get("text", "") if verse_data else data.get("text", "")
        
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        verse_dict = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse_num,
            "version": version,
        }
        self._current_display = verse_dict
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)
        if book and chapter and verse_num and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse_num))
        logger.info(f"Search → live: {ref} [{version}]")

    def _on_trans_badge_to_navigator(self, data: dict):
        """Single-click translation badge → navigate to reference in that translation + update preview."""
        book = data.get("book", "")
        chapter = str(data.get("chapter", ""))
        verse = str(data.get("verse_num", ""))
        text = data.get("text", "")
        version = data.get("version", "")
        self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)

        # Also update preview with the verse data in the badge's translation
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse}"
        self._current_preview = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version,
        }
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self.live_preview.set_preview_payload(payload)
        logger.info(f"Badge → navigator + preview: {book} {chapter}:{verse} [{version}]")

    def _on_trans_badge_to_live(self, data: dict):
        """Double-click translation badge → send to live in that translation."""
        book = data.get("book", "")
        chapter = str(data.get("chapter", ""))
        verse_num = str(data.get("verse_num", ""))
        text = data.get("text", "")
        version = data.get("version", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        verse_dict = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse_num,
            "version": version,
        }
        self._current_display = verse_dict
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)
        if book and chapter and verse_num and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse_num))
        logger.info(f"Badge → live: {ref}")

    def _on_verse_single_click(self, version: str):
        """Called when operator single-clicks a verse in the browser. Updates preview only."""
        verse_data = self.browser_panel.get_selected_verse()
        if not verse_data:
            return

        book = self.browser_panel._current_book or ""
        ref = f"[{get_display_name(version)}] {book} {verse_data['chapter']}:{verse_data['verse']}"
        text = verse_data.get("text", "")

        self._current_preview = {
            "text": text,
            "book": book,
            "chapter": verse_data["chapter"],
            "verse_num": verse_data["verse"],
            "version": version
        }

        payload = self._build_payload(text, ref, version, book, verse_data["chapter"], verse_data["verse"])
        self.live_preview.set_preview_payload(payload)
        logger.info(f"Preview updated: {ref}")

    def _on_preview_clicked(self):
        """Called when operator clicks the preview screen. Navigates browser to the previewed verse."""
        if not self._current_preview:
            return
        book = self._current_preview.get("book", "")
        chapter = self._current_preview.get("chapter", "")
        verse = self._current_preview.get("verse_num", "")
        version = self._current_preview.get("version", "")
        if book and chapter and verse:
            self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)
            logger.info(f"Preview click → navigate to {book} {chapter}:{verse}")

    def _on_preview_double_click(self):
        """Called when operator double-clicks the preview screen. Pushes preview to live."""
        if not self._current_preview:
            return

        data = self._current_preview

        # ── Slide preview ──
        if data.get("item_type") == "slide":
            self._apply_slide_display(
                self._current_sched_data, data.get("deck_title", ""),
                data.get("slides", []), data.get("slide_index", 0),
            )
            logger.info(f"Preview pushed to live (slide): {data.get('ref', '')}")
            return

        # ── Verse preview (existing behavior) ──
        verse_text = data.get("text", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        self._current_display = data
        self._is_cleared = False

        payload = self._build_payload(verse_text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)

        self._broadcast_to_ws(payload)

        if book and chapter and verse_num and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse_num))

        logger.info(f"Preview pushed to live: {ref}")

    def _on_live_clicked(self):
        """Called when operator clicks the live screen. Navigates browser to the displayed verse."""
        if not self._current_display:
            return
        book = self._current_display.get("book", "")
        chapter = self._current_display.get("chapter", "")
        verse = self._current_display.get("verse_num", "")
        version = self._current_display.get("version", "")
        if book and chapter and verse:
            self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)
            logger.info(f"Live click → navigate to {book} {chapter}:{verse}")

    def _on_clear_recall(self):
        """Toggle between clear and recall of the last displayed verse/slide."""
        if not self._is_cleared and self._current_display:
            self._last_cleared_display = self._current_display
            self._current_display = None
            self._is_cleared = True

            self.live_preview.clear_live()

            self._broadcast_to_ws({"action": "clear"})
            logger.info("Display cleared")

        elif self._is_cleared and self._last_cleared_display:
            data = self._last_cleared_display
            self._current_display = data
            self._is_cleared = False
            payload = self._payload_for_display(data)
            self.live_preview.set_live_payload(payload)
            self._broadcast_to_ws(payload)
            logger.info("Display recalled")

    def _on_theme_changed(self, output_id: str, theme_name: str):
        """Single-click theme: update that output's theme + re-render preview."""
        self._themes_by_output[output_id] = theme_name
        # Keep legacy property in sync
        if output_id == "1":
            self._current_theme = theme_name

        if output_id == "1" and self._current_preview:
            # Main output preview update
            data = self._current_preview
            book = data.get("book", "")
            chapter = data.get("chapter", "")
            verse_num = data.get("verse_num", "")
            version = data.get("version", "")
            ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"
            payload = self._build_payload(data.get("text", ""), ref, version, book, chapter, verse_num, output_id="1")
            self.live_preview.set_preview_payload(payload)
        logger.info(f"Output {output_id} theme changed to: {theme_name}")

    def _on_theme_double_click(self, output_id: str, theme_name: str):
        """Double-click theme: update that output's theme + re-render live + broadcast."""
        self._themes_by_output[output_id] = theme_name
        if output_id == "1":
            self._current_theme = theme_name

        if self._current_display:
            payload = self._payload_for_display(self._current_display, output_id=output_id)
            if output_id == "1":
                self.live_preview.set_live_payload(payload)
            self._broadcast_to_ws(payload)
            logger.info(f"Output {output_id} theme double-clicked: {theme_name}, live re-rendered")
        else:
            logger.info(f"Output {output_id} theme double-clicked: {theme_name} (no live verse)")

    def _on_prev_verse(self):
        """Show the previous verse/slide (schedule-aware)."""
        logger.info("_on_prev_verse called")
        cur = self._current_display
        if cur and cur.get("item_type") == "slide":
            idx = cur.get("slide_index", 0) - 1
            if idx >= 0:
                return self._apply_slide_display(
                    self._current_sched_data, cur["deck_title"], cur["slides"], idx
                )
            return self._step_schedule(-1)
        if self._current_from_schedule and self._current_sched_data is not None:
            return self._step_schedule(-1)
        if not self._prev_verse_data:
            logger.info("prev_verse: no previous verse")
            return
        prev = self._prev_verse_data
        version = prev.get("version", "") or (self._current_display.get("version", "") if self._current_display else "")
        self._navigate_to_bible_verse(prev, version, skip_navigator=True)

    def _on_next_verse(self):
        """Show the next verse/slide (schedule-aware)."""
        logger.info("_on_next_verse called")
        cur = self._current_display
        if cur and cur.get("item_type") == "slide":
            idx = cur.get("slide_index", 0) + 1
            if idx < len(cur.get("slides", [])):
                return self._apply_slide_display(
                    self._current_sched_data, cur["deck_title"], cur["slides"], idx
                )
            return self._step_schedule(1)
        if self._current_from_schedule and self._current_sched_data is not None:
            return self._step_schedule(1)
        if not self._next_verse_data:
            logger.info("next_verse: no next verse")
            return
        nxt = self._next_verse_data
        version = nxt.get("version", "") or (self._current_display.get("version", "") if self._current_display else "")
        self._navigate_to_bible_verse(nxt, version, skip_navigator=True)

    def _update_verse_neighbors(self, version: str, book: str, chapter: int, verse: int):
        """Compute and store the previous and next verse relative to the given verse."""
        from core.bible_service import get_prev_verse, get_next_verse
        try:
            self._prev_verse_data = get_prev_verse(version, book, chapter, verse)
        except Exception:
            self._prev_verse_data = None
        try:
            self._next_verse_data = get_next_verse(version, book, chapter, verse)
        except Exception:
            self._next_verse_data = None

    def _navigate_to_bible_verse(self, verse_data: dict, version: str, skip_navigator: bool = False):
        """Display a Bible verse on live + preview. Optionally skip translation switch."""
        book = verse_data.get("book", "")
        chapter = str(verse_data.get("chapter", ""))
        verse_num = str(verse_data.get("verse", ""))
        text = verse_data.get("text", "")

        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        self._current_display = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse_num,
            "version": version,
        }
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)

        if skip_navigator:
            # Highlight + scroll (ensure visible) + update navigator inputs, but no translation switch
            self.browser_panel._set_highlight(book, int(chapter), int(verse_num))
            self.browser_panel._scroll_to_highlight()
            self.browser_panel._update_navigator()
        else:
            self.browser_panel.navigate_to_reference(book, chapter, verse_num, translation=version)

        # Update neighbors for next prev/next press
        if book and chapter and verse_num and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse_num))

        logger.info(f"Prev/Next → {ref}")

    def _display_schedule_item(self, item: dict):
        """Display a schedule item on the live output only (verse or slide deck)."""
        if item.get("item_type") == "slide":
            slides = item.get("slides", [])
            self._apply_slide_display(item, item.get("name") or item.get("ref", ""), slides, 0)
            return

        ref = item.get("ref", "")
        text = item.get("text", "")
        version = item.get("translation", "")

        reference = ref.split("] ", 1)[1] if "] " in ref else ref
        parts = reference.rsplit(":", 1)
        book_chapter = parts[0] if len(parts) == 2 else reference
        verse = parts[1] if len(parts) == 2 else ""
        book = book_chapter.rsplit(" ", 1)[0] if " " in book_chapter else book_chapter
        chapter = book_chapter.rsplit(" ", 1)[1] if " " in book_chapter else ""

        # Keep the operator's navigator in sync when stepping through the schedule
        if book and chapter and verse and version:
            self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)

        self._current_sched_data = item
        self._current_from_schedule = True

        self._current_display = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version,
        }
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self.live_preview.set_live_payload(payload)

        self._broadcast_to_ws(payload)

        if book and chapter and verse and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse))

    def _on_schedule_click(self, data: dict):
        """Single-click schedule item: navigate to verse in browser + update preview."""
        theme = data.get("theme", "default")

        # ── Slide deck item ──
        if data.get("item_type") == "slide":
            slides = data.get("slides", [])
            if not slides:
                return
            slide = slides[0]
            section = slide.get("section")
            title = data.get("name") or data.get("ref") or "(untitled)"
            ref = f"{title} \u00b7 {section}" if section else title

            self._current_preview = {
                "item_type": "slide",
                "text": slide.get("text", ""),
                "ref": ref,
                "book": "", "chapter": "", "verse_num": "", "version": "",
                "deck_title": title,
                "section": section,
                "slides": slides,
                "slide_index": 0,
            }

            saved_theme = self._current_theme
            self._current_theme = theme
            payload = self._build_payload(slide.get("text", ""), ref, "")
            self._current_theme = saved_theme
            self.live_preview.set_preview_payload(payload)
            logger.info(f"Schedule preview (slide): {ref}")
            return

        # ── Verse item (existing behavior) ──
        ref = data.get("ref", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse = data.get("verse", "")
        text = data.get("text", "")
        version = data.get("translation", "")

        # Navigate browser to this verse
        self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)

        self._current_preview = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version
        }

        from core.theme_loader import get_theme
        saved_theme = self._current_theme
        self._current_theme = theme
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self._current_theme = saved_theme
        self.live_preview.set_preview_payload(payload)
        logger.info(f"Schedule preview: {ref}")

    def _on_schedule_double_click(self, data: dict):
        """Double-click schedule item: navigate to verse + push to live with its frozen theme."""
        theme = data.get("theme", "default")

        # ── Slide deck item ──
        if data.get("item_type") == "slide":
            slides = data.get("slides", [])
            if not slides:
                return
            self._apply_slide_display(
                data, data.get("name") or data.get("ref", ""), slides, 0
            )
            logger.info(f"Schedule live (slide deck): {data.get('ref', '')} (theme: {theme})")
            return

        # ── Verse item (existing behavior) ──
        ref = data.get("ref", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse = data.get("verse", "")
        text = data.get("text", "")
        version = data.get("translation", "")

        # Navigate browser to this verse
        self.browser_panel.navigate_to_reference(book, chapter, verse, translation=version)

        self._current_sched_data = data
        self._current_from_schedule = True

        self._current_display = {
            "text": text,
            "book": book,
            "chapter": chapter,
            "verse_num": verse,
            "version": version,
        }
        self._is_cleared = False

        from core.theme_loader import get_theme
        saved_theme = self._current_theme
        self._current_theme = theme
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self._current_theme = saved_theme
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)
        if book and chapter and verse and version:
            self._update_verse_neighbors(version, book, int(chapter), int(verse))
        logger.info(f"Schedule live: {ref} (theme: {theme})")

    def _on_start_transcription(self):
        """Start audio capture (Thread 1) and STT inference (Thread 2)."""
        try:
            from core.stt_inference import start_stt
            from core.audio_capture import start_capture
            from core.database import get_setting
            from core.service_manager import service_active
            
            service_active.set()
            
            saved = get_setting("audio.device_index", "")
            device_index = int(saved) if saved and saved.isdigit() else None
            
            start_capture(device_index=device_index)
            start_stt()
            
            # Update button states
            self.stt_panel._is_transcribing = True
            self.stt_panel._set_btn_recording()
            self.stt_panel.btn_transcribe.setText("STOP")
            self.stt_panel.btn_transcribe.setStyleSheet(self.stt_panel._stt_btn_active_style)
            
            logger.info(f"Transcription started (T1 + T2), device={device_index}")
        except Exception as e:
            logger.error(f"Failed to start transcription: {e}")

    def _on_stop_transcription(self):
        """Stop audio capture (Thread 1) and STT inference (Thread 2)."""
        try:
            from core.stt_inference import stop_stt
            from core.audio_capture import stop_capture
            from core.service_manager import service_active
            
            stop_capture()
            stop_stt()
            service_active.clear()
            
            # Update button states
            self.stt_panel._is_transcribing = False
            self.stt_panel._set_btn_ready()
            self.stt_panel.btn_transcribe.setText("TRANSCRIBE")
            self.stt_panel.btn_transcribe.setStyleSheet(self.stt_panel._stt_btn_style)
            
            logger.info("Transcription stopped (T1 + T2)")
        except Exception as e:
            logger.error(f"Failed to stop transcription: {e}")

    def _toggle_recording(self):
        """Toggle audio recording on/off."""
        from core import audio_recorder
        from core.audio_capture import start_capture
        from core.database import get_setting
        from core.service_manager import service_active

        if audio_recorder.is_recording():
            filepath = audio_recorder.stop_recording()
            self.stt_panel.set_recording_state(False)
            logger.info(f"Recording saved: {filepath}")
        else:
            # Ensure audio capture is running
            if not service_active.is_set():
                service_active.set()
                saved = get_setting("audio.device_index", "")
                device_index = int(saved) if saved and saved.isdigit() else None
                start_capture(device_index=device_index)

            saved = get_setting("audio.device_index", "")
            device_index = int(saved) if saved and saved.isdigit() else None
            audio_recorder.start_recording(device_index=device_index)
            self.stt_panel.set_recording_state(True)

    def _toggle_pause_recording(self):
        """Pause/resume audio recording."""
        from core import audio_recorder
        audio_recorder.pause_recording()
        if audio_recorder.is_paused():
            self.stt_panel.btn_pause_rec.setText("RESUME")
        else:
            self.stt_panel.btn_pause_rec.setText("PAUSE")

    def _broadcast_to_ws(self, payload: dict):
        """
        Send a display payload to all connected outputs via WebSocket.
        Each output receives the payload with its own theme applied.
        For non-theme-specific payloads (like clear), sends as-is to all.
        """
        try:
            from core.websocket_server import broadcast_display, _server_loop

            if _server_loop is None or _server_loop.is_closed():
                return

            if payload.get("action") == "clear":
                asyncio.run_coroutine_threadsafe(
                    broadcast_display(payload), _server_loop
                )
            else:
                for oid in self._themes_by_output:
                    themed = self._build_payload(
                        payload.get("text", ""),
                        payload.get("ref", ""),
                        payload.get("translation", ""),
                        payload.get("book", ""),
                        payload.get("chapter", ""),
                        payload.get("verse", ""),
                        output_id=oid,
                    )
                    asyncio.run_coroutine_threadsafe(
                        broadcast_display(themed, target=oid), _server_loop
                    )
        except Exception as e:
            logger.error(f"Failed to initiate WebSocket broadcast: {e}")

    # ── Schedule Filing ──────────────────────────────────────────────

    def _on_schedule_modified(self):
        """Prompt user when schedule has unsaved changes."""
        from PyQt6.QtWidgets import QMessageBox
        # Just log for now; the panel tracks modification state
        logger.info("Schedule modified — unsaved changes")

    def _on_schedule_loaded(self, file_path: str):
        """Called when a schedule file is loaded."""
        from core.database import set_setting
        set_setting("display.last_schedule", file_path)
        logger.info(f"Schedule loaded: {file_path}")

    def _restore_last_schedule(self):
        """Restore the last used schedule on startup."""
        from core.database import get_setting
        last_path = get_setting("display.last_schedule", "")
        if last_path and os.path.exists(last_path):
            try:
                self.schedule_panel.load_schedule(last_path)
                logger.info(f"Restored last schedule: {last_path}")
            except Exception as e:
                logger.warning(f"Could not restore last schedule: {e}")
