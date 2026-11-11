"""ui/theme_kit/color_field.py

ColorField — a compact swatch + text field with our own colour popover.

No ``QColorDialog``: the popover is painted from the kit's tokens, so Windows
and Linux show the same saturation plane, hue/alpha strips, hex field and
palette row. ``ColorEditor`` is exported because PaintField embeds the same
editor for gradient stops.

The field preserves the caller's text verbatim (``rgba(...)``, ``@token``,
``currentColor``). Painting resolves what it can and falls back to a neutral
checkerboard; schema validation stays with the caller.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFontMetrics, QLinearGradient, QPainter, QPen,
)
from PyQt6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    checkerboard, elide, font, paint_focus_ring, qcolor,
)
from ui.theme_kit.flow import FlowRow
from ui.theme_kit.popup import PopupSurface, attach_tooltip

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_FUNC_RE = re.compile(r"^(rgba?|hsla?)\(([^)]*)\)$", re.I)
_TOKEN_EMPTY_LABEL = "Not set"


# ─── Colour conversion ──────────────────────────────────────────────────────

def _split_color_args(body: str) -> list[str]:
    if "," in body:
        return [part.strip() for part in body.split(",") if part.strip()]
    # Modern space syntax: ``rgb(12 34 56 / 0.5)``.
    if "/" in body:
        left, right = body.split("/", 1)
        return [part for part in left.split() if part] + [right.strip()]
    return [part for part in body.split() if part]


def _number_or_percent(text: str) -> Optional[float]:
    text = text.strip()
    try:
        if text.endswith("%"):
            return float(text[:-1]) / 100.0
        return float(text)
    except ValueError:
        return None


def parse_css_color(text: Any) -> Optional[QColor]:
    """Parse the CSS colour shapes the theme schema accepts."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    low = raw.lower()
    if low in ("transparent", "none"):
        return QColor(0, 0, 0, 0)
    if low in ("currentcolor", "inherit") or low.startswith("@"):
        return None
    match = _HEX_RE.match(raw)
    if match:
        digits = match.group(1)
        if len(digits) == 3:
            r, g, b = (int(c * 2, 16) for c in digits)
            return QColor(r, g, b, 255)
        if len(digits) == 4:
            r, g, b, a = (int(c * 2, 16) for c in digits)
            return QColor(r, g, b, a)
        if len(digits) == 6:
            return QColor(int(digits[0:2], 16), int(digits[2:4], 16),
                          int(digits[4:6], 16), 255)
        if len(digits) == 8:
            return QColor(int(digits[0:2], 16), int(digits[2:4], 16),
                          int(digits[4:6], 16), int(digits[6:8], 16))
        return None
    match = _FUNC_RE.match(raw)
    if not match:
        color = QColor(raw)
        return color if color.isValid() else None
    kind = match.group(1).lower()
    args = _split_color_args(match.group(2))
    if kind.startswith("rgb"):
        if len(args) < 3:
            return None
        values = []
        for part in args[:3]:
            number = _number_or_percent(part)
            if number is None:
                return None
            values.append(round(number * 255) if part.strip().endswith("%")
                          else round(number))
        alpha = 255
        if len(args) >= 4:
            a = _number_or_percent(args[3])
            if a is None:
                return None
            alpha = round(a * 255)
        return QColor(*[max(0, min(255, v)) for v in values],
                      max(0, min(255, alpha)))
    # HSL / HSLA.
    if len(args) < 3:
        return None
    try:
        hue = float(args[0].strip().rstrip("deg")) % 360.0
    except ValueError:
        return None
    sat = _number_or_percent(args[1])
    light = _number_or_percent(args[2])
    if sat is None or light is None:
        return None
    if not args[1].strip().endswith("%"):
        sat = sat  # already 0-1 when a bare 0-1 is given? keep as parsed
    alpha = 255
    if len(args) >= 4:
        a = _number_or_percent(args[3])
        if a is None:
            return None
        alpha = round(a * 255)
    color = QColor()
    color.setHslF(hue / 360.0, max(0.0, min(1.0, sat)),
                  max(0.0, min(1.0, light)),
                  max(0.0, min(1.0, alpha / 255.0)))
    return color


def css_color(color: QColor, *, force_alpha: bool = False) -> str:
    """Canonical compact CSS: ``#rrggbb`` or ``#rrggbbaa``."""
    if color.alpha() < 255 or force_alpha:
        return "#{:02x}{:02x}{:02x}{:02x}".format(
            color.red(), color.green(), color.blue(), color.alpha())
    return "#{:02x}{:02x}{:02x}".format(
        color.red(), color.green(), color.blue())


