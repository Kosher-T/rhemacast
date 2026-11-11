"""ui/theme_kit/switch.py

Switch — the kit's boolean control.

Painted, not QSS: the Fusion/Windows checkbox indicators differ in size,
inset and focus ring. The switch is a checkable QAbstractButton so Space,
Enter and screen readers get the expected behaviour for free.
"""

from __future__ import annotations

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton, QSizePolicy

from ui import tokens
from ui.theme_kit.base import font, paint_focus_ring

_TRACK_W = 30
_TRACK_H = 16
_KNOB = 12


class Switch(QAbstractButton):
    """Small on/off switch with an optional inline label.

    Signals
        changed(bool) — emitted after the user toggles it.
    """

    changed = pyqtSignal(bool)

    def __init__(self, checked: bool = False, text: str = "",
                 parent=None):
        super().__init__(parent)
        self.setText(str(text))
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName(text or "Toggle")
        self._hover = False
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.update()
        self.changed.emit(bool(checked))

    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, checked: bool, *, emit: bool = False) -> None:
        if self.isChecked() == bool(checked):
            return
        self.blockSignals(True)
        self.setChecked(bool(checked))
        self.blockSignals(False)
        self.update()
        if emit:
            self.changed.emit(bool(checked))

    def sizeHint(self) -> QSize:
        width = _TRACK_W
        if self.text():
            metrics = QFontMetrics(font(tokens.TYPE_CAPTION))
            width += tokens.SPACE_8 + metrics.horizontalAdvance(self.text())
        return QSize(width, tokens.CONTROL_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        enabled = self.isEnabled()
        checked = self.isChecked()
        left = self.width() - _TRACK_W
        centre_y = self.height() / 2.0
        track = QRectF(left, centre_y - _TRACK_H / 2, _TRACK_W, _TRACK_H)

        if not enabled:
            track_color = tokens.BG_CARD
            edge = tokens.BORDER_HAIRLINE
        elif checked:
            track_color = tokens.ACCENT
            edge = tokens.ACCENT
        elif self._hover:
            track_color = tokens.BG_CARD_HOVER
            edge = tokens.BORDER_POPOVER
        else:
            track_color = tokens.BG_CARD_HOVER
            edge = tokens.BORDER_HAIRLINE
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(track_color))
        painter.drawRoundedRect(track, _TRACK_H / 2, _TRACK_H / 2)

        knob_x = (track.right() - _KNOB - 2 if checked
                  else track.left() + 2)
        knob_color = (tokens.TEXT_PRIMARY if checked and enabled
                      else tokens.TEXT_MUTED if not enabled
                      else tokens.TEXT_SECONDARY)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(knob_color))
        painter.drawEllipse(
            QRectF(knob_x, centre_y - _KNOB / 2, _KNOB, _KNOB))

        if self.text():
            f = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
            painter.setFont(f)
            painter.setPen(QColor(
                tokens.TEXT_MUTED if not enabled else
                tokens.TEXT_PRIMARY if checked else tokens.TEXT_SECONDARY))
            text_rect = QRectF(0, 0, max(0, left - tokens.SPACE_8),
                               self.height())
            metrics = QFontMetrics(f)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(self.text(),
                                   Qt.TextElideMode.ElideRight,
                                   int(text_rect.width())))

        if self.hasFocus():
            paint_focus_ring(painter,
                             QRectF(self.rect()).adjusted(1, 3, -1, -3),
                             tokens.RADIUS_SM)
        painter.end()


__all__ = ["Switch"]
