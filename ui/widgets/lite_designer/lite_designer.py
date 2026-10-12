"""
ui/widgets/lite_designer/lite_designer.py

The one Lite Designer popup, under a shared title bar (Reset / Save / x),
built on the ThemeQuickEditor shell language.

Entry rules:
  - Deck context menu (later: schedule items) -> the freeform editor.
  - Theme context menu (Quick Edit) -> the theme quick editor.

Which of the two shows is decided by how the popup was OPENED, and there
is no switch between them. There used to be a [ Freeform | Theme ] bar,
but each entry point could only ever use one of the two — the theme
Quick Edit has no deck, so freeform was disabled there, and a deck edit
has no business presenting a theme editor — so the bar could only restate
where you already were.

Freeform page: FormatRibbon + slide cards (single shared live editor) +
  live DisplayView preview. Save is STRICTLY preview (same contract as
  Edit-as-Text): preview strip refreshes, live untouched.
Theme page: today's quick-editor look verbatim (properties + preview).
"""

import copy
import logging

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QPushButton, QFrame, QTextEdit, QLineEdit,
                             QScrollArea, QMessageBox, QStackedWidget,
                             QSizePolicy, QApplication)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QSizeF, QEvent
from PyQt6.QtGui import QTextCursor, QKeySequence, QTextOption
import time as _time

from ui.widgets.theme_properties_panel import ThemePropertiesPanel
from ui.widgets.theme_preview import ThemePreview
from ui.widgets.display_view import DisplayView
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.widgets.lite_designer.format_ribbon import FormatRibbon
from ui.widgets.lite_designer.slide_cards import (
    SlideCard, display_text_px, move_to_word_end_right, word_ahead_stop,
    select_word_at, select_block, smart_delete_extend, TripleTracker)
from ui.widgets.lite_designer.rich_txt import (
    txt_to_doc, doc_to_txt, apply_spacing_to_doc, normalize_formatting)
from ui.styles import BLUE_500
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, TEXT_FAINT,
    ACCENT, ACCENT_HOVER, ACCENT_SOFT, ACCENT_BORDER, SELECTION_BG,
    TEXT_SELECTION,
)
import core.theme_loader
from core.slide_parser import (deck_to_txt, parse_slide_txt,
                                slide_owns_marker)

logger = logging.getLogger(__name__)

_POPUP_STYLE = (
    "QWidget {"
    "  background: rgba(20, 20, 23, 0.97);"
    "  border: 1px solid rgba(255, 255, 255, 0.08);"
    "  border-radius: 16px;"
    "  color: " + TEXT_PRIMARY + ";"
    "  font-family: 'Nunito', sans-serif;"
    "  font-size: 11px;"
    "}"
)
_TITLE_BAR_STYLE = ("QFrame { background: transparent;"
                    "  border-bottom: 1px solid rgba(255,255,255,0.06); }")
_TITLE_LABEL_STYLE = ("background: transparent; border: none; color: " + TEXT_PRIMARY + ";"
                      "font-size: 12px; font-weight: 700;")
_BADGE_STYLE = ("background: " + ACCENT_SOFT + "; color: " + ACCENT + ";"
                "border: 1px solid " + ACCENT_BORDER + "; border-radius: 4px;"
                "padding: 1px 8px; font-size: 10px; font-weight: 700;")
_LIVE_BADGE_STYLE = ("background: rgba(239, 68, 68, 0.15); color: #f87171;"
                     "border: 1px solid rgba(239,68,68,0.4); border-radius: 4px;"
                     "padding: 1px 8px; font-size: 10px; font-weight: 700;")
_ICON_STYLE = ("background: transparent; border: none; color: " + ACCENT + ";"
               "font-size: 14px;")
_BTN_GHOST = ("QPushButton { background: transparent; color: " + TEXT_MUTED + ";"
              "  border: 1px solid rgba(255,255,255,0.08); border-radius: 4px;"
              "  padding: 4px 12px; font-size: 10px; font-weight: 600; }"
              "QPushButton:hover { background: rgba(255,255,255,0.06);"
              "  color: " + TEXT_PRIMARY + "; }")
_BTN_PRIMARY = ("QPushButton { background: " + BLUE_500 + "; color: #ffffff;"
                "  border: none; border-radius: 4px; padding: 4px 16px;"
                "  font-size: 10px; font-weight: 700; }"
                "QPushButton:hover { background: " + ACCENT_HOVER + "; }"
                "QPushButton:pressed { background: " + ACCENT + "; }")
_BTN_EXPAND = ("QPushButton { background: " + ACCENT_SOFT + "; color: " + ACCENT + ";"
               "  border: 1px solid " + ACCENT_BORDER + "; border-radius: 4px;"
               "  padding: 4px 14px; font-size: 10px; font-weight: 700; }"
               "QPushButton:hover { background: " + SELECTION_BG + "; }")
_BTN_CLOSE = ("QPushButton { background: transparent; color: " + TEXT_FAINT + ";"
              "  border: none; border-radius: 4px; padding: 4px 8px;"
              "  font-size: 13px; font-weight: 700; }"
              "QPushButton:hover { background: rgba(239,68,68,0.15);"
              "  color: #ef4444; }")
_TITLE_FIELD_STYLE = ("QLineEdit { background: rgba(0,0,0,0.3); color: " + TEXT_PRIMARY + ";"
                      "  border: 1px solid rgba(255,255,255,0.1);"
                      "  border-radius: 6px; padding: 4px 10px; font-size: 13px;"
                      "  font-weight: 700; }")
def _editor_style(px: int) -> str:
    # Glyph size interpolated (fixed via display_text_px): a bare-QWidget
    # ancestor rule (the popup's 11px) would otherwise win over widget
    # fonts, so the size must live in this QTextEdit-selected rule.
    return ("QTextEdit { background: transparent; color: " + TEXT_PRIMARY + ";"
            "  border: none; padding: 0px;"
            "  font-family: 'Nunito', sans-serif;"
            f"  font-size: {px}px;"
            "  selection-background-color: " + TEXT_SELECTION + "; }"
            # Viewport is an unstyled QWidget child: shield it from
            # ancestor bare-QWidget borders (see slide_cards).
            "QTextEdit QWidget { background: transparent; border: none; }")
_STATUS_STYLE = ("background: transparent; border: none; color: " + TEXT_FAINT + ";"
                 "font-size: 10px;")
# Breathing room above a section-headed run (not the first): marks a new
# section group while cards inside a group stay joined edge-to-edge.
_SECTION_GAP = 8
_GAP_STYLE = "QWidget { background: transparent; border: none; }"
# Preview render pacing: keypresses within _BURST_WINDOW_MS of each other
# are one typing burst. Mid-burst renders run at most every
# _PREVIEW_THROTTLE_MS; a trailing render always follows the last
# keypress by the same delay; idle never renders.
_BURST_WINDOW_MS = 200
_PREVIEW_THROTTLE_MS = 300


def _burst_render_due(last_ms, deadline_ms, now_ms) -> bool:
    """Throttle gate (pure, unit-tested): render now only inside an
    ongoing burst past the throttle deadline. Burst starts and idle
    gaps merely arm the trailing timer."""
    if last_ms is None or now_ms - last_ms > _BURST_WINDOW_MS:
        return False
    return deadline_ms is not None and now_ms >= deadline_ms


# Card-list scrollbar: permanently reserved 6px lane (never pops in and
# shoves card buttons sideways mid-click), flat 2D thumb, no arrow keys.
_CARDS_SCROLL_STYLE = (
    "QScrollArea { border: none; background: transparent; }"
    "QScrollBar:vertical {"
    "  background: transparent; width: 6px; margin: 0px; border: none;"
    "}"
    "QScrollBar::handle:vertical {"
    "  background: rgba(161, 161, 170, 0.35); min-height: 20px;"
    "  border: none; border-radius: 3px;"
    "}"
    "QScrollBar::handle:vertical:hover {"
    "  background: rgba(161, 161, 170, 0.6);"
    "}"
    "QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {"
    "  height: 0px; border: none; background: none;"
    "}"
    "QScrollBar::sub-page:vertical, QScrollBar::add-page:vertical {"
    "  background: none; border: none;"
    "}"
)


