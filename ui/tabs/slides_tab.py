"""
ui/tabs/slides_tab.py

SLIDES tab — songs / freeform slide decks.
Left: deck list with search + import/delete. Right: ordered slide preview
rendered with the hardcoded "default" theme (Lite Designer comes later).
"""

import logging
import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSplitter, QLineEdit, QFileDialog,
    QMessageBox, QSizePolicy, QGridLayout,
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_950, SLATE_900, SLATE_800, SLATE_700, SLATE_600,
    SLATE_500, SLATE_400, SLATE_300, WHITE,
    BLUE_500, BLUE_400, RED_500,
    BORDER_SUBTLE, BORDER_LIGHT,
)

logger = logging.getLogger(__name__)

_PREVIEW_THEME_NAME = "default"


def _parse_px(value: str | None, default: float) -> float:
    """Parse '44px' → 44.0, falling back to default."""
    try:
        return float(str(value).strip().rstrip("px"))
    except (TypeError, ValueError):
        return default


class _DeckCard(QFrame):
    """Clickable card for one slide deck."""

    clicked = pyqtSignal(int)  # deck_id

    def __init__(self, deck: dict, parent=None):
        super().__init__(parent)
        self.deck_id = deck["id"]
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(64)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        title = deck.get("title") or "(untitled)"
        name_label = QLabel(title)
        name_label.setStyleSheet(
            f"color: {WHITE}; font-size: 13px; font-weight: 700; background: transparent;"
        )
        name_label.setWordWrap(False)
        text_col.addWidget(name_label)

        updated = (deck.get("updated_at") or "")[:10]
        meta = QLabel(f"{deck.get('slide_count', 0)} slides  ·  {updated}")
        meta.setStyleSheet(
            f"color: {SLATE_400}; font-size: 10px; background: transparent;"
        )
        text_col.addWidget(meta)
        text_col.addStretch()

        layout.addLayout(text_col, 1)
        self._apply_style()

    def _apply_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: rgba(59, 130, 246, 0.18);
                    border: 1px solid {BLUE_500};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {SLATE_800};
                    border: 1px solid transparent;
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    background: {SLATE_700};
                }}
            """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.deck_id)
        super().mousePressEvent(event)


class _SlideCard(QFrame):
    """One previewed slide — section label + text, themed like the display."""

    clicked = pyqtSignal()  # emits with no args; index bound by caller

    def __init__(self, index: int, section: str | None, text: str, theme: dict, parent=None):
        super().__init__(parent)
        self._index = index
        self.setFixedSize(340, 191)  # 16:9
        self.setStyleSheet(f"""
            QFrame {{
                background: #000000;
                border: 1px solid {BORDER_LIGHT};
                border-radius: 6px;
            }}
        """)

        t = theme.get("text", {})
        r = theme.get("reference", {})

        text_color = t.get("color", "#ffffff")
        font_family = t.get("font_family", "'Nunito', sans-serif")
        weight = int(t.get("weight", 700))
        size_px = max(11.0, _parse_px(t.get("size"), 44) * 0.30)
        line_height = float(t.get("line_height", 1.2))
        letter_spacing = t.get("letter_spacing", "-0.02em")

        ref_color = r.get("color", "#cccccc")
        ref_size = max(8.0, _parse_px(r.get("size"), 34) * 0.22)
        ref_transform = r.get("text_transform", "uppercase").lower()
        ref_spacing = r.get("letter_spacing", "0.1em")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        idx_label = QLabel(str(index + 1))
        idx_label.setStyleSheet(
            f"color: {SLATE_600}; font-size: 9px; font-weight: 700; background: transparent;"
        )
        top_row.addWidget(idx_label)
        top_row.addStretch()
        layout.addLayout(top_row)

        layout.addStretch()

        if section:
            sec_label = QLabel(section.upper() if ref_transform == "uppercase" else section)
            sec_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sec_label.setWordWrap(True)
            sec_label.setStyleSheet(f"""
                color: {ref_color};
                font-size: {ref_size:.0f}px;
                font-weight: 600;
                letter-spacing: {ref_spacing};
                background: transparent;
            """)
            layout.addWidget(sec_label)

        body = QLabel()
        body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        body.setWordWrap(True)
        from core.slide_parser import has_inline_markup, inline_markup_to_html
        if has_inline_markup(text):
            # Rich text so inline [words: (#hex)] colors show in preview
            body.setTextFormat(Qt.TextFormat.RichText)
            body.setText(inline_markup_to_html(text))
        else:
            body.setText(text)
        body.setStyleSheet(f"""
            color: {text_color};
            font-family: {font_family};
            font-size: {size_px:.0f}px;
            font-weight: {weight};
            line-height: {line_height};
            letter-spacing: {letter_spacing};
            background: transparent;
        """)
        layout.addWidget(body)

        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SlidesTab(QWidget):
    """SLIDES tab — deck management + preview."""

    deck_to_schedule = pyqtSignal(dict)       # full deck dict
    slide_live_requested = pyqtSignal(int, int)      # deck_id, slide_index
    slide_preview_requested = pyqtSignal(int, int)   # deck_id, slide_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._decks: list[dict] = []
        self._cards: dict[int, _DeckCard] = {}
        self._current_deck: dict | None = None
        self._selected_slide_idx: int | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ──
        toolbar = QWidget()
        toolbar.setFixedHeight(48)
        toolbar.setStyleSheet(f"""
            QWidget {{
                background: {SLATE_900};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(16, 0, 16, 0)
        tb.setSpacing(10)

        header_col = QVBoxLayout()
        header_col.setSpacing(0)
        title = QLabel("Slides")
        title.setStyleSheet(f"color: {WHITE}; font-size: 15px; font-weight: 800;")
        header_col.addWidget(title)
        subtitle = QLabel("SONGS · ANNOUNCEMENTS · FREEFORM")
        subtitle.setStyleSheet(
            f"color: {SLATE_500}; font-size: 8px; font-weight: 700; letter-spacing: 1px;"
        )
        header_col.addWidget(subtitle)
        tb.addLayout(header_col)

        tb.addSpacing(16)

        self.btn_import = QPushButton("Import .txt")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self._on_import)
        tb.addWidget(self.btn_import)

        self.btn_import_ew = QPushButton("Import EasyWorship")
        self.btn_import_ew.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import_ew.setToolTip("Import songs from an EasyWorship v6 Data folder (containing Songs.db)")
        self.btn_import_ew.clicked.connect(self._on_import_easyworship)
        tb.addWidget(self.btn_import_ew)

        self.btn_schedule = QPushButton("+ Schedule")
        self.btn_schedule.setEnabled(False)
        self.btn_schedule.setToolTip("Add the selected deck to the service schedule")
        self.btn_schedule.clicked.connect(self._on_add_to_schedule)
        tb.addWidget(self.btn_schedule)

        self.btn_live = QPushButton("Go Live")
        self.btn_live.setEnabled(False)
        self.btn_live.setToolTip("Push the selected slide to the live output")
        self.btn_live.clicked.connect(self._on_go_live)
        tb.addWidget(self.btn_live)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setEnabled(False)
        self.btn_delete.clicked.connect(self._on_delete)
        tb.addWidget(self.btn_delete)

        tb.addStretch()

        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Search title or lyrics…")
        self.search_box.setFixedWidth(260)
        self.search_box.textChanged.connect(self._on_search)
        tb.addWidget(self.search_box)

        root.addWidget(toolbar)

        # ── Body ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"QSplitter::handle {{ background: {BORDER_SUBTLE}; }}")

        # Left: deck list
        left_panel = QWidget()
        left_panel.setStyleSheet(f"background: {SLATE_950};")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 0, 8)
        left_layout.setSpacing(6)

        self.deck_scroll = QScrollArea()
        self.deck_scroll.setWidgetResizable(True)
        self.deck_scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
        """)
        self.deck_list_container = QWidget()
        self.deck_list_container.setStyleSheet("background: transparent;")
        self.deck_list_layout = QVBoxLayout(self.deck_list_container)
        self.deck_list_layout.setContentsMargins(0, 0, 0, 0)
        self.deck_list_layout.setSpacing(6)
        self.deck_list_layout.addStretch()
        self.deck_scroll.setWidget(self.deck_list_container)

        left_layout.addWidget(self.deck_scroll)
        splitter.addWidget(left_panel)

        # Right: slide preview
        right_panel = QWidget()
        right_panel.setStyleSheet(f"background: {SLATE_950};")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(8, 8, 8, 8)
        right_layout.setSpacing(6)

        self.preview_title = QLabel("Select a deck to preview")
        self.preview_title.setStyleSheet(
            f"color: {SLATE_400}; font-size: 11px; font-weight: 700;"
        )
        right_layout.addWidget(self.preview_title)

        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.preview_container = QWidget()
        self.preview_container.setStyleSheet("background: transparent;")
        self.preview_grid = QGridLayout(self.preview_container)
        self.preview_grid.setContentsMargins(0, 0, 0, 0)
        self.preview_grid.setSpacing(10)
        self.preview_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.preview_scroll.setWidget(self.preview_container)
        right_layout.addWidget(self.preview_scroll, 1)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])

        root.addWidget(splitter, 1)

        self.refresh()

    # ── Data ────────────────────────────────────────────────────────────────

    def refresh(self, keep_selection: bool = True):
        """Reload decks from the service, preserving selection when possible."""
        from core.slide_service import list_decks
        selected_id = self._current_deck["id"] if keep_selection and self._current_deck else None
        self._decks = list_decks()
        self._populate_deck_list(selected_id)

    def _populate_deck_list(self, selected_id: int | None = None):
        while self.deck_list_layout.count() > 1:
            item = self.deck_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()

        if not self._decks:
            empty = QLabel("No decks yet.\nImport a .txt file to begin.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {SLATE_600}; font-size: 11px; background: transparent; padding-top: 24px;"
            )
            self.deck_list_layout.insertWidget(0, empty)
        else:
            for deck in self._decks:
                card = _DeckCard(deck)
                card.clicked.connect(self._on_deck_clicked)
                self.deck_list_layout.insertWidget(self.deck_list_layout.count() - 1, card)
                self._cards[deck["id"]] = card
                if selected_id is not None and deck["id"] == selected_id:
                    self._select_deck(deck, scroll=False)

        if selected_id is None or not any(d["id"] == selected_id for d in self._decks):
            self._current_deck = None
            self._selected_slide_idx = None
            self.btn_delete.setEnabled(False)
            self.btn_schedule.setEnabled(False)
            self.btn_live.setEnabled(False)
            self.preview_title.setText("Select a deck to preview")
            self._clear_preview()

    def _select_deck(self, deck: dict, scroll: bool = False):
        self._current_deck = deck
        self._selected_slide_idx = None
        self.btn_live.setEnabled(False)
        self.btn_schedule.setEnabled(True)
        for did, card in self._cards.items():
            card.set_selected(did == deck["id"])
        self.btn_delete.setEnabled(True)
        label = deck.get("title") or "(untitled)"
        self.preview_title.setText(f"{label}  ·  {deck['slide_count']} slides")
        self._render_preview(deck)
        if scroll:
            card = self._cards.get(deck["id"])
            if card:
                self.deck_scroll.ensureWidgetVisible(card)

    def _clear_preview(self):
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def _render_preview(self, deck: dict):
        from core.theme_loader import get_theme
        try:
            theme = get_theme(_PREVIEW_THEME_NAME)
        except Exception as e:
            logger.warning(f"Theme '{_PREVIEW_THEME_NAME}' unavailable ({e}); using bare styling")
            theme = {}

        self._clear_preview()
        cols = 2
        for i, slide in enumerate(deck.get("slides", [])):
            card = _SlideCard(i, slide.get("section"), slide.get("text", ""), theme)
            card.setCursor(Qt.CursorShape.PointingHandCursor)
            card.clicked.connect(lambda idx=i: self._on_slide_card_clicked(idx))
            self.preview_grid.addWidget(card, i // cols, i % cols)

    def _on_slide_card_clicked(self, index: int):
        """Select a slide card; single-click previews it, Go Live becomes armed."""
        self._selected_slide_idx = index
        # Highlight selected card
        for i in range(self.preview_grid.count()):
            w = self.preview_grid.itemAt(i).widget()
            if w:
                border = f"2px solid {BLUE_500}" if i == index else f"1px solid {BORDER_LIGHT}"
                w.setStyleSheet(f"""
                    QFrame {{
                        background: #000000;
                        border: {border};
                        border-radius: 6px;
                    }}
                """)
        self.btn_live.setEnabled(True)
        if self._current_deck:
            self.slide_preview_requested.emit(self._current_deck["id"], index)

    def _on_add_to_schedule(self):
        if self._current_deck:
            self.deck_to_schedule.emit(dict(self._current_deck))

    def _on_go_live(self):
        if not self._current_deck:
            return
        idx = self._selected_slide_idx if self._selected_slide_idx is not None else 0
        self.slide_live_requested.emit(self._current_deck["id"], idx)

    # ── Actions ─────────────────────────────────────────────────────────────

    def _on_deck_clicked(self, deck_id: int):
        deck = next((d for d in self._decks if d["id"] == deck_id), None)
        if deck:
            self._select_deck(deck, scroll=False)

    def _on_search(self, text: str):
        from core.slide_service import list_decks, search_decks
        query = text.strip()
        self._decks = search_decks(query) if query else list_decks()
        self._populate_deck_list(selected_id=None)

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
                deck = import_txt(path)
                imported.append(deck)
            except Exception as e:
                logger.error(f"Failed to import {path}: {e}")
                failed.append((path, str(e)))
        self.refresh(keep_selection=False)
        if failed:
            detail = "\n\n".join(f"{p}\n{err}" for p, err in failed)
            QMessageBox.warning(self, "Import Failed", f"Some files could not be imported:\n\n{detail}")

    def _on_import_easyworship(self):
        """Import songs from an EasyWorship v6 Data directory (Songs.db + SongWords.db)."""
        from PyQt6.QtWidgets import QApplication
        data_dir = QFileDialog.getExistingDirectory(
            self,
            "Select EasyWorship Data folder",
            "",
            QFileDialog.Option.ShowDirsOnly,
        )
        if not data_dir:
            return

        if not os.path.isfile(os.path.join(data_dir, "Songs.db")):
            QMessageBox.warning(
                self,
                "EasyWorship Import",
                f"No Songs.db found in:\n{data_dir}\n\n"
                "Select the folder that contains Songs.db and SongWords.db "
                "(e.g. EasyWorship/Default/v6.1/Databases/Data).",
            )
            return

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            from core.easyworship_import import import_easyworship
            result = import_easyworship(data_dir=data_dir)
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
            self,
            "Delete Deck",
            f"Delete \"{deck.get('title') or '(untitled)'}\"?\nThis cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        from core.slide_service import delete_deck
        delete_deck(deck["id"])
        self._current_deck = None
        self.refresh(keep_selection=False)
