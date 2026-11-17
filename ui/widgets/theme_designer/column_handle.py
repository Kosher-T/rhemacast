"""Drag handle between Theme Designer columns.

The handle is a painted QWidget, not a native QSplitter handle. The Theme
Designer needs three things a stock splitter does not give it:

* the same black and purple paint on Pop!OS and Windows, with no native
  control style involved,
* a visible hover state and a visible drag state,
* double-click to reset one column to its default width.

The tab owns the width maths; this widget owns hit testing and paint, and
emits an incremental horizontal delta while the pointer is down.
"""

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from core.constants import DESIGNER_HANDLE_WIDTH
from ui.styles import ACCENT, ACCENT_BORDER, ACCENT_SOFT, BORDER_SUBTLE


class ColumnHandle(QWidget):
    """Vertical drag handle for one side column.

    Signals
        drag_started()      the left button went down
        dragged(int)        incremental horizontal delta since the last emit
        drag_finished()     the left button came up after a drag
        reset_requested()   the handle was double-clicked
    """

    drag_started = pyqtSignal()
    dragged = pyqtSignal(int)
    drag_finished = pyqtSignal()
    reset_requested = pyqtSignal()

    def __init__(self, side: str = "left", parent=None):
        super().__init__(parent)
        self._side = "right" if str(side).lower() == "right" else "left"
        self._hovered = False
        self._dragging = False
        self._last_x = 0

        self.setObjectName("rcColumnHandle")
        self.setFixedWidth(DESIGNER_HANDLE_WIDTH)
        self.setCursor(Qt.CursorShape.SplitHCursor)
        self.setMouseTracking(True)
        # Mouse-only control: it must not add a stop to the Tab order of
        # every field beside it.
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAccessibleName(f"Resize the {self._side} column")
        self.setToolTip("Drag to resize. Double-click to reset.")

    # ── state ───────────────────────────────────────────────────────────────

    def side(self) -> str:
        return self._side

    def is_dragging(self) -> bool:
        return self._dragging

    def is_hovered(self) -> bool:
        return self._hovered

    # ── input ───────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_x = int(event.globalPosition().x())
            self.drag_started.emit()
            self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            x = int(event.globalPosition().x())
            delta = x - self._last_x
            if delta:
                self._last_x = x
                self.dragged.emit(delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.drag_finished.emit()
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.reset_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    # ── paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        centre_x = rect.center().x()
        middle_y = rect.center().y()

        if self._dragging:
            # Full-height wash plus the strongest line and grip: the column
            # being moved is unambiguous while the button is held.
            painter.fillRect(rect, QColor(ACCENT_SOFT))
            line = QColor(ACCENT)
            line_width = 2.0
            grip = QColor(ACCENT)
            grip_width, grip_height = 4.0, 44.0
        elif self._hovered:
            line = QColor(ACCENT_BORDER)
            line_width = 2.0
            grip = QColor(ACCENT_BORDER)
            grip_width, grip_height = 4.0, 36.0
        else:
            line = QColor(BORDER_SUBTLE)
            line_width = 1.0
            grip = QColor(ACCENT_SOFT)
            grip_width, grip_height = 3.0, 28.0

        pen = QPen(line)
        pen.setWidthF(line_width)
        painter.setPen(pen)
        painter.drawLine(QPointF(centre_x, 0.0),
                         QPointF(centre_x, rect.height()))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(grip)
        painter.drawRoundedRect(
            QRectF(centre_x - grip_width / 2.0,
                   middle_y - grip_height / 2.0,
                   grip_width, grip_height),
            grip_width / 2.0, grip_width / 2.0)
