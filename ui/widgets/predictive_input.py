"""
ui/widgets/predictive_input.py

Predictive Scripture Input: Book | Chapter | Verse
- Spacebar advances focus between sections.
- Backspace retreats to previous section if empty.
- Enter navigates the Bible browser to the reference.
- Numbering is a tandem: editing the book resets chapter+verse to 1, and
  editing the chapter resets verse to 1 — on the edit itself, not on the
  next Space/arrow commit.
- Chapter and verse share one width and centre their digits.
- Typing "1" instantly resolves to "1 Samuel" (first matching book).
- Invalid characters are silently ignored.
- Untyped suffix of the matched book name is highlighted (selected).
"""

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLineEdit, QLabel, QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal, QEvent, QTimer
from PyQt6.QtGui import QKeyEvent, QMouseEvent

from ui.styles import WHITE
from ui.tokens import ACCENT, BG_CARD, BG_CARD_HOVER, RADIUS_SM, TEXT_MUTED
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

    # Verified vocabulary; subclasses extend (e.g. testament filter).
    candidates = BIBLE_BOOKS
    # When False, Space/Right/Enter merely commit the autofill instead
    # of emitting navigation signals (filter-box behavior).
    navigate_on_commit = True

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
            if self.navigate_on_commit:
                if self.text().strip():
                    self.book_resolved.emit(self.text().strip())
                    self.advance_to_chapter.emit()
            else:
                # Filter-box mode: merely commit the autofill, no navigation.
                self.setCursorPosition(len(self.text()))
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
            if self.navigate_on_commit:
                if self.text().strip():
                    self.book_resolved.emit(self.text().strip())
                    self.push.emit()
                    self.clearFocus()
            else:
                # Filter-box mode: commit the autofill, keep focus for retyping.
                self.setCursorPosition(len(self.text()))
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
        """Find the first candidate matching the typed prefix (case-insensitive).

        Supports typed shortcuts like "1c" for "1 Chronicles" by also
        trying the prefix with a space after leading digits.
        """
        lower = prefix.strip().lower()
        if not lower:
            return None
        # Direct match
        for book in self.candidates:
            if book.lower().startswith(lower):
                return book
        # Try with space after leading digits (e.g., "1c" -> "1 c")
        if lower[0].isdigit():
            spaced = lower[0] + " " + lower[1:]
            for book in self.candidates:
                if book.lower().startswith(spaced):
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


# Extra verified terms accepted by the book filter (beyond BIBLE_BOOKS).
FILTER_TERMS = ["Old Testament", "New Testament", "Gospels"]

# Testament membership derived from canonical order (Genesis..Malachi | Matthew..Revelation).
OLD_TESTAMENT_BOOKS = frozenset(BIBLE_BOOKS[:39])
NEW_TESTAMENT_BOOKS = frozenset(BIBLE_BOOKS[39:])

# The four gospels.
GOSPELS_BOOKS = frozenset(["Matthew", "Mark", "Luke", "John"])


class BookFilterInput(BookInput):
    """Book/testament filter box: identical typing mechanics to BookInput
    (typed-buffer, verified-inputs-only, highlighted autofill, click-select-all)
    but Space/Right/Enter merely commit the autofill — no navigation signals.
    """

    candidates = BIBLE_BOOKS + FILTER_TERMS
    navigate_on_commit = False  # defense in depth; commit keys are intercepted above

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("Filter: book…")

    def _autosize(self):
        # Padded box style (unlike the navigator's borderless fields).
        text = self.text() or self.placeholderText()
        w = self.fontMetrics().horizontalAdvance(text) + 28
        self.setFixedWidth(max(w, 130))

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        if key in (
            Qt.Key.Key_Space,
            Qt.Key.Key_Right,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        ):
            # Preserve the "1/2/3 + Space inserts a space" rule for
            # numbered books ("1 Samuel"); otherwise commit, never navigate.
            if (
                key == Qt.Key.Key_Space
                and self._typed
                and self._typed[-1] in "123"
            ):
                super().keyPressEvent(event)
                return
            self._commit()
            return
        super().keyPressEvent(event)

    def _commit(self):
        self._typed = self.text()
        self.setCursorPosition(len(self.text()))

    def current_filter(self) -> str | None:
        """Resolved verified term (autofilled match) or None when empty/unmatched."""
        if not self._typed:
            return None
        match = self._find_match(self._typed)
        if match:
            return match
        shown = self.text().strip()
        for term in self.candidates:
            if term.lower() == shown.lower():
                return term
        return None

    def clear_filter(self):
        self._typed = ""
        self.clear()


