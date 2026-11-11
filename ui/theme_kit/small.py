"""ui/theme_kit/small.py

Small shared pieces: IconButton, Divider, InlineMessage and Badge.

These are deliberately plain. They exist so compound editors (gradient stops,
shadow layers, border sides, timeline markers) do not each reinvent a tiny
plus/close button with a different hit box.
"""

from __future__ import annotations

from typing import Any

from PyQt6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QHBoxLayout, QLabel, QLineEdit, QSizePolicy, QVBoxLayout,
    QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    font, icon_pixmap, paint_focus_ring, paints_icon,
)
from ui.theme_kit.popup import attach_tooltip


class IconButton(QAbstractButton):
    """Compact icon or glyph button (plus, minus, close, custom icon).

    Signals
        changed(bool) — only for checkable buttons, after a user toggle.
    """

    changed = pyqtSignal(bool)

    def __init__(self, icon: Any = None, *, glyph: str = "", text: str = "",
                 tooltip: str = "", accessible_name: str = "",
                 checkable: bool = False, checked: bool = False,
                 variant: str = "normal", compact: bool = True,
                 parent=None):
        super().__init__(parent)
        self._icon = icon
        self._glyph = glyph
        self._hover = False
        self._variant = variant
        self._compact = compact
        self.setCheckable(checkable)
        self.setChecked(bool(checked))
        self.setText(str(text))
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        name = accessible_name or tooltip or text or glyph or "Button"
        self.setAccessibleName(name)
        if tooltip:
            attach_tooltip(self, tooltip)
        self.toggled.connect(self._on_toggled)

    def _on_toggled(self, checked: bool) -> None:
        self.update()
        self.changed.emit(bool(checked))

    def set_icon(self, icon: Any) -> None:
        self._icon = icon
        self.update()

    def set_variant(self, variant: str) -> None:
        self._variant = variant
        self.update()

    def sizeHint(self) -> QSize:
        height = (tokens.CONTROL_HEIGHT_SM if self._compact
                  else tokens.CONTROL_HEIGHT)
        width = height
        if self.text():
            width += QFontMetrics(font(tokens.TYPE_CAPTION)).horizontalAdvance(
                self.text()) + 14
        return QSize(width, height)

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
        variant = self._variant
        if not enabled:
            fill, edge, color = (tokens.BG_PANEL, tokens.BORDER_HAIRLINE,
                                 tokens.TEXT_MUTED)
        elif checked:
            fill, edge, color = (tokens.ACCENT_TINT, tokens.ACCENT,
                                 tokens.TEXT_PRIMARY)
        elif variant == "accent":
            fill, edge, color = (tokens.ACCENT_TINT, tokens.ACCENT,
                                 tokens.TEXT_PRIMARY)
        elif variant == "danger":
            fill, edge, color = (tokens.BG_FIELD,
                                 tokens.DANGER if self._hover else
                                 tokens.BORDER_HAIRLINE,
                                 tokens.DANGER if self._hover else
                                 tokens.TEXT_MUTED)
        elif variant == "ghost":
            fill = None
            edge = None
            color = (tokens.TEXT_PRIMARY if self._hover
                     else tokens.TEXT_SECONDARY)
        elif self._hover:
            fill, edge, color = (tokens.BG_CARD_HOVER,
                                 tokens.BORDER_POPOVER, tokens.TEXT_PRIMARY)
        else:
            fill, edge, color = (tokens.BG_FIELD, tokens.BORDER_HAIRLINE,
                                 tokens.TEXT_SECONDARY)

        if fill is not None:
            painter.setPen(QPen(QColor(edge), 1))
            painter.setBrush(QColor(fill))
            painter.drawRoundedRect(rect, tokens.RADIUS_SM,
                                    tokens.RADIUS_SM)
        elif self._hover:
            painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER))

        icon_size = 12 if self._compact else 14
        label = self.text()
        # With a label the glyph sits at the left edge and the text follows
        # it; centring both on the whole button drew them on top of each
        # other ("Add shadow" lost its "A" under the plus).
        icon_centre = (QPointF(rect.left() + 6 + icon_size / 2,
                               rect.center().y()) if label
                       else rect.center())
        if paints_icon(self._icon):
            pixmap = icon_pixmap(self._icon, icon_size).pixmap(
                icon_size, icon_size)
            painter.drawPixmap(
                int(icon_centre.x() - icon_size / 2),
                int(icon_centre.y() - icon_size / 2), pixmap)
        elif self._glyph:
            self._paint_glyph(painter, icon_centre, color)
        if label:
            label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM)
            painter.setFont(label_font)
            painter.setPen(QColor(color))
            text_left = rect.left() + 6 + icon_size + 4
            painter.drawText(
                QRectF(text_left, rect.top(),
                       max(0.0, rect.right() - text_left - 6),
                       rect.height()),
                int(Qt.AlignmentFlag.AlignLeft
                    | Qt.AlignmentFlag.AlignVCenter), label)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()

    def _paint_glyph(self, painter: QPainter, centre, color: str) -> None:
        pen = QPen(QColor(color), 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        cx, cy = centre.x(), centre.y()
        half = 4.0
        if self._glyph in ("plus", "add"):
            painter.drawLine(int(cx - half), int(cy), int(cx + half), int(cy))
            painter.drawLine(int(cx), int(cy - half), int(cx), int(cy + half))
        elif self._glyph in ("minus", "remove"):
            painter.drawLine(int(cx - half), int(cy), int(cx + half), int(cy))
        elif self._glyph in ("close", "x"):
            painter.drawLine(int(cx - 3), int(cy - 3),
                             int(cx + 3), int(cy + 3))
            painter.drawLine(int(cx + 3), int(cy - 3),
                             int(cx - 3), int(cy + 3))
        elif self._glyph == "up":
            painter.drawPolyline(
                QRectF(cx - 4, cy + 2, 4, 4).topLeft(),
                QRectF(cx, cy - 3, 4, 4).topLeft(),
                QRectF(cx + 4, cy + 2, 4, 4).topLeft())
        elif self._glyph == "down":
            painter.drawPolyline(
                QRectF(cx - 4, cy - 2, 4, 4).topLeft(),
                QRectF(cx, cy + 3, 4, 4).topLeft(),
                QRectF(cx + 4, cy - 2, 4, 4).topLeft())
        elif self._glyph in ("link", "unlink"):
            # Two interlocking rings; unlinking opens the right ring.
            painter.setBrush(Qt.BrushStyle.NoBrush)
            gap = 3 if self._glyph == "unlink" else 1
            painter.drawEllipse(QRectF(cx - 6.5, cy - 3, 7, 6))
            painter.drawEllipse(QRectF(cx - 0.5 + gap, cy - 3, 7, 6))
        elif self._glyph in ("eye", "eye_off"):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path_points = (
                QPointF(cx - 6, cy),
                QPointF(cx - 2, cy - 3.4),
                QPointF(cx + 2, cy - 3.4),
                QPointF(cx + 6, cy),
                QPointF(cx + 2, cy + 3.4),
                QPointF(cx - 2, cy + 3.4),
                QPointF(cx - 6, cy),
            )
            painter.drawPolyline(*path_points)
            painter.drawEllipse(QPointF(cx, cy), 1.6, 1.6)
            if self._glyph == "eye_off":
                painter.drawLine(int(cx - 6), int(cy + 5),
                                 int(cx + 6), int(cy - 5))
        elif self._glyph in ("play", "pause"):
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            if self._glyph == "play":
                painter.drawPolygon(
                    QPointF(cx - 3, cy - 4.5),
                    QPointF(cx + 4.5, cy),
                    QPointF(cx - 3, cy + 4.5))
            else:
                painter.drawRect(QRectF(cx - 3.5, cy - 4, 2.4, 8))
                painter.drawRect(QRectF(cx + 1.2, cy - 4, 2.4, 8))
        elif self._glyph in ("copy", "duplicate"):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(cx - 5, cy - 2.5, 7, 8), 1.2, 1.2)
            painter.drawRoundedRect(QRectF(cx - 1.5, cy - 5.5, 7, 8), 1.2, 1.2)
        elif self._glyph in ("trash", "delete"):
            painter.drawLine(int(cx - 5), int(cy - 3),
                             int(cx + 5), int(cy - 3))
            painter.drawLine(int(cx - 2), int(cy - 5.5),
                             int(cx + 2), int(cy - 5.5))
            painter.drawPolyline(
                QPointF(cx - 4, cy - 3), QPointF(cx - 3, cy + 5),
                QPointF(cx + 3, cy + 5), QPointF(cx + 4, cy - 3))
            painter.drawLine(int(cx - 1), int(cy - 1),
                             int(cx - 1), int(cy + 3))
            painter.drawLine(int(cx + 1), int(cy - 1),
                             int(cx + 1), int(cy + 3))
        elif self._glyph in ("lock", "unlock"):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(
                QRectF(cx - 4.5, cy - 0.5, 9, 7), 1.2, 1.2)
            if self._glyph == "lock":
                painter.drawArc(QRectF(cx - 3.2, cy - 6.5, 6.4, 7),
                                0, 180 * 16)
            else:
                painter.drawArc(QRectF(cx - 1.2, cy - 7, 6.4, 7),
                                20 * 16, 160 * 16)


