"""
ui/panels/browser_panel.py

Manual navigation panel: Bible browser with translation bar.
Implements single-click (browse) and double-click (broadcast) on translations.
Wired to bible.db via core.bible_service for live chapter/verse navigation.

The entire bible (~31k verses) is loaded at startup via a virtual model
so only visible rows are rendered. A verse is always highlighted, and
the predictive navigator always reflects that verse's book/chapter/verse.
"""

import json
import os
import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListView, QLineEdit, QFrame, QScrollArea, QStackedWidget,
    QStyleOptionViewItem, QStyledItemDelegate, QStyle, QMessageBox,
    QMenu, QInputDialog, QAbstractItemView
)
from PyQt6.QtGui import QIcon, QWheelEvent, QFontMetrics, QDrag, QAction, QCursor
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QModelIndex, QVariant, QAbstractListModel, QMimeData, QPoint

from ui.styles import (
    PANEL_BODY_STYLE, SLATE_300, SLATE_500, BLUE_500,
    TRANSLATION_BTN_INACTIVE, TRANSLATION_BTN_ACTIVE,
    VERSE_EVEN_BG, VERSE_ODD_BG, VERSE_SELECTED_BG, VERSE_HOVER_BG, VERSE_SELECTED_TEXT,
    BORDER_SUBTLE, SLATE_950, WHITE
)
from ui.widgets.predictive_input import PredictiveScriptureInput
from ui.dialogs.add_translation_dialog import AddTranslationDialog
from core.bible_service import (
    AVAILABLE_TRANSLATIONS, get_chapter, get_all_verses, search_verses_text,
    hybrid_search, import_translation_file, refresh_available_translations,
    get_display_name, set_display_name, get_translation_order, set_translation_order
)
from core.database import get_setting, set_setting

logger = logging.getLogger(__name__)

BOOK_ABBREV = {
    "Genesis": "Gen", "Exodus": "Exod", "Leviticus": "Lev", "Numbers": "Num",
    "Deuteronomy": "Deut", "Joshua": "Josh", "Judges": "Judg", "Ruth": "Ruth",
    "1 Samuel": "1 Sam", "2 Samuel": "2 Sam", "1 Kings": "1 Kgs", "2 Kings": "2 Kgs",
    "1 Chronicles": "1 Chr", "2 Chronicles": "2 Chr", "Ezra": "Ezra",
    "Nehemiah": "Neh", "Esther": "Esth", "Job": "Job", "Psalms": "Ps",
    "Proverbs": "Prov", "Ecclesiastes": "Eccl", "Song of Solomon": "Song",
    "Isaiah": "Isa", "Jeremiah": "Jer", "Lamentations": "Lam",
    "Ezekiel": "Ezek", "Daniel": "Dan", "Hosea": "Hos", "Joel": "Joel",
    "Amos": "Amos", "Obadiah": "Obad", "Jonah": "Jonah", "Micah": "Mic",
    "Nahum": "Nah", "Habakkuk": "Hab", "Zephaniah": "Zeph", "Haggai": "Hag",
    "Zechariah": "Zech", "Malachi": "Mal", "Matthew": "Matt", "Mark": "Mark",
    "Luke": "Luke", "John": "John", "Acts": "Acts", "Romans": "Rom",
    "1 Corinthians": "1 Cor", "2 Corinthians": "2 Cor", "Galatians": "Gal",
    "Ephesians": "Eph", "Philippians": "Phil", "Colossians": "Col",
    "1 Thessalonians": "1 Thess", "2 Thessalonians": "2 Thess",
    "1 Timothy": "1 Tim", "2 Timothy": "2 Tim", "Titus": "Titus",
    "Philemon": "Phlm", "Hebrews": "Heb", "James": "Jas",
    "1 Peter": "1 Pet", "2 Peter": "2 Pet", "1 John": "1 John",
    "2 John": "2 John", "3 John": "3 John", "Jude": "Jude",
    "Revelation": "Rev",
}

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


