"""ui/theme_kit/anchor_picker.py

AnchorPicker — a 3×3 anchor grid plus Fill, and AnchorRow, the same picker
paired with optional x/y offsets.

Anchor values are plain strings supplied by the caller (``top_left``,
``center``, ``fill``...). The widget never validates them against a schema; it
only paints and reports the value the caller asked for.
"""

from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget

from ui import tokens
from ui.theme_kit.base import font, paint_focus_ring
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip

#: Grid order. Row-major, exactly what the arrow keys walk.
ANCHOR_GRID = (
    ("top_left", "top", "top_right"),
    ("left", "center", "right"),
    ("bottom_left", "bottom", "bottom_right"),
)
ANCHORS = tuple(value for row in ANCHOR_GRID for value in row) + ("fill",)
_GRID_INDEX = {value: (row, column)
               for row, values in enumerate(ANCHOR_GRID)
               for column, value in enumerate(values)}


class AnchorPicker(QWidget):
    """A compact 3×3 anchor grid with an optional Fill row.

    Signals
        changed(object) — the selected anchor string.
    """

    changed = pyqtSignal(object)

    def __init__(self, value: Any = "center", *,
                 allow_fill: bool = True, cell: int = 22,
                 accessible_name: str = "Anchor", parent=None):
        super().__init__(parent)
        self._value = str(value or "center")
        self._allow_fill = bool(allow_fill)
        self._cell = int(cell)
        self._hover: Optional[str] = None
        self._focus_index = 0
        self._pressed: Optional[str] = None
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName(accessible_name)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        attach_tooltip(self, lambda: self._value.replace("_", " ").title())

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> str:
        return self._value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        text = str(value or "").strip()
        if text not in ANCHORS or (text == "fill" and not self._allow_fill):
            return
        if text == self._value:
            return
        self._value = text
        self._focus_index = self._index_for(text)
        self.update()
        if emit:
            self.changed.emit(text)

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    def options(self) -> list[str]:
        values = list(ANCHORS[:-1])
        if self._allow_fill:
            values.append("fill")
        return values

    # ── geometry ────────────────────────────────────────────────────────────
    @staticmethod
    def _gap() -> int:
        return 2

    def _grid_width(self) -> int:
        return self._cell * 3 + self._gap() * 2

    def _grid_origin(self) -> QPointF:
        width = self._grid_width()
        height = width
        total_height = height + (20 if self._allow_fill else 0)
        return QPointF(max(0.0, (self.width() - width) / 2),
                       max(0.0, (self.height() - total_height) / 2))

    def _cell_rect(self, row: int, column: int) -> QRectF:
        origin = self._grid_origin()
        step = self._cell + self._gap()
        return QRectF(origin.x() + column * step,
                      origin.y() + row * step,
                      self._cell, self._cell)

    def _fill_rect(self) -> QRectF:
        origin = self._grid_origin()
        return QRectF(origin.x(), origin.y() + self._grid_width() + 4,
                      self._grid_width(), 16)

    def _anchor_at(self, position: QPointF) -> Optional[str]:
        for row, values in enumerate(ANCHOR_GRID):
            for column, value in enumerate(values):
                if self._cell_rect(row, column).contains(position):
                    return value
        if self._allow_fill and self._fill_rect().contains(position):
            return "fill"
        return None

    def sizeHint(self) -> QSize:
        width = self._grid_width()
        return QSize(width, width + (20 if self._allow_fill else 0))

    def minimumSizeHint(self) -> QSize:
        return self.sizeHint()

    # ── focus ───────────────────────────────────────────────────────────────
    def _index_for(self, value: str) -> int:
        values = self.options()
        try:
            return values.index(value)
        except ValueError:
            return 4

    def _focus_value(self) -> str:
        options = self.options()
        if not options:
            return "center"
        return options[self._focus_index % len(options)]

    def _move_focus(self, dx: int, dy: int) -> None:
        value = self._focus_value()
        if value == "fill":
            if dy < 0:
                self._focus_index = self._index_for("bottom")
            return
        row, column = _GRID_INDEX[value]
        row = max(0, min(2, row + dy))
        column = max(0, min(2, column + dx))
        self._focus_index = self._index_for(ANCHOR_GRID[row][column])
        self.update()

    # ── interaction ─────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event) -> None:
        anchor = self._anchor_at(event.position())
        if anchor != self._hover:
            self._hover = anchor
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._pressed = self._anchor_at(event.position())
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        anchor = self._anchor_at(event.position())
        if anchor is not None and anchor == self._pressed:
            self._focus_index = self._index_for(anchor)
            self._select(anchor)
        self._pressed = None
        event.accept()

    def _select(self, anchor: str) -> None:
        if anchor == self._value:
            return
        self._value = anchor
        self.update()
        self.changed.emit(anchor)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right,
                   Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._move_focus(-1 if key == Qt.Key.Key_Left else
                             1 if key == Qt.Key.Key_Right else 0,
                             -1 if key == Qt.Key.Key_Up else
                             1 if key == Qt.Key.Key_Down else 0)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self._focus_index = 0
            self.update()
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self._focus_index = len(self.options()) - 1
            self.update()
            event.accept()
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._select(self._focus_value())
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self._focus_index = self._index_for(self._value)
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    # ── painting ────────────────────────────────────────────────────────────
    def _paint_cell(self, painter: QPainter, rect: QRectF, value: str,
                    *, focused: bool, hovered: bool, selected: bool) -> None:
        enabled = self.isEnabled()
        if not enabled:
            fill, edge, ink = (tokens.BG_PANEL, tokens.BORDER_HAIRLINE,
                               tokens.TEXT_MUTED)
        elif selected:
            fill, edge, ink = (tokens.ACCENT_TINT, tokens.ACCENT,
                               tokens.ACCENT_TEXT)
        elif hovered:
            fill, edge, ink = (tokens.BG_CARD_HOVER,
                               tokens.BORDER_POPOVER, tokens.TEXT_PRIMARY)
        else:
            fill, edge, ink = (tokens.BG_FIELD, tokens.BORDER_HAIRLINE,
                               tokens.TEXT_SECONDARY)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                tokens.RADIUS_SM, tokens.RADIUS_SM)
        if value == "fill":
            painter.setFont(font(10, tokens.WEIGHT_SEMIBOLD))
            painter.setPen(QColor(ink))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "Fill")
        else:
            self._paint_anchor_mark(painter, rect, value, ink)
        if focused:
            paint_focus_ring(painter, rect, tokens.RADIUS_SM)

    def _paint_anchor_mark(self, painter: QPainter, rect: QRectF,
                           value: str, color: str) -> None:
        painter.setPen(QPen(QColor(color), 1.3))
        painter.setBrush(QColor(color))
        inner = rect.adjusted(6, 6, -6, -6)
        row, column = _GRID_INDEX[value]
        size = 3.0
        x = (inner.left() if column == 0 else
             inner.right() if column == 2 else inner.center().x())
        y = (inner.top() if row == 0 else
             inner.bottom() if row == 2 else inner.center().y())
        if row == 1 and column == 1:
            painter.drawEllipse(QPointF(x, y), 2.6, 2.6)
            return
        painter.drawRoundedRect(QRectF(x - size, y - size,
                                       size * 2, size * 2), 1.2, 1.2)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        focus_value = self._focus_value() if self.hasFocus() else ""
        for row, values in enumerate(ANCHOR_GRID):
            for column, value in enumerate(values):
                self._paint_cell(
                    painter, self._cell_rect(row, column), value,
                    focused=bool(focus_value == value),
                    hovered=self._hover == value,
                    selected=self._value == value)
        if self._allow_fill:
            self._paint_cell(
                painter, self._fill_rect(), "fill",
                focused=bool(focus_value == "fill"),
                hovered=self._hover == "fill",
                selected=self._value == "fill")
        painter.end()


