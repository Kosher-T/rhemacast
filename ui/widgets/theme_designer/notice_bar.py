"""
ui/widgets/theme_designer/notice_bar.py

One-line inline notice strip used by the Theme Designer for file-watcher
events ("changed on disk", "theme was deleted", "file is not valid JSON").

It sits under the toolbar, never floats over the editor, and only appears
when there is something to say. Actions are plain buttons; the caller owns
what each one does.
"""

from __future__ import annotations

from typing import Callable, Iterable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

from ui import tokens

#: Per-tone surface: the amber wash warns, the accent wash is informational.
_TONES = {
    "warning": (tokens.WARNING, tokens.WARNING_TINT),
    "neutral": (tokens.ACCENT, tokens.WARNING_TINT),
}

_BUTTON_STYLE = (
    "QPushButton {"
    f"  background: transparent;"
    f"  color: {tokens.TEXT_PRIMARY};"
    f"  border: 1px solid {tokens.BORDER_POPOVER};"
    "  border-radius: 4px;"
    f"  font-size: {tokens.TYPE_CAPTION}px;"
    f"  font-weight: {tokens.WEIGHT_SEMIBOLD};"
    "  padding: 2px 8px;"
    "}"
    "QPushButton:hover {"
    f"  background: {tokens.BG_CARD_HOVER};"
    "}"
)


class NoticeBar(QFrame):
    """Collapsible notice row: text on the left, actions on the right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rcThemeNoticeBar")
        self.setVisible(False)
        self._tone = "warning"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 5, 8, 5)
        layout.setSpacing(8)

        self._label = QLabel("")
        self._label.setWordWrap(False)
        self._label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._label, 1)

        self._actions_layout = QHBoxLayout()
        self._actions_layout.setContentsMargins(0, 0, 0, 0)
        self._actions_layout.setSpacing(6)
        layout.addLayout(self._actions_layout)

        self._apply_tone()

    # ── API ──────────────────────────────────────────────────────────────────

    def show_notice(self, text: str,
                    actions: Iterable[tuple[str, Callable[[], None]]] = (),
                    tone: str = "warning") -> None:
        """Show one sentence plus up to a few explicit next steps."""
        self._tone = tone if tone in _TONES else "warning"
        self._label.setText(str(text))
        self._clear_actions()
        for label, handler in actions:
            button = QPushButton(str(label))
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setStyleSheet(_BUTTON_STYLE)
            button.setFixedHeight(22)
            button.clicked.connect(handler)
            self._actions_layout.addWidget(button)
        self._apply_tone()
        self.setVisible(True)

    def current_text(self) -> str:
        return self._label.text()

    def dismiss(self) -> None:
        self.setVisible(False)
        self._label.setText("")
        self._clear_actions()

    def is_showing(self) -> bool:
        return self.isVisible() and bool(self._label.text())

    # ── internals ────────────────────────────────────────────────────────────

    def _clear_actions(self) -> None:
        while self._actions_layout.count():
            item = self._actions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _apply_tone(self) -> None:
        edge, wash = _TONES.get(self._tone, _TONES["warning"])
        self.setStyleSheet(
            "QFrame#rcThemeNoticeBar {"
            f"  background: {wash};"
            f"  border-left: 3px solid {edge};"
            f"  border-bottom: 1px solid {tokens.BORDER_HAIRLINE};"
            "}"
        )
        self._label.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            "background: transparent;")
