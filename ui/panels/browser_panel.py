"""
ui/panels/browser_panel.py

Manual navigation panel: Bible browser with translation bar.
Implements single-click (browse) and double-click (broadcast) on translations.
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QFrame, QScrollArea, QStackedWidget
)
from PyQt6.QtGui import QIcon, QWheelEvent
from PyQt6.QtCore import Qt, pyqtSignal, QSize

from ui.styles import (
    PANEL_BODY_STYLE, SLATE_300, SLATE_500, BLUE_500,
    TRANSLATION_BTN_INACTIVE, TRANSLATION_BTN_ACTIVE,
    VERSE_EVEN_BG, VERSE_ODD_BG, VERSE_SELECTED_BG, VERSE_HOVER_BG,
    BORDER_SUBTLE, SLATE_950, WHITE
)
from ui.widgets.predictive_input import PredictiveScriptureInput


class _HScrollArea(QScrollArea):
    """QScrollArea that converts vertical wheel/trackpad scroll into horizontal scroll."""

    def wheelEvent(self, event: QWheelEvent):
        delta = event.angleDelta()
        h_bar = self.horizontalScrollBar()

        if delta.y() != 0:
            # Mouse wheel vertical → scroll horizontally
            h_bar.setValue(h_bar.value() - delta.y())
            event.accept()
        elif delta.x() != 0:
            # Trackpad two-finger horizontal swipe
            h_bar.setValue(h_bar.value() - delta.x())
            event.accept()
        else:
            super().wheelEvent(event)


class VerseRow(QFrame):
    """A single verse row in the Bible browser."""

    clicked = pyqtSignal(dict)
    double_clicked = pyqtSignal(dict)

    def __init__(self, chapter: int, verse: int, text: str, is_even: bool, parent=None):
        super().__init__(parent)
        self.verse_data = {"chapter": chapter, "verse": verse, "text": text}
        self._selected = False

        bg = VERSE_EVEN_BG if is_even else VERSE_ODD_BG
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: none;
                border-left: 2px solid transparent;
                padding: 6px 8px;
            }}
            QFrame:hover {{
                background: {VERSE_HOVER_BG};
            }}
        """)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        ref_label = QLabel(f"{chapter}:{verse}")
        ref_label.setStyleSheet(f"color: {BLUE_500}; font-size: 10px; font-weight: 700; min-width: 32px;")
        layout.addWidget(ref_label)

        text_label = QLabel(text)
        text_label.setStyleSheet(f"color: {SLATE_300}; font-size: 12px; line-height: 1.5;")
        text_label.setWordWrap(True)
        layout.addWidget(text_label, 1)

    def mousePressEvent(self, event):
        self.clicked.emit(self.verse_data)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.double_clicked.emit(self.verse_data)
        super().mouseDoubleClickEvent(event)

    def set_selected(self, selected: bool):
        self._selected = selected
        if selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {VERSE_SELECTED_BG};
                    border: none;
                    border-left: 2px solid {BLUE_500};
                    padding: 6px 8px;
                }}
            """)


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


class BrowserPanel(QWidget):
    """Manual Bible navigation panel with translation bar."""

    # Emitted when operator double-clicks a translation
    broadcast_in_version = pyqtSignal(str)

    def __init__(self, translations: list = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(PANEL_BODY_STYLE)
        self._current_translation = "NIV"
        self._selected_verse = None
        self._translation_buttons: dict[str, TranslationButton] = {}

        if translations is None:
            translations = [
                "AMP", "ESV", "KJV", "NIV", "NKJV", "NLT", "MSG", "NASB",
                "ASV", "BBE", "CSB", "CEV", "GNV", "GW", "HCSB", "ICB", 
                "ISV", "LEB", "MEV", "NET", "RSV", "WEB", "YLT"
            ]

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
        toolbar_layout.addWidget(add_btn)

        # Nav input container (bg-black/40 px-2 py-1 gap-2 border-l border-white/10)
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
        
        # Stacked widget to switch between Predictive Input and Natural Language Search
        self.nav_stack = QStackedWidget()
        
        # Mode 0: Predictive Input
        self.predictive_input = PredictiveScriptureInput()
        self.predictive_input.setStyleSheet("background: transparent; border: none;") # Override floating pill styles
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
        self.nav_stack.addWidget(self.search_input)
        
        nav_layout.addWidget(self.nav_stack, 1)

        nav_container.setFixedWidth(300)
        toolbar_layout.addWidget(nav_container)

        layout.addWidget(toolbar)

        # ── Verse Display Area ──
        self.verse_list = QListWidget()
        self.verse_list.setSpacing(0)
        self.verse_list.setStyleSheet(f"""
            QListWidget {{
                background: rgba(0, 0, 0, 50);
                padding: 4px;
            }}
        """)
        layout.addWidget(self.verse_list)

    def load_verses(self, verses: list):
        """Load a list of verse dicts into the browser display."""
        self.verse_list.clear()
        for i, v in enumerate(verses):
            row = VerseRow(v["chapter"], v["verse"], v["text"], i % 2 == 0)
            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.verse_list.addItem(item)
            self.verse_list.setItemWidget(item, row)

    def _on_translation_single_click(self, abbrev: str):
        """Switch browse view to that version (no broadcast)."""
        for name, btn in self._translation_buttons.items():
            btn.set_active(name == abbrev)
        self._current_translation = abbrev

    def _on_translation_double_click(self, abbrev: str):
        """Broadcast currently-selected verse in that version."""
        self.broadcast_in_version.emit(abbrev)

    def _toggle_nav_mode(self):
        """Switch between Predictive Scripture Nav and Natural Language Search."""
        current_idx = self.nav_stack.currentIndex()
        if current_idx == 0:
            # Switch to search
            self.nav_stack.setCurrentIndex(1)
            self.mode_toggle_btn.setIcon(self._icon_book)
            self.mode_toggle_btn.setToolTip("Switch to Book/Chapter/Verse navigation")
            self.search_input.setFocus()
        else:
            # Switch to predictive
            self.nav_stack.setCurrentIndex(0)
            self.mode_toggle_btn.setIcon(self._icon_search)
            self.mode_toggle_btn.setToolTip("Switch to Natural Language Search")
            self.predictive_input.reset()
