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

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from ui.styles import WHITE, BLUE_500, SLATE_500, SLATE_950, BORDER_SUBTLE
from core.bible_service import get_chapter_count, get_verse_count

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
    push = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Book")
        self.setTextMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.textChanged.connect(self._autosize)
        self._typed = ""
        self._click_selected = False
        self._focus_arrived = False
        self._autosize()

    def _autosize(self):
        text = self.text() or self.placeholderText()
        w = self.fontMetrics().horizontalAdvance(text) + 2
        self.setFixedWidth(w)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.selectAll()
        self._click_selected = True
        self._focus_arrived = True

    def _on_focus_arrived(self):
        self.setFocus()
        self.selectAll()
        self._focus_arrived = True

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Space or key == Qt.Key.Key_Right:
            # In book input: if the last typed character is 1-3,
            # insert a space so the user can type "2 Chronicles", "3 John", etc.
            if self._typed and self._typed[-1] in "123":
                self._typed += " "
                self._update_prediction()
                return
            if self.text().strip():
                self.book_resolved.emit(self.text().strip())
                self.advance_to_chapter.emit()
            return

        if key == Qt.Key.Key_Backspace:
            if self._click_selected:
                self._click_selected = False
                return
            if self._typed:
                self._typed = self._typed[:-1]
                self._update_prediction()
            return

        if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            if self.text().strip():
                self.book_resolved.emit(self.text().strip())
                self.push.emit()
                self.clearFocus()
            return

        if key == Qt.Key.Key_Control or key == Qt.Key.Key_Shift or key == Qt.Key.Key_Alt:
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and text.lower() == "a":
            self.selectAll()
            return

        if not text or not (text.isalpha() or text.isdigit()):
            return

        if self._click_selected or self._focus_arrived:
            self._typed = ""
            self._click_selected = False
            self._focus_arrived = False

        candidate = self._typed + text
        match = self._find_match(candidate)
        if match:
            self._typed = candidate
            self.setText(match)
            self.setSelection(len(self._typed), len(match) - len(self._typed))

    def _find_match(self, prefix: str) -> str | None:
        """Find the first book matching the typed prefix (case-insensitive)."""
        lower = prefix.lower()
        for book in BIBLE_BOOKS:
            if book.lower().startswith(lower):
                return book
        return None

    def _update_prediction(self):
        if not self._typed:
            self.selectAll()
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

    def set_value(self, text: str):
        """Programmatically set the book name (no signals emitted)."""
        self._typed = text
        self.setText(text)


