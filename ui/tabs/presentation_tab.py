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
        self._current_theme = "default"   # Active display theme
        
        # Schedule navigation index
        self._schedule_index = -1

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
        
        # Browser panel: single-click → update preview only
        self.browser_panel.verse_clicked.connect(self._on_verse_single_click)
        
        # Browser panel: double-click → update live + preview
        self.browser_panel.broadcast_in_version.connect(self._on_browser_broadcast)

        # Browser panel: Alt+click verse(s) → add to schedule
        self.browser_panel.verses_to_schedule.connect(self._on_verses_to_schedule)

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
        
        # Schedule panel: single-click → preview, double-click → live
        self.schedule_panel.item_clicked.connect(self._on_schedule_click)
        self.schedule_panel.item_double_clicked.connect(self._on_schedule_double_click)

    def _build_payload(self, text: str, ref: str, version: str, book: str = "",
                       chapter: str = "", verse: str = "") -> dict:
        """Build a display payload matching the WS broadcast format."""
        from core.theme_loader import get_theme
        theme_data = get_theme(self._current_theme)
        return {
            "action": "display",
            "text": text,
            "ref": ref,
            "reference": f"{book} {chapter}:{verse}" if book else ref,
            "translation": get_display_name(version) if version else "",
            "book": book,
            "chapter": str(chapter),
            "verse": str(verse),
            "theme": self._current_theme,
            "theme_data": theme_data,
        }

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

        self._current_display = data
        self._is_cleared = False

        payload = self._build_payload(verse_text, ref, version, book, chapter, verse_num)
        self.live_preview.set_live_payload(payload)

        self._broadcast_to_ws(payload)

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

        logger.info(f"Browser broadcast: {ref}")

    def _on_verses_to_schedule(self, verses: list):
        """Add one or more verses (from Alt+click in browser) to the schedule."""
        for v in verses:
            item_data = {
                "ref": f"{v.get('book', '')} {v.get('chapter', '')}:{v.get('verse', '')}".strip(),
                "book": v.get("book", ""),
                "chapter": v.get("chapter", ""),
                "verse": v.get("verse", ""),
                "text": v.get("text", ""),
                "translation": v.get("translation", ""),
                "theme": v.get("theme", "default"),
            }
            self.schedule_panel.add_item(item_data)
        logger.info(f"Queued {len(verses)} verse(s) to schedule via Alt+click")

    def _on_search_to_schedule(self, data: dict):
        """Add a search result verse to the schedule."""
        item_data = {
            "ref": f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}".strip(),
            "book": data.get("book", ""),
            "chapter": data.get("chapter", ""),
            "verse": data.get("verse_num", ""),
            "text": data.get("text", ""),
            "translation": data.get("version", ""),
            "theme": "default",
        }
        self.schedule_panel.add_item(item_data)
        logger.info(f"Search result sent to schedule: {item_data['ref']}")

    def _on_search_to_navigator(self, data: dict):
        """Single-click search result → navigate browser to that reference in current translation + update preview with navigator's translation."""
        book = data.get("book", "")
        chapter = str(data.get("chapter", ""))
        verse = str(data.get("verse_num", ""))
        # Navigate in the current browser translation (don't switch)
        version = self.browser_panel._current_translation
        self.browser_panel.navigate_to_reference(book, chapter, verse)

        # Fetch verse text from the CURRENT browser translation (navigator's translation)
        from core.bible_service import get_verse
        verse_data = get_verse(version, book, int(chapter), int(verse))
        text = verse_data.get("text", "") if verse_data else data.get("text", "")

        # Update preview with the navigator's translation
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

    def _on_preview_double_click(self):
        """Called when operator double-clicks the preview screen. Pushes preview to live."""
        if not self._current_preview:
            return

        data = self._current_preview
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

        logger.info(f"Preview pushed to live: {ref}")

    def _on_clear_recall(self):
        """Toggle between clear and recall of the last displayed verse."""
        if not self._is_cleared and self._current_display:
            self._last_cleared_display = self._current_display
            self._current_display = None
            self._is_cleared = True

            self.live_preview.clear_live()

            self._broadcast_to_ws({"action": "clear"})
            logger.info("Display cleared")

        elif self._is_cleared and self._last_cleared_display:
            self._on_display_verse(self._last_cleared_display)
            logger.info("Display recalled")

    def _on_theme_changed(self, theme_name: str):
        """Single-click theme: set as default + re-render preview verse with new theme."""
        self._current_theme = theme_name
        from core.theme_loader import set_current_theme
        set_current_theme(theme_name)
        if self._current_preview:
            data = self._current_preview
            book = data.get("book", "")
            chapter = data.get("chapter", "")
            verse_num = data.get("verse_num", "")
            version = data.get("version", "")
            ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"
            payload = self._build_payload(data.get("text", ""), ref, version, book, chapter, verse_num)
            self.live_preview.set_preview_payload(payload)
        logger.info(f"Theme changed to: {theme_name} (preview updated)")

    def _on_theme_double_click(self, theme_name: str):
        """Double-click theme: set as default + push preview to live with that theme."""
        self._current_theme = theme_name
        from core.theme_loader import set_current_theme
        set_current_theme(theme_name)
        if self._current_preview:
            data = self._current_preview
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

            logger.info(f"Theme double-clicked: {theme_name}, pushed preview to live")
        else:
            logger.info(f"Theme double-clicked: {theme_name} (no preview verse to push)")

    def _on_prev_verse(self):
        """Navigate to the previous item in the schedule."""
        schedule = self.schedule_panel.get_schedule()
        if not schedule:
            return
        
        self._schedule_index = max(0, self._schedule_index - 1)
        item = schedule[self._schedule_index]
        
        # Construct a display-compatible dict from the schedule item
        self._display_schedule_item(item)

    def _on_next_verse(self):
        """Navigate to the next item in the schedule."""
        schedule = self.schedule_panel.get_schedule()
        if not schedule:
            return
        
        self._schedule_index = min(len(schedule) - 1, self._schedule_index + 1)
        item = schedule[self._schedule_index]
        
        self._display_schedule_item(item)

    def _display_schedule_item(self, item: dict):
        """Display a schedule item on the live output only."""
        ref = item.get("ref", "")
        text = item.get("text", "")
        version = item.get("translation", "")

        reference = ref.split("] ", 1)[1] if "] " in ref else ref
        parts = reference.rsplit(":", 1)
        book_chapter = parts[0] if len(parts) == 2 else reference
        verse = parts[1] if len(parts) == 2 else ""
        book = book_chapter.rsplit(" ", 1)[0] if " " in book_chapter else book_chapter
        chapter = book_chapter.rsplit(" ", 1)[1] if " " in book_chapter else ""

        self._current_display = item
        self._is_cleared = False

        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self.live_preview.set_live_payload(payload)

        self._broadcast_to_ws(payload)

    def _on_schedule_click(self, data: dict):
        """Single-click schedule item: update preview only."""
        ref = data.get("ref", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse = data.get("verse", "")
        text = data.get("text", "")
        version = data.get("translation", "")
        theme = data.get("theme", "default")

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
        """Double-click schedule item: push to live with its frozen theme."""
        ref = data.get("ref", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse = data.get("verse", "")
        text = data.get("text", "")
        version = data.get("translation", "")
        theme = data.get("theme", "default")

        self._current_display = data
        self._is_cleared = False

        from core.theme_loader import get_theme
        saved_theme = self._current_theme
        self._current_theme = theme
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self._current_theme = saved_theme
        self.live_preview.set_live_payload(payload)
        self._broadcast_to_ws(payload)
        logger.info(f"Schedule live: {ref} (theme: {theme})")

    def _on_start_transcription(self):
        """Start audio capture (Thread 1) and STT inference (Thread 2)."""
        try:
            from core.stt_inference import start_stt
            from core.audio_capture import start_capture
            
            # Start audio capture on system default device
            start_capture(device_index=None)
            
            # Start STT inference
            start_stt()
            
            logger.info("Transcription started (T1 + T2)")
        except Exception as e:
            logger.error(f"Failed to start transcription: {e}")

    def _on_stop_transcription(self):
        """Stop audio capture (Thread 1) and STT inference (Thread 2)."""
        try:
            from core.stt_inference import stop_stt
            from core.audio_capture import stop_capture
            
            stop_capture()
            stop_stt()
            
            logger.info("Transcription stopped (T1 + T2)")
        except Exception as e:
            logger.error(f"Failed to stop transcription: {e}")

    def _broadcast_to_ws(self, payload: dict):
        """
        Send a display command to all connected WebSocket clients (OBS Browser Sources).
        Runs the async broadcast in a fire-and-forget manner.
        """
        try:
            from core.websocket_server import broadcast_display
            
            # We need to run the async broadcast from a sync context.
            # Use a thread to fire the coroutine without blocking the UI.
            def _fire():
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(broadcast_display(payload))
                    loop.close()
                except Exception as e:
                    logger.error(f"WebSocket broadcast error: {e}")
            
            t = threading.Thread(target=_fire, daemon=True)
            t.start()
        except Exception as e:
            logger.error(f"Failed to initiate WebSocket broadcast: {e}")
