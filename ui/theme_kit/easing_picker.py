"""ui/theme_kit/easing_picker.py

EasingPicker — a compact easing field with a painted curve popover.

Preset names and custom ``cubic-bezier(a, b, c, d)`` strings are both stored
verbatim. The caller validates them; painting falls back to a straight line
for an unrecognised string.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    draw_check, draw_chevron, elide, font, paint_focus_ring,
)
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import PopupSurface, attach_tooltip

_CUBIC_RE = re.compile(
    r"^cubic-bezier\(\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*,"
    r"\s*(-?\d*\.?\d+)\s*,\s*(-?\d*\.?\d+)\s*\)$", re.I)

#: keyword → (x1, y1, x2, y2). ``spring`` overshoots; the editor keeps y
#: outside 0–1 for its preview only.
EASING_CURVES = {
    "linear": (0.0, 0.0, 1.0, 1.0),
    "ease-in": (0.42, 0.0, 1.0, 1.0),
    "ease-out": (0.0, 0.0, 0.58, 1.0),
    "ease-in-out": (0.42, 0.0, 0.58, 1.0),
    "smooth": (0.25, 0.1, 0.25, 1.0),
    "spring": (0.34, 1.56, 0.64, 1.0),
}
PRESETS = tuple(EASING_CURVES)

DISPLAY_NAMES = {
    "linear": "Linear",
    "ease-in": "Ease in",
    "ease-out": "Ease out",
    "ease-in-out": "Ease in-out",
    "smooth": "Smooth",
    "spring": "Spring",
}


def parse_easing(text: Any) -> tuple[float, float, float, float]:
    """Return control points for painting; unknown text paints linear."""
    raw = "" if text is None else str(text).strip()
    match = _CUBIC_RE.match(raw)
    if match:
        try:
            return tuple(float(part) for part in match.groups())  # type: ignore[return-value]
        except ValueError:
            return EASING_CURVES["linear"]
    return EASING_CURVES.get(raw.lower(), EASING_CURVES["linear"])


def is_custom_easing(text: Any) -> bool:
    return bool(_CUBIC_RE.match("" if text is None else str(text).strip()))


def format_cubic_bezier(values: tuple[float, float, float, float]) -> str:
    def _fmt(value: float) -> str:
        text = f"{value:.3f}".rstrip("0").rstrip(".")
        return text or "0"

    return "cubic-bezier({})".format(
        ", ".join(_fmt(value) for value in values))


def easing_label(text: Any) -> str:
    raw = "" if text is None else str(text).strip()
    if not raw:
        return "No easing"
    if raw.lower() in DISPLAY_NAMES:
        return DISPLAY_NAMES[raw.lower()]
    if is_custom_easing(raw):
        return "Custom curve"
    return raw


def paint_easing_curve(painter: QPainter, rect: QRectF, text: Any,
                       *, color: str = tokens.ACCENT,
                       width: float = 1.4) -> None:
    """Draw the curve inside ``rect`` with a little vertical padding."""
    x1, y1, x2, y2 = parse_easing(text)
    top = min(0.0, y1, y2)
    bottom = max(1.0, y1, y2)
    span = max(0.001, bottom - top)
    pad = 2.0
    inner = rect.adjusted(pad, pad, -pad, -pad)

    def point(t: float) -> QPointF:
        inv = 1.0 - t
        x = (3 * inv * inv * t * x1 + 3 * inv * t * t * x2 + t * t * t)
        y = (3 * inv * inv * t * y1 + 3 * inv * t * t * y2 + t * t * t)
        return QPointF(inner.left() + x * inner.width(),
                       inner.bottom() - (y - top) / span * inner.height())

    path = QPainterPath()
    path.moveTo(point(0.0))
    for step in range(1, 33):
        path.lineTo(point(step / 32.0))
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawPath(path)
    painter.restore()


# ─── Painted pieces ─────────────────────────────────────────────────────────

class _CurveSwatch(QWidget):
    def __init__(self, text: Any = "linear", *, width: int = 40,
                 height: int = 22, parent=None):
        super().__init__(parent)
        self._text = text
        self._color = tokens.ACCENT_TEXT
        self.setFixedSize(width, height)

    def set_value(self, text: Any, color: Optional[str] = None) -> None:
        self._text = text
        if color is not None:
            self._color = color
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(rect, 3, 3)
        paint_easing_curve(painter, rect.adjusted(2, 2, -2, -2), self._text,
                           color=self._color, width=1.3)
        painter.end()


class _EasingRow(QAbstractButton):
    changed = pyqtSignal(str)

    def __init__(self, value: str, *, checked: bool = False, parent=None):
        super().__init__(parent)
        self._value = value
        self._hover = False
        self.setCheckable(True)
        self.setChecked(checked)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(DISPLAY_NAMES.get(value, value))
        self.setFixedHeight(30)
        self.clicked.connect(lambda: self.changed.emit(self._value))

    def value(self) -> str:
        return self._value

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        selected = self.isChecked()
        if selected:
            painter.setPen(QPen(QColor(tokens.ACCENT), 1))
            painter.setBrush(QColor(tokens.ACCENT_TINT))
        elif self._hover:
            painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
            painter.setBrush(QColor(tokens.BG_CARD_HOVER))
        else:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)

        custom = self._value == "__custom__"
        if not custom:
            paint_easing_curve(
                painter, QRectF(rect.left() + 6, rect.top() + 4,
                                rect.width() * 0.42, rect.height() - 8),
                self._value,
                color=(tokens.ACCENT_TEXT if selected
                       else tokens.TEXT_SECONDARY),
                width=1.5)
        label_font = font(tokens.TYPE_CAPTION,
                          tokens.WEIGHT_SEMIBOLD if selected
                          else tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY if selected
                              else tokens.TEXT_SECONDARY))
        label = ("Custom curve" if custom
                 else DISPLAY_NAMES.get(self._value, self._value))
        left = rect.left() + (6 if custom else rect.width() * 0.48)
        painter.drawText(
            QRectF(left, rect.top(),
                   rect.width() - (left - rect.left()) - 22, rect.height()),
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elide(label, rect.width() - (left - rect.left()) - 22))
        if selected:
            draw_check(painter, QRectF(rect.right() - 18, rect.top(),
                                       14, rect.height()))
        if self.hasFocus():
            paint_focus_ring(painter, rect, tokens.RADIUS_SM)
        painter.end()


class _EasingPopup(PopupSurface):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, field: "EasingPicker"):
        super().__init__(field.window())
        self._field = field
        self._cancelled = False
        self._updating = False
        self._rows: list[_EasingRow] = []

        layout = self.content
        layout.setSpacing(tokens.SPACE_4)
        for value in PRESETS:
            row = _EasingRow(value, checked=value == field._value)
            row.changed.connect(self._on_preset)
            layout.addWidget(row)
            self._rows.append(row)

        divider = QWidget(self)
        divider.setFixedHeight(1)
        divider.setStyleSheet(
            f"background: {tokens.BORDER_HAIRLINE};")
        layout.addWidget(divider)

        self.custom_toggle = _EasingRow(
            "__custom__", checked=is_custom_easing(field._value))
        # Use a plain label for the custom row rather than a preset curve.
        self.custom_toggle._value = "__custom__"
        self.custom_toggle.changed.connect(
            lambda _value: self._use_custom())
        layout.addWidget(self.custom_toggle)

        custom = QWidget(self)
        custom_layout = QVBoxLayout(custom)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(tokens.SPACE_4)
        self.preview_curve = QWidget(self)
        self.preview_curve.setFixedHeight(58)
        self.preview_curve.setSizePolicy(QSizePolicy.Policy.Expanding,
                                         QSizePolicy.Policy.Fixed)
        self.preview_curve.paintEvent = self._paint_preview  # type: ignore[assignment]
        custom_layout.addWidget(self.preview_curve)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(tokens.SPACE_4)
        self.x1 = NumberField(0, minimum=-2, maximum=3, step=0.01,
                              decimals=2, label="Control point x1")
        self.y1 = NumberField(0, minimum=-2, maximum=3, step=0.01,
                              decimals=2, label="Control point y1")
        self.x2 = NumberField(1, minimum=-2, maximum=3, step=0.01,
                              decimals=2, label="Control point x2")
        self.y2 = NumberField(1, minimum=-2, maximum=3, step=0.01,
                              decimals=2, label="Control point y2")
        for field_widget in (self.x1, self.y1, self.x2, self.y2):
            field_widget.preview.connect(
                lambda _value: self._on_custom_field(commit=False))
            field_widget.changed.connect(
                lambda _value: self._on_custom_field(commit=True))
            controls.addWidget(field_widget, 1)
        custom_layout.addLayout(controls)
        layout.addWidget(custom)
        self.custom_panel = custom

        self._sync_custom(field._value)
        self.setMinimumWidth(272)

    # ── preset/custom ───────────────────────────────────────────────────────
    def _on_preset(self, value: str) -> None:
        self._field._set_from_popover(value, commit=True)
        self.close()

    def _use_custom(self) -> None:
        self.custom_panel.setVisible(True)
        values = (self.x1.numeric_value() or 0.0,
                  self.y1.numeric_value() or 0.0,
                  self.x2.numeric_value() or 0.0,
                  self.y2.numeric_value() or 0.0)
        text = format_cubic_bezier(values)
        self._field._set_from_popover(text, commit=False)
        self._update_preview()
        self.x1.setFocus(Qt.FocusReason.MouseFocusReason)

    def _sync_custom(self, text: Any) -> None:
        x1, y1, x2, y2 = parse_easing(text)
        custom = is_custom_easing(text)
        self._updating = True
        try:
            self.x1.set_value(x1)
            self.y1.set_value(y1)
            self.x2.set_value(x2)
            self.y2.set_value(y2)
        finally:
            self._updating = False
        self.custom_panel.setVisible(custom)
        for row in self._rows:
            row.setChecked(row.value() == str(text or "").strip().lower())
            row.update()
        self.custom_toggle.setChecked(custom)
        self.custom_toggle.update()
        self._update_preview()

    def _values(self) -> tuple[float, float, float, float]:
        return (self.x1.numeric_value() or 0.0,
                self.y1.numeric_value() or 0.0,
                self.x2.numeric_value() or 0.0,
                self.y2.numeric_value() or 0.0)

    def _update_preview(self) -> None:
        self.preview_curve.update()

    def _paint_preview(self, event) -> None:
        painter = QPainter(self.preview_curve)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.preview_curve.rect()).adjusted(0.5, 0.5, -0.5,
                                                          -0.5)
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)
        inner = rect.adjusted(10, 8, -10, -8)
        # Grid.
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        for fraction in (0.25, 0.5, 0.75):
            x = inner.left() + fraction * inner.width()
            y = inner.top() + fraction * inner.height()
            painter.drawLine(QPointF(x, inner.top()),
                             QPointF(x, inner.bottom()))
            painter.drawLine(QPointF(inner.left(), y),
                             QPointF(inner.right(), y))
        text = format_cubic_bezier(self._values())
        paint_easing_curve(painter, inner, text,
                           color=tokens.ACCENT_TEXT, width=1.8)
        painter.end()

    def _on_custom_field(self, *_args, commit: bool = False) -> None:
        if self._updating:
            return
        text = format_cubic_bezier(self._values())
        self._field._set_from_popover(text, commit=commit)
        self._update_preview()

    # ── keys / close ────────────────────────────────────────────────────────
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._cancelled:
            self.cancelled.emit()
        else:
            text = self._field._value
            if text != self._field._open_value:
                self.committed.emit(text)
        super().closeEvent(event)


class EasingPicker(QWidget):
    """Compact easing field: curve preview, label, chevron, own popover.

    Signals
        changed(object) — committed easing string.
        preview(object) — live easing while dragging a custom control point.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)
    opened = pyqtSignal()

    def __init__(self, value: Any = "ease-out", *,
                 presets: Optional[list[str]] = None,
                 allow_custom: bool = True, parent=None):
        super().__init__(parent)
        self._value = "" if value is None else str(value)
        self._allow_custom = bool(allow_custom)
        self._allowed = list(presets) if presets is not None else list(PRESETS)
        self._hover = False
        self._warning = ""
        self._popover: Optional[_EasingPopup] = None
        self._open_value = self._value
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Easing")
        attach_tooltip(self, lambda: self._warning or self._value
                       or "No easing")

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        return self._value or None

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        text = "" if value is None else str(value)
        if text == self._value:
            return
        self._value = text
        self.update()
        if emit:
            self.changed.emit(self.value())

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    # ── popover ─────────────────────────────────────────────────────────────
    def _open_popover(self) -> None:
        if not self.isEnabled():
            return
        if self._popover is not None:
            self._popover.close()
            return
        popover = _EasingPopup(self)
        self._popover = popover
        self._open_value = self._value
        popover.committed.connect(self._on_popover_committed)
        popover.cancelled.connect(self._on_popover_cancelled)
        popover.closed.connect(self._on_popover_closed)
        popover.destroyed.connect(self._on_popover_destroyed)
        popover.show_below(self, width=286, max_height=470, align="left")
        self.opened.emit()

    def _set_from_popover(self, text: str, *, commit: bool) -> None:
        self._value = text
        self.update()
        if commit:
            self.changed.emit(self.value())
        else:
            self.preview.emit(self.value())

    def _on_popover_committed(self, text: str) -> None:
        if text == self._value:
            return
        self._value = text
        self.update()
        self.changed.emit(self.value())

    def _on_popover_cancelled(self) -> None:
        self._value = self._open_value
        self.update()
        self.preview.emit(self.value())

    def _on_popover_closed(self) -> None:
        # Popups are not deleted on close; release and drop them so the next
        # click opens a fresh one.
        popover = self._popover
        self._popover = None
        if popover is not None:
            popover.deleteLater()

    def _on_popover_destroyed(self, *_args) -> None:
        self._popover = None

    # ── events / painting ───────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._open_popover()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_Space, Qt.Key.Key_Down):
            self._open_popover()
            event.accept()
            return
        super().keyPressEvent(event)

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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        focused = self.hasFocus() or (
            self._popover is not None and self._popover.isVisible())
        if not enabled:
            surface, edge = tokens.BG_PANEL, tokens.BORDER_HAIRLINE
        elif focused:
            surface, edge = tokens.BG_FIELD, tokens.ACCENT
        elif self._warning:
            surface, edge = tokens.BG_FIELD, tokens.WARNING
        elif self._hover:
            surface, edge = tokens.BG_FIELD, tokens.BORDER_POPOVER
        else:
            surface, edge = tokens.BG_FIELD, tokens.BORDER_HAIRLINE
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)

        curve_rect = QRectF(rect.left() + 4, rect.top() + 4,
                            rect.height() - 8, rect.height() - 8)
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.BG_PANEL))
        painter.drawRoundedRect(curve_rect, 3, 3)
        paint_easing_curve(
            painter, curve_rect, self._value,
            color=tokens.ACCENT_TEXT if enabled else tokens.TEXT_MUTED,
            width=1.4)

        text_rect = QRectF(curve_rect.right() + 6, rect.top(),
                           max(0.0, rect.right() - curve_rect.right() - 24),
                           rect.height())
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_MUTED if not enabled
                              else tokens.TEXT_PRIMARY))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(label_font).elidedText(
                easing_label(self._value), Qt.TextElideMode.ElideRight,
                int(text_rect.width())))
        draw_chevron(
            painter, QRectF(rect.right() - 14, rect.top(), 10,
                            rect.height()).center(),
            "down", tokens.TEXT_MUTED, size=4.2)
        if focused:
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(180, tokens.CONTROL_HEIGHT)


__all__ = [
    "EasingPicker", "EASING_CURVES", "PRESETS", "parse_easing",
    "is_custom_easing", "format_cubic_bezier", "easing_label",
    "paint_easing_curve",
]
