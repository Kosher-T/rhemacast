"""ui/theme_kit/slider_field.py

SliderField — a slim accent track with a NumberField attached on the right.

The track is painted, not a QSlider: Fusion and the Windows style disagree
about groove, handle and focus chrome. Dragging emits ``preview`` and the
release emits ``changed``. The number field remains the keyboard/typed entry
path and can be scrubbed exactly like a standalone NumberField.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QWidget

from ui import tokens
from ui.theme_kit.base import format_number, paint_focus_ring
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip


class _SliderTrack(QWidget):
    preview = pyqtSignal(object)
    changed = pyqtSignal(object)
    dragging = pyqtSignal(bool)

    def __init__(self, *, minimum: float = 0.0, maximum: float = 1.0,
                 step: float = 0.01, value: float = 0.0,
                 integer: bool = False, decimals: Optional[int] = None,
                 default: Optional[float] = None, label: str = "",
                 parent=None):
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum if maximum > minimum else minimum + 1
        self._step = step
        self._value = value
        self._integer = integer
        self._decimals = decimals
        self._default = default
        self._label = label
        self._hover = False
        self._dragging = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName(label or "Slider")
        attach_tooltip(self, lambda: self._tooltip_text())

    # ── value ───────────────────────────────────────────────────────────────
    def value(self) -> float:
        return self._value

    def set_value(self, value: float, *, emit: bool = False) -> None:
        value = self._clamp(value)
        if value == self._value:
            return
        self._value = value
        self.update()
        if emit:
            self.changed.emit(value)

    def set_range(self, minimum: float, maximum: float) -> None:
        self._minimum = minimum
        self._maximum = maximum if maximum > minimum else minimum + 1
        self._value = self._clamp(self._value)
        self.update()

    def set_default(self, value: Optional[float]) -> None:
        self._default = value
        self.update()

    def set_step(self, step: float) -> None:
        self._step = step

    def _clamp(self, value: float) -> float:
        value = max(self._minimum, min(self._maximum, float(value)))
        if self._integer:
            return float(int(round(value)))
        # Keep the same precision policy as NumberField: whole steps are
        # clean; fine steps keep two decimals.
        return float(round(value, 6))

    def _value_from_x(self, x: int) -> float:
        ratio = max(0.0, min(1.0, (x - 8) / max(1, self.width() - 16)))
        return self._clamp(self._minimum + ratio
                           * (self._maximum - self._minimum))

    def _tooltip_text(self) -> str:
        low = format_number(self._minimum, integer=self._integer,
                            decimals=self._decimals)
        high = format_number(self._maximum, integer=self._integer,
                             decimals=self._decimals)
        return (f"{self._label}: {low} – {high}" if self._label
                else f"{low} – {high}")

    # ── interaction ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._dragging = True
        self.dragging.emit(True)
        value = self._value_from_x(int(event.position().x()))
        if value != self._value:
            self._value = value
            self.update()
            self.preview.emit(value)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not self._dragging:
            return
        value = self._value_from_x(int(event.position().x()))
        if value != self._value:
            self._value = value
            self.update()
            self.preview.emit(value)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.dragging.emit(False)
        self.changed.emit(self._value)
        event.accept()

    def wheelEvent(self, event) -> None:
        if not self.hasFocus():
            event.ignore()
            return
        self._step_value(1 if event.angleDelta().y() > 0 else -1,
                         event.modifiers())
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._step_value(1, event.modifiers())
            event.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._step_value(-1, event.modifiers())
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self.set_value(self._minimum, emit=True)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self.set_value(self._maximum, emit=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def _step_value(self, direction: int, modifiers) -> None:
        step = self._step
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            step *= 10
        elif modifiers & Qt.KeyboardModifier.AltModifier:
            step /= 10
        self.set_value(self._value + direction * step, emit=True)
        self.preview.emit(self._value)

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
        width = max(1, self.width())
        padding = 8
        usable = max(1, width - padding * 2)
        span = max(0.0001, self._maximum - self._minimum)
        ratio = max(0.0, min(1.0, (self._value - self._minimum) / span))
        knob_x = padding + ratio * usable
        centre_y = self.height() // 2
        bar = QRectF(padding, centre_y - 2, usable, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.BG_CARD_HOVER))
        painter.drawRoundedRect(bar, 2, 2)
        fill = QRectF(bar.left(), bar.top(), max(0.0, knob_x - bar.left()),
                      bar.height())
        painter.setBrush(QColor(tokens.ACCENT))
        painter.drawRoundedRect(fill, 2, 2)
        if self._default is not None:
            default_ratio = max(
                0.0, min(1.0, (self._default - self._minimum) / span))
            tick_x = padding + default_ratio * usable
            painter.setPen(QPen(QColor(tokens.TEXT_MUTED), 1))
            painter.drawLine(
                int(tick_x), centre_y - 7, int(tick_x), centre_y + 7)
            painter.setPen(Qt.PenStyle.NoPen)
        radius = 5.0 if (self._hover or self.hasFocus()
                         or self._dragging) else 4.0
        painter.setBrush(QColor(tokens.TEXT_PRIMARY))
        painter.setPen(QPen(QColor(tokens.ACCENT), 1.2))
        painter.drawEllipse(
            QRectF(knob_x - radius, centre_y - radius,
                   radius * 2, radius * 2))
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(110, tokens.CONTROL_HEIGHT)


class SliderField(QWidget):
    """Track + number entry for bounded values (opacity, scale, ...).

    Signals
        changed(object) — committed value.
        preview(object) — while dragging the track or scrubbing the number.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)
    dragging = pyqtSignal(bool)

    def __init__(self, value: float = 0.0, *, minimum: float = 0.0,
                 maximum: float = 1.0, step: float = 0.01,
                 default: Optional[float] = None, integer: bool = False,
                 decimals: Optional[int] = None, label: str = "",
                 field_width: int = 62, parent=None):
        super().__init__(parent)
        self._syncing = False
        self._integer = integer
        self._decimals = decimals
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_8)
        self._track = _SliderTrack(
            minimum=minimum, maximum=maximum, step=step, value=value,
            integer=integer, decimals=decimals, default=default, label=label)
        self._number = NumberField(
            value, minimum=minimum, maximum=maximum, step=step,
            integer=integer, decimals=decimals, label=label)
        self._number.setFixedWidth(field_width)
        layout.addWidget(self._track, 1)
        layout.addWidget(self._number, 0)
        self.setFocusProxy(self._track)

        self._track.preview.connect(self._on_track_preview)
        self._track.changed.connect(self._on_track_changed)
        self._track.dragging.connect(self.dragging)
        self._number.preview.connect(self._on_number_preview)
        self._number.changed.connect(self._on_number_changed)
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> float:
        return self._track.value()

    def set_value(self, value: float, *, emit: bool = False) -> None:
        self._syncing = True
        try:
            self._track.set_value(value)
            self._number.set_value(
                int(round(value)) if self._integer else value)
        finally:
            self._syncing = False
        if emit:
            self.changed.emit(self.value())

    def set_range(self, minimum: float, maximum: float) -> None:
        self._track.set_range(minimum, maximum)
        self._number.set_range(minimum, maximum, emit=False)
        self.set_value(self._track.value())

    def set_default(self, value: Optional[float]) -> None:
        self._track.set_default(value)

    def set_step(self, step: float) -> None:
        self._track.set_step(step)
        self._number.set_step(step)

    def set_accessible_label(self, text: str) -> None:
        self._track.setAccessibleName(text)
        self._number.set_accessible_label(text)

    # ── plumbing ────────────────────────────────────────────────────────────
    def _on_track_preview(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._number.set_value(
                int(round(value)) if self._integer else value)
        finally:
            self._syncing = False
        self.preview.emit(value)

    def _on_track_changed(self, value: float) -> None:
        if self._syncing:
            return
        self._syncing = True
        try:
            self._number.set_value(
                int(round(value)) if self._integer else value)
        finally:
            self._syncing = False
        self.changed.emit(value)

    def _on_number_preview(self, value) -> None:
        if self._syncing or value is None:
            return
        self._syncing = True
        try:
            self._track.set_value(float(value))
        finally:
            self._syncing = False
        self.preview.emit(value)

    def _on_number_changed(self, value) -> None:
        if self._syncing or value is None:
            return
        self._syncing = True
        try:
            self._track.set_value(float(value))
        finally:
            self._syncing = False
        self.changed.emit(self._track.value())


__all__ = ["SliderField"]