def resolve_paint_color(text: Any, palette: Optional[dict[str, str]] = None
                        ) -> Optional[QColor]:
    """Resolve a plain colour or ``@token`` for painting only."""
    if text is None:
        return None
    raw = str(text).strip()
    if raw.startswith("@") and palette:
        key = raw[1:]
        value = palette.get(key)
        if value is None:
            lowered = {k.casefold(): v for k, v in palette.items()}
            value = lowered.get(key.casefold())
        if value is not None:
            return parse_css_color(value)
    return parse_css_color(raw)


def _normalise_text(text: str) -> Optional[str]:
    """Accept a colour, a palette token, or a known keyword; else None."""
    raw = str(text).strip()
    if not raw:
        return None
    low = raw.lower()
    if low in ("currentcolor", "inherit", "transparent", "none"):
        return raw
    if raw.startswith("@"):
        return raw
    color = parse_css_color(raw)
    if color is None:
        return None
    return css_color(color)


# ─── Painted picker pieces ──────────────────────────────────────────────────

class _ColorPlane(QWidget):
    preview = pyqtSignal(QColor)
    committed = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hue = 0
        self._sat = 255
        self._val = 255
        self._alpha = 255
        self._hover = False
        self._dragging = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(104)
        self.setAccessibleName("Colour saturation and brightness")
        self.setCursor(Qt.CursorShape.CrossCursor)

    def color(self) -> QColor:
        return QColor.fromHsv(self._hue, self._sat, self._val, self._alpha)

    def set_color(self, color: QColor) -> None:
        if color.hsvHue() >= 0:
            self._hue = color.hsvHue()
        self._sat = color.hsvSaturation()
        self._val = color.value()
        self._alpha = color.alpha()
        self.update()

    def set_hue(self, hue: int) -> None:
        self._hue = max(0, min(359, int(hue)))
        self.update()

    def set_alpha(self, alpha: int) -> None:
        self._alpha = max(0, min(255, int(alpha)))
        self.update()

    def _field_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(1, 1, -1, -1)

    def _apply_position(self, x: float, y: float) -> None:
        rect = self._field_rect()
        self._sat = max(0, min(255, round(
            (x - rect.left()) / max(1.0, rect.width()) * 255)))
        self._val = max(0, min(255, round(
            (1.0 - (y - rect.top()) / max(1.0, rect.height())) * 255)))
        self.update()
        self.preview.emit(self.color())

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._dragging = True
        self._apply_position(event.position().x(), event.position().y())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._apply_position(event.position().x(), event.position().y())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.committed.emit(self.color())
        event.accept()

    def keyPressEvent(self, event) -> None:
        step = 20 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 4
        key = event.key()
        changed = True
        if key == Qt.Key.Key_Left:
            self._sat = max(0, self._sat - step)
        elif key == Qt.Key.Key_Right:
            self._sat = min(255, self._sat + step)
        elif key == Qt.Key.Key_Up:
            self._val = min(255, self._val + step)
        elif key == Qt.Key.Key_Down:
            self._val = max(0, self._val - step)
        else:
            changed = False
            super().keyPressEvent(event)
        if changed:
            self.update()
            self.preview.emit(self.color())
            self.committed.emit(self.color())
            event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self._field_rect()
        base = QColor.fromHsv(self._hue, 255, 255)
        horizontal = QLinearGradient(rect.left(), 0, rect.right(), 0)
        horizontal.setColorAt(0.0, QColor(255, 255, 255))
        horizontal.setColorAt(1.0, base)
        painter.fillRect(rect, horizontal)
        vertical = QLinearGradient(0, rect.top(), 0, rect.bottom())
        vertical.setColorAt(0.0, QColor(0, 0, 0, 0))
        vertical.setColorAt(1.0, QColor(0, 0, 0, 255))
        painter.fillRect(rect, vertical)

        x = rect.left() + self._sat / 255.0 * rect.width()
        y = rect.top() + (1.0 - self._val / 255.0) * rect.height()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(0, 0, 0, 170), 2))
        painter.drawEllipse(QRectF(x - 5, y - 5, 10, 10))
        painter.setPen(QPen(QColor(255, 255, 255, 230), 1))
        painter.drawEllipse(QRectF(x - 4, y - 4, 8, 8))

        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
        painter.end()


