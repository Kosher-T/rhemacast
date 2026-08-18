"""
ui/tabs/history_tab.py

Sermon Archive Browser — History tab.
Displays past sermon sessions with categorized insights,
natural language search, and archive statistics.
"""

import logging
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QLineEdit, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal

from ui.styles import (
    SLATE_950, SLATE_900, SLATE_800, SLATE_700, SLATE_600,
    SLATE_500, SLATE_400, SLATE_300, WHITE, BORDER_SUBTLE,
    BLUE_500, BLUE_400, CYAN_400, EMERALD_500, EMERALD_400,
    AMBER_500, RED_500, PANEL_BG
)

logger = logging.getLogger(__name__)

# ── Category badge colors ──
CATEGORY_COLORS = {
    "Prophecy": EMERALD_500,
    "Declaration": BLUE_500,
    "Prayer Point": AMBER_500,
    "Main Scripture": EMERALD_400,
}

# ── Styles ──
_SIDEBAR_STYLE = f"""
    QWidget {{
        background: rgba(15, 23, 42, 60);
        border-right: 1px solid {BORDER_SUBTLE};
    }}
"""

_SIDEBAR_ITEM_STYLE = f"""
    QPushButton {{
        background: transparent;
        color: {SLATE_400};
        border: none;
        border-radius: 6px;
        padding: 10px 16px;
        text-align: left;
        font-size: 13px;
        font-weight: 500;
    }}
    QPushButton:hover {{
        background: rgba(255, 255, 255, 0.04);
        color: {WHITE};
    }}
    QPushButton[active="true"] {{
        background: rgba(37, 99, 235, 0.15);
        color: {WHITE};
        font-weight: 600;
    }}
"""

_SIDEBAR_HEADER_STYLE = f"""
    color: {SLATE_500};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 0 16px 8px 16px;
"""

_SEARCH_INPUT_STYLE = f"""
    QLineEdit {{
        background: rgba(30, 41, 59, 0.5);
        color: {SLATE_300};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 12px 16px 12px 40px;
        font-size: 14px;
        selection-background-color: rgba(59, 130, 246, 0.3);
    }}
    QLineEdit:focus {{
        border-color: rgba(59, 130, 246, 0.4);
    }}
    QLineEdit::placeholder {{
        color: {SLATE_600};
    }}
"""

_ESC_BADGE_STYLE = f"""
    background: rgba(30, 41, 59, 0.6);
    color: {SLATE_500};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 10px;
    font-weight: 600;
"""

_AI_BADGE_STYLE = f"""
    color: {CYAN_400};
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
"""

_DATE_HEADER_STYLE = f"""
    color: {SLATE_400};
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    padding: 8px 0;
"""

_INSIGHT_CARD_STYLE = f"""
    QFrame {{
        background: rgba(30, 41, 59, 0.35);
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
    }}
    QFrame:hover {{
        border-color: rgba(255, 255, 255, 0.08);
        background: rgba(30, 41, 59, 0.5);
    }}
"""

_STATS_PANEL_STYLE = f"""
    QFrame {{
        background: rgba(15, 23, 42, 80);
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
    }}
"""

_STATS_LABEL_STYLE = f"""
    color: {SLATE_500};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
"""

_STATS_VALUE_STYLE = f"""
    color: {WHITE};
    font-size: 18px;
    font-weight: 700;
"""


