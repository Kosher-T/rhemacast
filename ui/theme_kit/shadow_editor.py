"""ui/theme_kit/shadow_editor.py

ShadowEditor — an inline box/text shadow layer editor — and ShadowField, the
compact field that hosts it in a popover.

Custom edits emit a CSS shadow string (the kit's one deliberate shape
deviation); a shared reference emits ``{"shared": name}`` unchanged. CSS that
the structured editor cannot represent stays in raw CSS mode instead of being
flattened.

No shadow is painted with QGraphicsDropShadowEffect: every preview paints its
own offset silhouette so Windows and Linux agree.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout, QLineEdit, QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, checkerboard, coerce_options, draw_chevron, elide, font,
    paint_focus_ring, parse_number_text,
)
from ui.theme_kit.color_field import (
    ColorField, parse_css_color, resolve_paint_color,
)
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import PopupSurface, attach_tooltip
from ui.theme_kit.segmented import SegmentedToggle, ToggleButton
from ui.theme_kit.small import IconButton, InlineMessage

_LENGTH_RE = re.compile(r"^(-?\d*\.?\d+)(px)?$", re.I)
_COLOR_KEYWORDS = {"transparent", "currentcolor", "inherit", "none"}


@dataclass
class ShadowLayer:
    x: float = 0.0
    y: float = 4.0
    blur: float = 12.0
    spread: float = 0.0
    color: str = "rgba(0, 0, 0, 0.4)"
    inset: bool = False

    def copy(self) -> "ShadowLayer":
        return replace(self)

    def css(self) -> str:
        parts: list[str] = []
        if self.inset:
            parts.append("inset")
        parts.append(_fmt_length(self.x))
        parts.append(_fmt_length(self.y))
        parts.append(_fmt_length(self.blur))
        if self.spread:
            parts.append(_fmt_length(self.spread))
        parts.append(self.color or "transparent")
        return " ".join(parts)


def _fmt_length(value: float) -> str:
    text = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"{text or '0'}px"


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


def _split_tokens(text: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth = max(0, depth - 1)
            current.append(char)
        elif char.isspace() and depth == 0:
            if current:
                tokens.append("".join(current))
                current = []
        else:
            current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _is_color_token(token: str) -> bool:
    low = token.strip().lower()
    if low in _COLOR_KEYWORDS or low.startswith("@"):
        return True
    return parse_css_color(token) is not None


def _length(token: str) -> Optional[float]:
    match = _LENGTH_RE.match(token.strip())
    if not match:
        return None
    return float(match.group(1))


def parse_shadow(text: Any) -> Optional[list[ShadowLayer]]:
    """Parse a CSS shadow list. ``None`` means "not structured"; ``[]`` none."""
    if text is None:
        return []
    if isinstance(text, dict):
        if "shared" in text:
            return None
        return [ShadowLayer(
            float(text.get("x", 0) or 0), float(text.get("y", 0) or 0),
            float(text.get("blur", 0) or 0), float(text.get("spread", 0) or 0),
            str(text.get("color", "rgba(0, 0, 0, 0.5)")),
            bool(text.get("inset", False)))]
    raw = str(text).strip()
    if not raw or raw.lower() in ("none", "off"):
        return []
    if raw.startswith("{"):
        return None
    layers: list[ShadowLayer] = []
    for chunk in _split_top_level(raw):
        tokens = _split_tokens(chunk)
        inset = False
        lengths: list[float] = []
        color = ""
        for token in tokens:
            low = token.lower()
            if low == "inset":
                if inset:
                    return None
                inset = True
                continue
            number = _length(token)
            if number is not None and len(lengths) < 4:
                lengths.append(number)
                continue
            if not color and _is_color_token(token):
                color = token
                continue
            # A second color, or an unknown token, is not this editor's shape.
            return None
        if len(lengths) < 2 or len(lengths) > 4 or not color:
            return None
        x, y = lengths[0], lengths[1]
        blur = lengths[2] if len(lengths) > 2 else 0.0
        spread = lengths[3] if len(lengths) > 3 else 0.0
        layers.append(ShadowLayer(x, y, blur, spread, color, inset))
    return layers or None


def format_shadow(layers: Iterable[ShadowLayer]) -> str:
    items = [layer.css() for layer in layers]
    return ", ".join(items) if items else "none"


def shadow_summary(value: Any) -> str:
    if isinstance(value, dict) and "shared" in value:
        return f"Shared · {value.get('shared')}"
    layers = parse_shadow(value)
    if layers is None:
        return str(value)
    if not layers:
        return "None"
    if len(layers) == 1:
        layer = layers[0]
        return (f"{'Inset · ' if layer.inset else ''}"
                f"{_fmt_length(layer.x)} {_fmt_length(layer.y)} "
                f"{_fmt_length(layer.blur)}")
    return f"{len(layers)} shadow layers"


# ─── Layer row ──────────────────────────────────────────────────────────────

class _LayerRow(QWidget):
    changed = pyqtSignal()
    preview = pyqtSignal()
    removed = pyqtSignal(object)

    def __init__(self, layer: ShadowLayer, index: int, *,
                 palette: Iterable[tuple[str, str]] = (),
                 can_remove: bool = True, show_spread: bool = True,
                 parent=None):
        super().__init__(parent)
        self._layer = layer.copy()
        self._show_spread = bool(show_spread)
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(tokens.SPACE_4)
        self.title = InlineMessage(f"Shadow {index + 1}", role="muted")
        head.addWidget(self.title, 1)
        self.inset = ToggleButton(
            text="In", checked=layer.inset, tooltip="Inset shadow",
            accessible_name=f"Shadow {index + 1} inset")
        self.inset.changed.connect(self._on_inset)
        head.addWidget(self.inset, 0)
        self.remove = IconButton(
            glyph="trash", tooltip="Remove shadow layer",
            accessible_name="Remove shadow layer", variant="ghost",
            parent=self)
        self.remove.setEnabled(can_remove)
        self.remove.clicked.connect(lambda: self.removed.emit(self))
        head.addWidget(self.remove, 0)
        layout.addLayout(head)

        # Two rows of two: four values across the row overflowed a 240 px
        # panel and pushed the fourth field out of the popover. Each field
        # carries its own inline label, so no row-label column eats width.
        grid = QVBoxLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(tokens.SPACE_4)
        self.x = NumberField(layer.x, minimum=-500, maximum=500, step=1,
                             label="Shadow X", inline_label="X")
        self.y = NumberField(layer.y, minimum=-500, maximum=500, step=1,
                             label="Shadow Y", inline_label="Y")
        self.blur = NumberField(layer.blur, minimum=0, maximum=500, step=1,
                                label="Shadow blur", inline_label="Blur")
        self.spread = NumberField(layer.spread, minimum=-500, maximum=500,
                                  step=1, label="Shadow spread",
                                  inline_label="Spread")
        for pair in ((self.x, self.y), (self.blur, self.spread)):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(tokens.SPACE_4)
            for field in pair:
                row.addWidget(field, 1)
            grid.addLayout(row)
        self.spread.setVisible(self._show_spread)
        layout.addLayout(grid)

        self.color = ColorField(layer.color, palette=palette, alpha=True)
        layout.addWidget(self.color)

        for field in (self.x, self.y, self.blur, self.spread):
            field.preview.connect(lambda _v: self._emit(preview=True))
            field.changed.connect(lambda _v: self._emit(preview=False))
        self.color.preview.connect(lambda _v: self._emit(preview=True))
        self.color.changed.connect(lambda _v: self._emit(preview=False))

    def layer(self) -> ShadowLayer:
        return ShadowLayer(
            float(self.x.numeric_value() or 0),
            float(self.y.numeric_value() or 0),
            float(self.blur.numeric_value() or 0),
            float(self.spread.numeric_value() or 0),
            str(self.color.value() or "transparent"),
            bool(self.inset.isChecked()))

    def set_layer(self, layer: ShadowLayer) -> None:
        self._updating = True
        try:
            self.x.set_value(layer.x)
            self.y.set_value(layer.y)
            self.blur.set_value(layer.blur)
            self.spread.set_value(layer.spread)
            self.color.set_value(layer.color)
            self.inset.blockSignals(True)
            self.inset.setChecked(layer.inset)
            self.inset.blockSignals(False)
            self.inset.update()
        finally:
            self._updating = False

    def _on_inset(self, _checked: bool) -> None:
        if not self._updating:
            self._emit(preview=False)

    def _emit(self, *, preview: bool) -> None:
        if self._updating:
            return
        self.changed.emit() if not preview else self.preview.emit()


# ─── Inline editor ──────────────────────────────────────────────────────────

class ShadowEditor(QWidget):
    """Inline shadow editor.

    Signals
        changed(object) — ``"none"``, a CSS string, or ``{"shared": name}``.
        preview(object) — live value while a field drags.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "none", *,
                 shared_options: Iterable[Any] = (),
                 palette: Iterable[tuple[str, str]] = (),
                 allow_shared: bool = True, max_layers: int = 12,
                 show_spread: bool = True, structured: bool = False,
                 parent=None):
        super().__init__(parent)
        self._structured = bool(structured)
        self._shared_options = coerce_options(shared_options)
        self._palette = list(palette)
        self._allow_shared = bool(allow_shared)
        self._max_layers = max(1, int(max_layers))
        self._show_spread = bool(show_spread)
        self._updating = False
        self._layers: list[ShadowLayer] = []
        self._raw = ""
        self._raw_mode = False
        self._rows: list[_LayerRow] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        modes = [ChoiceOption("none", "None"),
                 ChoiceOption("custom", "Custom")]
        if self._allow_shared and self._shared_options:
            modes.append(ChoiceOption("shared", "Shared"))
        self.mode = SegmentedToggle(modes, "none",
                                   accessible_name="Shadow type")
        self.mode.changed.connect(self._on_mode)
        layout.addWidget(self.mode)

        self.shared_row = QWidget(self)
        shared_layout = QVBoxLayout(self.shared_row)
        shared_layout.setContentsMargins(0, 0, 0, 0)
        shared_layout.setSpacing(tokens.SPACE_4)
        self.shared_dropdown = CompactDropdown(
            self._shared_options, variant="field")
        self.shared_dropdown.changed.connect(self._on_shared)
        shared_layout.addWidget(self.shared_dropdown)
        self.shared_note = InlineMessage(
            "The shared shadow is edited in its shared file.", role="muted")
        shared_layout.addWidget(self.shared_note)
        layout.addWidget(self.shared_row)

        self.custom_host = QWidget(self)
        custom_layout = QVBoxLayout(self.custom_host)
        custom_layout.setContentsMargins(0, 0, 0, 0)
        custom_layout.setSpacing(tokens.SPACE_4)
        self.rows_host = QWidget(self.custom_host)
        self.rows_layout = QVBoxLayout(self.rows_host)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        self.rows_layout.setSpacing(tokens.SPACE_8)
        custom_layout.addWidget(self.rows_host)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(tokens.SPACE_4)
        self.add_button = IconButton(
            glyph="plus", text="Add shadow", tooltip="Add a shadow layer",
            accessible_name="Add shadow layer", parent=self)
        self.add_button.clicked.connect(self._add_layer)
        actions.addWidget(self.add_button, 0)
        self.count_label = InlineMessage("", role="muted")
        actions.addWidget(self.count_label, 1)
        self.css_toggle = ToggleButton(
            text="CSS", tooltip="Edit shadow as CSS",
            accessible_name="Edit shadow CSS")
        self.css_toggle.changed.connect(self._toggle_raw)
        actions.addWidget(self.css_toggle, 0)
        custom_layout.addLayout(actions)

        self.raw_edit = QLineEdit(self.custom_host)
        self.raw_edit.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.raw_edit.setPlaceholderText("0 4px 12px rgba(0, 0, 0, 0.4)")
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
        custom_layout.addWidget(self.raw_edit)

        self.notice = InlineMessage("", role="muted")
        self.notice.hide()
        custom_layout.addWidget(self.notice)
        layout.addWidget(self.custom_host)
        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        mode = self.mode.value()
        if mode == "none":
            return "none"
        if mode == "shared":
            name = self.shared_dropdown.value()
            return {"shared": name} if name else "none"
        if self._raw_mode:
            return self.raw_edit.text().strip() or "none"
        self._collect()
        if self._structured and len(self._layers) == 1:
            # The schema stores a single shadow as an object; a multi-shadow
            # value has no object form, so it stays the CSS string the
            # validator accepts (see docs/theme_kit_stage1_report.md).
            layer = self._layers[0]
            return {"x": layer.x, "y": layer.y, "blur": layer.blur,
                    "spread": layer.spread, "color": layer.color,
                    "inset": bool(layer.inset)}
        return format_shadow(self._layers)

    def set_value(self, value: Any) -> None:
        self._updating = True
        try:
            if isinstance(value, dict) and "shared" in value:
                if self._allow_shared and self._shared_options:
                    self.mode.set_value("shared")
                    self.shared_dropdown.set_value(value.get("shared"))
                else:
                    self.mode.set_value("none")
            elif value is None or str(value).strip().lower() in (
                    "none", "off", ""):
                self.mode.set_value("none")
            else:
                layers = parse_shadow(value)
                if layers is None:
                    self.mode.set_value("custom")
                    self._raw_mode = True
                    self._raw = str(value)
                    self.raw_edit.setText(self._raw)
                    self.css_toggle.blockSignals(True)
                    self.css_toggle.setChecked(True)
                    self.css_toggle.blockSignals(False)
                else:
                    self.mode.set_value("custom")
                    self._raw_mode = False
                    self.css_toggle.blockSignals(True)
                    self.css_toggle.setChecked(False)
                    self.css_toggle.blockSignals(False)
                    self._layers = layers
                    self._rebuild_rows()
            self._apply_mode()
        finally:
            self._updating = False

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        for row in self._rows:
            row.color.set_palette(self._palette)

    def set_shared_options(self, options: Iterable[Any]) -> None:
        self._shared_options = coerce_options(options)
        self.shared_dropdown.set_options(self._shared_options)

    # ── rows ────────────────────────────────────────────────────────────────
    def _collect(self) -> None:
        self._layers = [row.layer() for row in self._rows]

    def _rebuild_rows(self) -> None:
        for row in self._rows:
            self.rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        if not self._layers:
            self._layers = [ShadowLayer()]
        self._layers = self._layers[:self._max_layers]
        for index, layer in enumerate(self._layers):
            row = _LayerRow(
                layer, index, palette=self._palette,
                can_remove=len(self._layers) > 1,
                show_spread=self._show_spread, parent=self.rows_host)
            row.changed.connect(self._on_row_changed)
            row.preview.connect(self._on_row_preview)
            row.removed.connect(self._remove_row)
            self.rows_layout.addWidget(row)
            self._rows.append(row)
        self._update_count()

    def _update_count(self) -> None:
        count = len(self._rows)
        self.count_label.setText(f"{count}/{self._max_layers}")
        self.count_label.setToolTip(
            f"{count} shadow layer{'s' if count != 1 else ''}, "
            f"max {self._max_layers}")
        self.add_button.setEnabled(count < self._max_layers)
        for row in self._rows:
            row.remove.setEnabled(count > 1)

    def _add_layer(self) -> None:
        if len(self._rows) >= self._max_layers:
            return
        self._collect()
        last = self._layers[-1] if self._layers else ShadowLayer()
        self._layers.append(ShadowLayer(
            last.x, last.y + 4, last.blur, last.spread, last.color,
            last.inset))
        self._rebuild_rows()
        self._emit(commit=True)

    def _remove_row(self, row: _LayerRow) -> None:
        if len(self._rows) <= 1:
            return
        self._collect()
        if row in self._rows:
            index = self._rows.index(row)
            if 0 <= index < len(self._layers):
                del self._layers[index]
        self._rebuild_rows()
        self._emit(commit=True)

    def _on_row_changed(self) -> None:
        if self._updating:
            return
        self._collect()
        self._emit(commit=True)

    def _on_row_preview(self) -> None:
        if self._updating:
            return
        self._collect()
        self._emit(commit=False)

    def _emit(self, *, commit: bool) -> None:
        text = format_shadow(self._layers)
        if commit:
            self.changed.emit(text)
        else:
            self.preview.emit(text)

    # ── modes ───────────────────────────────────────────────────────────────
    def _on_mode(self, mode: str) -> None:
        if self._updating:
            return
        self._raw_mode = False
        self.css_toggle.blockSignals(True)
        self.css_toggle.setChecked(False)
        self.css_toggle.blockSignals(False)
        if mode == "custom" and not self._rows:
            self._rebuild_rows()
        self._apply_mode()
        self.changed.emit(self.value())

    def _apply_mode(self) -> None:
        mode = self.mode.value()
        self.shared_row.setVisible(mode == "shared")
        self.custom_host.setVisible(mode == "custom")
        if mode == "custom":
            self.rows_host.setVisible(not self._raw_mode)
            self.add_button.setVisible(not self._raw_mode)
            self.count_label.setVisible(not self._raw_mode)
            self.raw_edit.setVisible(self._raw_mode)
            if self._raw_mode:
                self.css_toggle.blockSignals(True)
                self.css_toggle.setChecked(True)
                self.css_toggle.blockSignals(False)
            self._update_count()

    def _on_shared(self, _name: Any) -> None:
        if not self._updating:
            self.changed.emit(self.value())

    def _toggle_raw(self, checked: bool) -> None:
        if checked:
            self._collect()
            text = format_shadow(self._layers)
            self.raw_edit.setText(text)
            self._raw = text
            self._raw_mode = True
            self._apply_mode()
            self.raw_edit.setFocus(Qt.FocusReason.MouseFocusReason)
            return
        text = self.raw_edit.text().strip()
        layers = parse_shadow(text) if text else []
        if layers is None or not layers:
            self.notice.setText(
                "This shadow is not structured enough to edit as layers; "
                "keep CSS mode.")
            self.notice.show()
            self.css_toggle.blockSignals(True)
            self.css_toggle.setChecked(True)
            self.css_toggle.blockSignals(False)
            return
        self.notice.hide()
        self._raw_mode = False
        self._layers = layers
        self._rebuild_rows()
        self._apply_mode()
        self.changed.emit(self.value())

    def _commit_raw(self) -> None:
        if not self._raw_mode:
            return
        text = self.raw_edit.text().strip()
        if not text:
            return
        self._raw = text
        self.changed.emit(text)