class _ChannelStrip(QWidget):
    preview = pyqtSignal(int)
    committed = pyqtSignal(int)

    def __init__(self, kind: str = "hue", parent=None):
        super().__init__(parent)
        self._kind = kind
        self._value = 0
        self._base = QColor(255, 255, 255)
        self._dragging = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Hue" if kind == "hue" else "Alpha")
        self.setCursor(Qt.CursorShape.SizeHorCursor)

    def value(self) -> int:
        return self._value

    def set_value(self, value: int) -> None:
        maximum = 359 if self._kind == "hue" else 255
        self._value = max(0, min(maximum, int(value)))
        self.update()

    def set_base_color(self, color: QColor) -> None:
        self._base = QColor(color)
        if self._kind == "alpha":
            self.update()

    def _apply(self, x: float) -> None:
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        ratio = max(0.0, min(1.0, (x - rect.left())
                            / max(1.0, rect.width())))
        maximum = 359 if self._kind == "hue" else 255
        self._value = round(ratio * maximum)
        self.update()
        self.preview.emit(self._value)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._dragging = True
        self._apply(event.position().x())
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._apply(event.position().x())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if not self._dragging:
            return
        self._dragging = False
        self.committed.emit(self._value)
        event.accept()

    def keyPressEvent(self, event) -> None:
        maximum = 359 if self._kind == "hue" else 255
        step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Down):
            self._value = max(0, self._value - step)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Up):
            self._value = min(maximum, self._value + step)
        elif event.key() == Qt.Key.Key_Home:
            self._value = 0
        elif event.key() == Qt.Key.Key_End:
            self._value = maximum
        else:
            super().keyPressEvent(event)
            return
        self.update()
        self.preview.emit(self._value)
        self.committed.emit(self._value)
        event.accept()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._kind == "hue":
            gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
            for index in range(7):
                gradient.setColorAt(
                    index / 6.0, QColor.fromHsv(index * 60 % 360, 255, 255))
            painter.fillRect(rect, gradient)
        else:
            checkerboard(painter, rect, 4)
            gradient = QLinearGradient(rect.left(), 0, rect.right(), 0)
            left = QColor(self._base)
            left.setAlpha(0)
            right = QColor(self._base)
            right.setAlpha(255)
            gradient.setColorAt(0.0, left)
            gradient.setColorAt(1.0, right)
            painter.fillRect(rect, gradient)
        maximum = 359 if self._kind == "hue" else 255
        ratio = self._value / maximum if maximum else 0
        x = rect.left() + ratio * rect.width()
        painter.setPen(QPen(QColor(0, 0, 0, 180), 2))
        painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        painter.setPen(QPen(QColor(255, 255, 255, 220), 1))
        painter.drawLine(int(x), int(rect.top()), int(x), int(rect.bottom()))
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.drawRect(rect)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
        painter.end()


class _SwatchButton(QAbstractButton):
    """Palette swatch; value may be a colour or an ``@token``."""

    def __init__(self, label: str, value: str,
                 palette: Optional[dict[str, str]] = None, parent=None):
        super().__init__(parent)
        self._label = label
        self._value = value
        self._palette = palette or {}
        self._hover = False
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(label)
        attach_tooltip(self, f"{label} — {value}")

    def value(self) -> str:
        return self._value

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checkerboard(painter, rect, 3)
        color = resolve_paint_color(self._value, self._palette)
        if color is not None:
            painter.fillRect(rect, color)
        else:
            painter.setPen(QPen(QColor(tokens.TEXT_MUTED), 1))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        painter.setPen(QPen(QColor(tokens.ACCENT if self.hasFocus()
                                   or self._hover else tokens.BORDER_POPOVER),
                           1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()), 4)
        painter.end()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)