class Divider(QWidget):
    def __init__(self, orientation: str = "horizontal", parent=None):
        super().__init__(parent)
        self._orientation = orientation
        if orientation == "vertical":
            self.setFixedWidth(1)
            self.setSizePolicy(QSizePolicy.Policy.Fixed,
                               QSizePolicy.Policy.Expanding)
        else:
            self.setFixedHeight(1)
            self.setSizePolicy(QSizePolicy.Policy.Expanding,
                               QSizePolicy.Policy.Fixed)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(tokens.BORDER_HAIRLINE))
        painter.end()


class InlineMessage(QLabel):
    """A small wrapped note used inside compound editors."""

    def __init__(self, text: str = "", role: str = "muted", parent=None):
        super().__init__(text, parent)
        self._role = role
        self.setWordWrap(True)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,
                           QSizePolicy.Policy.Minimum)
        self.setStyleSheet(
            f"color: {self._color()};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            "background: transparent;")

    def _color(self) -> str:
        return {
            "warning": tokens.WARNING,
            "danger": tokens.DANGER,
            "info": tokens.ACCENT_TEXT,
        }.get(self._role, tokens.TEXT_MUTED)

    def set_role(self, role: str) -> None:
        self._role = role
        self.setStyleSheet(
            f"color: {self._color()};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            "background: transparent;")


class Badge(QWidget):
    """A tiny rounded count/label pill."""

    def __init__(self, text: str = "", *, accent: bool = False, parent=None):
        super().__init__(parent)
        self._text = str(text)
        self._accent = accent
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        self.setFixedHeight(16)

    def set_text(self, text: str) -> None:
        self._text = str(text)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(10, tokens.WEIGHT_SEMIBOLD))
        return QSize(metrics.horizontalAdvance(self._text) + 10, 16)

    def paintEvent(self, event) -> None:
        if not self._text:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.ACCENT_TINT if self._accent
                                else tokens.BG_CARD_HOVER))
        painter.drawRoundedRect(rect, 8, 8)
        painter.setFont(font(10, tokens.WEIGHT_SEMIBOLD))
        painter.setPen(QColor(tokens.ACCENT_TEXT if self._accent
                              else tokens.TEXT_MUTED))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._text)
        painter.end()


