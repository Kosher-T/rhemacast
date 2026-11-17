"""ui/theme_kit/segmented.py

SegmentedToggle — a compact exclusive icon/word switch — and ToggleButton,
the single checkable icon button used by text-format and layer toolbars.

Both are painted so Windows and Linux agree on segment insets, hover washes
and the focus ring. Segment labels are caller-owned; nothing here knows a
theme property.
"""

from __future__ import annotations

from typing import Any, Iterable

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import QAbstractButton, QSizePolicy, QWidget

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, coerce_options, font, icon_pixmap, paint_focus_ring,
    paints_icon,
)
from ui.theme_kit.popup import attach_tooltip


class SegmentedToggle(QWidget):
    """One-of-N switch with equal-width painted segments.

    Signals
        changed(object) — the selected value.
    """

    changed = pyqtSignal(object)

    def __init__(self, options: Iterable[Any] = (), value: Any = None, *,
                 allow_empty: bool = False, min_segment: int = 26,
                 accessible_name: str = "Options", parent=None):
        super().__init__(parent)
        self._options = coerce_options(options)
        self._value = value
        self._allow_empty = bool(allow_empty)
        self._min_segment = int(min_segment)
        self._hover_index = -1
        self._pressed_index = -1
        #: Focus ring is for keyboard users only: a click selects a segment and
        #: is already obvious, so it must not outline the whole row.
        self._keyboard_focus = True
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setAccessibleName(accessible_name)
        attach_tooltip(self, lambda: self._tooltip_text())
        if self._value is None and self._options and not self._allow_empty:
            self._value = self._options[0].value

    # ── public ──────────────────────────────────────────────────────────────
    def value(self) -> Any:
        return self._value

    def set_value(self, value: Any, *, emit: bool = False) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()
        if emit:
            self.changed.emit(value)

    def set_options(self, options: Iterable[Any], *,
                    value: Any = ..., emit: bool = False) -> None:
        self._options = coerce_options(options)
        if value is not ...:
            self._value = value
        elif not any(option.value == self._value
                     for option in self._options):
            self._value = (self._options[0].value
                           if self._options and not self._allow_empty else None)
        self.updateGeometry()
        self.update()
        if emit:
            self.changed.emit(self._value)

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    def _index_for(self, value: Any) -> int:
        for index, option in enumerate(self._options):
            if option.value == value:
                return index
        return -1

    def _tooltip_text(self) -> str:
        if 0 <= self._hover_index < len(self._options):
            option = self._options[self._hover_index]
            return option.tooltip or option.disabled_reason
        return ""

    # ── geometry ────────────────────────────────────────────────────────────
    def _segment_width(self) -> float:
        if not self._options:
            return self.width()
        return (self.width() - 4) / len(self._options)

    def _segment_rect(self, index: int) -> QRectF:
        width = self._segment_width()
        return QRectF(2 + index * width, 2, width, self.height() - 4)

    def _index_at(self, x: float) -> int:
        if not self._options:
            return -1
        width = self._segment_width()
        if width <= 0:
            return -1
        index = int((x - 2) // width)
        return index if 0 <= index < len(self._options) else -1

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(tokens.TYPE_CAPTION))
        width = 4
        for option in self._options:
            segment = self._min_segment
            if paints_icon(option.icon):
                segment = max(segment, 26)
            if option.text:
                extra = metrics.horizontalAdvance(option.text) + 14
                if paints_icon(option.icon):
                    extra += 17
                segment = max(segment, extra)
            width += segment
        return QSize(width, tokens.CONTROL_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(max(30, len(self._options) * self._min_segment),
                     tokens.CONTROL_HEIGHT)

    # ── interaction ─────────────────────────────────────────────────────────
    def _select_index(self, index: int) -> None:
        if not (0 <= index < len(self._options)):
            return
        option = self._options[index]
        if option.disabled_reason:
            return
        if option.value == self._value:
            if self._allow_empty:
                self._value = None
                self.update()
                self.changed.emit(None)
            return
        self._value = option.value
        self.update()
        self.changed.emit(option.value)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position().x())
        self._pressed_index = index
        self._keyboard_focus = False
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(event.position().x())
        if index != self._hover_index:
            self._hover_index = index
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position().x())
        if index == self._pressed_index:
            self._select_index(index)
        self._pressed_index = -1
        event.accept()

    def leaveEvent(self, event) -> None:
        self._hover_index = -1
        self.update()
        super().leaveEvent(event)

    def focusInEvent(self, event) -> None:
        # Every focus reason except a click keeps the ring: pointer users have
        # the selected segment as their cue, keyboard users have nothing else.
        if event.reason() != Qt.FocusReason.MouseFocusReason:
            self._keyboard_focus = True
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self._keyboard_focus = True
        self.update()
        super().focusOutEvent(event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        current = self._index_for(self._value)
        # Reaching the widget by keyboard, then using it, keeps the ring on.
        self._keyboard_focus = True
        self.update()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self._step(-1)
            event.accept()
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self._step(1)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            self._select_index(0)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            self._select_index(len(self._options) - 1)
            event.accept()
            return
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if current < 0:
                self._select_index(0)
            event.accept()
            return
        super().keyPressEvent(event)

    def _step(self, direction: int) -> None:
        if not self._options:
            return
        index = self._index_for(self._value)
        if index < 0:
            index = 0 if direction > 0 else len(self._options) - 1
        for _ in range(len(self._options)):
            index = (index + direction) % len(self._options)
            if not self._options[index].disabled_reason:
                self._select_index(index)
                return

    # ── painting ────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        outer = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.setBrush(QColor(tokens.BG_FIELD))
        painter.drawRoundedRect(outer, tokens.RADIUS_SM, tokens.RADIUS_SM)

        selected_index = self._index_for(self._value)
        for index, option in enumerate(self._options):
            rect = self._segment_rect(index)
            enabled = self.isEnabled() and not option.disabled_reason
            if index == selected_index and enabled:
                painter.setPen(QPen(QColor(tokens.ACCENT), 1))
                painter.setBrush(QColor(tokens.ACCENT_TINT))
                painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5),
                                        4, 4)
            elif index == self._hover_index and enabled:
                painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER))

            if not enabled:
                color = tokens.TEXT_MUTED
            elif index == selected_index:
                color = tokens.TEXT_PRIMARY
            else:
                color = tokens.TEXT_SECONDARY

            has_icon = paints_icon(option.icon)
            label_font = font(tokens.TYPE_CAPTION,
                              tokens.WEIGHT_SEMIBOLD
                              if index == selected_index
                              else tokens.WEIGHT_MEDIUM)
            metrics = QFontMetrics(label_font)
            text_w = metrics.horizontalAdvance(option.text) if option.text else 0
            icon_w = 16 if has_icon else 0
            gap = 5 if (has_icon and option.text) else 0
            # Centre the whole icon+label group once. Centring the label a
            # second time inside the remaining rect drifted it to the right.
            content_w = icon_w + gap + text_w
            start = rect.center().x() - content_w / 2
            if has_icon:
                pixmap = icon_pixmap(option.icon, 14).pixmap(14, 14)
                painter.drawPixmap(int(start), int(rect.center().y() - 7),
                                   pixmap)
                start += icon_w + gap
            if option.text:
                painter.setFont(label_font)
                painter.setPen(QColor(color))
                text_rect = QRectF(start, rect.top(),
                                   max(0.0, text_w), rect.height())
                painter.drawText(
                    text_rect,
                    int(Qt.AlignmentFlag.AlignLeft
                        | Qt.AlignmentFlag.AlignVCenter),
                    metrics.elidedText(option.text,
                                       Qt.TextElideMode.ElideRight,
                                       int(text_rect.width())))
            if index == selected_index and enabled:
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens.ACCENT))
                y = rect.bottom() - 2
                painter.drawRoundedRect(
                    QRectF(rect.center().x() - 6, y, 12, 2), 1, 1)

        if self.hasFocus() and self._keyboard_focus:
            # Ring the current segment, not the whole row: the row-wide ring
            # read as "this entire switch is selected".
            ring = self._segment_rect(
                selected_index if selected_index >= 0 else 0)
            paint_focus_ring(painter, ring.adjusted(0.5, 0.5, -0.5, -0.5), 4)
        painter.end()