class ColorEditor(QWidget):
    """Saturation plane + hue/alpha + hex + palette, without a window.

    Used by ColorField's popover and by PaintField's gradient stop page.
    Signals carry CSS text, never QColor, so the caller can store the same
    shape the theme file accepts.
    """

    preview = pyqtSignal(str)
    committed = pyqtSignal(str)

    def __init__(self, value: Any = "#ffffff", *,
                 palette: Iterable[tuple[str, str]] = (),
                 keywords: Iterable[str] = (), alpha: bool = True,
                 parent=None):
        super().__init__(parent)
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self._keywords = [str(k) for k in keywords]
        self._alpha = bool(alpha)
        self._text = ""
        self._updating = False
        self._last_color = QColor(255, 255, 255, 255)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        self.plane = _ColorPlane(self)
        layout.addWidget(self.plane)

        strip_row = QVBoxLayout()
        strip_row.setContentsMargins(0, 0, 0, 0)
        strip_row.setSpacing(3)
        self.hue = _ChannelStrip("hue", self)
        strip_row.addWidget(self.hue)
        self.alpha = _ChannelStrip("alpha", self)
        self.alpha.setVisible(self._alpha)
        strip_row.addWidget(self.alpha)
        layout.addLayout(strip_row)

        hex_row = QHBoxLayout()
        hex_row.setContentsMargins(0, 0, 0, 0)
        hex_row.setSpacing(tokens.SPACE_4)
        self.hex_edit = QLineEdit(self)
        self.hex_edit.setFixedHeight(tokens.CONTROL_HEIGHT_SM)
        self.hex_edit.setPlaceholderText("#rrggbb or rgba(...)")
        self.hex_edit.setStyleSheet(
            f"QLineEdit {{ background: {tokens.BG_FIELD};"
            f" color: {tokens.TEXT_PRIMARY};"
            f" border: 1px solid {tokens.BORDER_POPOVER};"
            f" border-radius: {tokens.RADIUS_SM}px;"
            f" padding: 0 {tokens.SPACE_8}px;"
            f" font-size: {tokens.TYPE_CAPTION}px;"
            f" selection-background-color: {tokens.ACCENT}; }}"
            f"QLineEdit:focus {{ border-color: {tokens.ACCENT}; }}")
        self.hex_edit.setAccessibleName("Colour value")
        self.hex_edit.returnPressed.connect(self._commit_hex)
        self.hex_edit.editingFinished.connect(self._commit_hex)
        hex_row.addWidget(self.hex_edit, 1)

        self.clear_button = _MiniClear(self)
        self.clear_button.clicked.connect(self._clear)
        self.clear_button.setVisible(False)
        hex_row.addWidget(self.clear_button, 0)
        layout.addLayout(hex_row)

        self.palette_row = FlowRow(self)
        self.palette_layout = self.palette_row.flow
        layout.addWidget(self.palette_row)
        self._palette_buttons: list[_SwatchButton] = []

        self.keyword_row = FlowRow(self)
        self.keyword_layout = self.keyword_row.flow
        layout.addWidget(self.keyword_row)
        self._keyword_buttons: list[_ChipKeyword] = []

        self.plane.preview.connect(self._on_color_preview)
        self.plane.committed.connect(self._on_color_committed)
        self.hue.preview.connect(self._on_hue_preview)
        self.hue.committed.connect(self._on_hue_committed)
        self.alpha.preview.connect(self._on_alpha_preview)
        self.alpha.committed.connect(self._on_alpha_committed)

        self._rebuild_palette()
        self._rebuild_keywords()
        self.set_value(value, emit=False)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> str:
        return self._text

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        self._updating = True
        try:
            self._text = "" if value is None else str(value)
            color = resolve_paint_color(self._text, self._palette_map)
            if color is not None:
                self._last_color = color
                self.plane.set_color(color)
                self.hue.set_value(max(0, color.hsvHue()))
                self.alpha.set_value(color.alpha())
                self.alpha.set_base_color(color)
            self.hex_edit.setText(self._text)
            self._sync_keyword_buttons()
            self._sync_palette_buttons()
        finally:
            self._updating = False
        if emit:
            self.preview.emit(self._text)

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self._rebuild_palette()
        self._sync_palette_buttons()

    def set_keywords(self, keywords: Iterable[str]) -> None:
        self._keywords = [str(k) for k in keywords]
        self._rebuild_keywords()
        self._sync_keyword_buttons()

    def current_color(self) -> QColor:
        return self.plane.color()

    # ── value plumbing ──────────────────────────────────────────────────────
    def _emit(self, text: str, *, commit: bool) -> None:
        self._text = text
        self._updating = True
        try:
            self.hex_edit.setText(text)
            self._sync_keyword_buttons()
            self._sync_palette_buttons()
        finally:
            self._updating = False
        self.preview.emit(text)
        if commit:
            self.committed.emit(text)

    def _on_color_preview(self, color: QColor) -> None:
        if self._updating:
            return
        self._last_color = color
        self.alpha.set_base_color(color)
        self._emit(css_color(color), commit=False)

    def _on_color_committed(self, color: QColor) -> None:
        if self._updating:
            return
        self._last_color = color
        self.alpha.set_base_color(color)
        self._emit(css_color(color), commit=True)

    def _on_hue_preview(self, hue: int) -> None:
        self.plane.set_hue(hue)
        self._on_color_preview(self.plane.color())

    def _on_hue_committed(self, hue: int) -> None:
        self.plane.set_hue(hue)
        self._on_color_committed(self.plane.color())

    def _on_alpha_preview(self, alpha: int) -> None:
        self.plane.set_alpha(alpha)
        self._on_color_preview(self.plane.color())

    def _on_alpha_committed(self, alpha: int) -> None:
        self.plane.set_alpha(alpha)
        self._on_color_committed(self.plane.color())

    def _commit_hex(self) -> None:
        if self._updating:
            return
        raw = self.hex_edit.text().strip()
        if not raw:
            self.hex_edit.setText(self._text)
            return
        normalised = _normalise_text(raw)
        if normalised is None:
            self.hex_edit.setText(self._text)
            return
        if normalised == self._text:
            return
        color = resolve_paint_color(normalised, self._palette_map)
        self._updating = True
        try:
            if color is not None:
                self._last_color = color
                self.plane.set_color(color)
                self.hue.set_value(max(0, color.hsvHue()))
                self.alpha.set_value(color.alpha())
                self.alpha.set_base_color(color)
            self._text = normalised
            self._sync_keyword_buttons()
            self._sync_palette_buttons()
        finally:
            self._updating = False
        self.preview.emit(normalised)
        self.committed.emit(normalised)

    def _clear(self) -> None:
        self._text = ""
        self.hex_edit.setText("")
        self._sync_keyword_buttons()
        self._sync_palette_buttons()
        self.preview.emit("")
        self.committed.emit("")

    # ── palette / keywords ──────────────────────────────────────────────────
    def _rebuild_palette(self) -> None:
        for button in self._palette_buttons:
            self.palette_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._palette_buttons = []
        for label, value in self._palette:
            button = _SwatchButton(label, value, self._palette_map,
                                   self.palette_row)
            button.clicked.connect(
                lambda _checked=False, v=value: self._apply_palette(v))
            self.palette_layout.addWidget(button)
            self._palette_buttons.append(button)
        self.palette_row.setVisible(bool(self._palette))

    def _sync_palette_buttons(self) -> None:
        for button in self._palette_buttons:
            button.update()

    def _apply_palette(self, value: str) -> None:
        color = resolve_paint_color(value, self._palette_map)
        self._updating = True
        try:
            if color is not None:
                self._last_color = color
                self.plane.set_color(color)
                self.hue.set_value(max(0, color.hsvHue()))
                self.alpha.set_value(color.alpha())
                self.alpha.set_base_color(color)
            self._text = value
            self.hex_edit.setText(value)
            self._sync_keyword_buttons()
            self._sync_palette_buttons()
        finally:
            self._updating = False
        self.preview.emit(value)
        self.committed.emit(value)

    def _rebuild_keywords(self) -> None:
        for button in self._keyword_buttons:
            self.keyword_layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._keyword_buttons = []
        for keyword in self._keywords:
            button = _ChipKeyword(keyword, self.keyword_row)
            button.clicked.connect(
                lambda _checked=False, k=keyword: self._apply_keyword(k))
            self.keyword_layout.addWidget(button)
            self._keyword_buttons.append(button)
        self.keyword_row.setVisible(bool(self._keywords))

    def _sync_keyword_buttons(self) -> None:
        folded = self._text.casefold()
        for button in self._keyword_buttons:
            button.setChecked(button.keyword().casefold() == folded)

    def _apply_keyword(self, keyword: str) -> None:
        self._text = keyword
        self._updating = True
        try:
            self.hex_edit.setText(keyword)
            self._sync_keyword_buttons()
            self._sync_palette_buttons()
        finally:
            self._updating = False
        self.preview.emit(keyword)
        self.committed.emit(keyword)