class SectionLabel(QLabel):
    """Small-caps group label (matches the PropertySection header type)."""

    def __init__(self, text: str = "", parent=None):
        super().__init__(str(text).upper(), parent)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            "background: transparent;")
        label_font = font(11, tokens.WEIGHT_SEMIBOLD)
        label_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.6)
        self.setFont(label_font)

    def set_label(self, text: str) -> None:
        self.setText(str(text).upper())


class EmptyState(QWidget):
    """Centred muted message for an empty list or unselected block."""

    def __init__(self, text: str = "Nothing selected",
                 hint: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(tokens.SPACE_8, tokens.SPACE_8,
                                  tokens.SPACE_8, tokens.SPACE_8)
        layout.setSpacing(2)
        self._message = QLabel(text, self)
        self._message.setWordWrap(True)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setStyleSheet(
            f"color: {tokens.TEXT_SECONDARY};"
            f"font-size: {tokens.TYPE_CAPTION}px; background: transparent;")
        layout.addWidget(self._message)
        self._hint = QLabel(hint, self)
        self._hint.setWordWrap(True)
        self._hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._hint.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: {tokens.TYPE_CAPTION}px; background: transparent;")
        self._hint.setVisible(bool(hint))
        layout.addWidget(self._hint)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)

    def set_text(self, text: str, hint: str = "") -> None:
        self._message.setText(text)
        self._hint.setText(hint)
        self._hint.setVisible(bool(hint))


