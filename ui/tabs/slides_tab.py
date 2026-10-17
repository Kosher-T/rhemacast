"""
ui/tabs/slides_tab.py

SLIDES tab — songs / announcements / freeform workspace.

Layout (composition of modular panels, see ui/panels/README.md):
  LEFT    SchedulePanel      (same widget as SCRIPTURE tab)
  MIDDLE  LivePreviewPanel   (live + preview screens)
          + SlideGridPanel "PREVIEW" (preview deck's slides)
          + SlideGridPanel "LIVE"    (live deck's slides)
  RIGHT   DeckListPanel      (deck library + import/delete)

The tab owns NO panel internals — it only wires panel signals to panel
public methods plus its own display state (preview/live payloads, schedule
stepping, WebSocket broadcast).
"""

import asyncio
import logging
import os

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt

from ui.styles import SLATE_950
from ui.panels.schedule_panel import SchedulePanel
from ui.panels.live_preview_panel import LivePreviewPanel
from ui.panels.slide_grid_panel import SlideGridPanel
from ui.panels.deck_list_panel import DeckListPanel
from core.bible_service import get_display_name

logger = logging.getLogger(__name__)


class SlidesTab(QWidget):
    """SLIDES workspace tab."""

    def __init__(self, parent=None, schedule_model=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")

        # Display state (see core/display_state.py) — same contract
        # as the SCRIPTURE tab: shared singleton in prioritized mode,
        # this tab's own scoped state in simultaneous mode. Never plain
        # attrs here: constructing this lazy tab must not wipe the other
        # tab's screens.
        from core.display_state import display_state_for
        self._display = display_state_for("SLIDES")

        from core.database import get_setting
        from core.outputs import (DECK_OUTPUTS, SCRIPTURE_OUTPUTS,
                                  active_outputs, main_output_for_tab)
        # Slides use their OWN per-output theme namespace on the deck set,
        # independent of the scripture output themes — changing a theme in
        # one tab never affects the other. Defaults to the "slides" theme
        # (no title line). Only the operator's ACTIVE outputs appear here;
        # deleted outputs stop broadcasting entirely.
        self._themes_by_output: dict[str, str] = {}
        for oid in active_outputs("SLIDES"):
            self._themes_by_output[oid] = get_setting(f"display.slides_output_{oid}_theme", "slides")
        # The main output is this set's first active id — it follows the
        # Outputs page when the operator deletes/adds outputs.
        self._main_output = main_output_for_tab("SLIDES") or "4"
        self._current_theme = self._themes_by_output.get(self._main_output, "slides")
        # Verses shown here (schedule items, recall) render with the SCRIPTURE
        # output themes — theme follows content type, not the tab. Mapped
        # positionally by POOL position (4<-1, 5<-2, 6<-3) so a deck output
        # keeps its scripture theme even when the operator removes another.
        self._verse_themes_by_output: dict[str, str] = {}
        scripture_pool = {oid: theme_oid for oid, theme_oid
                          in zip(DECK_OUTPUTS, SCRIPTURE_OUTPUTS)}
        for deck_oid in self._themes_by_output:
            verse_oid = scripture_pool.get(deck_oid)
            if verse_oid:
                self._verse_themes_by_output[deck_oid] = get_setting(
                    f"display.output_{verse_oid}_theme", "default")

        # Slide section-hop navigation (Ctrl+Left/Right) transient state:
        # highlight position decoupled from the displayed slide while held.
        self._song_nav_active = False
        self._song_nav_index: int | None = None
        # Invisibility cloak over OBS output — SHARED live-screen state
        # (DisplayState.cloaked, replaces per-tab clear): while on, pushes
        # update the model/operator screens normally but nothing is
        # broadcast; only a double-click push or the cloak toggle removes
        # it. Persists across tabs by construction.
        # (initialized on the shared state; see _cloak property below)

        # ── Panels ──
        self.schedule_panel = SchedulePanel(model=schedule_model)
        self.live_preview = LivePreviewPanel()
        self.preview_grid = SlideGridPanel("PREVIEW")
        self.live_grid = SlideGridPanel("LIVE")
        self.live_grid.edit_menu_enabled = False  # live strip is inviolable
        self.deck_panel = DeckListPanel()

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        outer = QSplitter(Qt.Orientation.Horizontal)
        outer.setChildrenCollapsible(False)
        outer.addWidget(self._wrap(self.schedule_panel))
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.setContentsMargins(4, 4, 4, 4)
        middle_layout.setSpacing(6)

        # Vertical splitter: screens on top, strips below. Drag the handle
        # to enlarge the operator screens (same pattern as SCRIPTURE tab).
        vertical = QSplitter(Qt.Orientation.Vertical)
        vertical.setChildrenCollapsible(False)
        vertical.addWidget(self.live_preview)

        strips = QSplitter(Qt.Orientation.Horizontal)
        strips.setChildrenCollapsible(False)
        strips.addWidget(self.preview_grid)
        strips.addWidget(self.live_grid)
        vertical.addWidget(strips)
        middle_layout.addWidget(vertical)
        outer.addWidget(middle)

        outer.addWidget(self.deck_panel)
        outer.setStretchFactor(0, 0)
        outer.setStretchFactor(1, 1)
        outer.setStretchFactor(2, 0)

        root.addWidget(outer)

        # Persisted layouts (defaults on first run; saved sizes win after).
        from core.panel_layout import track_splitter
        self._outer_splitter = track_splitter("slides.outer", outer, [280, 900, 300])
        self._strips_splitter = track_splitter("slides.strips", strips, [500, 500])
        self._vertical_splitter = track_splitter("slides.vertical", vertical, [380, 620])

        self._connect_signals()
        self._restore_last_schedule()

    def showEvent(self, event):
        super().showEvent(event)
        # Screens first: a hidden WebEngine view keeps a current DOM
        # (background signals) but presents its last committed frame
        # until a fresh one commits — re-push shared state so the tab
        # never shows a stale frame on arrival.
        self.resync_screens()
        # Pick up font changes made in Settings while away
        self.preview_grid.refresh_strip_fonts()
        self.live_grid.refresh_strip_fonts()
        self.deck_panel.refresh_card_size()
        # Re-apply saved splitter layouts once real sizes exist
        from core.panel_layout import restore_splitter
        restore_splitter("slides.outer", self._outer_splitter)
        restore_splitter("slides.strips", self._strips_splitter)
        restore_splitter("slides.vertical", self._vertical_splitter)

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
    def _live_sched_uid(self):
        return self._display.live_sched_uid

    @_live_sched_uid.setter
    def _live_sched_uid(self, value):
        self._display.live_sched_uid = value

    @property
    def _cloak(self):
        return self._display.cloaked

    @_cloak.setter
    def _cloak(self, value):
        self._display.set_cloaked(value)

    @property
    def _live_from_schedule(self):
        return self._display.live_from_schedule

    @_live_from_schedule.setter
    def _live_from_schedule(self, value):
        self._display.live_from_schedule = bool(value)

    @staticmethod
    def _wrap(panel: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)
        panel.setProperty("class", "MainPanel")
        layout.addWidget(panel)
        return wrapper

    # ── Wiring ──────────────────────────────────────────────────────────────

    def _connect_signals(self):
        # Deck library → preview / schedule / live
        self.deck_panel.deck_selected.connect(self._on_deck_selected)
        self.deck_panel.add_to_schedule_requested.connect(self._on_deck_to_schedule)
        self.deck_panel.go_live_requested.connect(self._on_deck_go_live)
        self.deck_panel.deck_deleted.connect(self._on_deck_deleted)
        self.deck_panel.deck_text_updated.connect(self._on_deck_text_updated)
        self.deck_panel.deck_edit_requested.connect(self._open_lite_designer)
        self.deck_panel.output_theme_changed.connect(
            self._on_output_theme_changed)
        self.deck_panel.outputs_changed.connect(self._on_outputs_changed)
        self.deck_panel.output_theme_double_clicked.connect(
            self._on_output_theme_double_click)
        # Single-slide edits refresh the preview side only (live rule kept).
        # Only the preview strip offers slide editing — never the live one.
        self.preview_grid.slide_edit_requested.connect(self.deck_panel.open_slide_editor)
        self.deck_panel.deck_slide_updated.connect(self._on_deck_slide_updated)

        # Preview strip → preview screen; double-click → live
        self.preview_grid.slide_clicked.connect(self._on_preview_slide_clicked)
        self.preview_grid.slide_double_clicked.connect(self._on_preview_slide_double_clicked)

        # Live strip → live screen + broadcast
        self.live_grid.slide_clicked.connect(self._on_live_slide_clicked)
        self.live_grid.slide_double_clicked.connect(
            self._on_live_slide_double_clicked)

        # Schedule (same behavior as SCRIPTURE tab)
        self.schedule_panel.item_clicked.connect(self._on_schedule_click)
        self.schedule_panel.item_double_clicked.connect(self._on_schedule_double_click)
        self.schedule_panel.schedule_loaded.connect(self._on_schedule_loaded)

        # Live/preview screens
        self.live_preview.clear_recall.connect(self._on_clear_recall)
        self.live_preview.prev_verse.connect(self._on_prev)
        self.live_preview.next_verse.connect(self._on_next)
        self.live_preview.preview_double_clicked.connect(self._on_preview_double_click)

        # Screens render the SHARED display state — updates from any tab
        # appear here (and vice versa).
        self._display.live_changed.connect(self.live_preview.set_live_payload)
        self._display.preview_changed.connect(self.live_preview.set_preview_payload)
        self._display.cleared.connect(self.live_preview.clear_live)
        # Cloak button mirrors the SHARED cloak state (cloak_changed fires
        # synchronously, so the button can never drift — whichever tab
        # toggles, both tabs' buttons follow).
        self._display.cloak_changed.connect(self.live_preview.set_clear_active)
        self.live_preview.set_clear_active(self._display.cloaked)
        if self._display.live_payload:
            self.live_preview.set_live_payload(self._display.live_payload)
        if self._display.preview_payload:
            self.live_preview.set_preview_payload(self._display.preview_payload)

    # ── Payloads + broadcast ────────────────────────────────────────────────

    def _build_payload(self, text: str, ref: str, version: str = "",
                       output_id: str | None = None, slide_format: dict | None = None,
                       is_slide: bool = True, deck_id: int | None = None) -> dict:
        from core.theme_loader import resolve_theme
        output_id = output_id or self._main_output_id()
        if is_slide:
            theme_name = self._themes_by_output.get(output_id, "slides")
            # Slides fall back to the freeform "slides" theme — never the
            # scripture "default" (per-kind defaults, not app-wide).
            theme_name, theme_data = resolve_theme(theme_name, fallback="slides")
        else:
            theme_name = self._verse_themes_by_output.get(output_id, "default")
            theme_name, theme_data = resolve_theme(theme_name)
        payload = {
            "action": "display",
            "text": text,
            "ref": ref,
            "reference": ref,
            "translation": get_display_name(version) if version else "",
            "book": "",
            "chapter": "",
            "verse": "",
            "content": "slide" if is_slide else "verse",
            "theme": theme_name,
            "theme_data": theme_data,
        }
        if slide_format is not None:
            payload["slide_format"] = slide_format
        if deck_id is not None:
            payload["deck_id"] = deck_id
        return payload

    def _payload_for_display(self, data: dict, output_id: str | None = None) -> dict:
        output_id = output_id or self._main_output_id()
        if data.get("item_type") == "slide":
            return self._build_payload(data.get("text", ""),
                                       self._slide_display_ref(data, output_id),
                                       "", output_id,
                                       slide_format=data.get("slide_format"),
                                       deck_id=data.get("deck_id"))
        # Verse display dicts carry a prebuilt ref — or book/chapter parts
        # (SCRIPTURE-tab shape); never emit a blank ref when parts exist.
        ref = data.get("ref", "")
        if not ref and data.get("book"):
            ref = (f"[{get_display_name(data.get('version', ''))}] "
                   f"{data.get('book', '')} {data.get('chapter', '')}:{data.get('verse_num', '')}")
        return self._build_payload(
            data.get("text", ""), ref, data.get("version", ""), output_id,
            is_slide=False,
        )

    def _main_output_id(self) -> str:
        """This set's main output, tolerating test harnesses that build the
        tab without __init__ (Qt raises on any attribute then)."""
        try:
            return self._main_output or "4"
        except (AttributeError, RuntimeError):
            return "4"

    def _on_outputs_changed(self, output_ids: list):
        """Outputs page add/remove: adopt the new active set.

        Added outputs pick up their stored theme; removed ones stop
        broadcasting and stop being restored. When the main output itself
        was removed, the next surviving output becomes main.
        """
        from core.database import get_setting
        from core.outputs import active_outputs, main_output_for_tab
        active = list(output_ids or active_outputs("SLIDES"))
        themes: dict[str, str] = {}
        verse_themes: dict[str, str] = {}
        from core.outputs import DECK_OUTPUTS, SCRIPTURE_OUTPUTS
        scripture_pool = dict(zip(DECK_OUTPUTS, SCRIPTURE_OUTPUTS))
        for oid in active:
            themes[oid] = self._themes_by_output.get(oid) or get_setting(
                f"display.slides_output_{oid}_theme", "slides")
            verse_oid = scripture_pool.get(oid)
            if verse_oid:
                verse_themes[oid] = self._verse_themes_by_output.get(oid) or \
                    get_setting(f"display.output_{verse_oid}_theme", "default")
        self._themes_by_output = themes
        self._verse_themes_by_output = verse_themes
        self._main_output = main_output_for_tab("SLIDES") or (active[0] if active else "4")
        self._current_theme = themes.get(self._main_output, "slides")
        # The operator screens follow the main output's theme immediately.
        if self._current_preview is not None:
            self._display.publish_preview(
                self._payload_for_display(self._current_preview),
                self._current_preview)
        logger.info(f"Deck outputs now: {active} (main {self._main_output})")

    def _on_output_theme_changed(self, output_id: str, theme_name: str):
        """Single-click theme (Outputs page): update that output's theme +
        re-render preview. The main output is this set's first active id."""
        self._themes_by_output[output_id] = theme_name
        if output_id == self._main_output_id():
            self._current_theme = theme_name
        if output_id == self._main_output and self._current_preview is not None:
            data = self._current_preview
            payload = self._payload_for_display(data, output_id=self._main_output)
            self._display.publish_preview(payload, data)
        logger.info(f"Output {output_id} theme changed to: {theme_name}")

    def _on_output_theme_double_click(self, output_id: str, theme_name: str):
        """Double-click theme: update that output's theme + re-render live
        + broadcast."""
        self._themes_by_output[output_id] = theme_name
        if output_id == self._main_output_id():
            self._current_theme = theme_name
        if self._current_display is not None:
            payload = self._payload_for_display(
                self._current_display, output_id=output_id)
            if output_id == self._main_output_id():
                self._display.publish_live(
                    payload, self._current_display,
                    self._display.live_sched_uid,
                    self._display.live_from_schedule)
            self._broadcast_to_ws(payload)
            logger.info(f"Output {output_id} theme double-clicked: {theme_name}")
        else:
            logger.info(f"Output {output_id} theme double-clicked: {theme_name} (nothing live)")

    def _obs_gated(self, payload: dict) -> bool:
        """True when this payload must not reach OBS: cloaked covers
        everything except the blank itself."""
        return bool(self._cloak) and payload.get("action") != "clear"

    def _broadcast_to_ws(self, payload: dict, data: dict | None = None,
                           preserve_theme: bool = False) -> bool:
        from core.database import log_live_payload
        is_slide = data is not None and data.get("item_type") == "slide"
        # History: anything hitting live gets documented (display + clear),
        # independent of whether a WS loop is up for OBS. Slides log their
        # stored ref (identity) even when the theme hides it on screen.
        log_live_payload(payload, kind=("slide" if is_slide else "verse"),
                         ref=(data.get("ref") if is_slide else None))
        if payload.get("action") != "clear":
            is_slide = data is not None and data.get("item_type") == "slide"
            deck_id = (
                data.get("deck_id")
                if is_slide and isinstance(data, dict)
                else payload.get("deck_id")
            )
            if preserve_theme:
                themed_outputs = self._display.matching_live_output_payloads()
                for output_id in self._themes_by_output:
                    if output_id not in themed_outputs:
                        ref = (self._slide_display_ref(data, output_id) if is_slide
                               else payload.get("ref", ""))
                        themed_outputs[output_id] = self._build_payload(
                            payload.get("text", ""), ref,
                            payload.get("translation", ""), output_id=output_id,
                            slide_format=(data.get("slide_format") if is_slide else None),
                            is_slide=is_slide,
                            deck_id=deck_id,
                        )
            else:
                themed_outputs = {}
                for output_id in self._themes_by_output:
                    # Slide title visibility is per-output (each output has its
                    # own slides theme); verses pass their ref through as-is.
                    # Theme namespace follows content type, not the tab.
                    ref = (self._slide_display_ref(data, output_id) if is_slide
                           else payload.get("ref", ""))
                    themed_outputs[output_id] = self._build_payload(
                        payload.get("text", ""), ref,
                        payload.get("translation", ""), output_id=output_id,
                        slide_format=(data.get("slide_format") if is_slide else None),
                        is_slide=is_slide,
                        deck_id=deck_id,
                    )
                # Even a muted/behind-cloak push advances the model, so its
                # per-output themes become the next restore's authority.
                self._display.remember_live_output_payloads(themed_outputs)
        # OBS fan-out goes through the output router: this tab's own set
        # only (never the other tab's), plus cross-set cloaking in
        # prioritized mode. Gated pushes still advance only the model.
        try:
            from core.output_router import (
                broadcast_tab_payload, clear_tab_outputs)
            if self._obs_gated(payload):
                return False  # cloaked: OBS holds its blank, model advances.
            if payload.get("action") == "clear":
                clear_tab_outputs("SLIDES")
            else:
                broadcast_tab_payload("SLIDES", themed_outputs)
            return True
        except Exception as e:
            logger.error(f"Failed to initiate WebSocket broadcast: {e}")
            return False

    # ── Slide display core ──────────────────────────────────────────────────

    @staticmethod
    def _slide_ref(title: str, section: str | None) -> str:
        title = title or "(untitled)"
        return f"{title} · {section}" if section else title

    def _slide_display_ref(self, data: dict, output_id: str | None = None) -> str:
        output_id = output_id or self._main_output_id()
        """Reference line for a slide payload, honoring the theme's show_title.

        The stored display dict keeps the full "Title · Section" ref (logs,
        identity); the payload blanks it when the rendering theme opts out
        with {"slide": {"show_title": false}}.
        """
        from core.theme_loader import resolve_theme, slide_title_visible
        _, theme = resolve_theme(
            self._themes_by_output.get(output_id, "slides"), fallback="slides")
        if not slide_title_visible(theme):
            return ""
        if data.get("ref"):
            return data["ref"]
        return self._slide_ref(data.get("deck_title", ""), data.get("section"))

    @staticmethod
    def _same_deck(a: dict | None, b: dict | None) -> bool:
        """True if two deck dicts describe the same deck (stable across copies)."""
        if not a or not b:
            return False
        if a.get("id") is not None and b.get("id") is not None:
            return a.get("id") == b.get("id")
        if a.get("source_path") and b.get("source_path"):
            return a.get("source_path") == b.get("source_path")
        return a.get("slides") is not None and a.get("slides") is b.get("slides")

    def _sync_grid(self, grid, deck: dict, index: int, title: str, force: bool = False):
        """Show index on a strip WITHOUT rebuilding when the deck is unchanged.

        Rebuilding on every step reset the scrollbar to the top and dropped
        transient view state — selection-only updates keep scroll position.
        Pass force=True when the deck object is fresh (edited / re-sent to
        live): same id, new slides — the fast path would keep stale cards.
        """
        if not force and self._same_deck(grid.deck, deck):
            grid.set_selected_index(index)
        else:
            grid.set_deck(deck, select_index=index)
            grid.set_title(title)

    def _set_cloak(self, on: bool):
        """Single funnel for cloak transitions (toggle or double-click
        push). State lives on the shared DisplayState; the button syncs
        via the cloak_changed subscription. Muting rides along: while
        muted, publishes advance the model with zero screen updates
        (no flash possible)."""
        self._display.set_cloaked(on)

    def _show_slide(self, deck: dict, index: int, live: bool,
                    sched_data: dict | None = None, force_grid: bool = False,
                    uncloak: bool = False):
        """Show one slide on preview or live (+broadcast when live)."""
        slides = deck.get("slides", []) if deck else []
        if not slides:
            return
        index = max(0, min(index, len(slides) - 1))
        title = deck.get("title") or "(untitled)"
        slide = slides[index]
        ref = self._slide_ref(title, slide.get("section"))
        data = {
            "item_type": "slide",
            "text": slide.get("text", ""),
            "ref": ref,
            "version": "",
            "deck_id": deck.get("id"),
            "deck_title": title,
            "slide_format": deck.get("format") or None,
            "slides": slides,
            "slide_index": index,
        }
        payload = self._build_payload(data["text"],
                                       self._slide_display_ref(data), "",
                                       slide_format=data["slide_format"],
                                       deck_id=data.get("deck_id"))
        if live:
            # A fresh live send (click, schedule, recall…) cancels any
            # in-progress Ctrl-navigation; nav steps re-arm after calling.
            self._song_nav_active = False
            self._song_nav_index = None
            self._current_display = data
            self._live_sched_uid = (
                sched_data.get("_sched_uid") if isinstance(sched_data, dict) else None
            )
            self._live_from_schedule = sched_data is not None
            if uncloak:
                self._set_cloak(False)
            self._display.publish_live(payload, data,
                                       self._live_sched_uid, self._live_from_schedule)
            self._sync_grid(self.live_grid, deck, index, f"LIVE · {title}", force=force_grid)
            self._broadcast_to_ws(payload, data)
            logger.info(f"Slide live: {ref} ({index + 1}/{len(slides)})")
        else:
            self._current_preview = data
            self._display.publish_preview(payload, data)
            self._sync_grid(self.preview_grid, deck, index, f"PREVIEW · {title}", force=force_grid)
            logger.info(f"Slide preview: {ref}")

    def _show_verse(self, ref: str, text: str, version: str, live: bool,
                    sched_data: dict | None = None, uncloak: bool = False):
        """Show a schedule verse item on preview or live (scripture theme)."""
        data = {"item_type": "verse", "text": text, "ref": ref, "version": version}
        payload = self._build_payload(text, ref, version, is_slide=False)
        if live:
            self._song_nav_active = False
            self._song_nav_index = None
            self._current_display = data
            self._live_sched_uid = (
                sched_data.get("_sched_uid") if isinstance(sched_data, dict) else None
            )
            self._live_from_schedule = sched_data is not None
            if uncloak:
                self._set_cloak(False)
            self._display.publish_live(payload, data,
                                       self._live_sched_uid, self._live_from_schedule)
            self._broadcast_to_ws(payload)
            logger.info(f"Verse live: {ref}")
        else:
            self._current_preview = data
            self._display.publish_preview(payload, data)
            logger.info(f"Verse preview: {ref}")

    # ── Deck library handlers ───────────────────────────────────────────────

    def _on_deck_selected(self, deck: dict):
        """Deck click → load its slides into the preview strip + preview slide 0."""
        # Library rows are summaries (no slides) — fetch the full deck.
        if deck.get("slides") is None and deck.get("id") is not None:
            from core.slide_service import get_deck
            deck = get_deck(deck["id"]) or deck
        if deck.get("slides"):
            self._show_slide(deck, 0, live=False)

    def _on_deck_to_schedule(self, deck: dict):
        if deck.get("slides") is None and deck.get("id") is not None:
            from core.slide_service import get_deck
            deck = get_deck(deck["id"]) or deck
        item_data = {
            "item_type": "slide",
            "ref": deck.get("title") or "(untitled)",
            "name": deck.get("title") or "(untitled)",
            "deck_id": deck.get("id"),
            "slides": deck.get("slides", []),
            "format": deck.get("format"),
            "theme": self._current_theme,
        }
        self.schedule_panel.add_item(item_data)
        logger.info(f"Deck added to schedule: {item_data['ref']}")

    def _open_lite_designer(self, deck_id: int):
        """Deck menu → Edit…: the Lite Designer freeform editor."""
        from ui.widgets.lite_designer.lite_designer import LiteDesigner
        live = (self._current_display or {}).get("deck_id") == deck_id
        editor = LiteDesigner(parent=self.window(), deck_id=deck_id,
                              theme_name=self._current_theme,
                              default_tab="freeform", freeform_enabled=True,
                              live=live)
        editor.deck_saved.connect(self._on_lite_designer_saved)
        editor.edit_full_requested.connect(self._open_theme_designer_tab)
        editor.show()

    def _on_lite_designer_saved(self, deck_id: int, index: int = 0):
        # Titles may have changed → refresh the library, then preview side.
        self.deck_panel.refresh(keep_selection=True)
        # Preview ALWAYS follows the designer's highlighted card — not the
        # tab's stale preview position.
        from core.slide_service import get_deck
        deck = get_deck(deck_id)
        if not deck or not deck.get("slides"):
            return
        index = max(0, min(index, len(deck["slides"]) - 1))
        self.preview_grid.set_deck(deck, select_index=index)
        self.preview_grid.set_title(f"PREVIEW · {deck.get('title') or '(untitled)'}")
        self._show_slide(deck, index, live=False)

    def _open_theme_designer_tab(self, theme_name: str):
        window = self.window()
        if window is not None and hasattr(window, "_open_full_designer"):
            window._open_full_designer(theme_name)

    def _on_deck_go_live(self, deck_id: int):
        from core.slide_service import get_deck
        deck = get_deck(deck_id)
        if deck and deck.get("slides"):
            self._show_slide(deck, 0, live=True, force_grid=True)

    def _on_deck_deleted(self, deck_id: int):
        for grid, attr in ((self.preview_grid, "_current_preview"),
                           (self.live_grid, "_current_display")):
            state = getattr(self, attr)
            if state and state.get("item_type") == "slide" and state.get("deck_id") == deck_id:
                grid.clear()
                grid.set_title("PREVIEW" if grid is self.preview_grid else "LIVE")
                setattr(self, attr, None)
        if self._current_display is None:
            self._is_cleared = True

    def _on_deck_text_updated(self, deck_id: int):
        """A deck was edited as text: refresh PREVIEW only.

        Preview strip + preview screen re-show the same index from the fresh
        deck (clamped if slides were removed). Live is deliberately untouched —
        it keeps the old deck state until the operator double-clicks a
        preview slide, which is the only thing that ever sends to live.
        """
        from core.slide_service import get_deck
        deck = get_deck(deck_id)
        if not deck or not deck.get("slides"):
            return
        state = self._current_preview
        if not (state and state.get("item_type") == "slide"
                and state.get("deck_id") == deck_id):
            return
        idx = min(state.get("slide_index", 0), len(deck["slides"]) - 1)
        # Forced rebuild: _sync_grid's same-deck fast path only moves
        # selection, so edited card text would never refresh otherwise.
        self.preview_grid.set_deck(deck, select_index=idx)
        self.preview_grid.set_title(f"PREVIEW · {deck.get('title') or '(untitled)'}")
        self._show_slide(deck, idx, live=False)

    def _on_deck_slide_updated(self, deck_id: int, index: int):
        """One slide edited: refresh that preview card (+screen) only.

        No rebuild, no scroll jump, no selection change. Live is deliberately
        untouched — it keeps the old deck until a preview double-click.
        """
        from core.slide_service import get_deck
        deck = get_deck(deck_id)
        if not deck or not deck.get("slides"):
            return
        if not (0 <= index < len(deck["slides"])):
            return
        fresh = deck["slides"]
        # Strip first: it shows this deck regardless of what the preview
        # SCREEN is showing (verse, another deck, nothing) — previously
        # the screen gate below skipped the strip too, sticking it stale.
        grid = self.preview_grid
        if grid.deck is not None and grid.deck.get("id") == deck_id:
            grid.deck["slides"] = fresh
            grid.deck["title"] = deck.get("title")
            grid.update_slide_card(index, fresh[index]["text"])
        state = self._current_preview
        if not (state and state.get("item_type") == "slide"
                and state.get("deck_id") == deck_id):
            return
        state["slides"] = fresh
        state["deck_title"] = deck.get("title") or "(untitled)"
        if state.get("slide_index", 0) == index:
            self._show_slide(
                {"id": deck_id, "title": deck.get("title") or "(untitled)",
                 "slides": fresh, "format": deck.get("format")},
                index, live=False,
            )

    # ── Strip handlers ──────────────────────────────────────────────────────

    def _on_preview_slide_clicked(self, index: int):
        deck = self.preview_grid.deck
        if deck:
            self._show_slide(deck, index, live=False)

    def _on_preview_slide_double_clicked(self, index: int):
        deck = self.preview_grid.deck
        if deck:
            # Forced: live may hold a stale copy of this deck (same id, old
            # slides) — without it the live screen updates but its strip keeps
            # the old cards.
            self._show_slide(deck, index, live=True, force_grid=True,
                             uncloak=True)

    def _on_live_slide_clicked(self, index: int):
        deck = self.live_grid.deck
        if deck:
            self._show_slide(deck, index, live=True)

    def _on_live_slide_double_clicked(self, index: int):
        deck = self.live_grid.deck
        if deck:
            # Double-click push removes the cloak (one of its two exits).
            self._show_slide(deck, index, live=True, uncloak=True)

    # ── Schedule handlers (mirror SCRIPTURE behavior) ───────────────────────

    def _on_schedule_click(self, data: dict):
        if data.get("item_type") == "slide":
            slides = data.get("slides", [])
            if slides:
                self._show_slide(
                    {"id": data.get("deck_id"), "title": data.get("name") or data.get("ref", ""),
                     "slides": slides, "format": data.get("format")},
                    0, live=False,
                )
            return
        self._show_verse(data.get("ref", ""), data.get("text", ""),
                         data.get("translation", ""), live=False)

    def _on_schedule_double_click(self, data: dict):
        if data.get("item_type") == "slide":
            slides = data.get("slides", [])
            if slides:
                self._show_slide(
                    {"id": data.get("deck_id"), "title": data.get("name") or data.get("ref", ""),
                     "slides": slides, "format": data.get("format")},
                    0, live=True, sched_data=data, uncloak=True,
                )
            return
        self._show_verse(data.get("ref", ""), data.get("text", ""),
                         data.get("translation", ""), live=True, sched_data=data,
                         uncloak=True)

    def _on_schedule_loaded(self, file_path: str):
        from core.database import set_setting
        set_setting("display.last_schedule", file_path)

    def _restore_last_schedule(self):
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
        except Exception as e:
            logger.warning(f"Could not restore last schedule: {e}")

    def refresh_display_names(self, old_display: str, new_display: str):
        """Re-render current screens after a translation rename.

        Stored "[Old] ref" strings are patched, then preview/live rebuild
        (resolving the new name) and live re-broadcasts.
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
            self._broadcast_to_ws(payload, self._current_display)

    # ── Screens ─────────────────────────────────────────────────────────────

    def resync_screens(self):
        """Cover-gated silent re-push of shared payloads into this tab's
        views (idempotent).

        Hidden WebEngine views receive every publish but present their
        last committed frame until a fresh one commits — without this,
        arriving on a tab flashes whatever it last presented. Covers
        hide that stale frame; the silent refresh replays no animation
        and touches no transition memory; reveal fires after 2
        presented frames carry the update (500ms timer as fallback).
        Cloak respected: cloaked re-blanks instead of re-pushing."""
        if self._display.cloaked:
            live = "clear"
        elif self._display.live_payload:
            live = self._display.live_payload
        else:
            live = None
        self.live_preview.refresh_views(live, self._display.preview_payload)
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self.live_preview.reveal_screens)

    def _on_preview_double_click(self):
        """Double-click preview screen → push preview to live."""
        if not self._current_preview:
            return
        data = self._current_preview
        if data.get("item_type") == "slide":
            self._show_slide(
                {"id": data.get("deck_id"), "title": data.get("deck_title", ""),
                 "slides": data.get("slides", []), "format": data.get("slide_format")},
                data.get("slide_index", 0), live=True, uncloak=True,
            )
        else:
            self._show_verse(data.get("ref", ""), data.get("text", ""),
                             data.get("version", ""), live=True, uncloak=True)

    def _on_clear_recall(self):
        if not self._cloak:
            # Cloak on: blank OBS + operator live views only. Model,
            # operator preview and strips stay exactly as they are —
            # everything keeps working underneath the cover. Uncloak
            # shows whatever is current THEN (never a stale recall),
            # so no recall memory is kept.
            self._set_cloak(True)
            # set_cloaked already emitted cleared (operator views blank);
            # OBS takes its blank here (originating tab broadcasts).
            self._broadcast_to_ws({"action": "clear"}, self._current_display)
            logger.info("Display cloaked")
        else:
            # Cloak off: show whatever is underneath NOW (it may have
            # advanced while covered — never stale recall).
            self._set_cloak(False)
            stored = self._display.matching_live_output_payload()
            if stored is not None and self._current_display:
                # Replaying beats rebuilding: the stored payload carries the
                # originating output theme, so a verse cloaked in SCRIPTURE
                # does not come back wearing this tab's slide/verse map.
                payload = stored
                self._display.publish_live(
                    payload, self._current_display,
                    self._display.live_sched_uid,
                    self._display.live_from_schedule)
                self._broadcast_to_ws(payload, self._current_display,
                                      preserve_theme=True)
            elif self._current_display:
                payload = self._payload_for_display(self._current_display)
                self._display.publish_live(
                    payload, self._current_display,
                    self._display.live_sched_uid,
                    self._display.live_from_schedule)
                self._broadcast_to_ws(payload, self._current_display)
            if self._current_display:
                logger.info("Display uncloaked")

    # ── Prev / Next ─────────────────────────────────────────────────────────

    def _on_prev(self):
        self._step_live(-1)

    def _on_next(self):
        self._step_live(1)

    def _step_live(self, delta: int):
        """Step within the displayed deck only.

        Never bleeds into the schedule: Alt+Left / Alt+Right own schedule
        stepping, so an exhausted deck stays put instead of jumping to the
        neighbouring item.
        """
        cur = self._current_display
        if cur and cur.get("item_type") == "slide":
            idx = cur.get("slide_index", 0) + delta
            if 0 <= idx < len(cur.get("slides", [])):
                return self._show_slide(
                    {"id": cur.get("deck_id"), "title": cur.get("deck_title", ""),
                     "slides": cur["slides"], "format": cur.get("slide_format")},
                    idx, live=True,
                    sched_data={"_sched_uid": self._live_sched_uid}
                    if self._live_from_schedule else None,
                )
            logger.info("deck boundary — staying on this slide")
            return
        logger.info("prev/next: no deck on live to step through")

    def _step_schedule(self, delta: int):
        items = self.schedule_panel.get_schedule()
        row = next((i for i, d in enumerate(items)
                    if d.get("_sched_uid") == self._live_sched_uid), None)
        if row is None:
            return
        target = row + delta
        while 0 <= target < len(items):
            d = items[target]
            if d.get("item_type") == "slide":
                slides = d.get("slides", [])
                if slides:
                    idx = 0 if delta > 0 else len(slides) - 1
                    return self._show_slide(
                        {"id": d.get("deck_id"), "title": d.get("name") or d.get("ref", ""),
                         "slides": slides, "format": d.get("format")},
                        idx, live=True, sched_data=d,
                    )
                target += delta
                continue
            return self._show_verse(d.get("ref", ""), d.get("text", ""),
                                    d.get("translation", ""), live=True, sched_data=d)

    # ── Slide section-hop navigation (Ctrl+Left/Right) ────────────────────

    @staticmethod
    def _nav_mode() -> str:
        """Display behavior while section-hopping: instant / deferred / blank."""
        from core.database import get_setting
        return get_setting("slides.nav_mode", "deferred")

    def song_nav_step(self, delta: int):
        """Jump the live-strip highlight to the first slide of the prev/next section.

        Only the highlight moves here (except instant mode, which also sends).
        The display decision happens on Ctrl release in _end_song_nav — so a
        bare Ctrl press/release, without the full combo, does nothing.
        No-ops unless live is showing a slide deck.
        """
        from core.slide_service import section_run_starts
        cur = self._current_display
        if not (cur and cur.get("item_type") == "slide"
                and cur.get("slides")):
            logger.info("Slide nav ignored: live is not showing a slide deck")
            return
        slides = cur["slides"]
        base = cur.get("slide_index", 0)
        runs = section_run_starts(slides)
        if self._song_nav_active and self._song_nav_index is not None:
            base = max(0, min(self._song_nav_index, len(slides) - 1))
        if delta > 0:
            targets = [r for r in runs if r > base]
        else:
            targets = [r for r in runs if r < base]
        if not targets:
            return
        target = targets[0] if delta > 0 else targets[-1]
        mode = self._nav_mode()
        if not self._song_nav_active:
            self._song_nav_active = True
            if mode == "blank":
                # Soft blank: wire + own live screen only. Shared live_data
                # stays intact so release can re-send (publish_clear would
                # wipe it — stranding the screen blank — and clobber the
                # Esc-recall memory as a side effect).
                self.live_preview.clear_live()
                self._broadcast_to_ws({"action": "clear"}, cur)
        self._song_nav_index = target
        if mode == "instant":
            deck = {"id": cur.get("deck_id"), "title": cur.get("deck_title", ""),
                    "slides": slides}
            anchor = ({"_sched_uid": self._live_sched_uid}
                      if self._live_from_schedule else None)
            self._show_slide(deck, target, live=True, sched_data=anchor)
            self._song_nav_active = True
            self._song_nav_index = target
        else:
            # Highlight only — display stays until Ctrl is released.
            self.live_grid.set_selected_index(target)

    def _end_song_nav(self):
        """Ctrl released (or app deactivated): finish section-hop navigation."""
        if not self._song_nav_active:
            return
        mode = self._nav_mode()
        self._song_nav_active = False
        idx = self._song_nav_index
        self._song_nav_index = None
        if mode == "instant" or idx is None:
            return
        cur = self._current_display
        if not (cur and cur.get("item_type") == "slide" and cur.get("slides")):
            return
        if not (0 <= idx < len(cur["slides"])):
            return
        if mode == "deferred" and idx == cur.get("slide_index"):
            return  # released without moving — already showing
        # Blank mode always re-sends: the screen is blank even if the index
        # happens to match the pre-navigation slide.
        deck = {"id": cur.get("deck_id"), "title": cur.get("deck_title", ""),
                "slides": cur["slides"]}
        anchor = ({"_sched_uid": self._live_sched_uid}
                  if self._live_from_schedule else None)
        self._show_slide(deck, idx, live=True, sched_data=anchor)
