"""
ui/panels/browser_panel.py

Manual navigation panel: Bible browser with translation bar.
Implements single-click (browse) and double-click (broadcast) on translations.
Wired to bible.db via core.bible_service for live chapter/verse navigation.

The entire bible (~31k verses) is loaded at startup via a virtual model
so only visible rows are rendered. A verse is always highlighted, and
the predictive navigator always reflects that verse's book/chapter/verse.
"""

import os
import webbrowser
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListView, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QStyleOptionViewItem, QStyledItemDelegate, QStyle
)
from PyQt6.QtGui import QIcon, QWheelEvent, QFontMetrics
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QModelIndex, QVariant, QAbstractListModel

from ui.styles import (
    PANEL_BODY_STYLE, SLATE_300, SLATE_500, BLUE_500,
    TRANSLATION_BTN_INACTIVE, TRANSLATION_BTN_ACTIVE,
    VERSE_EVEN_BG, VERSE_ODD_BG, VERSE_SELECTED_BG, VERSE_HOVER_BG,
    BORDER_SUBTLE, SLATE_950, WHITE
)
from ui.widgets.predictive_input import PredictiveScriptureInput
from core.bible_service import (
    AVAILABLE_TRANSLATIONS, get_chapter, get_all_verses, search_verses_text
)
from core.database import get_setting, set_setting

logger = logging.getLogger(__name__)

# Fixed height for each verse row (pixels)
_ROW_HEIGHT = 32


class _HScrollArea(QScrollArea):
    """QScrollArea that converts vertical wheel/trackpad scroll into horizontal scroll."""

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta()
        h_bar = self.horizontalScrollBar()

        if delta.y() != 0:
            h_bar.setValue(h_bar.value() - delta.y())
            event.accept()
        elif delta.x() != 0:
            h_bar.setValue(h_bar.value() - delta.x())
            event.accept()
        else:
            super().wheelEvent(event)


# ── Virtual Model for ~31k verses ──────────────────────────────────────────

