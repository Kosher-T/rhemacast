"""
ui/panels/deck_list_panel.py

Modular panel: slide-deck library with search + import/delete actions.

Contract (see ui/panels/README.md):
  - OUT: deck_selected(dict), add_to_schedule_requested(dict),
         go_live_requested(int deck_id), decks_changed
  - IN:  refresh(), selected_deck()
  - Owns its file dialogs and service calls. Never imports sibling panels.
"""

import logging
import os
import re
import tempfile

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFileDialog, QMessageBox, QMenu,
    QListView, QStyledItemDelegate, QAbstractItemView, QStyle,
)
from PyQt6.QtCore import (
    Qt, pyqtSignal, QFileSystemWatcher, QTimer, QUrl,
    QAbstractListModel, QModelIndex, QSize,
)
from PyQt6.QtGui import (
    QDesktopServices, QColor, QFont, QFontMetrics, QPainter, QPen,
)

from ui.styles import (
    SLATE_950, SLATE_800, SLATE_700,
    SLATE_600, SLATE_500, SLATE_400,
    WHITE, SELECTION_BG, SELECTION_BORDER,
    BORDER_SUBTLE, CYAN_400, MENU_BG, apply_minimal_scrollbar,
)
from ui.widgets.text_nav import install_line_edit_nav

logger = logging.getLogger(__name__)

DEFAULT_DECK_TITLE_SIZE = 12


def _deck_title_size() -> int:
    """Deck-list title size from settings (meta line runs 3px smaller)."""
    from core.database import get_setting
    try:
        return int(get_setting("slides.deck_font_size", str(DEFAULT_DECK_TITLE_SIZE)))
    except (TypeError, ValueError):
        return DEFAULT_DECK_TITLE_SIZE


class DeckListModel(QAbstractListModel):
    """Summary rows for the virtualized deck list.

    QListView only instantiates/paints visible rows, so 100k decks scroll
    like 100. Rows are plain summary dicts (id/title/slide_count/updated_at)
    — full slides load on demand via get_deck().
    """

    _ID_ROLE = Qt.ItemDataRole.UserRole
    _ROW_ROLE = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []
        self._row_h = 2 * DEFAULT_DECK_TITLE_SIZE + 18

    def set_rows(self, rows: list[dict]):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()

    def set_row_height(self, h: int):
        if h != self._row_h:
            self._row_h = h
            self.layoutChanged.emit()

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        d = self._rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return d.get("title", "")
        if role == self._ID_ROLE:
            return d.get("id")
        if role == self._ROW_ROLE:
            return d
        if role == Qt.ItemDataRole.SizeHintRole:
            return QSize(0, self._row_h)
        return None

    def index_for_id(self, deck_id: int) -> QModelIndex:
        for row, d in enumerate(self._rows):
            if d.get("id") == deck_id:
                return self.index(row, 0)
        return QModelIndex()