class SearchField(QWidget):
    """Compact search box: magnifier, debounced text, clear button.

    Signals
        changed(str) — emitted after the debounce interval, not per key.
        submitted(str) — Enter was pressed.
    """

    changed = pyqtSignal(str)
    submitted = pyqtSignal(str)

    def __init__(self, placeholder: str = "Search", *,
                 delay_ms: int = 250, parent=None):
        super().__init__(parent)
        self._focused = False
        self._hover = False
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(7, 0, 3, 0)
        layout.setSpacing(4)
        self._icon = _SearchGlyph(self)
        layout.addWidget(self._icon, 0)
        self._edit = QLineEdit(self)
        self._edit.setFrame(False)
        self._edit.setPlaceholderText(placeholder)
        self._edit.setAccessibleName(placeholder)
        self._edit.setStyleSheet(
            "QLineEdit { background: transparent; border: none;"
            f" color: {tokens.TEXT_PRIMARY}; padding: 0;"
            f" font-size: {tokens.TYPE_CAPTION}px;"
            f" selection-background-color: {tokens.ACCENT};"
            f" selection-color: {tokens.TEXT_PRIMARY}; }}")
        self._edit.installEventFilter(self)
        layout.addWidget(self._edit, 1)
        self._clear = IconButton(
            glyph="close", tooltip="Clear search",
            accessible_name="Clear search", variant="ghost",
            compact=True, parent=self)
        self._clear.clicked.connect(self.clear)
        self._clear.setVisible(False)
        layout.addWidget(self._clear, 0)
        self.setFocusProxy(self._edit)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(max(0, int(delay_ms)))
        self._timer.timeout.connect(self._emit_changed)
        self._edit.textChanged.connect(self._on_text_changed)
        self._edit.returnPressed.connect(
            lambda: self.submitted.emit(self._edit.text()))
        self.setMouseTracking(True)

    def text(self) -> str:
        return self._edit.text()

    def set_text(self, text: str, *, emit: bool = False) -> None:
        self._edit.setText(text)
        if emit:
            self.changed.emit(self._edit.text())

    def clear(self) -> None:
        self._timer.stop()
        self._edit.clear()
        self._clear.setVisible(False)
        self.changed.emit("")

    def set_placeholder(self, text: str) -> None:
        self._edit.setPlaceholderText(text)

    def _on_text_changed(self, text: str) -> None:
        self._clear.setVisible(bool(text))
        self._timer.start()

    def _emit_changed(self) -> None:
        self.changed.emit(self._edit.text())

    def eventFilter(self, obj, event) -> bool:
        if obj is self._edit:
            if event.type() == QEvent.Type.FocusIn:
                self._focused = True
                self.update()
            elif event.type() == QEvent.Type.FocusOut:
                self._focused = False
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
        edge = (tokens.ACCENT if self._focused else
                tokens.BORDER_POPOVER if self._hover else
                tokens.BORDER_HAIRLINE)
        painter.setPen(QPen(QColor(edge), 1))
        painter.setBrush(QColor(tokens.BG_FIELD if enabled
                                else tokens.BG_PANEL))
        painter.drawRoundedRect(rect, tokens.RADIUS_SM, tokens.RADIUS_SM)
        if self._focused:
            paint_focus_ring(painter, QRectF(self.rect()), tokens.RADIUS_SM)
        painter.end()


