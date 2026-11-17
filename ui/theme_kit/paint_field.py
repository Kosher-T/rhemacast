"""ui/theme_kit/paint_field.py

PaintField — a compact colour-or-gradient control with a painted popover.

Solid colours reuse ``ColorEditor``; gradients get a structured editor
(linear/radial, angle, stop rows) that emits standard CSS. An unrecognised
gradient is preserved through a raw CSS field rather than being flattened into
a default.

The caller decides whether gradients/none are allowed. Schema validation is
still the caller's job; this widget only builds shapes a browser accepts.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFontMetrics, QLinearGradient, QPainter, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QHBoxLayout, QLineEdit, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, checkerboard, draw_chevron, elide, font, format_number,
    paint_focus_ring, parse_number_text,
)
from ui.theme_kit.color_field import (
    ColorEditor, css_color, parse_css_color, resolve_paint_color,
)
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import PopupSurface, attach_tooltip
from ui.theme_kit.segmented import SegmentedToggle
from ui.theme_kit.small import IconButton, InlineMessage

_GRADIENT_RE = re.compile(r"^(linear|radial)-gradient\((.+)\)$", re.I | re.S)
_NUM_POS_RE = re.compile(r"^(-?\d+(?:\.\d+)?)%?$")


@dataclass
class GradientStop:
    at: Optional[float] = 0.0
    color: str = "#ffffff"


@dataclass
class GradientSpec:
    kind: str = "linear"
    angle: float = 180.0
    shape: str = "circle"
    stops: list[GradientStop] = field(default_factory=list)


# ─── Parsing / formatting ───────────────────────────────────────────────────

def _split_top_level(text: str, separator: str = ",") -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char == separator and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return [part for part in parts if part]


def _last_top_level_space(text: str) -> int:
    depth = 0
    index = -1
    for position, char in enumerate(text):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char.isspace() and depth == 0:
            index = position
    return index


def _parse_stop(part: str) -> Optional[GradientStop]:
    text = part.strip()
    if not text:
        return None
    at: Optional[float] = None
    color_text = text
    split = _last_top_level_space(text)
    if split > 0:
        tail = text[split + 1:].strip()
        match = _NUM_POS_RE.match(tail)
        if match:
            at = max(0.0, min(100.0, float(match.group(1))))
            color_text = text[:split].strip()
    # A second position token ("red 0% 40%") is not a shape this editor owns.
    if _last_top_level_space(color_text) > 0:
        tail = color_text[_last_top_level_space(color_text) + 1:].strip()
        if _NUM_POS_RE.match(tail):
            return None
    if parse_css_color(color_text) is None and not color_text.startswith("@"):
        return None
    return GradientStop(at, color_text)


def _angle_from_keyword(text: str) -> Optional[float]:
    low = text.strip().lower()
    if low.endswith("deg"):
        number = parse_number_text(low[:-3])
        return None if number is None else float(number) % 360.0
    mapping = {
        "to top": 0.0, "to top right": 45.0, "to right": 90.0,
        "to bottom right": 135.0, "to bottom": 180.0,
        "to bottom left": 225.0, "to left": 270.0,
        "to top left": 315.0,
    }
    return mapping.get(low)


def parse_gradient(text: Any) -> Optional[GradientSpec]:
    if text is None:
        return None
    match = _GRADIENT_RE.match(str(text).strip())
    if not match:
        return None
    kind = match.group(1).lower()
    parts = _split_top_level(match.group(2))
    if not parts:
        return None
    spec = GradientSpec(kind=kind)
    if kind == "linear":
        angle = _angle_from_keyword(parts[0])
        if angle is not None:
            spec.angle = angle
            parts = parts[1:]
    else:
        first = parts[0].strip().lower()
        if first == "circle":
            spec.shape = "circle"
            parts = parts[1:]
        elif first == "ellipse":
            spec.shape = "ellipse"
            parts = parts[1:]
        elif first.startswith(("circle ", "ellipse ", "at ", "closest-",
                               "farthest-")):
            # Shape/size/position syntax this structured editor does not
            # own; keep the original string via raw mode instead of
            # silently dropping the position.
            return None
    for part in parts:
        stop = _parse_stop(part)
        if stop is None:
            return None
        spec.stops.append(stop)
    if not spec.stops:
        return None
    return spec


def format_gradient(spec: GradientSpec) -> str:
    if not spec.stops:
        return "none"
    if spec.kind == "radial":
        head = spec.shape or "circle"
    else:
        head = f"{format_number(spec.angle, decimals=1)}deg"
    pieces = [head]
    for stop in spec.stops:
        if stop.at is None:
            pieces.append(stop.color)
        else:
            pieces.append(
                f"{stop.color} {format_number(stop.at, decimals=1)}%")
    return f"{spec.kind}-gradient({', '.join(pieces)})"


def _resolved_positions(stops: list[GradientStop]) -> list[float]:
    positions: list[Optional[float]] = [stop.at for stop in stops]
    if not positions:
        return []
    if positions[0] is None:
        positions[0] = 0.0
    if positions[-1] is None:
        positions[-1] = 100.0
    index = 0
    while index < len(positions):
        if positions[index] is not None:
            index += 1
            continue
        start = index - 1
        end = index
        while end < len(positions) and positions[end] is None:
            end += 1
        left = positions[start] if positions[start] is not None else 0.0
        right = positions[end] if end < len(positions) and positions[
            end] is not None else 100.0
        count = end - start
        for offset in range(1, count):
            positions[start + offset] = left + (right - left) * offset / count
        index = end
    return [float(max(0.0, min(100.0, value))) for value in positions]


def paint_gradient(painter: QPainter, rect: QRectF, spec: GradientSpec,
                   palette: Optional[dict[str, str]] = None) -> None:
    positions = _resolved_positions(spec.stops)
    colors: list[QColor] = []
    for stop in spec.stops:
        color = resolve_paint_color(stop.color, palette)
        colors.append(color if color is not None else QColor(0, 0, 0, 0))
    if not colors:
        return
    if spec.kind == "radial":
        centre = rect.center()
        radius = max(rect.width(), rect.height()) / 2
        gradient = QRadialGradient(centre, max(1.0, radius))
    else:
        angle = math.radians(spec.angle)
        dx, dy = math.sin(angle), -math.cos(angle)
        half = (abs(dx) * rect.width() + abs(dy) * rect.height()) / 2
        centre = rect.center()
        gradient = QLinearGradient(
            centre.x() - dx * half, centre.y() - dy * half,
            centre.x() + dx * half, centre.y() + dy * half)
    for position, color in zip(positions, colors):
        gradient.setColorAt(max(0.0, min(1.0, position / 100.0)), color)
    painter.fillRect(rect, gradient)


def paint_value(painter: QPainter, rect: QRectF, value: Any,
                palette: Optional[dict[str, str]] = None) -> None:
    checkerboard(painter, rect)
    if value is None or str(value).strip().lower() in ("", "none"):
        return
    spec = parse_gradient(value)
    if spec is not None:
        paint_gradient(painter, rect, spec, palette)
        return
    color = resolve_paint_color(value, palette)
    if color is not None:
        painter.fillRect(rect, color)


def paint_mode(value: Any) -> str:
    """Derive the editor mode from a stored paint value.

    The mode is never stored: none/empty/fully transparent is ``"none"``, a
    gradient is ``"gradient"`` and anything else that paints is ``"solid"``.
    """
    if value is None:
        return "none"
    text = str(value).strip()
    if not text:
        return "none"
    if text.casefold() in ("none", "transparent"):
        return "none"
    if parse_gradient(text) is not None:
        return "gradient"
    color = parse_css_color(text)
    if color is not None and color.alpha() == 0:
        return "none"
    return "solid"


def _describe(value: Any, palette: Optional[dict[str, str]] = None) -> str:
    """Collapsed-field text: hex for solids, ``Gradient``, ``None``.

    ``#rrggbbaa`` is only ever shown as eight digits when the colour is
    actually translucent; a transparent value is "None", never a hex string.
    """
    if paint_mode(value) == "none":
        return "None"
    text = str(value).strip()
    if parse_gradient(text) is not None:
        return "Gradient"
    # Show the colour, not a symbolic name: theme files may store ``@gold``
    # but the field paints hex.
    color = resolve_paint_color(text, palette)
    if color is None:
        return text
    return css_color(color, force_alpha=color.alpha() < 255)


# ─── Painted pieces ─────────────────────────────────────────────────────────

class _PaintSwatch(QWidget):
    def __init__(self, value: Any = "#ffffff", *,
                 palette: Optional[dict[str, str]] = None, parent=None):
        super().__init__(parent)
        self._value = value
        self._palette = palette or {}
        self.setFixedSize(20, 20)

    def set_value(self, value: Any,
                  palette: Optional[dict[str, str]] = None) -> None:
        self._value = value
        if palette is not None:
            self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        paint_value(painter, rect, self._value, self._palette)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)
        painter.end()


def _mix_color(left: QColor, right: QColor, ratio: float) -> QColor:
    ratio = max(0.0, min(1.0, float(ratio)))
    return QColor(
        round(left.red() + (right.red() - left.red()) * ratio),
        round(left.green() + (right.green() - left.green()) * ratio),
        round(left.blue() + (right.blue() - left.blue()) * ratio),
        round(left.alpha() + (right.alpha() - left.alpha()) * ratio))


def sample_gradient(spec: GradientSpec, position: float,
                    palette: Optional[dict[str, str]] = None) -> str:
    """Colour of *spec* at *position* (0–100), as a CSS colour string."""
    positions = _resolved_positions(spec.stops)
    colors = [resolve_paint_color(stop.color, palette) or QColor(0, 0, 0, 0)
              for stop in spec.stops]
    if not colors:
        return "#ffffff"
    at = max(0.0, min(100.0, float(position)))
    if at <= positions[0]:
        return css_color(colors[0])
    if at >= positions[-1]:
        return css_color(colors[-1])
    for index in range(len(positions) - 1):
        left, right = positions[index], positions[index + 1]
        if left <= at <= right:
            span = right - left
            ratio = 0.0 if span <= 0 else (at - left) / span
            return css_color(_mix_color(colors[index], colors[index + 1], ratio))
    return css_color(colors[-1])


class _GradientBar(QWidget):
    """The gradient ramp: the gradient plus one draggable handle per stop.

    Clicking the ramp adds a stop at that position, dragging a handle moves it
    and right-click (or Delete) removes one above the minimum. Structural
    edits are the owner's job — this widget reports them — while a drag
    mutates the shared :class:`GradientSpec` in place, so the ramp and the
    preview follow the cursor without rebuilding the editor.
    """

    preview = pyqtSignal()
    changed = pyqtSignal()
    add_requested = pyqtSignal(float)
    remove_requested = pyqtSignal(int)
    selected_changed = pyqtSignal(int)

    _RAMP_TOP = 2.0
    _RAMP_HEIGHT = 17.0
    _SIDE = 7.0
    _HANDLE = 9.0

    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec = GradientSpec(stops=[
            GradientStop(0.0, "#ffffff"), GradientStop(100.0, "#000000")])
        self._palette: dict[str, str] = {}
        self._selected = 0
        self._drag: Optional[int] = None
        self.setFixedHeight(34)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Gradient ramp")
        attach_tooltip(self, "Click the ramp to add a stop, drag a handle to "
                            "move it, right-click to remove")

    # ── public ──────────────────────────────────────────────────────────────
    def set_spec(self, spec: GradientSpec,
                 palette: Optional[dict[str, str]] = None) -> None:
        self._spec = spec
        if palette is not None:
            self._palette = palette
        self._selected = max(0, min(self._selected, len(spec.stops) - 1))
        self.update()

    def selected(self) -> int:
        return self._selected

    def set_selected(self, index: int, *, emit: bool = False) -> None:
        count = len(self._spec.stops)
        if not count:
            return
        index = max(0, min(int(index), count - 1))
        changed = index != self._selected
        self._selected = index
        self.update()
        if changed and emit:
            self.selected_changed.emit(index)

    # ── geometry ────────────────────────────────────────────────────────────
    def _ramp(self) -> QRectF:
        return QRectF(self._SIDE, self._RAMP_TOP,
                      max(1.0, self.width() - self._SIDE * 2),
                      self._RAMP_HEIGHT)

    def _x_for(self, position: float) -> float:
        ramp = self._ramp()
        return ramp.left() + ramp.width() * max(0.0, min(100.0, position)) / 100.0

    def _position_at(self, x: float) -> float:
        ramp = self._ramp()
        if ramp.width() <= 0:
            return 0.0
        return max(0.0, min(100.0, (x - ramp.left()) / ramp.width() * 100.0))

    def _stop_at(self, x: float) -> Optional[int]:
        best: Optional[int] = None
        best_gap = self._HANDLE + 3
        for index, position in enumerate(_resolved_positions(self._spec.stops)):
            gap = abs(self._x_for(position) - x)
            if gap <= best_gap:
                best_gap = gap
                best = index
        return best

    def _handle_rect(self, index: int) -> QRectF:
        positions = _resolved_positions(self._spec.stops)
        at = positions[index] if index < len(positions) else 0.0
        centre_y = self._RAMP_TOP + self._RAMP_HEIGHT + 6
        size = self._HANDLE
        return QRectF(self._x_for(at) - size / 2, centre_y - size / 2,
                      size, size)

    # ── painting ────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        ramp = self._ramp()
        checkerboard(painter, ramp, 4)
        paint_gradient(painter, ramp, self._spec, self._palette)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(ramp, 4, 4)
        for index, stop in enumerate(self._spec.stops):
            rect = self._handle_rect(index)
            color = resolve_paint_color(stop.color, self._palette)
            painter.setBrush(color or QColor(255, 255, 255, 255))
            selected = index == self._selected
            painter.setPen(QPen(
                QColor(tokens.ACCENT if selected else tokens.BORDER_POPOVER),
                2 if selected else 1))
            painter.drawEllipse(rect)
        painter.end()

    # ── interaction ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            index = self._stop_at(event.position().x())
            if index is not None:
                self.remove_requested.emit(index)
            event.accept()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        x = event.position().x()
        index = self._stop_at(x)
        if index is None:
            self.add_requested.emit(self._position_at(x))
            event.accept()
            return
        self.set_selected(index, emit=True)
        self._drag = index
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None or self._drag >= len(self._spec.stops):
            super().mouseMoveEvent(event)
            return
        position = self._position_at(event.position().x())
        self._spec.stops[self._drag].at = position
        self.update()
        self.preview.emit()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if self._drag is not None and event.button() == Qt.MouseButton.LeftButton:
            self._drag = None
            self.changed.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        count = len(self._spec.stops)
        if not count:
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.remove_requested.emit(self._selected)
            event.accept()
            return
        step = 5.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            stop = self._spec.stops[self._selected]
            current = stop.at
            if current is None:
                current = _resolved_positions(self._spec.stops)[self._selected]
            delta = -step if event.key() == Qt.Key.Key_Left else step
            stop.at = max(0.0, min(100.0, current + delta))
            self.update()
            self.preview.emit()
            self.changed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class GradientEditor(QWidget):
    """Structured linear/radial gradient editor.

    The ramp owns positions; one :class:`ColorEditor` edits the selected
    stop's colour (plane, hue, alpha and hex), so a gradient is edited with
    exactly the same control as a solid.

    Signals
        preview(str) — live CSS while a stop or the angle is dragged.
        changed(str) — committed CSS (release, add/remove, kind/angle, hex).
    """

    preview = pyqtSignal(str)
    changed = pyqtSignal(str)

    def __init__(self, value: Any = "", *,
                 palette: Iterable[tuple[str, str]] = (),
                 min_stops: int = 2, max_stops: int = 12,
                 parent=None):
        super().__init__(parent)
        self._palette = list(palette)
        self._spec = GradientSpec(stops=[
            GradientStop(0.0, "#ffffff"), GradientStop(100.0, "#000000")])
        self._min_stops = max(2, min_stops)
        self._max_stops = max(self._min_stops, max_stops)
        self._updating = False
        self._raw_mode = False
        self._selected = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        self.bar = _GradientBar(self)
        self.bar.preview.connect(self._on_bar_preview)
        self.bar.changed.connect(self._on_bar_changed)
        self.bar.add_requested.connect(self._add_stop_at)
        self.bar.remove_requested.connect(self._remove_stop_at)
        self.bar.selected_changed.connect(self._on_selected)
        layout.addWidget(self.bar)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(tokens.SPACE_4)
        self.kind = SegmentedToggle(
            [ChoiceOption("linear", "Linear"), ChoiceOption("radial", "Radial")],
            "linear", accessible_name="Gradient type")
        controls.addWidget(self.kind, 1)
        self.angle = NumberField(
            180, minimum=0, maximum=360, step=5, suffix="°",
            label="Gradient angle")
        self.angle.setFixedWidth(66)
        controls.addWidget(self.angle, 0)
        layout.addLayout(controls)

        self.stop_editor = ColorEditor(
            "#ffffff", palette=self._palette, alpha=True)
        self.stop_editor.preview.connect(self._on_stop_preview)
        self.stop_editor.committed.connect(self._on_stop_committed)
        layout.addWidget(self.stop_editor)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(tokens.SPACE_4)
        self.add_button = IconButton(glyph="plus", text="Add stop",
                                     tooltip="Add a gradient stop",
                                     parent=self)
        self.add_button.clicked.connect(self._add_stop)
        actions.addWidget(self.add_button, 0)
        self.count_label = InlineMessage("", role="muted")
        actions.addWidget(self.count_label, 1)
        self.css_toggle = IconButton(
            text="CSS", tooltip="Edit gradient as CSS", checkable=True,
            variant="ghost", accessible_name="Edit gradient CSS",
            parent=self)
        self.css_toggle.changed.connect(self._toggle_raw)
        actions.addWidget(self.css_toggle, 0)
        layout.addLayout(actions)

        self.raw_edit = QLineEdit(self)
        self.raw_edit.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.raw_edit.setPlaceholderText("linear-gradient(...)")
        self.raw_edit.setStyleSheet(
            f"QLineEdit {{ background: {tokens.BG_FIELD};"
            f" color: {tokens.TEXT_PRIMARY};"
            f" border: 1px solid {tokens.BORDER_POPOVER};"
            f" border-radius: {tokens.RADIUS_SM}px;"
            f" padding: 0 {tokens.SPACE_8}px;"
            f" font-size: {tokens.TYPE_CAPTION}px; }}"
            f"QLineEdit:focus {{ border-color: {tokens.ACCENT}; }}")
        self.raw_edit.returnPressed.connect(self._commit_raw)
        self.raw_edit.editingFinished.connect(self._commit_raw)
        self.raw_edit.hide()
        layout.addWidget(self.raw_edit)

        self.notice = InlineMessage("", role="muted")
        self.notice.hide()
        layout.addWidget(self.notice)

        self.kind.changed.connect(self._on_kind)
        self.angle.preview.connect(self._on_angle_preview)
        self.angle.changed.connect(self._on_angle_changed)
        self.set_gradient(value)

    # ── public ──────────────────────────────────────────────────────────────
    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self.bar.set_spec(self._spec, dict(self._palette))
        self.stop_editor.set_palette(self._palette)
        self.bar.update()

    def set_gradient(self, value: Any) -> None:
        text = "" if value is None else str(value)
        spec = parse_gradient(text)
        if spec is None:
            if not text:
                spec = GradientSpec(stops=[
                    GradientStop(0.0, "#ffffff"),
                    GradientStop(100.0, "#000000")])
            else:
                self._raw_mode = True
                self.css_toggle.blockSignals(True)
                self.css_toggle.setChecked(True)
                self.css_toggle.blockSignals(False)
                self.raw_edit.setText(text)
                self._show_raw(True)
                self._update_preview_raw(text)
                return
        self._raw_mode = False
        self.css_toggle.blockSignals(True)
        self.css_toggle.setChecked(False)
        self.css_toggle.blockSignals(False)
        self.raw_edit.hide()
        self._spec = spec
        if not self._spec.stops:
            self._spec.stops = [GradientStop(0.0, "#ffffff"),
                                GradientStop(100.0, "#000000")]
        while len(self._spec.stops) < self._min_stops:
            self._spec.stops.append(GradientStop(
                100.0, self._spec.stops[-1].color))
        self._spec.stops = self._spec.stops[:self._max_stops]
        self._selected = 0
        self._sync_controls()
        self._show_stop()

    def gradient(self) -> str:
        if self._raw_mode:
            return self.raw_edit.text().strip()
        return format_gradient(self._spec)

    def spec(self) -> GradientSpec:
        return self._spec

    # ── syncing ─────────────────────────────────────────────────────────────
    def _sync_controls(self) -> None:
        self.bar.set_spec(self._spec, dict(self._palette))
        self._updating = True
        try:
            self.kind.set_value(self._spec.kind)
            self.angle.set_value(self._spec.angle)
            self.angle.setVisible(self._spec.kind == "linear")
        finally:
            self._updating = False

    def _show_stop(self) -> None:
        if not self._spec.stops:
            return
        self._selected = max(0, min(self._selected, len(self._spec.stops) - 1))
        stop = self._spec.stops[self._selected]
        self._updating = True
        try:
            self.stop_editor.set_value(stop.color)
        finally:
            self._updating = False
        self.bar.set_selected(self._selected)
        count = len(self._spec.stops)
        label = f"Stop {self._selected + 1} of {count}"
        if stop.at is not None:
            label += f" · {format_number(stop.at, decimals=1)}%"
        self.count_label.setText(label)
        self.add_button.setEnabled(count < self._max_stops)

    def _update_preview_raw(self, text: str) -> None:
        spec = parse_gradient(text)
        if spec is None:
            spec = GradientSpec(stops=[GradientStop(0.0, "#00000000"),
                                       GradientStop(100.0, "#00000000")])
        self.bar.set_spec(spec, dict(self._palette))

    # ── stop actions ────────────────────────────────────────────────────────
    def _on_selected(self, index: int) -> None:
        if self._updating:
            return
        self._selected = index
        self._show_stop()

    def _on_bar_preview(self) -> None:
        if self._updating:
            return
        self._show_stop()
        self.preview.emit(format_gradient(self._spec))

    def _on_bar_changed(self) -> None:
        if self._updating:
            return
        self._show_stop()
        self.changed.emit(format_gradient(self._spec))

    def _on_stop_preview(self, text: str) -> None:
        if self._updating or not self._spec.stops:
            return
        self._spec.stops[self._selected].color = str(text)
        self.bar.update()
        self.preview.emit(format_gradient(self._spec))

    def _on_stop_committed(self, text: str) -> None:
        if self._updating or not self._spec.stops:
            return
        self._spec.stops[self._selected].color = str(text)
        self.bar.update()
        self.changed.emit(format_gradient(self._spec))

    def _add_stop_at(self, position: Any) -> None:
        if self._raw_mode or len(self._spec.stops) >= self._max_stops:
            return
        try:
            at = max(0.0, min(100.0, float(position)))
        except (TypeError, ValueError):
            at = 50.0
        color = sample_gradient(self._spec, at, self._palette)
        stop = GradientStop(at, color)
        self._spec.stops.append(stop)
        self._spec.stops.sort(
            key=lambda item: item.at if item.at is not None else 0.0)
        self._selected = self._spec.stops.index(stop)
        self._sync_controls()
        self._show_stop()
        self.changed.emit(format_gradient(self._spec))

    def _remove_stop_at(self, index: int) -> None:
        if self._raw_mode or len(self._spec.stops) <= self._min_stops:
            return
        if not 0 <= index < len(self._spec.stops):
            return
        del self._spec.stops[index]
        self._selected = min(index, len(self._spec.stops) - 1)
        self._sync_controls()
        self._show_stop()
        self.changed.emit(format_gradient(self._spec))

    def _add_stop(self) -> None:
        if len(self._spec.stops) >= self._max_stops:
            return
        stops = self._spec.stops
        # Insert at the widest gap so the new stop is always visible.
        best_index = max(0, len(stops) - 1)
        best_gap = -1.0
        for index in range(len(stops) - 1):
            left = stops[index].at if stops[index].at is not None else 0.0
            right = stops[index + 1].at if (
                stops[index + 1].at is not None) else 100.0
            if right - left > best_gap:
                best_gap = right - left
                best_index = index + 1
        left = stops[best_index - 1].at if stops[
            best_index - 1].at is not None else 0.0
        right = (stops[best_index].at
                 if best_index < len(stops)
                 and stops[best_index].at is not None else 100.0)
        self._add_stop_at((left + right) / 2)

    # ── controls ────────────────────────────────────────────────────────────
    def _on_kind(self, kind: str) -> None:
        if self._updating:
            return
        self._spec.kind = kind
        self.angle.setVisible(kind == "linear")
        self.bar.update()
        self.changed.emit(format_gradient(self._spec))

    def _on_angle_preview(self, value) -> None:
        if self._updating or value is None:
            return
        self._spec.angle = float(value)
        self.bar.update()
        self.preview.emit(format_gradient(self._spec))

    def _on_angle_changed(self, value) -> None:
        if self._updating or value is None:
            return
        self._spec.angle = float(value)
        self.bar.update()
        self.changed.emit(format_gradient(self._spec))

    def _toggle_raw(self, checked: bool) -> None:
        if checked:
            self.raw_edit.setText(format_gradient(self._spec))
            self._show_raw(True)
            self.raw_edit.setFocus(Qt.FocusReason.MouseFocusReason)
            return
        text = self.raw_edit.text().strip()
        if not text:
            self._force_raw_toggle(True)
            return
        spec = parse_gradient(text)
        if spec is None:
            self.notice.setText("This gradient is not structured enough to "
                                "edit as stops; keep CSS mode.")
            self.notice.show()
            self._force_raw_toggle(True)
            return
        self.notice.hide()
        self._raw_mode = False
        self._spec = spec
        self._show_raw(False)
        self._sync_controls()
        self._show_stop()
        self.changed.emit(format_gradient(self._spec))

    def _force_raw_toggle(self, checked: bool) -> None:
        self.css_toggle.blockSignals(True)
        self.css_toggle.setChecked(checked)
        self.css_toggle.blockSignals(False)

    def _show_raw(self, raw: bool) -> None:
        self._raw_mode = raw
        self.bar.setVisible(True)
        self.stop_editor.setVisible(not raw)
        self.kind.setVisible(not raw)
        self.angle.setVisible(not raw and self._spec.kind == "linear")
        self.add_button.setVisible(not raw)
        self.count_label.setVisible(not raw)
        self.raw_edit.setVisible(raw)
        if not raw:
            self.notice.hide()

    def _commit_raw(self) -> None:
        if not self._raw_mode:
            return
        text = self.raw_edit.text().strip()
        if not text:
            return
        self._update_preview_raw(text)
        self.preview.emit(text)
        self.changed.emit(text)


class _PaintPopover(PopupSurface):
    committed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, field: "PaintField"):
        super().__init__(field.window())
        self._field = field
        self._cancelled = False
        self._updating = False
        self._current_text = "" if field._value is None else str(field._value)
        spec = parse_gradient(field._value)

        layout = self.content
        layout.setSpacing(tokens.SPACE_8)

        # A (label, value) tuple is ONE option, not an option pair: the old
        # call made SegmentedToggle render "('Solid', 'solid')".
        modes = [ChoiceOption("solid", "Solid")]
        if field._allow_gradient:
            modes.append(ChoiceOption("gradient", "Gradient"))
        if field._allow_none:
            modes.append(ChoiceOption("none", "None"))
        self.mode = SegmentedToggle(modes, "solid",
                                    accessible_name="Paint type")
        layout.addWidget(self.mode)

        from PyQt6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget(self)
        layout.addWidget(self.stack)

        # Solid page.
        solid_page = QWidget(self)
        solid_layout = QVBoxLayout(solid_page)
        solid_layout.setContentsMargins(0, 0, 0, 0)
        solid_layout.setSpacing(tokens.SPACE_4)
        initial_solid = field._value
        if spec is not None and spec.stops:
            initial_solid = spec.stops[0].color
        color = resolve_paint_color(initial_solid, field._palette_map)
        if color is None or color.alpha() == 0:
            # A transparent value must not seed the plane at alpha 0, or the
            # first hue pick would produce an invisible #rrggbb00.
            initial_solid = field.last_solid() or "#ffffff"
        self.editor = ColorEditor(
            initial_solid, palette=field._palette,
            keywords=field._keywords, alpha=True)
        self.editor.preview.connect(self._on_solid_preview)
        self.editor.committed.connect(self._on_solid_committed)
        solid_layout.addWidget(self.editor)
        self.stack.addWidget(solid_page)

        # Gradient page.
        gradient_page = QWidget(self)
        gradient_layout = QVBoxLayout(gradient_page)
        gradient_layout.setContentsMargins(0, 0, 0, 0)
        gradient_layout.setSpacing(tokens.SPACE_4)
        self.gradient = GradientEditor(
            field._value if spec is not None else "",
            palette=field._palette, min_stops=2,
            max_stops=field._max_stops)
        self.gradient.preview.connect(self._on_gradient_preview)
        self.gradient.changed.connect(self._on_gradient_changed)
        gradient_layout.addWidget(self.gradient)
        self.stack.addWidget(gradient_page)

        # None page.
        none_page = QWidget(self)
        none_layout = QVBoxLayout(none_page)
        none_layout.setContentsMargins(0, 0, 0, 0)
        self.none_note = InlineMessage(
            "No paint. Choose Solid or Gradient to paint this value again.",
            role="muted")
        none_layout.addWidget(self.none_note)
        none_layout.addStretch(1)
        self.stack.addWidget(none_page)

        # The mode is derived from the stored value, never stored: an empty,
        # "none" or fully transparent value opens the None page, a gradient
        # opens the Gradient page, anything else opens Solid.
        self.mode.changed.connect(self._on_mode)
        self._sync_mode(follow_page=True)
        self.setMinimumWidth(260)
        self._sync_height()

    def _page_for(self, mode: str) -> int:
        if mode == "gradient":
            return 1
        if mode == "none":
            return 2
        return 0

    def _apply_mode(self, mode: str) -> None:
        self.stack.setCurrentIndex(self._page_for(mode))
        self._sync_height()

    def _sync_height(self) -> None:
        page = self.stack.currentWidget()
        hint = page.sizeHint().height() if page is not None else 0
        height = (tokens.SPACE_16 + tokens.CONTROL_HEIGHT
                  + tokens.SPACE_8 + hint + tokens.POPUP_GUTTER * 2)
        self.resize(self.width(), max(120, min(480, height)))

    def _sync_mode(self, *, follow_page: bool = False) -> None:
        """Show the mode the stored value implies.

        The mode is never its own state: painting a colour over a transparent
        value turns the value into a solid, and the segment follows it in the
        same update instead of waiting for a mode button.

        The page only follows on open and on a mode click. Dragging the alpha
        strip to 0 legitimately makes the value transparent (derived None),
        but yanking the page out from under the cursor would strand the drag;
        the page catches up when the popover reopens.
        """
        mode = self._field.paint_mode()
        self.mode.blockSignals(True)
        self.mode.set_value(mode)
        self.mode.blockSignals(False)
        if follow_page:
            self._apply_mode(mode)

    # ── value restores ──────────────────────────────────────────────────────
    def _solid_text(self) -> str:
        """The solid a mode switch lands on, or opaque white."""
        value = self._field._value
        if paint_mode(value) == "solid":
            text = str(value)
        else:
            text = self._field.last_solid() or "#ffffff"
        if not text.strip():
            text = "#ffffff"
        self.editor.set_value(text)
        return text

    def _gradient_text(self) -> str:
        """The gradient a mode switch lands on, or a 2-stop default."""
        value = self._field._value
        if paint_mode(value) == "gradient":
            text = str(value)
        else:
            text = self._field.last_gradient()
        if not text:
            base = (str(value) if paint_mode(value) == "solid"
                    else self._field.last_solid() or "#ffffff")
            text = format_gradient(GradientSpec(
                kind="linear", angle=180.0,
                stops=[GradientStop(0.0, base),
                       GradientStop(100.0, "#00000000")]))
        self.gradient.set_gradient(text)
        return text

    def _paint(self, text: Any, *, commit: bool = False) -> None:
        text = "" if text is None else str(text)
        self._current_text = text
        if commit:
            # Commit through the popover signal: the field is what forwards a
            # committed value to the store (`changed`). Pre-setting `_value`
            # on the preview path first would make that commit look unchanged
            # and the edit would never leave the popover.
            self.committed.emit(text)
        else:
            self._field._on_popover_preview(text)
        self._sync_mode()

    # ── edits ───────────────────────────────────────────────────────────────
    def _on_mode(self, mode: str) -> None:
        """A mode button only switches type; the value stays the truth."""
        if self._updating:
            return
        if mode == "none":
            text = "transparent"
        elif mode == "gradient":
            text = self._gradient_text()
        else:
            text = self._solid_text()
        self._paint(text, commit=True)
        self._apply_mode(self._field.paint_mode())

    def _on_solid_preview(self, text: str) -> None:
        self._paint(text)

    def _on_solid_committed(self, text: str) -> None:
        self._paint(text, commit=True)

    def _on_gradient_preview(self, text: str) -> None:
        self._paint(text)

    def _on_gradient_changed(self, text: str) -> None:
        self._paint(text, commit=True)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._cancelled:
            self.cancelled.emit()
        elif self._current_text != self._field.committed_value():
            # A drag still in flight is flushed; an unchanged popover writes
            # nothing.
            self.committed.emit(self._current_text)
        super().closeEvent(event)


class PaintField(QWidget):
    """Compact colour/gradient/none field with the kit's paint popover.

    Signals
        changed(object) — committed paint string (or None).
        preview(object) — live paint string while dragging.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "#ffffff", *,
                 palette: Iterable[tuple[str, str]] = (),
                 keywords: Iterable[str] = (), allow_gradient: bool = True,
                 allow_none: bool = True, nullable: bool = False,
                 max_stops: int = 12, parent=None):
        super().__init__(parent)
        self._value = "" if value is None else str(value)
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self._keywords = [str(k) for k in keywords]
        self._allow_gradient = bool(allow_gradient)
        self._allow_none = bool(allow_none)
        self._nullable = bool(nullable)
        self._max_stops = max(2, max_stops)
        self._popover: Optional[_PaintPopover] = None
        self._open_value = ""
        #: Session-only memory of the last visible solid and gradient. Mode
        #: switches restore these; they are never stored in the theme.
        self._last_solid = ""
        self._last_gradient = ""
        self._hover = False
        self._warning = ""
        self._remember(self._value)
        #: The value the store holds. ``_value`` also carries the in-flight
        #: drag value, so it cannot answer "did this commit change anything?".
        self._committed_value = self._value
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Paint")
        attach_tooltip(self, lambda: self._warning
                       or _describe(self._value, self._palette_map)
                       or "Not set")

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        return self._value or None

    def paint_mode(self) -> str:
        """Mode derived from the value, narrowed to what this field allows."""
        mode = paint_mode(self._value)
        if mode == "gradient" and not self._allow_gradient:
            return "solid"
        if mode == "none" and not self._allow_none:
            return "solid"
        return mode

    def last_solid(self) -> str:
        return self._last_solid

    def last_gradient(self) -> str:
        return self._last_gradient

    def _remember(self, text: Any) -> None:
        """Cache the last visible solid/gradient for mode switches."""
        value = "" if text is None else str(text).strip()
        if not value:
            return
        if parse_gradient(value) is not None:
            self._last_gradient = value
            return
        color = resolve_paint_color(value, self._palette_map)
        if color is not None and color.alpha() > 0:
            self._last_solid = value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        text = "" if value is None else str(value)
        changed = text != self._committed_value
        self._value = text
        self._committed_value = text
        self._remember(text)
        self.update()
        if emit and changed:
            self.changed.emit(self.value())

    def committed_value(self) -> str:
        """The value the store holds, ignoring an un-released drag value."""
        return self._committed_value

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self._palette_map = dict(self._palette)
        self.update()

    def set_keywords(self, keywords: Iterable[str]) -> None:
        self._keywords = [str(k) for k in keywords]

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
        popover = _PaintPopover(self)
        self._popover = popover
        self._open_value = self._value
        popover.committed.connect(self._on_popover_committed)
        popover.cancelled.connect(self._on_popover_cancelled)
        popover.closed.connect(self._on_popover_closed)
        popover.destroyed.connect(self._on_popover_destroyed)
        popover.show_below(self, width=270, max_height=500, align="left")

    def _on_popover_preview(self, text: Any) -> None:
        self._value = "" if text is None else str(text)
        self._remember(self._value)
        self.update()
        self.preview.emit(self.value())

    def _on_popover_committed(self, text: Any) -> None:
        """Commit a finished edit (release, click, hex field, mode switch).

        The dedupe compares against what the *store* holds, not ``_value``:
        the preview path advances ``_value`` continuously while dragging, so
        comparing with it swallowed every commit and the preview only caught
        up when a mode switch wrote a different string.
        """
        text = "" if text is None else str(text)
        self._value = text
        self._remember(text)
        self.update()
        if text == self._committed_value:
            return
        self._committed_value = text
        self.changed.emit(self.value())

    def _on_popover_cancelled(self) -> None:
        """Escape rewinds the store too: it stayed in step while editing."""
        previous = self._value
        self._value = self._open_value
        self.update()
        if self._committed_value != self._open_value:
            self._committed_value = self._open_value
            self.changed.emit(self.value())
        elif self._value != previous:
            self.preview.emit(self.value())

    def _on_popover_closed(self) -> None:
        popover = self._popover
        self._popover = None
        if popover is not None:
            popover.deleteLater()
        self.update()

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

        swatch = QRectF(rect.left() + 4, rect.top() + 4,
                        rect.height() - 8, rect.height() - 8)
        paint_value(painter, swatch, self._value, self._palette_map)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(swatch, 3, 3)

        text_rect = QRectF(swatch.right() + 6, rect.top(),
                           max(0.0, rect.right() - swatch.right() - 22),
                           rect.height())
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(
            tokens.TEXT_MUTED if not enabled else
            tokens.TEXT_MUTED if not self._value else tokens.TEXT_PRIMARY))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(label_font).elidedText(
                _describe(self._value, self._palette_map),
                Qt.TextElideMode.ElideRight,
                int(text_rect.width())))
        draw_chevron(
            painter, QRectF(rect.right() - 16, rect.top(), 12,
                            rect.height()).center(),
            "down", tokens.TEXT_MUTED, size=4.4)
        if focused:
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()

    def sizeHint(self) -> QSize:
        return QSize(170, tokens.CONTROL_HEIGHT)


__all__ = [
    "PaintField", "GradientEditor", "GradientSpec", "GradientStop",
    "parse_gradient", "format_gradient", "paint_mode", "paint_value",
    "sample_gradient",
]
