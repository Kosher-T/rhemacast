"""ui/theme_kit/timeline.py

Timeline — a keyframe track for custom animation definitions.

Frames are plain dictionaries so the caller keeps the theme file shape. The
editor touches only the keys it knows, preserves unknown keys, and remembers
which keys the author had written explicitly so a round-trip does not add
noise.

Defaults follow the theme reference: 2–8 frames, first at 0, last at 100,
strictly increasing.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QGridLayout, QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    font, format_number, paint_focus_ring,
)
from ui.theme_kit.number_field import NumberField
from ui.theme_kit.popup import attach_tooltip
from ui.theme_kit.small import IconButton, InlineMessage

#: (key, label, minimum, maximum, step, unit, keywords)
_KEYFRAME_FIELDS = (
    ("opacity", "Opacity", 0.0, 1.0, 0.05, "", ("base",)),
    ("translate_x", "Move X", -2000, 2000, 1, "px", ("px", "%")),
    ("translate_y", "Move Y", -2000, 2000, 1, "px", ("px", "%")),
    ("scale", "Scale", 0.01, 4.0, 0.01, "", ()),
    ("rotate", "Rotate", -1080, 1080, 1, "", ()),
    ("blur", "Blur", 0.0, 60.0, 0.5, "", ("base",)),
)
_FIELD_KEYS = {entry[0] for entry in _KEYFRAME_FIELDS}


def _frame_at(frame: dict[str, Any]) -> float:
    try:
        return float(frame.get("at", 0))
    except (TypeError, ValueError):
        return 0.0


def _normalise_frames(frames: Iterable[dict[str, Any]],
                      minimum: int, maximum: int) -> list[dict[str, Any]]:
    clean: list[dict[str, Any]] = []
    for frame in frames:
        if isinstance(frame, dict):
            clean.append(dict(frame))
    clean.sort(key=_frame_at)
    if not clean:
        clean = [{"at": 0}, {"at": 100}]
    clean = clean[:maximum]
    while len(clean) < minimum:
        clean.append({"at": 100.0})
    clean[0]["at"] = 0
    clean[-1]["at"] = 100
    # Keep the middle strictly increasing.
    for index in range(1, len(clean) - 1):
        low = _frame_at(clean[index - 1]) + 0.5
        high = _frame_at(clean[index + 1]) - 0.5
        clean[index]["at"] = max(low, min(high, _frame_at(clean[index])))
    return clean


class _KeyframeTrack(QWidget):
    """Painted ruler plus draggable frame markers."""

    moved = pyqtSignal(int, float)
    selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._frames: list[dict[str, Any]] = []
        self._selected = 0
        self._drag_index = -1
        self._hover = -1
        self._last_at = 0.0
        self.setFixedHeight(42)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAccessibleName("Keyframe timeline")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)

    def set_frames(self, frames: list[dict[str, Any]],
                   selected: int = 0) -> None:
        self._frames = frames
        self._selected = max(0, min(selected, len(frames) - 1))
        self.update()

    def index_at(self, x: float) -> int:
        if not self._frames:
            return -1
        rect = self._track_rect()
        best = -1
        best_distance = 12.0
        for index, frame in enumerate(self._frames):
            position = rect.left() + _frame_at(frame) / 100.0 * rect.width()
            distance = abs(position - x)
            if distance < best_distance:
                best_distance = distance
                best = index
        return best

    def _track_rect(self) -> QRectF:
        return QRectF(self.rect()).adjusted(10, 20, -10, -10)

    def _position(self, index: int) -> float:
        rect = self._track_rect()
        return rect.left() + _frame_at(self._frames[index]) / 100.0 * rect.width()

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        index = self.index_at(event.position().x())
        if index >= 0:
            self._selected = index
            self._drag_index = index
            self._last_at = _frame_at(self._frames[index])
            self.selected.emit(index)
            self.update()
            event.accept()
            return
        self._drag_index = -1
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if self._drag_index < 0:
            index = self.index_at(event.position().x())
            if index != self._hover:
                self._hover = index
                self.update()
            return
        index = self._drag_index
        if index <= 0 or index >= len(self._frames) - 1:
            return
        rect = self._track_rect()
        ratio = (event.position().x() - rect.left()) / max(1.0, rect.width())
        low = _frame_at(self._frames[index - 1]) + 0.5
        high = _frame_at(self._frames[index + 1]) - 0.5
        at = round(max(low, min(high, ratio * 100.0)) * 10.0) / 10.0
        if at != self._last_at:
            self._frames[index]["at"] = at
            self._last_at = at
            self.update()
            self.moved.emit(index, at)
        event.accept()

    def mouseReleaseEvent(self, event) -> None:
        self._drag_index = -1
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            step = 10.0 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1.0
            index = self._selected
            if 0 < index < len(self._frames) - 1:
                low = _frame_at(self._frames[index - 1]) + 0.5
                high = _frame_at(self._frames[index + 1]) - 0.5
                at = max(low, min(high,
                                  _frame_at(self._frames[index])
                                  + (step if key == Qt.Key.Key_Right
                                     else -step)))
                self._frames[index]["at"] = round(at * 10.0) / 10.0
                self.update()
                self.moved.emit(index, self._frames[index]["at"])
            event.accept()
            return
        if key in (Qt.Key.Key_Home, Qt.Key.Key_End):
            self._selected = 0 if key == Qt.Key.Key_Home else len(
                self._frames) - 1
            self.selected.emit(self._selected)
            self.update()
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
        rect = self._track_rect()
        painter.setPen(QPen(QColor(tokens.BORDER_HAIRLINE), 1))
        painter.drawLine(QPointF(rect.left(), rect.center().y()),
                         QPointF(rect.right(), rect.center().y()))
        painter.setFont(font(9, tokens.WEIGHT_MEDIUM))
        for tick in (0, 25, 50, 75, 100):
            x = rect.left() + tick / 100.0 * rect.width()
            painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
            painter.drawLine(QPointF(x, rect.center().y() - 4),
                             QPointF(x, rect.center().y() + 4))
            painter.setPen(QColor(tokens.TEXT_MUTED))
            painter.drawText(
                QRectF(x - 12, rect.bottom() + 1, 24, 12),
                int(Qt.AlignmentFlag.AlignCenter), str(tick))
        for index, frame in enumerate(self._frames):
            x = self._position(index)
            y = rect.center().y()
            selected = index == self._selected
            hover = index == self._hover and self._drag_index < 0
            color = (tokens.ACCENT if selected
                     else tokens.ACCENT_TEXT if hover
                     else tokens.TEXT_SECONDARY)
            painter.setPen(QPen(QColor(color), 1))
            painter.setBrush(QColor(tokens.BG_POPOVER))
            painter.drawEllipse(QPointF(x, y), 5.5 if selected else 4.5,
                                5.5 if selected else 4.5)
            painter.setBrush(QColor(color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(x, y), 2.2, 2.2)
            if selected:
                painter.setPen(QPen(QColor(tokens.ACCENT), 1))
                painter.drawLine(QPointF(x, y - 8), QPointF(x, rect.top()))
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()).adjusted(1, 1, -1, -1),
                             tokens.RADIUS_SM)
        painter.end()


class KeyframeEditor(QWidget):
    """The property grid for one selected keyframe."""

    edited = pyqtSignal(str, object)
    previewed = pyqtSignal(str, object)

    def __init__(self, frame: Optional[dict[str, Any]] = None, parent=None):
        super().__init__(parent)
        self._frame: dict[str, Any] = dict(frame or {})
        self._explicit: set[str] = set(self._frame)
        self._updating = False
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(tokens.SPACE_8)
        grid.setVerticalSpacing(tokens.SPACE_4)
        self._fields: dict[str, NumberField] = {}
        for index, (key, label, minimum, maximum, step, unit,
                    keywords) in enumerate(_KEYFRAME_FIELDS):
            row, column = divmod(index, 2)
            field = NumberField(
                self._value_for(key, default=minimum),
                minimum=minimum, maximum=maximum, step=step,
                unit=unit, keywords=keywords,
                nullable=key in ("opacity", "blur"),
                # The clear glyph leaves ~38 px of text at 240 px; "Not set"
                # elides there, so the track uses the short form.
                placeholder="Unset" if key in ("opacity", "blur") else "Not set",
                suffix="°" if key == "rotate" else "",
                label=label)
            field.setMinimumWidth(64)
            field.changed.connect(
                lambda value, k=key: self._on_changed(k, value))
            field.preview.connect(
                lambda value, k=key: self._on_previewed(k, value))
            grid.addWidget(field, row, column)
            self._fields[key] = field
        self.set_frame(self._frame)

    @staticmethod
    def _value_for(key: str, default: Any = 0) -> Any:
        return default

    def set_frame(self, frame: dict[str, Any]) -> None:
        self._frame = dict(frame or {})
        self._explicit = set(self._frame)
        self._updating = True
        try:
            for key, _label, minimum, _maximum, _step, unit, keywords in (
                    _KEYFRAME_FIELDS):
                if key in self._frame:
                    value = self._frame[key]
                elif key in ("opacity", "blur"):
                    value = None
                elif key in ("translate_x", "translate_y"):
                    value = 0
                elif key == "scale":
                    value = 1
                else:
                    value = 0
                self._fields[key].set_value(value)
        finally:
            self._updating = False

    def _on_changed(self, key: str, value: Any) -> None:
        if self._updating:
            return
        self._explicit.add(key)
        self._frame[key] = value
        self.edited.emit(key, value)

    def _on_previewed(self, key: str, value: Any) -> None:
        if self._updating:
            return
        self._frame[key] = value
        self.previewed.emit(key, value)

    def frame(self) -> dict[str, Any]:
        result = dict(self._frame)
        for key in _FIELD_KEYS:
            if key in self._explicit:
                result[key] = self._fields[key].value()
        return result


class Timeline(QWidget):
    """Keyframe timeline + editor for one animation definition.

    Signals
        changed(list) — committed frame list.
        preview(list) — live frame list while a marker or value is dragged.
        selected(int) — the selected frame index changed.
    """

    changed = pyqtSignal(object)
    preview = pyqtSignal(object)
    selected = pyqtSignal(int)

    def __init__(self, frames: Optional[Iterable[dict[str, Any]]] = None,
                 *, minimum: int = 2, maximum: int = 8,
                 show_editor: bool = True, parent=None):
        super().__init__(parent)
        self._minimum = max(2, int(minimum))
        self._maximum = max(self._minimum, int(maximum))
        self._frames = _normalise_frames(frames or [], self._minimum,
                                         self._maximum)
        self._selected = 0
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(tokens.SPACE_4)
        self.title = InlineMessage("")
        head.addWidget(self.title, 1)
        self.add_button = IconButton(
            glyph="plus", tooltip="Add keyframe",
            accessible_name="Add keyframe", parent=self)
        self.add_button.clicked.connect(self.add_frame)
        head.addWidget(self.add_button, 0)
        self.remove_button = IconButton(
            glyph="minus", tooltip="Remove keyframe",
            accessible_name="Remove keyframe", parent=self)
        self.remove_button.clicked.connect(self.remove_frame)
        head.addWidget(self.remove_button, 0)
        layout.addLayout(head)

        self.track = _KeyframeTrack(self)
        self.track.moved.connect(self._on_moved)
        self.track.selected.connect(self._on_selected)
        layout.addWidget(self.track)

        self.editor = KeyframeEditor(parent=self)
        self.editor.edited.connect(self._on_edited)
        self.editor.previewed.connect(self._on_previewed)
        self.editor.setVisible(bool(show_editor))
        layout.addWidget(self.editor)

        self.hint = InlineMessage(
            "First and last frames are pinned at 0 and 100.", role="muted")
        layout.addWidget(self.hint)
        self._sync()

    # ── public ──────────────────────────────────────────────────────────────
    def frames(self) -> list[dict[str, Any]]:
        current = self.editor.frame()
        current["at"] = self._frames[self._selected].get("at", 0)
        self._frames[self._selected] = current
        return [dict(frame) for frame in self._frames]

    def set_frames(self, frames: Iterable[dict[str, Any]]) -> None:
        self._frames = _normalise_frames(frames, self._minimum, self._maximum)
        self._selected = min(self._selected, len(self._frames) - 1)
        self._sync()

    def add_frame(self) -> None:
        if len(self._frames) >= self._maximum:
            return
        self._collect_editor()
        best_index = max(1, len(self._frames) - 1)
        best_gap = -1.0
        for index in range(len(self._frames) - 1):
            gap = _frame_at(self._frames[index + 1]) - _frame_at(
                self._frames[index])
            if gap > best_gap:
                best_gap = gap
                best_index = index + 1
        left = _frame_at(self._frames[best_index - 1])
        right = _frame_at(self._frames[best_index])
        at = round((left + right) / 2.0 * 10.0) / 10.0
        self._frames.insert(best_index, {"at": at})
        self._selected = best_index
        self._sync()
        self.changed.emit(self.frames())

    def remove_frame(self) -> None:
        if len(self._frames) <= self._minimum:
            return
        if self._selected <= 0 or self._selected >= len(self._frames) - 1:
            return
        del self._frames[self._selected]
        self._selected = max(0, min(self._selected, len(self._frames) - 1))
        self._sync()
        self.changed.emit(self.frames())

    def set_accessible_label(self, text: str) -> None:
        self.setAccessibleName(text)
        self.track.setAccessibleName(f"{text} timeline")

    # ── internals ───────────────────────────────────────────────────────────
    def _collect_editor(self) -> None:
        frame = self.editor.frame()
        frame["at"] = self._frames[self._selected].get("at", 0)
        self._frames[self._selected] = frame

    def _sync(self) -> None:
        self._updating = True
        try:
            self.track.set_frames(self._frames, self._selected)
            self.editor.set_frame(self._frames[self._selected])
            count = len(self._frames)
            self.title.setText(f"Keyframes · {count}/{self._maximum}")
            self.add_button.setEnabled(count < self._maximum)
            self.remove_button.setEnabled(
                self._minimum < count and 0 < self._selected < count - 1)
        finally:
            self._updating = False

    def _on_selected(self, index: int) -> None:
        if self._updating:
            return
        self._collect_editor()
        self._selected = max(0, min(index, len(self._frames) - 1))
        self._sync()
        self.selected.emit(self._selected)

    def _on_moved(self, index: int, at: float) -> None:
        if index == self._selected:
            self._collect_editor()
        self._frames[index]["at"] = at
        self._sync()
        self.preview.emit(self.frames())

    def _on_edited(self, _key: str, _value: Any) -> None:
        if self._updating:
            return
        self._collect_editor()
        self.changed.emit(self.frames())

    def _on_previewed(self, _key: str, _value: Any) -> None:
        if self._updating:
            return
        self._collect_editor()
        self.preview.emit(self.frames())


__all__ = ["Timeline", "KeyframeEditor", "TIMELINE_FIELDS"]

TIMELINE_FIELDS = _KEYFRAME_FIELDS