class ToggleButton(QAbstractButton):
    """A single checkable icon/word button (bold, italic, lock, ...).

    Signals
        changed(bool) — emitted after a user toggle.
    """

    changed = pyqtSignal(bool)

    def __init__(self, icon: Any = None, text: str = "", *,
                 checked: bool = False, tooltip: str = "",
                 accessible_name: str = "", parent=None):
        super().__init__(parent)
        self._icon = icon
        self._hover = False
        self.setCheckable(True)
        self.setChecked(bool(checked))
        self.setText(str(text))
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        name = accessible_name or tooltip or text or "Toggle"
        self.setAccessibleName(name)
        if tooltip:
            attach_tooltip(self, tooltip)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.update()
        self.changed.emit(bool(checked))

    def value(self) -> bool:
        return self.isChecked()

    def set_value(self, checked: bool, *, emit: bool = False) -> None:
        if self.isChecked() == bool(checked):
            return
        self.setChecked(bool(checked))
        self.update()
        if emit:
            self.changed.emit(bool(checked))

    def set_icon(self, icon: Any) -> None:
        self._icon = icon
        self.update()

    def sizeHint(self) -> QSize:
        width = tokens.CONTROL_HEIGHT
        if self.text():
            width += QFontMetrics(font(tokens.TYPE_CAPTION)).horizontalAdvance(
                self.text()) + 8
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
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        checked = self.isChecked()
        if not enabled:
            fill, edge, color = (tokens.BG_PANEL, tokens.BORDER_HAIRLINE,
                                 tokens.TEXT_MUTED)
        elif checked:
            fill, edge, color = (tokens.ACCENT_TINT, tokens.ACCENT,
                                 tokens.TEXT_PRIMARY)
        elif self._hover:
            fill, edge, color = (tokens.BG_CARD_HOVER,
                                 tokens.BORDER_POPOVER,
                                 tokens.TEXT_PRIMARY)
        else:
            fill, edge, color = (tokens.BG_FIELD, tokens.BORDER_HAIRLINE,
                                 tokens.TEXT_SECONDARY)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)

        has_icon = paints_icon(self._icon)
        text = self.text()
        content_w = (16 if has_icon else 0) + (
            QFontMetrics(font(tokens.TYPE_CAPTION)).horizontalAdvance(text)
            if text else 0) + (5 if has_icon and text else 0)
        start = rect.center().x() - content_w / 2
        if has_icon:
            pixmap = icon_pixmap(self._icon, 14).pixmap(14, 14)
            painter.drawPixmap(int(start), int(rect.center().y() - 7), pixmap)
            start += 16 + (5 if text else 0)
        if text:
            label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_SEMIBOLD
                              if checked else tokens.WEIGHT_MEDIUM)
            painter.setFont(label_font)
            painter.setPen(QColor(color))
            painter.drawText(
                QRectF(start, rect.top(),
                       max(0.0, rect.right() - start - 2), rect.height()),
                int(Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter),
                text)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()


__all__ = ["SegmentedToggle", "ToggleButton"]
