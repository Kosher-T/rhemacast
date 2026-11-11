"""ui/theme_kit/chip_select.py

ChipSelect — wrapping choice pills — and ChoiceField, the caller-level helper
that decides whether a choice set is better served by chips or a dropdown.

Like every kit control these are caller-driven: the number of options, their
labels, disabled reasons and the chosen value all come from outside. Nothing
here knows a theme property name.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, coerce_options, font, icon_pixmap, paint_focus_ring,
    paints_icon,
)
from ui.theme_kit.flow import FlowLayout
from ui.theme_kit.popup import attach_tooltip


class _Chip(QAbstractButton):
    """One painted pill. Checkable state is owned by the parent group."""

    def __init__(self, option: ChoiceOption, *, parent=None):
        super().__init__(parent)
        self._option = option
        self._hover = False
        self._group: Optional["ChipSelect"] = None
        self.setText(option.text)
        self.setCheckable(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor
                       if not option.disabled_reason
                       else Qt.CursorShape.ArrowCursor)
        self.setAccessibleName(option.text)
        self.setEnabled(not bool(option.disabled_reason))
        if option.tooltip or option.disabled_reason:
            attach_tooltip(self, option.tooltip or option.disabled_reason)

    def option(self) -> ChoiceOption:
        return self._option

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(tokens.TYPE_CAPTION,
                                    tokens.WEIGHT_MEDIUM))
        # 22 px: 9 left inset + 8 right inset + antialias/rounding slack,
        # so the painted elide never eats the last glyph.
        width = metrics.horizontalAdvance(self._option.text) + 22
        if paints_icon(self._option.icon):
            width += 18
        return QSize(max(34, width), tokens.CONTROL_HEIGHT_SM)

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

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if self._group is not None and key in (
                Qt.Key.Key_Left, Qt.Key.Key_Up, Qt.Key.Key_Right,
                Qt.Key.Key_Down):
            self._group.focus_step(self, -1 if key in (
                Qt.Key.Key_Left, Qt.Key.Key_Up) else 1)
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        checked = self.isChecked()
        radius = rect.height() / 2

        if not enabled:
            fill = tokens.BG_PANEL
            edge = tokens.BORDER_HAIRLINE
            text = tokens.TEXT_MUTED
        elif checked and self._option.muted:
            # An "inherit/none/auto" choice is a selected *absence*: outline it
            # instead of filling it like a real value.
            fill = tokens.BG_FIELD
            edge = tokens.ACCENT
            text = tokens.TEXT_SECONDARY
        elif checked:
            fill = tokens.ACCENT_TINT
            edge = tokens.ACCENT
            text = tokens.TEXT_PRIMARY
        elif self._hover:
            fill = tokens.BG_CARD_HOVER
            edge = tokens.BORDER_POPOVER
            text = tokens.TEXT_PRIMARY
        else:
            fill = tokens.BG_FIELD
            edge = tokens.BORDER_HAIRLINE
            text = (tokens.TEXT_MUTED if self._option.muted
                    else tokens.TEXT_SECONDARY)

        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, radius, radius)

        left = rect.left() + 9
        if paints_icon(self._option.icon):
            pixmap = icon_pixmap(self._option.icon, 12).pixmap(12, 12)
            painter.drawPixmap(int(left), int(rect.center().y() - 6), pixmap)
            left += 17
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
        painter.setFont(label_font)
        painter.setPen(QColor(text))
        text_rect = QRectF(left, rect.top(),
                           max(0.0, rect.right() - left - 8),
                           rect.height())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(label_font).elidedText(
                self.text(), Qt.TextElideMode.ElideRight,
                int(text_rect.width())))

        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
        painter.end()


class ChipSelect(QWidget):
    """A wrapping single- or multi-choice pill group.

    Signals
        changed(object) — single mode: one value (or None when deselected);
            multi mode: a list of values in option order.
    """

    changed = pyqtSignal(object)

    def __init__(self, options: Iterable[Any] = (), value: Any = None, *,
                 multi: bool = False, allow_deselect: bool = False,
                 h_spacing: int = tokens.SPACE_4,
                 v_spacing: int = tokens.SPACE_4, parent=None):
        super().__init__(parent)
        self._options = coerce_options(options)
        self._multi = bool(multi)
        self._allow_deselect = bool(allow_deselect)
        self._selected: list[Any] = []
        self._chips: list[_Chip] = []
        self._last_width = 0
        self._layout = FlowLayout(self, margin=0, h_spacing=h_spacing,
                                  v_spacing=v_spacing)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._build()
        if self._multi:
            if isinstance(value, (list, tuple, set)):
                self.set_values(list(value))
            elif value is not None:
                self.set_values([value])
        else:
            self.set_value(value)

    # ── construction ────────────────────────────────────────────────────────
    def _clear_chips(self) -> None:
        for chip in self._chips:
            self._layout.removeWidget(chip)
            chip.setParent(None)
            chip.deleteLater()
        self._chips = []

    def _build(self) -> None:
        self._clear_chips()
        for option in self._options:
            chip = _Chip(option)
            chip._group = self
            chip.clicked.connect(lambda _checked=False, c=chip: self._on_chip(c))
            self._layout.addWidget(chip)
            self._chips.append(chip)
        self._sync_chips()

    def _on_chip(self, chip: _Chip) -> None:
        option = chip.option()
        if option.disabled_reason:
            return
        value = option.value
        if self._multi:
            values = list(self._selected)
            if value in values:
                values.remove(value)
            else:
                values.append(value)
            self._selected = values
            self._sync_chips()
            self.changed.emit(self.value())
            return
        if self._selected and self._selected[0] == value:
            if self._allow_deselect:
                self._selected = []
                self._sync_chips()
                self.changed.emit(None)
            else:
                chip.setChecked(True)
            return
        self._selected = [value]
        self._sync_chips()
        self.changed.emit(value)

    def _sync_chips(self) -> None:
        for chip in self._chips:
            chip.setChecked(chip.option().value in self._selected)

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        if self._multi:
            return [option.value for option in self._options
                    if option.value in self._selected]
        return self._selected[0] if self._selected else None

    def values(self) -> list[Any]:
        return list(self.value()) if self._multi else (
            [self.value()] if self._selected else [])

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        if self._multi:
            self.set_values(value if isinstance(value, (list, tuple, set))
                            else ([] if value is None else [value]), emit=emit)
            return
        if value is not None and not any(
                option.value == value for option in self._options):
            return
        self._selected = [] if value is None else [value]
        self._sync_chips()
        if emit:
            self.changed.emit(self.value())

    def set_values(self, values: Iterable[Any], *, emit: bool = False) -> None:
        wanted = list(values)
        self._selected = [option.value for option in self._options
                          if option.value in wanted]
        self._sync_chips()
        if emit:
            self.changed.emit(self.value())

    def set_options(self, options: Iterable[Any], *,
                    value: Any = ..., emit: bool = False) -> None:
        self._options = coerce_options(options)
        if value is not ...:
            self._selected = [] if value is None else (
                list(value) if isinstance(value, (list, tuple, set))
                else [value])
        else:
            allowed = {option.value for option in self._options}
            self._selected = [v for v in self._selected if v in allowed]
        self._build()
        if emit:
            self.changed.emit(self.value())

    def options(self) -> list[ChoiceOption]:
        return list(self._options)

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    def focus_step(self, current: _Chip, direction: int) -> None:
        if not self._chips:
            return
        index = self._chips.index(current) if current in self._chips else 0
        count = len(self._chips)
        for _ in range(count):
            index = (index + direction) % count
            chip = self._chips[index]
            if chip.isEnabled():
                chip.setFocus(Qt.FocusReason.TabFocusReason)
                return

    def sizeHint(self) -> QSize:
        resized = self.testAttribute(Qt.WidgetAttribute.WA_Resized)
        width = max(1, self.width() if resized else 220)
        return QSize(width, self._layout.heightForWidth(width))

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._layout.heightForWidth(width)


class ChoiceField(QWidget):
    """One-call choice control that picks chips or a dropdown.

    ``style`` is ``"auto"``, ``"chips"`` or ``"dropdown"``. Auto picks chips
    only when the set is short, flat and label-driven; long, grouped, icon or
    font-preview lists stay a dropdown.
    """

    changed = pyqtSignal(object)
    opened = pyqtSignal()

    def __init__(self, options: Iterable[Any] = (), value: Any = None, *,
                 style: str = "auto", multi: bool = False,
                 chip_limit: int = 7, label_limit: int = 14,
                 searchable: bool = False, parent=None):
        super().__init__(parent)
        self._options = coerce_options(options)
        self._style = style
        self._multi = bool(multi)
        self._chip_limit = chip_limit
        self._label_limit = label_limit
        self._searchable = bool(searchable)
        self._value = value
        self._control: Optional[QWidget] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self._layout = layout
        self._build()

    def _decide(self) -> str:
        if self._style in ("chips", "dropdown"):
            return self._style
        if self._multi:
            return "chips"
        if len(self._options) > self._chip_limit:
            return "dropdown"
        for option in self._options:
            if option.group or option.font_family or paints_icon(option.icon):
                return "dropdown"
            if len(option.text) > self._label_limit:
                return "dropdown"
        return "chips"

    def _build(self) -> None:
        if self._control is not None:
            self._layout.removeWidget(self._control)
            self._control.setParent(None)
            self._control.deleteLater()
            self._control = None
        if self._decide() == "chips":
            control = ChipSelect(self._options, self._value,
                                 multi=self._multi)
            control.changed.connect(self._on_changed)
        else:
            from ui.theme_kit.dropdown import CompactDropdown
            control = CompactDropdown(
                self._options, self._value, searchable=self._searchable)
            control.changed.connect(self._on_changed)
            control.opened.connect(self.opened)
        self._control = control
        self._layout.addWidget(control)

    def _on_changed(self, value: Any) -> None:
        self._value = value
        self.changed.emit(value)

    def control(self) -> Optional[QWidget]:
        return self._control

    def value(self) -> Any:
        return self._control.value() if self._control is not None else self._value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        self._value = value
        if self._control is not None:
            self._control.set_value(value, emit=emit)

    def set_options(self, options: Iterable[Any], *,
                    value: Any = ..., emit: bool = False) -> None:
        self._options = coerce_options(options)
        if value is not ...:
            self._value = value
        self._build()
        if emit:
            self.changed.emit(self.value())

    def set_style(self, style: str) -> None:
        self._style = style
        self._build()

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)
        if self._control is not None:
            self._control.setAccessibleName(text)


__all__ = ["ChipSelect", "ChoiceField"]