class InsightCard(QFrame):
    """A single insight card (prophecy, declaration, prayer point, scripture)."""

    def __init__(self, category: str, text: str, speaker: str = "",
                 time_str: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(_INSIGHT_CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── Top row: badge + time ──
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        badge = QLabel(category.upper())
        badge_color = CATEGORY_COLORS.get(category, SLATE_500)
        badge.setStyleSheet(f"""
            color: {badge_color};
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        badge.setFixedHeight(22)
        top_row.addWidget(badge)
        top_row.addStretch()

        if time_str:
            time_label = QLabel(time_str)
            time_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
            top_row.addWidget(time_label)

        layout.addLayout(top_row)

        # ── Quote text ──
        quote = QLabel(f'\u201c{text}\u201d')
        quote.setWordWrap(True)
        quote.setStyleSheet(f"""
            color: {SLATE_300};
            font-size: 13px;
            line-height: 1.5;
            padding: 2px 0;
        """)
        layout.addWidget(quote)

        # ── Bottom row: speaker + action ──
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)

        if speaker:
            speaker_label = QLabel(speaker)
            speaker_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
            bottom_row.addWidget(speaker_label)

        bottom_row.addStretch()

        action_btn = QPushButton()
        action_btn.setFixedSize(28, 28)
        action_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_500};
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.06);
                color: {SLATE_300};
            }}
        """)
        action_btn.setText("\u2197")  # northeast arrow
        action_btn.setToolTip("Open in context")
        bottom_row.addWidget(action_btn)

        layout.addLayout(bottom_row)


class ScriptureCard(QFrame):
    """A main scripture card with verse reference and text."""

    def __init__(self, reference: str, text: str, time_str: str = "",
                 parent=None):
        super().__init__(parent)
        self.setStyleSheet(_INSIGHT_CARD_STYLE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        # ── Top row: badge + time ──
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        badge = QLabel("MAIN SCRIPTURE")
        badge.setStyleSheet(f"""
            color: {EMERALD_400};
            background: rgba(30, 41, 59, 0.8);
            border: 1px solid rgba(255, 255, 255, 0.06);
            border-radius: 4px;
            padding: 3px 10px;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 0.5px;
        """)
        badge.setFixedHeight(22)
        top_row.addWidget(badge)
        top_row.addStretch()

        if time_str:
            time_label = QLabel(time_str)
            time_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
            top_row.addWidget(time_label)

        layout.addLayout(top_row)

        # ── Reference block ──
        ref_frame = QFrame()
        ref_frame.setStyleSheet(f"""
            QFrame {{
                background: rgba(16, 185, 129, 0.08);
                border-radius: 6px;
                padding: 8px 12px;
            }}
        """)
        ref_layout = QHBoxLayout(ref_frame)
        ref_layout.setContentsMargins(12, 8, 12, 8)
        ref_layout.setSpacing(12)

        # Book abbreviation circle
        abbrev = reference.split()[0][:3].upper() if reference else "REF"
        circle = QLabel(abbrev)
        circle.setFixedSize(36, 36)
        circle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        circle.setStyleSheet(f"""
            background: rgba(16, 185, 129, 0.2);
            color: {EMERALD_400};
            border-radius: 18px;
            font-size: 11px;
            font-weight: 700;
        """)
        ref_layout.addWidget(circle)

        ref_text_layout = QVBoxLayout()
        ref_text_layout.setSpacing(2)

        ref_title = QLabel(reference)
        ref_title.setStyleSheet(f"color: {WHITE}; font-size: 14px; font-weight: 700;")
        ref_text_layout.addWidget(ref_title)

        if text:
            ref_body = QLabel(text)
            ref_body.setWordWrap(True)
            ref_body.setStyleSheet(f"color: {SLATE_400}; font-size: 11px;")
            ref_text_layout.addWidget(ref_body)

        ref_layout.addLayout(ref_text_layout)
        layout.addWidget(ref_frame)

        # ── Bottom row: anchored label + action ──
        bottom_row = QHBoxLayout()

        anchored = QLabel("ANCHORED SEGMENT")
        anchored.setStyleSheet(f"""
            color: {SLATE_600};
            font-size: 9px;
            font-weight: 700;
            letter-spacing: 1px;
        """)
        bottom_row.addWidget(anchored)
        bottom_row.addStretch()

        action_btn = QPushButton()
        action_btn.setFixedSize(28, 28)
        action_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {SLATE_500};
                border: none;
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background: rgba(255, 255, 255, 0.06);
                color: {SLATE_300};
            }}
        """)
        action_btn.setText("\u2398")  # copy icon
        action_btn.setToolTip("Copy verse")
        bottom_row.addWidget(action_btn)

        layout.addLayout(bottom_row)


class HistoryTab(QWidget):
    """Sermon Archive Browser — History tab."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_category = "All Insights"

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Left sidebar ──
        root.addWidget(self._create_sidebar())

        # ── Main content ──
        root.addWidget(self._create_content(), 1)

        # Load data
        self._load_sessions()

    def _create_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(_SIDEBAR_STYLE)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setSpacing(2)

        header = QLabel("INSIGHT CATEGORIES")
        header.setStyleSheet(_SIDEBAR_HEADER_STYLE)
        layout.addWidget(header)

        self._category_buttons = {}
        categories = [
            ("All Insights", "\u2606"),   # star
            ("Prophecies", "\u2605"),     # filled star
            ("Declarations", "\u25C6"),   # diamond
            ("Prayer Points", "\u271A"),  # cross
            ("Main Scriptures", "\u2710"), # pen
        ]

        for name, icon in categories:
            btn = QPushButton(f"  {icon}  {name}")
            btn.setStyleSheet(_SIDEBAR_ITEM_STYLE)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, n=name: self._select_category(n))
            layout.addWidget(btn)
            self._category_buttons[name] = btn

        layout.addStretch()

        # ── Archive stats ──
        stats_frame = QFrame()
        stats_frame.setStyleSheet(_STATS_PANEL_STYLE)
        stats_layout = QVBoxLayout(stats_frame)
        stats_layout.setContentsMargins(16, 14, 16, 14)
        stats_layout.setSpacing(10)

        stats_title = QLabel("ARCHIVE STATS")
        stats_title.setStyleSheet(_STATS_LABEL_STYLE)
        stats_layout.addWidget(stats_title)

        self._total_services = QLabel("0")
        self._total_services.setStyleSheet(_STATS_VALUE_STYLE)
        stats_layout.addWidget(self._total_services)

        services_label = QLabel("Total Services")
        services_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        stats_layout.addWidget(services_label)

        stats_layout.addSpacing(4)

        self._total_insights = QLabel("0")
        self._total_insights.setStyleSheet(_STATS_VALUE_STYLE)
        stats_layout.addWidget(self._total_insights)

        insights_label = QLabel("Total Insights")
        insights_label.setStyleSheet(f"color: {SLATE_500}; font-size: 11px;")
        stats_layout.addWidget(insights_label)

        layout.addWidget(stats_frame)

        return sidebar

    def _create_content(self) -> QWidget:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(24, 16, 24, 16)
        layout.setSpacing(0)

        # ── Search bar ──
        search_row = QHBoxLayout()
        search_row.setSpacing(12)

        search_container = QWidget()
        search_container.setStyleSheet(f"background: transparent;")
        search_layout = QHBoxLayout(search_container)
        search_layout.setContentsMargins(0, 0, 0, 0)
        search_layout.setSpacing(0)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(
            "Search insights using natural language (e.g., 'fire outbreak', 'divine provision')..."
        )
        self._search_input.setStyleSheet(_SEARCH_INPUT_STYLE)
        self._search_input.setFixedHeight(44)
        self._search_input.textChanged.connect(self._on_search)
        search_layout.addWidget(self._search_input)

        esc_badge = QLabel("ESC to clear")
        esc_badge.setStyleSheet(_ESC_BADGE_STYLE)
        search_layout.addWidget(esc_badge, 0, Qt.AlignmentFlag.AlignRight)

        search_row.addWidget(search_container, 1)
        layout.addLayout(search_row)

        # ── AI badge ──
        ai_row = QHBoxLayout()
        ai_row.setContentsMargins(0, 8, 0, 12)

        sparkle = QLabel("\u2728")
        sparkle.setStyleSheet(f"font-size: 12px;")
        ai_row.addWidget(sparkle)

        ai_text = QLabel("AI-ENHANCED SEMANTIC SEARCH ACTIVE")
        ai_text.setStyleSheet(_AI_BADGE_STYLE)
        ai_row.addWidget(ai_text)

        ai_row.addStretch()
        layout.addLayout(ai_row)

        # ── Scrollable content area ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255, 255, 255, 0.08);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255, 255, 255, 0.15);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
        """)

        self._cards_container = QWidget()
        self._cards_layout = QVBoxLayout(self._cards_container)
        self._cards_layout.setContentsMargins(0, 0, 0, 0)
        self._cards_layout.setSpacing(0)
        self._cards_layout.addStretch()

        scroll.setWidget(self._cards_container)
        layout.addWidget(scroll, 1)

        return content

    def _select_category(self, name: str):
        self._active_category = name
        for cat_name, btn in self._category_buttons.items():
            btn.setProperty("active", cat_name == name)
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._filter_cards()

    def _on_search(self, text: str):
        self._filter_cards()

    def _filter_cards(self):
        search = self._search_input.text().strip().lower()
        category = self._active_category

        for i in range(self._cards_layout.count()):
            item = self._cards_layout.itemAt(i)
            if item and item.widget():
                widget = item.widget()
                if hasattr(widget, '_category') and hasattr(widget, '_text'):
                    matches_cat = (category == "All Insights" or
                                   widget._category == category.rstrip("s"))
                    matches_search = (not search or
                                      search in widget._text.lower())
                    widget.setVisible(matches_cat and matches_search)

    def _load_sessions(self):
        """Load sermon sessions from the database and display as insight cards."""
        try:
            from core.database import get_open_sessions, stitch_transcript, get_connection

            sessions = get_open_sessions()
            if not sessions:
                self._show_empty_state()
                return

            self._total_services.setText(str(len(sessions)))

            total_insights = 0

            conn = get_connection()
            for session_id in sessions:
                # Get session start time
                row = conn.execute(
                    "SELECT start_time FROM sessions WHERE session_id = ?",
                    (session_id,)
                ).fetchone()
                if not row:
                    continue

                dt = datetime.fromtimestamp(row["start_time"] / 1000)
                date_str = dt.strftime("%A, %B %d, %Y").upper()

                # Get display events for this session
                events = conn.execute(
                    """SELECT action, ref, text, translation, theme, timestamp_ms
                       FROM display_events
                       WHERE session_id = ?
                       ORDER BY timestamp_ms ASC""",
                    (session_id,)
                ).fetchall()

                # Get transcript text
                transcript = stitch_transcript(session_id)

                # Add date header
                self._add_date_header(date_str)

                # Add display events as insight cards
                for ev in events:
                    ref, text = ev["ref"], ev["text"]
                    ts = ev["timestamp_ms"]
                    if not ref and not text:
                        continue

                    time_str = datetime.fromtimestamp(ts / 1000).strftime("%I:%M %p")

                    if ref and text:
                        # Scripture display event → Main Scripture card
                        card = ScriptureCard(
                            reference=ref,
                            text=text[:120] + ("..." if len(text) > 120 else ""),
                            time_str=time_str,
                        )
                        card._category = "Main Scripture"
                        card._text = f"{ref} {text}"
                        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
                        total_insights += 1

                # Add transcript excerpt if available
                if transcript and len(transcript) > 50:
                    words = transcript.split()
                    for chunk_start in range(0, min(len(words), 200), 40):
                        chunk = " ".join(words[chunk_start:chunk_start + 40])
                        if len(chunk) < 20:
                            continue

                        category = self._categorize_text(chunk)

                        card = InsightCard(
                            category=category,
                            text=chunk[:200],
                            speaker="Transcript",
                            time_str="",
                        )
                        card._category = category
                        card._text = chunk.lower()
                        self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
                        total_insights += 1

            conn.close()
            self._total_insights.setText(str(total_insights))

        except Exception as e:
            logger.error(f"Failed to load history sessions: {e}")
            self._show_empty_state()

    def _categorize_text(self, text: str) -> str:
        """Simple heuristic categorization of transcript text."""
        lower = text.lower()
        if any(w in lower for w in ["pray", "prayer", "lord", "father god"]):
            return "Prayer Point"
        if any(w in lower for w in ["declare", "decree", "proclaim"]):
            return "Declaration"
        if any(w in lower for w in ["prophesy", "prophet", "thus says", "the lord says"]):
            return "Prophecy"
        if any(w in lower for w in ["scripture", "verse", "chapter", "book of"]):
            return "Main Scripture"
        return "Declaration"

    def _add_date_header(self, date_str: str):
        label = QLabel(date_str)
        label.setStyleSheet(_DATE_HEADER_STYLE)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, label)

    def _show_empty_state(self):
        self._total_services.setText("0")
        self._total_insights.setText("0")

        empty = QLabel("No sermon sessions recorded yet.\nStart a transcription session to begin building your archive.")
        empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty.setStyleSheet(f"""
            color: {SLATE_500};
            font-size: 14px;
            padding: 60px 40px;
            line-height: 1.6;
        """)
        self._cards_layout.insertWidget(self._cards_layout.count() - 1, empty)
