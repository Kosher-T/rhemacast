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
    checkerboard, draw_chevron, elide, font, format_number,
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


def _describe(value: Any) -> str:
    if value is None or str(value).strip() == "":
        return "Not set"
    text = str(value)
    if text.strip().lower() in ("none", "transparent"):
        return text.strip().capitalize()
    spec = parse_gradient(text)
    if spec is not None:
        return ("Linear gradient" if spec.kind == "linear"
                else "Radial gradient")
    return text


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


class _GradientPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._spec = GradientSpec(stops=[
            GradientStop(0.0, "#ffffff"), GradientStop(100.0, "#000000")])
        self._palette: dict[str, str] = {}
        self.setFixedHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_spec(self, spec: GradientSpec,
                 palette: Optional[dict[str, str]] = None) -> None:
        self._spec = spec
        if palette is not None:
            self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        checkerboard(painter, rect, 4)
        paint_gradient(painter, rect, self._spec, self._palette)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect, 4, 4)
        painter.end()


class _GradientStopRow(QWidget):
    preview = pyqtSignal()
    edited = pyqtSignal()
    removed = pyqtSignal(object)

    def __init__(self, stop: GradientStop, *,
                 palette: Iterable[tuple[str, str]] = (),
                 can_remove: bool = True, parent=None):
        super().__init__(parent)
        self._updating = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        self.position = NumberField(
            stop.at, minimum=0, maximum=100, step=1, nullable=True,
            placeholder="auto", suffix="%", label="Stop position")
        self.position.setFixedWidth(62)
        layout.addWidget(self.position, 0)

        from ui.theme_kit.color_field import ColorField
        self.color = ColorField(
            stop.color, palette=palette, alpha=True, nullable=False)
        layout.addWidget(self.color, 1)

        self.remove = IconButton(glyph="minus", tooltip="Remove stop",
                                 variant="ghost", parent=self)
        self.remove.setEnabled(can_remove)
        self.remove.clicked.connect(lambda: self.removed.emit(self))
        layout.addWidget(self.remove, 0)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)

        self.position.preview.connect(self._on_preview)
        self.position.changed.connect(self._on_changed)
        self.color.preview.connect(self._on_preview)
        self.color.changed.connect(self._on_changed)

    def stop(self) -> GradientStop:
        value = self.position.value()
        if isinstance(value, str):
            stripped = value.rstrip("%")
            value = parse_number_text(stripped)
        at = None if value is None else float(value)
        return GradientStop(at, str(self.color.value() or ""))

    def set_stop(self, stop: GradientStop) -> None:
        self._updating = True
        try:
            self.position.set_value(stop.at)
            self.color.set_value(stop.color)
        finally:
            self._updating = False

    def _on_preview(self, *_args) -> None:
        if not self._updating:
            self.preview.emit()

    def _on_changed(self, *_args) -> None:
        if not self._updating:
            self.edited.emit()


