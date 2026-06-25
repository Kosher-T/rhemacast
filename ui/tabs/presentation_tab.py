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
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import (
    MACRO_BTN_AMBER, MACRO_BTN_CLEAR,
    RED_500, WHITE, SLATE_950, BORDER_SUBTLE
)

logger = logging.getLogger(__name__)


class LiveOutputFrame(QWidget):
    """Center panel: Live output viewport + macro controls."""

    clear_recall = pyqtSignal()
    prev_verse = pyqtSignal()
    next_verse = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Live indicator (outside the viewport)
        live_row = QHBoxLayout()
        live_row.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
        live_row.setContentsMargins(0, 0, 0, 4)
        live_dot = QLabel("●")
        live_dot.setStyleSheet(f"color: {RED_500}; font-size: 10px;")
        live_label = QLabel("LIVE")
        live_label.setStyleSheet(f"""
            color: {RED_500}; font-size: 12px; font-weight: 900;
            letter-spacing: 3px;
        """)
        live_row.addWidget(live_dot)
        live_row.addWidget(live_label)
        layout.addLayout(live_row)
        
        # ── Live Output Viewport ──
        self.viewport = QFrame()
        self.viewport.setObjectName("LiveOutputViewport")
        self.viewport.setStyleSheet(f"""
            QFrame#LiveOutputViewport {{
                background: black;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
            }}
        """)
        
        self.ar_widget = AspectRatioWidget(self.viewport, aspect_ratio=16.0/9.0, min_width=320, max_width=840)

        vp_layout = QVBoxLayout(self.viewport)
        vp_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.output_label = QLabel("LIVE OUTPUT")
        self.output_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 12);
            font-size: 28px; font-weight: 900;
            font-style: italic;
        """)
        self.output_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vp_layout.addWidget(self.output_label)

        layout.addWidget(self.ar_widget, 1)

        # ── Macro Controls ──
        controls_container = QWidget()
        controls = QHBoxLayout(controls_container)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(12)

        btn_prev = QPushButton("<")
        btn_prev.setStyleSheet(MACRO_BTN_AMBER)
        btn_prev.setFixedSize(80, 40)
        btn_prev.setToolTip("Previous Verse")
        btn_prev.clicked.connect(self.prev_verse.emit)
        controls.addWidget(btn_prev)

        _icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "eye-off.svg")
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(QIcon(_icon_path))
        self.btn_clear.setIconSize(QSize(18, 18))
        self.btn_clear.setStyleSheet(MACRO_BTN_CLEAR)
        self.btn_clear.setFixedSize(90, 40)
        self.btn_clear.setToolTip("Clear screen / Recall last cleared verse")
        self.btn_clear.clicked.connect(self.clear_recall.emit)
        controls.addWidget(self.btn_clear)

        btn_next = QPushButton(">")
        btn_next.setStyleSheet(MACRO_BTN_AMBER)
        btn_next.setFixedSize(80, 40)
        btn_next.setToolTip("Next Verse")
        btn_next.clicked.connect(self.next_verse.emit)
        controls.addWidget(btn_next)

        macro_wrapper = QHBoxLayout()
        macro_wrapper.addStretch()
        macro_wrapper.addWidget(controls_container)
        macro_wrapper.addStretch()
        layout.addLayout(macro_wrapper)

    def set_live_text(self, text: str, ref: str):
        """Update the live output viewport with verse text."""
        self.output_label.setText(f"{text}\n\n— {ref}")
        self.output_label.setStyleSheet(f"""
            color: {WHITE};
            font-size: 16px; font-weight: 600;
            font-style: normal;
            padding: 16px;
        """)
        self.output_label.setWordWrap(True)

    def clear_live_output(self):
        """Reset the live output to its default empty state."""
        self.output_label.setText("LIVE OUTPUT")
        self.output_label.setStyleSheet(f"""
            color: rgba(255, 255, 255, 12);
            font-size: 28px; font-weight: 900;
            font-style: italic;
        """)


class PresentationTab(QWidget):
    """The main Presentation workspace tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Display state
        self._current_display = None      # Currently displayed verse dict
        self._last_cleared_display = None  # Last verse before clear (for recall)
        self._is_cleared = True
        
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
        self.live_output = LiveOutputFrame()
        self.stt_panel = STTPanel()

        top_splitter.addWidget(wrap_panel(self.schedule_panel))
        top_splitter.addWidget(self.live_output) # Center panel has its own padding/wrapper logic
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
        
        # Live output: clear/recall toggle
        self.live_output.clear_recall.connect(self._on_clear_recall)
        
        # Live output: prev/next verse navigation (uses schedule)
        self.live_output.prev_verse.connect(self._on_prev_verse)
        self.live_output.next_verse.connect(self._on_next_verse)
        
        # STT panel: transcription start/stop → control Thread 1 + Thread 2
        self.stt_panel.transcription_started.connect(self._on_start_transcription)
        self.stt_panel.transcription_stopped.connect(self._on_stop_transcription)
        
        # Browser panel: double-click broadcast
        self.browser_panel.broadcast_in_version.connect(self._on_browser_broadcast)

    def _on_display_verse(self, data: dict):
        """
        Called when operator clicks 'Show' on a queue item.
        Updates the live output, operator preview, and broadcasts via WebSocket.
        """
        verse_text = data.get("text", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        ref = f"[{version}] {book} {chapter}:{verse_num}"
        
        # Update local display state
        self._current_display = data
        self._is_cleared = False
        
        # Update UI
        self.live_output.set_live_text(verse_text, ref)
        self.stt_panel.update_preview(verse_text, ref)
        
        # Add to schedule if not already there
        self.schedule_panel.add_item(ref, version, verse_text)
        
        # Broadcast via WebSocket
        self._broadcast_to_ws({
            "action": "display",
            "text": verse_text,
            "ref": ref,
            "translation": version,
            "book": book,
            "chapter": str(chapter),
            "verse": str(verse_num),
            "theme": "default"
        })
        
        logger.info(f"Displaying: {ref}")

    def _on_browser_broadcast(self, version: str):
        """Called when operator double-clicks a translation in the browser panel."""
        verse_data = self.browser_panel.get_selected_verse()
        if not verse_data:
            return
        
        book = self.browser_panel._current_book or ""
        ref = f"[{version}] {book} {verse_data['chapter']}:{verse_data['verse']}"
        text = verse_data.get("text", "")
        
        self._current_display = {
            "text": text,
            "book": book,
            "chapter": verse_data["chapter"],
            "verse_num": verse_data["verse"],
            "version": version
        }
        self._is_cleared = False
        
        self.live_output.set_live_text(text, ref)
        self.stt_panel.update_preview(text, ref)
        self.schedule_panel.add_item(ref, version, text)
        
        self._broadcast_to_ws({
            "action": "display",
            "text": text,
            "ref": ref,
            "translation": version,
            "book": book,
            "chapter": str(verse_data["chapter"]),
            "verse": str(verse_data["verse"]),
            "theme": "default"
        })
        
        logger.info(f"Browser broadcast: {ref}")

    def _on_clear_recall(self):
        """Toggle between clear and recall of the last displayed verse."""
        if not self._is_cleared and self._current_display:
            # Clear the screen
            self._last_cleared_display = self._current_display
            self._current_display = None
            self._is_cleared = True
            
            self.live_output.clear_live_output()
            self.stt_panel.clear_preview()
            
            self._broadcast_to_ws({"action": "clear"})
            logger.info("Display cleared")
            
        elif self._is_cleared and self._last_cleared_display:
            # Recall the last cleared verse
            self._on_display_verse(self._last_cleared_display)
            logger.info("Display recalled")

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
        """Display a schedule item on the live output."""
        ref = item.get("ref", "")
        text = item.get("text", "")
        version = item.get("translation", "")
        
        self._current_display = item
        self._is_cleared = False
        
        self.live_output.set_live_text(text, ref)
        self.stt_panel.update_preview(text, ref)
        
        self._broadcast_to_ws({
            "action": "display",
            "text": text,
            "ref": ref,
            "translation": version,
            "theme": item.get("theme", "default")
        })

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