class _ChipKeyword(QAbstractButton):
    def __init__(self, keyword: str, parent=None):
        super().__init__(parent)
        self._keyword = keyword
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(keyword)
        self.setAccessibleName(keyword)
        metrics = QFontMetrics(font(tokens.TYPE_CAPTION))
        self.setFixedSize(metrics.horizontalAdvance(keyword) + 16,
                          tokens.CONTROL_HEIGHT_SM)

    def keyword(self) -> str:
        return self._keyword

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        checked = self.isChecked()
        painter.setPen(QPen(QColor(tokens.ACCENT if checked
                                   else tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.ACCENT_TINT if checked
                                else tokens.BG_FIELD))
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setFont(font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(tokens.TEXT_PRIMARY if checked
                              else tokens.TEXT_SECONDARY))
        painter.drawText(
            rect, int(Qt.AlignmentFlag.AlignCenter),
            elide(self._keyword, rect.width() - 10))
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()), 4)
        painter.end()


class _ColorPopover(PopupSurface):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, field: "ColorField"):
        super().__init__(field.window())
        self._field = field
        self._cancelled = False
        self.editor = ColorEditor(
            field._value, palette=field._palette,
            keywords=field._keywords, alpha=field._alpha)
        self.content.addWidget(self.editor)
        self.editor.preview.connect(field._on_popover_preview)
        self.editor.committed.connect(self._on_committed)
        self.setMinimumWidth(238)

    def _on_committed(self, text: str) -> None:
        self.committed.emit(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._cancelled:
            self.cancelled.emit()
        else:
            text = self.editor.value()
            if text != self._field._value:
                self.committed.emit(text)
        super().closeEvent(event)


class ColorField(QWidget):
    """Compact swatch + colour text, opening the kit colour popover.

    Signals
        changed(object) — a CSS colour/token string, or None when cleared.
        preview(object) — live value while the popover drags.

    Args
        palette: ``[(label, value)]``; value may be a colour or ``@token``.
        keywords: extra accepted strings shown as chips (``inherit``,
            ``currentColor``, ``transparent``...).
        nullable: shows a clear button and emits None.
        alpha: exposes the alpha strip in the popover.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "#ffffff", *,
                 palette: Iterable[tuple[str, str]] = (),
                 keywords: Iterable[str] = (), nullable: bool = False,
                 alpha: bool = True, placeholder: str = _TOKEN_EMPTY_LABEL,
                 parent=None):
        super().__init__(parent)
        self._value = "" if value is None else str(value)
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self._keywords = [str(k) for k in keywords]
        self._nullable = bool(nullable)
        self._alpha = bool(alpha)
        self._placeholder = placeholder
        self._hover = False
        self._warning = ""
        self._popover: Optional[_ColorPopover] = None
        self._swatch_hover = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 0, 4, 0)
        layout.setSpacing(5)
        self._swatch = _FieldSwatch(self)
        self._swatch.clicked.connect(self._open_popover)
        layout.addWidget(self._swatch, 0)

        self._edit = QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none;"
            f" color: {tokens.TEXT_PRIMARY};"
            f" padding: 0px; font-size: {tokens.TYPE_CAPTION}px;"
            f" selection-background-color: {tokens.ACCENT};"
            f" selection-color: {tokens.TEXT_PRIMARY}; }}")
        self._edit.setPlaceholderText(self._placeholder)
        self._edit.setAccessibleName("Colour value")
        self._edit.editingFinished.connect(self._commit_text)
        self._edit.returnPressed.connect(self._commit_text)
        layout.addWidget(self._edit, 1)

        self._clear = _MiniClear(self)
        self._clear.clicked.connect(self._clear_value)
        layout.addWidget(self._clear, 0)
        self._clear.setVisible(False)

        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setFocusProxy(self._edit)
        self.setMouseTracking(True)
        self._edit.installEventFilter(self)
        attach_tooltip(self, lambda: self._warning or self._value
                       or self._placeholder)
        self._sync()

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        return self._value or None

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        text = "" if value is None else str(value)
        if text == self._value:
            self._sync()
            return
        self._value = text
        self._sync()
        if emit:
            self.changed.emit(self.value())

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self._swatch.update()

    def set_keywords(self, keywords: Iterable[str]) -> None:
        self._keywords = [str(k) for k in keywords]

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self._edit.setAccessibleName(text)
        self._swatch.setAccessibleName(text or "Choose colour")

    # ── syncing ─────────────────────────────────────────────────────────────
    def _sync(self) -> None:
        self._edit.setText(self._value)
        self._clear.setVisible(self._nullable and bool(self._value))
        self._swatch.set_value(self._value, self._palette_map)
        self.update()

    def _commit_text(self) -> None:
        raw = self._edit.text().strip()
        if not raw:
            if self._nullable and self._value:
                self._value = ""
                self._sync()
                self.changed.emit(None)
            else:
                self._edit.setText(self._value)
            return
        normalised = _normalise_text(raw)
        if normalised is None:
            # Not something the kit can paint. Keep the caller's text; the
            # caller is the validator and may show a warning.
            self._value = raw
            self._sync()
            self.changed.emit(raw)
            return
        if normalised == self._value:
            self._sync()
            return
        self._value = normalised
        self._sync()
        self.changed.emit(normalised)

    def _clear_value(self) -> None:
        if not self._nullable or not self._value:
            return
        self._value = ""
        self._sync()
        self.changed.emit(None)

    # ── popover ─────────────────────────────────────────────────────────────
    def _open_popover(self) -> None:
        if not self.isEnabled():
            return
        if self._popover is not None:
            self._popover.close()
            return
        popover = _ColorPopover(self)
        self._popover = popover
        self._open_value = self._value
        popover.committed.connect(self._on_popover_committed)
        popover.cancelled.connect(self._on_popover_cancelled)
        popover.destroyed.connect(self._on_popover_destroyed)
        popover.show_below(self, width=248, max_height=400,
                           align="left")

    def _on_popover_preview(self, text: str) -> None:
        self._value = "" if text is None else str(text)
        self._edit.setText(self._value)
        self._swatch.set_value(self._value, self._palette_map)
        self._clear.setVisible(self._nullable and bool(self._value))
        self.preview.emit(self.value())

    def _on_popover_committed(self, text: str) -> None:
        text = "" if text is None else str(text)
        if text == self._value:
            return
        self._value = text
        self._sync()
        self.changed.emit(self.value())

    def _on_popover_cancelled(self) -> None:
        self._value = getattr(self, "_open_value", self._value)
        self._sync()
        self.preview.emit(self.value())

    def _on_popover_destroyed(self, *_args) -> None:
        self._popover = None

    # ── events / painting ───────────────────────────────────────────────────
    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit:
            if event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut):
                self.update()
        return super().eventFilter(obj, event)

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
        focused = self._edit.hasFocus() or (
            self._popover is not None and self._popover.isVisible())
        surface = tokens.BG_FIELD if enabled else tokens.BG_PANEL
        if not enabled:
            edge = tokens.BORDER_HAIRLINE
        elif focused:
            edge = tokens.ACCENT
        elif self._warning:
            edge = tokens.WARNING
        elif self._hover:
            edge = tokens.BORDER_POPOVER
        else:
            edge = tokens.BORDER_HAIRLINE
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)
        if focused:
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(150, tokens.CONTROL_HEIGHT)


class _FieldSwatch(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = ""
        self._palette: dict[str, str] = {}
        self._hover = False
        self.setFixedSize(20, 20)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("Choose colour")
        attach_tooltip(self, lambda: self._value or "Choose colour")

    def set_value(self, value: str, palette: dict[str, str]) -> None:
        self._value = value or ""
        self._palette = palette
        self.update()

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
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        checkerboard(painter, rect, 3)
        color = resolve_paint_color(self._value, self._palette)
        if color is not None:
            painter.fillRect(rect, color)
        elif self._value:
            painter.setPen(QPen(QColor(tokens.TEXT_MUTED), 1))
            painter.drawLine(rect.topLeft(), rect.bottomRight())
        else:
            painter.setPen(QPen(QColor(tokens.TEXT_MUTED), 1))
            painter.drawLine(
                QPointF(rect.left() + 5, rect.bottom() - 5),
                QPointF(rect.right() - 5, rect.top() + 5))
        painter.setPen(QPen(QColor(
            tokens.ACCENT if self.hasFocus() or self._hover
            else tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()), 4)
        painter.end()


class _MiniClear(QAbstractButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName("Clear colour")
        attach_tooltip(self, "Clear (not set)")

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        color = tokens.TEXT_SECONDARY if self.underMouse() else tokens.TEXT_MUTED
        painter.setPen(QPen(QColor(color), 1.2))
        painter.drawLine(4, 4, self.width() - 4, self.height() - 4)
        painter.drawLine(self.width() - 4, 4, 4, self.height() - 4)
        painter.end()


__all__ = [
    "ColorField", "ColorEditor", "parse_css_color", "css_color",
    "resolve_paint_color",
]
