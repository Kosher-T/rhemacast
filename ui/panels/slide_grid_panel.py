"""
ui/panels/slide_grid_panel.py

Modular panel: ordered grid of slide cards for one deck.

Contract (see ui/panels/README.md):
  - OUT: slide_clicked(int), slide_double_clicked(int) — index into .deck["slides"]
  - IN:  set_deck(deck | None), set_title(str), set_selected_index(int)
  - Never imports sibling panels. Theme comes from core.theme_loader.
  - Pure text rendering (QLabel) — no WebEngine, instant, zero dependencies.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame,
    QScrollArea, QGridLayout, QGraphicsOpacityEffect,
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer, QEvent, QObject, QPropertyAnimation

from ui.popups import menu_qss
from ui.styles import (
    SLATE_950, SLATE_900, SLATE_600, SLATE_400, SLATE_800,
    BLUE_500, BLUE_400, BORDER_LIGHT, SELECTION_BG, MENU_BG,
    TEXT_FAINT,
)

logger = logging.getLogger(__name__)

# Strip typography default (operator UI, not screen emulation).
# The live value comes from the "slides.strip_font_size" setting.
DEFAULT_STRIP_TEXT_SIZE = 13
STRIP_SECTION_SIZE = 12


def _grid_header_style() -> str:
    """PREVIEW / LIVE grid caption — shares the "panel.labels" group.

    Unset keeps this caption's original 12px / 700 (the Scripture panel
    headers default to 13 / 600); a saved group value applies to both.
    """
    from ui.app_theme import area_font, font_qss
    spec = area_font("panel.labels", 12, 700, size_min=8, size_max=28)
    return (f"color: {SLATE_400};{font_qss(spec)} "
            f"letter-spacing: 0.5px; background: transparent; "
            f"padding: 2px 4px;")


def strip_text_size() -> int:
    """Current strip font size from settings (falls back to default)."""
    try:
        from core.database import get_setting
        return int(get_setting("slides.strip_font_size",
                               str(DEFAULT_STRIP_TEXT_SIZE)))
    except (TypeError, ValueError):
        return DEFAULT_STRIP_TEXT_SIZE


def strip_font_family() -> str:
    """Operator strip-font override ("" = follow the deck theme)."""
    try:
        from core.database import get_setting
        from ui.app_theme import resolve_font_family
        return resolve_font_family(get_setting("slides.strip_font_family", ""))
    except Exception:
        return ""


def strip_font_weight() -> int | None:
    """Operator strip-weight override (None = follow the deck theme)."""
    try:
        from core.database import get_setting
        raw = get_setting("slides.strip_font_weight", "")
        if not str(raw or "").strip():
            return None
        weight = int(raw)
        return weight if 1 <= weight <= 1000 else None
    except (TypeError, ValueError):
        return None


class SlideCard(QFrame):
    """One slide card: index badge + full multi-line text.

    No section label here — sections are group headers in the grid.
    Card chrome is flat 2D, painted manually: dark fill with no border
    when idle, vibrant wash + warm orange edge when highlighted.
    Body labels carry no text-interaction flags so clicks anywhere on the
    card propagate here and select the slide.
    """

    clicked = pyqtSignal()
    double_clicked = pyqtSignal()
    right_clicked = pyqtSignal()

    def __init__(self, index: int, text: str, theme: dict, strip_size: int = DEFAULT_STRIP_TEXT_SIZE, parent=None):
        super().__init__(parent)
        self._index = index
        self._selected = False
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Expand to fill the grid cell width; height follows content.
        from PyQt6.QtWidgets import QSizePolicy
        sp = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        sp.setHeightForWidth(True)
        self.setSizePolicy(sp)

        from core.theme_loader import theme_container
        t = theme_container(theme).get("text", {}) or theme.get("text", {})
        text_color = t.get("color", "#ffffff")
        font_family = t.get("font_family", "'Nunito', sans-serif")
        try:
            weight = int(t.get("weight", 700))
        except (TypeError, ValueError):
            weight = 700
        # Operator overrides win over the deck theme when configured.
        override_family = strip_font_family()
        if override_family:
            font_family = override_family
        override_weight = strip_font_weight()
        if override_weight is not None:
            weight = override_weight

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        idx_label = QLabel(str(index + 1))
        idx_label.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 12px; font-weight: 700; background: transparent;"
        )
        layout.addWidget(idx_label)
        self._idx_label = idx_label

        # Full slide text with real line breaks (word-wrapped, autosized).
        # Strips render text, color, and italics only — display sizing,
        # weight, and case never leak into navigation.
        from core.slide_parser import has_inline_markup, inline_markup_to_html
        body = QLabel()
        body.setObjectName("slide_body")
        body.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        body.setWordWrap(True)
        raw = (text or "").strip() or "—"
        if has_inline_markup(raw):
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(inline_markup_to_html(raw, allow=frozenset(("color", "italics"))))
        else:
            body.setText(raw)
        body.setStyleSheet(
            f"color: {text_color}; font-family: {font_family}; "
            f"font-size: {strip_size}px; font-weight: {weight}; "
            f"background: transparent; border: none;"
        )
        layout.addWidget(body)
        self._body = body
        # Trailing stretch: grid rows stretch short cards to the row height —
        # without this the layout smears that slack between the badge and the
        # text instead of parking it below, so text must hug the top.
        layout.addStretch(1)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        """Exact content height so AlignTop cards hug text without clipping."""
        margins = self.layout().contentsMargins()
        avail = max(0, width - margins.left() - margins.right())
        return (
            margins.top() + margins.bottom()
            + self._idx_label.sizeHint().height()
            + self.layout().spacing()
            + self._body.heightForWidth(avail)
        )

    @property
    def index(self) -> int:
        return self._index

    def set_selected(self, selected: bool):
        if self._selected != selected:
            self._selected = selected
            self.update()

    def paintEvent(self, event):
        # Flat 2D look: dark fill, no border when idle; vibrant wash +
        # warm orange edge when highlighted. Behavior untouched.
        from PyQt6.QtGui import QPainter, QColor, QPen
        from PyQt6.QtCore import Qt
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self._selected:
            p.setBrush(QColor(SELECTION_BG))
            p.setPen(QPen(QColor(251, 146, 60, 230)))
        else:
            p.setBrush(QColor(SLATE_900))
            p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(self.rect(), 6, 6)

    def set_slide_text(self, text: str):
        """Replace the body text in place (no rebuild; layout reflows)."""
        from core.slide_parser import has_inline_markup, inline_markup_to_html
        raw = (text or "").strip() or "—"
        if has_inline_markup(raw):
            self._body.setTextFormat(Qt.TextFormat.RichText)
            self._body.setText(inline_markup_to_html(raw, allow=frozenset(("color", "italics"))))
        else:
            self._body.setTextFormat(Qt.TextFormat.PlainText)
            self._body.setText(raw)
        self.updateGeometry()

    def mousePressEvent(self, event):
        # Accept (no super()): the base double-click implementation
        # re-fires mousePressEvent, which would emit a phantom single click
        # after every double-click. Same pattern as live_preview_panel.
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.double_clicked.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class _FadeScrollBar(QObject):
    """Mobile-style scroll indicator for the strips: no reserved lane,
    thin thumb floating over content, visible on hover/scroll, fading
    out after idleness. Indicator only — never draggable, never in the
    layout, so it can never shove cards sideways."""

    LANE = 6
    MIN_THUMB = 24
    IDLE_MS = 1200
    FADE_MS = 150

    def __init__(self, scroll: QScrollArea):
        super().__init__(scroll)
        self._scroll = scroll
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._lane = QWidget(scroll)
        self._lane.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._lane.setStyleSheet("background: transparent; border: none;")
        self._thumb = QWidget(self._lane)
        self._thumb.setStyleSheet(
            "background: rgba(161, 161, 170, 0.45); border: none;"
            "border-radius: 3px;")
        self._effect = QGraphicsOpacityEffect(self._lane)
        self._effect.setOpacity(0.0)
        self._lane.setGraphicsEffect(self._effect)
        self._lane.hide()
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(_FadeScrollBar.FADE_MS)
        self._fade.finished.connect(self._on_fade_done)
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.setInterval(_FadeScrollBar.IDLE_MS)
        self._hide_timer.timeout.connect(self.hide)
        bar = scroll.verticalScrollBar()
        bar.valueChanged.connect(lambda _v: self._poke())
        bar.rangeChanged.connect(lambda _a, _b: self._layout())
        scroll.viewport().installEventFilter(self)
        scroll.installEventFilter(self)

    @staticmethod
    def thumb_geometry(view_h: int, maximum: int, page_step: int,
                       value: int):
        """(thumb_h, thumb_y) for the lane; hidden when maximum <= 0."""
        total = maximum + page_step
        if maximum <= 0 or total <= 0 or view_h <= 0:
            return None
        h = max(_FadeScrollBar.MIN_THUMB, view_h * page_step // total)
        h = min(h, view_h)
        y = (view_h - h) * value // maximum if maximum else 0
        return h, y

    def eventFilter(self, obj, event):
        try:
            scroll = self._scroll
            if obj is scroll.viewport():
                if event.type() == QEvent.Type.Enter:
                    self._poke()
                elif event.type() == QEvent.Type.Leave:
                    self._arm_hide()
                elif event.type() == QEvent.Type.Resize:
                    self._layout()
            elif obj is scroll \
                    and event.type() == QEvent.Type.Resize:
                self._layout()
        except (AttributeError, RuntimeError):
            pass  # teardown: owner half-destroyed, stay out
        return False

    def _layout(self):
        try:
            self._place_lane()
        except RuntimeError:
            pass  # teardown: owner half-destroyed, stay out

    def _place_lane(self):
        lane_w = _FadeScrollBar.LANE
        self._lane.setGeometry(self._scroll.width() - lane_w, 0,
                               lane_w, self._scroll.height())
        bar = self._scroll.verticalScrollBar()
        geo = _FadeScrollBar.thumb_geometry(
            self._scroll.viewport().height(),
            bar.maximum(), bar.pageStep(), bar.value())
        if geo is None:
            self._lane.hide()
            return
        h, y = geo
        self._thumb.setGeometry(0, y, lane_w, h)

    def _poke(self):
        try:
            bar = self._scroll.verticalScrollBar()
            if bar.maximum() <= 0:
                self._lane.hide()
                return
            self._layout()
            self._fade.stop()
            self._hide_timer.stop()
            self._effect.setOpacity(1.0)
            self._lane.show()
            self._lane.raise_()
            self._hide_timer.start()
        except RuntimeError:
            pass  # teardown: owner half-destroyed, stay out

    def _arm_hide(self):
        try:
            if self._lane.isVisibleTo(self._scroll):
                self._hide_timer.start()
        except RuntimeError:
            pass

    def hide(self):
        try:
            self._hide_timer.stop()
            if not self._lane.isVisible():
                return
            self._fade.stop()
            self._fade.setStartValue(self._effect.opacity())
            self._fade.setEndValue(0.0)
            self._fade.start()
        except RuntimeError:
            pass

    def _on_fade_done(self):
        try:
            if self._effect.opacity() <= 0.0:
                self._lane.hide()
        except RuntimeError:
            pass


class SlideGridPanel(QWidget):
    """Scrollable grid of SlideCards for the current deck."""

    slide_clicked = pyqtSignal(int)
    slide_double_clicked = pyqtSignal(int)
    slide_edit_requested = pyqtSignal(int, int)  # deck_id, slide index

    # The live strip sets this False: right-click does nothing there.
    edit_menu_enabled = True

    def __init__(self, title: str = "", columns: int = 2, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._deck: dict | None = None
        self._selected_index: int | None = None
        self._columns = max(1, columns)
        self._built_strip_fonts: tuple | None = None
        # Trailing grid row holding all extra vertical space (see set_deck).
        self._trailing_stretch_row: int | None = None
        # Incremental card build: jobs are (row, col, slide_idx); the first
        # screenful builds synchronously, the rest in idle chunks so a
        # 500-slide deck paints instantly. _build_gen cancels stale chains.
        self._build_gen = 0
        self._build_jobs: list = []
        self._build_pos = 0
        self._build_theme: dict = {}
        self._build_size = DEFAULT_STRIP_TEXT_SIZE

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        self._header = QLabel(title)
        self._header.setStyleSheet(_grid_header_style())
        root.addWidget(self._header)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        # Mobile-style overlay indicator (auto-hide); the shared
        # always-on bar is deliberately NOT used here.
        self._fade_bar = _FadeScrollBar(self._scroll)
        self._container = QWidget()
        self._container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setSpacing(8)
        self._grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        # Columns share the strip width equally; cards expand to fill them
        # while their Ignored-policy labels elide inside the given width.
        self._grid.setColumnStretch(0, 1)
        self._grid.setColumnStretch(1, 1)
        self._scroll.setWidget(self._container)
        root.addWidget(self._scroll, 1)

        self._empty_label = QLabel("No deck loaded")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {TEXT_FAINT}; font-size: 12px; background: transparent; padding-top: 24px;"
        )
        self._grid.addWidget(self._empty_label, 0, 0)

        # Settings → Interface: PREVIEW/LIVE captions share the panel-label
        # font group.
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "panel.labels":
            self._header.setStyleSheet(_grid_header_style())

    # ── Public API ──────────────────────────────────────────────────────────

    @property
    def deck(self) -> dict | None:
        return self._deck

    @property
    def selected_index(self) -> int | None:
        return self._selected_index

    def set_title(self, title: str):
        self._header.setText(title)

    # Build tuning: first screenful synchronous, then this many per idle slice.
    _FIRST_PAINT_CARDS = 30
    _BUILD_CHUNK = 25

    def set_deck(self, deck: dict | None, select_index: int | None = None):
        """Load a deck's slides, grouped under section headers.

        Consecutive slides sharing a section form one run: an optional
        divider + header row (spanning both columns), then the run's cards
        in left-to-right reading order. The horizontal break between runs
        is deliberately thicker than the vertical card gutters so slide
        order reads left-to-right, not top-to-bottom.
        Headers/dividers build immediately (cheap); cards build synchronously
        through the first screenful (and any requested select_index), the
        rest in idle chunks — a 500-slide deck paints instantly.
        Clears selection unless select_index given.
        """
        self._deck = deck
        self._selected_index = None
        self._build_gen += 1
        self._clear_grid()
        if self._trailing_stretch_row is not None:
            self._grid.setRowStretch(self._trailing_stretch_row, 0)
            self._trailing_stretch_row = None
        slides = deck.get("slides", []) if deck else []
        if not slides:
            self._grid.addWidget(self._empty_label, 0, 0)
            self._empty_label.setText(
                f"No slides in “{deck.get('title') or '(untitled)'}”" if deck else "No deck loaded"
            )
            self._empty_label.show()
            return
        self._empty_label.hide()

        from core.theme_loader import get_theme
        try:
            theme = get_theme("default")
        except Exception as e:
            logger.warning(f"Preview theme unavailable ({e}); using bare styling")
            theme = {}
        strip_size = strip_text_size()
        self._built_strip_fonts = (strip_size, strip_font_family(),
                                   strip_font_weight())
        self._build_theme = theme
        self._build_size = strip_size

        # Plan pass (data only, no widgets): headers/dividers now, cards queued.
        cols = self._columns
        row = 0
        first_group = True
        i, n = 0, len(slides)
        jobs = []
        while i < n:
            section = slides[i].get("section")
            j = i
            while j < n and slides[j].get("section") == section:
                j += 1
            run = list(range(i, j))

            if section is not None:
                if not first_group:
                    row = self._add_section_break(row)
                self._add_section_header(row, section, len(run))
                row += 1
            elif not first_group:
                # Section-less run after a section (defensive; the parser
                # keeps sections sticky, so this is rare) — break, no header.
                row = self._add_section_break(row)

            for k, idx in enumerate(run):
                jobs.append((row + k // cols, k % cols, idx))
            row += (len(run) + cols - 1) // cols
            first_group = False
            i = j

        # Trailing stretch row: absorbs any viewport space left over when the
        # deck is shorter than the strip, so rows stay content-sized instead
        # of inflating to fill. Zero-height once content overflows.
        self._grid.setRowStretch(row, 1)
        self._trailing_stretch_row = row

        self._build_jobs = jobs
        self._build_pos = 0
        sync_n = min(len(jobs), max(self._FIRST_PAINT_CARDS, (select_index or 0) + 1))
        self._build_cards(sync_n)
        if self._build_pos < len(jobs):
            gen = self._build_gen
            QTimer.singleShot(0, lambda: self._build_more(gen))

        if select_index is not None:
            self.set_selected_index(select_index)

    def _build_cards(self, count: int):
        """Build the next `count` queued cards synchronously."""
        jobs = self._build_jobs
        deck_title = (self._deck or {}).get("title") or "(untitled)"
        end = min(len(jobs), self._build_pos + count)
        while self._build_pos < end:
            row, col, idx = jobs[self._build_pos]
            self._build_pos += 1
            slide = (self._deck or {}).get("slides", [])
            slide = slide[idx] if 0 <= idx < len(slide) else {}
            try:
                card = SlideCard(idx, slide.get("text", ""), self._build_theme, self._build_size)
            except Exception as e:
                logger.warning(f"Slide card {idx} failed to build: {e}")
                continue
            card.clicked.connect(lambda _idx=idx: self._on_card_clicked(_idx))
            card.double_clicked.connect(lambda _idx=idx: self._on_card_double_clicked(_idx))
            if self.edit_menu_enabled:
                card.right_clicked.connect(lambda _idx=idx: self._on_card_menu(_idx))
            # No alignment: cards in a row stretch to the tallest (uniform
            # rows). Text still hugs the top via the card's own trailing
            # stretch, so short cards show empty slate below, never smeared text.
            self._grid.addWidget(card, row, col)
            if not slide.get("text", "").strip():
                logger.warning(f"Slide {idx} of deck '{deck_title}' has empty text")

    def _build_more(self, gen: int):
        """Idle-chained continuation; stale generations no-op."""
        if gen != self._build_gen:
            return
        self._build_cards(self._BUILD_CHUNK)
        if self._build_pos < len(self._build_jobs):
            QTimer.singleShot(0, lambda: self._build_more(gen))

    def _build_through(self, index: int):
        """Build synchronously up to (and including) a slide index on demand."""
        while (self._build_pos < len(self._build_jobs)
               and self._build_jobs[self._build_pos][2] <= index):
            self._build_cards(1)

    def _add_section_break(self, row: int) -> int:
        """Thick horizontal break (spacer + rule) spanning both columns."""
        spacer = QWidget()
        spacer.setFixedHeight(6)
        spacer.setStyleSheet("background: transparent; border: none;")
        self._grid.addWidget(spacer, row, 0, 1, self._columns)
        row += 1
        line = QWidget()
        line.setFixedHeight(2)
        line.setStyleSheet(f"background: {BORDER_LIGHT}; border: none;")
        self._grid.addWidget(line, row, 0, 1, self._columns)
        return row + 1

    def _add_section_header(self, row: int, section: str, count: int):
        """Section label row spanning both columns."""
        header = QLabel(f"{section.upper()} · {count}")
        header.setStyleSheet(
            f"color: {BLUE_400}; font-size: {STRIP_SECTION_SIZE}px; font-weight: 700; "
            f"border-left: 3px solid {BLUE_500}; padding-left: 8px; "
            f"background: transparent; margin-top: 4px;"
        )
        self._grid.addWidget(header, row, 0, 1, self._columns)

    def set_selected_index(self, index: int | None):
        # Complete the build through the target first: with incremental
        # loading the card may not exist yet (e.g. stepping far down).
        if index is not None and self._card_at(index) is None:
            self._build_through(index)
        self._selected_index = index
        for i in range(self._grid.count()):
            w = self._grid.itemAt(i).widget()
            if isinstance(w, SlideCard):
                w.set_selected(w.index == index)
        if index is not None:
            card = self._card_at(index)
            if card:
                self._scroll.ensureWidgetVisible(card)

    def clear(self):
        self._deck = None
        self._selected_index = None
        self._built_strip_fonts = None
        self._build_gen += 1  # cancel any chained idle build
        self._build_jobs = []
        self._build_pos = 0
        self._clear_grid()
        self._empty_label.setText("No deck loaded")
        self._empty_label.show()
        self._grid.addWidget(self._empty_label, 0, 0)

    def refresh_strip_fonts(self):
        """Rebuild cards if the strip font settings changed (keeps selection + scroll)."""
        if not self._deck:
            return
        current = (strip_text_size(), strip_font_family(), strip_font_weight())
        if current == self._built_strip_fonts:
            return
        sel = self._selected_index
        sb = self._scroll.verticalScrollBar().value()
        self.set_deck(self._deck, select_index=sel)
        self._scroll.verticalScrollBar().setValue(sb)

    # ── Internals ───────────────────────────────────────────────────────────

    def _clear_grid(self):
        while self._grid.count():
            item = self._grid.takeAt(0)
            w = item.widget()
            if w and w is not self._empty_label:
                w.setParent(None)  # detach now so findChildren/selection skip it
                w.deleteLater()
        self._empty_label.setParent(None)

    def _card_at(self, index: int) -> SlideCard | None:
        for i in range(self._grid.count()):
            w = self._grid.itemAt(i).widget()
            if isinstance(w, SlideCard) and w.index == index:
                return w
        return None

    def _on_card_clicked(self, index: int):
        # No single/double disambiguation delay: a press highlights and acts
        # instantly. A following double-click only ADDS the double-click
        # action — preview-then-live is the correct sequence, not a conflict,
        # so there is nothing to suppress by waiting.
        self.set_selected_index(index)
        self.slide_clicked.emit(index)

    def _on_card_double_clicked(self, index: int):
        self.set_selected_index(index)
        self.slide_double_clicked.emit(index)

    def _on_card_menu(self, index: int):
        from PyQt6.QtWidgets import QMenu
        from PyQt6.QtGui import QCursor
        if not self.edit_menu_enabled:
            return
        deck = self._deck or {}
        if deck.get("id") is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        edit = menu.addAction("Edit Slide…")
        edit.triggered.connect(
            lambda: self.slide_edit_requested.emit(deck["id"], index))
        menu.exec(QCursor.pos())

    def update_slide_card(self, index: int, text: str) -> bool:
        """Refresh one built card's text in place (no rebuild, no scroll jump).

        Returns False when the card isn't built yet (beyond the idle frontier);
        unbuilt cards pick the fresh text up from deck data when built.
        """
        card = self._card_at(index)
        if card is None:
            return False
        card.set_slide_text(text)
        return True