class VerseListModel(QAbstractListModel):
    """
    Lightweight list model backed by a plain Python list of verse dicts.
    Only visible rows are instantiated as widgets by the delegate.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._verses: list[dict] = []

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._verses)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._verses):
            return QVariant()
        v = self._verses[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return f"{v['book']} {v['chapter']}:{v['verse']}  {v['text']}"
        return QVariant()

    def verse_at(self, row: int) -> dict | None:
        if 0 <= row < len(self._verses):
            return self._verses[row]
        return None

    def load_all(self, verses: list[dict]):
        """Replace the entire dataset and reset the model."""
        self.beginResetModel()
        self._verses = verses
        self.endResetModel()

    def find_row(self, book: str, chapter: int, verse: int) -> int:
        """Binary-ish scan for the row matching book/chapter/verse. Returns -1 if not found."""
        target = f"{book} {chapter}:{verse}"
        for i, v in enumerate(self._verses):
            if v["book"] == book and v["chapter"] == chapter and v["verse"] == verse:
                return i
        return -1


class VerseDelegate(QStyledItemDelegate):
    """
    Custom delegate that renders each verse row without needing a
    full QWidget per row, keeping memory usage low for 31k items.
    """

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):
        model = index.model()
        verse = model.verse_at(index.row()) if hasattr(model, 'verse_at') else None
        if not verse:
            super().paint(painter, option, index)
            return

        painter.save()

        # Determine background
        is_selected = option.state & QStyle.StateFlag.State_Selected
        if is_selected:
            bg = VERSE_SELECTED_BG
        elif index.row() % 2 == 0:
            bg = VERSE_EVEN_BG
        else:
            bg = VERSE_ODD_BG

        from PyQt6.QtGui import QColor, QPen
        color = QColor(bg)
        if bg.startswith("rgba"):
            # Parse rgba manually — alpha is 0.0-1.0, convert to 0-255
            parts = bg.replace("rgba(", "").replace(")", "").split(",")
            alpha = float(parts[3].strip())
            color = QColor(int(parts[0].strip()), int(parts[1].strip()),
                           int(parts[2].strip()), int(alpha * 255))
        elif bg == "transparent":
            color = QColor(0, 0, 0, 0)
        else:
            color = QColor(bg)

        painter.fillRect(option.rect, color)

        # Left accent border
        if is_selected:
            painter.fillRect(option.rect.x(), option.rect.y(), 2, option.rect.height(),
                             QColor(BLUE_500))

        # Reference text (chapter:verse)
        ref = f"{verse['chapter']}:{verse['verse']}"
        ref_rect = option.rect.adjusted(8, 0, 0, 0)
        ref_rect.setWidth(32)
        painter.setPen(QPen(QColor(BLUE_500)))
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(ref_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, ref)

        # Verse text
        text_rect = option.rect.adjusted(50, 0, -8, 0)
        painter.setPen(QPen(QColor(SLATE_300)))
        font.setPixelSize(12)
        font.setBold(False)
        painter.setFont(font)
        fm = QFontMetrics(font)
        elided = fm.elidedText(verse["text"], Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, _ROW_HEIGHT)


# ── Translation Button ─────────────────────────────────────────────────────

class TranslationButton(QPushButton):
    """A single translation button in the translation bar."""

    single_clicked = pyqtSignal(str)
    double_clicked_signal = pyqtSignal(str)

    def __init__(self, abbrev: str, parent=None):
        super().__init__(abbrev, parent)
        self.abbrev = abbrev
        self._active = False
        self.setStyleSheet(TRANSLATION_BTN_INACTIVE)
        self.setToolTip(f"Single-click: browse in {abbrev}. Double-click: broadcast in {abbrev}.")
        self.clicked.connect(lambda: self.single_clicked.emit(self.abbrev))

    def mouseDoubleClickEvent(self, event):
        self.double_clicked_signal.emit(self.abbrev)
        super().mouseDoubleClickEvent(event)

    def set_active(self, active: bool):
        self._active = active
        self.setStyleSheet(TRANSLATION_BTN_ACTIVE if active else TRANSLATION_BTN_INACTIVE)


# ── Browser Panel ──────────────────────────────────────────────────────────

class BrowserPanel(QWidget):
    """Manual Bible navigation panel with translation bar."""

    # Emitted when operator double-clicks a translation
    broadcast_in_version = pyqtSignal(str)

    def __init__(self, translations: list = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)

        # Load last used translation from settings, default to AMP
        saved_translation = get_setting("bible.last_translation", "AMP")
        if saved_translation not in AVAILABLE_TRANSLATIONS:
            saved_translation = "AMP"
        self._current_translation = saved_translation

        # The verse that is always highlighted
        self._highlighted_book = "Genesis"
        self._highlighted_chapter = 1
        self._highlighted_verse = 1

        self._translation_buttons: dict[str, TranslationButton] = {}

        if translations is None:
            translations = list(AVAILABLE_TRANSLATIONS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Translation Bar + Nav Input ──
        toolbar = QWidget()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(f"""
            background-color: rgba(15, 23, 42, 200);
            border-bottom: 1px solid rgba(0, 0, 0, 0.4);
        """)
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(0, 0, 0, 0)
        toolbar_layout.setSpacing(0)

        # Translation buttons (scrollable)
        scroll_area = _HScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet("""
            QScrollArea { border: none; background: transparent; }
            QScrollBar:horizontal { height: 0px; }
        """)

        trans_area = QWidget()
        trans_area.setStyleSheet("background: transparent;")
        trans_layout = QHBoxLayout(trans_area)
        trans_layout.setContentsMargins(0, 0, 0, 0)
        trans_layout.setSpacing(6)

        for abbrev in translations:
            btn = TranslationButton(abbrev)
            btn.single_clicked.connect(self._on_translation_single_click)
            btn.double_clicked_signal.connect(self._on_translation_double_click)
            trans_layout.addWidget(btn)
            self._translation_buttons[abbrev] = btn
            if abbrev == self._current_translation:
                btn.set_active(True)

        trans_layout.addStretch()
        scroll_area.setWidget(trans_area)

        toolbar_layout.addWidget(scroll_area, 1)

        # Add translation button
        add_btn = QPushButton("+ Add")
        add_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {BLUE_500};
                font-size: 10px;
                font-weight: 700;
                border: none;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                color: {WHITE};
            }}
        """)
        add_btn.setToolTip("Download additional Bible translations from biblelist.netlify.app")
        add_btn.clicked.connect(lambda: webbrowser.open("https://biblelist.netlify.app/"))
        toolbar_layout.addWidget(add_btn)

        # Nav input container
        nav_container = QWidget()
        nav_container.setStyleSheet(f"""
            background: rgba(0, 0, 0, 100);
            border-left: 1px solid {BORDER_SUBTLE};
        """)
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        # Toggle Mode Button
        _assets = os.path.join(os.path.dirname(__file__), "..", "assets")
        self._icon_search = QIcon(os.path.join(_assets, "search.svg"))
        self._icon_book = QIcon(os.path.join(_assets, "book.svg"))
        self.mode_toggle_btn = QPushButton()
        self.mode_toggle_btn.setIcon(self._icon_search)
        self.mode_toggle_btn.setIconSize(QSize(18, 18))
        self.mode_toggle_btn.setFixedSize(28, 28)
        self.mode_toggle_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {BLUE_500};
                border: none;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                background: rgba(59, 130, 246, 0.2);
            }}
        """)
        self.mode_toggle_btn.clicked.connect(self._toggle_nav_mode)
        nav_layout.addWidget(self.mode_toggle_btn)

        # Stacked widget: Predictive Input vs Natural Language Search
        self.nav_stack = QStackedWidget()

        # Mode 0: Predictive Input
        self.predictive_input = PredictiveScriptureInput()
        self.predictive_input.setStyleSheet("background: transparent; border: none;")
        self.predictive_input.navigate_requested.connect(self._on_navigate_requested)
        self.nav_stack.addWidget(self.predictive_input)

        # Mode 1: Natural Language Search
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("SEARCH: keywords...")
        self.search_input.setStyleSheet(f"""
            QLineEdit {{
                background: transparent;
                color: {WHITE};
                border: none;
                font-size: 11px;
            }}
        """)
        self.search_input.returnPressed.connect(self._on_search_submitted)
        self.nav_stack.addWidget(self.search_input)

        nav_layout.addWidget(self.nav_stack, 1)

        nav_container.setFixedWidth(300)
        toolbar_layout.addWidget(nav_container)

        layout.addWidget(toolbar)

        # ── Verse Display Area (virtual QListView) ──
        self._model = VerseListModel()
        self._delegate = VerseDelegate()

        self.verse_list = QListView()
        self.verse_list.setModel(self._model)
        self.verse_list.setItemDelegate(self._delegate)
        self.verse_list.setUniformItemSizes(True)
        self.verse_list.setSpacing(0)
        self.verse_list.setStyleSheet(f"""
            QListView {{
                background: rgba(0, 0, 0, 50);
                padding: 4px;
                outline: none;
            }}
        """)
        self.verse_list.clicked.connect(self._on_verse_clicked)
        self.verse_list.doubleClicked.connect(self._on_verse_double_clicked)
        layout.addWidget(self.verse_list)

        # ── Load entire bible + highlight Genesis 1:1 ──
        self._bible_cache: dict[str, list[dict]] = {}
        self._load_bible()

    # ── Bible Loading ──────────────────────────────────────────────────────

    def _load_bible(self):
        """Load the entire bible for the current translation into the virtual model.
        Uses an in-memory cache to avoid re-querying bible.db on repeated switches."""
        if self._current_translation not in self._bible_cache:
            logger.info(f"Loading entire bible [{self._current_translation}]...")
            verses = get_all_verses(self._current_translation)
            if verses:
                self._bible_cache[self._current_translation] = verses
                logger.info(f"Loaded {len(verses)} verses [{self._current_translation}]")
            else:
                logger.error("Failed to load bible verses")
                return

        self._model.load_all(self._bible_cache[self._current_translation])

        # Preserve the current highlight (or default to Genesis 1:1 on first load)
        self._set_highlight(self._highlighted_book, self._highlighted_chapter, self._highlighted_verse)
        self._scroll_to_highlight()
        self._update_navigator()

    def _set_highlight(self, book: str, chapter: int, verse: int):
        """Update the highlighted verse state and select it in the list (no scroll)."""
        self._highlighted_book = book
        self._highlighted_chapter = chapter
        self._highlighted_verse = verse

        row = self._model.find_row(book, chapter, verse)
        if row >= 0:
            index = self._model.index(row)
            self.verse_list.setCurrentIndex(index)

    def _scroll_to_highlight(self):
        """Scroll the currently highlighted verse to the top of the viewport."""
        row = self._model.find_row(
            self._highlighted_book, self._highlighted_chapter, self._highlighted_verse
        )
        if row >= 0:
            index = self._model.index(row)
            self.verse_list.scrollTo(index, QListView.ScrollHint.PositionAtTop)

    def _update_navigator(self):
        """Update the predictive input fields to reflect the highlighted verse."""
        self.predictive_input.set_values(
            self._highlighted_book,
            self._highlighted_chapter,
            self._highlighted_verse
        )

    # ── Verse Interaction ──────────────────────────────────────────────────

    def _on_verse_clicked(self, index: QModelIndex):
        """Single click: highlight the verse and update the navigator."""
        verse = self._model.verse_at(index.row())
        if not verse:
            return

        self._set_highlight(verse["book"], verse["chapter"], verse["verse"])
        self._update_navigator()

    def _on_verse_double_clicked(self, index: QModelIndex):
        """Double click: broadcast the verse."""
        verse = self._model.verse_at(index.row())
        if not verse:
            return

        self._set_highlight(verse["book"], verse["chapter"], verse["verse"])
        self._update_navigator()
        self.broadcast_in_version.emit(self._current_translation)

    # ── Navigation ─────────────────────────────────────────────────────────

    def _on_navigate_requested(self, book: str, chapter: int, verse: int):
        """Handle predictive input navigation → scroll to and highlight the verse."""
        self._set_highlight(book, chapter, verse)
        self._scroll_to_highlight()
        self._update_navigator()

    def _on_search_submitted(self):
        """Handle natural language search via FTS/LIKE on bible.db."""
        query = self.search_input.text().strip()
        if not query:
            return

        results = search_verses_text(query, self._current_translation, limit=30)
        if results:
            # Search results come back without 'book' in some paths, add if missing
            for r in results:
                if "book" not in r:
                    r["book"] = self._highlighted_book
            self._model.load_all(results)
            if results:
                first = results[0]
                self._set_highlight(first["book"], first["chapter"], first["verse"])
                self._scroll_to_highlight()
                self._update_navigator()
            logger.info(f"Search '{query}' returned {len(results)} results")
        else:
            self._model.load_all([])
            logger.info(f"Search '{query}' returned no results")

    # ── Translation Switching ──────────────────────────────────────────────

    def _on_translation_single_click(self, abbrev: str):
        """Switch to that translation and navigate to the currently highlighted verse."""
        for name, btn in self._translation_buttons.items():
            btn.set_active(name == abbrev)
        self._current_translation = abbrev

        # Persist the selected translation
        set_setting("bible.last_translation", abbrev)

        # Reload the entire bible in the new translation
        self._load_bible()

    def _on_translation_double_click(self, abbrev: str):
        """Double-click: switch translation, navigate to highlighted verse, push to live."""
        for name, btn in self._translation_buttons.items():
            btn.set_active(name == abbrev)
        self._current_translation = abbrev
        set_setting("bible.last_translation", abbrev)

        # Reload bible in new translation, preserving highlighted verse
        self._load_bible()

        # Push the highlighted verse to live display
        self.broadcast_in_version.emit(self._current_translation)

    # ── Mode Toggle ────────────────────────────────────────────────────────

    def _toggle_nav_mode(self):
        """Switch between Predictive Scripture Nav and Natural Language Search."""
        current_idx = self.nav_stack.currentIndex()
        if current_idx == 0:
            self.nav_stack.setCurrentIndex(1)
            self.mode_toggle_btn.setIcon(self._icon_book)
            self.mode_toggle_btn.setToolTip("Switch to Book/Chapter/Verse navigation")
            self.search_input.setFocus()
        else:
            self.nav_stack.setCurrentIndex(0)
            self.mode_toggle_btn.setIcon(self._icon_search)
            self.mode_toggle_btn.setToolTip("Switch to Natural Language Search")
            self.predictive_input.reset()

    # ── Public Accessors ───────────────────────────────────────────────────

    def get_selected_verse(self) -> dict | None:
        """Return the currently highlighted verse data with full text."""
        row = self._model.find_row(
            self._highlighted_book, self._highlighted_chapter, self._highlighted_verse
        )
        verse = self._model.verse_at(row) if row >= 0 else None
        if verse:
            return verse
        # Fallback without text
        return {
            "book": self._highlighted_book,
            "chapter": self._highlighted_chapter,
            "verse": self._highlighted_verse,
            "text": ""
        }

    def get_current_translation(self) -> str:
        """Return the currently active translation abbreviation."""
        return self._current_translation

    @property
    def _current_book(self) -> str:
        """Backward-compatible accessor for the highlighted book."""
        return self._highlighted_book

    @property
    def _current_chapter(self) -> int:
        """Backward-compatible accessor for the highlighted chapter."""
        return self._highlighted_chapter
