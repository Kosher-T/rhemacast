"""
ui/widgets/text_nav.py

Shared editing gestures for every textbox in the app (the full contract
is specified in docs/slide-cards.md under "Editing behavior
specification"). Dependency-free apart from Qt: slide_cards.py imports
the pure kernels from here (never the reverse).

Contents:
- Pure string kernels: `word_end_right_stop`, `word_span_at`.
- `_LineEditNav` / `install_line_edit_nav`: word gestures for QLineEdit.
  focus-select-all, triple-click-select-all, single-line paste, and
  ShortcutOverride claims so app shortcuts never fire mid-edit.
"""

import time
import unicodedata

from PyQt6.QtWidgets import QApplication, QLineEdit
from PyQt6.QtCore import Qt, QPoint, QEvent, QObject
from PyQt6.QtGui import QTextCursor


def _is_punctuation(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P")


_APOSTROPHES = frozenset({"'", "’"})


def _is_word_char(ch: str) -> bool:
    return ch == "_" or ch.isalnum()


def word_end_right_stop(text: str, offset: int):
    """End-of-word stop for Ctrl+Right / Ctrl+Delete, block-local.

    Only a punctuation cluster immediately ahead is special (consume it,
    stop before a following space). Letters, spaces, block ends,
    newlines and exotic classes return None: Qt default handles those
    (Ctrl+Left/Right space behavior stays native everywhere).
    """
    n = len(text)
    if offset >= n or not _is_punctuation(text[offset]):
        return None
    i = offset
    while i < n and _is_punctuation(text[i]):
        i += 1
    return i


def word_span_at(text: str, pos: int):
    """Double-click word span: letters/digits/underscore with internal
    apostrophes for contractions ("don't" is one word). Leading and
    trailing quotes are excluded. None when not on word characters
    (Qt default applies)."""
    n = len(text)
    on_word = pos < n and _is_word_char(text[pos])
    linked = (
        pos < n and text[pos] in _APOSTROPHES
        and ((pos > 0 and _is_word_char(text[pos - 1]))
             or (pos + 1 < n and _is_word_char(text[pos + 1])))
        or pos > 0 and pos <= n and text[pos - 1] in _APOSTROPHES
        and pos > 1 and _is_word_char(text[pos - 2]))
    if not (on_word or linked):
        return None
    start, end = pos, pos
    while True:
        while start > 0 and _is_word_char(text[start - 1]):
            start -= 1
        if start > 1 and text[start - 1] in _APOSTROPHES \
                and _is_word_char(text[start - 2]):
            start -= 1
            continue
        break
    while True:
        while end < n and _is_word_char(text[end]):
            end += 1
        if end + 1 < n and text[end] in _APOSTROPHES \
                and _is_word_char(text[end + 1]):
            end += 1
            continue
        break
    if start == end:
        return None
    return start, end


_SEP = chr(0x2029)
_NL = chr(0x2029)  # block separator as reported by QTextDocument
_WORD_ONLY = None  # compiled lazily (re import cost only when used)


def _char_at(doc, pos: int) -> str:
    """Character at a document position (characterAt returns str)."""
    return doc.characterAt(pos)


def _word_only_pattern():
    global _WORD_ONLY
    if _WORD_ONLY is None:
        import re
        _WORD_ONLY = re.compile(r"[\w'\u2019]+", re.UNICODE)
    return _WORD_ONLY


def smart_delete_extend(doc, start, end, forward: bool):
    """Extend a selection for smart Delete/Backspace, or None for default.

    - Spans block boundaries, or covers exactly one whole block
      (triple-click shape): Delete eats one following newline, Backspace
      eats one preceding newline when present.
    - Exactly one word (letters/digits/underscore, internal apostrophes):
      Delete eats one following space, Backspace one preceding space.
      Anything else adjacent (punctuation, newline, doc edge): word only.
    The caller then falls through to default deletion (uniform undo).
    """
    if start == end:
        return None
    if start > end:
        start, end = end, start
    last = doc.characterCount() - 1
    cur = QTextCursor(doc)
    cur.setPosition(start)
    cur.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    sel = cur.selectedText()
    if _SEP in sel:
        if forward:
            if end < last and _char_at(doc, end) == _NL:
                end += 1
        elif start > 0 and _char_at(doc, start - 1) == _NL:
            start -= 1
        return start, end
    block = doc.findBlock(start)
    if start == block.position() \
            and end == block.position() + len(block.text()):
        if forward:
            if end < last and _char_at(doc, end) == _NL:
                end += 1
        elif start > 0 and _char_at(doc, start - 1) == _NL:
            start -= 1
        return start, end
    if _word_only_pattern().fullmatch(sel):
        if forward:
            if end < last and _char_at(doc, end) == " ":
                end += 1
        elif start > 0 and _char_at(doc, start - 1) == " ":
            start -= 1
        return start, end
    return None


class _LineEditNav(QObject):
    """Word gestures for a QLineEdit. Installed once per field; every
    other key and mouse event falls through to Qt untouched."""

    def __init__(self, edit: QLineEdit):
        super().__init__(edit)
        self._edit = edit
        edit.installEventFilter(self)
        self._count = 0
        self._at = 0.0
        self._pos = None

    def _press(self, pos) -> int:
        now = time.monotonic()
        if self._count > 0 and self._pos is not None \
                and (now - self._at) * 1000.0 \
                <= QApplication.doubleClickInterval() \
                and (pos - self._pos).manhattanLength() \
                <= QApplication.startDragDistance():
            self._count += 1
        else:
            self._count = 1
        self._at = now
        self._pos = QPoint(pos)
        if self._count >= 3:
            self._count = 0
            return 3
        return self._count

    def eventFilter(self, obj, event):
        if obj is not self._edit:
            return False
        etype = event.type()
        if etype == QEvent.Type.FocusIn:
            # Arriving at a non-empty box selects what is in it. Driven by
            # FocusIn alone, so it fires once per focus acquisition and
            # never on a click inside an already-focused box — which is
            # what used to make the highlight toggle on every click.
            # selectAll() on an empty box is a no-op, so no special case.
            self._edit.selectAll()
            return False
        if etype == QEvent.Type.MouseButtonPress:
            self._edit.setFocus(Qt.FocusReason.MouseFocusReason)
            if event.button() == Qt.MouseButton.LeftButton \
                    and self._press(event.pos()) == 3:
                self._edit.selectAll()
                return True
            if event.button() != Qt.MouseButton.LeftButton:
                self._count = 0
            return False
        if etype == QEvent.Type.MouseButtonDblClick:
            self._press(event.pos())
            if event.button() == Qt.MouseButton.LeftButton:
                span = word_span_at(self._edit.text(),
                                    self._edit.cursorPositionAt(event.pos()))
                if span is not None:
                    self._edit.setSelection(span[0], span[1] - span[0])
                    return True
            return False
        if etype == QEvent.Type.KeyPress:
            mods = event.modifiers()
            if mods & (Qt.KeyboardModifier.AltModifier
                       | Qt.KeyboardModifier.MetaModifier):
                return False
            if event.key() == Qt.Key.Key_Right and (
                    mods & Qt.KeyboardModifier.ControlModifier):
                stop = word_end_right_stop(self._edit.text(),
                                           self._edit.cursorPosition())
                if stop is None:
                    return False
                if mods & Qt.KeyboardModifier.ShiftModifier:
                    pos = self._edit.cursorPosition()
                    self._edit.setSelection(pos, stop - pos)
                else:
                    self._edit.setCursorPosition(stop)
                return True
            if event.key() == Qt.Key.Key_Delete and (
                    mods & Qt.KeyboardModifier.ControlModifier) \
                    and not (mods & Qt.KeyboardModifier.ShiftModifier):
                pos = self._edit.cursorPosition()
                stop = word_end_right_stop(self._edit.text(), pos)
                if stop is None:
                    return False
                self._edit.setSelection(pos, stop - pos)
                self._edit.del_()
                return True
        return False


def install_line_edit_nav(edit: QLineEdit):
    """Idempotent word-gesture installer for a QLineEdit. Returns the
    (single) filter object."""
    if not isinstance(edit, QLineEdit):
        raise TypeError("install_line_edit_nav needs a QLineEdit")
    found = edit.findChildren(_LineEditNav)
    if found:
        return found[0]
    return _LineEditNav(edit)
