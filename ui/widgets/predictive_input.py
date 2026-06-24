"""
ui/widgets/predictive_input.py

Predictive Scripture Input: Book | Chapter | Verse
- Spacebar advances focus between sections.
- Backspace retreats to previous section if empty.
- Enter navigates the Bible browser to the reference.
- Typing "1" instantly resolves to "1 Samuel" (first matching book).
- Invalid characters are silently ignored.
- Untyped suffix of the matched book name is highlighted (selected).
"""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent

from ui.styles import WHITE, BLUE_500, SLATE_500, SLATE_950, BORDER_SUBTLE

# Canonical book ordering
BIBLE_BOOKS = [
    "Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy",
    "Joshua", "Judges", "Ruth", "1 Samuel", "2 Samuel",
    "1 Kings", "2 Kings", "1 Chronicles", "2 Chronicles",
    "Ezra", "Nehemiah", "Esther", "Job", "Psalms", "Proverbs",
    "Ecclesiastes", "Song of Solomon", "Isaiah", "Jeremiah",
    "Lamentations", "Ezekiel", "Daniel", "Hosea", "Joel", "Amos",
    "Obadiah", "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah",
    "Haggai", "Zechariah", "Malachi",
    "Matthew", "Mark", "Luke", "John", "Acts", "Romans",
    "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
    "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
    "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews",
    "James", "1 Peter", "2 Peter", "1 John", "2 John", "3 John",
    "Jude", "Revelation"
]


class BookInput(QLineEdit):
    """Custom line edit for book name with predictive completion."""

    advance_to_chapter = pyqtSignal()
    book_resolved = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Book")
        self._typed = ""

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Space:
            # Advance to chapter section
            if self.text().strip():
                self.book_resolved.emit(self.text().strip())
                self.advance_to_chapter.emit()
            return

        if key == Qt.Key.Key_Backspace:
            if self._typed:
                self._typed = self._typed[:-1]
                self._update_prediction()
            return

        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if self.text().strip():
                self.book_resolved.emit(self.text().strip())
                self.advance_to_chapter.emit()
            return

        # Accept alphanumeric characters only
        if not text or not (text.isalpha() or text.isdigit()):
            return

        # Attempt to match
        candidate = self._typed + text
        match = self._find_match(candidate)
        if match:
            self._typed = candidate
            self.setText(match)
            # Select the untyped suffix
            self.setSelection(len(self._typed), len(match) - len(self._typed))
        # else: silently ignore invalid character

    def _find_match(self, prefix: str) -> str | None:
        """Find the first book matching the typed prefix (case-insensitive)."""
        lower = prefix.lower()
        for book in BIBLE_BOOKS:
            if book.lower().startswith(lower):
                return book
        return None

    def _update_prediction(self):
        if not self._typed:
            self.clear()
            return
        match = self._find_match(self._typed)
        if match:
            self.setText(match)
            self.setSelection(len(self._typed), len(match) - len(self._typed))
        else:
            self.setText(self._typed)

    def reset(self):
        self._typed = ""
        self.clear()


class NumericInput(QLineEdit):
    """Simple numeric-only input for chapter or verse."""

    advance = pyqtSignal()
    retreat = pyqtSignal()

    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMaximumWidth(60)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Space:
            if self.text().strip():
                self.advance.emit()
            return

        if key == Qt.Key.Key_Backspace:
            if not self.text():
                self.retreat.emit()
                return
            super().keyPressEvent(event)
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.advance.emit()
            return

        # Only accept digits
        if text and text.isdigit():
            super().keyPressEvent(event)
        # else: silently ignore


class PredictiveScriptureInput(QWidget):
    """
    Composite input: Book | Chapter | Verse
    Emits `navigate_requested` with (book, chapter, verse).
    """

    navigate_requested = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName("PredictiveContainer")
        self.setStyleSheet(f"""
            QWidget#PredictiveContainer {{
                background: transparent;
                border: none;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        field_style = f"""
            QLineEdit {{
                background: transparent;
                color: {WHITE};
                border: none;
                font-size: 12px;
                font-weight: 600;
                padding: 4px;
            }}
        """
        separator_style = f"color: {SLATE_500}; font-size: 14px; font-weight: 300; padding: 0 2px;"

        # Book
        self.book_input = BookInput()
        self.book_input.setStyleSheet(field_style)
        self.book_input.advance_to_chapter.connect(lambda: self.chapter_input.setFocus())
        layout.addWidget(self.book_input, 3)

        sep1 = QLabel("|")
        sep1.setStyleSheet(separator_style)
        layout.addWidget(sep1)

        # Chapter
        self.chapter_input = NumericInput("Ch")
        self.chapter_input.setStyleSheet(field_style)
        self.chapter_input.advance.connect(lambda: self.verse_input.setFocus())
        self.chapter_input.retreat.connect(lambda: self.book_input.setFocus())
        layout.addWidget(self.chapter_input, 1)

        sep2 = QLabel(":")
        sep2.setStyleSheet(separator_style)
        layout.addWidget(sep2)

        # Verse
        self.verse_input = NumericInput("Vs")
        self.verse_input.setStyleSheet(field_style)
        self.verse_input.advance.connect(self._on_navigate)
        self.verse_input.retreat.connect(lambda: self.chapter_input.setFocus())
        layout.addWidget(self.verse_input, 1)

    def _on_navigate(self):
        book = self.book_input.text().strip()
        chapter = self.chapter_input.text().strip()
        verse = self.verse_input.text().strip()

        if book and chapter:
            self.navigate_requested.emit(
                book,
                int(chapter) if chapter else 1,
                int(verse) if verse else 1
            )

    def reset(self):
        self.book_input.reset()
        self.chapter_input.clear()
        self.verse_input.clear()
        self.book_input.setFocus()
