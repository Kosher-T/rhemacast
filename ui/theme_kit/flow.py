"""ui/theme_kit/flow.py

A wrapping row layout for chips and narrow property controls.

Qt has no public flow layout. This is the standard height-for-width
implementation, kept small and deterministic: items keep their size hints,
wrap without truncating, and the parent reports the correct height so a
``QScrollArea`` does not clip the second line.
"""

from __future__ import annotations

from PyQt6.QtCore import QMargins, QPoint, QRect, QSize, Qt
from PyQt6.QtWidgets import QLayout, QLayoutItem, QSizePolicy, QWidget

from ui import tokens


class FlowLayout(QLayout):
    def __init__(self, parent=None, *, margin: int = 0,
                 h_spacing: int = tokens.SPACE_4,
                 v_spacing: int = tokens.SPACE_4):
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._h_space = h_spacing
        self._v_space = v_spacing
        self.setContentsMargins(QMargins(margin, margin, margin, margin))

    def addItem(self, item: QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem | None:
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(),
                      margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QRect, *, test_only: bool) -> int:
        margins = self.contentsMargins()
        effective = rect.adjusted(margins.left(), margins.top(),
                                  -margins.right(), -margins.bottom())
        x = effective.x()
        y = effective.y()
        line_height = 0
        for item in self._items:
            widget = item.widget()
            if widget is not None and widget.isHidden():
                continue
            hint = item.sizeHint()
            next_x = x + hint.width() + self._h_space
            if (next_x - self._h_space > effective.right() + 1
                    and line_height > 0):
                x = effective.x()
                y = y + line_height + self._v_space
                next_x = x + hint.width() + self._h_space
                line_height = 0
            if not test_only:
                item.setGeometry(
                    QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()


class FlowRow(QWidget):
    """A plain widget whose height follows its wrapped content.

    ``FlowLayout`` knows ``heightForWidth``; a bare ``QWidget`` does not
    forward it, so palette rows and chip rows get clipped without this
    wrapper.
    """

    def __init__(self, parent=None, *, margin: int = 0,
                 h_spacing: int = tokens.SPACE_4,
                 v_spacing: int = tokens.SPACE_4):
        super().__init__(parent)
        self.flow = FlowLayout(self, margin=margin, h_spacing=h_spacing,
                               v_spacing=v_spacing)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred,
                             QSizePolicy.Policy.Minimum)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._last_width = 0

    def add(self, widget: QWidget) -> None:
        self.flow.addWidget(widget)

    def remove(self, widget: QWidget) -> None:
        self.flow.removeWidget(widget)

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.flow.heightForWidth(width)

    def sizeHint(self) -> QSize:
        resized = self.testAttribute(Qt.WidgetAttribute.WA_Resized)
        width = max(1, self.width() if resized else 220)
        return QSize(width, self.flow.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:
        hint = self.flow.minimumSize()
        return QSize(min(hint.width(), 80), hint.height())


__all__ = ["FlowLayout", "FlowRow"]