class NumericInput(QLineEdit):
    """Simple numeric-only input for chapter or verse."""

    advance = pyqtSignal()
    retreat = pyqtSignal()
    push = pyqtSignal()

    def __init__(self, placeholder: str, parent=None, auto_size=True, max_value=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setTextMargins(0, 0, 0, 0)
        self._click_selected = False
        self._sel_start = 0
        self._max_value = max_value
        if auto_size:
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.textChanged.connect(self._autosize)
            self._autosize()

    def _autosize(self):
        text = self.text() or self.placeholderText()
        w = self.fontMetrics().horizontalAdvance(text) + 2
        self.setFixedWidth(w)

    def _sync_selection(self):
        if self.text() and self._sel_start < len(self.text()):
            self.setSelection(self._sel_start, len(self.text()) - self._sel_start)

    def mousePressEvent(self, event: QMouseEvent):
        super().mousePressEvent(event)
        self.selectAll()
        self._click_selected = True
        self._sel_start = 0

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        text = event.text()

        if key == Qt.Key.Key_Space or key == Qt.Key.Key_Right:
            self.advance.emit()
            return

        if key == Qt.Key.Key_Left:
            self.retreat.emit()
            return

        if key == Qt.Key.Key_Backspace:
            if self._click_selected:
                self._click_selected = False
                if self.text():
                    self.setText("1")
                    self._sel_start = 0
                    self.retreat.emit()
                else:
                    self.retreat.emit()
                return
            if not self.text():
                self.retreat.emit()
                return
            if self._sel_start > 0:
                self._sel_start -= 1
                self._sync_selection()
            elif self._sel_start == 0:
                self.setText("1")
                self._sel_start = 0
                self.retreat.emit()
            return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.push.emit()
            self.clearFocus()
            return

        if key == Qt.Key.Key_Control or key == Qt.Key.Key_Shift or key == Qt.Key.Key_Alt:
            return

        if event.modifiers() & Qt.KeyboardModifier.ControlModifier and text.lower() == "a":
            self.selectAll()
            return

        if text and text.isdigit():
            if self._max_value is not None:
                max_val = self._max_value() if callable(self._max_value) else self._max_value
                if max_val is not None:
                    if self._sel_start < len(self.text()):
                        candidate = text
                    else:
                        candidate = self.text() + text
                    if int(candidate) > max_val:
                        return
            super().keyPressEvent(event)
            self._sel_start = len(self.text())

    def set_value(self, value: int):
        """Programmatically set the numeric value (no signals emitted)."""
        self.setText(str(value))
        self._sel_start = len(self.text())


class PredictiveScriptureInput(QWidget):
    """
    Composite input: Book | Chapter | Verse
    Emits `navigate_requested` with (book, chapter, verse).
    """

    navigate_requested = pyqtSignal(str, int, int)
    push_requested = pyqtSignal(str, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._translation = "KJV"
        self._live_nav_suppressed = False

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
                padding: 0px;
                margin: 0px;
            }}
        """
        separator_style = f"color: {SLATE_500}; font-size: 14px; font-weight: 300; padding: 0px; margin: 0px;"

        # Book
        self.book_input = BookInput()
        self.book_input.setStyleSheet(field_style)
        self.book_input.advance_to_chapter.connect(self._advance_to_chapter)
        self.book_input.push.connect(self._on_push)
        self.book_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.book_input)

        layout.addSpacing(2)

        # Chapter — max validated against book
        self.chapter_input = NumericInput("Ch", max_value=self._chapter_max)
        self.chapter_input.setStyleSheet(field_style)
        self.chapter_input.advance.connect(self._advance_to_verse)
        self.chapter_input.push.connect(self._on_push)
        self.chapter_input.retreat.connect(self.book_input._on_focus_arrived)
        self.chapter_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.chapter_input)

        layout.addSpacing(1)

        sep2 = QLabel(":")
        sep2.setStyleSheet(separator_style)
        layout.addWidget(sep2)

        layout.addSpacing(2)

        # Verse — max validated against book:chapter
        self.verse_input = NumericInput("Vs", auto_size=False, max_value=self._verse_max)
        self.verse_input.setStyleSheet(field_style)
        self.verse_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.verse_input.advance.connect(self._on_navigate)
        self.verse_input.push.connect(self._on_push)
        self.verse_input.retreat.connect(self._retreat_to_chapter)
        self.verse_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.verse_input)

    def _chapter_max(self):
        book = self.book_input.text().strip()
        if not book:
            return None
        return get_chapter_count(self._translation, book) or None

    def _verse_max(self):
        book = self.book_input.text().strip()
        chapter = self.chapter_input.text().strip()
        if not book or not chapter:
            return None
        return get_verse_count(self._translation, book, int(chapter)) or None

    def _advance_to_chapter(self):
        self.chapter_input.set_value(1)
        self.chapter_input._sel_start = 0
        self.verse_input.set_value(1)
        self.verse_input._sel_start = 0
        self.chapter_input.setFocus()
        self.chapter_input.selectAll()

    def _advance_to_verse(self):
        self.verse_input.set_value(1)
        self.verse_input._sel_start = 0
        self.verse_input.setFocus()
        self.verse_input.selectAll()

    def _retreat_to_chapter(self):
        self.chapter_input.setFocus()
        self.chapter_input.selectAll()
        self.chapter_input._click_selected = True

    def set_translation(self, translation: str):
        self._translation = translation

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

    def _on_push(self):
        book = self.book_input.text().strip()
        chapter = self.chapter_input.text().strip()
        verse = self.verse_input.text().strip()

        if book and chapter:
            self.push_requested.emit(
                book,
                int(chapter) if chapter else 1,
                int(verse) if verse else 1
            )

    def _try_live_navigate(self):
        if self._live_nav_suppressed:
            return
        book = self.book_input.text().strip()
        chapter = self.chapter_input.text().strip()
        verse = self.verse_input.text().strip()

        if book and book in BIBLE_BOOKS and chapter:
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

    def set_values(self, book: str, chapter: int, verse: int):
        """
        Programmatically set all three fields without emitting navigate_requested.
        Used by BrowserPanel to reflect the currently highlighted verse.
        """
        self._live_nav_suppressed = True
        self.book_input.set_value(book)
        self.chapter_input.set_value(chapter)
        self.verse_input.set_value(verse)
        self._live_nav_suppressed = False