# ─── Painted preview ────────────────────────────────────────────────────────

class _ShadowSwatch(QWidget):
    def __init__(self, value: Any = "none", *,
                 palette: Optional[dict[str, str]] = None, parent=None):
        super().__init__(parent)
        self._value = value
        self._palette = palette or {}
        self.setFixedSize(34, 22)

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
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.BG_PANEL))
        painter.drawRoundedRect(rect, 3, 3)
        layers = parse_shadow(self._value)
        if layers is None:
            painter.setPen(QPen(QColor(tokens.TEXT_MUTED), 1))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), "CSS")
            painter.end()
            return
        # Draw the shadows behind a small rounded tile, clipped to the swatch.
        tile = rect.adjusted(9, 7, -9, -7)
        painter.save()
        painter.setClipRect(rect)
        if layers:
            for layer in reversed(layers):
                color = resolve_paint_color(layer.color, self._palette)
                if color is None:
                    continue
                color = QColor(color)
                color.setAlpha(max(0, min(255, color.alpha())))
                scale = 0.18
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(color)
                painter.drawRoundedRect(
                    tile.adjusted(layer.x * scale - layer.spread * scale,
                                  layer.y * scale - layer.spread * scale,
                                  layer.x * scale + layer.spread * scale,
                                  layer.y * scale + layer.spread * scale),
                    3, 3)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(tile, 3, 3)
        painter.restore()
        painter.end()


