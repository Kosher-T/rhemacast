"""
ui/tabs/library_tab.py

Library tab — Bible Version Manager.
Displays installed translations as cards, with options to import or browse more versions.
"""

import logging

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QFrame, QGridLayout, QSizePolicy, QSplitter
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_950, SLATE_900, SLATE_800, SLATE_700, SLATE_600,
    SLATE_500, SLATE_400, SLATE_300, WHITE,
    BLUE_500, BLUE_400, EMERALD_500, EMERALD_400,
    BORDER_SUBTLE, BORDER_LIGHT
)

logger = logging.getLogger(__name__)

# ─── Bible version metadata ───────────────────────────────────────────────────

_STANDARD_VERSIONS = {"AMP", "BSB", "ESV", "KJV", "NIV", "NKJV", "NLT"}

_VERSION_META = {
    "KJV":  {"full": "King James Version",          "desc": "Public Domain. Full archaic index.",         "color": SLATE_700,  "abbr": "Kj"},
    "NKJV": {"full": "New King James Version",      "desc": "Modernized KJV language.",                   "color": BLUE_500,   "abbr": "Kj"},
    "NIV":  {"full": "New International Version",    "desc": "Full access (OT/NT).",                      "color": "#f59e0b",  "abbr": "N'"},
    "ESV":  {"full": "English Standard Version",     "desc": "Word-for-word accuracy.",                    "color": EMERALD_500,"abbr": "E'"},
    "NLT":  {"full": "New Living Translation",       "desc": "Thought-for-thought readability.",           "color": "#8b5cf6",  "abbr": "nL"},
    "AMP":  {"full": "Amplified Bible",              "desc": "Expanded meaning of original text.",         "color": "#ec4899",  "abbr": "M"},
    "BSB":  {"full": "Berean Standard Bible",        "desc": "Literal, fair-equality renderings.",         "color": "#06b6d4",  "abbr": "BS"},
    "BIBLE_ENGLISH_MSG": {"full": "The Message",     "desc": "Paraphrase by Eugene Peterson.",            "color": "#64748b",  "abbr": "I S"},
    "MSG":  {"full": "The Message",                  "desc": "Paraphrase by Eugene Peterson.",             "color": "#64748b",  "abbr": "I S"},
    "TPT":  {"full": "The Passion Translation",      "desc": "",                                           "color": "#475569",  "abbr": "P'"},
    "ERV":  {"full": "Easy-to-Read Version",         "desc": "",                                           "color": "#64748b",  "abbr": "R'"},
}


# ─── Sidebar ──────────────────────────────────────────────────────────────────

