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
    QListView, QFrame, QScrollArea,
    QStyleOptionViewItem, QStyledItemDelegate, QStyle, QMenu, QAbstractItemView
)
from PyQt6.QtGui import QWheelEvent, QFontMetrics, QDrag, QCursor
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QModelIndex, QVariant, QAbstractListModel, QMimeData, QPoint, QEvent

from ui import dialogs
from ui.popups import menu_qss
from ui.styles import (
    PANEL_BODY_STYLE, SLATE_300, BLUE_500,
    translation_btn_style,
    VERSE_TEXT_SIZE, VERSE_REF_SIZE,
    TOOLBAR_BG, BG_RAISED, ACCENT_BORDER, BORDER_SUBTLE, WHITE,
    apply_minimal_scrollbar,
)
from ui.widgets.predictive_input import PredictiveScriptureInput
from ui.tokens import (
    BUTTON_HEIGHT, ROW_EVEN, ROW_HOVER, ROW_ODD, SPACE_4, SPACE_8,
    ACCENT, ACCENT_TEXT, BG_CARD_SELECTED, SELECTED_BAR_WIDTH,
    TEXT_PRIMARY, button_qss,
)
from ui.dialogs.add_translation_dialog import AddTranslationDialog
from core.bible_service import (
    AVAILABLE_TRANSLATIONS, get_chapter, get_all_verses,
    import_translation_file, refresh_available_translations,
    get_display_name, get_translation_order, set_translation_order
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
_ROW_HEIGHT = 26


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

    _BOOK_ALIASES = {"Psalm": "Psalms"}

    def find_row(self, book: str, chapter: int, verse: int) -> int:
        """Binary-ish scan for the row matching book/chapter/verse. Returns -1 if not found."""
        normalized = self._BOOK_ALIASES.get(book, book)
        for i, v in enumerate(self._verses):
            if v["book"] == normalized and v["chapter"] == chapter and v["verse"] == verse:
                return i
        return -1


class _VerseListView(QListView):
    """QListView that snaps wheel-scroll to row boundaries.

    Supports multi-select (Ctrl/Shift+click).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # The delegate paints its own quiet hover; the view only tracks
        # which row the pointer is over (no per-row widgets).
        self.hover_row = -1
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            if event.type() == QEvent.Type.MouseMove:
                row = self.indexAt(event.position().toPoint()).row()
                if row != self.hover_row:
                    self.hover_row = row
                    self.viewport().update()
            elif event.type() == QEvent.Type.Leave:
                if self.hover_row != -1:
                    self.hover_row = -1
                    self.viewport().update()
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.verse_text_size = VERSE_TEXT_SIZE
        self.verse_ref_size = VERSE_REF_SIZE
        self.verse_font_family = ""
        self.verse_font_weight = 400
        self.verse_ref_font_family = ""
        self.verse_ref_font_weight = 700

    def paint(self, painter, option: QStyleOptionViewItem, index: QModelIndex):
        model = index.model()
        verse = model.verse_at(index.row()) if hasattr(model, 'verse_at') else None
        if not verse:
            super().paint(painter, option, index)
            return

        painter.save()

        # Determine background — flat stripes (one barely-there wash) and a
        # quiet hover, both from ui.tokens. A selected row uses the same
        # surface + 3px accent bar as a schedule card / Outputs row.
        is_selected = option.state & QStyle.StateFlag.State_Selected
        hovered = getattr(option.widget, "hover_row", -1) == index.row()
        if is_selected:
            bg = BG_CARD_SELECTED
        elif hovered:
            bg = ROW_HOVER
        elif index.row() % 2 == 0:
            bg = ROW_EVEN
        else:
            bg = ROW_ODD

        from PyQt6.QtGui import QColor, QPen
        painter.fillRect(option.rect, QColor(bg))

        # Left accent bar — painted inside the row's left inset, so the
        # content stays at x+6 and text never shifts when selection moves.
        if is_selected:
            painter.fillRect(option.rect.x(), option.rect.y(),
                             SELECTED_BAR_WIDTH, option.rect.height(),
                             QColor(ACCENT))

        # Reference text (Book chapter:verse)
        abbrev = BOOK_ABBREV.get(verse['book'], verse['book'][:4])
        ref = f"{abbrev} {verse['chapter']}:{verse['verse']}"
        ref_rect = option.rect.adjusted(6, 0, 0, 0)
        ref_rect.setWidth(55)
        painter.setPen(QPen(QColor(ACCENT_TEXT if is_selected else BLUE_500)))
        font = painter.font()
        font.setPixelSize(self.verse_ref_size)
        if self.verse_ref_font_family:
            font.setFamily(self.verse_ref_font_family)
        font.setWeight(self.verse_ref_font_weight)
        painter.setFont(font)
        painter.drawText(ref_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, ref)

        # Verse text
        text_rect = option.rect.adjusted(62, 0, -6, 0)
        text_color = TEXT_PRIMARY if is_selected else SLATE_300
        painter.setPen(QPen(QColor(text_color)))
        font.setPixelSize(self.verse_text_size)
        if self.verse_font_family:
            font.setFamily(self.verse_font_family)
        font.setWeight(self.verse_font_weight)
        painter.setFont(font)
        fm = QFontMetrics(font)
        elided = fm.elidedText(verse["text"], Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(0, _ROW_HEIGHT)


# ── Virtualized Translation List ─────────────────────────────────────────────


# ── Translation Button (Legacy - kept for drag/drop compatibility) ──────────────────────────

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
        self.apply_font()
        self._update_tooltip()
        self.clicked.connect(lambda: self.single_clicked.emit(self.canonical))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setAccessibleName(f"Translation: {self.display_name}")
        self.setAccessibleDescription("Single-click to browse, double-click to broadcast, right-click for options")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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

    def apply_font(self):
        """Re-read the "panel.labels" group for this bar button."""
        self.setStyleSheet(translation_btn_style(self._active))

    def set_active(self, active: bool):
        self._active = active
        self.apply_font()

    # ── Context Menu (Rename) ────────────────────────────────────────────────────

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss())
        rename_action = menu.addAction("Rename...")
        rename_action.triggered.connect(self._on_rename)
        menu.addSeparator()
        sort_az = menu.addAction("Sort A \u2192 Z")
        sort_az.triggered.connect(lambda: self.sort_requested.emit("az"))
        sort_za = menu.addAction("Sort Z \u2192 A")
        sort_za.triggered.connect(lambda: self.sort_requested.emit("za"))
        menu.exec(self.mapToGlobal(pos))

    def _on_rename(self):
        new_name, ok = dialogs.get_text(
            self,
            "Rename Translation",
            f"Display name for {self.canonical}:",
            text=self.display_name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name:
            dialogs.warning(self, "Invalid Name", "Display name cannot be empty.")
            return
        if len(new_name) > 20:
            dialogs.warning(self, "Invalid Name", "Display name must be 20 characters or fewer.")
            return
        # Check for duplicates (allow keeping the same name)
        if new_name != self.display_name:
            from core.bible_service import rename_translation
            try:
                rename_translation(self.canonical, new_name)
            except ValueError as e:
                dialogs.warning(self, "Invalid Name", str(e))
                return
            self.display_name = new_name
            self.setText(new_name)
            self._update_tooltip()
            self.rename_requested.emit(self.canonical)

    # ── Drag & Drop ────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if self._drag_start_pos is None:
            return
        if (event.position().toPoint() - self._drag_start_pos).manhattanLength() < _DRAG_THRESHOLD:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-translation-canonical", self.canonical.encode())
        drag.setMimeData(mime)
        drag.setPixmap(self.grab())
        drag.exec(Qt.DropAction.MoveAction)

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

    # Emitted when operator double-clicks a verse (push highlighted verse)
    broadcast_in_version = pyqtSignal(str)
    # Emitted when operator double-clicks a translation (push LIVE verse)
    broadcast_live_translation = pyqtSignal(str)
    # Emitted when operator single-clicks a verse (for preview update)
    verse_clicked = pyqtSignal(str)
    # Emitted when Enter is pressed in the navigator → push to live
    navigator_push = pyqtSignal(str, str, str)
    # Emitted when translation changes (for FTS search panel)
    translation_changed = pyqtSignal(str)
    # Emitted when a translation is renamed (canonical code)
    translation_renamed = pyqtSignal(str)

    def __init__(self, translations: list = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        # Focus ring: owned by PresentationTab's ring state machine and drawn
        # around the whole work area (this panel + queue), so no ring here.

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
            background-color: {TOOLBAR_BG};
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
        trans_layout.setContentsMargins(SPACE_8, SPACE_8, SPACE_8, SPACE_8)
        trans_layout.setSpacing(SPACE_4)

        for abbrev in translations:
            display = get_display_name(abbrev)
            btn = TranslationButton(abbrev, display)
            btn.setFixedHeight(BUTTON_HEIGHT)
            btn.single_clicked.connect(self._on_translation_single_click)
            btn.double_clicked_signal.connect(self._on_translation_double_click)
            btn.sort_requested.connect(self._on_sort_translations)
            btn.rename_requested.connect(lambda _: self._apply_sort())
            btn.rename_requested.connect(self.translation_renamed.emit)
            trans_layout.addWidget(btn)
            self._translation_buttons[abbrev] = btn
            if abbrev == self._current_translation:
                btn.set_active(True)

        trans_layout.addStretch()

        self._add_btn = QPushButton("+ Add")
        self._add_btn.setAccessibleName("Add translation")
        self._add_btn.setAccessibleDescription("Import a new Bible translation")
        self._add_btn.setFixedHeight(BUTTON_HEIGHT)
        self._add_btn.setStyleSheet(self._add_btn_style())
        self._add_btn.clicked.connect(self._on_add_translation)
        trans_layout.addWidget(self._add_btn)

        scroll_area.setWidget(trans_area)

        toolbar_layout.addWidget(scroll_area, 1)

        # Nav input container
        nav_container = QWidget()
        nav_container.setStyleSheet(f"""
            background: rgba(0, 0, 0, 100);
            border-left: 1px solid {BORDER_SUBTLE};
        """)
        nav_layout = QHBoxLayout(nav_container)
        nav_layout.setContentsMargins(8, 4, 8, 4)
        nav_layout.setSpacing(8)

        # Predictive Scripture Input
        self.predictive_input = PredictiveScriptureInput()
        self.predictive_input.setStyleSheet("background: transparent; border: none;")
        self.predictive_input.navigate_requested.connect(self._on_navigate_requested)
        self.predictive_input.push_requested.connect(self._on_navigator_push)
        self.predictive_input.set_translation(self._current_translation)
        nav_layout.addWidget(self.predictive_input)

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
        apply_minimal_scrollbar(self.verse_list)
        self.verse_list.clicked.connect(self._on_verse_clicked)
        self.verse_list.doubleClicked.connect(self._on_verse_double_clicked)

        # Load user-configured font sizes from database
        self.update_verse_font_sizes()

        layout.addWidget(self.verse_list)

        # ── Load entire bible + highlight Genesis 1:1 ──
        self._bible_cache: dict[str, list[dict]] = {}
        self._load_bible()

        # ── Quick-verse typing: bare digits anywhere in this panel (outside
        # real inputs) start a short-lived verse-number take; Enter pushes it.
        from ui.widgets.quick_verse import QuickVerseRecorder
        self._quick_verse = QuickVerseRecorder(self)
        self._quick_verse.committed.connect(self._on_quick_verse_committed)
        self._quick_verse.buffer_changed.connect(self._on_quick_verse_buffer)

        self._quick_badge = QLabel(self)
        self._quick_badge.setStyleSheet(f"""
            QLabel {{
                background: {BG_RAISED};
                color: {WHITE};
                border: 1px solid {ACCENT_BORDER};
                border-radius: 8px;
                padding: 2px 8px;
                font-size: 13px;
                font-weight: 700;
            }}
        """)
        self._quick_badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._quick_badge.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._quick_badge.hide()

        # Settings → Interface: the translation bar reads "panel.labels".
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_quick_badge()

    def _position_quick_badge(self):
        """Keep the quick-verse badge pinned bottom-right (never reflows)."""
        badge = getattr(self, "_quick_badge", None)
        if badge is None:
            return
        margin = 12
        badge.adjustSize()
        badge.move(max(0, self.width() - badge.width() - margin),
                   max(0, self.height() - badge.height() - margin))
        if not badge.isHidden():
            badge.raise_()

    def _on_quick_verse_buffer(self, digits: str):
        """Show the in-progress take; hide the badge when it lapses."""
        if digits:
            self._quick_badge.setText(digits)
            self._position_quick_badge()
            self._quick_badge.show()
            self._quick_badge.raise_()
        else:
            self._quick_badge.hide()

    def _on_quick_verse_committed(self, digits: str):
        """Enter on a quick take: inject → navigate → push, or nothing."""
        try:
            verse = int(digits)
        except (TypeError, ValueError):
            return
        book = self.predictive_input.book_input.text().strip() \
            or self._highlighted_book
        chapter_text = self.predictive_input.chapter_input.text().strip()
        try:
            chapter = int(chapter_text) if chapter_text else self._highlighted_chapter
        except (TypeError, ValueError):
            chapter = self._highlighted_chapter
        if not book or chapter is None:
            return
        from core.bible_service import get_verse_count
        try:
            verse_max = get_verse_count(self._current_translation, book, int(chapter)) or 0
        except (TypeError, ValueError):
            return
        if not 1 <= verse <= verse_max:
            return  # invalid verse: nothing happens upon Enter
        self.predictive_input.verse_input.set_value(verse)
        self.navigate_to_reference(book, str(chapter), str(verse))
        self.navigator_push.emit(book, str(chapter), str(verse))

    # ── Bible Loading ──────────────────────────────────────────────────────

    def _load_bible(self) -> bool:
        """Load the entire bible for the current translation into the virtual model.
        Uses an in-memory cache to avoid re-querying bible.db on repeated switches.
        Returns False when the verses are not loadable (missing translation,
        locked/unreadable bible.db); callers must not leave the browser in a
        half-switched state in that case."""
        if self._current_translation not in self._bible_cache:
            logger.info(f"Loading entire bible [{self._current_translation}]...")
            verses = get_all_verses(self._current_translation)
            if verses:
                self._bible_cache[self._current_translation] = verses
                logger.info(f"Loaded {len(verses)} verses [{self._current_translation}]")
            else:
                logger.error("Failed to load bible verses [%s]",
                             self._current_translation)
                return False

        self._model.load_all(self._bible_cache[self._current_translation])

        # Preserve the current highlight (or default to Genesis 1:1 on first load)
        self._set_highlight(self._highlighted_book, self._highlighted_chapter, self._highlighted_verse)
        self._scroll_to_highlight()
        self._update_navigator()
        return True

    def _switch_translation(self, translation: str) -> bool:
        """Switch the browser's active translation, verifying the load succeeds.

        All translation mutations (buttons, state, settings) happen together and
        are fully reverted when the bible cannot be loaded — a failed switch must
        never leave the browser half-switched (viewer showing one translation,
        buttons claiming another), which reads to the operator as "click does
        nothing". Returns True when the new translation is live.
        """
        previous = self._current_translation
        for _name, btn in self._translation_buttons.items():
            btn.set_active(_name == translation)
        self._current_translation = translation
        self.verse_list._translation = translation
        self.predictive_input.set_translation(translation)
        set_setting("bible.last_translation", translation)

        if not self._load_bible():
            logger.warning("Translation [%s] not loadable — reverting to [%s]",
                           translation, previous)
            for _name, btn in self._translation_buttons.items():
                btn.set_active(_name == previous)
            self._current_translation = previous
            self.verse_list._translation = previous
            self.predictive_input.set_translation(previous)
            set_setting("bible.last_translation", previous)
            self._load_bible()
            return False
        return True

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
        """Scroll the currently highlighted verse into view (centered if off-screen)."""
        row = self._model.find_row(
            self._highlighted_book, self._highlighted_chapter, self._highlighted_verse
        )
        if row >= 0:
            index = self._model.index(row)
            self.verse_list.scrollTo(index, QListView.ScrollHint.EnsureVisible)

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
        """Handle Enter in navigator → push the verse to live, then hand
        keyboard focus back to the verse list.

        Focus has to LEAVE the navigator to do this: it is a real text
        input, and the quick-verse recorder deliberately ignores
        keystrokes inside text inputs. Leaving focus there after a push
        meant typing a verse number just typed more text into the
        navigator, and the operator had to click a row in the bible list
        to get digit-capture focus back — two steps where one is the
        obvious one.
        """
        self.navigator_push.emit(book, str(chapter), str(verse))
        self.focus_verse_list()

    def focus_verse_list(self):
        """Put keyboard focus on the verse list — the same state as
        clicking a row, which is what arms type-a-verse-number push."""
        view = getattr(self, "verse_list", None)
        if view is None:
            return False
        try:
            if not view.isVisible():
                return False
            view.setFocus(Qt.FocusReason.OtherFocusReason)
            return view.hasFocus()
        except RuntimeError:
            return False

    def navigate_to_reference(self, book: str, chapter: str, verse: str,
                              translation: str = None):
        """Navigate the browser to a specific reference, optionally switching translation.

        Used by search panel to jump to a result. If *translation* is provided and
        differs from the current one, switches translation first.
        """
        if translation and translation != self._current_translation:
            # Switch translation (all-or-revert — never half-switched)
            self._switch_translation(translation)

        chap_int = int(chapter) if chapter else 1
        verse_int = int(verse) if verse else 1
        self._set_highlight(book, chap_int, verse_int)
        self._scroll_to_highlight()
        self._update_navigator()

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
        self._switch_translation(abbrev)

        # Update preview with the highlighted verse in the new translation
        self.verse_clicked.emit(self._current_translation)

        # Notify FTS search panel
        self.translation_changed.emit(self._current_translation)

    def _on_translation_double_click(self, abbrev: str):
        """Double-click: switch translation, push the LIVE verse to live."""
        self._switch_translation(abbrev)

        # Push the live-displayed verse (not the highlight) in this version
        self.broadcast_live_translation.emit(self._current_translation)

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

        # Gather all translation buttons, the stretch spacer, and the
        # Add button. Add is NOT a translation: it must stay pinned after
        # the stretch, never be sorted into the bar (re-adding sorted
        # buttons appends them, which used to leave Add at the front).
        buttons = []
        stretch_item = None
        add_btn = getattr(self, "_add_btn", None)
        for i in range(layout.count()):
            item = layout.itemAt(i)
            widget = item.widget() if item else None
            if isinstance(widget, TranslationButton):
                buttons.append(widget)
            elif item and item.spacerItem():
                stretch_item = item

        # Sort by display name
        reverse = (self._sort_mode == "za")
        buttons.sort(key=lambda b: b.display_name.lower(), reverse=reverse)

        # Remove stretch, all buttons, and Add from layout
        if stretch_item:
            layout.removeItem(stretch_item)
        for btn in buttons:
            layout.removeWidget(btn)
        if add_btn is not None:
            layout.removeWidget(add_btn)

        # Re-add sorted buttons, stretch, then Add at the far right
        for btn in buttons:
            layout.addWidget(btn)
        if stretch_item:
            layout.addItem(stretch_item)
        if add_btn is not None:
            layout.addWidget(add_btn)

        # Persist the new order (translations only — Add stays out)
        new_order = [btn.canonical for btn in buttons]
        set_translation_order(new_order)

    # ── Settings-backed type ────────────────────────────────────────────────

    def _add_btn_style(self) -> str:
        """+ Add QSS — same "panel.labels" group, 12/600 default.

        Dashed form of the shared ghost button: the outline is the add
        affordance, and the width is reserved at rest.
        """
        from ui.app_theme import area_font, font_qss
        spec = area_font("panel.labels", 12, 600, size_min=8, size_max=28)
        return button_qss("ghost", font_css=font_qss(spec),
                          padding=f"0 {SPACE_8}px", dashed=True)

    def apply_translation_fonts(self):
        """Push the "panel.labels" font group onto the whole translation bar."""
        for btn in self._translation_buttons.values():
            btn.apply_font()
        if getattr(self, "_add_btn", None) is not None:
            self._add_btn.setStyleSheet(self._add_btn_style())

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "panel.labels":
            self.apply_translation_fonts()

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
            dialogs.critical(
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
        """Dynamically add a new translation button to the scroll area."""
        if abbrev in self._translation_buttons:
            return  # already exists

        display = get_display_name(abbrev)
        btn = TranslationButton(abbrev, display)
        btn.single_clicked.connect(self._on_translation_single_click)
        btn.double_clicked_signal.connect(self._on_translation_double_click)
        btn.sort_requested.connect(self._on_sort_translations)
        btn.rename_requested.connect(lambda _: self._apply_sort())
        btn.rename_requested.connect(self.translation_renamed.emit)
        self._translation_buttons[abbrev] = btn

        # Find the trans_layout inside the scroll area
        for scroll in self.findChildren(QScrollArea):
            widget = scroll.widget()
            if widget and widget.layout():
                layout = widget.layout()
                # Insert before the stretch spacer
                for i in range(layout.count()):
                    item = layout.itemAt(i)
                    if item and item.spacerItem():
                        layout.insertWidget(i, btn)
                        return
                # No stretch found, just add at end
                layout.addWidget(btn)
                return

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

    def update_verse_font_sizes(self, text_size: int | None = None, ref_size: int | None = None):
        """Update verse list font sizes and trigger a repaint."""
        from core.database import get_setting
        if text_size is None:
            text_size = int(get_setting("bible.verse_text_size",
                                        str(VERSE_TEXT_SIZE)))
        if ref_size is None:
            ref_size = int(get_setting("bible.verse_ref_size",
                                       str(VERSE_REF_SIZE)))
        self._delegate.verse_text_size = text_size
        self._delegate.verse_ref_size = ref_size
        self.update_verse_fonts()

    def update_verse_fonts(self):
        """Re-read all six Bible font keys (family/weight/size × text/ref)
        and repaint. Family "" keeps the painter font; weights default to
        today's rendering (text 400, ref bold 700)."""
        from core.database import get_setting
        from ui.app_theme import resolve_font_family, resolve_font_weight
        self._delegate.verse_font_family = resolve_font_family(
            get_setting("bible.verse_font_family", ""))
        self._delegate.verse_font_weight = resolve_font_weight(
            get_setting("bible.verse_font_weight", ""), 400)
        self._delegate.verse_ref_font_family = resolve_font_family(
            get_setting("bible.verse_ref_font_family", ""))
        self._delegate.verse_ref_font_weight = resolve_font_weight(
            get_setting("bible.verse_ref_font_weight", ""), 700)
        self.verse_list.viewport().update()

    def get_all_selected_verses(self) -> list[dict]:
        """Return all currently selected (Ctrl/Shift+click) verse data dicts."""
        indexes = self.verse_list.selectionModel().selectedIndexes()
        verses = []
        for idx in indexes:
            verse = self._model.verse_at(idx.row())
            if verse:
                verses.append(verse)
        return verses

    @property
    def _current_book(self) -> str:
        """Backward-compatible accessor for the highlighted book."""
        return self._highlighted_book

    @property
    def _current_chapter(self) -> int:
        """Backward-compatible accessor for the highlighted chapter."""
        return self._highlighted_chapter
