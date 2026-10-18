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
import threading

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel,
    QPushButton, QFrame
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

        # Display state (see core/display_state.py): in prioritized mode
        # this is the shared singleton (preview/live identical across
        # tabs); in simultaneous mode it is this tab's own scoped state.
        # Tab-local gesture code accesses it through the properties below
        # — never plain attrs, so constructing this tab never wipes
        # another tab's screens.
        from core.display_state import display_state_for
        self._display = display_state_for("SCRIPTURE")
        self._prev_verse_data = None      # Previous verse (for Prev button)
        self._next_verse_data = None      # Next verse (for Next button)
        # Prev/next bracket whatever is DISPLAYED, and live_data is the one
        # record of that. Deriving them from a hook rather than from each
        # display path is deliberate: the queue used to be refreshed at
        # ten call sites, and the path that missed (a search-result click)
        # left the neighbours of the previously displayed verse in place,
        # so Next walked off from the wrong scripture.
        self._display.add_live_data_hook(self._on_live_data_changed)
        self._display.register_owner_op("SCRIPTURE", "step", self._step_verse)
        self._display.register_owner_op("SCRIPTURE", "uncloak", self._uncloak_now)
        self._init_workspace()

    # ── Shared-state aliases (read/write core.display_state) ──────────────

    @property
    def _current_display(self):
        return self._display.live_data

    @_current_display.setter
    def _current_display(self, value):
        self._display.live_data = value

    @property
    def _current_preview(self):
        return self._display.preview_data

    @_current_preview.setter
    def _current_preview(self, value):
        self._display.preview_data = value

    @property
    def _last_cleared_display(self):
        return self._display.last_cleared_data

    @_last_cleared_display.setter
    def _last_cleared_display(self, value):
        self._display.last_cleared_data = value

    @property
    def _is_cleared(self):
        return self._display.is_cleared

    @_is_cleared.setter
    def _is_cleared(self, value):
        self._display.is_cleared = value

    @property
    def _cloak(self):
        """Shared cloak state (DisplayState.cloaked) — persists across
        tabs by construction. Replaces the old per-tab clear/recall."""
        return self._display.cloaked

    @_cloak.setter
    def _cloak(self, value):
        self._display.set_cloaked(value)

    def _set_cloak(self, on: bool):
        """Single funnel for cloak transitions. Button syncs via the
        cloak_changed subscription below."""
        self._display.set_cloaked(on)

    def _obs_gated(self, payload: dict) -> bool:
        """True when this payload must not reach OBS: cloaked covers
        everything except the blank itself (mirror of the slides tab)."""
        return bool(self._cloak) and payload.get("action") != "clear"

    @property
    def _current_sched_data(self):
        uid = self._display.live_sched_uid
        if uid is None:
            return None
        return {"_sched_uid": uid}

    @_current_sched_data.setter
    def _current_sched_data(self, value):
        if isinstance(value, dict):
            self._display.live_sched_uid = value.get("_sched_uid")
            self._display.live_from_schedule = self._display.live_sched_uid is not None
        elif value is None:
            self._display.live_sched_uid = None
            self._display.live_from_schedule = False

    @property
    def _current_from_schedule(self):
        return self._display.live_from_schedule

    @_current_from_schedule.setter
    def _current_from_schedule(self, value):
        self._display.live_from_schedule = bool(value)

    def _init_workspace(self):
        """Build panels, wire signals, subscribe screens to shared state."""

        # Per-output themes: {"1": "default", "2": "default", ...}
        from core.database import get_setting
        from core.outputs import active_outputs, main_output_for_tab
        # Only the operator's ACTIVE outputs appear here; deleted outputs
        # stop broadcasting entirely.
        self._themes_by_output: dict[str, str] = {}
        for oid in active_outputs("SCRIPTURE"):
            self._themes_by_output[oid] = get_setting(f"display.output_{oid}_theme", "default")

        # Main output = this set's first active id (follows the Outputs
        # page when the operator deletes/adds outputs).
        self._main_output = main_output_for_tab("SCRIPTURE") or "1"
        self._current_theme = self._themes_by_output.get(self._main_output, "default")

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

        self._schedule_wrap = wrap_panel(self.schedule_panel)
        top_splitter.addWidget(self._schedule_wrap)
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

        # The bottom splitter is the whole scripture work area: browser plus
        # the themes/FTS/fuzzy queue. The focus ring wraps a plain container
        # around it (not the splitter itself): a QSplitter's layout engine
        # repositions its children, so an overlay parented directly to it
        # gets its geometry clobbered and the ring stops tracking the edge.
        bottom_splitter.addWidget(wrap_panel(self.browser_panel))
        bottom_splitter.addWidget(wrap_panel(self.queue_panel))

        def wrap_bottom(inner: QWidget) -> QWidget:
            box = QWidget()
            box_l = QVBoxLayout(box)
            box_l.setContentsMargins(0, 0, 0, 0)
            box_l.setSpacing(0)
            box_l.addWidget(inner)
            return box

        # Default widths: 60% | 40%
        bottom_splitter.setSizes([600, 400])

        self._work_wrap = wrap_bottom(bottom_splitter)
        main_splitter.addWidget(self._work_wrap)

        root_layout.addWidget(main_splitter)

        # ── Focus rings ──
        # One state machine owns both regions: the work area (browser +
        # themes/FTS/fuzzy queue) lights on scripture; the schedule ring
        # lights only while Alt+Left/Right navigation is armed — i.e. after
        # a schedule double-click into live, until a verse step or focus
        # leaving the schedule disarms it. Mere focus never arms. See
        # ui.focus_ring.FocusRingStateMachine.
        from ui.focus_ring import FocusRingStateMachine
        self._ring_state = FocusRingStateMachine(
            work_area=self._work_wrap,
            schedule=self._schedule_wrap,
            work_area_of_schedule=self._scripture_displayed,
            # Single-clicking a verse is preview navigation inside the
            # armed workflow: it must not disarm the schedule ring.
            arm_keep=(self.browser_panel.verse_list,),
        )
        # Re-evaluate whenever what is on live changes (deck vs scripture).
        self._display.nav_changed.connect(self._ring_state.update)
        self._display.nav_changed.connect(self._enforce_verse_typing_focus)
        app = QApplication.instance()
        if app is not None:
            app.focusChanged.connect(self._enforce_verse_typing_focus)

        # Persisted layouts (defaults on first run; saved sizes win after).
        from core.panel_layout import track_splitter
        self._main_splitter = track_splitter(
            "presentation.main", main_splitter, [650, 350])
        self._top_splitter = track_splitter(
            "presentation.top", top_splitter, [300, 600, 300])
        self._bottom_splitter = track_splitter(
            "presentation.bottom", bottom_splitter, [600, 400])

        # ── Wire all signals ──
        self._connect_signals()

    def _enforce_verse_typing_focus(self, *_args) -> None:
        """Keep the caret where verse typing actually works.

        The quick-verse shortcut fires from anywhere except a box that
        wants the digits, but "works" is not the same as "obvious": if the
        work-area ring is lit (scripture is what the operator is working
        with) and the caret has drifted to some widget in the work area
        that is neither a text box nor the verse list, the operator gets a
        verse push with nothing visibly selected and no caret to steer
        with. Put the caret on the verse list so the take has an anchor.

        Scoped to the work area on purpose. The ring is lit whenever
        scripture is displayed, which includes while the operator is in
        the schedule — yanking the caret back from there would make the
        schedule unusable, so the schedule is left alone.
        """
        app = QApplication.instance()
        if app is None:
            return
        try:
            focused = app.focusWidget()
            if focused is None:
                return
            if not self._scripture_displayed():
                return
            # A text box owns its keystrokes — never take the caret.
            from ui.widgets.quick_verse import _is_digit_consuming
            if _is_digit_consuming(focused):
                return
            from ui.focus_ring import _within
            if not _within(focused, self._work_wrap):
                return
            if _within(focused, self.browser_panel):
                return  # already somewhere useful in the Bible panel
            self.browser_panel.focus_verse_list()
        except RuntimeError:
            pass

    def _scripture_displayed(self) -> bool:
        """True while SCRIPTURE (not a slide deck) is what's on live.

        Drives the work-area focus ring: a deck on live means the operator
        is working slides, so the scripture work-area ring steps aside. A
        cleared / never-set live screen counts as scripture — the ring is
        the resting state, not an exception.
        """
        data = self._current_display
        if not data:
            return True
        return data.get("item_type") != "slide"

    def showEvent(self, event):
        super().showEvent(event)
        # Screens first: re-push shared state so the tab never presents
        # a hidden view's last committed (stale) frame on arrival.
        self.resync_screens()
        # Focus rings are sized lazily; re-sync and re-evaluate now that
        # this tab actually has real geometry.
        self._ring_state.update()
        # Re-apply saved splitter layouts once real sizes exist
        from core.panel_layout import restore_splitter
        restore_splitter("presentation.main", self._main_splitter)
        restore_splitter("presentation.top", self._top_splitter)
        restore_splitter("presentation.bottom", self._bottom_splitter)

    def _connect_signals(self):
        """Connect all panel signals to their backend actions."""
        
        # Queue panel: "Show" button → broadcast verse to display
        self.queue_panel.display_requested.connect(self._on_display_verse)
        
        # Queue panel: theme selection → update preview only
        self.queue_panel.theme_changed.connect(self._on_theme_changed)
        
        # Queue panel: theme double-click → push preview to live with that theme
        self.queue_panel.theme_double_clicked.connect(self._on_theme_double_click)
        self.queue_panel.outputs_changed.connect(self._on_outputs_changed)
        
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

        # Browser panel: translation double-click → push LIVE verse in it
        self.browser_panel.broadcast_live_translation.connect(self._on_translation_broadcast)

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

        # Screens render the SHARED display state — this tab's views update
        # whenever any tab publishes (and vice versa).
        self._display.live_changed.connect(self.live_preview.set_live_payload)
        self._display.preview_changed.connect(self.live_preview.set_preview_payload)
        self._display.cleared.connect(self.live_preview.clear_live)
        # Cloak button mirrors the SHARED cloak state — whichever tab
        # toggles, both tabs' buttons follow.
        self._display.cloak_changed.connect(self.live_preview.set_clear_active)
        self.live_preview.set_clear_active(self._display.cloaked)
        # Render whatever is already showing (e.g. published before this tab loaded)
        if self._display.live_payload:
            self.live_preview.set_live_payload(self._display.live_payload)
        if self._display.preview_payload:
            self.live_preview.set_preview_payload(self._display.preview_payload)

        # Restore last schedule on startup
        self._restore_last_schedule()

    def _build_payload(self, text: str, ref: str, version: str, book: str = "",
                       chapter: str = "", verse: str = "", output_id: str | None = None,
                       slide_format: dict | None = None,
                       content: str = "verse", deck_id: int | None = None) -> dict:
        """Build a display payload matching the WS broadcast format.

        Slide text may carry inline color markup ([words: (#rrggbb)]). It is
        sent RAW here: sanitize_payload() HTML-escapes the payload for the
        wire, and display.js converts markers to <span> at render time.
        (Converting here would double-escape the spans into visible text.)
        """
        from core.theme_loader import resolve_theme
        output_id = output_id or self._main_output_id()
        theme_name = self._themes_by_output.get(output_id, "default")
        # Per-kind fallback: slide content never falls back app-wide to the
        # scripture theme.
        fallback = "slides" if content == "slide" else "default"
        theme_name, theme_data = resolve_theme(theme_name, fallback=fallback)
        payload = {
            "action": "display",
            "text": text,
            "ref": ref,
            "reference": f"{book} {chapter}:{verse}" if book else ref,
            "translation": get_display_name(version) if version else "",
            "book": book,
            "chapter": str(chapter),
            "verse": str(verse),
            "content": content,
            "theme": theme_name,
            "theme_data": theme_data,
        }
        if slide_format is not None:
            payload["slide_format"] = slide_format
        if deck_id is not None:
            payload["deck_id"] = deck_id
        return payload

    def _payload_for_display(self, data: dict, output_id: str | None = None) -> dict:
        """Build a display payload from a stored display dict (verse or slide)."""
        output_id = output_id or self._main_output_id()
        if data.get("item_type") == "slide":
            return self._build_payload(
                data.get("text", ""), data.get("ref", ""), "",
                output_id=output_id,
                slide_format=data.get("slide_format"),
                content="slide",
                deck_id=data.get("deck_id"),
            )
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        # Ref-only dicts (e.g. previewed from the SLIDES tab) have no
        # book/chapter parts — pass their stored ref through instead of
        # building "[T]  :" from empty parts.
        if book and chapter and verse_num:
            ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"
        else:
            ref = data.get("ref", "")
        return self._build_payload(data.get("text", ""), ref, version, book, chapter, verse_num, output_id=output_id)

    def _apply_slide_display(self, sched_data: dict | None, deck_title: str,
                             slides: list, index: int, uncloak: bool = False):
        """Display a single slide of a deck on live + broadcast.

        Stores enough state (slides list + index + schedule identity) for
        Left/Right to step through this deck's slides. Schedule items are
        stepped with Alt+Left / Alt+Right instead.
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
        slide_format = (sched_data.get("format")
                        if isinstance(sched_data, dict) else None)
        self._current_display = {
            "item_type": "slide",
            "text": text,
            "ref": ref,
            "book": "", "chapter": "", "verse_num": "", "version": "",
            "deck_title": title,
            "section": section,
            "slide_format": slide_format,
            "deck_id": (sched_data.get("deck_id")
                        if isinstance(sched_data, dict) else None),
            "slides": slides,
            "slide_index": index,
        }
        self._is_cleared = False

        deck_id = (sched_data.get("deck_id")
                     if isinstance(sched_data, dict) else None)
        if uncloak:
            # Double-click push removes the cloak (one of its two exits).
            self._set_cloak(False)
        payload = self._build_payload(text, ref, "", slide_format=slide_format,
                                        content="slide", deck_id=deck_id)
        # Publish to shared state (renders in every tab's live view)
        self._display.publish_live(payload, self._current_display,
                                   self._display.live_sched_uid,
                                   self._display.live_from_schedule)
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
        self._display.publish_live(payload, data, None, False)

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
        # Double-click push removes the cloak (one of its two exits).
        self._set_cloak(False)

        payload = self._build_payload(text, ref, version, book, verse_data["chapter"], verse_data["verse"])
        self._display.publish_live(payload, verse_dict, None, False)
        self._display.publish_preview(payload, verse_dict)

        self._broadcast_to_ws(payload)

        logger.info(f"Browser broadcast: {ref}")

    def _on_translation_broadcast(self, version: str):
        """Translation double-click: push the LIVE reference in `version`.

        Single-click works the preview (highlighted) verse; double-click
        re-renders whatever is already live. Falls back to the highlighted
        verse when nothing is live yet (or the live ref is missing here).
        """
        live = self._current_display or {}
        book = live.get("book", "")
        chapter = live.get("chapter", "")
        verse = live.get("verse_num", "")
        if book and chapter and verse:
            from core.bible_service import get_verse
            try:
                verse_data = get_verse(version, book, int(chapter), int(verse))
            except (TypeError, ValueError):
                verse_data = None
            if verse_data:
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
                self._set_cloak(False)

                payload = self._build_payload(text, ref, version, book, chapter, verse)
                self._display.publish_live(payload, verse_dict, None, False)
                self._broadcast_to_ws(payload)
                logger.info(f"Translation broadcast (live ref): {ref}")
                return
        self._on_browser_broadcast(version)

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
        self._display.publish_live(payload, verse_dict, None, False)
        self._display.publish_preview(payload, verse_dict)
        self._broadcast_to_ws(payload)
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
        self._display.publish_preview(payload, self._current_preview)

        # Preview-only by design (single click is a navigator-style action),
        # so live_data never changes and the display hook does not fire.
        # But the operator has moved: Next/Prev must step from the verse
        # they just clicked, not from whatever is still on live.
        self._set_verse_position(version, book, chapter, verse)
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
        # Double-click push removes the cloak (one of its two exits).
        self._set_cloak(False)

        payload = self._build_payload(text, ref, version, book, chapter, verse_num)
        self._display.publish_live(payload, verse_dict, None, False)
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
        self._display.publish_preview(payload, self._current_preview)
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
        # Double-click push removes the cloak (one of its two exits).
        self._set_cloak(False)

        payload = self._build_payload(text, ref, version, book, chapter, verse_num)
        self._display.publish_live(payload, verse_dict, None, False)
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
        self._display.publish_preview(payload, self._current_preview)
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
                uncloak=True,
            )
            logger.info(f"Preview pushed to live (slide): {data.get('ref', '')}")
            return

        # ── Verse preview ──
        # Replay beats rebuild: the stored payload carries the inline verse
        # number, the full reference and the theme this content was
        # rendered with. Rebuilding from the navigation dict alone loses
        # all three (bare text + translation on the OBS screen).
        stored = self._display.matching_preview_payload()
        if stored is not None:
            self._current_display = data
            self._is_cleared = False
            self._set_cloak(False)
            self._display.publish_live(stored, data,
                                       self._display.live_sched_uid,
                                       self._display.live_from_schedule)
            self._broadcast_to_ws(stored, data)
            logger.info(f"Preview pushed to live (replayed): {stored.get('ref', '')}")
            return

        verse_text = data.get("text", "")
        book = data.get("book", "")
        chapter = data.get("chapter", "")
        verse_num = data.get("verse_num", "")
        version = data.get("version", "")
        ref = f"[{get_display_name(version)}] {book} {chapter}:{verse_num}"

        self._current_display = data
        self._is_cleared = False
        # Double-click push removes the cloak (one of its two exits).
        self._set_cloak(False)

        payload = self._build_payload(verse_text, ref, version, book, chapter, verse_num)
        self._display.publish_live(payload, data,
                                   self._display.live_sched_uid,
                                   self._display.live_from_schedule)

        self._broadcast_to_ws(payload)


        logger.info(f"Preview pushed to live: {ref}")

    def resync_screens(self):
        """Cover-gated silent re-push of shared payloads into this tab's
        views (idempotent). See SlidesTab.resync_screens for the full
        rationale; cloak re-blanks instead of re-pushing."""
        if self._display.cloaked:
            live = "clear"
        elif self._display.live_payload:
            live = self._display.live_payload
        else:
            live = None
        self.live_preview.refresh_views(live, self._display.preview_payload)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self.live_preview.reveal_screens)

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
        """Cloak toggle — replaces the old clear/recall. Shared state:
        toggling here cloaks/uncloaks both tabs' live screens and OBS."""
        if not self._cloak:
            self._cloak_now()
            return
        # Uncloak restores the live screen, so the tab that OWNS the
        # displayed content performs it: a deck slide uncloaked here would
        # be rebuilt with scripture themes and pushed to scripture outputs.
        if self._display.dispatch_to_owner("uncloak"):
            return
        self._uncloak_now()

    def _cloak_now(self):
        """Blank the live screen; the model and preview stay intact."""
        self._set_cloak(True)
        from core.outputs import shared_display_enabled
        self._broadcast_to_ws({"action": "clear"}, self._current_display,
                              scope_all=shared_display_enabled())
        logger.info("Display cloaked")

    def _uncloak_now(self):
        """Reveal what is current now, replaying the stored payload so the
        originating output theme returns with it (a deck cloaked in SLIDES
        does not come back wearing SCRIPTURE's theme)."""
        self._set_cloak(False)
        stored = self._display.matching_live_output_payload()
        if stored is not None and self._current_display:
            payload = stored
            self._display.publish_live(payload, self._current_display,
                                       self._display.live_sched_uid,
                                       self._display.live_from_schedule)
            self._broadcast_to_ws(payload, self._current_display,
                                  preserve_theme=True)
        elif self._current_display:
            payload = self._payload_for_display(self._current_display)
            self._display.publish_live(payload, self._current_display,
                                       self._display.live_sched_uid,
                                       self._display.live_from_schedule)
            self._broadcast_to_ws(payload, self._current_display)
        if self._current_display:
            logger.info("Display uncloaked")

    def refresh_display_names(self, old_display: str, new_display: str):
        """Re-render current screens after a translation rename.

        Stored "[Old] ref" strings are patched, then preview/live rebuild
        from parts (resolving the new name) and live re-broadcasts.
        """
        prefix, new_prefix = f"[{old_display}]", f"[{new_display}]"
        for attr in ("_current_preview", "_current_display",
                     "_last_cleared_display"):
            data = getattr(self, attr, None)
            if isinstance(data, dict):
                ref = data.get("ref")
                if isinstance(ref, str) and ref.startswith(prefix):
                    data["ref"] = new_prefix + ref[len(prefix):]
        if self._current_preview:
            self._display.publish_preview(
                self._payload_for_display(self._current_preview),
                self._current_preview)
        if self._current_display and not self._is_cleared:
            payload = self._payload_for_display(self._current_display)
            self._display.publish_live(payload, self._current_display,
                                        self._display.live_sched_uid,
                                        self._display.live_from_schedule)
            self._broadcast_to_ws(payload)

    def _main_output_id(self) -> str:
        """This set's main output, tolerating test harnesses that build the
        tab without __init__ (Qt raises on any attribute then)."""
        try:
            return self._main_output or "1"
        except (AttributeError, RuntimeError):
            return "1"

    def _on_outputs_changed(self, output_ids: list):
        """Outputs page add/remove: adopt the new active set.

        Added outputs pick up their stored theme; removed ones stop
        broadcasting and stop being restored. When the main output itself
        was removed, the next surviving output becomes main.
        """
        from core.database import get_setting
        from core.outputs import active_outputs, main_output_for_tab
        active = list(output_ids or active_outputs("SCRIPTURE"))
        themes = {
            oid: self._themes_by_output.get(oid)
            or get_setting(f"display.output_{oid}_theme", "default")
            for oid in active
        }
        self._themes_by_output = themes
        self._main_output = main_output_for_tab("SCRIPTURE") or (active[0] if active else "1")
        self._current_theme = themes.get(self._main_output, "default")
        if self._current_preview:
            self._display.publish_preview(
                self._payload_for_display(self._current_preview),
                self._current_preview)
        logger.info(f"Scripture outputs now: {active} (main {self._main_output})")

    def _on_theme_changed(self, output_id: str, theme_name: str):
        """Single-click theme: update that output's theme + re-render preview."""
        self._themes_by_output[output_id] = theme_name
        # Keep legacy property in sync
        if output_id == self._main_output_id():
            self._current_theme = theme_name

        if output_id == self._main_output and self._current_preview:
            # Main output preview update (handles verse + slide dicts,
            # including ref-only shapes previewed from the SLIDES tab).
            data = self._current_preview
            payload = self._payload_for_display(data, output_id="1")
            self._display.publish_preview(payload, data)
        logger.info(f"Output {output_id} theme changed to: {theme_name}")

    def _on_theme_double_click(self, output_id: str, theme_name: str):
        """Double-click theme: update that output's theme + re-render live + broadcast."""
        self._themes_by_output[output_id] = theme_name
        if output_id == self._main_output_id():
            self._current_theme = theme_name

        if self._current_display:
            payload = self._payload_for_display(self._current_display, output_id=output_id)
            if output_id == self._main_output_id():
                self._display.publish_live(payload, self._current_display,
                                           self._display.live_sched_uid,
                                           self._display.live_from_schedule)
            self._broadcast_to_ws(payload)
            logger.info(f"Output {output_id} theme double-clicked: {theme_name}, live re-rendered")
        else:
            logger.info(f"Output {output_id} theme double-clicked: {theme_name} (no live verse)")

    def _neighbour(self, which: str):
        """The queued prev/next verse, recomputed if the queue is stale.

        The queue is normally kept fresh by the live_data hook, but prev/next
        must not depend on that having happened: a schedule verse pushed by
        any path that skipped it would otherwise leave the operator pressing
        a button that silently does nothing. Recomputing is two indexed
        lookups and only happens on the fallback, so it costs nothing in the
        normal case.
        """
        attr = f"_{which}_verse_data"
        cached = getattr(self, attr, None)
        if cached is not None:
            return cached
        data = self._current_display
        if not isinstance(data, dict) or data.get("item_type") == "slide":
            return None
        book = data.get("book", "")
        chapter = str(data.get("chapter", "") or "")
        verse = str(data.get("verse_num", data.get("verse", "")) or "")
        version = data.get("version", "") or ""
        if not (book and chapter and verse and version):
            return None
        try:
            self._update_verse_neighbors(version, book, int(chapter), int(verse))
        except (TypeError, ValueError):
            return None
        return getattr(self, attr, None)

    def _arm_schedule_ring(self) -> None:
        """Light the schedule ring: Alt+arrows continue from the pushed item."""
        try:
            self._ring_state.arm_schedule()
        except (AttributeError, RuntimeError):
            pass  # bare-namespace test tabs have no ring state machine

    def _disarm_schedule_ring(self) -> None:
        """Verse stepping ends the schedule Alt+arrows context."""
        try:
            self._ring_state.disarm_schedule()
        except (AttributeError, RuntimeError):
            pass

    def _on_prev_verse(self):
        """Entry point for prev: the DISPLAY state routes it.

        Tabs are interfaces — a deck displayed while the operator stands
        here must still be stepped by the deck's own code and theme, so the
        shared state hands the step to whichever tab owns the content.
        """
        if self._display.dispatch_step(-1):
            return
        self._step_verse(-1)

    def _on_next_verse(self):
        """Entry point for next: see _on_prev_verse."""
        if self._display.dispatch_step(1):
            return
        self._step_verse(1)

    def _step_verse(self, delta: int):
        """This tab's own prev/next implementation (the registered stepper)."""
        if delta < 0:
            return self._on_prev_verse_own()
        return self._on_next_verse_own()

    def _on_prev_verse_own(self):
        """Previous VERSE (scripture) or previous SLIDE (deck).

        Deliberately never steps schedule items: a schedule item that was
        sent to live is a *starting point*, so prev/next walk within what
        is displayed (the neighbouring verses, or the deck's own slides).
        Schedule-item stepping is its own hotkey (Alt+Left / Alt+Right).
        """
        self._disarm_schedule_ring()
        cur = self._current_display
        if cur and cur.get("item_type") == "slide":
            idx = cur.get("slide_index", 0) - 1
            if idx >= 0:
                return self._apply_slide_display(
                    self._current_sched_data, cur["deck_title"], cur["slides"], idx
                )
            logger.info("prev: deck start — staying put")
            return  # slides exhausted: do nothing
        prev = self._neighbour("prev")
        if not prev:
            logger.info("prev_verse: no previous verse")
            return
        version = prev.get("version", "") or (self._current_display.get("version", "") if self._current_display else "")
        self._navigate_to_bible_verse(prev, version, skip_navigator=True)

    def _on_next_verse_own(self):
        """Next VERSE (scripture) or next SLIDE (deck). See _on_prev_verse_own."""
        self._disarm_schedule_ring()
        cur = self._current_display
        if cur and cur.get("item_type") == "slide":
            idx = cur.get("slide_index", 0) + 1
            if idx < len(cur.get("slides", [])):
                return self._apply_slide_display(
                    self._current_sched_data, cur["deck_title"], cur["slides"], idx
                )
            logger.info("next: deck end — staying put")
            return  # slides exhausted: do nothing
        nxt = self._neighbour("next")
        if not nxt:
            logger.info("next_verse: no next verse")
            return
        version = nxt.get("version", "") or (self._current_display.get("version", "") if self._current_display else "")
        self._navigate_to_bible_verse(nxt, version, skip_navigator=True)

    # ─── schedule-item stepping (Alt+Left / Alt+Right) ───────────────────

    def _on_prev_schedule_item(self):
        """Previous schedule item (its own hotkey — prev/next no longer
        bleeds into the schedule)."""
        self._step_schedule(-1)

    def _on_next_schedule_item(self):
        """Next schedule item (Alt+Right)."""
        self._step_schedule(1)

    def _on_live_data_changed(self, data) -> None:
        """Keep the prev/next queue bracketing the displayed scripture.

        Any source: navigator, browser, schedule, search, prev/next itself.
        A slide deck has no verse neighbours, so the queue is emptied and
        the deck's own arrows take over.
        """
        if not isinstance(data, dict) or data.get("item_type") == "slide":
            self._prev_verse_data = None
            self._next_verse_data = None
            return
        book = data.get("book", "")
        chapter = str(data.get("chapter", "") or "")
        verse = str(data.get("verse_num", data.get("verse", "")) or "")
        version = data.get("version", "") or ""
        if not (book and chapter and verse and version):
            self._prev_verse_data = None
            self._next_verse_data = None
            return
        try:
            self._update_verse_neighbors(version, book, int(chapter), int(verse))
        except (TypeError, ValueError):
            self._prev_verse_data = None
            self._next_verse_data = None

    def _set_verse_position(self, version: str, book: str, chapter, verse) -> None:
        """Point the prev/next queue at a verse the operator moved to.

        For navigation that deliberately does not touch live (a
        preview-only search click). Anything that DOES display goes
        through the live_data hook instead, so this is only for the
        paths the hook cannot see.
        """
        try:
            self._update_verse_neighbors(version, book, int(chapter), int(verse))
        except (TypeError, ValueError):
            self._prev_verse_data = None
            self._next_verse_data = None

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
        self._display.publish_live(payload, self._current_display, None, False)
        self._broadcast_to_ws(payload)

        if skip_navigator:
            # Highlight + scroll (ensure visible) + update navigator inputs, but no translation switch
            self.browser_panel._set_highlight(book, int(chapter), int(verse_num))
            self.browser_panel._scroll_to_highlight()
            self.browser_panel._update_navigator()
        else:
            self.browser_panel.navigate_to_reference(book, chapter, verse_num, translation=version)


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
        self._display.publish_live(payload, self._current_display,
                                   self._display.live_sched_uid,
                                   self._display.live_from_schedule)

        self._broadcast_to_ws(payload)

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
                "slide_format": data.get("format"),
                "slides": slides,
                "slide_index": 0,
            }

            saved_theme = self._current_theme
            self._current_theme = theme
            payload = self._build_payload(slide.get("text", ""), ref, "",
                                          slide_format=data.get("format"),
                                          content="slide",
                                          deck_id=data.get("deck_id"))
            self._current_theme = saved_theme
            self._display.publish_preview(payload, self._current_preview)
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
        self._display.publish_preview(payload, self._current_preview)
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
                data, data.get("name") or data.get("ref", ""), slides, 0,
                uncloak=True,
            )
            self._arm_schedule_ring()
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
        # Double-click push removes the cloak (one of its two exits).
        self._set_cloak(False)

        from core.theme_loader import get_theme
        saved_theme = self._current_theme
        self._current_theme = theme
        payload = self._build_payload(text, ref, version, book, chapter, verse)
        self._current_theme = saved_theme
        self._display.publish_live(payload, self._current_display,
                                   self._display.live_sched_uid,
                                   self._display.live_from_schedule)
        self._broadcast_to_ws(payload)
        self._arm_schedule_ring()
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

    def _broadcast_to_ws(self, payload: dict, data: dict | None = None,
                           preserve_theme: bool = False,
                           scope_all: bool = False):
        """
        Send a display payload to all connected outputs via WebSocket.
        Each output receives the payload with its own theme applied.
        For non-theme-specific payloads (like clear), sends as-is to all.

        Restore paths pass preserve_theme=True: the stored per-output theme
        snapshots win over this tab's theme map, so a push originating in
        the other tab is replayed exactly.
        """
        from core.database import log_live_payload
        # History: anything hitting live gets documented (display + clear),
        # independent of whether a WS loop is up for OBS.
        kind = None
        if data is not None and data.get("item_type") == "slide":
            kind = "slide"
        log_live_payload(payload, kind=kind)
        try:
            if payload.get("action") != "clear":
                if preserve_theme:
                    themed_outputs = self._display.matching_live_output_payloads()
                    for output_id in self._themes_by_output:
                        if output_id not in themed_outputs:
                            themed_outputs[output_id] = self._build_payload(
                                payload.get("text", ""),
                                payload.get("ref", ""),
                                payload.get("translation", ""),
                                payload.get("book", ""),
                                payload.get("chapter", ""),
                                payload.get("verse", ""),
                                output_id=output_id,
                                slide_format=payload.get("slide_format"),
                                content=payload.get("content", "verse"),
                                deck_id=payload.get("deck_id"),
                            )
                else:
                    themed_outputs = {
                        output_id: self._build_payload(
                            payload.get("text", ""),
                            payload.get("ref", ""),
                            payload.get("translation", ""),
                            payload.get("book", ""),
                            payload.get("chapter", ""),
                            payload.get("verse", ""),
                            output_id=output_id,
                            slide_format=payload.get("slide_format"),
                            # Contract: re-theming must preserve content
                            # identity — a slide rebroadcast stays a slide.
                            content=payload.get("content", "verse"),
                            deck_id=payload.get("deck_id"),
                        )
                        for output_id in self._themes_by_output
                    }
                    # Even a muted/behind-cloak push advances the model, so its
                    # per-output themes become the next restore's authority.
                    self._display.remember_live_output_payloads(themed_outputs)

            # OBS fan-out goes through the output router: this tab's own
            # set only (never the other tab's), plus cross-set cloaking in
            # prioritized mode. Gated pushes still advance only the model.
            from core.output_router import (
                broadcast_tab_payload, clear_tab_outputs)
            if self._obs_gated(payload):
                return  # cloaked: OBS holds its blank, model advances.
            if payload.get("action") == "clear":
                if scope_all:
                    from core.output_router import clear_all_outputs
                    clear_all_outputs()
                else:
                    clear_tab_outputs("SCRIPTURE")
            else:
                broadcast_tab_payload("SCRIPTURE", themed_outputs)
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
        from core.schedule_model import schedule_model
        last_path = get_setting("display.last_schedule", "")
        if not (last_path and os.path.exists(last_path)):
            return
        # The model is shared: skip if this exact file is already loaded
        # (re-loading would re-stamp uids and break step anchors).
        if schedule_model.current_file == last_path and schedule_model.get_items():
            return
        try:
            self.schedule_panel.load_schedule(last_path)
            logger.info(f"Restored last schedule: {last_path}")
        except Exception as e:
            logger.warning(f"Could not restore last schedule: {e}")