# ─── Compact field ──────────────────────────────────────────────────────────

class _ShadowPopover(PopupSurface):
    committed = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, field: "ShadowField"):
        super().__init__(field.window())
        self._field = field
        self._cancelled = False
        self._structured = bool(getattr(field, "_structured", False))
        layout = self.content
        layout.setSpacing(tokens.SPACE_4)
        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollArea > QWidget > QWidget { background: transparent; }"
            "QScrollBar:vertical { background: transparent; width: 8px;"
            f" margin: 0; }}\n"
            "QScrollBar::handle:vertical { background: "
            f"{tokens.BORDER_POPOVER}; border-radius: 4px; min-height: 24px; }}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical"
            " { height: 0; }")
        self.editor = ShadowEditor(
            field._value, shared_options=field._shared_options,
            palette=field._palette, allow_shared=field._allow_shared,
            max_layers=field._max_layers,
            show_spread=field._show_spread, structured=self._structured)
        self.editor.changed.connect(self._on_editor_changed)
        self.editor.preview.connect(field._on_popover_preview)
        self.scroll.setWidget(self.editor)
        layout.addWidget(self.scroll)
        self.setMinimumWidth(320)
        self.resize(320, min(480, max(220, self.editor.sizeHint().height()
                                       + tokens.SPACE_16 + 16)))

    def _on_editor_changed(self, value: Any) -> None:
        self._field._value = "" if value is None else value
        self._field.update()
        self._field.preview.emit(self._field.value())

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self._cancelled = True
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        if self._cancelled:
            self.cancelled.emit()
        else:
            value = self.editor.value()
            if value != self._field._value:
                self.committed.emit(value)
        super().closeEvent(event)