class GradientEditor(QWidget):
    """Structured linear/radial gradient editor.

    Signals
        preview(str) — live CSS while a stop colour/position is dragged.
        changed(str) — committed CSS (release, add/remove, kind/angle).
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
        self._min_stops = max(1, min_stops)
        self._max_stops = max(self._min_stops, max_stops)
        self._updating = False
        self._raw_mode = False
        self._rows: list[_GradientStopRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        self.preview_bar = _GradientPreview(self)
        layout.addWidget(self.preview_bar)

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(tokens.SPACE_4)
        self.kind = SegmentedToggle(
            [("Linear", "linear"), ("Radial", "radial")], "linear",
            accessible_name="Gradient type")
        controls.addWidget(self.kind, 1)
        self.angle = NumberField(
            180, minimum=0, maximum=360, step=5, suffix="°",
            label="Gradient angle")
        self.angle.setFixedWidth(66)
        controls.addWidget(self.angle, 0)
        layout.addLayout(controls)

        self.rows_host = QWidget(self)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(tokens.SPACE_4)
        layout.addWidget(self.rows_host)

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
        for row in self._rows:
            row.color.set_palette(self._palette)

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
        self._sync_controls()
        self._rebuild_rows()
        self._update_preview()
        self._update_count()

    def gradient(self) -> str:
        if self._raw_mode:
            return self.raw_edit.text().strip()
        return format_gradient(self._spec)

    def spec(self) -> GradientSpec:
        return self._spec

    # ── syncing ─────────────────────────────────────────────────────────────
    def _sync_controls(self) -> None:
        self._updating = True
        try:
            self.kind.set_value(self._spec.kind)
            self.angle.set_value(self._spec.angle)
            self.angle.setVisible(self._spec.kind == "linear")
        finally:
            self._updating = False

    def _rebuild_rows(self) -> None:
        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for index, stop in enumerate(self._spec.stops):
            row = _GradientStopRow(
                stop, palette=self._palette,
                can_remove=len(self._spec.stops) > self._min_stops,
                parent=self.rows_host)
            row.preview.connect(self._on_row_preview)
            row.edited.connect(self._on_row_edited)
            row.removed.connect(self._remove_row)
            self.rows_layout.addWidget(row)
            self._rows.append(row)

    def _update_count(self) -> None:
        count = len(self._spec.stops)
        self.count_label.setText(f"{count} stop{'s' if count != 1 else ''}")
        self.add_button.setEnabled(count < self._max_stops)
        for row in self._rows:
            row.remove.setEnabled(count > self._min_stops)

    def _collect(self) -> None:
        self._spec.stops = [row.stop() for row in self._rows]

    def _update_preview(self) -> None:
        self.preview_bar.set_spec(self._spec, dict(self._palette))

    def _update_preview_raw(self, text: str) -> None:
        spec = parse_gradient(text)
        if spec is not None:
            self.preview_bar.set_spec(spec, dict(self._palette))
        else:
            self.preview_bar.set_spec(
                GradientSpec(stops=[GradientStop(0.0, "#00000000"),
                                    GradientStop(100.0, "#00000000")]),
                dict(self._palette))

    # ── row actions ─────────────────────────────────────────────────────────
    def _on_row_preview(self) -> None:
        self._collect()
        self._update_preview()
        self.preview.emit(format_gradient(self._spec))

    def _on_row_edited(self) -> None:
        self._collect()
        self._update_preview()
        self.changed.emit(format_gradient(self._spec))

    def _remove_row(self, row: _GradientStopRow) -> None:
        if len(self._spec.stops) <= self._min_stops:
            return
        self._collect()
        index = self._rows.index(row) if row in self._rows else -1
        if index >= 0:
            del self._spec.stops[index]
        self._rebuild_rows()
        self._update_preview()
        self._update_count()
        self.changed.emit(format_gradient(self._spec))

    def _add_stop(self) -> None:
        if len(self._spec.stops) >= self._max_stops:
            return
        self._collect()
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
        at = (left + right) / 2
        color = stops[best_index - 1].color
        stops.insert(best_index, GradientStop(at, color))
        self._rebuild_rows()
        self._update_preview()
        self._update_count()
        self.changed.emit(format_gradient(self._spec))

    # ── controls ────────────────────────────────────────────────────────────
    def _on_kind(self, kind: str) -> None:
        if self._updating:
            return
        self._spec.kind = kind
        self.angle.setVisible(kind == "linear")
        self._update_preview()
        self.changed.emit(format_gradient(self._spec))

    def _on_angle_preview(self, value) -> None:
        if self._updating or value is None:
            return
        self._spec.angle = float(value)
        self._update_preview()
        self.preview.emit(format_gradient(self._spec))

    def _on_angle_changed(self, value) -> None:
        if self._updating or value is None:
            return
        self._spec.angle = float(value)
        self._update_preview()
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
        self._rebuild_rows()
        self._update_preview()
        self._update_count()
        self.changed.emit(format_gradient(self._spec))

    def _force_raw_toggle(self, checked: bool) -> None:
        self.css_toggle.blockSignals(True)
        self.css_toggle.setChecked(checked)
        self.css_toggle.blockSignals(False)

    def _show_raw(self, raw: bool) -> None:
        self._raw_mode = raw
        self.preview_bar.setVisible(True)
        self.rows_host.setVisible(not raw)
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
        spec = parse_gradient(field._value)

        layout = self.content
        layout.setSpacing(tokens.SPACE_8)

        modes = []
        modes.append(("Solid", "solid"))
        if field._allow_gradient:
            modes.append(("Gradient", "gradient"))
        if field._allow_none:
            modes.append(("None", "none"))
        self.mode = SegmentedToggle(modes, "solid", accessible_name="Paint type")
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
            "Paint is disabled for this value. Choose Solid or Gradient to "
            "paint it again.", role="muted")
        none_layout.addWidget(self.none_note)
        none_layout.addStretch(1)
        self.stack.addWidget(none_page)

        self.mode.changed.connect(self._on_mode)
        mode = "solid"
        if spec is not None:
            mode = "gradient"
        elif field._value is None or str(field._value).strip().lower() in (
                "", "none"):
            mode = "none" if field._allow_none else "solid"
        self.mode.blockSignals(True)
        self.mode.set_value(mode)
        self.mode.blockSignals(False)
        self._apply_mode(mode)
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

    def _on_mode(self, mode: str) -> None:
        if self._updating:
            return
        self._apply_mode(mode)
        if mode == "none":
            text = "none" if self._field._allow_none else ""
        elif mode == "gradient":
            text = self.gradient.gradient()
        else:
            text = str(self.editor.value() or "")
        self._field._on_popover_preview(text)
        self.committed.emit(text)

    def _on_solid_preview(self, text: str) -> None:
        if self.mode.value() != "solid":
            return
        self._field._on_popover_preview(text)

    def _on_solid_committed(self, text: str) -> None:
        if self.mode.value() != "solid":
            return
        self.committed.emit(text)

    def _on_gradient_preview(self, text: str) -> None:
        if self.mode.value() != "gradient":
            return
        self._field._on_popover_preview(text)

    def _on_gradient_changed(self, text: str) -> None:
        if self.mode.value() != "gradient":
            return
        self.committed.emit(text)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._cancelled:
            self.cancelled.emit()
        else:
            mode = self.mode.value()
            if mode == "none":
                text = "none"
            elif mode == "gradient":
                text = self.gradient.gradient()
            else:
                text = str(self.editor.value() or "")
            if text != self._field._value:
                self.committed.emit(text)
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
        self._hover = False
        self._warning = ""
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Paint")
        attach_tooltip(self, lambda: self._warning or self._value
                       or "Not set")

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
        popover.destroyed.connect(self._on_popover_destroyed)
        popover.show_below(self, width=270, max_height=500, align="left")

    def _on_popover_preview(self, text: Any) -> None:
        self._value = "" if text is None else str(text)
        self.update()
        self.preview.emit(self.value())

    def _on_popover_committed(self, text: Any) -> None:
        text = "" if text is None else str(text)
        if text == self._value:
            return
        self._value = text
        self.update()
        self.changed.emit(self.value())

    def _on_popover_cancelled(self) -> None:
        self._value = self._open_value
        self.update()
        self.preview.emit(self.value())

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
                _describe(self._value), Qt.TextElideMode.ElideRight,
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
    "parse_gradient", "format_gradient", "paint_value",
]