class _SideBarItem(QPushButton):
    """Clickable sidebar row."""

    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setFixedHeight(32)
        self.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_400};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                text-align: left;
                font-size: 12px;
                font-weight: 500;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.05);
                color: {SLATE_300};
            }}
            QPushButton:disabled {{
                color: {SLATE_600};
            }}
        """)


class _Sidebar(QWidget):
    """Left sidebar with section headers and items."""

    filter_changed = pyqtSignal(str)  # "all", "standard", "custom"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(140)
        self.setMaximumWidth(240)
        self.setStyleSheet(f"""
            QWidget {{
                background: {SLATE_900};
                border-right: 1px solid {BORDER_SUBTLE};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 0)
        layout.setSpacing(2)

        header = QLabel("RESOURCES")
        header.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; font-weight: 700; letter-spacing: 1px; padding-left: 4px;")
        layout.addWidget(header)
        layout.addSpacing(6)

        self.btn_bibles = _SideBarItem("\U0001f4d6  Bibles")
        self.btn_bibles.clicked.connect(lambda: self.filter_changed.emit("all"))
        self.btn_bibles.setStyleSheet(f"""
            QPushButton {{
                background: rgba(59, 130, 246, 0.15);
                color: {WHITE};
                border: none;
                border-radius: 6px;
                padding: 4px 12px;
                text-align: left;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        layout.addWidget(self.btn_bibles)

        sub = QVBoxLayout()
        sub.setContentsMargins(24, 2, 0, 0)
        sub.setSpacing(2)
        self.btn_standard = _SideBarItem("Standard Versions")
        self.btn_custom = _SideBarItem("Custom Imports")
        self.btn_standard.clicked.connect(lambda: self.filter_changed.emit("standard"))
        self.btn_custom.clicked.connect(lambda: self.filter_changed.emit("custom"))
        sub.addWidget(self.btn_standard)
        sub.addWidget(self.btn_custom)
        layout.addLayout(sub)

        layout.addSpacing(6)
        self.btn_songs = _SideBarItem("\U0001f3b5  Songs")
        self.btn_songs.setEnabled(False)
        layout.addWidget(self.btn_songs)

        self.btn_media = _SideBarItem("\U0001f3ac  Media")
        self.btn_media.setEnabled(False)
        layout.addWidget(self.btn_media)

        layout.addStretch()

    def set_counts(self, standard: int, custom: int):
        """Update sidebar item labels with counts."""
        self.btn_standard.setText(f"Standard Versions  ({standard})")
        self.btn_custom.setText(f"Custom Imports  ({custom})")


# ─── Version Card ─────────────────────────────────────────────────────────────

class _VersionCard(QFrame):
    """Card showing an installed Bible version."""

    def __init__(self, version: str, parent=None):
        super().__init__(parent)
        from core.bible_service import get_display_name
        display = get_display_name(version)
        meta = _VERSION_META.get(version, {})
        full_name = meta.get("full", display)
        desc = meta.get("desc", "")
        color = meta.get("color", SLATE_700)
        abbr = meta.get("abbr", display[:2] if len(display) >= 2 else display)

        self.setFixedHeight(88)
        self.setStyleSheet(f"""
            QFrame {{
                background: {SLATE_800};
                border: none;
                border-radius: 8px;
            }}
            QFrame:hover {{
                background: {SLATE_700};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(14)

        badge = QLabel(abbr)
        badge.setFixedSize(48, 48)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(f"""
            background: {color};
            color: {WHITE};
            border-radius: 10px;
            font-size: 14px;
            font-weight: 800;
        """)
        layout.addWidget(badge)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        name_label = QLabel(full_name)
        name_label.setStyleSheet(f"color: {WHITE}; font-size: 13px; font-weight: 700; background: transparent;")
        text_col.addWidget(name_label)

        if desc:
            desc_label = QLabel(desc)
            desc_label.setStyleSheet(f"color: {SLATE_400}; font-size: 11px; background: transparent;")
            text_col.addWidget(desc_label)

        text_col.addStretch()
        layout.addLayout(text_col, 1)

        status = QLabel("INSTALLED")
        status.setStyleSheet(f"""
            color: {EMERALD_400};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 0.5px;
            background: transparent;
        """)
        layout.addWidget(status, 0, Qt.AlignmentFlag.AlignTop)


class _BrowseMoreCard(QFrame):
    """Clickable card to browse or import more Bible versions."""

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: 2px dashed {SLATE_600};
                border-radius: 8px;
            }}
            QFrame:hover {{
                border-color: {BLUE_400};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(2)

        icon = QLabel("+")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet(f"color: {SLATE_500}; font-size: 18px; background: transparent; border: none;")
        layout.addWidget(icon)

        text = QLabel("Browse 200+ other versions")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setStyleSheet(f"color: {SLATE_400}; font-size: 10px; background: transparent; border: none;")
        layout.addWidget(text)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ─── Bible Version Manager (main content) ─────────────────────────────────────

class _BibleVersionManager(QWidget):
    """Main content area showing installed Bible versions as cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")
        self._all_cards: list[_VersionCard] = []
        self._current_filter = "all"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 12, 24, 12)
        layout.setSpacing(10)

        # ── Header row ──
        header_row = QHBoxLayout()
        header_col = QVBoxLayout()
        title = QLabel("Bible Version Manager")
        title.setStyleSheet(f"color: {WHITE}; font-size: 22px; font-weight: 700;")
        header_col.addWidget(title)
        subtitle = QLabel("CONFIGURE AND DOWNLOAD SCRIPTURE DATABASES")
        subtitle.setStyleSheet(f"color: {SLATE_500}; font-size: 10px; font-weight: 600; letter-spacing: 0.8px;")
        header_col.addWidget(subtitle)
        header_row.addLayout(header_col)
        header_row.addStretch()
        layout.addLayout(header_row)

        # ── Version grid ──
        self._grid_widget = QWidget()
        self._grid_widget.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(self._grid_widget)
        self._grid.setSpacing(4)
        self._grid.setContentsMargins(0, 0, 0, 0)
        for c in range(5):
            self._grid.setColumnStretch(c, 1)

        from core.bible_service import get_available_translations
        installed = get_available_translations()

        self._standard = sorted(v for v in installed if v in _STANDARD_VERSIONS)
        self._custom = sorted(v for v in installed if v not in _STANDARD_VERSIONS)

        self._build_grid(installed)

        self._grid_widget.setLayout(self._grid)
        self._grid_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._grid_widget)
        layout.addStretch()

    def _build_grid(self, versions: list, show_browse: bool = True):
        """Rebuild the grid with the given version list."""
        # Clear existing cards
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        col = 0
        row = 0
        for ver in versions:
            card = _VersionCard(ver)
            self._grid.addWidget(card, row, col)
            col += 1
            if col >= 5:
                col = 0
                row += 1

        if show_browse:
            browse_card = _BrowseMoreCard()
            browse_card.clicked.connect(self._on_browse_more)
            self._grid.addWidget(browse_card, row, col)

        # Resize grid widget to fit content
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, self._adjust_grid_height)

    def _adjust_grid_height(self):
        """Set grid widget height to match its content."""
        hints = []
        for i in range(self._grid.count()):
            item = self._grid.itemAt(i)
            if item.widget():
                hints.append(item.widget().sizeHint().height())
        if hints:
            rows = max(1, (len(hints) + 4) // 5)
            total_h = sum(hints[:5]) + (rows - 1) * self._grid.spacing()
            self._grid_widget.setFixedHeight(total_h)

    def apply_filter(self, filter_type: str):
        """Filter cards by standard/custom/all."""
        self._current_filter = filter_type
        if filter_type == "standard":
            self._build_grid(self._standard, show_browse=False)
        elif filter_type == "custom":
            self._build_grid(self._custom, show_browse=True)
        else:
            from core.bible_service import get_available_translations
            self._build_grid(get_available_translations(), show_browse=True)

    def _on_browse_more(self):
        from ui.dialogs.add_translation_dialog import AddTranslationDialog
        from core.bible_service import (
            import_translation_file, refresh_available_translations, get_display_name
        )
        dialog = AddTranslationDialog(self)
        if dialog.exec() == AddTranslationDialog.DialogCode.Accepted:
            path = dialog.selected_path()
            if not path:
                return
            try:
                version = import_translation_file(path)
                refresh_available_translations()

                # Add translation button to the browser panel (same as "+ Add")
                main_win = self.window()
                if hasattr(main_win, '_tabs'):
                    pres_tab = main_win._tabs.get("PRESENTATION")
                    if pres_tab and hasattr(pres_tab, 'browser_panel'):
                        bp = pres_tab.browser_panel
                        if hasattr(bp, '_add_translation_button'):
                            bp._add_translation_button(version)

                # Hot-refresh the grid to show the new card
                self._refresh_grid()
            except Exception as e:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.critical(
                    self, "Import Failed",
                    f"Could not import the file:\n\n{e}",
                )

    def _refresh_grid(self):
        """Re-fetch installed translations and rebuild the grid."""
        from core.bible_service import get_available_translations
        installed = get_available_translations()
        self._standard = sorted(v for v in installed if v in _STANDARD_VERSIONS)
        self._custom = sorted(v for v in installed if v not in _STANDARD_VERSIONS)
        if self._current_filter == "standard":
            self._build_grid(self._standard, show_browse=False)
        elif self._current_filter == "custom":
            self._build_grid(self._custom, show_browse=True)
        else:
            self._build_grid(installed, show_browse=True)


# ─── Library Tab (top-level) ──────────────────────────────────────────────────

class LibraryTab(QWidget):
    """Library tab with toolbar, sidebar, and Bible Version Manager content."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"background: {SLATE_950};")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Top toolbar ──
        toolbar = QWidget()
        toolbar.setFixedHeight(36)
        toolbar.setStyleSheet(f"""
            QWidget {{
                background: {SLATE_900};
                border-bottom: 1px solid {BORDER_SUBTLE};
            }}
        """)
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(16)

        for text, active in (("Bible Versions", True), ("Songs", False), ("Media", False)):
            btn = QPushButton(text)
            if active:
                btn.setStyleSheet(f"color: {WHITE}; background: transparent; border: none; font-size: 11px; font-weight: 700; border-bottom: 2px solid {BLUE_500}; padding-bottom: 4px;")
            else:
                btn.setStyleSheet(f"color: {SLATE_500}; background: transparent; border: none; font-size: 11px; font-weight: 500;")
                btn.setEnabled(False)
            tb_layout.addWidget(btn)

        tb_layout.addStretch()
        root.addWidget(toolbar)

        # ── Body (resizable sidebar + content) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background: {BORDER_SUBTLE};
            }}
            QSplitter::handle:hover {{
                background: {SLATE_600};
            }}
        """)

        self._sidebar = _Sidebar()
        self._content = _BibleVersionManager()

        # Update sidebar counts
        self._sidebar.set_counts(
            len(self._content._standard),
            len(self._content._custom),
        )

        # Wire sidebar filter
        self._sidebar.filter_changed.connect(self._content.apply_filter)

        splitter.addWidget(self._sidebar)
        splitter.addWidget(self._content)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([160, 1000])

        root.addWidget(splitter)
