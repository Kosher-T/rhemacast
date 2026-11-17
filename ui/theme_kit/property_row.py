"""ui/theme_kit/property_row.py

PropertyRow — the wrapper every Theme Designer control sits in — and
PropertySection, the collapsible group around rows.

The row owns layout and state chrome only. It never inspects a value, a
schema range or a property name: the caller supplies the label, the control,
the changed flag, warning text and disabled reason.
"""

from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QApplication, QFrame, QHBoxLayout, QLabel, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import draw_chevron, paint_focus_ring
from ui.theme_kit.popup import attach_tooltip


class _Marker(QWidget):
    """Tiny state dot beside a label (accent = changed, amber = warning)."""

    def __init__(self, color: str, size: int = tokens.CHANGED_DOT_SIZE,
                 parent=None):
        super().__init__(parent)
        self._color = color
        self._size = size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(QRectF(0, 0, self._size, self._size))


class _ResetButton(QAbstractButton):
    """A quiet reset-to-default glyph, drawn rather than typed.

    A Unicode ``↺`` would render differently per platform; a painted arc
    keeps the row identical on Windows and Linux and lets the glyph scale
    with the label's font size.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(16, 16)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName("Reset to default")
        self._visible = False
        attach_tooltip(self, "Reset to default")

    def set_shown(self, shown: bool) -> None:
        if self._visible == shown:
            # The initial call passes False while _visible already is False;
            # still apply it, or the overlay starts life visible and reserves
            # label space in rows that have no reset.
            self.setVisible(shown)
            return
        self._visible = shown
        self.setVisible(shown)
        self.update()

    def is_shown(self) -> bool:
        return self._visible

    def paintEvent(self, event) -> None:
        if not self._visible:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        # The glyph is an overlay on the label column while it is showing;
        # wash out the text underneath instead of letting it show through.
        painter.fillRect(self.rect(), QColor(tokens.BG_PANEL))
        rect = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        color = tokens.ACCENT_TEXT if self.underMouse() else tokens.TEXT_MUTED
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()),
                             tokens.RADIUS_SM)
            color = tokens.ACCENT_TEXT
        pen = QPen(QColor(color), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(rect, 35 * 16, 285 * 16)
        # Arrow head at the open end of the arc.
        head = QPoint(int(rect.right() - 1), int(rect.top() + 2))
        painter.drawLine(head, head + QPoint(-4, 0))
        painter.drawLine(head, head + QPoint(0, 4))
        painter.end()


class PropertyRow(QFrame):
    """Label + control row with changed/warning/disabled chrome.

    Signals
        reset_requested() — the reset glyph or the context action fired.

    The control can expose ``begin_scrub`` / ``scrub_to`` / ``end_scrub`` to
    let the label itself be a scrub handle (NumberField does); otherwise the
    label is inert.
    """

    reset_requested = pyqtSignal()

    def __init__(self, label: str, control: Optional[QWidget] = None, *,
                 label_width: int = tokens.LABEL_COLUMN_WIDTH,
                 full_width: bool = False, changed: bool = False,
                 warning: str = "", disabled_reason: str = "",
                 parent=None):
        super().__init__(parent)
        self.setObjectName("rcPropertyRow")
        self._label_text = str(label)
        self._label_width = label_width
        # A label longer than the configured column grows it instead of
        # eliding. The configured width stays the minimum, so ordinary rows
        # keep the shared column at any panel width.
        self._effective_label_width = int(label_width)
        self._full_width = bool(full_width)
        self._changed = bool(changed)
        self._warning = ""
        self._disabled_reason = ""
        self._base_enabled = True
        self._hovered = False
        self._focus_inside = False
        self._scrub_active = False
        self._scrub_origin = QPoint()
        self._scrubbing_control = False
        self.setMouseTracking(True)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(0, 0, 0, 0)
        self._outer.setSpacing(2)

        self._label_row = QWidget(self)
        self._label_layout = QHBoxLayout(self._label_row)
        self._label_layout.setContentsMargins(0, 0, 0, 0)
        self._label_layout.setSpacing(0)

        self._changed_dot = _Marker(tokens.ACCENT)
        self._changed_dot.setFixedSize(tokens.CHANGED_DOT_SIZE,
                                       tokens.CHANGED_DOT_SIZE)
        self._changed_dot.setProperty("role", "changed")
        self._label_layout.addWidget(self._changed_dot)
        self._label_layout.addSpacing(tokens.SPACE_4)

        self._label = QLabel(self._label_text, self)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setSizePolicy(QSizePolicy.Policy.Ignored,
                                  QSizePolicy.Policy.Preferred)
        self._label.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            f"font-weight: {tokens.WEIGHT_MEDIUM};"
            "background: transparent;")
        attach_tooltip(self._label, lambda: self._label_tooltip())
        self._label_layout.addWidget(self._label, 1)
        self._label_layout.addSpacing(tokens.SPACE_4)

        self._warning_dot = _Marker(tokens.WARNING, 6)
        self._warning_dot.hide()
        attach_tooltip(self._warning_dot, lambda: self._warning)
        self._label_layout.addWidget(self._warning_dot)

        self._reset = _ResetButton(self)
        self._reset.clicked.connect(self.reset_requested)
        self._reset.set_shown(False)

        self._control_host = QWidget(self)
        self._control_layout = QHBoxLayout(self._control_host)
        self._control_layout.setContentsMargins(0, 0, 0, 0)
        self._control_layout.setSpacing(tokens.SPACE_4)
        self._control: Optional[QWidget] = None

        self._build_layout()
        if control is not None:
            self.set_control(control)

        # Re-elide when the row or font changes.
        self._label.installEventFilter(self)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)

        self.set_changed(changed)
        self.set_warning(warning)
        if disabled_reason:
            self.set_disabled_reason(disabled_reason)

    # ── construction ────────────────────────────────────────────────────────
    def _build_layout(self) -> None:
        while self._outer.count():
            item = self._outer.takeAt(0)
            if item.widget() is not None:
                item.widget().setParent(None)
        if self._full_width:
            self._label_row.setMinimumWidth(0)
            self._outer.addWidget(self._label_row)
            self._outer.addWidget(self._control_host)
        else:
            self._effective_label_width = self.required_label_width()
            self._label_row.setFixedWidth(self._effective_label_width)
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(tokens.SPACE_4)
            row.addWidget(self._label_row, 0)
            row.addWidget(self._control_host, 1)
            self._outer.addLayout(row)
        # The reset glyph is an overlay, not a layout item: it must not steal
        # 16 px from every label column when it is hidden.
        self._reset.setParent(self)
        self._reset.raise_()
        self._position_reset()

    def required_label_width(self) -> int:
        """The configured column, or the width this label actually needs."""
        metrics = QFontMetrics(self._label.font())
        chrome = 12  # changed dot and its spacing
        if self._warning_dot.isVisible():
            chrome += 6 + tokens.SPACE_4
        # The reset glyph is an overlay at the right edge of the column. Its
        # 16 px plus a hair of clearance stay inside the column so showing it
        # does not elide the label. Two extra pixels keep elidedText from
        # replacing the last glyph at exactly the text width.
        chrome += 16 + 3
        needed = metrics.horizontalAdvance(self._label_text) + chrome
        return max(int(self._label_width), needed)

    def _update_label_column(self) -> None:
        """Grow the label column to its text; never shrink below the minimum."""
        if self._full_width:
            return
        width = self.required_label_width()
        if width == self._effective_label_width:
            return
        self._effective_label_width = width
        self._label_row.setFixedWidth(width)
        self._position_reset()

    def _sync_label_width(self) -> None:
        if self._full_width:
            available = max(0, self._label_row.width() - 20)
        else:
            # The label starts after the changed dot and its spacing (8 px);
            # the reset glyph is painted 17 px from the right edge.
            available = max(0, self._effective_label_width
                            - (27 if self._reset.isVisible() else 12))
            if self._warning_dot.isVisible():
                available -= 6 + tokens.SPACE_4
        metrics = QFontMetrics(self._label.font())
        elided = metrics.elidedText(self._label_text,
                                    Qt.TextElideMode.ElideRight,
                                    max(0, available))
        if elided != self._label.text():
            self._label.setText(elided)

    def _label_tooltip(self) -> str:
        if self._disabled_reason:
            return f"{self._label_text} — {self._disabled_reason}"
        return self._label_text

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_label_column()
        self._sync_label_width()
        self._position_reset()

    def _position_reset(self) -> None:
        """Keep the reset glyph at the right edge of the label column."""
        if self._full_width:
            x = max(0, self.width() - 17)
            y = 4
        else:
            x = max(0, self._effective_label_width - 17)
            y = max(0, (tokens.CONTROL_HEIGHT - 16) // 2)
        self._reset.move(x, y)
        self._reset.raise_()

    def eventFilter(self, obj, event) -> bool:
        if obj is self._label:
            if event.type() == QEvent.Type.Resize:
                self._sync_label_width()
            elif event.type() == QEvent.Type.MouseButtonPress:
                if self._begin_label_scrub(event):
                    return True
            elif event.type() == QEvent.Type.MouseMove:
                if self._scrub_active and self._scrubbing_control:
                    self._move_label_scrub(event)
                    return True
            elif event.type() == QEvent.Type.MouseButtonRelease:
                if self._scrub_active and self._scrubbing_control:
                    self._end_label_scrub()
                    return True
        return super().eventFilter(obj, event)

    # ── control ─────────────────────────────────────────────────────────────
    def set_control(self, control: QWidget) -> None:
        if self._control is control:
            return
        if self._control is not None:
            self._control_layout.removeWidget(self._control)
            self._control.setParent(None)
        self._control = control
        control.setParent(self._control_host)
        control.setSizePolicy(QSizePolicy.Policy.Expanding,
                              control.sizePolicy().verticalPolicy())
        self._control_layout.addWidget(control, 1)
        self._base_enabled = control.isEnabled()
        if self._disabled_reason:
            control.setEnabled(False)
        if hasattr(control, "begin_scrub"):
            self._label.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self._label.unsetCursor()

    def control(self) -> Optional[QWidget]:
        return self._control

    def set_label(self, text: str) -> None:
        self._label_text = str(text)
        self._update_label_column()
        self._sync_label_width()

    def set_label_column_width(self, width: int) -> None:
        """Adopt a shared column width; the row never drops below it."""
        if self._full_width:
            return
        self._label_width = max(int(width), self._label_width)
        self._update_label_column()
        self._sync_label_width()

    def label(self) -> str:
        return self._label_text

    # ── state chrome ────────────────────────────────────────────────────────
    def set_changed(self, changed: bool) -> None:
        self._changed = bool(changed)
        self._changed_dot.setVisible(self._changed)
        self._sync_label_width()
        self._refresh_reset()

    def is_changed(self) -> bool:
        return self._changed

    def set_warning(self, text: str) -> None:
        self._warning = str(text or "")
        self._warning_dot.setVisible(bool(self._warning))
        self._update_label_column()
        self._sync_label_width()
        self._refresh_reset()

    def warning(self) -> str:
        return self._warning

    def set_disabled_reason(self, reason: str) -> None:
        self._disabled_reason = str(reason or "")
        disabled = bool(self._disabled_reason)
        if self._control is not None:
            self._control.setEnabled(
                self._base_enabled and not disabled)
        self._label.setStyleSheet(
            f"color: {tokens.TEXT_MUTED if disabled else tokens.TEXT_SECONDARY};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            f"font-weight: {tokens.WEIGHT_MEDIUM};"
            "background: transparent;")
        self.setProperty("disabled", disabled)
        self._reset.setEnabled(not disabled)
        self._refresh_reset()

    def disabled_reason(self) -> str:
        return self._disabled_reason

    def set_reset_visible_mode(self, mode: str) -> None:
        """``hover`` (default), ``always`` or ``never``."""
        self._reset_mode = mode
        self._refresh_reset()

    _reset_mode = "hover"

    def _refresh_reset(self) -> None:
        if self._reset_mode == "never":
            shown = False
        elif self._reset_mode == "always":
            shown = True
        else:
            shown = (self._changed or self._hovered or self._focus_inside)
        changed = self._reset.isVisible() != shown
        self._reset.set_shown(shown)
        if changed:
            self._sync_label_width()
        self._position_reset()

    def enterEvent(self, event) -> None:
        self._hovered = True
        self._refresh_reset()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self._refresh_reset()
        super().leaveEvent(event)

    def _on_focus_changed(self, old, new) -> None:
        inside = new is self or (new is not None
                                 and self.isAncestorOf(new))
        if inside != self._focus_inside:
            self._focus_inside = inside
            self._refresh_reset()

    # ── label scrubbing ────────────────────────────────────────────────────
    def _begin_label_scrub(self, event) -> bool:
        control = self._control
        if control is None or not hasattr(control, "begin_scrub"):
            return False
        if not control.isEnabled():
            return False
        self._scrub_origin = event.globalPosition().toPoint()
        self._scrub_active = True
        self._scrubbing_control = True
        control.begin_scrub()
        event.accept()
        return True

    def _move_label_scrub(self, event) -> None:
        control = self._control
        delta = event.globalPosition().toPoint() - self._scrub_origin
        if hasattr(control, "scrub_to"):
            control.scrub_to(delta.x(), event.modifiers())
        event.accept()

    def _end_label_scrub(self) -> None:
        control = self._control
        self._scrub_active = False
        self._scrubbing_control = False
        if control is not None and hasattr(control, "end_scrub"):
            control.end_scrub()

    # ── size ────────────────────────────────────────────────────────────────
    def sizeHint(self) -> QSize:
        hint = super().sizeHint()
        if not self._full_width:
            hint.setHeight(max(tokens.CONTROL_HEIGHT, hint.height()))
        return hint


# ─── Sections ───────────────────────────────────────────────────────────────

class _SectionHeader(QAbstractButton):
    toggled_expanded = pyqtSignal(bool)

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = str(title)
        self._count = 0
        self._expanded = True
        self.setCheckable(True)
        self.setChecked(True)
        self.setFixedHeight(tokens.BUTTON_HEIGHT)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"{title} section")
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, checked: bool) -> None:
        self._expanded = bool(checked)
        self.toggled_expanded.emit(self._expanded)
        self.update()

    def set_expanded(self, expanded: bool) -> None:
        if self._expanded == bool(expanded):
            return
        self._expanded = bool(expanded)
        self.setChecked(self._expanded)
        self.update()

    def set_count(self, count: int) -> None:
        if self._count == count:
            return
        self._count = int(count)
        self.update()

    def enterEvent(self, event) -> None:
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = self.rect()
        if self.underMouse():
            painter.fillRect(rect, QColor(tokens.BG_CARD))
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(rect).adjusted(1, 1, -1, -1),
                             tokens.RADIUS_SM)

        draw_chevron(
            painter,
            QRectF(8, 0, 12, rect.height()).center(),
            "down" if self._expanded else "right",
            tokens.TEXT_SECONDARY if self.underMouse() else tokens.TEXT_MUTED,
            size=6.0)
        text_rect = rect.adjusted(26, 0, -34 if self._count else -8, 0)
        f = QFont(self.font())
        f.setPixelSize(11)
        f.setWeight(QFont.Weight(tokens.WEIGHT_SEMIBOLD))
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        painter.setFont(f)
        painter.setPen(QColor(tokens.TEXT_SECONDARY))
        metrics = QFontMetrics(f)
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(self._title.upper(),
                               Qt.TextElideMode.ElideRight,
                               text_rect.width()))

        if self._count:
            badge_w = 18
            badge = QRectF(rect.right() - badge_w - 8,
                           (rect.height() - 16) / 2, badge_w, 16)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.ACCENT_TINT))
            painter.drawRoundedRect(badge, 8, 8)
            f2 = QFont(self.font())
            f2.setPixelSize(10)
            f2.setWeight(QFont.Weight(tokens.WEIGHT_SEMIBOLD))
            painter.setFont(f2)
            painter.setPen(QColor(tokens.ACCENT_TEXT))
            painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter),
                             str(self._count))
        painter.end()


class PropertySection(QWidget):
    """Collapsible group of PropertyRows.

    ``state_key`` is passed back in ``expanded_changed(state_key, expanded)``
    so the caller can persist collapse state; the section itself never writes
    settings.
    """

    expanded_changed = pyqtSignal(str, bool)

    def __init__(self, title: str, *, state_key: str = "",
                 expanded: bool = True, parent=None):
        super().__init__(parent)
        self.state_key = state_key or title
        self._rows: list[PropertyRow] = []
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.header = _SectionHeader(title)
        self.header.set_expanded(expanded)
        layout.addWidget(self.header)
        layout.addSpacing(tokens.SPACE_4)

        self.body = QWidget(self)
        self._body_layout = QVBoxLayout(self.body)
        self._body_layout.setContentsMargins(0, 0, 0, tokens.SPACE_8)
        self._body_layout.setSpacing(tokens.SPACE_4)
        layout.addWidget(self.body)
        self.body.setVisible(expanded)

        self.header.toggled_expanded.connect(self._on_toggled)

    def _on_toggled(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.expanded_changed.emit(self.state_key, expanded)

    def add_row(self, row: QWidget) -> QWidget:
        self._body_layout.addWidget(row)
        if isinstance(row, PropertyRow):
            self._rows.append(row)
            self._align_rows()
        return row

    def _align_rows(self) -> None:
        """Give every row in the section the widest label column."""
        rows = []
        for row in self._rows:
            try:
                if row.parent() is not None:
                    rows.append(row)
            except RuntimeError:
                # A rebuilt form deleted the underlying widget.
                continue
        self._rows = rows
        if not rows:
            return
        width = max(row.required_label_width() for row in rows)
        for row in rows:
            row.set_label_column_width(width)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._align_rows()

    def add_widget(self, widget: QWidget) -> QWidget:
        self._body_layout.addWidget(widget)
        return widget

    def add_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)

    def set_changed_count(self, count: int) -> None:
        self.header.set_count(count)

    def set_expanded(self, expanded: bool) -> None:
        self.header.set_expanded(expanded)
        self.body.setVisible(bool(expanded))

    def is_expanded(self) -> bool:
        return self.body.isVisible()


__all__ = ["PropertyRow", "PropertySection"]
