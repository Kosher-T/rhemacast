"""ui/theme_kit/border_editor.py

BorderEditor — the inline border editor — and BorderField, its compact
one-line form that opens the editor in the kit's own popover.

A border value in a theme file may be ``"none"``, a CSS-like string, an object
with base keys plus per-side ``sides`` overrides, or ``{"shared": name}``. The
editor represents all four and emits the object form on custom edits; it never
validates ranges or defaults against the schema (the caller passes them in).
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, coerce_options, draw_check, draw_chevron, font,
    paint_focus_ring, qcolor,
)
from ui.theme_kit.color_field import ColorField
from ui.theme_kit.dropdown import CompactDropdown
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import PopupSurface, attach_tooltip
from ui.theme_kit.property_row import PropertyRow
from ui.theme_kit.segmented import SegmentedToggle
from ui.theme_kit.small import IconButton, InlineMessage

#: Allowlisted styles from the theme reference, offered when the caller does
#: not pass its own list.
BORDER_STYLES = (
    "none", "solid", "dashed", "dotted", "double", "groove", "ridge",
    "inset", "outset",
)
SIDES = ("top", "right", "bottom", "left")
_DEFAULTS = {"width": 1, "style": "solid", "color": "currentColor",
             "radius": 0}
_LENGTH_RE = re.compile(r"^(-?\d+(?:\.\d+)?)(?:px)?$", re.I)

_PEN_STYLES = {
    "none": Qt.PenStyle.NoPen,
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
    "double": Qt.PenStyle.SolidLine,
    "groove": Qt.PenStyle.SolidLine,
    "ridge": Qt.PenStyle.SolidLine,
    "inset": Qt.PenStyle.SolidLine,
    "outset": Qt.PenStyle.SolidLine,
}


# ─── Parsing ────────────────────────────────────────────────────────────────

def _number(value: Any, fallback: float) -> float:
    if isinstance(value, bool) or value is None:
        return fallback
    if isinstance(value, (int, float)):
        return value
    match = _LENGTH_RE.match(str(value).strip())
    if match:
        return float(match.group(1))
    return fallback


def _tidy(number: float) -> Any:
    return int(number) if float(number).is_integer() else round(number, 2)


def parse_border(value: Any) -> Optional[dict[str, Any]]:
    """Return ``None`` for none/off, a shared dict, or a normalised object."""
    if value is None:
        return None
    if isinstance(value, dict):
        if "shared" in value:
            return {"shared": value.get("shared")}
        result = {
            "width": _tidy(_number(value.get("width"), _DEFAULTS["width"])),
            "style": str(value.get("style") or _DEFAULTS["style"]).lower(),
            "color": str(value.get("color") or _DEFAULTS["color"]),
            "radius": _tidy(_number(value.get("radius"), _DEFAULTS["radius"])),
        }
        sides = value.get("sides")
        if isinstance(sides, dict):
            clean = {
                side: dict(spec) for side, spec in sides.items()
                if side in SIDES and isinstance(spec, dict)
            }
            if clean:
                result["sides"] = clean
        return result
    text = str(value).strip()
    if not text or text.lower() in ("none", "off"):
        return None
    width = _DEFAULTS["width"]
    style = _DEFAULTS["style"]
    color = _DEFAULTS["color"]
    for chunk in text.split():
        low = chunk.lower()
        if low in BORDER_STYLES:
            style = low
        elif _LENGTH_RE.match(low):
            width = _tidy(_number(low, width))
        else:
            color = chunk
    return {"width": width, "style": style, "color": color, "radius": 0}


def border_summary(value: Any) -> str:
    parsed = parse_border(value)
    if parsed is None:
        return "None"
    if "shared" in parsed:
        return f"Shared · {parsed['shared']}"
    parts = [f"{parsed['width']}px", parsed["style"]]
    if parsed["color"] not in ("currentColor", "", None):
        parts.append(str(parsed["color"]))
    if parsed.get("sides"):
        parts.append("· sides")
    return " ".join(parts)


def border_is_shared(value: Any) -> bool:
    return isinstance(value, dict) and "shared" in value


# ─── Side diagram ───────────────────────────────────────────────────────────

class BorderSidesBox(QWidget):
    """A small box diagram; each edge is a click target.

    Signals
        selected(str) — the edge the user clicked (top/right/bottom/left).
    """

    selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._overrides: set[str] = set()
        self._active = ""
        self._hover = ""
        self._enabled = True
        self.setFixedSize(64, 64)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Border sides")
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        attach_tooltip(self, lambda: self._tooltip())

    def set_state(self, overrides: Iterable[str], active: str = "") -> None:
        self._overrides = {side for side in overrides if side in SIDES}
        self._active = active if active in SIDES else ""
        self.update()

    def set_enabled_state(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        self.update()

    def _tooltip(self) -> str:
        if self._hover:
            base = f"{self._hover.title()} border"
            if self._hover in self._overrides:
                return f"{base} — overridden (click to edit)"
            return f"{base} — inherits the base border (click to override)"
        return "Click an edge to override that side"

    # ── geometry ────────────────────────────────────────────────────────────
    def _frame(self) -> QRectF:
        return QRectF(self.rect()).adjusted(9, 9, -9, -9)

    def _edge_rect(self, side: str) -> QRectF:
        frame = self._frame()
        if side == "top":
            return QRectF(frame.left(), frame.top() - 5, frame.width(), 10)
        if side == "bottom":
            return QRectF(frame.left(), frame.bottom() - 5, frame.width(), 10)
        if side == "left":
            return QRectF(frame.left() - 5, frame.top(), 10, frame.height())
        return QRectF(frame.right() - 5, frame.top(), 10, frame.height())

    def _edge_at(self, position: QPointF) -> str:
        for side in SIDES:
            if self._edge_rect(side).contains(position):
                return side
        return ""

    # ── interaction ─────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event) -> None:
        hover = self._edge_at(event.position()) if self._enabled else ""
        if hover != self._hover:
            self._hover = hover
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = ""
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._enabled:
            return
        side = self._edge_at(event.position())
        if side:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._active = side
            self.update()
            self.selected.emit(side)
            event.accept()

    def keyPressEvent(self, event) -> None:
        index = SIDES.index(self._active) if self._active in SIDES else -1
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            index = (index - 1) % len(SIDES)
        elif event.key() in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            index = (index + 1) % len(SIDES)
        elif event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return,
                             Qt.Key.Key_Enter):
            side = self._active or "top"
            self._active = side
            self.update()
            self.selected.emit(side)
            event.accept()
            return
        else:
            super().keyPressEvent(event)
            return
        self._active = SIDES[index]
        self.update()
        self.selected.emit(self._active)
        event.accept()

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    # ── painting ────────────────────────────────────────────────────────────
    def _edge_color(self, side: str) -> str:
        if side == self._active:
            return tokens.ACCENT_TEXT
        if side in self._overrides:
            return tokens.ACCENT
        if side == self._hover:
            return tokens.TEXT_PRIMARY
        return tokens.TEXT_MUTED

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        frame = self._frame()
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(frame, 3, 3)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        width = 3 if self._enabled else 2
        for side in SIDES:
            color = self._edge_color(side) if self._enabled else tokens.TEXT_MUTED
            pen = QPen(QColor(color), width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            inner = frame.adjusted(6, 6, -6, -6)
            if side == "top":
                painter.drawLine(QPointF(inner.left(), frame.top()),
                                 QPointF(inner.right(), frame.top()))
            elif side == "bottom":
                painter.drawLine(QPointF(inner.left(), frame.bottom()),
                                 QPointF(inner.right(), frame.bottom()))
            elif side == "left":
                painter.drawLine(QPointF(frame.left(), inner.top()),
                                 QPointF(frame.left(), inner.bottom()))
            else:
                painter.drawLine(QPointF(frame.right(), inner.top()),
                                 QPointF(frame.right(), inner.bottom()))
            if side in self._overrides and self._enabled:
                centre = self._edge_rect(side).center()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens.ACCENT))
                painter.drawEllipse(centre, 2.4, 2.4)
        if self._enabled and self._active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.ACCENT_TINT))
            painter.drawRoundedRect(frame.adjusted(14, 14, -14, -14), 2, 2)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()).adjusted(
                1, 1, -1, -1), tokens.RADIUS_SM)
        painter.end()


# ─── Editor ─────────────────────────────────────────────────────────────────

class BorderEditor(QWidget):
    """Inline border editor for one value.

    Signals
        changed(object) — ``"none"``, ``{"shared": name}`` or a border object
            ``{"width", "style", "color", "radius", "sides"?}``.
        preview(object) — live value while a colour drags.

    Args
        styles: allowlisted style values (caller-supplied; defaults to the
            reference list).
        width_range: inclusive bounds.
        palette: ``[(label, value)]`` for the colour fields.

    There is no radius control here. The shape radius is the container's
    ``border_radius``, edited once under Border ▸ Radius; a stored
    ``border.radius`` is preserved on the object it came from but is no longer
    offered here, because the container value wins and editing the duplicate
    looked like a dead control.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "none", *,
                 shared_options: Iterable[Any] = (),
                 palette: Iterable[tuple[str, str]] = (),
                 allow_shared: bool = True,
                 styles: Iterable[str] = BORDER_STYLES,
                 width_range: tuple[float, float] = (0, 40),
                 parent=None):
        super().__init__(parent)
        self._palette = list(palette)
        self._shared_options = coerce_options(shared_options)
        self._allow_shared = bool(allow_shared)
        self._styles = [str(style) for style in styles]
        self._width_range = width_range
        self._base: dict[str, Any] = dict(_DEFAULTS)
        self._side_specs: dict[str, dict[str, Any]] = {}
        self._editing_side: Optional[str] = None
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        modes = [ChoiceOption("none", "None"),
                 ChoiceOption("custom", "Custom")]
        if self._allow_shared and self._shared_options:
            modes.append(ChoiceOption("shared", "Shared"))
        self.mode = SegmentedToggle(modes, "none",
                                    accessible_name="Border source")
        self.mode.changed.connect(self._on_mode)
        layout.addWidget(self.mode)

        # ── shared ──────────────────────────────────────────────────────────
        self.shared_host = QWidget(self)
        shared_layout = QVBoxLayout(self.shared_host)
        shared_layout.setContentsMargins(0, 0, 0, 0)
        shared_layout.setSpacing(tokens.SPACE_4)
        self.shared_dropdown = CompactDropdown(
            self._shared_options, variant="field")
        self.shared_dropdown.changed.connect(self._emit_commit)
        shared_layout.addWidget(self.shared_dropdown)
        shared_layout.addWidget(InlineMessage(
            "The shared border is edited in its shared file.", role="muted"))
        layout.addWidget(self.shared_host)

        # ── custom ──────────────────────────────────────────────────────────
        self.custom_host = QWidget(self)
        custom = QVBoxLayout(self.custom_host)
        custom.setContentsMargins(0, 0, 0, 0)
        custom.setSpacing(tokens.SPACE_4)

        style_options = [ChoiceOption(style, style.title())
                         for style in self._styles]
        self.width_field = NumberField(
            1, minimum=width_range[0], maximum=width_range[1],
            integer=True, label="Border width")
        self.style_dropdown = CompactDropdown(
            style_options, "solid", variant="field")
        attach_tooltip(self.style_dropdown, "Border style")
        width_host = QWidget(self)
        width_row = QHBoxLayout(width_host)
        width_row.setContentsMargins(0, 0, 0, 0)
        width_row.setSpacing(tokens.SPACE_4)
        self.width_field.setFixedWidth(62)
        width_row.addWidget(self.width_field, 0)
        width_row.addWidget(self.style_dropdown, 1)
        custom.addWidget(PropertyRow("Width", width_host, label_width=52))

        self.color_field = ColorField(
            "currentColor", palette=self._palette,
            keywords=("currentColor", "inherit"), nullable=False)
        color_host = QWidget(self)
        color_row = QHBoxLayout(color_host)
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(tokens.SPACE_4)
        color_row.addWidget(self.color_field, 1)
        custom.addWidget(PropertyRow("Color", color_host, label_width=52))

        sides_head = QWidget(self)
        sides_head_row = QHBoxLayout(sides_head)
        sides_head_row.setContentsMargins(0, 0, 0, 0)
        sides_head_row.setSpacing(tokens.SPACE_4)
        self.sides_note = InlineMessage("Sides", role="muted")
        sides_head_row.addWidget(self.sides_note, 1)
        self.clear_side = IconButton(
            glyph="close", tooltip="Clear this side override",
            accessible_name="Clear side override", parent=self)
        self.clear_side.clicked.connect(self._clear_side)
        self.clear_side.setVisible(False)
        sides_head_row.addWidget(self.clear_side, 0)
        custom.addWidget(sides_head)

        sides_row = QWidget(self)
        sides_row_layout = QHBoxLayout(sides_row)
        sides_row_layout.setContentsMargins(0, 0, 0, 0)
        sides_row_layout.setSpacing(tokens.SPACE_8)
        self.sides_box = BorderSidesBox(self)
        self.sides_box.selected.connect(self._on_side_selected)
        sides_row_layout.addWidget(self.sides_box, 0)
        self.side_hint = InlineMessage(
            "Click an edge to override that side.", role="muted")
        sides_row_layout.addWidget(self.side_hint, 1)
        custom.addWidget(sides_row)

        self.side_host = QWidget(self)
        side_layout = QVBoxLayout(self.side_host)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(tokens.SPACE_4)
        side_style_options = [ChoiceOption(style, style.title())
                              for style in self._styles]
        self.side_width = NumberField(
            1, minimum=width_range[0], maximum=width_range[1],
            integer=True, label="Side width")
        self.side_style = CompactDropdown(
            side_style_options, "solid", variant="field")
        attach_tooltip(self.side_style, "Side border style")
        side_width_host = QWidget(self)
        side_width_row = QHBoxLayout(side_width_host)
        side_width_row.setContentsMargins(0, 0, 0, 0)
        side_width_row.setSpacing(tokens.SPACE_4)
        self.side_width.setFixedWidth(62)
        side_width_row.addWidget(self.side_width, 0)
        side_width_row.addWidget(self.side_style, 1)
        side_layout.addWidget(
            PropertyRow("Width", side_width_host, label_width=52))

        self.side_color = ColorField(
            "currentColor", palette=self._palette,
            keywords=("currentColor", "inherit"), nullable=False)
        side_color_host = QWidget(self)
        side_color_row = QHBoxLayout(side_color_host)
        side_color_row.setContentsMargins(0, 0, 0, 0)
        side_color_row.setSpacing(tokens.SPACE_4)
        side_color_row.addWidget(self.side_color, 1)
        side_layout.addWidget(
            PropertyRow("Color", side_color_host, label_width=52))
        custom.addWidget(self.side_host)

        layout.addWidget(self.custom_host)

        # Commits are routed by the row that produced them: a base field owns
        # the base, the side row owns the selected side's override. Routing
        # both through one handler materialised a side override from the
        # seeded side fields on every base edit, which pinned that side to the
        # old base values.
        for signal in (self.width_field.changed, self.style_dropdown.changed,
                       self.color_field.changed):
            signal.connect(self._emit_base_commit)
        for signal in (self.side_width.changed, self.side_style.changed,
                       self.side_color.changed):
            signal.connect(self._emit_side_commit)
        for signal in (self.width_field.preview, self.color_field.preview,
                       self.side_width.preview, self.side_color.preview):
            signal.connect(self._emit_preview)

        self.set_value(value)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        """The border these fields describe, with committed side overrides."""
        return self._compose(self._side_specs)

    def _compose(self, side_specs: dict[str, dict[str, Any]]) -> Any:
        mode = self.mode.value()
        if mode == "none":
            return "none"
        if mode == "shared":
            name = self.shared_dropdown.value()
            return {"shared": name} if name else "none"
        base = self._live_base()
        sides: dict[str, dict[str, Any]] = {}
        for side, spec in side_specs.items():
            diff = {key: value for key, value in spec.items()
                    if base.get(key) != value}
            if diff:
                sides[side] = diff
        if sides:
            base["sides"] = sides
        return base

    def _live_side_specs(self) -> dict[str, dict[str, Any]]:
        """``_side_specs`` with the side being dragged folded in.

        A drag updates the fields, not the model: ``_side_specs`` only learns
        the override on release. Composing a preview from the model therefore
        dropped the side edit the operator was looking at, so the preview pane
        froze while the width or colour of one side dragged.
        """
        if not self._editing_side:
            return self._side_specs
        specs = dict(self._side_specs)
        spec = self._selected_side_spec()
        if spec:
            specs[self._editing_side] = spec
        else:
            specs.pop(self._editing_side, None)
        return specs

    def set_value(self, value: Any) -> None:
        self._updating = True
        try:
            parsed = parse_border(value)
            if parsed is None:
                self.mode.set_value("none")
                self._base = dict(_DEFAULTS)
                self._side_specs = {}
            elif "shared" in parsed:
                if self._allow_shared and self._shared_options:
                    self.mode.set_value("shared")
                    self.shared_dropdown.set_value(parsed["shared"])
                else:
                    self.mode.set_value("none")
            else:
                self.mode.set_value("custom")
                self._base = {
                    "width": parsed["width"],
                    "style": parsed["style"],
                    "color": parsed["color"],
                    "radius": parsed["radius"],
                }
                self._side_specs = dict(parsed.get("sides", {}))
            self._sync_fields()
            self._apply_mode()
        finally:
            self._updating = False

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self.color_field.set_palette(self._palette)
        self.side_color.set_palette(self._palette)

    def set_shared_options(self, options: Iterable[Any]) -> None:
        self._shared_options = coerce_options(options)
        self.shared_dropdown.set_options(self._shared_options)

    def set_editing_side(self, side: str) -> None:
        """Select a side programmatically (used by the gallery)."""
        if side in SIDES:
            self._on_side_selected(side)

    # ── syncing ─────────────────────────────────────────────────────────────
    def _live_base(self) -> dict[str, Any]:
        """The border the fields describe, radius carried over unchanged."""
        return {
            "width": _tidy(self.width_field.numeric_value() or 0),
            "style": self.style_dropdown.value() or "solid",
            "color": self.color_field.value() or "currentColor",
            "radius": _tidy(self._base.get("radius") or 0),
        }

    def _sync_fields(self) -> None:
        """Write every field from the model (a freshly loaded value)."""
        base = self._base
        self.width_field.set_value(base["width"])
        self.style_dropdown.set_options(
            [ChoiceOption(style, style.title()) for style in self._styles],
            value=base["style"])
        self.color_field.set_value(base["color"])
        self._sync_side_fields()
        overrides = self._override_set()
        self._refresh_side_chrome(overrides)

    def _sync_side_fields(self) -> None:
        """Seed the selected side's row from the base the operator sees.

        Reading ``_base`` here reset the whole base row to the value the
        popover opened with as soon as a side was clicked — the base fields
        are edited live and only ``_live_base()`` knows what they hold. It
        also seeded the side from stale numbers, so touching one property
        wrote the others into the override.
        """
        side = self._editing_side
        if not side:
            return
        live = self._live_base()
        spec = self._side_specs.get(side)
        values = dict(live)
        if spec:
            values.update({key: value for key, value in spec.items()
                           if key in live})
        self.side_width.set_value(values["width"])
        self.side_style.set_options(
            [ChoiceOption(style, style.title()) for style in self._styles],
            value=values["style"])
        self.side_color.set_value(values["color"])

    def _override_set(self) -> set[str]:
        base = self._live_base()
        result = set()
        for side, spec in self._side_specs.items():
            if any(base.get(key) != value for key, value in spec.items()):
                result.add(side)
        return result

    def _refresh_side_chrome(self, overrides: set[str]) -> None:
        self.sides_box.set_state(overrides, self._editing_side or "")
        if self._editing_side:
            self.sides_note.setText(
                f"Editing {self._editing_side.title()}")
            self.clear_side.setVisible(
                self._editing_side in overrides)
            self.side_hint.setText(
                "Overridden" if self._editing_side in overrides
                else "Inherits the base border")
        else:
            self.sides_note.setText("Sides")
            self.clear_side.setVisible(False)
            self.side_hint.setText("Click an edge to override that side.")
        self.side_host.setVisible(bool(self._editing_side))

    def _apply_mode(self) -> None:
        mode = self.mode.value()
        self.custom_host.setVisible(mode == "custom")
        self.shared_host.setVisible(mode == "shared")
        self._refresh_side_chrome(self._override_set())

    # ── events ──────────────────────────────────────────────────────────────
    def _on_mode(self, mode: str) -> None:
        """Switch the editor and commit the new source.

        The switch used to be a preview only, because a commit closed the
        surface. That made "None" a lie: it painted, then the dismiss rewound
        the value, so the border came back. A commit keeps the surface open
        now, so the switch can commit like any other edit.
        """
        self._apply_mode()
        if self._updating:
            return
        self.changed.emit(self.value())

    def _on_side_selected(self, side: str) -> None:
        if self._updating:
            return
        self._editing_side = side
        self._sync_side_fields()
        self._refresh_side_chrome(self._override_set())

    def _clear_side(self) -> None:
        if self._editing_side:
            self._side_specs.pop(self._editing_side, None)
            self._sync_side_fields()
            self._refresh_side_chrome(self._override_set())
            self._emit_commit()

    def _selected_side_spec(self) -> dict[str, Any]:
        """Only what the side row changes; anything else inherits the base.

        The colour row is seeded with the base colour, so storing it
        unconditionally made every side edit an unremovable colour override
        and stopped later base-colour edits from reaching that side.
        """
        base = self._live_base()
        full = {
            "width": _tidy(self.side_width.numeric_value() or 0),
            "style": self.side_style.value() or "solid",
            "color": self.side_color.value() or "currentColor",
        }
        return {key: value for key, value in full.items()
                if base.get(key) != value}

    def _emit_commit(self, *_args) -> None:
        """A source-level pick (the shared dropdown) commits the whole value."""
        if self._updating:
            return
        self.changed.emit(self.value())

    def _emit_base_commit(self, *_args) -> None:
        """A base field writes the base only; sides keep their overrides."""
        if self._updating:
            return
        # The fields are the base now: ``_sync_fields`` and the side seed read
        # this, so a stale model rewrote the row with the values the popover
        # opened with (and seeded sides from numbers nobody had on screen).
        self._base = self._live_base()
        self._refresh_side_chrome(self._override_set())
        self.changed.emit(self.value())

    def _emit_side_commit(self, *_args) -> None:
        """The side row owns the selected side's override, nothing else."""
        if self._updating:
            return
        if self._editing_side:
            spec = self._selected_side_spec()
            if spec:
                self._side_specs[self._editing_side] = spec
            else:
                self._side_specs.pop(self._editing_side, None)
            self._refresh_side_chrome(self._override_set())
        self.changed.emit(self.value())

    def _emit_preview(self, *_args) -> None:
        if self._updating:
            return
        self.preview.emit(self._compose(self._live_side_specs()))


