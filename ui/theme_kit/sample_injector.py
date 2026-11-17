"""ui/theme_kit/sample_injector.py

SampleInjector — one compact toolbar button that walks a caller-supplied list
of preview samples (short / medium / long / random / custom / blank).

The widget is content-agnostic: a state is an id, a label, an optional icon and
an optional group (see :class:`ui.theme_kit.base.SampleState`). It never loads
a verse or a slide; it reports which state the operator picked and whether the
choice means "re-roll" (the shuffle state).

No native popup is used: the jump list and the custom-text editor are
``PopupSurface`` windows so placement, radius and row metrics are ours.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import (
    QPoint, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    SampleState, coerce_option, draw_check, draw_chevron, elide, font,
    icon_pixmap, paint_focus_ring, paints_icon,
)
from ui.theme_kit.popup import PopupSurface, attach_tooltip
from ui.theme_kit.small import InlineMessage


class _SampleRow(QWidget):
    picked = pyqtSignal(str)

    def __init__(self, state: SampleState, current: bool, parent=None):
        super().__init__(parent)
        self._state = state
        self._current = current
        self._hover = False
        self.setFixedHeight(24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(state.label)
        self.setMouseTracking(True)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
                event.position().toPoint()):
            self.picked.emit(self._state.id)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_Space):
            self.picked.emit(self._state.id)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        if self._hover:
            painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER))
        if self.hasFocus():
            paint_focus_ring(painter, rect.adjusted(1, 0, -1, 0),
                             tokens.RADIUS_SM)
        left = 6.0
        if paints_icon(self._state.icon):
            pixmap = icon_pixmap(self._state.icon, 12).pixmap(12, 12)
            painter.drawPixmap(int(rect.left() + 6),
                               int(rect.center().y() - 6), pixmap)
            left = 24.0
        label = self._state.label
        if self._state.kind == "custom":
            label = f"{label}…"
        painter.setFont(font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(tokens.TEXT_PRIMARY if self._hover
                              else tokens.TEXT_SECONDARY))
        text_rect = QRectF(rect.left() + left, rect.top(),
                           rect.width() - left - 24, rect.height())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elide(label, text_rect.width()))
        if self._state.kind in ("shuffle", "blank"):
            kind_rect = QRectF(rect.right() - 22, rect.center().y() - 7, 16, 14)
            painter.setFont(font(9, tokens.WEIGHT_SEMIBOLD))
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(kind_rect, int(Qt.AlignmentFlag.AlignCenter),
                             "↻" if self._state.kind == "shuffle" else "—")
        if self._current:
            tick_rect = QRectF(rect.right() - 18, rect.center().y() - 5, 10, 10)
            draw_check(painter, tick_rect)
        painter.end()


class _SampleListPopup(PopupSurface):
    picked = pyqtSignal(str)

    def __init__(self, states: list[SampleState], current: str, parent=None):
        super().__init__(parent)
        group = ""
        for state in states:
            if state.group and state.group != group:
                group = state.group
                label = InlineMessage(state.group.upper(), role="muted")
                label.setStyleSheet(
                    f"color: {tokens.TEXT_MUTED};"
                    f"font-size: 10px; font-weight: {tokens.WEIGHT_SEMIBOLD};"
                    "background: transparent; letter-spacing: 0.6px;")
                self.content.addWidget(label)
            row = _SampleRow(state, state.id == current, self)
            row.picked.connect(self._on_picked)
            self.content.addWidget(row)
        self.content.addSpacing(2)

    def _on_picked(self, state_id: str) -> None:
        self.picked.emit(state_id)
        self.close()


class _CustomPopover(PopupSurface):
    applied = pyqtSignal(str, str)
    cancelled = pyqtSignal()

    def __init__(self, text: str = "", reference: str = "", parent=None):
        super().__init__(parent)
        title = InlineMessage("Custom sample")
        self.content.addWidget(title)
        self.text_edit = QLineEdit(text, self)
        self.text_edit.setPlaceholderText("Sample text")
        self.text_edit.setAccessibleName("Custom sample text")
        self.text_edit.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.reference_edit = QLineEdit(reference, self)
        self.reference_edit.setPlaceholderText("Reference (optional)")
        self.reference_edit.setAccessibleName("Custom sample reference")
        self.reference_edit.setFixedHeight(tokens.CONTROL_HEIGHT)
        field_qss = tokens.field_qss().replace(
            "QLineEdit, QPlainTextEdit, QDoubleSpinBox",
            "QLineEdit").replace(
            "QLineEdit:focus, QPlainTextEdit:focus, QDoubleSpinBox:focus",
            "QLineEdit:focus")
        for edit in (self.text_edit, self.reference_edit):
            edit.setStyleSheet(field_qss)
            edit.setFixedHeight(tokens.CONTROL_HEIGHT)
            self.content.addWidget(edit)
        buttons = QWidget(self)
        row = QHBoxLayout(buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.SPACE_4)
        row.addStretch(1)
        cancel = QPushButton("Cancel", buttons)
        cancel.setStyleSheet(tokens.button_qss("ghost"))
        cancel.setFixedHeight(tokens.CONTROL_HEIGHT_SM)
        cancel.clicked.connect(self._cancel)
        row.addWidget(cancel)
        apply_button = QPushButton("Apply", buttons)
        apply_button.setStyleSheet(tokens.button_qss("primary"))
        apply_button.setFixedHeight(tokens.CONTROL_HEIGHT_SM)
        apply_button.clicked.connect(self._apply)
        row.addWidget(apply_button)
        self.content.addWidget(buttons)
        self.text_edit.setFocus()

    def _apply(self) -> None:
        self.applied.emit(self.text_edit.text(), self.reference_edit.text())
        self.close()

    def _cancel(self) -> None:
        self.cancelled.emit()
        self.close()

    def closeEvent(self, event) -> None:
        super().closeEvent(event)


class SampleInjector(QWidget):
    """Previous / next / jump control over caller-supplied preview samples.

    Signals
        changed(str, bool) — (state id, reroll flag). The flag is True when
            the operator landed on a ``shuffle`` state (choose another sample
            now) and on every click of that state.
        custom_requested(str, str) — (text, reference) from the custom popover.
            The caller applies the content and then calls
            :meth:`set_current` to the custom state.

    Args
        states: iterable of :class:`SampleState` (or plain strings).
        current: initial state id.
    """

    changed = pyqtSignal(str, bool)
    custom_requested = pyqtSignal(str, str)

    def __init__(self, states: Iterable[Any] = (), current: str = "",
                 *, label: str = "Sample", parent=None):
        super().__init__(parent)
        self._states: list[SampleState] = []
        self._current = current
        self._hover = ""
        self._arrows = True
        self._press_timer = QTimer(self)
        self._press_timer.setSingleShot(True)
        self._press_timer.setInterval(360)
        self._press_timer.timeout.connect(self._open_list)
        self._suppress_release = False
        self._popup: Optional[PopupSurface] = None
        self._custom: Optional[_CustomPopover] = None
        self._custom_text = ""
        self._custom_reference = ""
        self.set_states(states, current or None)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(label)
        attach_tooltip(self, lambda: self._tooltip())

    # ── public ──────────────────────────────────────────────────────────────
    def set_states(self, states: Iterable[Any], current: Optional[str] = None,
                   *, emit: bool = False) -> None:
        cleaned: list[SampleState] = []
        for item in states:
            if isinstance(item, SampleState):
                cleaned.append(item)
            else:
                option = coerce_option(item)
                cleaned.append(SampleState(
                    str(option.value), option.text, option.icon,
                    option.group))
        self._states = cleaned
        ids = {state.id for state in cleaned}
        if current is not None and current in ids:
            self._current = current
        elif self._current not in ids:
            self._current = cleaned[0].id if cleaned else ""
        self.update()
        if emit and self._current:
            self.changed.emit(self._current, False)

    def states(self) -> list[SampleState]:
        return list(self._states)

    def current(self) -> str:
        return self._current

    def set_current(self, state_id: str, *, reroll: bool = False,
                    emit: bool = False) -> None:
        if not any(state.id == state_id for state in self._states):
            return
        self._current = state_id
        self.update()
        if emit:
            self.changed.emit(state_id, bool(reroll))

    def current_state(self) -> Optional[SampleState]:
        for state in self._states:
            if state.id == self._current:
                return state
        return None

    def set_custom_value(self, text: str, reference: str = "") -> None:
        self._custom_text = str(text or "")
        self._custom_reference = str(reference or "")

    def set_arrows_visible(self, visible: bool) -> None:
        self._arrows = bool(visible)
        self.updateGeometry()
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    # ── navigation ──────────────────────────────────────────────────────────
    def next_state(self) -> None:
        self._step(1)

    def previous_state(self) -> None:
        self._step(-1)

    def _step(self, direction: int) -> None:
        if not self._states:
            return
        ids = [state.id for state in self._states]
        try:
            index = ids.index(self._current)
        except ValueError:
            index = 0
        index = (index + direction) % len(ids)
        self._choose(self._states[index])

    def _choose(self, state: SampleState) -> None:
        if state.kind == "custom":
            self._open_custom()
            return
        self._current = state.id
        self.update()
        self.changed.emit(state.id, state.kind == "shuffle")

    # ── popovers ────────────────────────────────────────────────────────────
    def _open_list(self) -> None:
        self._press_timer.stop()
        self._suppress_release = True
        if not self._states:
            return
        if self._popup is not None:
            self._popup.close()
            return
        popup = _SampleListPopup(self._states, self._current, self)
        self._popup = popup
        popup.picked.connect(self._on_list_picked)
        popup.closed.connect(self._on_popup_closed)
        popup.destroyed.connect(self._on_popup_destroyed)
        popup.show_below(self, width=max(200, self.width()),
                         max_height=320, align="left")

    def _on_list_picked(self, state_id: str) -> None:
        for state in self._states:
            if state.id == state_id:
                self._choose(state)
                return

    def _on_popup_closed(self) -> None:
        # Popups are not deleted on close; release and drop them so the next
        # click opens a fresh one.
        popup = self._popup
        self._popup = None
        if popup is not None:
            popup.deleteLater()

    def _on_popup_destroyed(self, *_args) -> None:
        self._popup = None

    def _open_custom(self) -> None:
        if self._custom is not None:
            self._custom.close()
            return
        popover = _CustomPopover(self._custom_text, self._custom_reference,
                                 self)
        self._custom = popover
        popover.applied.connect(self._on_custom_applied)
        popover.closed.connect(self._on_custom_closed)
        popover.destroyed.connect(self._on_custom_destroyed)
        popover.show_below(self, width=260, max_height=220, align="left")

    def _on_custom_applied(self, text: str, reference: str) -> None:
        self._custom_text = text
        self._custom_reference = reference
        self.changed.emit(self._current, False)
        self.custom_requested.emit(text, reference)

    def _on_custom_closed(self) -> None:
        popover = self._custom
        self._custom = None
        if popover is not None:
            popover.deleteLater()

    def _on_custom_destroyed(self, *_args) -> None:
        self._custom = None

    # ── painting / geometry ─────────────────────────────────────────────────
    def _regions(self) -> dict[str, QRectF]:
        rect = QRectF(self.rect())
        arrow = 22.0 if self._arrows else 0.0
        return {
            "left": QRectF(rect.left(), rect.top(), arrow, rect.height()),
            "right": QRectF(rect.right() - arrow - 12, rect.top(),
                            arrow, rect.height()),
            "list": QRectF(rect.right() - 14, rect.top(), 14, rect.height()),
            "center": QRectF(rect.left() + arrow, rect.top(),
                             max(0.0, rect.width() - arrow * 2 - 14),
                             rect.height()),
        }

    def _region_at(self, position: QPointF) -> str:
        for name in ("left", "right", "list", "center"):
            if self._regions()[name].contains(position):
                return name
        return ""

    def _tooltip(self) -> str:
        state = self.current_state()
        base = state.label if state else "Sample"
        if state and state.kind == "shuffle":
            return f"{base} — click for another sample"
        return f"{base} — click for the next sample, hold for the list"

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(tokens.TYPE_CAPTION,
                                    tokens.WEIGHT_MEDIUM))
        label = self.current_state().label if self.current_state() else "Sample"
        width = metrics.horizontalAdvance(label) + 24 + 22 * 2 + 14 + 28
        return QSize(max(150, width), tokens.CONTROL_HEIGHT)

    def minimumSizeHint(self) -> QSize:
        return QSize(120, tokens.CONTROL_HEIGHT)

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def mouseMoveEvent(self, event) -> None:
        region = self._region_at(event.position())
        if region != self._hover:
            self._hover = region
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = ""
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self._suppress_release = False
        self._press_timer.start()
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._press_timer.stop()
        if self._suppress_release:
            self._suppress_release = False
            event.accept()
            return
        region = self._region_at(event.position())
        if region == "left":
            self.previous_state()
        elif region in ("right", "center"):
            state = self.current_state()
            if state is not None and state.kind == "shuffle" and \
                    self._current == state.id:
                self.changed.emit(state.id, True)
            else:
                self.next_state()
        elif region == "list":
            self._open_list()
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            self.previous_state()
            event.accept()
            return
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            self.next_state()
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            state = self.current_state()
            if state is not None and state.kind == "shuffle":
                self.changed.emit(state.id, True)
            else:
                self.next_state()
            event.accept()
            return
        if key == Qt.Key.Key_Home and self._states:
            self._choose(self._states[0])
            event.accept()
            return
        if key == Qt.Key.Key_End and self._states:
            self._choose(self._states[-1])
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        enabled = self.isEnabled()
        if not enabled:
            # Muted colours alone still look clickable on the black theme.
            painter.setOpacity(0.55)
        focused = self.hasFocus() or (
            self._popup is not None and self._popup.isVisible()) or (
            self._custom is not None and self._custom.isVisible())
        surface = tokens.BG_FIELD if enabled else tokens.BG_PANEL
        edge = (tokens.ACCENT if focused else
                tokens.BORDER_POPOVER if self._hover else
                tokens.BORDER_HAIRLINE)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(surface))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)

        regions = self._regions()
        if self._hover in ("left", "right", "list") and enabled:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.BG_CARD_HOVER))
            painter.drawRoundedRect(regions[self._hover], tokens.RADIUS_SM,
                                    tokens.RADIUS_SM)

        ink = tokens.TEXT_SECONDARY if enabled else tokens.TEXT_MUTED
        if self._arrows:
            draw_chevron(
                painter, regions["left"].center(), "left",
                tokens.TEXT_PRIMARY if self._hover == "left" else ink,
                size=4.6)
            draw_chevron(
                painter, regions["right"].center(), "right",
                tokens.TEXT_PRIMARY if self._hover == "right" else ink,
                size=4.6)
        draw_chevron(painter, regions["list"].center(), "down", ink, size=3.4)

        centre = regions["center"]
        state = self.current_state()
        left = centre.left() + 2
        if state is not None and paints_icon(state.icon):
            pixmap = icon_pixmap(state.icon, 12).pixmap(12, 12)
            painter.drawPixmap(int(left), int(centre.center().y() - 6), pixmap)
            left += 17
        label = state.label if state is not None else "No samples"
        painter.setFont(font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(tokens.TEXT_PRIMARY if enabled
                              else tokens.TEXT_MUTED))
        dots_width = 0.0
        count = len(self._states)
        if 2 <= count <= 8:
            dots_width = count * 6 + 4
        text_width = max(0.0, centre.right() - left - dots_width - 2)
        text_rect = QRectF(left, centre.top(), text_width, centre.height())
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elide(label, text_width))
        if dots_width:
            index = next((i for i, s in enumerate(self._states)
                          if s.id == self._current), 0)
            dot_y = centre.center().y()
            start = centre.right() - dots_width
            for position in range(count):
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(
                    tokens.ACCENT if position == index
                    else tokens.BORDER_POPOVER if enabled
                    else tokens.BORDER_HAIRLINE))
                painter.drawEllipse(
                    QPointF(start + 3 + position * 6, dot_y), 2.0, 2.0)
        if focused:
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()


__all__ = ["SampleInjector"]