class ShadowField(QWidget):
    """Compact shadow summary field with the kit's shadow popover.

    Signals
        changed(object) — ``"none"``, a CSS shadow string, or a shared ref.
        preview(object) — live value while the popover edits.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "none", *,
                 shared_options: Iterable[Any] = (),
                 palette: Iterable[tuple[str, str]] = (),
                 allow_shared: bool = True, max_layers: int = 12,
                 show_spread: bool = True, structured: bool = False,
                 parent=None):
        super().__init__(parent)
        self._value = "" if value is None else value
        self._structured = bool(structured)
        self._shared_options = list(shared_options)
        self._palette = list(palette)
        self._allow_shared = bool(allow_shared)
        self._max_layers = max_layers
        self._show_spread = bool(show_spread)
        self._structured = bool(structured)
        self._hover = False
        self._warning = ""
        self._popover: Optional[_ShadowPopover] = None
        self._open_value: Any = self._value
        self._suppress_press = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Shadow")
        attach_tooltip(self, lambda: self._warning or shadow_summary(
            self._value))

    def value(self) -> Any:
        return self._value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()
        if emit:
            self.changed.emit(self.value())

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self.update()

    def set_shared_options(self, options: Iterable[Any]) -> None:
        self._shared_options = list(options)

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        self.update()

    # ── popover ─────────────────────────────────────────────────────────────
    def _open_popover(self) -> None:
        if not self.isEnabled():
            return
        popover = self._popover
        if popover is not None:
            if popover.isVisible():
                popover.close()
                return
            # Dismissed (Esc / outside click) but never deleted: reopen from
            # a clean editor rather than showing stale content.
            self._popover = None
            popover.deleteLater()
        popover = _ShadowPopover(self)
        self._popover = popover
        self._open_value = self._value
        popover.committed.connect(self._on_committed)
        popover.cancelled.connect(self._on_cancelled)
        popover.destroyed.connect(
            lambda *_args, _popover=popover: self._on_destroyed(_popover))
        # A Qt.Popup grabs the mouse on show and the platform replays the
        # press that opened it. That replay must not read as a second click
        # (it used to close the popover inside the same press).
        self._suppress_press = True
        QTimer.singleShot(0, self._clear_suppressed_press)
        popover.show_below(self, width=340, max_height=520, align="left")

    def _clear_suppressed_press(self) -> None:
        self._suppress_press = False

    def _on_popover_preview(self, value: Any) -> None:
        self._value = "" if value is None else value
        self.update()
        self.preview.emit(self.value())

    def _on_committed(self, value: Any) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()
        self.changed.emit(self.value())

    def _on_cancelled(self) -> None:
        self._value = self._open_value
        self.update()
        self.preview.emit(self.value())

    def _on_destroyed(self, obj=None, *_args) -> None:
        if self._popover is obj:
            self._popover = None

    # ── events / painting ───────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self._suppress_press:
                event.accept()
                return
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
        swatch = _ShadowSwatch(self._value, palette=dict(self._palette))
        swatch.render(
            painter, QPointF(rect.left() + 4, rect.top() + 2).toPoint())
        text_rect = QRectF(rect.left() + 42, rect.top(),
                           max(0.0, rect.width() - 60), rect.height())
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY if enabled
                              else tokens.TEXT_MUTED))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(label_font).elidedText(
                shadow_summary(self._value), Qt.TextElideMode.ElideRight,
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
    "ShadowEditor", "ShadowField", "ShadowLayer", "parse_shadow",
    "format_shadow", "shadow_summary",
]
