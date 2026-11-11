"""ui/theme_kit/dropdown.py

CompactDropdown — a flat, dense select control with its own popup list.

Why not QComboBox: its popup is a platform-styled top-level window, the
scrollbar/row chrome differs between Windows and Linux, and it cannot render
a font family in its own typeface. This control paints the field, owns the
popup, clamps it on-screen, supports type-to-jump, and can show a search box
for long lists.

The popup is rebuilt per opening; no state survives except the chosen value.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import QAbstractListModel, QEvent, QModelIndex, QPoint, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QKeyEvent, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractItemView, QLineEdit, QListView, QSizePolicy, QStyle,
    QStyledItemDelegate, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    ChoiceOption, coerce_options, draw_check, draw_chevron, elide, font,
    paint_focus_ring,
)
from ui.theme_kit.popup import PopupSurface


def _primary_family(value: str) -> str:
    if not value:
        return ""
    first = value.split(",")[0].strip().strip("'\"")
    return first


_ROLE_OPTION = Qt.ItemDataRole.UserRole + 1
_ROLE_LABEL = Qt.ItemDataRole.UserRole + 2
_ROLE_MUTED = Qt.ItemDataRole.UserRole + 3
_ROLE_DISABLED = Qt.ItemDataRole.UserRole + 4
_ROLE_REASON = Qt.ItemDataRole.UserRole + 5
_ROLE_FONT = Qt.ItemDataRole.UserRole + 6
_ROLE_GROUP = Qt.ItemDataRole.UserRole + 7
_ROLE_GROUP_START = Qt.ItemDataRole.UserRole + 8
_ROLE_CURRENT = Qt.ItemDataRole.UserRole + 9
_ROLE_ICON = Qt.ItemDataRole.UserRole + 10


class _OptionModel(QAbstractListModel):
    def __init__(self, options: list[ChoiceOption], current: Any,
                 query: str = ""):
        super().__init__()
        self._options = options
        self._current = current
        self._rows: list[int] = []
        self._group_starts: dict[int, str] = {}
        self.set_query(query)

    def set_query(self, query: str) -> None:
        needle = query.strip().casefold()
        rows = [i for i, option in enumerate(self._options)
                if not needle or needle in option.text.casefold()]
        self.beginResetModel()
        self._rows = rows
        self._group_starts = {}
        previous = None
        for row, source_index in enumerate(rows):
            group = self._options[source_index].group
            if group and group != previous:
                self._group_starts[row] = group
            if group:
                previous = group
        self.endResetModel()

    def row_for_value(self, value: Any) -> int:
        for row, source_index in enumerate(self._rows):
            if self._options[source_index].value == value:
                return row
        return -1

    def option(self, row: int) -> Optional[ChoiceOption]:
        if 0 <= row < len(self._rows):
            return self._options[self._rows[row]]
        return None

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        option = self._options[self._rows[index.row()]]
        if role == _ROLE_OPTION:
            return option
        if role in (Qt.ItemDataRole.DisplayRole, _ROLE_LABEL):
            return option.text
        if role == _ROLE_MUTED:
            return option.muted
        if role == _ROLE_DISABLED:
            return bool(option.disabled_reason)
        if role == _ROLE_REASON:
            return option.disabled_reason
        if role == _ROLE_FONT:
            return option.font_family
        if role == _ROLE_GROUP:
            return option.group
        if role == _ROLE_GROUP_START:
            return self._group_starts.get(index.row(), "")
        if role == _ROLE_CURRENT:
            return option.value == self._current
        if role == _ROLE_ICON:
            return option.icon
        if role == Qt.ItemDataRole.ToolTipRole:
            return option.tooltip or option.disabled_reason
        return None


class _OptionDelegate(QStyledItemDelegate):
    ROW = 26
    GROUP = 16

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(option.rect)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        current = bool(index.data(_ROLE_CURRENT))
        muted = bool(index.data(_ROLE_MUTED))
        disabled = bool(index.data(_ROLE_DISABLED))
        group = index.data(_ROLE_GROUP_START)
        font_family = _primary_family(index.data(_ROLE_FONT) or "")

        if selected or hovered:
            painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER
                                         if hovered and not selected
                                         else tokens.BG_CARD_SELECTED))
        if selected:
            painter.fillRect(
                QRectF(rect.left() + 2, rect.top() + 3, 3,
                       rect.height() - 6),
                QColor(tokens.ACCENT))

        y = rect.top()
        if group:
            painter.setFont(font(9, tokens.WEIGHT_SEMIBOLD))
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(
                QRectF(rect.left() + 10, y + 1, rect.width() - 20,
                       self.GROUP - 2),
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                str(group).upper())
            y += self.GROUP

        row_rect = QRectF(rect.left(), y, rect.width(), rect.bottom() - y)
        label_left = rect.left() + 10
        if current:
            tick = QRectF(rect.left() + 4, row_rect.center().y() - 5, 11, 10)
            draw_check(painter, tick)
            label_left = rect.left() + 20

        reason = str(index.data(_ROLE_REASON) or "")
        reason_width = 0
        if reason:
            font_reason = font(9, tokens.WEIGHT_MEDIUM)
            metrics = QFontMetrics(font_reason)
            reason_width = min(90, metrics.horizontalAdvance(reason) + 4)
        text_rect = QRectF(label_left, y, rect.width() - label_left
                           - 8 - reason_width, rect.bottom() - y)
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM,
                          font_family)
        painter.setFont(label_font)
        if disabled:
            color = tokens.TEXT_MUTED
        elif muted:
            color = tokens.TEXT_MUTED
        else:
            color = tokens.TEXT_PRIMARY
        painter.setPen(QColor(color))
        label = QFontMetrics(label_font).elidedText(
            str(index.data(Qt.ItemDataRole.DisplayRole)),
            Qt.TextElideMode.ElideRight, int(max(0.0, text_rect.width())))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            label)
        if reason:
            painter.setFont(font(9, tokens.WEIGHT_MEDIUM))
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(
                QRectF(rect.right() - reason_width - 8, y, reason_width,
                       rect.bottom() - y),
                int(Qt.AlignmentFlag.AlignRight
                    | Qt.AlignmentFlag.AlignVCenter),
                QFontMetrics(font(9)).elidedText(
                    reason, Qt.TextElideMode.ElideRight, reason_width))
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        height = self.ROW
        if index.data(_ROLE_GROUP_START):
            height += self.GROUP
        return QSize(120, height)


class _DropdownPopup(PopupSurface):
    picked = pyqtSignal(object)

    def __init__(self, field: "CompactDropdown"):
        super().__init__(field.window())
        self._field = field
        self._type_buffer = ""
        self._type_timer = QTimer(self)
        self._type_timer.setSingleShot(True)
        self._type_timer.setInterval(450)
        self._type_timer.timeout.connect(self._clear_type_buffer)

        self.model = _OptionModel(field._options, field._value, query="")
        self.view = QListView(self)
        self.view.setModel(self.model)
        self.view.setItemDelegate(_OptionDelegate(self.view))
        self.view.setFrameShape(QListView.Shape.NoFrame)
        self.view.setMouseTracking(True)
        self.view.setUniformItemSizes(False)
        self.view.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.view.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.view.setStyleSheet(
            f"QListView {{ background: transparent; border: none;"
            f" outline: none; padding: 0px; }}")

        self.search: Optional[QLineEdit] = None
        if field._searchable or field._force_search:
            self.search = QLineEdit(self)
            self.search.setPlaceholderText("Search…")
            self.search.setClearButtonEnabled(True)
            self.search.setFixedHeight(tokens.CONTROL_HEIGHT_SM)
            self.search.setStyleSheet(
                f"QLineEdit {{ background: {tokens.BG_FIELD};"
                f" color: {tokens.TEXT_PRIMARY};"
                f" border: 1px solid {tokens.BORDER_POPOVER};"
                f" border-radius: {tokens.RADIUS_SM}px;"
                f" padding: 0 {tokens.SPACE_8}px;"
                f" font-size: {tokens.TYPE_CAPTION}px; }}"
                f"QLineEdit:focus {{ border-color: {tokens.ACCENT}; }}")
            self.search.textChanged.connect(self._on_search)
            self.search.installEventFilter(self)
            self.content.addWidget(self.search)

        self.content.addWidget(self.view, 1)
        self.view.clicked.connect(self._on_clicked)
        self.view.activated.connect(self._on_clicked)
        self.view.installEventFilter(self)
        self.setMinimumWidth(120)

        row_height = _OptionDelegate.ROW
        rows = max(1, min(9, len(field._options)))
        wanted_h = (tokens.SPACE_16 + rows * row_height
                    + (tokens.CONTROL_HEIGHT_SM + tokens.SPACE_4
                       if self.search is not None else 0))
        self.setMinimumHeight(wanted_h)
        self.setMaximumHeight(min(tokens.POPUP_MAX_HEIGHT, wanted_h + 20))

        self._select_current()
        QTimer.singleShot(0, self._focus_initial)

    def _clear_type_buffer(self) -> None:
        self._type_buffer = ""

    def _focus_initial(self) -> None:
        if self.search is not None:
            self.search.setFocus(Qt.FocusReason.PopupFocusReason)
        else:
            self.view.setFocus(Qt.FocusReason.PopupFocusReason)

    def _select_current(self) -> None:
        row = self.model.row_for_value(self._field._value)
        if row < 0 and self.model.rowCount():
            row = 0
        if row >= 0:
            index = self.model.index(row, 0)
            self.view.setCurrentIndex(index)
            self.view.scrollTo(index, QAbstractItemView.ScrollHint.PositionAtCenter)

    def _on_search(self, text: str) -> None:
        self.model.set_query(text)
        row = self.model.row_for_value(self._field._value)
        if row < 0 and self.model.rowCount():
            row = 0
        if row >= 0:
            index = self.model.index(row, 0)
            self.view.setCurrentIndex(index)
            self.view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def _on_clicked(self, index: QModelIndex) -> None:
        option = index.data(_ROLE_OPTION)
        if option is None:
            return
        if option.disabled_reason:
            return
        self.picked.emit(option.value)
        self.close()

    def _move(self, step: int) -> None:
        if not self.model.rowCount():
            return
        row = self.view.currentIndex().row()
        row = max(0, min(self.model.rowCount() - 1, row + step))
        index = self.model.index(row, 0)
        self.view.setCurrentIndex(index)
        self.view.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def _pick_current(self) -> None:
        index = self.view.currentIndex()
        if index.isValid():
            self._on_clicked(index)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if obj is self.search:
                if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                    step = 1 if key == Qt.Key.Key_Down else -1
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                    self._move(step)
                    return True
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._pick_current()
                    return True
                if key == Qt.Key.Key_Escape:
                    self.close()
                    return True
            elif obj is self.view:
                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                    self._pick_current()
                    return True
                if key == Qt.Key.Key_Escape:
                    self.close()
                    return True
                if key == Qt.Key.Key_Up:
                    self._move(-1)
                    return True
                if key == Qt.Key.Key_Down:
                    self._move(1)
                    return True
                if key == Qt.Key.Key_PageUp:
                    self._move(-6)
                    return True
                if key == Qt.Key.Key_PageDown:
                    self._move(6)
                    return True
                text = event.text()
                if text and text.isprintable() and not event.modifiers():
                    self._type_buffer += text.casefold()
                    self._type_timer.start()
                    needle = self._type_buffer
                    start = self.view.currentIndex().row()
                    count = self.model.rowCount()
                    for offset in range(1, count + 1):
                        row = (start + offset) % count
                        option = self.model.option(row)
                        if option is not None and option.text.casefold().startswith(needle):
                            index = self.model.index(row, 0)
                            self.view.setCurrentIndex(index)
                            self.view.scrollTo(
                                index,
                                QAbstractItemView.ScrollHint.EnsureVisible)
                            break
                    return True
        return super().eventFilter(obj, event)

    def show_for_field(self) -> None:
        field = self._field
        width = field._popup_width or max(field.width(), 140)
        self.show_below(field, width=width, max_height=field._popup_max_height,
                        align=field._popup_align)


class CompactDropdown(QWidget):
    """Flat select field with our own popup list.

    Signals
        changed(object) — emitted only when the chosen value actually changes.
        opened() — the popup opened (useful to close sibling popovers).
    """

    changed = pyqtSignal(object)
    opened = pyqtSignal()

    def __init__(self, options: Iterable[Any] = (), value: Any = None, *,
                 placeholder: str = "—", searchable: bool = False,
                 force_search: bool = False, preview_font: bool = False,
                 variant: str = "field", min_width: int = 0,
                 max_width: Optional[int] = None,
                 popup_width: Optional[int] = None,
                 popup_max_height: int = tokens.POPUP_MAX_HEIGHT,
                 popup_align: str = "left",
                 parent=None):
        super().__init__(parent)
        self._options = coerce_options(options)
        self._value = value
        self._placeholder = placeholder
        self._searchable = bool(searchable)
        self._force_search = bool(force_search)
        self._preview_font = bool(preview_font)
        self._variant = variant
        self._popup_width = popup_width
        self._popup_max_height = popup_max_height
        self._popup_align = popup_align
        self._hover = False
        self._open = False
        self._popup: Optional[_DropdownPopup] = None

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(min_width)
        if max_width is not None:
            self.setMaximumWidth(max_width)
        self.setFixedHeight(tokens.CONTROL_HEIGHT)
        self.setMouseTracking(True)
        self.setAccessibleName("Select")
        if not self._options:
            self._value = None
        elif value is None:
            self._value = self._first_selectable_value()

    # ── state ───────────────────────────────────────────────────────────────
    def _first_selectable_value(self) -> Any:
        for option in self._options:
            if not option.disabled_reason:
                return option.value
        return self._options[0].value if self._options else None

    def option_for(self, value: Any) -> Optional[ChoiceOption]:
        for option in self._options:
            if option.value == value:
                return option
        return None

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
        elif self.option_for(self._value) is None:
            self._value = self._first_selectable_value()
        self.update()
        if emit:
            self.changed.emit(self._value)

    def set_placeholder(self, text: str) -> None:
        self._placeholder = text
        self.update()

    def set_searchable(self, searchable: bool) -> None:
        self._searchable = bool(searchable)

    def set_preview_font(self, enabled: bool) -> None:
        self._preview_font = bool(enabled)
        self.update()

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)

    # ── geometry / painting ─────────────────────────────────────────────────
    def sizeHint(self) -> QSize:
        hint = QSize(160, tokens.CONTROL_HEIGHT)
        if self._options:
            metrics = QFontMetrics(font(tokens.TYPE_CAPTION))
            widest = max(metrics.horizontalAdvance(option.text)
                         for option in self._options)
            hint.setWidth(max(90, widest + 34))
        return hint

    def minimumSizeHint(self) -> QSize:
        return QSize(60, tokens.CONTROL_HEIGHT)

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
        focused = self.hasFocus() or self._open
        if self._variant == "bare":
            if self._hover and enabled:
                painter.fillRect(self.rect(), QColor(tokens.BG_CARD_HOVER))
            if focused:
                paint_focus_ring(painter, QRectF(self.rect()),
                                 tokens.RADIUS_SM)
        else:
            if enabled and (focused or self._hover):
                surface = tokens.BG_FIELD
            elif enabled:
                surface = tokens.BG_FIELD
            else:
                surface = tokens.BG_PANEL
            painter.setBrush(QColor(surface))
            edge = (tokens.ACCENT if focused else
                    tokens.BORDER_POPOVER if self._hover else
                    tokens.BORDER_HAIRLINE)
            painter.setPen(QPen(QColor(edge), 1))
            painter.drawRoundedRect(rect, tokens.RADIUS_SM,
                                    tokens.RADIUS_SM)

        option = self.option_for(self._value)
        text = option.text if option is not None else (
            str(self._value) if self._value is not None else self._placeholder)
        muted = option.muted if option is not None else self._value is None
        family = (_primary_family(option.font_family)
                  if option is not None and self._preview_font else "")
        label_font = font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM, family)
        metrics = QFontMetrics(label_font)
        chevron_space = 16
        text_rect = QRectF(8, 0, max(0, self.width() - chevron_space - 12),
                           self.height())
        if not enabled:
            color = tokens.TEXT_MUTED
        elif muted:
            color = tokens.TEXT_MUTED
        else:
            color = tokens.TEXT_PRIMARY
        painter.setFont(label_font)
        painter.setPen(QColor(color))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                               int(text_rect.width())))
        draw_chevron(
            painter,
            QPoint(int(self.width() - 10), self.height() // 2),
            "down" if not self._open else "up",
            tokens.TEXT_MUTED if not (self._hover or focused)
            else tokens.TEXT_SECONDARY,
            size=4.6)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()).adjusted(0, 0, 0, 0),
                             tokens.RADIUS_SM)
        painter.end()

    # ── popup ───────────────────────────────────────────────────────────────
    def open_popup(self) -> None:
        if self._popup is not None:
            self.close_popup()
        if not self.isEnabled() or not self._options:
            return
        self._popup = _DropdownPopup(self)
        self._popup.picked.connect(self._on_picked)
        self._popup.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._open = True
        self.update()
        self._popup.destroyed.connect(self._on_popup_destroyed)
        self._popup.show_for_field()
        self.opened.emit()
        if not self._popup.isVisible():
            self._open = False
            self.update()

    def close_popup(self) -> None:
        if self._popup is not None:
            self._popup.close()

    def _on_popup_destroyed(self, *_args) -> None:
        self._popup = None
        self._open = False
        self.update()

    def _on_picked(self, value: Any) -> None:
        self._open = False
        self._popup = None
        if value == self._value:
            self.update()
            return
        self._value = value
        self.update()
        self.changed.emit(value)

    # ── events ──────────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.open_popup()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Down, Qt.Key.Key_Up,
                   Qt.Key.Key_Return, Qt.Key.Key_Enter,
                   Qt.Key.Key_Space):
            self.open_popup()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusInEvent(self, event) -> None:
        self.update()
        super().focusInEvent(event)

    def focusOutEvent(self, event) -> None:
        self.update()
        super().focusOutEvent(event)

    def hideEvent(self, event) -> None:
        self.close_popup()
        super().hideEvent(event)

    def wheelEvent(self, event) -> None:
        # A wheel over a closed dropdown belongs to the scroll area.
        event.ignore()


__all__ = ["CompactDropdown"]