class AnchorRow(QWidget):
    """AnchorPicker plus optional x/y offset fields.

    Signals
        changed(object) — ``{"anchor": str, "x": ..., "y": ...}``; ``x``/``y``
        are omitted while the anchor is ``fill``.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = None, *, show_offsets: bool = False,
                 x_key: str = "x", y_key: str = "y",
                 x_range=(-10000, 10000), y_range=(-10000, 10000),
                 parent=None):
        super().__init__(parent)
        data = value if isinstance(value, dict) else {}
        anchor = data.get("anchor", value if isinstance(value, str)
                          else "center")
        self._x_key = x_key
        self._y_key = y_key
        self._show_offsets = bool(show_offsets)
        self._updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_8)
        self.picker = AnchorPicker(anchor)
        layout.addWidget(self.picker, 0)
        self.x_field: Optional[NumberField] = None
        self.y_field: Optional[NumberField] = None
        if self._show_offsets:
            offsets = QVBoxLayout()
            offsets.setContentsMargins(0, 0, 0, 0)
            offsets.setSpacing(tokens.SPACE_4)
            self.x_field = NumberField(
                data.get(x_key, 0), minimum=x_range[0],
                maximum=x_range[1], step=1, units=["px", "%"],
                label="Horizontal offset")
            self.y_field = NumberField(
                data.get(y_key, 0), minimum=y_range[0],
                maximum=y_range[1], step=1, units=["px", "%"],
                label="Vertical offset")
            offsets.addWidget(self.x_field)
            offsets.addWidget(self.y_field)
            layout.addLayout(offsets, 1)
            self.x_field.changed.connect(self._emit)
            self.x_field.preview.connect(self._emit_preview)
            self.y_field.changed.connect(self._emit)
            self.y_field.preview.connect(self._emit_preview)
            self._sync_offsets()
        self.picker.changed.connect(self._on_anchor)

    def _on_anchor(self, _anchor: str) -> None:
        self._sync_offsets()
        self.changed.emit(self.value())

    def _sync_offsets(self) -> None:
        if not self._show_offsets:
            return
        enabled = self.picker.value() != "fill"
        assert self.x_field is not None and self.y_field is not None
        self.x_field.setEnabled(enabled)
        self.y_field.setEnabled(enabled)

    def value(self) -> dict[str, Any]:
        data: dict[str, Any] = {"anchor": self.picker.value()}
        if self._show_offsets and self.picker.value() != "fill":
            assert self.x_field is not None and self.y_field is not None
            data[self._x_key] = self.x_field.value()
            data[self._y_key] = self.y_field.value()
        return data

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        data = value if isinstance(value, dict) else {"anchor": value}
        self._updating = True
        try:
            self.picker.set_value(data.get("anchor", "center"))
            if self._show_offsets:
                assert self.x_field is not None and self.y_field is not None
                self.x_field.set_value(data.get(self._x_key, 0))
                self.y_field.set_value(data.get(self._y_key, 0))
                self._sync_offsets()
        finally:
            self._updating = False
        if emit:
            self.changed.emit(self.value())

    def _emit(self, *_args) -> None:
        if not self._updating:
            self.changed.emit(self.value())

    def _emit_preview(self, *_args) -> None:
        if not self._updating:
            self.preview.emit(self.value())


__all__ = ["AnchorPicker", "AnchorRow", "ANCHOR_GRID", "ANCHORS"]