class _SearchGlyph(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(QColor(tokens.TEXT_MUTED), 1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(1, 1, 7.5, 7.5))
        painter.drawLine(QPointF(7.6, 7.6), QPointF(11, 11))
        painter.end()


class TextInput(QLineEdit):
    """Compact text field with a live neutral/warning/error border.

    Signals
        changed(str) — committed (Enter or focus loss).
        text_changed(str) — per keystroke, for live validation.
    """

    changed = pyqtSignal(str)
    text_changed = pyqtSignal(str)

    def __init__(self, text: str = "", *, placeholder: str = "",
                 max_length: int = 32767, parent=None):
        super().__init__(text, parent)
        self._state = "neutral"
        self._message = ""
        self._committed = str(text)
        self.setPlaceholderText(placeholder)
        self.setMaxLength(max_length)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setAccessibleName(placeholder or "Text")
        self.textChanged.connect(self.text_changed)
        self.textChanged.connect(self._on_text_changed)
        self.editingFinished.connect(self._commit)
        self.returnPressed.connect(self._commit)
        self._apply_style()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str, message: str = "") -> None:
        self._state = state if state in ("neutral", "warning", "error") \
            else "neutral"
        self._message = str(message or "")
        self._apply_style()

    def set_message(self, message: str) -> None:
        self._message = str(message or "")
        self._apply_style()

    def _on_text_changed(self, _text: str) -> None:
        if self._state != "neutral":
            self._state = "neutral"
            self._message = ""
            self._apply_style()

    def _commit(self) -> None:
        text = self.text()
        if text != self._committed:
            self._committed = text
            self.changed.emit(text)

    def _apply_style(self) -> None:
        edge = {"neutral": tokens.BORDER_POPOVER if self.hasFocus()
                else tokens.BORDER_HAIRLINE,
                "warning": tokens.WARNING,
                "error": tokens.DANGER}.get(self._state,
                                            tokens.BORDER_HAIRLINE)
        self.setStyleSheet(
            f"QLineEdit {{ background: {tokens.BG_FIELD};"
            f" color: {tokens.TEXT_PRIMARY};"
            f" border: 1px solid {edge};"
            f" border-radius: {tokens.RADIUS_SM}px;"
            f" padding: 0 {tokens.SPACE_8}px;"
            f" font-size: {tokens.TYPE_CAPTION}px;"
            f" selection-background-color: {tokens.ACCENT};"
            f" selection-color: {tokens.TEXT_PRIMARY}; }}"
            f"QLineEdit:focus {{ border-color: "
            f"{tokens.ACCENT if self._state == 'neutral' else edge}; }}")
        self.setProperty("_rc_kit_tooltip", lambda: self._message)
        attach_tooltip(self, lambda: self._message)
        self.update()

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self._apply_style()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._apply_style()