# ─── Compact field ──────────────────────────────────────────────────────────

class _BorderPreview(QWidget):
    """Paints a small rounded box wearing the border."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value: Any = "none"
        self._palette: dict[str, str] = {}
        self.setFixedSize(26, 18)

    def set_value(self, value: Any, palette: dict[str, str]) -> None:
        self._value = value
        self._palette = palette
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        parsed = parse_border(self._value)
        if parsed is None or "shared" in parsed:
            width = 1 if parsed is not None else 1
            color = tokens.TEXT_MUTED
            pen_style = (Qt.PenStyle.SolidLine if parsed is not None
                         else Qt.PenStyle.DotLine)
            radius = 3
            if parsed is not None:
                color = tokens.ACCENT_TEXT
        else:
            width = max(1, min(3, int(parsed["width"] or 1)))
            raw = str(parsed["color"])
            if raw.startswith("@") and raw[1:] in self._palette:
                raw = self._palette[raw[1:]]
            color = qcolor(raw if raw != "currentColor"
                           else tokens.TEXT_SECONDARY).name()
            pen_style = _PEN_STYLES.get(parsed["style"],
                                        Qt.PenStyle.SolidLine)
            radius = int(min(6, max(2, (parsed["radius"] or 0) / 2)))
        painter.setBrush(QColor(tokens.BG_PANEL))
        painter.setPen(QPen(QColor(color), width, pen_style))
        painter.drawRoundedRect(rect, radius, radius)
        painter.end()


class _BorderPopover(PopupSurface):
    committed = pyqtSignal(object)
    previewed = pyqtSignal(object)
    cancelled = pyqtSignal()

    def __init__(self, value: Any, *, shared_options=(), palette=(),
                 allow_shared=True, parent=None):
        super().__init__(parent)
        self._open_value = value
        #: A commit writes through but keeps the surface open, so the close
        #: that follows is a dismissal, not a cancel. Without this flag
        #: ``closeEvent`` emitted ``cancelled``, the field rewound to the value
        #: it opened with, and the row showed "None" again even though the
        #: edit had landed.
        self._committed = False
        #: A mode switch is a preview, not a commit. Tracking it separately
        #: keeps a preview made *after* a commit honest: dismissing that still
        #: rewinds it, while dismissing committed fields does not.
        self._preview_open = False
        self.editor = BorderEditor(
            value, shared_options=shared_options, palette=palette,
            allow_shared=allow_shared, parent=self)
        self.content.addWidget(self.editor)
        self.editor.changed.connect(self._on_committed)
        self.editor.preview.connect(self._on_previewed)

    def _on_previewed(self, value: Any) -> None:
        self._preview_open = True
        self.previewed.emit(value)

    def _on_committed(self, value: Any) -> None:
        """Write the edit through and stay open.

        The surface edits several values (width, style, colour, per-side
        overrides). Closing on the first commit made the rest unreachable: the
        operator had to reopen the popover once per field, and a colour edit
        closed it before the style could be set. Every commit lands on the
        document immediately; the surface closes when it is dismissed (click
        away or Escape), which is the contract the colour, paint and shadow
        popovers already follow.
        """
        self._committed = True
        self._preview_open = False
        self.committed.emit(value)

    def closeEvent(self, event) -> None:
        if self.isVisible() and (self._preview_open or not self._committed):
            self.cancelled.emit()
        super().closeEvent(event)


class BorderField(QWidget):
    """One-line border summary that opens BorderEditor in a popover.

    Signals
        changed(object) — committed value (same shapes as BorderEditor).
        preview(object) — live value while the popover edits.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)

    def __init__(self, value: Any = "none", *,
                 shared_options: Iterable[Any] = (),
                 palette: Iterable[tuple[str, str]] = (),
                 allow_shared: bool = True, parent=None):
        super().__init__(parent)
        self._value: Any = "none" if value is None else value
        self._shared_options = coerce_options(shared_options)
        self._palette = list(palette)
        self._allow_shared = bool(allow_shared)
        self._hover = False
        self._warning = ""
        self._popover: Optional[_BorderPopover] = None
        self._open_value: Any = self._value
        self._suppress_press = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("Border")
        attach_tooltip(self, lambda: self._warning or border_summary(
            self._value))

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        return self._value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()
        if emit:
            self.changed.emit(self._value)

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self._palette = list(palette)
        self.update()

    def set_shared_options(self, options: Iterable[Any]) -> None:
        self._shared_options = coerce_options(options)

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

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
        popover = _BorderPopover(
            self._value, shared_options=self._shared_options,
            palette=self._palette, allow_shared=self._allow_shared,
            parent=self)
        self._popover = popover
        self._open_value = self._value
        popover.committed.connect(self._on_committed)
        popover.previewed.connect(self._on_preview)
        popover.cancelled.connect(self._on_cancelled)
        popover.destroyed.connect(
            lambda *_args, _popover=popover: self._on_destroyed(_popover))
        self._suppress_press = True
        QTimer.singleShot(0, self._clear_suppressed_press)
        popover.show_below(self, width=288, max_height=520, align="left")

    def _clear_suppressed_press(self) -> None:
        self._suppress_press = False

    def _on_committed(self, value: Any) -> None:
        self._value = value
        # The next cancel must rewind to this value, not to the one the
        # previous opening started from.
        self._open_value = value
        self.update()
        self.changed.emit(value)

    def _on_preview(self, value: Any) -> None:
        self._value = value
        self.update()
        self.preview.emit(value)

    def _on_cancelled(self) -> None:
        self._value = self._open_value
        self.update()
        self.preview.emit(self._value)

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

        preview = _BorderPreview(self)
        preview.set_value(self._value, dict(self._palette))
        preview.render(painter,
                       QPointF(rect.left() + 4, rect.center().y() - 9).toPoint())
        text_rect = QRectF(rect.left() + 36, rect.top(),
                           max(0.0, rect.width() - 54), rect.height())
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_PRIMARY if enabled
                              else tokens.TEXT_MUTED))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(label_font).elidedText(
                border_summary(self._value), Qt.TextElideMode.ElideRight,
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
    "BORDER_STYLES", "SIDES", "parse_border", "border_summary",
    "border_is_shared", "BorderSidesBox", "BorderEditor", "BorderField",
]