class NumericInput(QLineEdit):
    """Numeric-only input for chapter or verse.

    Digits are centred: these fields hold one or two characters, and a
    left-aligned "1" in a 48px lane reads like an empty field. The lane
    width is owned by the parent navigator, so chapter and verse always
    come out the same size (see PredictiveScriptureInput._fit_numeric_fields).
    """

    advance = pyqtSignal()
    retreat = pyqtSignal()
    push = pyqtSignal()

    def __init__(self, placeholder: str, parent=None, max_value=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setTextMargins(0, 0, 0, 0)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._click_selected = False
        self._sel_start = 0
        self._max_value = max_value

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
        # Held while this widget itself rewrites the numbers (set_values,
        # reset, the renumber pass) so restoring a reference never counts
        # as the operator editing it.
        self._tandem_suppressed = False

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

        # Book — the tandem handler is connected BEFORE live navigation so
        # the numbers under the book are already 1 when this edit's single
        # navigation fires.
        self.book_input = BookInput()
        self.book_input.setStyleSheet(self._field_style())
        self.book_input.advance_to_chapter.connect(self._advance_to_chapter)
        self.book_input.push.connect(self._on_push)
        self.book_input.textChanged.connect(self._on_book_text_changed)
        self.book_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.book_input)

        layout.addSpacing(2)

        # Chapter — max validated against book
        self.chapter_input = NumericInput("Ch", max_value=self._chapter_max)
        self.chapter_input.setStyleSheet(self._field_style())
        self.chapter_input.advance.connect(self._advance_to_verse)
        self.chapter_input.push.connect(self._on_push)
        self.chapter_input.retreat.connect(self.book_input._on_focus_arrived)
        self.chapter_input.textChanged.connect(self._on_chapter_text_changed)
        self.chapter_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.chapter_input)

        layout.addSpacing(1)

        self._separator = QLabel(":")
        self._separator.setStyleSheet(self._separator_style())
        self._separator.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(self._separator)

        layout.addSpacing(2)

        # Verse — max validated against book:chapter. Same lane as the
        # chapter field (fitted together in _fit_numeric_fields), never
        # expanding, so the two read as one pair.
        self.verse_input = NumericInput("Vs", max_value=self._verse_max)
        self.verse_input.setStyleSheet(self._field_style())
        self.verse_input.advance.connect(self._on_navigate)
        self.verse_input.push.connect(self._on_push)
        self.verse_input.retreat.connect(self._retreat_to_chapter)
        self.verse_input.textChanged.connect(self._try_live_navigate)
        layout.addWidget(self.verse_input)

        # Every field is a fixed lane now, so any width this widget is
        # handed beyond its hint goes here instead of into the colon's
        # label box (which would push the ":" off centre).
        layout.addStretch(1)

        # Focus underline: a 2px strip painted inside the focused field's
        # rect. A QSS border would join the field's size hint and move the
        # text; this overlay cannot change either the rect or the text.
        self._fields = (self.book_input, self.chapter_input, self.verse_input)
        self._focus_underline = QFrame(self)
        self._focus_underline.setFixedHeight(2)
        self._focus_underline.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._focus_underline.setStyleSheet(
            f"background: {ACCENT}; border-radius: 1px;")
        self._focus_underline.hide()
        for field in self._fields:
            field.installEventFilter(self)

        # Widths were fitted with the app font before the group stylesheet
        # landed; refit so a saved size is not clipped on first paint.
        self.apply_fonts()

        # Settings → Interface: navigator text reads the "bible.verse"
        # group (family/weight/size are per-consumer defaults).
        from ui.app_theme import subscribe_interface_font_changed
        subscribe_interface_font_changed(self._on_interface_font_changed)

    # ── Settings-backed type ────────────────────────────────────────────────

    def _field_style(self) -> str:
        """Navigator field QSS — family/weight/size from "bible.verse".

        Unset keeps the navigator's own 13px / 600; a saved group value
        applies to all three fields.
        """
        from ui.app_theme import area_font, font_qss
        spec = area_font("bible.verse", 13, 600, size_min=8, size_max=16,
                         family_key="bible.verse_font_family",
                         weight_key="bible.verse_font_weight",
                         size_key="bible.verse_text_size")
        return f"""
            QLineEdit {{
                background: {BG_CARD};
                color: {WHITE};
                border: none;
                border-radius: {RADIUS_SM}px;
                {font_qss(spec)}
                padding: 0px;
                margin: 0px;
            }}
            QLineEdit:hover, QLineEdit:focus {{
                background: {BG_CARD_HOVER};
            }}
        """

    def _separator_style(self) -> str:
        """Colon separator — same group, 14px / 500 default."""
        from ui.app_theme import area_font, font_qss
        spec = area_font("bible.verse", 14, 500, size_min=8, size_max=16,
                         family_key="bible.verse_font_family",
                         weight_key="bible.verse_font_weight",
                         size_key="bible.verse_text_size")
        return (f"color: {TEXT_MUTED}; {font_qss(spec)} "
                "padding: 0px; margin: 0px;")

    def _on_interface_font_changed(self, prefix: str):
        if prefix == "bible.verse":
            self.apply_fonts()

    # ── Focus underline (overlay; never touches geometry or text) ──────────

    def eventFilter(self, obj, event):
        if obj in getattr(self, "_fields", ()) and event.type() in (
                QEvent.Type.FocusIn, QEvent.Type.FocusOut):
            if event.type() == QEvent.Type.FocusIn:
                self._place_underline(obj)
            else:
                # Focus may already be arriving at a sibling field; resolve
                # after Qt finishes the focus transition.
                QTimer.singleShot(0, self._sync_underline)
        return super().eventFilter(obj, event)

    def _sync_underline(self):
        focused = self.focusWidget()
        if focused in getattr(self, "_fields", ()):
            self._place_underline(focused)
        else:
            self._focus_underline.hide()

    def _place_underline(self, field):
        rect = field.geometry()
        self._focus_underline.setGeometry(
            rect.x() + 2, rect.y() + rect.height() - 2,
            max(0, rect.width() - 4), 2)
        self._focus_underline.show()
        self._focus_underline.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_focus_underline", None) is not None:
            self._sync_underline()

    def apply_fonts(self):
        """Push the "bible.verse" group onto the navigator without a rebuild."""
        for field in (self.book_input, self.chapter_input, self.verse_input):
            field.setStyleSheet(self._field_style())
            field.ensurePolished()
        self._separator.setStyleSheet(self._separator_style())
        self._separator.ensurePolished()
        # Book and the numeric pair are font-metric fitted — refit so a
        # larger saved size is not clipped.
        self.book_input._autosize()
        self._fit_numeric_fields()
        if getattr(self, "_focus_underline", None) is not None:
            self._sync_underline()

    # Chapter and verse read as one pair, so they get one width: fitted to
    # the widest reference either can carry ("176" — three digits) instead
    # of to the digits currently shown. A growing number therefore never
    # reflows the two fields mid-edit, and neither field can ever be a
    # different size from the other.
    _NUMERIC_WIDTH_SAMPLE = "000"
    _NUMERIC_WIDTH_PAD = 16      # matches the legacy autosize padding
    _NUMERIC_MIN_WIDTH = 48      # legacy lane; the app font lands here

    def _fit_numeric_fields(self):
        width = max(
            self._NUMERIC_MIN_WIDTH,
            self.chapter_input.fontMetrics()
            .horizontalAdvance(self._NUMERIC_WIDTH_SAMPLE)
            + self._NUMERIC_WIDTH_PAD,
        )
        self.chapter_input.setFixedWidth(width)
        self.verse_input.setFixedWidth(width)

    # ── Numbering tandem (book → chapter → verse) ───────────────────────────

    def _on_book_text_changed(self):
        if self._tandem_suppressed:
            return
        self._renumber(self.chapter_input, self.verse_input)

    def _on_chapter_text_changed(self):
        if self._tandem_suppressed:
            return
        self._renumber(self.verse_input)

    def _renumber(self, *fields):
        """Reset the fields after the edited one to 1, atomically.

        A reference reads left to right, so changing the book invalidates
        the chapter and the verse below it, and changing the chapter
        invalidates the verse. That happens on the edit itself — the
        operator no longer has to press Space or Right to see it.

        Live navigation is held for the duration, so one edit produces one
        navigation (fired by the edited field's own handler afterwards)
        rather than one per field that changed.
        """
        if all(field.text() == "1" for field in fields):
            return
        live_prev = self._live_nav_suppressed
        tandem_prev = self._tandem_suppressed
        self._live_nav_suppressed = True
        self._tandem_suppressed = True
        try:
            for field in fields:
                if field.text() != "1":
                    field.set_value(1)
        finally:
            self._live_nav_suppressed = live_prev
            self._tandem_suppressed = tandem_prev

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
        """Empty every field. An empty navigator has no numbering to fix,
        so the tandem rule is held off while clearing."""
        self._tandem_suppressed = True
        self._live_nav_suppressed = True
        try:
            self.book_input.reset()
            self.chapter_input.clear()
            self.verse_input.clear()
        finally:
            self._tandem_suppressed = False
            self._live_nav_suppressed = False
        self.book_input.setFocus()

    def set_values(self, book: str, chapter: int, verse: int):
        """
        Programmatically set all three fields without emitting navigate_requested.
        Used by BrowserPanel to reflect the currently highlighted verse.

        The tandem rule is held off: restoring a known reference must not
        rewrite the chapter/verse that came with it.
        """
        self._live_nav_suppressed = True
        self._tandem_suppressed = True
        try:
            self.book_input.set_value(book)
            self.chapter_input.set_value(chapter)
            self.verse_input.set_value(verse)
        finally:
            self._live_nav_suppressed = False
            self._tandem_suppressed = False