class ValidationItem(QWidget):
    """One ThemeReport message: severity icon, text, click-to-navigate.

    Signals
        activated(str) — the message's property path (may be empty).
    """

    activated = pyqtSignal(str)

    def __init__(self, severity: str = "warning", message: str = "",
                 path: str = "", parent=None):
        super().__init__(parent)
        self._severity = severity
        self._message = str(message)
        self._path = str(path or "")
        self._hover = False
        self.setFixedHeight(24)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName(f"{severity}: {message}")
        attach_tooltip(self, lambda: self._path or self._message)

    def path(self) -> str:
        return self._path

    def set_message(self, severity: str, message: str,
                    path: str = "") -> None:
        self._severity = severity
        self._message = str(message)
        self._path = str(path or "")
        self.setAccessibleName(f"{severity}: {message}")
        self.update()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self._path)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_Space):
            self.activated.emit(self._path)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def _color(self) -> str:
        return {"error": tokens.DANGER, "warning": tokens.WARNING,
                "note": tokens.ACCENT_TEXT}.get(self._severity,
                                               tokens.TEXT_MUTED)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        if self._hover:
            painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER))
        if self.hasFocus():
            paint_focus_ring(painter, rect.adjusted(1, 0, -1, 0),
                             tokens.RADIUS_SM)
        colour = QColor(self._color())
        centre = QPointF(rect.left() + 10, rect.center().y())
        if self._severity == "error":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawEllipse(centre, 3.6, 3.6)
        elif self._severity == "warning":
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(colour)
            painter.drawPolygon(QPointF(centre.x(), centre.y() - 4),
                                QPointF(centre.x() + 4, centre.y() + 3.4),
                                QPointF(centre.x() - 4, centre.y() + 3.4))
        else:
            painter.setPen(QPen(colour, 1.2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(centre, 3.4, 3.4)
            painter.drawEllipse(centre, 0.8, 0.8)
        text_rect = QRectF(rect.left() + 18, rect.top(),
                           rect.width() - 24, rect.height())
        painter.setFont(font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(tokens.TEXT_SECONDARY if not self._hover
                              else tokens.TEXT_PRIMARY))
        message = painter.fontMetrics().elidedText(
            self._message, Qt.TextElideMode.ElideRight,
            int(text_rect.width()))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            message)
        painter.end()


class ValidationBadge(QWidget):
    """A small clickable count pill for a validation summary."""

    clicked = pyqtSignal()

    def __init__(self, text: str = "", *, severity: str = "warning",
                 parent=None):
        super().__init__(parent)
        self._text = str(text)
        self._severity = severity
        self._hover = False
        self.setFixedHeight(18)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Validation messages")

    def set_text(self, text: str, severity: str = "warning") -> None:
        self._text = str(text)
        self._severity = severity
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(font(10, tokens.WEIGHT_SEMIBOLD))
        return QSize(metrics.horizontalAdvance(self._text) + 14, 18)

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                           Qt.Key.Key_Space):
            self.clicked.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        colour = {"error": tokens.DANGER, "warning": tokens.WARNING,
                  "note": tokens.ACCENT_TEXT}.get(self._severity,
                                                 tokens.TEXT_MUTED)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.WARNING_TINT if self._hover
                                else tokens.BG_FIELD))
        painter.drawRoundedRect(rect, 9, 9)
        painter.setFont(font(10, tokens.WEIGHT_SEMIBOLD))
        painter.setPen(QColor(colour))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter),
                         self._text)
        if self.hasFocus():
            paint_focus_ring(painter, rect, 9)
        painter.end()


