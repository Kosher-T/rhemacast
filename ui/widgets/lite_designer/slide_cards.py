"""
ui/widgets/lite_designer/slide_cards.py

SlideCard: one slide in the Freeform column — index badge, section chip
(inline rename), move/delete/add controls, and a body that is EITHER a
static rich label OR the single shared live QTextEdit (hosted on demand).

Only one card hosts the editor at a time (the Lite Designer moves it on
activation) — N slides cost N labels + 1 editor.
"""

from PyQt6.QtWidgets import (QFrame, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QToolButton, QWidget)
from PyQt6.QtCore import Qt, pyqtSignal

_CARD_STYLE = (
    "SlideCard { background: rgba(30, 41, 59, 0.7);"
    "  border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }"
    "SlideCard[active=\"true\"] { border-color: rgba(59,130,246,0.7); }"
)
_CHIP_STYLE = (
    "QLineEdit { background: rgba(6,182,212,0.08); color: #67e8f6;"
    "  border: none; border-radius: 0px;"
    "  padding: 2px 8px; font-size: 10px; font-weight: 700; }"
)
_IDX_STYLE = ("color: #475569; font-size: 9px; font-weight: 600;"
              "background: transparent;")
_MINI_BTN = (
    "QToolButton { background: transparent; border: none; color: #64748b;"
    "  font-size: 11px; font-weight: 700; padding: 1px 4px; }"
    "QToolButton:hover { color: #f8fafc; }"
)
_BODY_STYLE = (
    "QLabel { color: #e2e8f0; font-size: 13px;"
    "  background: rgba(255,255,255,0.04); border: none; border-radius: 4px;"
    "  padding: 6px; }"
)


class SlideCard(QFrame):
    """One slide row. Index is positional (set_index on reorder)."""

    activated = pyqtSignal(int)            # clicked → host the editor here
    section_changed = pyqtSignal(int, str)  # index, new section ("" = clear)
    delete_requested = pyqtSignal(int)
    move_requested = pyqtSignal(int, int)  # index, delta (-1/+1)
    add_after_requested = pyqtSignal(int)

    def __init__(self, index: int, section: str | None, parent=None):
        super().__init__(parent)
        self._index = index
        self.setObjectName("SlideCard")
        self.setStyleSheet(_CARD_STYLE)
        self.setProperty("active", False)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 6)
        root.setSpacing(4)

        # ── header: [#n] [chip] ↑ ↓ + × ──
        header = QHBoxLayout()
        header.setSpacing(4)
        self._idx = QLabel()
        self._idx.setStyleSheet(_IDX_STYLE)
        header.addWidget(self._idx)

        self._chip = QLineEdit()
        self._chip.setStyleSheet(_CHIP_STYLE)
        self._chip.setPlaceholderText("Section…")
        self._chip.setToolTip("Section for this slide (empty = none)")
        self._chip.editingFinished.connect(self._on_chip_finished)
        header.addWidget(self._chip, 1)

        for label, tip, slot in (
                ("↑", "Move up", lambda: self.move_requested.emit(self._index, -1)),
                ("↓", "Move down", lambda: self.move_requested.emit(self._index, 1)),
                ("+", "Add slide after", lambda: self.add_after_requested.emit(self._index)),
                ("×", "Delete slide", lambda: self.delete_requested.emit(self._index))):
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setStyleSheet(_MINI_BTN)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(slot)
            header.addWidget(b)
        root.addLayout(header)

        # ── body: static label, swapped for the shared editor on activation ──
        self._body_wrap = QWidget()
        self._body_layout = QVBoxLayout(self._body_wrap)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._label = QLabel()
        self._label.setStyleSheet(_BODY_STYLE)
        self._label.setWordWrap(True)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.NoTextInteraction)
        self._body_layout.addWidget(self._label)
        root.addWidget(self._body_wrap)

        self._editor = None
        self.set_index(index)
        self.set_section(section or "")

    # ─── identity ───────────────────────────────────────────────────────

    def set_index(self, index: int):
        self._index = index
        self._idx.setText(f"#{index + 1}")

    def set_section(self, section: str):
        if self._chip.text() != section:
            self._chip.blockSignals(True)
            self._chip.setText(section)
            self._chip.blockSignals(False)

    def _on_chip_finished(self):
        self.section_changed.emit(self._index, self._chip.text().strip())

    # ─── body swap ──────────────────────────────────────────────────────

    def set_static_html(self, html: str):
        self._label.setText(html or "<i style='color:#475569'>Empty slide</i>")

    def host_editor(self, editor):
        """Move the shared live editor into this card."""
        self.release_editor()
        self._body_layout.removeWidget(self._label)
        self._label.setParent(None)
        self._editor = editor
        self._body_layout.addWidget(editor)
        editor.setVisible(True)

    def release_editor(self):
        if self._editor is not None:
            self._body_layout.removeWidget(self._editor)
            self._editor.setParent(None)
            self._editor = None
        if self._label.parent() is not self._body_wrap:
            self._body_layout.addWidget(self._label)

    def set_active(self, on: bool):
        self.setProperty("active", on)
        # Re-polish so the active border applies without a rebuild.
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._index)
        super().mousePressEvent(event)