class LiteDesigner(QWidget):
    """Single popup: the freeform deck editor, or the theme quick editor."""

    deck_saved = pyqtSignal(int, int)  # deck_id, active slide index
    theme_saved = pyqtSignal(str)
    edit_full_requested = pyqtSignal(str)

    def __init__(self, parent=None, deck_id=None, theme_name="slides",
                 default_tab="freeform", freeform_enabled=True, live=False):
        super().__init__(parent)
        self._deck_id = deck_id
        self._theme_name = theme_name
        self._live = live
        if deck_id is not None:
            # Deck editing must render the item's own (freeform per-output)
            # theme. A scripture kind here is always a caller bug — loud
            # warning, no silent auto-switch (explicit pass-through wins).
            try:
                kind = core.theme_loader.get_theme_kind(theme_name)
                if kind != core.theme_loader.FREEFORM:
                    logger.warning(
                        "LiteDesigner deck %s opened with %s-kind theme '%s' "
                        "(expected freeform) — preview follows the passed theme.",
                        deck_id, kind, theme_name)
            except Exception:
                pass
        self.setWindowFlags(
            Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setFixedSize(1280, 720)
        # Explicit title: untitled surfaces make the compositor fall back to
        # the process name ("debug.py"). If a ghost window ever appears, its
        # title tells us whether it is this popup's surface or something else.
        self.setWindowTitle("Lite Designer")
        self.setStyleSheet(_POPUP_STYLE)

        self._slides = []
        self._title = ""
        self._format = {}
        self._docs = {}
        self._active = 0
        self._hosted: int | None = None  # which card currently hosts _edit
        self._dirty = False
        self._splitting = False
        # Tiered text selection (Ctrl+A ladder, text only — cards never
        # paint a selection state):
        #   0 = none (normal caret) · 1 = active display box ·
        #   2 = active display + section chip · 3 = active section run ·
        #   4 = whole deck (title field never included)
        self._sel_tier = 0
        self._applying_scope_format = False
        self._cards = []

        self._original_theme = {}
        self._working_theme = {}
        self._theme_dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_title_bar())

        self._stack = QStackedWidget()
        self._freeform_page = self._build_freeform_page()
        self._theme_page = self._build_theme_page()
        self._stack.addWidget(self._freeform_page)
        self._stack.addWidget(self._theme_page)
        root.addWidget(self._stack, 1)

        # Which page this popup shows is decided by HOW IT WAS OPENED, not
        # by a switch the operator flips. A deck edit is freeform and only
        # freeform; a theme Quick Edit has no deck and only theme. There
        # was once a [ Freeform | Theme ] bar for this, but one of the two
        # options was always unavailable for a given entry point, so the
        # bar could only ever restate where you already were.
        if default_tab == "theme" or not freeform_enabled or deck_id is None:
            self._apply_mode("theme")
        else:
            self._apply_mode("freeform")

        if deck_id is not None:
            self._load_deck()
        self._load_theme()

    def _build_title_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(_TITLE_BAR_STYLE)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(14, 0, 10, 0)
        lay.setSpacing(8)
        icon = QLabel("PNG")
        icon.setStyleSheet(_ICON_STYLE)
        icon.setFixedWidth(20)
        lay.addWidget(icon)
        title = QLabel("Lite Designer")
        title.setStyleSheet(_TITLE_LABEL_STYLE)
        lay.addWidget(title)
        self._badge = QLabel("")
        self._badge.setStyleSheet(_BADGE_STYLE)
        lay.addWidget(self._badge)
        if self._live:
            live = QLabel("LIVE - preview only")
            live.setStyleSheet(_LIVE_BADGE_STYLE)
            lay.addWidget(live)
        lay.addStretch()
        self._status = QLabel("")
        self._status.setStyleSheet(_STATUS_STYLE)
        lay.addWidget(self._status)
        btn_full = QPushButton("Edit in Full Designer")
        btn_full.setStyleSheet(_BTN_EXPAND)
        btn_full.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_full.clicked.connect(
            lambda: self.edit_full_requested.emit(self._theme_name))
        lay.addWidget(btn_full)
        btn_reset = QPushButton("Reset")
        btn_reset.setStyleSheet(_BTN_GHOST)
        btn_reset.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_reset.clicked.connect(self._on_reset)
        lay.addWidget(btn_reset)
        btn_save = QPushButton("Save")
        btn_save.setToolTip("Apply to preview (stays open)")
        btn_save.setStyleSheet(_BTN_PRIMARY)
        btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_save.clicked.connect(self._on_save)
        lay.addWidget(btn_save)
        btn_close = QPushButton("X")
        btn_close.setStyleSheet(_BTN_CLOSE)
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self._on_close)
        lay.addWidget(btn_close)
        return bar

    def _apply_mode(self, which: str):
        """Show the freeform or theme page and badge it accordingly.

        Not a user-facing switch any more — see __init__ — just the one
        place that sets the page and the title it carries.
        """
        is_free = which == "freeform"
        self._stack.setCurrentIndex(0 if is_free else 1)
        self._badge.setText(
            (self._title or "(untitled)") if is_free else self._theme_name)

    def _build_freeform_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self._ribbon = FormatRibbon()
        self._ribbon.format_applied.connect(self._on_content_edited)
        self._ribbon.deck_format_changed.connect(self._on_deck_format_patch)
        lay.addWidget(self._ribbon)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        left = QFrame()
        left.setFixedWidth(440)
        left.setStyleSheet("QFrame { background: transparent;"
                           "  border-right: 1px solid rgba(255,255,255,0.06); }")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 8, 10, 8)
        ll.setSpacing(6)
        self._title_field = QLineEdit()
        self._title_field.setStyleSheet(_TITLE_FIELD_STYLE)
        self._title_field.setPlaceholderText("Deck title...")
        self._title_field.editingFinished.connect(self._on_title_finished)
        ll.addWidget(self._title_field)

        self._cards_scroll = QScrollArea()
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # Always on: the lane is reserved up front so the bar never pops
        # in on growth and shoves card buttons sideways under the cursor.
        self._cards_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._cards_scroll.setStyleSheet(_CARDS_SCROLL_STYLE)
        self._cards_host = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 4, 0)
        self._cards_layout.setSpacing(0)
        self._cards_layout.addStretch()
        self._cards_scroll.setWidget(self._cards_host)
        ll.addWidget(self._cards_scroll, 1)

        add_btn = QPushButton("+ Add slide")
        add_btn.setStyleSheet(_BTN_GHOST)
        add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        add_btn.clicked.connect(self._on_add_last)
        ll.addWidget(add_btn)
        body.addWidget(left)

        self._edit = QTextEdit()
        self._edit.setStyleSheet(_editor_style(display_text_px()))
        self._edit.setFrameShape(QFrame.Shape.NoFrame)
        self._edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._edit.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self._edit.document().setDocumentMargin(0)
        self._edit.setSizePolicy(QSizePolicy.Policy.Expanding,
                                 QSizePolicy.Policy.Fixed)
        self._edit.textChanged.connect(self._on_editor_text)
        self._edit.document().contentsChange.connect(self._on_contents_change)
        self._edit.installEventFilter(self)
        self._edit.viewport().installEventFilter(self)
        self._word_triple = TripleTracker()
        self._ribbon.set_editor(self._edit)

        right = QFrame()
        right.setStyleSheet("QFrame { background: transparent; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(4)
        lbl = QLabel("Preview")
        lbl.setStyleSheet("color: " + TEXT_MUTED + "; font-size: 9px; font-weight: 700;"
                          "letter-spacing: 1px; background: transparent;")
        rl.addWidget(lbl)
        frame = QFrame()
        frame.setStyleSheet("background: black;"
                            "border: 1px solid rgba(255,255,255,0.08);"
                            "border-radius: 8px;")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(0, 0, 0, 0)
        self._preview = DisplayView(live_mode=False)
        self._preview.setMinimumHeight(1)
        fl.addWidget(self._preview)
        self._ar = AspectRatioWidget(frame, aspect_ratio=16.0 / 9.0,
                                     min_width=160, max_width=800)
        rl.addWidget(self._ar, 1)
        body.addWidget(right, 1)

        lay.addLayout(body, 1)

        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(_PREVIEW_THROTTLE_MS)
        self._preview_timer.timeout.connect(self._refresh_preview)
        self._burst_last_ms = None
        self._burst_next_ms = None
        return page

    def _build_theme_page(self):
        page = QWidget()
        body = QHBoxLayout(page)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        left = QFrame()
        left.setFixedWidth(380)
        left.setStyleSheet("QFrame { background: transparent;"
                           "  border-right: 1px solid rgba(255,255,255,0.06); }")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)
        self._props = ThemePropertiesPanel()
        self._props.theme_changed.connect(self._on_theme_changed)
        ll.addWidget(self._props)
        body.addWidget(left)
        right = QFrame()
        right.setStyleSheet("QFrame { background: transparent; }")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(16, 12, 16, 12)
        rl.setSpacing(0)
        self._theme_preview = ThemePreview(verse_key="popup", label="Preview",
                                           min_width=160, max_width=800)
        rl.addWidget(self._theme_preview, 1)
        body.addWidget(right, 1)
        return page

    # ─── deck load / serialize ──────────────────────────────────────

    def _load_deck(self):
        from core.slide_service import get_deck
        deck = get_deck(self._deck_id) if self._deck_id is not None else None
        if not deck:
            return
        self._slides = [dict(s) for s in deck.get("slides", [])] or [
            {"section": None, "text": ""}]
        self._title = deck.get("title") or ""
        self._format = dict(deck.get("format") or {})
        self._docs = {}
        self._active = 0
        self._dirty = False
        self._title_field.setText(self._title)
        self._ribbon.set_deck_spacing(self._format.get("spacing"))
        self._rebuild_cards()
        self._sync_ribbon_theme()
        self._activate(0)

    def _sync_ribbon_theme(self):
        """Push the DISPLAY theme's baseline formatting into the ribbon.

        The theme styles the output (bold weight, shadow/outline, case,
        align); a card document only carries the deck's own run props.
        Without this the ribbon reads empty on load even though the deck
        displays bold + outlined. Reads from disk (never _working_theme),
        matching the preview's save-only contract.
        """
        try:
            _name, theme_data = core.theme_loader.resolve_theme(
                self._theme_name, fallback="slides")
            self._ribbon.set_theme_defaults(
                core.theme_loader.display_format_defaults(theme_data))
        except Exception:
            self._ribbon.set_theme_defaults({})

    def _base_spacing(self):
        return self._format.get("spacing")

    def _track_doc(self, doc):
        """Re-fit the editor whenever this document finishes a relayout."""
        try:
            doc.documentLayout().documentSizeChanged.connect(
                lambda _s: self._fit_editor_height())
        except (RuntimeError, TypeError):
            pass

    def _doc_for(self, index):
        doc = self._docs.get(index)
        if doc is None:
            doc = txt_to_doc(self._slides[index].get("text", ""))
            doc.setDocumentMargin(0)
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(doc, self._format["spacing"])
            # The layout tells US when it is done (fresh size, no forcing).
            self._track_doc(doc)
            # Tier collapse listens here too (see _on_contents_change): the
            # docs are cached, so one connection per created doc is enough.
            try:
                doc.contentsChange.connect(self._on_contents_change)
            except (RuntimeError, TypeError):
                pass
            self._docs[index] = doc
        return doc

    def _store_active(self):
        """Serialize live docs back into the working slide list.

        Stores EVERY cached doc, not just the active one: fan-out ops and
        paints touch inactive docs, and the txt model is the source of
        truth — anything unstored is invisible to save/copy/preview.
        (Small docs; the cost is negligible next to a single re-layout.)
        """
        for i, doc in self._docs.items():
            if 0 <= i < len(self._slides):
                self._slides[i]["text"] = doc_to_txt(
                    doc, base_spacing=self._base_spacing())

    # ─── cards ──────────────────────────────────────────────────────

    def _section_runs(self) -> list:
        """Runs delimited by ownership — same sticky rule as the strips.

        A run starts at slide 0 and at every slide that owns its marker;
        members (empty chips) join the run above. Text in a chip = new
        section, even when identical to the section above.
        """
        runs = []
        for i in range(len(self._slides)):
            if i == 0 or slide_owns_marker(self._slides, i):
                runs.append([self._slides[i].get("section"), [i]])
            else:
                runs[-1][1].append(i)
        return runs

    def _rebuild_cards(self):
        """Rebuild the card list from the slide model, wholesale.

        ONE code path for every structural change (add/delete/move/
        paste/section edit/load): release the live editor properly,
        resize the card pool, re-sequence one flat layout, re-sync
        every card, restore scroll and focus. No envelopes (they were
        invisible shells — transparent, zero margins — contributing
        nothing but cross-layout reparents at ~5ms a move), no diff
        bookkeeping: cards whose position is unchanged are never
        touched, so the model is the only source of truth and a
        rebuild cannot drift from it. Structural ops are infrequent
        (never per-keystroke). Paints frozen for the duration: one
        relayout+repaint at the end instead of one per mutation.
        """
        # Focus intent survives the rebuild (widget identity does not —
        # cards are re-homed, so restore by role afterwards).
        focus = QApplication.focusWidget()
        focus_token = None
        if focus is self._edit:
            focus_token = "editor"
        else:
            for i, card in enumerate(self._cards):
                if focus is not None and focus is card._chip:
                    focus_token = ("chip", i)
                    break
        scroll = None
        try:
            scroll = self._cards_scroll.verticalScrollBar().value()
        except RuntimeError:
            pass
        self._cards_host.setUpdatesEnabled(False)
        try:
            # Proper release (never a raw setParent rip): the hosting
            # card's flag resets with it, so re-hosting below cannot
            # no-op on a stale "already hosting" belief.
            for card in self._cards:
                if card._editor_hosted:
                    card.release_editor()
            self._hosted = None
            while len(self._cards) > len(self._slides):
                doomed = self._cards.pop()
                self._cards_layout.removeWidget(doomed)
                doomed.deleteLater()
            while len(self._cards) < len(self._slides):
                self._cards.append(self._new_card())
            # Drop gap spacers + the trailing stretch (recreated below);
            # cards stay parented until the sequencing walk moves them.
            for gap in self._cards_host.findChildren(QWidget, "SectionGap"):
                self._cards_layout.removeWidget(gap)
                gap.setParent(None)
                gap.deleteLater()
            # Desired order: cards with a gap above each headed non-first
            # run. Walk forward, moving only misplaced widgets — cards
            # already in position keep parent, polish and state.
            desired: list = []
            for q, (section, run) in enumerate(self._section_runs()):
                if q > 0 and section:
                    gap = QWidget()
                    gap.setObjectName("SectionGap")
                    gap.setFixedHeight(_SECTION_GAP)
                    gap.setStyleSheet(_GAP_STYLE)
                    gap.setProperty("run", q)
                    desired.append(gap)
                for i in run:
                    self._sync_card(self._cards[i], i)
                    desired.append(self._cards[i])
            for pos, widget in enumerate(desired):
                current = self._cards_layout.itemAt(pos)
                if current is not None and current.widget() is widget:
                    continue
                self._cards_layout.insertWidget(pos, widget)
            self._cards_layout.addStretch()
            self._refresh_card_states()
        finally:
            self._cards_host.setUpdatesEnabled(True)
        try:
            self._cards_layout.activate()
            if scroll is not None:
                bar = self._cards_scroll.verticalScrollBar()
                bar.setValue(min(scroll, bar.maximum()))
        except RuntimeError:
            pass
        if focus_token == "editor":
            try:
                self._edit.setFocus()
            except RuntimeError:
                pass
        elif isinstance(focus_token, tuple) \
                and 0 <= focus_token[1] < len(self._cards):
            try:
                self._cards[focus_token[1]]._chip.setFocus()
            except RuntimeError:
                pass

    def _new_card(self) -> SlideCard:
        card = SlideCard(0, "")
        card.activated.connect(self._activate)
        card.section_changed.connect(self._on_section_changed)
        card.delete_requested.connect(self._delete_slide)
        card.move_requested.connect(self._move_slide)
        card.add_after_requested.connect(
            lambda idx: self._add_slide(idx + 1))
        card.add_and_continue_requested.connect(
            lambda idx: self._add_slide_and_continue(idx + 1))
        # Tier keys (Ctrl+A/C/X/V, Esc, plain Delete) are intercepted in
        # the designer's event filter before the chip's own handlers.
        card._chip.setProperty("liteChip", True)
        card._chip.installEventFilter(self)
        card._chip.textChanged.connect(self._on_chip_text)
        return card

    def _on_chip_text(self):
        """Typing in a section chip collapses any tier selection."""
        if self._sel_tier:
            self._clear_tier()

    def _sync_card(self, card: SlideCard, i: int):
        """Refresh one reused card for slide i (no reconstruction)."""
        slide = self._slides[i]
        card.set_index(i)
        card.set_joined(i == 0, i == len(self._slides) - 1)
        # Edge slides cannot move past the deck ends: hide those buttons
        # (rather than disable) so the pill collapses. Indices never
        # change on a swap, so the move path needs no extra pass.
        card.set_move_up_visible(i > 0)
        card.set_move_down_visible(i < len(self._slides) - 1)
        card.set_section(slide.get("section")
                         if slide_owns_marker(self._slides, i) else "")
        if i != self._active:
            # Plain text display (redesigned card uses text fields, not HTML labels)
            card.set_content_text(slide.get("text", ""))

    def _refresh_card_states(self):
        for i, card in enumerate(self._cards):
            card.set_index(i)
            card.set_active(i == self._active)
            if i != self._active and i < len(self._slides):
                card.set_content_text(self._slides[i].get("text", ""))

    def _activate(self, index):
        if not (0 <= index < len(self._slides)):
            return
        # Pointing at a slide collapses any tier selection.
        self._clear_tier()
        self._burst_last_ms = None
        self._burst_next_ms = None
        doc = self._doc_for(index)
        if index == self._active and self._hosted == index \
                and self._edit.document() is doc:
            # Fully hosted — zero churn, not even this. But never rip
            # focus out of the section box: the user is editing the
            # section name, not the slide text.
            try:
                in_section = self._cards[index]._chip.hasFocus()
            except (IndexError, AttributeError):
                in_section = False
            if not in_section:
                self._edit.setFocus()
            return
        if index != self._active:
            # Switching slides stores the previous one. Same-card fallthrough
            # (first load / post-rebuild) never stores: the editor may hold
            # the SlideCard empty document, which must not overwrite.
            self._store_active()
        prev = self._active if 0 <= self._active < len(self._cards) else None
        self._active = index
        if prev is not None and prev != index and prev < len(self._cards):
            old = self._cards[prev]
            old.release_editor()
            if prev < len(self._slides):
                old.set_content_text(self._slides[prev].get("text", ""))
        card = self._cards[index]
        if self._edit.document() is not doc:
            self._edit.blockSignals(True)
            self._edit.setDocument(doc)
            self._edit.blockSignals(False)
        card.host_editor(self._edit)
        self._hosted = index
        self._fit_editor_height()
        self._refresh_card_states()
        self._ribbon.refresh_state()
        # Clicks render instantly (no debounce): the preview ALWAYS shows
        # the highlighted card. Any pending keystroke render is stale.
        self._preview_timer.stop()
        self._refresh_preview()

    # ─── structural ops ─────────────────────────────────────────────

    def _normalize_markers(self):
        """Repair the ownership invariant after reordering.

        A slide whose value differs from the effective slide above MUST own
        its marker — otherwise the serializer emits nothing and the value
        silently inherits (data loss on save). Deck-top valued slides own
        too (their chip is the only place the name appears). Never clears:
        explicit splits survive conservative moves.
        """
        for i, s in enumerate(self._slides):
            cur = (s.get("section") or None)
            if i == 0:
                if cur is not None and not s.get("marker"):
                    s["marker"] = True
                continue
            prev = (self._slides[i - 1].get("section") or None)
            if cur != prev and not s.get("marker"):
                s["marker"] = True

    def _renumber_docs(self, start, delta):
        new = {}
        for k, doc in self._docs.items():
            if delta > 0 and k >= start:
                new[k + 1] = doc
            elif delta < 0 and k > start:
                new[k - 1] = doc
            elif delta < 0 and k == start:
                continue
            else:
                new[k] = doc
        self._docs = new

    def _add_slide(self, index):
        self._store_active()
        self._clear_tier()
        index = max(0, min(index, len(self._slides)))
        # New slides join the run above. Deck top starts section-less
        # (never inherit the last slide via index wraparound).
        section = (self._slides[index - 1].get("section")
                   if index > 0 else None)
        self._slides.insert(index, {"section": section, "text": ""})
        self._renumber_docs(index, +1)
        self._normalize_markers()
        self._dirty = True
        self._rebuild_cards()
        self._activate(index)
        self._schedule_preview()

    def _add_slide_and_continue(self, index):
        """Ctrl+Enter flow: add like the button, then keep the user
        typing — new slide scrolled into view, focus in its editor."""
        if not (0 <= index <= len(self._slides)):
            return
        self._add_slide(index)
        self._edit.setFocus()
        QTimer.singleShot(0, self._settle_after_add)

    def _settle_after_add(self):
        """Deferred tail of add-and-continue: drain the fit/resize event
        cascade (textbox auto-fit needs laid-out widths first) so the
        scroll-into-view aims final geometry and the refocus sticks
        (a synchronous setFocus alone can be swallowed by deferred
        focus-clear events from the rebuild)."""
        try:
            if not self.isVisible():
                return
            app = QApplication.instance()
            for _ in range(3):
                self._cards_layout.activate()
                if app is not None:
                    app.processEvents()
            if 0 <= self._active < len(self._cards):
                self._cards_scroll.ensureWidgetVisible(
                    self._cards[self._active])
            self._edit.setFocus()
        except RuntimeError:
            pass  # closed before the deferred tail ran

    def _on_add_last(self):
        self._add_slide(len(self._slides))

    def _confirm(self, text):
        return QMessageBox.question(self, "Lite Designer", text) == \
            QMessageBox.StandardButton.Yes

    def _delete_slide(self, index):
        if len(self._slides) <= 1:
            self._slides[0]["text"] = ""
            self._docs.pop(0, None)
            self._rebuild_cards()
            self._activate(0)
            self._dirty = True
            self._schedule_preview()
            return
        if (self._slides[index].get("text", "").strip()
                and not self._confirm("Delete this slide?")):
            return
        self._clear_tier()
        self._store_active()
        doomed = self._slides[index]
        del self._slides[index]
        self._renumber_docs(index, -1)
        self._pass_header(doomed.get("section"), index)
        if self._active >= len(self._slides):
            self._active = len(self._slides) - 1
        elif self._active > index:
            self._active -= 1
        self._normalize_markers()
        self._dirty = True
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()

    def _pass_header(self, doomed_section, at_index: int):
        """A removed header passes its role on: the slide now sitting at
        `at_index` owns the section when it carries the same value (so a
        cut header never strands same-valued followers as members)."""
        doomed = (doomed_section or None)
        if doomed is None or not (0 <= at_index < len(self._slides)):
            return
        nxt = self._slides[at_index]
        if (nxt.get("section") or None) == doomed:
            nxt["marker"] = True

    def _move_slide(self, index, delta):
        j = index + delta
        if not (0 <= index < len(self._slides) and 0 <= j < len(self._slides)):
            return
        self._clear_tier()
        self._store_active()
        before = [run for _, run in self._section_runs()]
        self._slides[index], self._slides[j] = \
            self._slides[j], self._slides[index]
        di = self._docs.pop(index, None)
        dj = self._docs.pop(j, None)
        if di is not None:
            self._docs[j] = di
        if dj is not None:
            self._docs[index] = dj
        if self._active == index:
            self._active = j
        elif self._active == j:
            self._active = index
        self._normalize_markers()
        self._dirty = True
        if [run for _, run in self._section_runs()] == before:
            self._move_sync_pair(index, j)
            return
        self._rebuild_cards()
        self._activate(self._active)
        # No _schedule_preview: _activate already rendered instantly, and
        # the active slide's bytes are unchanged by a move either way.

    def _move_sync_pair(self, index, j):
        """Cheapest correct move: section runs identical, so envelopes,
        indices and edge buttons are untouched — swap the two cards'
        displayed values in place. No rebuild, no preview re-render
        (the active slide's bytes travel with it, output identical),
        editor keeps focus and undo.
        """
        prev_hosted = self._hosted
        keep_focus = self._edit.hasFocus()
        self._sync_card(self._cards[index], index)
        self._sync_card(self._cards[j], j)
        self._cards[index].set_active(index == self._active)
        self._cards[j].set_active(j == self._active)
        if self._active in (index, j) and prev_hosted != self._active:
            # The active content changed cards: the editor's document
            # object already traveled via the _docs swap, so just
            # re-home the widget (no setDocument churn).
            self._cards[prev_hosted].release_editor()
            self._cards[self._active].host_editor(self._edit)
            self._hosted = self._active
            self._fit_editor_height()
            if keep_focus:
                self._edit.setFocus()

    def _on_section_changed(self, index, section):
        if not (0 <= index < len(self._slides)):
            return
        text = (section or "").strip()
        slide = self._slides[index]
        old_runs = None
        if not text:
            # Clear → member of the nearest owning slide above (None when
            # nothing owns above: section-less).
            above = None
            for k in range(index - 1, -1, -1):
                if slide_owns_marker(self._slides, k):
                    above = self._slides[k].get("section") or None
                    break
            if (slide.get("marker") is False
                    and (slide.get("section") or None) == above):
                self._cards[index].set_section("")
                return  # already a member — no churn
            slide["marker"] = False
            slide["section"] = above
        else:
            if (slide.get("section") == text
                    and slide_owns_marker(self._slides, index)):
                self._cards[index].set_section(text)
                return  # header text unchanged — no churn
            # Text in a chip = new section, even when identical to above.
            old_runs = [run for _, run in self._section_runs()]
            slide["section"] = text
            slide["marker"] = True
        self._dirty = True
        if old_runs is not None \
                and [run for _, run in self._section_runs()] == old_runs:
            # Membership unchanged (pure rename inside one run): the chip
            # already shows the new text — regrouping would only churn.
            self._schedule_preview()
            return
        # Renames can merge/split runs → regroup envelopes, keep editing.
        active = self._active
        self._rebuild_cards()
        self._activate(active)
        self._schedule_preview()

    def _on_title_finished(self):
        text = self._title_field.text().strip()
        if text != self._title:
            self._title = text
            self._dirty = True
            self._clear_tier()
            if self._stack.currentIndex() == 0:
                self._badge.setText(self._title or "(untitled)")
            self._schedule_preview()

    # ─── editing events ─────────────────────────────────────────────

    def _on_content_edited(self):
        # Ribbon formats never collapse the tier: the operator may chain
        # Bold-then-Italic or click a spinbox repeatedly on one highlight.
        # Typing collapse lives in the keypress filter (_drop_ladder_for_typing)
        # and in _on_contents_change (real text changes only).
        self._dirty = True
        self._fit_editor_height()
        self._schedule_preview()

    def _on_deck_format_patch(self, patch):
        self._format.update(patch)
        self._ribbon.set_deck_spacing(self._format.get("spacing"))
        for doc in self._docs.values():
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(doc, self._format["spacing"])
        self._clear_tier()
        self._dirty = True
        self._schedule_preview()

    def eventFilter(self, obj, event):
        # Qt can deliver one last event as the editor is torn down, and
        # asking a deleted widget for its viewport raises. Skip it rather
        # than let a RuntimeWarning-turned-error escape at teardown.
        # getattr (not just RuntimeError): during interpreter teardown or
        # after a dropped Python reference, _edit itself may be gone while
        # Qt still routes viewport events here — throwing out of an event
        # filter poisons the loop for every test/widget after us.
        edit = getattr(self, "_edit", None)
        if edit is None:
            return False
        try:
            mine = obj is edit.viewport()
        except RuntimeError:
            return False
        if mine:
            if event.type() == QEvent.Type.MouseButtonPress:
                if self._sel_tier:
                    self._clear_tier()  # fresh click intent, drop the ladder
                if self._word_triple.register(
                        event.button(), event.pos()) == 3:
                    cursor = self._edit.cursorForPosition(event.pos())
                    select_block(cursor)
                    self._edit.setTextCursor(cursor)
                    return True
                return False
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._word_triple.register(event.button(), event.pos())
                if event.button() == Qt.MouseButton.LeftButton:
                    cursor = self._edit.cursorForPosition(event.pos())
                    if select_word_at(cursor):
                        self._edit.setTextCursor(cursor)
                        return True
                return False
        if obj is not None and bool(obj.property("liteChip")):
            return self._chip_event(obj, event)
        if obj is self._edit and event.type() == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                               Qt.Key.Key_Alt, Qt.Key.Key_Meta):
                # Pure modifier presses (the Ctrl in Ctrl+A/C/X/V, Shift
                # held for selections) carry no intent — never collapse.
                return False
            if event.matches(QKeySequence.StandardKey.SelectAll):
                self._advance_tier()
                return True
            if self._sel_tier and not event.matches(
                    QKeySequence.StandardKey.Copy) \
                    and not event.matches(QKeySequence.StandardKey.Cut) \
                    and not event.matches(QKeySequence.StandardKey.Paste) \
                    and event.key() not in (Qt.Key.Key_Delete,
                                            Qt.Key.Key_Backspace,
                                            Qt.Key.Key_Escape):
                # Any other key starts fresh: drop the ladder, then handle
                # natively. The focused box KEEPS its selection so typing
                # replaces the highlight (see _drop_ladder_for_typing).
                self._drop_ladder_for_typing()
            if event.key() == Qt.Key.Key_Right and (
                    event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                # Custom word-end hop onto punctuation clusters (Ctrl+Left
                # stays Qt default); Shift extends the selection.
                cursor = self._edit.textCursor()
                if move_to_word_end_right(
                        cursor,
                        keep_anchor=bool(event.modifiers()
                                         & Qt.KeyboardModifier.ShiftModifier)):
                    self._edit.setTextCursor(cursor)
                    return True
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                    and (event.modifiers()
                         & Qt.KeyboardModifier.ControlModifier) \
                    and not (event.modifiers()
                             & Qt.KeyboardModifier.ShiftModifier):
                # Ctrl+Enter: same as add-slide, then keep typing in the
                # new slide (scrolled into view, editor focused).
                self._add_slide_and_continue(self._active + 1)
                return True
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                    and not (event.modifiers()
                             & (Qt.KeyboardModifier.ShiftModifier
                                | Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.MetaModifier)):
                # Selection rules extend the range, then fall through so
                # default deletion removes it in one undo step.
                cursor = self._edit.textCursor()
                forward = event.key() == Qt.Key.Key_Delete
                if cursor.hasSelection():
                    done = smart_delete_extend(
                        self._edit.document(), cursor.selectionStart(),
                        cursor.selectionEnd(), forward)
                    if done is not None:
                        cursor.setPosition(done[0])
                        cursor.setPosition(
                            done[1], QTextCursor.MoveMode.KeepAnchor)
                        self._edit.setTextCursor(cursor)
                elif event.modifiers() & Qt.KeyboardModifier.ControlModifier \
                        and event.key() == Qt.Key.Key_Delete:
                    block = cursor.block()
                    stop = word_ahead_stop(
                        block.text(), cursor.position() - block.position())
                    if stop is not None:
                        cursor.setPosition(
                            block.position() + stop,
                            QTextCursor.MoveMode.KeepAnchor)
                        self._edit.setTextCursor(cursor)
                # else: Qt default (incl. Ctrl+Backspace, which already
                # mirrors Ctrl+Left stops)
            if event.matches(QKeySequence.StandardKey.Paste):
                if self._sel_tier:
                    self._paste_scope()
                    return True
                return self._handle_paste()
            if event.matches(QKeySequence.StandardKey.Cut):
                if self._sel_tier:
                    self._cut_scope()
                    return True
                return False
            if event.key() == Qt.Key.Key_C \
                    and (event.modifiers()
                         & Qt.KeyboardModifier.ControlModifier):
                if self._sel_tier:
                    self._copy_scope()
                    return True
                return False
            if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                    and not (event.modifiers()
                             & (Qt.KeyboardModifier.ShiftModifier
                                | Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.MetaModifier)):
                if self._sel_tier:
                    self._delete_scope()
                    return True
            if event.key() == Qt.Key.Key_Escape and self._sel_tier:
                self._clear_tier()
                return True
        return super().eventFilter(obj, event)

    def _chip_event(self, obj, event) -> bool:
        """Tier keys while focus sits in a section chip.

        Ctrl+A climbs the same ladder (a fully-selected chip counts as an
        invitation to tier 1); clipboard keys act on the tier scope when
        one is up, else fall through to the chip's native behavior.
        """
        from PyQt6.QtCore import QEvent as _QE
        if event.type() == _QE.Type.MouseButtonPress:
            if self._sel_tier:
                self._clear_tier()
            return False
        if event.type() != _QE.Type.KeyPress:
            return False
        if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift,
                           Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            # Pure modifier presses carry no intent — never collapse.
            return False
        if event.matches(QKeySequence.StandardKey.SelectAll):
            self._advance_tier()
            return True
        if event.matches(QKeySequence.StandardKey.Paste):
            if self._sel_tier:
                self._paste_scope()
                return True
            return False
        if event.matches(QKeySequence.StandardKey.Cut):
            if self._sel_tier:
                self._cut_scope()
                return True
            return False
        if event.key() == Qt.Key.Key_C \
                and (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            if self._sel_tier:
                self._copy_scope()
                return True
            return False
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                and not (event.modifiers()
                         & (Qt.KeyboardModifier.ShiftModifier
                            | Qt.KeyboardModifier.AltModifier
                            | Qt.KeyboardModifier.MetaModifier)):
            if self._sel_tier:
                self._delete_scope()
                return True
            return False
        if event.key() == Qt.Key.Key_Escape and self._sel_tier:
            self._clear_tier()
            return True
        return False

    # ─── tiered text selection (Ctrl+A ladder) ──────────────────────
    #
    # The edit pane is a GUI for raw slide txt: every tier maps to a scope
    # of textboxes, visualized as TEXT selections only (cards never paint
    # a selection state). The deck title field is never in any scope.
    #   1 = active slide's display text
    #   2 = active display + section chip (skipped when the chip is empty)
    #   3 = every textbox in the active slide's section run
    #   4 = every textbox in the deck

    @staticmethod
    def _box_fully_selected(box) -> bool:
        cursor = box.textCursor()
        if not cursor.hasSelection():
            return False
        doc = box.document()
        return (cursor.selectionStart() == 0
                and cursor.selectionEnd() >= doc.characterCount() - 1)

    def _display_fully_selected(self) -> bool:
        return self._box_fully_selected(self._edit)

    def _active_chip_text(self) -> str:
        try:
            return self._cards[self._active]._chip.toPlainText().strip()
        except (IndexError, AttributeError):
            return ""

    def _advance_tier(self):
        """One Ctrl+A step up the ladder (always consumes the key)."""
        if self._deck_id is None or not self._slides:
            self._edit.selectAll()
            return
        if self._sel_tier == 0:
            focus = QApplication.focusWidget()
            chip = None
            try:
                chip = self._cards[self._active]._chip
            except (IndexError, AttributeError):
                pass
            if focus is chip and chip is not None \
                    and not self._box_fully_selected(chip):
                # Section-name editing keeps native select-all first;
                # the next Ctrl+A climbs from the display box instead.
                chip.selectAll()
                return
            if not self._display_fully_selected():
                self._edit.selectAll()
                self._edit.setFocus()
                self._sel_tier = 1
                self._retarget_fan_out()
                return
            self._sel_tier = 1  # display already fully selected: climb on
        if self._sel_tier == 1:
            if self._active_chip_text():
                self._sel_tier = 2
            else:
                self._sel_tier = 3  # no section content: skip tier 2
        elif self._sel_tier == 2:
            self._sel_tier = 3
        elif self._sel_tier == 3:
            self._sel_tier = 4
        # Tier 4 is the top: further Ctrl+A holds the whole-deck scope.
        self._visualize_tier()
        self._retarget_fan_out()

    def _visualize_tier(self):
        """Paint the tier scope as text selections (cards untouched)."""
        if not (1 <= self._sel_tier <= 4):
            return
        self._edit.selectAll()
        try:
            active_card = self._cards[self._active]
        except (IndexError, AttributeError):
            return
        if self._sel_tier == 1:
            return
        if self._sel_tier == 2:
            active_card._chip.selectAll()
            return
        for i in self._scope_indices():
            if 0 <= i < len(self._cards):
                self._cards[i].select_content()

    def _clear_tier(self):
        """Drop the ladder: tier 0, no fan-out, no text selected anywhere."""
        self._sel_tier = 0
        try:
            self._ribbon.fan_out = None
        except (AttributeError, RuntimeError):
            pass
        try:
            cursor = self._edit.textCursor()
            if cursor.hasSelection():
                cursor.clearSelection()
                self._edit.setTextCursor(cursor)
        except RuntimeError:
            pass
        for card in getattr(self, "_cards", []):
            try:
                card.clear_content_selection()
            except RuntimeError:
                pass

    def _drop_ladder_for_typing(self):
        """Printable key while a tier is up: drop the ladder but KEEP the
        focused box's selection.

        A highlighted range must be REPLACED by what is typed — a word
        processor never appends to it. The tier selections are real text
        selections, so clearing them before Qt inserts the character
        would collapse the cursor to the end of the highlight and the new
        text would append there (the reported bug). Selections in every
        OTHER box were visualization only (tiers 3-4 paint the scope
        across cards), so those are dropped as usual: typing collapses to
        the focused box, exactly like typing over tier 1.
        """
        focus = QApplication.focusWidget()
        self._sel_tier = 0
        try:
            self._ribbon.fan_out = None
        except (AttributeError, RuntimeError):
            pass
        for card in getattr(self, "_cards", []):
            for box in (getattr(card, "_chip", None),
                        getattr(card, "_display_box", None)):
                if box is None or box is focus or box is self._edit:
                    continue
                try:
                    cursor = box.textCursor()
                    if cursor.hasSelection():
                        cursor.clearSelection()
                        box.setTextCursor(cursor)
                except RuntimeError:
                    pass

    def _retarget_fan_out(self):
        """Ribbon char-format fan-out follows the tier: tiers 3-4 rewrite
        every scoped slide's runs; tiers 1-2 act natively on the focused
        display box (section chips stay plain text)."""
        if self._sel_tier in (3, 4):
            self._ribbon.fan_out = self._apply_format_to_scope
            self._ribbon.fan_out_remove_outline = self._strip_outline_in_scope
        else:
            self._ribbon.fan_out = None
            self._ribbon.fan_out_remove_outline = None

    def _strip_outline_in_scope(self):
        """Ribbon fan-out for outline-off: mark every scoped slide's content
        explicitly un-outlined (tiers 3-4)."""

        indices = self._scope_indices()
        if not indices:
            return
        self._applying_scope_format = True
        try:
            from ui.widgets.lite_designer.format_ribbon import set_outline_off
            if self._active in indices:
                set_outline_off(self._edit.document())
            for i in indices:
                if i == self._active:
                    continue
                set_outline_off(self._doc_for(i))
        finally:
            self._applying_scope_format = False
        self._store_active()
        self._dirty = True
        self._refresh_card_states()
        if self._sel_tier in (3, 4):
            # Same rebuild-eats-selection as _apply_format_to_scope above:
            # repaint so repeated clicks keep working.
            self._visualize_tier()
        self._schedule_preview()

    def _scope_indices(self) -> list:
        """Slide indices covered by the current tier scope."""
        if not (1 <= self._sel_tier <= 4) or not self._slides:
            return []
        if self._sel_tier in (1, 2):
            return [self._active] if 0 <= self._active < len(self._slides) \
                else []
        if self._sel_tier == 3:
            for _section, run in self._section_runs():
                if self._active in run:
                    return list(run)
            return [self._active]
        return list(range(len(self._slides)))

    def _scope_start(self) -> int:
        """Splice position for paste: where newcomers land."""
        if self._sel_tier == 3:
            indices = self._scope_indices()
            return indices[0] if indices else self._active
        if self._sel_tier == 4:
            return 0
        return self._active

    def _scope_body_txt(self) -> str:
        """Raw-txt rendering of the tier scope (for copy).

        Single slide → its display text (tier 1) or its full block with
        the `*section` line (tier 2); runs and decks → body blocks joined
        by slide boundaries (title and format line never included).
        """
        from core.slide_parser import slides_body_to_txt
        if self._sel_tier == 1:
            self._store_active()
            return self._slides[self._active].get("text", "")
        if self._sel_tier == 2:
            self._store_active()
            return slides_body_to_txt([self._slides[self._active]])
        indices = self._scope_indices()
        self._store_active()
        return slides_body_to_txt([self._slides[i] for i in indices])

    # ─── tier scope ops (copy / cut / paste / delete) ────────────────

    def _copy_scope(self):
        """Ctrl+C on a tier: the scope's raw txt goes to the clipboard.

        Never wipes the clipboard with a blank scope (an empty slide's
        tier copy keeps whatever was there before) — a wiped clipboard
        turns the next paste into a silent no-op.
        """
        from PyQt6.QtWidgets import QApplication
        try:
            body = self._scope_body_txt()
        except Exception:
            logger.exception("Tier copy failed")
            self._flash("Copy failed — see console")
            return
        if not (body or "").strip():
            self._flash("Nothing to copy")
            return
        from core.clipboard import write_text
        write_text(body)
        self._flash({1: "Slide copied", 2: "Slide + section copied",
                     3: "Section copied", 4: "Deck copied"}.get(
                         self._sel_tier, "Copied"))

    def _cut_scope(self):
        self._copy_scope()
        self._remove_scope()

    def _delete_scope(self):
        self._remove_scope()

    def _remove_scope(self):
        """Delete the tier scope from the slide list.

        Single slides vanish (raw-text analogy: their text is gone, so no
        card remains); a removed header passes ownership to the same-valued
        follower; wiping the whole deck collapses to one empty slide
        (title and deck format kept) — the deck always keeps ≥1 slide.
        """
        tier = self._sel_tier
        if tier in (1, 2):
            self._remove_slide(self._active, with_section=(tier == 2))
            return
        indices = self._scope_indices()
        if not indices:
            return
        if len(indices) >= len(self._slides):
            self._clear_all_slides()
            return
        self._store_active()
        doomed_section = self._slides[indices[0]].get("section")
        del self._slides[indices[0]:indices[-1] + 1]
        self._docs = {}
        self._pass_header(doomed_section, indices[0])
        self._active = min(indices[0], len(self._slides) - 1)
        self._normalize_markers()
        self._dirty = True
        self._clear_tier()
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()

    def _remove_slide(self, index: int, with_section: bool = False):
        """Delete one slide (tier 1/2 scope): no confirm dialog — the tier
        selection IS the confirmation. Sole-slide decks collapse to an
        empty card instead of vanishing."""
        if not (0 <= index < len(self._slides)):
            return
        self._store_active()
        if len(self._slides) <= 1:
            sole = self._slides[0]
            sole["text"] = ""
            if with_section:
                sole["section"] = None
                sole["marker"] = False
            self._docs.pop(0, None)
            self._dirty = True
            self._clear_tier()
            self._rebuild_cards()
            self._activate(0)
            self._schedule_preview()
            return
        doomed = self._slides[index]
        del self._slides[index]
        self._renumber_docs(index, -1)
        self._pass_header(doomed.get("section"), index)
        if self._active >= len(self._slides):
            self._active = len(self._slides) - 1
        elif self._active > index:
            self._active -= 1
        self._normalize_markers()
        self._dirty = True
        self._clear_tier()
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()

    def _paste_scope(self):
        """Paste onto a tier: the clipboard muscles in at the scope, then
        the GUI renders the newcomers as they should be (new cards, new
        sections, whatever the parsed structure demands).

        Tier 1 reuses the single-slide shatter path (an unmarked head
        inherits the replaced slide's context). Tiers 2-3 splice the
        clipboard VERBATIM into the slides body and re-parse the deck, so
        pasted `*sections` genuinely start new sections and stray
        title/format lines behave per spec (ignored / lyric). Tier 4
        replaces the whole deck from a standalone parse (deck title kept,
        pasted deck format merges) — a whole-deck paste is most often a
        full deck txt, which deserves full-deck grace, not lyric strays.
        Refusals (blank clipboard, zero parsed slides) flash and clear.
        Every failure flashes on the status bar and logs — paste must
        never die silently. Clipboard reads go through core.clipboard
        (Qt + system-tool fallback for blind bridges).
        """
        from core.clipboard import read_text
        try:
            text = read_text()
        except Exception:
            logger.exception("Paste: could not read clipboard")
            self._flash("Paste failed — see console")
            self._clear_tier()
            return
        if not text.strip():
            self._flash(self._describe_empty_clipboard())
            self._clear_tier()
            return
        logger.info("Paste: tier=%s clipboard_chars=%d",
                    self._sel_tier, len(text))
        try:
            self._paste_scope_inner(text)
        except Exception:
            logger.exception("Tier paste failed")
            self._flash("Paste failed — see console")
            self._clear_tier()

    @staticmethod
    def _describe_empty_clipboard() -> str:
        """Explain an empty text paste: list what the clipboard DOES hold
        (image? files? nothing at all?) so a blind clipboard bridge vs.
        non-text content is distinguishable at a glance. Consults both
        Qt's view and the system tools' view."""
        from core.clipboard import qt_formats, system_formats
        try:
            from PyQt6.QtWidgets import QApplication
            platform = QApplication.platformName()
        except Exception:
            platform = "?"
        formats = qt_formats() or system_formats()
        logger.info("Paste: no text on clipboard (platform=%s formats=%s)",
                    platform, formats)
        short = {"image/png": "image", "image/jpeg": "image",
                 "text/uri-list": "files", "text/html": "formatted text"}
        names = [short.get(f, f) for f in formats[:4]]
        if names:
            return ("Clipboard has no text "
                    f"(holds: {', '.join(names)})")
        return ("Clipboard is empty — nothing to paste "
                f"(platform={platform})")

    def _paste_scope_inner(self, text: str):
        tier = self._sel_tier
        if tier == 4:
            self._paste_deck_replace(text)
            return
        if tier == 1:
            frag = parse_slide_txt(text)
            slides = frag.get("slides", [])
            structural = len(slides) > 1 or any(
                s.get("section") for s in slides)
            if not structural:
                # Single unstructured slide: replace the display text only
                # (the slide keeps its section, like typing over tier 1).
                self._store_active()
                self._slides[self._active]["text"] = \
                    slides[0].get("text", "") if slides else text.strip()
                self._docs.pop(self._active, None)
                self._dirty = True
                self._clear_tier()
                self._rebuild_cards()
                self._activate(self._active)
                self._schedule_preview()
                return
            self._paste_slides_structural(slides, frag.get("title") or "")
            return
        self._splice_verbatim(tier, text)

    def _paste_deck_replace(self, text: str):
        """Tier-4 paste: the clipboard becomes the whole deck.

        Standalone parse (deck title kept; a pasted deck format line
        merges its set keys into the deck format). Unparseable clipboards
        become one literal slide. The tier clears (nothing stays armed).
        """
        raw = (text or "").strip()
        if not raw:
            self._clear_tier()
            return
        frag = parse_slide_txt(raw)
        slides = frag.get("slides") or [
            {"section": None, "marker": False, "text": raw}]
        for key, value in (frag.get("format") or {}).items():
            if value is not None:
                self._format[key] = value
        self._ribbon.set_deck_spacing(self._format.get("spacing"))
        self._slides = [dict(s) for s in slides]
        self._docs = {}
        self._active = 0
        self._dirty = True
        self._clear_tier()
        self._rebuild_cards()
        self._activate(0)
        self._schedule_preview()
        self._flash(f"Pasted {len(slides)} slide"
                    f"{'s' if len(slides) != 1 else ''}")

    def _splice_verbatim(self, tier: int, clipboard_text: str):
        """Replace a tier 2/3 scope with the clipboard's raw text, re-parse
        the deck body, and rebuild around the newcomers."""
        from core.slide_parser import slides_body_to_txt
        self._store_active()
        if tier == 3:
            indices = self._scope_indices()
            start, end = indices[0], indices[-1] + 1
        else:  # tier 2: the active slide's whole block incl. its marker
            start, end = self._active, self._active + 1
        head = slides_body_to_txt(self._slides[:start])
        tail = slides_body_to_txt(self._slides[end:])
        middle = (clipboard_text or "").strip()
        body = "\n\n\n".join(p for p in (head, middle, tail) if p.strip())
        if not body.strip():
            self._flash("Nothing to paste — no slides found")
            self._clear_tier()
            return
        parsed = parse_slide_txt(
            f"# {self._title or '(untitled)'}\n\n\n{body}\n")
        if not parsed["slides"]:
            self._flash("Nothing to paste — no slides found")
            self._clear_tier()
            return
        newcomers = len(parsed["slides"]) - (len(self._slides) - (end - start))
        self._slides = [dict(s) for s in parsed["slides"]]
        self._docs = {}
        self._active = max(0, min(start, len(self._slides) - 1))
        self._normalize_markers()
        self._dirty = True
        self._clear_tier()
        self._rebuild_cards()
        self._activate(self._active)
        self._schedule_preview()
        self._flash(f"Pasted {max(0, newcomers)} slide"
                    f"{'s' if newcomers != 1 else ''}")

    def _apply_format_to_scope(self, fmt):
        """Ribbon fan-out for tiers 3-4: apply one char format to every
        scoped slide's full content (tiers 1-2 act natively on the
        focused display box; section chips stay plain text).

        Per-document undo stacks stay intact (each slide reverts on its
        own Ctrl+Z). The tier is preserved so Bold-then-Italic chains
        keep working.
        """
        from PyQt6.QtGui import QTextCursor as _QC
        indices = self._scope_indices()
        if not indices:
            return
        # Char-format merges fire textChanged (Qt emits on format changes
        # too) — guard it so the fan-out doesn't collapse its own tier.
        self._applying_scope_format = True
        try:
            if self._active in indices:
                cursor = self._edit.textCursor()
                pos, anchor = cursor.position(), cursor.anchor()
                cursor.select(_QC.SelectionType.Document)
                cursor.mergeCharFormat(fmt)
                cursor.setPosition(anchor)
                cursor.setPosition(pos, _QC.MoveMode.KeepAnchor)
                self._edit.setTextCursor(cursor)
            for i in indices:
                if i == self._active:
                    continue
                cursor = _QC(self._doc_for(i))
                cursor.select(_QC.SelectionType.Document)
                cursor.mergeCharFormat(fmt)
        finally:
            self._applying_scope_format = False
        self._store_active()
        self._dirty = True
        self._refresh_card_states()
        if self._sel_tier in (3, 4):
            # The refresh above rebuilt card documents (fresh QTextDocuments
            # drop the scope painting): repaint the tier so the next ribbon
            # click still lands on a visible, working selection.
            self._visualize_tier()
        self._schedule_preview()

    def _handle_paste(self) -> bool:
        """Paste: structured slide txt shatters into slides, else insert.

        Plain text that parses as multi-slide or sectioned content REPLACES
        the current slide with the fragment's slide sequence (deck title
        kept). Anything else is inserted at the cursor as plain text with
        boundary newlines trimmed — stray leading/trailing blank lines
        from real-world copies must never spawn phantom splits that yank
        the user onto an empty card. Rich (HTML) clipboards insert via
        insertHtml with smuggled formatting folded into metadata props,
        so the edit pane stays inviolable while model + preview keep
        everything. Returns True when handled.
        """
        from core.clipboard import has_html, read_text
        try:
            text = read_text()
        except Exception:
            logger.exception("Paste: could not read clipboard")
            self._flash("Paste failed — see console")
            return True
        if not text.strip():
            self._flash(self._describe_empty_clipboard())
            return True
        logger.info("Paste: tier=0 clipboard_chars=%d", len(text))
        try:
            return self._handle_paste_inner(text)
        except Exception:
            logger.exception("Tier-0 paste failed")
            self._flash("Paste failed — see console")
            return True

    def _handle_paste_inner(self, text: str) -> bool:
        from core.clipboard import has_html
        frag = parse_slide_txt(text)
        slides = frag.get("slides", [])
        structural = len(slides) > 1 or any(
            s.get("section") for s in slides)
        if structural:
            self._paste_slides_structural(slides, frag.get("title") or "")
            return True
        if has_html():
            # Rich paste, handled manually (not native): insert the HTML,
            # then fold smuggled formatting into metadata props so the
            # edit pane stays inviolable (model + preview keep
            # everything). One undo step, cursor ends after the insert.
            from PyQt6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            html = ""
            try:
                mime = clipboard.mimeData() if clipboard is not None else None
                html = mime.html() if mime is not None else ""
            except Exception:
                html = ""
            if not html:
                return False
            cursor = self._edit.textCursor()
            cursor.beginEditBlock()
            try:
                cursor.insertHtml(html)
                normalize_formatting(self._edit.document(),
                                     self._base_spacing())
            finally:
                cursor.endEditBlock()
            self._edit.setTextCursor(cursor)
            return True
        clean = text.strip("\r\n")
        if not clean.strip():
            return True  # blank-only paste: quiet no-op, never a split bomb
        self._edit.insertPlainText(clean)
        return True

    def _paste_slides_structural(self, frag_slides: list, frag_title: str):
        """Replace the active slide with a parsed slide sequence (tier 1)."""
        self._store_active()
        i = self._active
        current = self._slides[i]
        incoming = []
        for k, fs in enumerate(frag_slides):
            section = (fs.get("section") or "").strip() or None
            marker = fs.get("marker")
            if marker is None:
                marker = section is not None and (
                    k == 0 or section != (frag_slides[k - 1].get("section")
                                          or "").strip() or None)
            if k == 0 and not fs.get("marker") and section is None:
                # Unmarked head inherits the replaced slide's context, so a
                # plain multi-paragraph paste joins the surrounding run.
                incoming.append({"section": current.get("section"),
                                 "marker": current.get("marker", False),
                                 "text": fs.get("text", "")})
            else:
                incoming.append({"section": section, "marker": bool(marker),
                                 "text": fs.get("text", "")})
        self._slides[i:i + 1] = incoming
        # Indices shifted — cached docs at/after i are stale. Rebuild them
        # lazily (drop) rather than renumbering around the insertion.
        for key in [k for k in self._docs if k >= i]:
            del self._docs[key]
        self._dirty = True
        self._rebuild_cards()
        self._activate(i)
        if frag_title and frag_title != self._title:
            self._flash(f"Pasted {len(incoming)} slides (deck title kept)")
        self._schedule_preview()

    def _clear_all_slides(self):
        """Tier-4 Delete: collapse the deck to one empty slide.

        Deleting the whole-deck scope removes all slides — leaving a
        single fresh card (title and deck format kept). No undo across
        the collapse (docs are rebuilt); the tier clears with it.
        """
        self._slides = [{"section": None, "marker": False, "text": ""}]
        self._docs = {}
        self._active = 0
        self._clear_tier()
        self._dirty = True
        self._rebuild_cards()
        self._activate(0)
        self._schedule_preview()

    def _on_contents_change(self, _pos, removed, added):
        """Collapse tier selections on REAL text changes only.

        Qt fires contentsChange for ribbon formats too (a merge reports the
        selection length as both counts), so the counts alone cannot tell
        formatting from typing: ribbon merges set _in_ribbon_merge and never
        collapse (this is what lets repeated spinbox clicks keep working).
        Typing/paste/delete/undo/loads change char counts for real — even
        typing exactly as many chars as selected — and collapse as before.
        """
        if getattr(self._ribbon, "_in_ribbon_merge", False):
            return
        if (removed or 0) > 0 or (added or 0) > 0:
            if self._sel_tier and not self._applying_scope_format:
                self._clear_tier()

    def _on_editor_text(self):
        self._fit_editor_height()
        if self._splitting:
            return
        self._dirty = True
        self._maybe_split()
        self._note_editor_burst()

    def _note_editor_burst(self, now_ms=None):
        """Typing burst tracker: render at most every throttle window
        mid-burst; always arm the trailing render (the event list ends
        with an update); silence when idle (no timer games)."""
        now = _time.monotonic() * 1000.0 if now_ms is None else now_ms
        if _burst_render_due(self._burst_last_ms, self._burst_next_ms, now):
            self._burst_next_ms = now + _PREVIEW_THROTTLE_MS
            self._refresh_preview()
        elif self._burst_last_ms is None \
                or now - self._burst_last_ms > _BURST_WINDOW_MS:
            self._burst_next_ms = now + _PREVIEW_THROTTLE_MS
        self._burst_last_ms = now
        self._schedule_preview()

    def _fit_editor_height(self):
        """Pin the live editor to its content height — no jump vs static.

        READ-ONLY by design: QTextDocument.adjustSize() freezes the page at
        whatever width it pleases (measured 4px!), and setTextWidth(-1)
        wipes the page entirely — both destroy wrapping. So we never force
        layout here; the documentSizeChanged connection above re-invokes
        this with a fresh size right after every relayout. The page-width
        self-heal only repairs damage (and tracks window resizes); the
        editor itself maintains it the rest of the time.
        Past the cap the editor scrolls instead of growing.
        """
        doc = self._edit.document()
        if doc is None:
            return
        if doc.documentMargin() != 0:
            doc.setDocumentMargin(0)
        vp_w = self._edit.viewport().width()
        if vp_w > 0 and doc.pageSize().width() != vp_w:
            doc.setPageSize(QSizeF(vp_w, -1))
        h = doc.documentLayout().documentSize().height()
        self._edit.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._edit.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        line_h = self._edit.fontMetrics().height() + 2
        if not doc.toPlainText().strip() and doc.blockCount() <= 1:
            self._edit.setFixedHeight(line_h)
        else:
            self._edit.setFixedHeight(max(line_h, int(h) + 2))

    def _maybe_split(self):
        """Double-Enter (two consecutive empty blocks) splits the slide."""
        if self._splitting:
            return
        doc = self._edit.document()
        count = doc.blockCount()
        at = -1
        for i in range(count - 1):
            a = doc.findBlockByNumber(i)
            b = doc.findBlockByNumber(i + 1)
            if (a.text() == "" and b.text() == ""
                    and not self._block_tagged(a) and not self._block_tagged(b)):
                at = i
                break
        if at < 0:
            return
        self._splitting = True
        try:
            self._store_active()
            # Clone blocks after the break into a fresh document.
            from PyQt6.QtGui import QTextDocument, QTextCursor
            new_doc = QTextDocument()
            new_cursor = QTextCursor(new_doc)
            first_new = True
            for i in range(at + 2, count):
                src = doc.findBlockByNumber(i)
                if not first_new:
                    new_cursor.insertBlock(src.blockFormat())
                else:
                    new_cursor.setBlockFormat(src.blockFormat())
                    first_new = False
                it = src.begin()
                while not it.atEnd():
                    frag = it.fragment()
                    if frag.isValid():
                        # Qt stores block breaks as U+2029 — drop them.
                        text = frag.text().replace(" ", "")
                        if text:
                            new_cursor.insertText(text, frag.charFormat())
                    it += 1
            # Remove the break + moved content from the source doc.
            cursor = QTextCursor(doc)
            cursor.setPosition(doc.findBlockByNumber(at).position())
            last = doc.lastBlock()
            cursor.setPosition(last.position() + last.length() - 1,
                               QTextCursor.MoveMode.KeepAnchor)
            cursor.removeSelectedText()
            if self._format.get("spacing") is not None:
                apply_spacing_to_doc(new_doc, self._format["spacing"])
            self._track_doc(new_doc)
            self._slides[self._active]["text"] = doc_to_txt(
                doc, base_spacing=self._base_spacing())
            section = self._slides[self._active].get("section")
            self._slides.insert(self._active + 1,
                                {"section": section, "text": ""})
            self._renumber_docs(self._active + 1, +1)
            self._docs[self._active + 1] = new_doc
            self._dirty = True
            self._rebuild_cards()
            self._activate(self._active + 1)
            self._edit.moveCursor(QTextCursor.MoveOperation.Start)
        finally:
            self._splitting = False
        self._schedule_preview()

    @staticmethod
    def _block_tagged(block):
        from ui.widgets.lite_designer.rich_txt import HR_BLOCK_PROP, GAP_BLOCK_PROP
        bfmt = block.blockFormat()
        return (bfmt.hasProperty(HR_BLOCK_PROP)
                or bfmt.hasProperty(GAP_BLOCK_PROP))

    # ─── preview ────────────────────────────────────────────────────

    def _schedule_preview(self):
        if self._deck_id is not None and self._stack.currentIndex() == 0:
            self._preview_timer.start()

    def _refresh_preview(self):
        """Render the ACTIVE slide — nothing else is read.

        Deliberately cheap (no full-deck serialize, no re-parse): raw slide
        text feeds the renderers directly, ref/format come from the model.
        Fires instantly on card switch, at most every throttle window
        mid-burst, and once trailing after the last keypress — never idle.

        Theme-aware: renders with the item's own theme (self._theme_name,
        passed in by the caller — the SLIDES tab's per-output theme for
        decks). resolve_theme guarantees theme_data is never None (unknown
        names fall back to the freeform "slides" theme, never the
        scripture theme), and the ref line honors the theme's
        slide.show_title exactly like display output — so the preview
        shows the item as it will be seen on display. Save-only contract:
        reads from disk, never _working_theme — unsaved Theme-tab edits
        apply on _save_theme, not here.
        """
        if self._deck_id is None:
            return
        if not (0 <= self._active < len(self._slides)):
            return
        text = doc_to_txt(self._edit.document(),
                           base_spacing=self._base_spacing())
        self._slides[self._active]["text"] = text
        slide = self._slides[self._active]
        title = self._title or "(untitled)"
        section = slide.get("section")
        theme_name, theme_data = core.theme_loader.resolve_theme(
            self._theme_name, fallback="slides")
        ref = core.theme_loader.slide_display_ref(title, section, theme_data)
        payload = {
            "action": "display",
            "text": text,
            "ref": ref,
            "reference": ref,
            "translation": "",
            "book": "",
            "chapter": "",
            "verse": "",
            "content": "slide",
            "theme": theme_name,
            "theme_data": theme_data,
            "slide_format": self._format or None,
        }
        self._preview.display_verse(payload)

    # ─── save / reset / close ───────────────────────────────────────

    def _flash(self, text):
        self._status.setText(text)
        QTimer.singleShot(2500, lambda: self._status.setText(""))

    def _save_freeform(self):
        if self._deck_id is None:
            return
        from core.slide_service import update_deck
        self._store_active()
        raw = deck_to_txt(self._title, self._slides, self._format or None)
        if not parse_slide_txt(raw)["slides"]:
            QMessageBox.warning(self, "Lite Designer",
                                "Nothing to save — the deck has no slides.")
            return
        update_deck(self._deck_id, raw_text=raw)
        self._dirty = False
        self._flash("Saved to preview")
        self.deck_saved.emit(self._deck_id, self._active)

    def _on_save(self):
        if self._stack.currentIndex() == 0:
            self._save_freeform()
        else:
            self._save_theme()

    def _on_reset(self):
        if self._stack.currentIndex() == 0:
            if self._deck_id is not None:
                self._load_deck()
        else:
            fresh = core.theme_loader.get_theme(self._theme_name)
            if fresh is not None:
                self._original_theme = copy.deepcopy(fresh)
                self._working_theme = copy.deepcopy(fresh)
                self._theme_dirty = False
                self._props.load_theme(self._working_theme)
                self._theme_preview.apply_theme(self._working_theme)

    def _on_close(self):
        if (self._dirty or self._theme_dirty) and not self._confirm(
                "Discard unsaved changes?"):
            return
        self.close()

    # ─── theme tab (quick-editor behavior) ──────────────────────────

    def _load_theme(self):
        theme_data = core.theme_loader.get_theme(self._theme_name)
        self._original_theme = copy.deepcopy(theme_data) if theme_data else {}
        self._working_theme = copy.deepcopy(self._original_theme)
        self._theme_dirty = False
        self._props.load_theme(self._working_theme)
        self._theme_preview.apply_theme(self._working_theme)

    def _on_theme_changed(self, theme_dict):
        # Save-only contract: Theme-tab edits update the Theme preview
        # immediately but NEVER touch the Freeform slide preview — that
        # re-renders from disk on _save_theme (or the next keystroke/
        # card switch via _refresh_preview).
        self._working_theme = theme_dict
        self._theme_dirty = True
        self._theme_preview.apply_theme(theme_dict)

    def _save_theme(self):
        core.theme_loader.save_theme(self._theme_name, self._working_theme)
        self._original_theme = copy.deepcopy(self._working_theme)
        self._theme_dirty = False
        # The saved theme now drives the display — reflect it in the
        # Freeform ribbon immediately (B/Outline/case/align).
        self._sync_ribbon_theme()
        self._flash("Theme saved")
        self.theme_saved.emit(self._theme_name)
        if self._deck_id is not None:
            # The Freeform preview reads the saved theme from disk — push
            # it now so the operator sees the saved result without
            # waiting for the next keystroke (works from the Theme tab:
            # _refresh_preview has no tab guard by design).
            try:
                self._refresh_preview()
            except Exception:
                pass