class DeckCardDelegate(QStyledItemDelegate):
    """Paints one slate deck card: title + meta, selected/hover states."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._title_px = DEFAULT_DECK_TITLE_SIZE
        self._meta_px = max(8, DEFAULT_DECK_TITLE_SIZE - 3)

    def set_sizes(self, title_px: int, meta_px: int):
        self._title_px = title_px
        self._meta_px = meta_px

    def paint(self, painter: QPainter, option, index):
        d = index.data(DeckListModel._ROW_ROLE)
        if not d:
            return super().paint(painter, option, index)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rect = option.rect.adjusted(1, 1, -1, -1)
        bg = QColor(SELECTION_BG) if selected else (
            QColor(SLATE_700) if hover else QColor(SLATE_800))
        painter.setBrush(bg)
        painter.setPen(QPen(QColor(SELECTION_BORDER) if selected else QColor(255, 255, 255, 25),
                            1.5 if selected else 1))
        painter.drawRoundedRect(rect, 8, 8)
        title = d.get("title") or "(untitled)"
        meta = f"{d.get('slide_count', 0)} slides  ·  {d.get('updated_at', '')}"
        x, w = rect.x() + 10, rect.width() - 20
        title_font = QFont(painter.font())
        title_font.setPixelSize(self._title_px)
        title_font.setWeight(QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor(WHITE))
        title_h = QFontMetrics(title_font).height()
        painter.drawText(x, rect.y() + 4, w, title_h + 4,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(title_font).elidedText(
                             title, Qt.TextElideMode.ElideRight, w))
        meta_font = QFont(painter.font())
        meta_font.setPixelSize(self._meta_px)
        painter.setFont(meta_font)
        painter.setPen(QColor(SLATE_400))
        painter.drawText(x, rect.y() + 4 + title_h + 3, w, title_h,
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         QFontMetrics(meta_font).elidedText(
                             meta, Qt.TextElideMode.ElideRight, w))
        painter.restore()

    def sizeHint(self, option, index):
        size = index.data(Qt.ItemDataRole.SizeHintRole)
        return size if isinstance(size, QSize) else super().sizeHint(option, index)


class DeckListPanel(QWidget):
    """Deck library: header, search, scrollable cards, action footer."""

    deck_selected = pyqtSignal(dict)
    add_to_schedule_requested = pyqtSignal(dict)
    go_live_requested = pyqtSignal(int)  # deck_id (slide 0)
    deck_deleted = pyqtSignal(int)  # deck_id
    deck_text_updated = pyqtSignal(int)  # deck_id edited as text + saved
    deck_edit_requested = pyqtSignal(int)  # deck_id → open Lite Designer
    deck_slide_updated = pyqtSignal(int, int)  # deck_id, slide index edited
    decks_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._decks: list[dict] = []  # ALL summaries (canonical lookup)
        self._current_deck: dict | None = None
        self._last_search_row: int | None = None  # history row for chosen marks
        # Temporary text-edit sessions (pre-Lite-Designer): deck_id ->
        # {"path": temp .txt path, "mtime": last seen mtime, "warned_empty": bool}
        self._edit_sessions: dict[int, dict] = {}
        self._watcher = QFileSystemWatcher(self)
        self._watcher.fileChanged.connect(self._on_watched_file_changed)
        # New-deck sessions (pre-Lite-Designer): temp path → last seen mtime.
        # The file lives in data/slides/ so it doubles as the deck's source.
        self._new_deck_sessions: dict[str, float] = {}
        self._watcher.fileChanged.connect(self._on_new_deck_file_changed)
        # Poll while sessions are open: atomic-save editors replace the file,
        # which can drop the watch — stat catches what signals miss.
        self._poll = QTimer(self)
        self._poll.setInterval(1000)
        self._poll.timeout.connect(self._check_edit_sessions)
        self._poll.timeout.connect(self._check_new_deck_sessions)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        # ── Header ──
        header = QLabel("DECKS")
        header.setStyleSheet(
            f"color: {SLATE_500}; font-size: 9px; font-weight: 700; "
            f"letter-spacing: 1px; background: transparent;"
        )
        root.addWidget(header)

        # ── Search ──
        self.search_box = QLineEdit()
        # Word gestures + focus-select-all + triple-click-select-all.
        # A plain QLineEdit on purpose: emulating a single-line field on
        # QTextEdit is what produced the selection and caret bugs.
        install_line_edit_nav(self.search_box)
        self.search_box.setPlaceholderText("Search title or lyrics…")
        self.search_box.setStyleSheet(f"""
            QLineEdit {{
                background: {SLATE_800};
                color: {WHITE};
                border: 1px solid {BORDER_SUBTLE};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {CYAN_400};
            }}
        """)
        self.search_box.textChanged.connect(
            lambda: self._on_search(self.search_box.text()))
        root.addWidget(self.search_box)

        # ── Session-only search history (Up/Down recall) ──
        # Qualifying a query: 2s idle, or the operator opens/activates a
        # matching deck / scrolls the list.
        from core.constants import SEARCH_HISTORY_IDLE_MS, SEARCH_HISTORY_MAX_ENTRIES
        from ui.widgets.search_history import SearchHistory
        self._search_history = SearchHistory(
            self.search_box, idle_ms=SEARCH_HISTORY_IDLE_MS,
            max_entries=SEARCH_HISTORY_MAX_ENTRIES)

        # ── Virtualized card list (only visible rows paint) ──
        self._model = DeckListModel(self)
        self._delegate = DeckCardDelegate(self)
        self._view = QListView()
        self._view.setModel(self._model)
        self._view.setItemDelegate(self._delegate)
        self._view.setUniformItemSizes(True)
        self._view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._view.setMouseTracking(True)  # hover highlight in delegate
        self._view.setSpacing(4)
        self._view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._view.setCursor(Qt.CursorShape.PointingHandCursor)
        self._view.setStyleSheet(
            "QListView { background: transparent; border: none; outline: none; }"
            "QListView::item { background: transparent; border: none; }"
        )
        apply_minimal_scrollbar(self._view)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._view.customContextMenuRequested.connect(self._on_context_menu)
        self._view.selectionModel().currentChanged.connect(self._on_current_changed)
        root.addWidget(self._view, 1)

        # Scroll-qualifies the query, but only after a render settles
        # (populating the list moves the scrollbar on its own).
        self._search_history.bind_scroll(self._view.verticalScrollBar())

        self._empty = QLabel("No decks yet.\nImport a .txt file or an\nEasyWorship library to begin.")
        self._empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty.setStyleSheet(
            f"color: {SLATE_600}; font-size: 11px; background: transparent; padding-top: 24px;"
        )
        self._empty.hide()
        root.addWidget(self._empty, 1)

        # ── Action footer (imports only — per-deck actions live in the
        # right-click context menu)
        footer = QVBoxLayout()
        footer.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        self.btn_import = QPushButton("Import .txt")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._on_import)
        row1.addWidget(self.btn_import)

        self.btn_import_ew = QPushButton("Import EasyWorship")
        self.btn_import_ew.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_ew.setToolTip(
            "Import songs from an EasyWorship v6 Data folder (containing Songs.db)"
        )
        self.btn_import_ew.clicked.connect(self._on_import_easyworship)
        row1.addWidget(self.btn_import_ew)
        footer.addLayout(row1)

        row0 = QHBoxLayout()
        row0.setSpacing(6)
        self.btn_export_list = QPushButton("Export Deck List…")
        self.btn_export_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_export_list.setToolTip(
            "Write all deck titles, slide counts, and dates to a txt file"
        )
        self.btn_export_list.clicked.connect(self._on_export_list)
        row0.addWidget(self.btn_export_list)
        footer.addLayout(row0)

        root.addLayout(footer)

        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        # Catch saves made by editors the file watcher missed (atomic-save)
        # while the user returns to the app.
        self._check_edit_sessions()
        self._check_new_deck_sessions()

    # ── Public API ──────────────────────────────────────────────────────────

    def selected_deck(self) -> dict | None:
        return self._current_deck

    def decks(self) -> list[dict]:
        return list(self._decks)

    def refresh(self, keep_selection: bool = True):
        """Reload deck summaries (no slides_json), preserving selection when possible."""
        from core.slide_service import list_deck_summaries
        selected_id = self._current_deck["id"] if keep_selection and self._current_deck else None
        self._decks = list_deck_summaries()
        self._populate(selected_id)
        self.decks_changed.emit()

    def clear_selection(self):
        self._current_deck = None
        self._view.clearSelection()

    def refresh_card_size(self):
        """Re-read the deck font setting (view relayouts; zero rebuilds)."""
        size = _deck_title_size()
        self._model.set_row_height(2 * size + 18)
        self._delegate.set_sizes(size, max(8, size - 3))

    # ── Internals ──────────────────────────────────────────────────────────

    @staticmethod
    def _to_summary(d: dict) -> dict:
        """Normalize an FTS (full-row) hit to summary shape."""
        if "slides" not in d and "_title_lower" in d:
            return d
        title = d.get("title") or "(untitled)"
        return {"id": d["id"], "title": title,
                "slide_count": len(d.get("slides", [])),
                "updated_at": (d.get("updated_at") or "")[:10],
                "_title_lower": title.lower()}

    def _apply_rows(self, rows: list[dict]):
        self._model.set_rows(rows)
        empty = not rows
        self._view.setVisible(not empty)
        self._empty.setVisible(empty)

    def _populate(self, selected_id: int | None = None):
        self._apply_rows(self._decks)
        if selected_id is not None and any(d["id"] == selected_id for d in self._decks):
            deck = next(d for d in self._decks if d["id"] == selected_id)
            self._select_deck(deck, emit=False)
        else:
            self._current_deck = None
            self._view.clearSelection()

    def _lookup(self, deck_id: int) -> dict | None:
        return next((d for d in self._decks if d["id"] == deck_id), None)

    def _select_deck(self, deck: dict, emit: bool = True):
        self._current_deck = deck
        idx = self._model.index_for_id(deck["id"])
        if idx.isValid():
            self._view.selectionModel().blockSignals(True)
            self._view.setCurrentIndex(idx)
            self._view.selectionModel().blockSignals(False)
        if emit:
            # History: a deck picked while searching answers that search.
            if self.search_box.text().strip() and self._last_search_row:
                # Clicking a hit qualifies the query (no idle wait).
                self._search_history.note_used()
                from core.database import mark_search_chosen
                mark_search_chosen(self._last_search_row, deck.get("title", ""))
            self.deck_selected.emit(dict(deck))

    def _on_current_changed(self, current, _previous):
        if not current.isValid():
            self._current_deck = None
            return
        deck = self._lookup(current.data(DeckListModel._ID_ROLE))
        if deck is not None:
            self._current_deck = deck
            if self.search_box.text().strip():
                # Selecting a matching deck qualifies the query.
                self._search_history.note_used()
            self.deck_selected.emit(dict(deck))

    def _deck_menu(self, deck_id: int) -> QMenu:
        """Right-click menu: new deck plus the four per-deck actions."""
        menu = QMenu(self)
        menu.setStyleSheet(self._menu_style())
        new = menu.addAction("New Deck…")
        new.triggered.connect(self._on_new_deck)
        menu.addSeparator()
        designer = menu.addAction("Edit…")
        designer.triggered.connect(lambda: self.deck_edit_requested.emit(deck_id))
        edit = menu.addAction("Edit as Text…")
        edit.triggered.connect(lambda: self._on_edit_deck(deck_id))
        live = menu.addAction("Go Live")
        live.triggered.connect(self._on_go_live)
        sched = menu.addAction("Add to Schedule")
        sched.triggered.connect(self._on_add_to_schedule)
        menu.addSeparator()
        delete = menu.addAction("Delete Deck")
        delete.triggered.connect(self._on_delete)
        return menu

    def _on_context_menu(self, pos):
        idx = self._view.indexAt(pos)
        if not idx.isValid():
            menu = QMenu(self)
            menu.setStyleSheet(self._menu_style())
            new = menu.addAction("New Deck…")
            new.triggered.connect(self._on_new_deck)
            menu.exec(self._view.viewport().mapToGlobal(pos))
            return
        deck = self._lookup(idx.data(DeckListModel._ID_ROLE))
        if not deck:
            return
        # Highlight only — no emit: right-click must not reload preview
        # (that resets the strip to slide 0 and jumps the scroll to top).
        self._select_deck(deck, emit=False)
        self._deck_menu(deck["id"]).exec(self._view.viewport().mapToGlobal(pos))

    @staticmethod
    def _menu_style() -> str:
        return f"""
            QMenu {{
                background: {MENU_BG};
                color: {WHITE};
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background: {SELECTION_BG};
            }}
        """

    def _on_search(self, text: str):
        from core.slide_service import list_deck_summaries, search_decks
        query = text.strip()
        if not query:
            self._last_search_row = None
            self._decks = list_deck_summaries()
            self._populate(selected_id=None)
            return
        rows = [self._to_summary(d) for d in search_decks(query)]
        self._apply_rows(rows)
        self._current_deck = None
        # Repopulating scrolls the list on its own; re-arm so only the
        # operator's own scrolling counts as qualifying the query.
        self._search_history.arm_scroll()
        # History: document the search (FTS hits). Keystroke runs coalesce.
        from core.database import (current_operator_session, log_search_event)
        self._last_search_row = log_search_event(
            current_operator_session(), "decks", query, len(rows),
            [d["title"] for d in rows[:5]])

    def _on_add_to_schedule(self):
        if self._current_deck:
            self.add_to_schedule_requested.emit(dict(self._current_deck))

    def _on_go_live(self):
        if self._current_deck:
            self.go_live_requested.emit(self._current_deck["id"])

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import slide txt files", "", "Text files (*.txt);;All files (*)"
        )
        if not paths:
            return
        from core.slide_service import import_txt
        imported, failed = [], []
        for path in paths:
            try:
                imported.extend(import_txt(path))
            except Exception as e:
                logger.error(f"Failed to import {path}: {e}")
                failed.append((path, str(e)))
        self.refresh(keep_selection=False)
        if failed:
            detail = "\n\n".join(f"{p}\n{err}" for p, err in failed)
            QMessageBox.warning(self, "Import Failed", f"Some files could not be imported:\n\n{detail}")

    def _on_export_list(self):
        """Write every deck (title, slide count, date) to a txt inventory file."""
        from datetime import date
        from core.slide_service import list_deck_summaries
        try:
            decks = sorted(list_deck_summaries(),
                           key=lambda d: d.get("title", "").lower())
        except Exception as e:
            logger.error(f"Deck list export failed: {e}")
            QMessageBox.critical(self, "Export Failed", f"Could not read decks:\n\n{e}")
            return
        lines = [
            f"RhemaCast Deck Library — {date.today().isoformat()}",
            f"{len(decks)} {'deck' if len(decks) == 1 else 'decks'}",
            "",
        ]
        if decks:
            for d in decks:
                lines.append(d.get("title") or "(untitled)")
        else:
            lines.append("(no decks)")
        lines.append("")
        default_name = f"deck-library-{date.today().isoformat()}.txt"
        default_path = os.path.join(os.path.expanduser("~"), default_name)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Deck List", default_path, "Text files (*.txt);;All files (*)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
        except OSError as e:
            logger.error(f"Deck list export failed: {e}")
            QMessageBox.critical(self, "Export Failed", f"Could not write file:\n\n{e}")
            return
        logger.info(f"Exported {len(decks)} decks to {path}")

    @staticmethod
    def _ask_existing_songs(existing: int, total: int):
        """Skip-vs-overwrite choice for songs already in the library.

        Returns "skip", "overwrite", or None (cancelled). Skip is the
        default: it never touches the operator's current decks.
        """
        box = QMessageBox()
        box.setWindowTitle("EasyWorship Import")
        box.setText(
            f"{existing} of {total} songs are already in your library.\n\n"
            "Skip them, or overwrite them with the imported versions?"
        )
        skip_btn = box.addButton(
            "Skip existing", QMessageBox.ButtonRole.ActionRole)
        overwrite_btn = box.addButton(
            "Overwrite existing", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(skip_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is skip_btn:
            return "skip"
        if clicked is overwrite_btn:
            return "overwrite"
        return None

    def _on_import_easyworship(self):
        """Import songs from an EasyWorship v6 Data directory."""
        from PyQt6.QtWidgets import QApplication
        data_dir = QFileDialog.getExistingDirectory(
            self, "Select EasyWorship Data folder", "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not data_dir:
            return
        if not os.path.isfile(os.path.join(data_dir, "Songs.db")):
            QMessageBox.warning(
                self, "EasyWorship Import",
                f"No Songs.db found in:\n{data_dir}\n\n"
                "Select the folder that contains Songs.db and SongWords.db "
                "(e.g. EasyWorship/Default/v6.1/Databases/Data).",
            )
            return
        from core.easyworship_import import (
            import_easyworship, count_existing_easyworship,
        )
        try:
            existing, total = count_existing_easyworship(data_dir)
        except Exception as e:
            logger.error(f"EasyWorship import failed: {e}")
            QMessageBox.critical(self, "Import Failed", f"EasyWorship import failed:\n\n{e}")
            return
        on_existing = "overwrite"
        if existing > 0:
            choice = self._ask_existing_songs(existing, total)
            if choice is None:
                return
            on_existing = choice
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            result = import_easyworship(
                data_dir=data_dir, on_existing=on_existing)
        except Exception as e:
            logger.error(f"EasyWorship import failed: {e}")
            QMessageBox.critical(self, "Import Failed", f"EasyWorship import failed:\n\n{e}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.refresh(keep_selection=False)
        failed = result.get("failed", [])
        msg = (
            f"New songs imported: {result['imported']}\n"
            f"Existing updated:   {result['updated']}\n"
            f"Skipped (no lyrics): {result['skipped']}"
        )
        if result.get("skipped_existing"):
            msg += f"\nSkipped (already in library): {result['skipped_existing']}"
        if failed:
            detail = "\n".join(f"{t}: {err}" for t, err in failed[:5])
            more = f"\n… and {len(failed) - 5} more" if len(failed) > 5 else ""
            QMessageBox.warning(self, "EasyWorship Import", f"{msg}\n\nFailed:\n{detail}{more}")
        else:
            QMessageBox.information(self, "EasyWorship Import", msg)

    def _on_delete(self):
        if not self._current_deck:
            return
        deck = self._current_deck
        confirm = QMessageBox.question(
            self, "Delete Deck",
            f"Delete \"{deck.get('title') or '(untitled)'}\"?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from core.slide_service import delete_deck
        deleted_id = deck["id"]
        delete_deck(deleted_id)
        self._current_deck = None
        self._end_edit_session(deleted_id)
        self.deck_deleted.emit(deleted_id)
        self.refresh(keep_selection=False)

    # ── Edit as text (temporary, pre-Lite-Designer) ─────────────────────────

    def _on_edit_deck(self, deck_id: int):
        """Edit action: re-open the open temp file, or start a new session."""
        if deck_id in self._edit_sessions:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._edit_sessions[deck_id]["path"]))
        else:
            self._begin_edit_session(deck_id)

    # ── Single-slide edit (dialog; structure untouched) ─────────────────────

    def open_slide_editor(self, deck_id: int, index: int):
        """Modal raw-text editor for one slide. No-ops on cancel/empty."""
        from PyQt6.QtWidgets import QDialog, QPlainTextEdit, QDialogButtonBox
        from core.slide_service import get_deck, update_slide
        deck = get_deck(deck_id)
        if not deck or not (0 <= index < len(deck.get("slides", []))):
            return
        slide = deck["slides"][index]
        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit Slide {index + 1} — {deck.get('title') or '(untitled)'}")
        dlg.setMinimumSize(480, 320)
        layout = QVBoxLayout(dlg)
        section = slide.get("section")
        info = QLabel(f"Section: {section or '—'}    ·    Raw text ([markers] preserved)")
        info.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; background: transparent;")
        layout.addWidget(info)
        edit = QPlainTextEdit(dlg)
        edit.setPlainText(slide.get("text", ""))
        layout.addWidget(edit, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        new_text = edit.toPlainText()
        if not new_text.strip():
            QMessageBox.warning(
                self, "Empty Slide",
                "Slide text can't be empty — keeping the previous version.\n"
                "(Restructure slides via Edit as Text… in the deck menu.)")
            return
        try:
            updated = update_slide(deck_id, index, new_text)
        except (IndexError, ValueError) as e:
            QMessageBox.critical(self, "Edit Failed", str(e))
            return
        if updated is None:
            QMessageBox.critical(self, "Edit Failed", "Deck no longer exists.")
            return
        self.refresh(keep_selection=True)
        self.deck_slide_updated.emit(deck_id, index)
        logger.info(f"Deck {deck_id} slide {index} edited")

    # ── New deck (temporary, pre-Lite-Designer) ─────────────────────────────

    _NEW_DECK_SKELETON = "# New Deck\n\n\n*Verse 1\n"

    def _on_new_deck(self):
        """Create a skeleton txt in data/slides/ and open it for editing.

        The first save carrying slides imports it as a deck (the file stays
        as the deck's source, like any hand-authored txt).
        """
        from pathlib import Path
        slides_dir = Path(__file__).resolve().parent.parent.parent / "data" / "slides"
        try:
            slides_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Could not create slides dir: {e}")
            return
        n = 0
        while True:
            name = "New Deck.txt" if n == 0 else f"New Deck {n + 1}.txt"
            path = slides_dir / name
            if not path.exists():
                break
            n += 1
        try:
            path.write_text(self._NEW_DECK_SKELETON, encoding="utf-8")
        except OSError as e:
            logger.error(f"Could not write new deck file: {e}")
            return
        key = str(path)
        self._new_deck_sessions[key] = os.path.getmtime(key)
        self._watcher.addPath(key)
        if not self._poll.isActive():
            self._poll.start()
        QDesktopServices.openUrl(QUrl.fromLocalFile(key))
        logger.info(f"New deck file opened: {key}")

    def _on_new_deck_file_changed(self, path: str):
        if path in self._new_deck_sessions:
            QTimer.singleShot(150, lambda: self._reload_new_deck_session(path))

    def _check_new_deck_sessions(self):
        """Stat open new-deck sessions (catches saves the watcher missed)."""
        for path in list(self._new_deck_sessions):
            self._reload_new_deck_session(path)

    def _reload_new_deck_session(self, path: str):
        if path not in self._new_deck_sessions:
            return
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            self._end_new_deck_session(path, delete_file=False)
            return
        if mtime == self._new_deck_sessions[path]:
            return
        self._new_deck_sessions[path] = mtime
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            logger.error(f"Could not read new deck file: {e}")
            return
        from core.slide_parser import parse_slide_txt
        from core.slide_service import import_txt
        if not parse_slide_txt(raw)["slides"]:
            return  # skeleton / wiped file — wait for real content
        try:
            imported = import_txt(path)
        except Exception as e:
            logger.error(f"Could not import new deck {path}: {e}")
            return
        self._end_new_deck_session(path, delete_file=False)
        self.refresh(keep_selection=False)
        if imported:
            new_id = imported[0]["id"]
            deck = next((d for d in self._decks if d["id"] == new_id), None)
            if deck is not None:
                self._select_deck(deck)  # emits → previews slide 0

    def _end_new_deck_session(self, path: str, delete_file: bool = False):
        if path not in self._new_deck_sessions:
            return
        del self._new_deck_sessions[path]
        try:
            self._watcher.removePath(path)
        except Exception:
            pass
        if delete_file:
            try:
                os.unlink(path)
            except OSError:
                pass
        if not self._edit_sessions and not self._new_deck_sessions:
            self._poll.stop()

    def _begin_edit_session(self, deck_id: int):
        from core.slide_service import get_deck
        from core.slide_parser import deck_to_txt
        deck = get_deck(deck_id)
        if not deck:
            return
        title = deck.get("title") or "song"
        slug = re.sub(r"[^\w\-]+", "_", title).strip("_")[:40] or "song"
        fd, path = tempfile.mkstemp(prefix=f"rhemacast_{deck_id}_{slug}_", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(deck_to_txt(deck.get("title") or "", deck.get("slides", []),
                                    deck.get("format")))
        except OSError as e:
            logger.error(f"Could not write edit temp file: {e}")
            return
        self._edit_sessions[deck_id] = {
            "path": path,
            "mtime": os.path.getmtime(path),
            "warned_empty": False,
        }
        self._watcher.addPath(path)
        if not self._poll.isActive():
            self._poll.start()
        QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        logger.info(f"Editing deck {deck_id} as text: {path}")

    def _on_watched_file_changed(self, path: str):
        deck_id = next((i for i, s in self._edit_sessions.items() if s["path"] == path), None)
        if deck_id is None:
            return
        # Debounce: editors often fire several change events per save;
        # the mtime check inside makes repeats no-ops.
        QTimer.singleShot(150, lambda: self._reload_edit_session(deck_id))

    def _check_edit_sessions(self):
        """Stat all open sessions (catches saves the watcher missed)."""
        for deck_id in list(self._edit_sessions):
            self._reload_edit_session(deck_id)

    def _reload_edit_session(self, deck_id: int):
        sess = self._edit_sessions.get(deck_id)
        if not sess:
            return
        try:
            mtime = os.path.getmtime(sess["path"])
        except OSError:
            # Temp file deleted externally → session over, keep the deck as-is.
            self._end_edit_session(deck_id, delete_file=False)
            return
        if mtime == sess["mtime"]:
            return
        sess["mtime"] = mtime
        try:
            with open(sess["path"], "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError as e:
            logger.error(f"Could not read edit temp file: {e}")
            return
        from core.slide_parser import parse_slide_txt
        from core.slide_service import update_deck
        if not parse_slide_txt(raw)["slides"]:
            if not sess["warned_empty"]:
                sess["warned_empty"] = True
                QMessageBox.warning(
                    self, "No Slides Found",
                    "The edited text contains no slides — keeping the previous version.\n"
                    "Add some lyric lines and save again.",
                )
            return
        sess["warned_empty"] = False
        updated = update_deck(deck_id, raw_text=raw)
        if updated is None:
            return
        # Atomic-save editors replace the file, which can drop the watch —
        # re-arm it so further saves keep working.
        if os.path.exists(sess["path"]) and sess["path"] not in self._watcher.files():
            self._watcher.addPath(sess["path"])
        self.refresh(keep_selection=True)
        self.deck_text_updated.emit(deck_id)
        logger.info(f"Deck {deck_id} reloaded from text edit")

    def _end_edit_session(self, deck_id: int, delete_file: bool = True):
        sess = self._edit_sessions.pop(deck_id, None)
        if not sess:
            return
        try:
            self._watcher.removePath(sess["path"])
        except Exception:
            pass
        if delete_file:
            try:
                os.unlink(sess["path"])
            except OSError:
                pass
        if not self._edit_sessions and not self._new_deck_sessions:
            self._poll.stop()