class _VerseListView(QListView):
    """QListView that snaps wheel-scroll to row boundaries.

    Supports multi-select (Ctrl/Shift+click).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        return super().eventFilter(obj, event)

    def wheelEvent(self, event: QWheelEvent):
        vbar = self.verticalScrollBar()
        if not vbar or vbar.maximum() == vbar.minimum():
            super().wheelEvent(event)
            return

        # Ctrl+wheel = jump half viewport (leave as-is)
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            super().wheelEvent(event)
            return

        # Scroll exactly one row per wheel notch.
        # With uniform item sizes, scrollbar value = row index (not pixels).
        delta = event.angleDelta().y()
        if delta == 0:
            return

        direction = -1 if delta > 0 else 1
        current_row = vbar.value()
        new_row = max(0, current_row + direction)
        vbar.setValue(new_row)
        event.accept()


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

        # Reference text (Book chapter:verse)
        abbrev = BOOK_ABBREV.get(verse['book'], verse['book'][:4])
        ref = f"{abbrev} {verse['chapter']}:{verse['verse']}"
        ref_rect = option.rect.adjusted(8, 0, 0, 0)
        ref_rect.setWidth(60)
        painter.setPen(QPen(QColor(BLUE_500)))
        font = painter.font()
        font.setPixelSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(ref_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, ref)

        # Verse text
        text_rect = option.rect.adjusted(68, 0, -8, 0)
        text_color = VERSE_SELECTED_TEXT if is_selected else SLATE_300
        painter.setPen(QPen(QColor(text_color)))
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

_DRAG_THRESHOLD = 5  # pixels before drag starts


class TranslationButton(QPushButton):
    """A single translation button in the translation bar.

    Supports:
      - Single-click: browse in this translation
      - Double-click: broadcast in this translation
      - Right-click: context menu with Rename
      - Drag: reorder by dragging to a new position
    """

    single_clicked = pyqtSignal(str)
    double_clicked_signal = pyqtSignal(str)
    rename_requested = pyqtSignal(str)  # canonical
    sort_requested = pyqtSignal(str)    # "az" or "za"

    def __init__(self, canonical: str, display_name: str = None, parent=None):
        self.canonical = canonical
        self.display_name = display_name or canonical
        super().__init__(self.display_name, parent)
        self._active = False
        self._drag_start_pos: QPoint | None = None
        self.setStyleSheet(TRANSLATION_BTN_INACTIVE)
        self._update_tooltip()
        self.clicked.connect(lambda: self.single_clicked.emit(self.canonical))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _update_tooltip(self):
        if self.display_name != self.canonical:
            self.setToolTip(
                f"{self.display_name} ({self.canonical})\n"
                f"Single-click: browse  |  Double-click: broadcast\n"
                f"Right-click: rename  |  Drag: reorder"
            )
        else:
            self.setToolTip(
                f"Single-click: browse in {self.canonical}\n"
                f"Double-click: broadcast in {self.canonical}\n"
                f"Right-click: rename  |  Drag: reorder"
            )

    def mouseDoubleClickEvent(self, event):
        self.double_clicked_signal.emit(self.canonical)
        super().mouseDoubleClickEvent(event)

    def set_active(self, active: bool):
        self._active = active
        self.setStyleSheet(TRANSLATION_BTN_ACTIVE if active else TRANSLATION_BTN_INACTIVE)

    # ── Context Menu (Rename) ────────────────────────────────────────────

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(self._on_rename)
        menu.addSeparator()
        sort_az = menu.addAction("Sort A \u2192 Z")
        sort_az.triggered.connect(lambda: self.sort_requested.emit("az"))
        sort_za = menu.addAction("Sort Z \u2192 A")
        sort_za.triggered.connect(lambda: self.sort_requested.emit("za"))
        menu.exec(self.mapToGlobal(pos))

    def _on_rename(self):
        new_name, ok = QInputDialog.getText(
            self,
            "Rename Translation",
            f"Display name for {self.canonical}:",
            text=self.display_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "Display name cannot be empty.")
            return
        if len(new_name) > 20:
            QMessageBox.warning(self, "Invalid Name", "Display name must be 20 characters or fewer.")
            return
        # Check for duplicates (allow keeping the same name)
        if new_name != self.display_name:
            self.display_name = new_name
            self.setText(new_name)
            self._update_tooltip()
            set_display_name(self.canonical, new_name)
            self.rename_requested.emit(self.canonical)

    # ── Drag & Drop ──────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos is None:
            super().mouseMoveEvent(event)
            return

        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() > _DRAG_THRESHOLD:
            drag = QDrag(self)
            mime = QMimeData()
            mime.setData("application/x-translation-canonical", self.canonical.encode())
            drag.setMimeData(mime)
            drag.setPixmap(self.grab())
            drag.setHotSpot(event.position().toPoint())
            drag.exec(Qt.DropAction.MoveAction)
            self._drag_start_pos = None

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)


def _reorder_in_layout(layout, source_canonical: str, target_canonical: str):
    """Move source_canonical before target_canonical in a QHBoxLayout."""
    widgets = []
    stretch_item = None
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item.widget() and isinstance(item.widget(), TranslationButton):
            widgets.append(item.widget())
        elif item.spacerItem():
            stretch_item = item

    # Find positions
    src_idx = next((i for i, w in enumerate(widgets) if w.canonical == source_canonical), None)
    tgt_idx = next((i for i, w in enumerate(widgets) if w.canonical == target_canonical), None)
    if src_idx is None or tgt_idx is None or src_idx == tgt_idx:
        return

    # Reorder
    moved = widgets.pop(src_idx)
    new_tgt = widgets.index(next(w for w in widgets if w.canonical == target_canonical))
    widgets.insert(new_tgt, moved)

    # Remove stretch and all widgets from layout
    if stretch_item:
        layout.removeItem(stretch_item)
    for w in list(widgets):
        layout.removeWidget(w)

    # Re-add in new order, then stretch at end
    for w in widgets:
        layout.addWidget(w)
    if stretch_item:
        layout.addItem(stretch_item)


class _DropQWidget(QWidget):
    """QWidget subclass that accepts drag-and-drop for translation reordering."""

    reorder_done = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat("application/x-translation-canonical"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat("application/x-translation-canonical"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if event.mimeData().hasFormat("application/x-translation-canonical"):
            source_canonical = event.mimeData().data("application/x-translation-canonical").data().decode()
            # Walk children to find the TranslationButton under cursor
            target_btn = self.childAt(event.position().toPoint())
            # childAt might return a non-button child; walk up to find the button
            while target_btn and not isinstance(target_btn, TranslationButton):
                target_btn = target_btn.parentWidget()
            if isinstance(target_btn, TranslationButton) and target_btn.canonical != source_canonical:
                layout = self.layout()
                if layout:
                    _reorder_in_layout(layout, source_canonical, target_btn.canonical)
                    self.reorder_done.emit()
            event.acceptProposedAction()


# ── Browser Panel ──────────────────────────────────────────────────────────

class BrowserPanel(QWidget):
    """Manual Bible navigation panel with translation bar."""

    # Emitted when operator double-clicks a translation
    broadcast_in_version = pyqtSignal(str)
    # Emitted when operator single-clicks a verse (for preview update)
    verse_clicked = pyqtSignal(str)
    # Emitted when Enter is pressed in the navigator → push to live
    navigator_push = pyqtSignal(str, str, str)
    # Emitted when translation changes (for FTS search panel)
    translation_changed = pyqtSignal(str)

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
        self._sort_mode: str | None = None  # None, "az", or "za"

        if translations is None:
            # Load custom order from settings; fall back to alphabetical
            saved_order = get_translation_order()
            if saved_order:
                # Filter to only versions that exist, append any new ones at end
                translations = [v for v in saved_order if v in AVAILABLE_TRANSLATIONS]
                translations += [v for v in AVAILABLE_TRANSLATIONS if v not in translations]
            else:
                translations = sorted(AVAILABLE_TRANSLATIONS)

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

        trans_area = _DropQWidget()
        trans_area.setStyleSheet("background: transparent;")
        trans_area.reorder_done.connect(self._save_translation_order)
        trans_layout = QHBoxLayout(trans_area)
        trans_layout.setContentsMargins(0, 0, 0, 0)
        trans_layout.setSpacing(6)

        for abbrev in translations:
            display = get_display_name(abbrev)
            btn = TranslationButton(abbrev, display)
            btn.single_clicked.connect(self._on_translation_single_click)
            btn.double_clicked_signal.connect(self._on_translation_double_click)
            btn.sort_requested.connect(self._on_sort_translations)
            btn.rename_requested.connect(lambda _: self._apply_sort())
            trans_layout.addWidget(btn)
            self._translation_buttons[abbrev] = btn
            if abbrev == self._current_translation:
                btn.set_active(True)

        trans_layout.addStretch()
        scroll_area.setWidget(trans_area)

        toolbar_layout.addWidget(scroll_area, 1)

        # Add translation button
        self._add_btn = QPushButton("+ Add")
        self._add_btn.setStyleSheet(f"""
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
        self._add_btn.setToolTip("Add a Bible translation from a file or download page")
        self._add_btn.clicked.connect(self._on_add_translation)
        toolbar_layout.addWidget(self._add_btn)

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
        self.predictive_input.push_requested.connect(self._on_navigator_push)
        self.predictive_input.set_translation(self._current_translation)
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
        self.search_input.textChanged.connect(self._on_search_text_changed)
        self.nav_stack.addWidget(self.search_input)

        nav_layout.addWidget(self.nav_stack, 1)

        nav_container.setFixedWidth(300)
        toolbar_layout.addWidget(nav_container)

        layout.addWidget(toolbar)

        # ── Verse Display Area (virtual QListView) ──
        self._model = VerseListModel()
        self._delegate = VerseDelegate()

        self.verse_list = _VerseListView()
        self.verse_list._translation = self._current_translation

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
        """Update the highlighted verse state and move the current index to it.

        Used for programmatic navigation (predictive input, initial load) where
        the list selection should follow. Does NOT call this from a click
        handler — setCurrentIndex would wipe a multi-selection.
        """
        self._store_highlight(book, chapter, verse)

        row = self._model.find_row(book, chapter, verse)
        if row >= 0:
            index = self._model.index(row)
            self.verse_list.setCurrentIndex(index)

    def _store_highlight(self, book: str, chapter: int, verse: int):
        """Store the highlighted verse state without touching the view/selection."""
        self._highlighted_book = book
        self._highlighted_chapter = chapter
        self._highlighted_verse = verse

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
        """Single click: highlight the verse, update navigator, and update preview.

        Uses _store_highlight (not _set_highlight) so that Ctrl/Shift multi-select
        is not wiped by setCurrentIndex.
        """
        verse = self._model.verse_at(index.row())
        if not verse:
            return

        self._store_highlight(verse["book"], verse["chapter"], verse["verse"])
        self._update_navigator()
        self.verse_clicked.emit(self._current_translation)

    def _on_verse_double_clicked(self, index: QModelIndex):
        """Double click: broadcast the verse."""
        verse = self._model.verse_at(index.row())
        if not verse:
            return

        self._store_highlight(verse["book"], verse["chapter"], verse["verse"])
        self._update_navigator()
        self.broadcast_in_version.emit(self._current_translation)

    # ── Navigation ─────────────────────────────────────────────────────────

    def _on_navigate_requested(self, book: str, chapter: int, verse: int):
        """Handle predictive input navigation → scroll to and highlight the verse."""
        self._set_highlight(book, chapter, verse)
        self._scroll_to_highlight()

    def _on_navigator_push(self, book: str, chapter: int, verse: int):
        """Handle Enter in navigator → push the verse to live."""
        self.navigator_push.emit(book, str(chapter), str(verse))

    def navigate_to_reference(self, book: str, chapter: str, verse: str,
                              translation: str = None):
        """Navigate the browser to a specific reference, optionally switching translation.

        Used by search panel to jump to a result. If *translation* is provided and
        differs from the current one, switches translation first.
        """
        if translation and translation != self._current_translation:
            # Switch translation
            for name, btn in self._translation_buttons.items():
                btn.set_active(name == translation)
            self._current_translation = translation
            self.verse_list._translation = translation
            self.predictive_input.set_translation(translation)
            set_setting("bible.last_translation", translation)
            self._load_bible()

        chap_int = int(chapter) if chapter else 1
        verse_int = int(verse) if verse else 1
        self._set_highlight(book, chap_int, verse_int)
        self._scroll_to_highlight()
        self._update_navigator()

    def _on_search_submitted(self):
        """Handle natural language search via FTS/LIKE on bible.db."""
        query = self.search_input.text().strip()
        if not query:
            return

        results = hybrid_search(query, self._current_translation, limit=30)
        if results:
            for r in results:
                if "book" not in r:
                    r["book"] = self._highlighted_book
            self._model.load_all(results)
            self.verse_list.scrollTo(self._model.index(0), QListView.ScrollHint.PositionAtTop)
            logger.info(f"Search '{query}' returned {len(results)} results")
        else:
            self._model.load_all([])
            logger.info(f"Search '{query}' returned no results")

    def _on_search_text_changed(self, text: str):
        """Live search on every keypress; restore Bible when empty."""
        query = text.strip()
        if not query:
            self._load_bible()
            return

        results = hybrid_search(query, self._current_translation, limit=30)
        if results:
            for r in results:
                if "book" not in r:
                    r["book"] = self._highlighted_book
            self._model.load_all(results)
            self.verse_list.scrollTo(self._model.index(0), QListView.ScrollHint.PositionAtTop)
        else:
            self._model.load_all([])

    # ── Translation Switching ──────────────────────────────────────────────

    def _save_translation_order(self):
        """Persist the current button order to settings.

        Called after drag-and-drop reordering — clears sort mode since
        the user is now manually controlling order.
        """
        self._sort_mode = None  # manual drag overrides auto-sort

        # Find the trans_layout by walking the toolbar's scroll area
        for scroll in self.findChildren(QScrollArea):
            widget = scroll.widget()
            if widget and widget.layout():
                layout = widget.layout()
                order = []
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.widget() and isinstance(item.widget(), TranslationButton):
                        order.append(item.widget().canonical)
                if order:
                    set_translation_order(order)
                return

    def _on_translation_single_click(self, abbrev: str):
        """Switch to that translation and navigate to the currently highlighted verse."""
        for name, btn in self._translation_buttons.items():
            btn.set_active(name == abbrev)
        self._current_translation = abbrev
        self.verse_list._translation = abbrev
        self.predictive_input.set_translation(abbrev)

        # Persist the selected translation
        set_setting("bible.last_translation", abbrev)

        # Reload the entire bible in the new translation
        self._load_bible()

        # Update preview with the highlighted verse in the new translation
        self.verse_clicked.emit(self._current_translation)

        # Notify FTS search panel
        self.translation_changed.emit(self._current_translation)

    def _on_translation_double_click(self, abbrev: str):
        """Double-click: switch translation, navigate to highlighted verse, push to live."""
        for name, btn in self._translation_buttons.items():
            btn.set_active(name == abbrev)
        self._current_translation = abbrev
        self.verse_list._translation = abbrev
        self.predictive_input.set_translation(abbrev)
        set_setting("bible.last_translation", abbrev)

        # Reload bible in new translation, preserving highlighted verse
        self._load_bible()

        # Push the highlighted verse to live display
        self.broadcast_in_version.emit(self._current_translation)

        # Notify FTS search panel
        self.translation_changed.emit(self._current_translation)

    def _on_sort_translations(self, order: str):
        """Sort translation buttons alphabetically by display name."""
        self._sort_mode = order
        self._apply_sort()

    def _apply_sort(self):
        """Re-apply the current _sort_mode to the translation bar.

        Called after any mutation (rename, add, drag-drop) to enforce
        the user's chosen sort order. If _sort_mode is None, does nothing.
        """
        if not self._sort_mode:
            return

        from core.bible_service import set_translation_order

        # Find the translation layout
        scroll_area = None
        for child in self.findChildren(QScrollArea):
            if hasattr(child, 'widget') and child.widget():
                scroll_area = child
                break
        if not scroll_area:
            return

        trans_widget = scroll_area.widget()
        if not trans_widget:
            return
        layout = trans_widget.layout()
        if not layout:
            return

        # Gather all buttons and the stretch spacer
        buttons = []
        stretch_item = None
        for i in range(layout.count()):
            item = layout.itemAt(i)
            if item.widget() and isinstance(item.widget(), TranslationButton):
                buttons.append(item.widget())
            elif item.spacerItem():
                stretch_item = item

        # Sort by display name
        reverse = (self._sort_mode == "za")
        buttons.sort(key=lambda b: b.display_name.lower(), reverse=reverse)

        # Remove stretch and all buttons from layout
        if stretch_item:
            layout.removeItem(stretch_item)
        for btn in buttons:
            layout.removeWidget(btn)

        # Re-add in sorted order, then stretch at end
        for btn in buttons:
            layout.addWidget(btn)
        if stretch_item:
            layout.addItem(stretch_item)

        # Persist the new order
        new_order = [btn.canonical for btn in buttons]
        set_translation_order(new_order)

    # ── Add Translation ─────────────────────────────────────────────────────

    def _on_add_translation(self):
        """Show the Add Translation dialog and handle import if chosen."""
        dialog = AddTranslationDialog(self)
        result = dialog.exec()
        if result != AddTranslationDialog.DialogCode.Accepted:
            return

        filepath = dialog.selected_path()
        if not filepath:
            return  # user chose "Visit Download Page" (already opened)

        # Import the file in a disabled state
        self._set_add_button_enabled(False)
        try:
            version = import_translation_file(filepath)
            refresh_available_translations()
            self._add_translation_button(version)
            logger.info(f"Translation '{version}' imported successfully")
        except Exception as e:
            logger.error(f"Failed to import translation: {e}")
            QMessageBox.critical(
                self,
                "Import Failed",
                f"Could not import the file:\n\n{e}",
            )
        finally:
            self._set_add_button_enabled(True)

    def _set_add_button_enabled(self, enabled: bool):
        """Enable/disable the +Add button."""
        if not hasattr(self, '_add_btn') or self._add_btn is None:
            return
        self._add_btn.setEnabled(enabled)
        self._add_btn.setText("+ Add" if enabled else "Importing...")

    def _add_translation_button(self, abbrev: str):
        """Dynamically add a new TranslationButton to the toolbar."""
        if abbrev in self._translation_buttons:
            return  # already exists

        display = get_display_name(abbrev)
        btn = TranslationButton(abbrev, display)
        btn.single_clicked.connect(self._on_translation_single_click)
        btn.double_clicked_signal.connect(self._on_translation_double_click)
        btn.sort_requested.connect(self._on_sort_translations)
        btn.rename_requested.connect(lambda _: self._apply_sort())
        btn.sort_requested.connect(self._on_sort_translations)

        # Find the scroll area's trans_layout and insert before the stretch
        scroll_area = None
        for child in self.findChildren(QScrollArea):
            if hasattr(child, 'widget') and child.widget():
                scroll_area = child
                break

        if scroll_area:
            trans_widget = scroll_area.widget()
            if trans_widget:
                layout = trans_widget.layout()
                # Insert at the end (before the stretch)
                count = layout.count()
                # Remove the stretch, add button, re-add stretch
                stretch_item = None
                for i in range(count - 1, -1, -1):
                    item = layout.itemAt(i)
                    if item and item.spacerItem():
                        stretch_item = layout.takeAt(i)
                        break
                layout.addWidget(btn)
                if stretch_item:
                    layout.addItem(stretch_item)

        self._translation_buttons[abbrev] = btn

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
            self.predictive_input.set_values(
                self._highlighted_book,
                self._highlighted_chapter,
                self._highlighted_verse
            )
            self._load_bible()

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