class BlockTabBar(QWidget):
    """Primary block tabs: label, visibility dot, changed-count badge.

    Tabs are ``(id, label)``, ``(id, label, visible)``,
    ``(id, label, visible, changed_count)`` or dicts with those keys.

    Signals
        selected(str) — a tab was chosen.
        visibility_toggled(str, bool) — its visibility dot was clicked.
    """

    selected = pyqtSignal(str)
    visibility_toggled = pyqtSignal(str, bool)

    def __init__(self, tabs: Any = (), current: str = "", parent=None):
        super().__init__(parent)
        self._tabs: list[dict[str, Any]] = []
        self._current = current
        self._hover = -1
        self._hover_dot = False
        self.set_tabs(tabs, current)
        self.setFixedHeight(self.ROW_HEIGHT + 1)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Blocks")

    # ── data ────────────────────────────────────────────────────────────────
    def set_tabs(self, tabs: Any, current: Any = None) -> None:
        self._tabs = []
        for item in tabs or ():
            if isinstance(item, dict):
                data = dict(item)
                data.setdefault("visible", True)
                data.setdefault("changed", 0)
            else:
                values = list(item)
                data = {
                    "id": str(values[0]),
                    "label": str(values[1]) if len(values) > 1 else str(values[0]),
                    "visible": bool(values[2]) if len(values) > 2 else True,
                    "changed": int(values[3]) if len(values) > 3 else 0,
                }
            self._tabs.append(data)
        ids = [tab["id"] for tab in self._tabs]
        if current is not None:
            self._current = str(current)
        if self._current not in ids:
            self._current = ids[0] if ids else ""
        self._sync_height()
        self.update()

    def current(self) -> str:
        return self._current

    def set_current(self, tab_id: str, *, emit: bool = False) -> None:
        if tab_id == self._current:
            return
        if not any(tab["id"] == tab_id for tab in self._tabs):
            return
        self._current = tab_id
        self.update()
        if emit:
            self.selected.emit(tab_id)

    def set_changed_count(self, tab_id: str, count: int) -> None:
        for tab in self._tabs:
            if tab["id"] == tab_id:
                tab["changed"] = int(count)
                self.update()
                return

    def set_tab_visible(self, tab_id: str, visible: bool) -> None:
        for tab in self._tabs:
            if tab["id"] == tab_id:
                tab["visible"] = bool(visible)
                self.update()
                return

    # ── geometry ────────────────────────────────────────────────────────────
    ROW_HEIGHT = 26

    def _tab_widths(self) -> list[float]:
        metrics = QFontMetrics(font(11, tokens.WEIGHT_SEMIBOLD))
        widths: list[float] = []
        for tab in self._tabs:
            badge = 18 if int(tab.get("changed", 0) or 0) else 0
            widths.append(18 + metrics.horizontalAdvance(str(tab["label"]))
                          + 8 + badge)
        return widths

    def _layout_rows(self) -> list[list[QRectF]]:
        """Lay tabs at their natural width, wrapping instead of eliding."""
        if not self._tabs:
            return []
        available = max(1.0, float(self.width()))
        rows: list[list[QRectF]] = [[]]
        x = 0.0
        for width in self._tab_widths():
            if rows[-1] and x + width > available + 0.5:
                rows.append([])
                x = 0.0
            rows[-1].append(QRectF(x, 0, width, self.ROW_HEIGHT))
            x += width
        for index, row in enumerate(rows):
            used = row[-1].right() if row else 0.0
            spare = available - used
            if spare > 0 and row:
                add = spare / len(row)
                rows[index] = [
                    QRectF(rect.left() + add * position,
                           index * self.ROW_HEIGHT,
                           rect.width() + add, self.ROW_HEIGHT)
                    for position, rect in enumerate(row)]
            else:
                rows[index] = [
                    QRectF(rect.left(), index * self.ROW_HEIGHT,
                           rect.width(), self.ROW_HEIGHT)
                    for rect in row]
        return rows

    def _tab_rects(self) -> list[QRectF]:
        return [rect for row in self._layout_rows() for rect in row]

    def _index_at(self, x: float, y: float = -1.0) -> int:
        for index, rect in enumerate(self._tab_rects()):
            if (rect.left() <= x <= rect.right()
                    and (y < 0 or rect.top() <= y <= rect.bottom())):
                return index
        return -1

    def _sync_height(self) -> None:
        rows = max(1, len(self._layout_rows()))
        height = rows * self.ROW_HEIGHT + 1
        if self.minimumHeight() != height:
            self.setFixedHeight(height)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._sync_height()

    def _dot_rect(self, rect: QRectF) -> QRectF:
        return QRectF(rect.left() + 6, rect.center().y() - 5, 10, 10)

    # ── interaction ─────────────────────────────────────────────────────────
    def mouseMoveEvent(self, event) -> None:
        index = self._index_at(event.position().x(), event.position().y())
        dot = False
        if 0 <= index < len(self._tabs):
            dot = self._dot_rect(self._tab_rects()[index]).contains(
                event.position())
        if index != self._hover or dot != self._hover_dot:
            self._hover = index
            self._hover_dot = dot
            self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = -1
        self._hover_dot = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position().x(), event.position().y())
        if index < 0:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        tab = self._tabs[index]
        if self._dot_rect(self._tab_rects()[index]).contains(
                event.position()) or self._dot_rect(
                    self._tab_rects()[index]).adjusted(-4, -4, 4, 4).contains(
                        event.position()):
            visible = not bool(tab.get("visible", True))
            tab["visible"] = visible
            self.update()
            self.visibility_toggled.emit(tab["id"], visible)
            event.accept()
            return
        self.set_current(tab["id"], emit=True)
        event.accept()

    def keyPressEvent(self, event) -> None:
        if not self._tabs:
            super().keyPressEvent(event)
            return
        ids = [tab["id"] for tab in self._tabs]
        index = ids.index(self._current) if self._current in ids else 0
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            index = (index + (1 if key == Qt.Key.Key_Right else -1)) \
                % len(ids)
            self.set_current(ids[index], emit=True)
        elif key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            self.set_current(ids[0 if key == Qt.Key.Key_Home else -1],
                             emit=True)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter,
                     Qt.Key.Key_Space):
            self.selected.emit(self._current)
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    # ── painting ────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(tokens.BG_PANEL))
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.drawLine(0, self.height() - 1, self.width(),
                         self.height() - 1)
        for index, tab in enumerate(self._tabs):
            rect = self._tab_rects()[index]
            current = tab["id"] == self._current
            hovered = index == self._hover
            if hovered and not current:
                painter.fillRect(rect, QColor(tokens.BG_CARD))
            if current:
                painter.fillRect(rect, QColor(tokens.ACCENT_TINT))
                painter.fillRect(QRectF(rect.left(), rect.bottom() - 2,
                                        rect.width(), 2),
                                 QColor(tokens.ACCENT))
            dot = self._dot_rect(rect)
            if self._hover_dot and hovered:
                painter.setBrush(QColor(tokens.BG_CARD_HOVER))
            else:
                painter.setBrush(QColor(tokens.ACCENT if tab.get(
                    "visible", True) else tokens.BORDER_POPOVER))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dot.center(), 2.5, 2.5)
            changed = int(tab.get("changed", 0) or 0)
            badge_width = 14 if (changed and rect.width() > 44) else 0
            label_rect = QRectF(rect.left() + 18, rect.top(),
                                max(0.0, rect.width() - 24 - badge_width),
                                rect.height())
            painter.setFont(font(11, tokens.WEIGHT_SEMIBOLD))
            painter.setPen(QColor(tokens.TEXT_PRIMARY if current
                                  else tokens.TEXT_SECONDARY))
            label = painter.fontMetrics().elidedText(
                str(tab["label"]), Qt.TextElideMode.ElideRight,
                int(label_rect.width()))
            painter.drawText(
                label_rect,
                int(Qt.AlignmentFlag.AlignLeft |
                    Qt.AlignmentFlag.AlignVCenter), label)
            if badge_width:
                badge = QRectF(rect.right() - 18, rect.center().y() - 7,
                               15, 14)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(tokens.ACCENT))
                painter.drawRoundedRect(badge, 7, 7)
                painter.setFont(font(9, tokens.WEIGHT_SEMIBOLD))
                painter.setPen(QColor(tokens.TEXT_PRIMARY))
                painter.drawText(badge, int(Qt.AlignmentFlag.AlignCenter),
                                 str(changed))
            if current and self.hasFocus():
                paint_focus_ring(painter, rect.adjusted(2, 2, -2, -3),
                                 tokens.RADIUS_SM)
        painter.end()


__all__ = [
    "IconButton", "Divider", "InlineMessage", "Badge", "SectionLabel",
    "EmptyState", "SearchField", "TextInput", "ValidationItem",
    "ValidationBadge", "BlockTabBar",
]
