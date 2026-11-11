"""ui/theme_kit/container_canvas.py

ContainerCanvas — a scaled design-canvas editor for 1–16 containers — and
ContainerStrip, the compact layer list beside it.

The canvas is a *controlled* widget: it never stores the authoritative
geometry. It paints the boxes the caller hands it, emits ``preview`` while a
drag is in progress and ``changed`` with the final numbers, and drops its
transient drag overlay as soon as the caller calls :meth:`set_boxes` again.
Anchor-``fill`` containers are drawn full-canvas and are not draggable.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PyQt6.QtWidgets import (
    QAbstractButton, QFrame, QHBoxLayout, QLabel, QScrollArea, QSizePolicy,
    QVBoxLayout, QWidget,
)

from ui import tokens
from ui.theme_kit.base import (
    draw_chevron, elide, font, paint_focus_ring, qcolor,
)
from ui.theme_kit.color_field import resolve_paint_color
from ui.theme_kit.popup import attach_tooltip
from ui.theme_kit.small import (
    Badge, EmptyState, IconButton, SectionLabel,
)
from ui.theme_kit.segmented import ToggleButton

_HANDLES = ("nw", "n", "ne", "e", "se", "s", "sw", "w")
_HANDLE_CURSORS = {
    "nw": Qt.CursorShape.SizeFDiagCursor,
    "se": Qt.CursorShape.SizeFDiagCursor,
    "ne": Qt.CursorShape.SizeBDiagCursor,
    "sw": Qt.CursorShape.SizeBDiagCursor,
    "n": Qt.CursorShape.SizeVerCursor,
    "s": Qt.CursorShape.SizeVerCursor,
    "e": Qt.CursorShape.SizeHorCursor,
    "w": Qt.CursorShape.SizeHorCursor,
}


@dataclass
class ContainerBox:
    """One container as the canvas needs it (design pixels)."""

    id: str
    label: str = ""
    x: float = 0
    y: float = 0
    width: float = 320
    height: float = 180
    layer: int = 0
    visible: bool = True
    fill: bool = False

    @classmethod
    def from_any(cls, item: Any) -> "ContainerBox":
        if isinstance(item, ContainerBox):
            return item
        if isinstance(item, dict):
            return cls(
                id=str(item.get("id", "")),
                label=str(item.get("label", "")),
                x=float(item.get("x", 0) or 0),
                y=float(item.get("y", 0) or 0),
                width=float(item.get("width", 320) or 0),
                height=float(item.get("height", 180) or 0),
                layer=int(item.get("layer", 0) or 0),
                visible=bool(item.get("visible", True)),
                fill=bool(item.get("fill", False)),
            )
        raise TypeError(f"unsupported container box: {item!r}")

    def geometry(self) -> dict[str, Any]:
        return {
            "x": int(round(self.x)),
            "y": int(round(self.y)),
            "width": int(round(self.width)),
            "height": int(round(self.height)),
        }

    def title(self) -> str:
        return self.label or self.id


class _Surface(QWidget):
    selected = pyqtSignal(str)
    changed = pyqtSignal(str, object)
    preview = pyqtSignal(str, object)
    zoom_changed = pyqtSignal(float)

    def __init__(self, canvas_size: tuple[float, float],
                 safe_area: float, show_readout: bool,
                 background: str, palette=(), parent=None):
        super().__init__(parent)
        self._canvas_w = float(canvas_size[0])
        self._canvas_h = float(canvas_size[1])
        self._zoom = 0.3
        self._fit_mode = True
        self._boxes: list[ContainerBox] = []
        self._selected = ""
        self._override: Optional[ContainerBox] = None
        self._drag: Optional[dict[str, Any]] = None
        self._guides: dict[str, list[float]] = {"v": [], "h": []}
        self._hover = ""
        self._safe = float(safe_area)
        self._show_safe = False
        self._readout = bool(show_readout)
        self._background = str(background or "transparent")
        self._palette = dict(palette or ())
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(220, 150)
        self.setAccessibleName("Container canvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        attach_tooltip(self, "Drag to move · handles resize · arrows nudge")

    # ── public ──────────────────────────────────────────────────────────────
    def set_canvas_size(self, width: float, height: float) -> None:
        self._canvas_w = max(1.0, float(width))
        self._canvas_h = max(1.0, float(height))
        if self._fit_mode:
            self._fit()
        self.update()

    def set_boxes(self, boxes: Iterable[Any], selected: Optional[str] = None,
                  *, keep_override: bool = False) -> None:
        self._boxes = [ContainerBox.from_any(box) for box in boxes]
        if not keep_override:
            self._override = None
        if selected is not None:
            self._selected = str(selected)
        if self._selected and not any(box.id == self._selected
                                      for box in self._boxes):
            self._selected = ""
        self.update()

    def set_selected(self, box_id: str, *, emit: bool = False) -> None:
        if box_id == self._selected:
            return
        self._selected = str(box_id or "")
        self.update()
        if emit:
            self.selected.emit(self._selected)

    def selected_id(self) -> str:
        return self._selected

    def set_background(self, value: str) -> None:
        self._background = str(value or "transparent")
        self.update()

    def set_safe_area_visible(self, visible: bool) -> None:
        self._show_safe = bool(visible)
        self.update()

    def safe_area_visible(self) -> bool:
        return self._show_safe

    def zoom(self) -> float:
        return self._zoom

    def set_zoom(self, value: float, *, emit: bool = True) -> None:
        self._fit_mode = False
        self._zoom = max(0.05, min(4.0, float(value)))
        if emit:
            self.zoom_changed.emit(self._zoom)
        self.update()

    def zoom_in(self) -> None:
        self.set_zoom(self._zoom * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self._zoom / 1.25)

    def fit(self) -> None:
        self._fit_mode = True
        self._fit()
        self.zoom_changed.emit(self._zoom)
        self.update()

    def _fit(self) -> None:
        margin = 16.0
        width = max(1.0, self.width() - margin)
        height = max(1.0, self.height() - margin)
        self._zoom = max(0.05, min(4.0, min(width / self._canvas_w,
                                            height / self._canvas_h)))

    # ── mapping ─────────────────────────────────────────────────────────────
    def _canvas_rect(self) -> QRectF:
        width = self._canvas_w * self._zoom
        height = self._canvas_h * self._zoom
        return QRectF((self.width() - width) / 2,
                      (self.height() - height) / 2, width, height)

    def _box_rect(self, box: ContainerBox) -> QRectF:
        canvas = self._canvas_rect()
        if box.fill:
            return QRectF(canvas)
        return QRectF(canvas.left() + box.x * self._zoom,
                      canvas.top() + box.y * self._zoom,
                      max(2.0, box.width * self._zoom),
                      max(2.0, box.height * self._zoom))

    def _design_point(self, position: QPointF) -> QPointF:
        canvas = self._canvas_rect()
        return QPointF((position.x() - canvas.left()) / self._zoom,
                       (position.y() - canvas.top()) / self._zoom)

    def _handle_rects(self, box: ContainerBox) -> dict[str, QRectF]:
        rect = self._box_rect(box)
        size = 7.0
        half = size / 2
        points = {
            "nw": QPointF(rect.left(), rect.top()),
            "n": QPointF(rect.center().x(), rect.top()),
            "ne": QPointF(rect.right(), rect.top()),
            "e": QPointF(rect.right(), rect.center().y()),
            "se": QPointF(rect.right(), rect.bottom()),
            "s": QPointF(rect.center().x(), rect.bottom()),
            "sw": QPointF(rect.left(), rect.bottom()),
            "w": QPointF(rect.left(), rect.center().y()),
        }
        return {name: QRectF(point.x() - half, point.y() - half, size, size)
                for name, point in points.items()}

    def _selected_box(self) -> Optional[ContainerBox]:
        if self._override is not None and self._override.id == self._selected:
            return self._override
        for box in self._boxes:
            if box.id == self._selected:
                return box
        return None

    def _box_at(self, position: QPointF) -> Optional[ContainerBox]:
        ordered = sorted(self._boxes, key=lambda box: (box.layer, box.id))
        for box in reversed([b for b in ordered if not b.fill]):
            if self._box_rect(box).contains(position):
                return box
        for box in ordered:
            if box.fill:
                return box
        return None

    # ── repaint-on-resize ───────────────────────────────────────────────────
    def resizeEvent(self, event) -> None:
        if self._fit_mode:
            self._fit()
            self.zoom_changed.emit(self._zoom)
        super().resizeEvent(event)

    # ── painting ────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor(tokens.BG_PANEL))
        canvas = self._canvas_rect()

        colour = resolve_paint_color(self._background, self._palette)
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.setBrush(colour if colour is not None
                         else QColor(tokens.BG_BASE))
        painter.drawRect(canvas)

        if self._show_safe and self._safe > 0:
            inset_x = canvas.width() * self._safe
            inset_y = canvas.height() * self._safe
            safe = canvas.adjusted(inset_x, inset_y, -inset_x, -inset_y)
            pen = QPen(QColor(tokens.BORDER_POPOVER), 1,
                       Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(safe)

        ordered = sorted(self._boxes, key=lambda box: (box.layer, box.id))
        for box in ordered:
            if box.id == self._selected:
                continue
            self._paint_box(painter, box, selected=False)
        selected = self._selected_box()
        if selected is not None:
            self._paint_box(painter, selected, selected=True)

        for x in self._guides["v"]:
            view_x = canvas.left() + x * self._zoom
            painter.setPen(QPen(QColor(tokens.ACCENT), 1,
                                Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(view_x, canvas.top()),
                             QPointF(view_x, canvas.bottom()))
        for y in self._guides["h"]:
            view_y = canvas.top() + y * self._zoom
            painter.setPen(QPen(QColor(tokens.ACCENT), 1,
                                Qt.PenStyle.DashLine))
            painter.drawLine(QPointF(canvas.left(), view_y),
                             QPointF(canvas.right(), view_y))

        if self._readout and (self._drag is not None
                              or self._override is not None):
            box = self._selected_box()
            if box is not None:
                self._paint_readout(painter, canvas, box)
        if self.hasFocus():
            paint_focus_ring(painter, QRectF(self.rect()).adjusted(
                0.5, 0.5, -0.5, -0.5), tokens.RADIUS_SM)
        painter.end()

    def _paint_box(self, painter: QPainter, box: ContainerBox, *,
                   selected: bool) -> None:
        rect = self._box_rect(box)
        hovered = box.id == self._hover and not selected
        if box.fill:
            fill = QColor(tokens.ACCENT_TINT)
            fill.setAlpha(60)
            painter.setPen(QPen(QColor(tokens.ACCENT_BORDER if selected
                                       else tokens.BORDER_POPOVER), 1,
                                Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawRect(rect)
        else:
            alpha = 255 if box.visible else 90
            fill = QColor(tokens.BG_FIELD)
            fill.setAlpha(min(alpha, 220))
            if selected:
                fill = QColor(tokens.ACCENT_TINT)
                fill.setAlpha(180)
            elif hovered:
                fill = QColor(tokens.BG_CARD_HOVER)
            painter.setPen(QPen(
                QColor(tokens.ACCENT if selected else
                       tokens.ACCENT_BORDER if hovered else
                       tokens.BORDER_POPOVER),
                1.4 if selected else 1.0,
                Qt.PenStyle.SolidLine if box.visible
                else Qt.PenStyle.DashLine))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 3, 3)

        if rect.height() >= 16 and rect.width() >= 40:
            label_font = font(9, tokens.WEIGHT_SEMIBOLD)
            painter.setFont(label_font)
            metrics = QFontMetrics(label_font)
            text = f"{int(box.layer)}  {box.title()}"
            chip_width = min(rect.width() - 6,
                             metrics.horizontalAdvance(text) + 10)
            chip_left = (rect.right() - chip_width - 3 if box.fill
                         else rect.left() + 3)
            chip = QRectF(chip_left, rect.top() + 3, chip_width, 14)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(tokens.BG_POPOVER))
            painter.drawRoundedRect(chip, 3, 3)
            painter.setPen(QColor(
                tokens.ACCENT_TEXT if selected else
                tokens.TEXT_SECONDARY if box.visible else tokens.TEXT_MUTED))
            painter.drawText(
                chip.adjusted(4, 0, -4, 0),
                int(Qt.AlignmentFlag.AlignLeft |
                    Qt.AlignmentFlag.AlignVCenter),
                metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                   int(chip.width() - 8)))

        if selected and not box.fill:
            for handle, handle_rect in self._handle_rects(box).items():
                painter.setPen(QPen(QColor(tokens.ACCENT), 1))
                painter.setBrush(QColor(tokens.BG_PANEL))
                painter.drawRect(handle_rect)

    def _paint_readout(self, painter: QPainter, canvas: QRectF,
                       box: ContainerBox) -> None:
        text = (f"x {int(round(box.x))}   y {int(round(box.y))}   "
                f"·   {int(round(box.width))} × {int(round(box.height))}")
        label_font = font(10, tokens.WEIGHT_MEDIUM)
        metrics = QFontMetrics(label_font)
        width = metrics.horizontalAdvance(text) + 14
        rect = QRectF(canvas.left() + 6, canvas.bottom() - 22,
                      min(width, canvas.width() - 12), 16)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.BG_POPOVER))
        painter.drawRoundedRect(rect, 3, 3)
        painter.setFont(label_font)
        painter.setPen(QColor(tokens.TEXT_SECONDARY))
        painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter),
                         metrics.elidedText(text, Qt.TextElideMode.ElideRight,
                                            int(rect.width() - 8)))

    # ── interaction ─────────────────────────────────────────────────────────
    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        position = event.position()
        selected = self._selected_box()
        if selected is not None and not selected.fill:
            for handle, rect in self._handle_rects(selected).items():
                if rect.adjusted(-2, -2, 2, 2).contains(position):
                    self._begin_drag(selected, "resize", handle, position)
                    event.accept()
                    return
        box = self._box_at(position)
        if box is None:
            self.set_selected("", emit=True)
            event.accept()
            return
        if box.id != self._selected:
            self.set_selected(box.id, emit=True)
        if box.fill:
            event.accept()
            return
        self._begin_drag(box, "move", "", position)
        event.accept()

    def _begin_drag(self, box: ContainerBox, mode: str, handle: str,
                    position: QPointF) -> None:
        self._drag = {
            "id": box.id,
            "mode": mode,
            "handle": handle,
            "start": self._design_point(position),
            "rect": QRectF(box.x, box.y, box.width, box.height),
            "changed": False,
        }
        self._guides = {"v": [], "h": []}
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._drag is None:
            position = event.position()
            selected = self._selected_box()
            cursor = Qt.CursorShape.ArrowCursor
            hovered = ""
            if selected is not None and not selected.fill:
                for handle, rect in self._handle_rects(selected).items():
                    if rect.adjusted(-2, -2, 2, 2).contains(position):
                        cursor = _HANDLE_CURSORS[handle]
                        hovered = selected.id
                        break
            if cursor == Qt.CursorShape.ArrowCursor:
                box = self._box_at(position)
                if box is not None:
                    hovered = box.id
                    cursor = (Qt.CursorShape.ArrowCursor if box.fill
                              else Qt.CursorShape.SizeAllCursor)
            self.setCursor(cursor)
            if hovered != self._hover:
                self._hover = hovered
                self.update()
            return
        self._update_drag(event.position())
        event.accept()

    def _update_drag(self, position: QPointF) -> None:
        drag = self._drag
        if drag is None:
            return
        point = self._design_point(position)
        start = drag["start"]
        origin: QRectF = drag["rect"]
        dx = point.x() - start.x()
        dy = point.y() - start.y()
        if drag["mode"] == "move":
            rect = QRectF(origin)
            rect.translate(dx, dy)
            rect = self._snap_move(rect, drag["id"])
            rect = self._clamp_rect(rect)
        else:
            rect = self._resize_rect(origin, drag["handle"], point)
            rect = self._snap_resize(rect, drag["handle"], drag["id"])
            rect = self._clamp_rect(rect)
        box = ContainerBox(
            id=drag["id"], label=self._label_for(drag["id"]),
            x=rect.x(), y=rect.y(), width=rect.width(),
            height=rect.height(), layer=self._layer_for(drag["id"]))
        drag["changed"] = (round(rect.x()) != round(origin.x())
                           or round(rect.y()) != round(origin.y())
                           or round(rect.width()) != round(origin.width())
                           or round(rect.height()) != round(origin.height()))
        drag["live"] = rect
        self._override = box
        self.preview.emit(box.id, box.geometry())
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        drag = self._drag
        self._drag = None
        self._guides = {"v": [], "h": []}
        if drag is not None and drag.get("changed"):
            rect: QRectF = drag.get("live", drag["rect"])
            box = ContainerBox(
                id=drag["id"], label=self._label_for(drag["id"]),
                x=rect.x(), y=rect.y(), width=rect.width(),
                height=rect.height(), layer=self._layer_for(drag["id"]))
            self._override = box
            self.changed.emit(box.id, box.geometry())
        self.update()
        event.accept()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape and self._drag is not None:
            self._drag = None
            self._override = None
            self._guides = {"v": [], "h": []}
            self.update()
            event.accept()
            return
        box = self._selected_box()
        if box is not None and not box.fill and event.key() in (
                Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up,
                Qt.Key.Key_Down):
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier \
                else 1
            rect = QRectF(box.x, box.y, box.width, box.height)
            if event.key() == Qt.Key.Key_Left:
                rect.translate(-step, 0)
            elif event.key() == Qt.Key.Key_Right:
                rect.translate(step, 0)
            elif event.key() == Qt.Key.Key_Up:
                rect.translate(0, -step)
            else:
                rect.translate(0, step)
            rect = self._clamp_rect(rect)
            nudged = ContainerBox(
                id=box.id, label=box.label, x=rect.x(), y=rect.y(),
                width=rect.width(), height=rect.height(), layer=box.layer,
                visible=box.visible)
            self._override = nudged
            self.changed.emit(nudged.id, nudged.geometry())
            self.update()
            event.accept()
            return
        super().keyPressEvent(event)

    # ── geometry helpers ────────────────────────────────────────────────────
    def _label_for(self, box_id: str) -> str:
        for box in self._boxes:
            if box.id == box_id:
                return box.label
        return ""

    def _layer_for(self, box_id: str) -> int:
        for box in self._boxes:
            if box.id == box_id:
                return box.layer
        return 0

    @staticmethod
    def _resize_rect(origin: QRectF, handle: str,
                     point: QPointF) -> QRectF:
        rect = QRectF(origin)
        left, right = origin.left(), origin.right()
        top, bottom = origin.top(), origin.bottom()
        if "w" in handle:
            left = point.x()
        if "e" in handle:
            right = point.x()
        if "n" in handle:
            top = point.y()
        if "s" in handle:
            bottom = point.y()
        minimum = 12.0
        if right - left < minimum:
            if "w" in handle:
                left = right - minimum
            else:
                right = left + minimum
        if bottom - top < minimum:
            if "n" in handle:
                top = bottom - minimum
            else:
                bottom = top + minimum
        return QRectF(QPointF(left, top), QPointF(right, bottom))

    def _candidates(self, box_id: str) -> tuple[list[float], list[float]]:
        xs = [0.0, self._canvas_w / 2, self._canvas_w]
        ys = [0.0, self._canvas_h / 2, self._canvas_h]
        for box in self._boxes:
            if box.id == box_id or box.fill:
                continue
            xs.extend([box.x, box.x + box.width / 2, box.x + box.width])
            ys.extend([box.y, box.y + box.height / 2, box.y + box.height])
        return xs, ys

    @staticmethod
    def _nearest(edges: Iterable[float], candidates: Iterable[float],
                 threshold: float) -> tuple[float, float, bool]:
        best_delta = 0.0
        best_line = 0.0
        found = False
        for edge in edges:
            for candidate in candidates:
                delta = candidate - edge
                if abs(delta) <= threshold and (
                        not found or abs(delta) < abs(best_delta)):
                    best_delta = delta
                    best_line = candidate
                    found = True
        return best_delta, best_line, found

    def _snap_move(self, rect: QRectF, box_id: str) -> QRectF:
        xs, ys = self._candidates(box_id)
        threshold = 6.0 / max(self._zoom, 1e-6)
        dx, line_x, found_x = self._nearest(
            (rect.left(), rect.center().x(), rect.right()), xs, threshold)
        if found_x:
            rect.translate(dx, 0)
        dy, line_y, found_y = self._nearest(
            (rect.top(), rect.center().y(), rect.bottom()), ys, threshold)
        if found_y:
            rect.translate(0, dy)
        self._guides = {
            "v": [line_x] if found_x else [],
            "h": [line_y] if found_y else [],
        }
        return rect

    def _snap_resize(self, rect: QRectF, handle: str,
                     box_id: str) -> QRectF:
        xs, ys = self._candidates(box_id)
        threshold = 6.0 / max(self._zoom, 1e-6)
        guides_v: list[float] = []
        guides_h: list[float] = []
        if "w" in handle:
            delta, line, found = self._nearest((rect.left(),), xs, threshold)
            if found:
                rect.setLeft(rect.left() + delta)
                guides_v.append(line)
        if "e" in handle:
            delta, line, found = self._nearest((rect.right(),), xs, threshold)
            if found:
                rect.setRight(rect.right() + delta)
                guides_v.append(line)
        if "n" in handle:
            delta, line, found = self._nearest((rect.top(),), ys, threshold)
            if found:
                rect.setTop(rect.top() + delta)
                guides_h.append(line)
        if "s" in handle:
            delta, line, found = self._nearest((rect.bottom(),), ys, threshold)
            if found:
                rect.setBottom(rect.bottom() + delta)
                guides_h.append(line)
        self._guides = {"v": guides_v, "h": guides_h}
        return rect

    def _clamp_rect(self, rect: QRectF) -> QRectF:
        width = min(rect.width(), self._canvas_w)
        height = min(rect.height(), self._canvas_h)
        x = max(0.0, min(rect.x(), self._canvas_w - width))
        y = max(0.0, min(rect.y(), self._canvas_h - height))
        return QRectF(x, y, width, height)


class ContainerCanvas(QWidget):
    """Canvas surface plus a compact zoom / safe-area footer.

    Signals
        selected(str) — a container id was selected (or "" to clear).
        changed(str, object) — ``(id, {"x","y","width","height"})`` after a
            drag, resize or arrow nudge. The caller applies it and calls
            :meth:`set_boxes` with the new geometry.
        preview(str, object) — the same payload continuously during a drag.
        zoom_changed(float) — scale factor changed.
    """

    selected = pyqtSignal(str)
    changed = pyqtSignal(str, object)
    preview = pyqtSignal(str, object)
    zoom_changed = pyqtSignal(float)

    def __init__(self, canvas_size: tuple[float, float] = (1920, 1080), *,
                 safe_area: float = 0.05, show_readout: bool = True,
                 background: str = "transparent",
                 palette: Iterable[tuple[str, str]] = (), parent=None):
        super().__init__(parent)
        self._updating = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.surface = _Surface(canvas_size, safe_area, show_readout,
                               background, palette, self)
        self.surface.selected.connect(self._on_selected)
        self.surface.changed.connect(self.changed)
        self.surface.preview.connect(self.preview)
        self.surface.zoom_changed.connect(self._on_zoom)
        layout.addWidget(self.surface, 1)

        footer = QWidget(self)
        row = QHBoxLayout(footer)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(tokens.SPACE_4)
        self.safe_toggle = ToggleButton(
            text="Safe", tooltip="Show the safe-area guide",
            accessible_name="Show safe area")
        self.safe_toggle.changed.connect(self.surface.set_safe_area_visible)
        row.addWidget(self.safe_toggle, 0)
        self.fill_note = QLabel("", footer)
        self.fill_note.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: 10px; background: transparent;")
        row.addWidget(self.fill_note, 1)
        self.zoom_out_button = IconButton(
            glyph="minus", tooltip="Zoom out", accessible_name="Zoom out",
            variant="ghost", compact=True, parent=footer)
        self.zoom_out_button.clicked.connect(self.surface.zoom_out)
        row.addWidget(self.zoom_out_button, 0)
        self.zoom_label = QLabel("100%", footer)
        self.zoom_label.setFixedWidth(36)
        self.zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.zoom_label.setStyleSheet(
            f"color: {tokens.TEXT_MUTED};"
            f"font-size: 10px; background: transparent;")
        row.addWidget(self.zoom_label, 0)
        self.zoom_in_button = IconButton(
            glyph="plus", tooltip="Zoom in", accessible_name="Zoom in",
            variant="ghost", compact=True, parent=footer)
        self.zoom_in_button.clicked.connect(self.surface.zoom_in)
        row.addWidget(self.zoom_in_button, 0)
        self.fit_button = IconButton(
            text="Fit", tooltip="Fit the canvas to the view",
            accessible_name="Fit canvas to view", variant="ghost",
            compact=True, parent=footer)
        self.fit_button.clicked.connect(self.surface.fit)
        row.addWidget(self.fit_button, 0)
        layout.addWidget(footer)

    # ── public ──────────────────────────────────────────────────────────────
    def set_canvas_size(self, width: float, height: float) -> None:
        self.surface.set_canvas_size(width, height)

    def set_boxes(self, boxes: Iterable[Any], selected: Optional[str] = None,
                  *, keep_override: bool = False) -> None:
        self.surface.set_boxes(boxes, selected, keep_override=keep_override)
        self._sync_fill_note()

    def set_selected(self, box_id: str, *, emit: bool = False) -> None:
        self.surface.set_selected(box_id, emit=emit)

    def selected_id(self) -> str:
        return self.surface.selected_id()

    def set_background(self, value: str) -> None:
        self.surface.set_background(value)

    def set_palette(self, palette: Iterable[tuple[str, str]]) -> None:
        self.surface._palette = dict(palette)

    def set_safe_area_visible(self, visible: bool) -> None:
        self.safe_toggle.blockSignals(True)
        self.safe_toggle.setChecked(bool(visible))
        self.safe_toggle.blockSignals(False)
        self.safe_toggle.update()
        self.surface.set_safe_area_visible(visible)

    def safe_area_visible(self) -> bool:
        return self.surface.safe_area_visible()

    def set_zoom(self, value: float) -> None:
        self.surface.set_zoom(value)

    def zoom(self) -> float:
        return self.surface.zoom()

    def fit(self) -> None:
        self.surface.fit()

    def zoom_in(self) -> None:
        self.surface.zoom_in()

    def zoom_out(self) -> None:
        self.surface.zoom_out()

    # ── internals ───────────────────────────────────────────────────────────
    def _on_selected(self, box_id: str) -> None:
        self._sync_fill_note()
        self.selected.emit(box_id)

    def _sync_fill_note(self) -> None:
        selected = self.surface._selected_box()
        if selected is not None and selected.fill:
            self.fill_note.setText("Fill anchor · not draggable")
        else:
            self.fill_note.setText("")

    def _on_zoom(self, zoom: float) -> None:
        self.zoom_label.setText(f"{round(zoom * 100)}%")
        self._sync_fill_note()
        self.zoom_changed.emit(zoom)


# ─── Layer strip ────────────────────────────────────────────────────────────

class _StripRow(QAbstractButton):
    picked = pyqtSignal(str)
    visibility_toggled = pyqtSignal(str, bool)
    drag_started = pyqtSignal(str)
    dragged = pyqtSignal(str, float)
    drag_finished = pyqtSignal(str)
    stepped = pyqtSignal(str, int)

    def __init__(self, box: ContainerBox, selected: bool, parent=None):
        super().__init__(parent)
        self._box = box
        self._selected = selected
        self._hover = False
        self._drag_y = 0.0
        self._dragging = False
        self.setFixedHeight(tokens.CONTROL_HEIGHT_SM)
        self.setCheckable(False)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        self.setAccessibleName(f"Container {box.title()}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Fixed)
        attach_tooltip(
            self, lambda: f"{box.title()} · layer {box.layer}"
                          + ("" if box.visible else " · hidden"))

    def box(self) -> ContainerBox:
        return self._box

    def _dot_rect(self) -> QRectF:
        return QRectF(6, (self.height() - 10) / 2, 10, 10)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect())
        if self._selected:
            painter.fillRect(rect, QColor(tokens.ACCENT_TINT))
            painter.fillRect(QRectF(0, 0, 2, rect.height()),
                             QColor(tokens.ACCENT))
        elif self._hover:
            painter.fillRect(rect, QColor(tokens.BG_CARD_HOVER))
        dot = self._dot_rect()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(tokens.ACCENT if self._box.visible
                                else tokens.BORDER_POPOVER))
        painter.drawEllipse(dot.center(), 3.0, 3.0)
        layer_rect = QRectF(rect.right() - 26, rect.top(), 20, rect.height())
        painter.setFont(font(9, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(tokens.TEXT_MUTED))
        painter.drawText(layer_rect,
                         int(Qt.AlignmentFlag.AlignRight |
                             Qt.AlignmentFlag.AlignVCenter),
                         str(self._box.layer))
        label_rect = QRectF(22, rect.top(), max(0.0, rect.width() - 52),
                            rect.height())
        painter.setFont(font(tokens.TYPE_CAPTION, tokens.WEIGHT_MEDIUM))
        painter.setPen(QColor(
            tokens.TEXT_PRIMARY if self._selected or self._hover
            else tokens.TEXT_SECONDARY if self._box.visible
            else tokens.TEXT_MUTED))
        painter.drawText(
            label_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elide(self._box.title(), label_rect.width()))
        draw_chevron(painter, QPointF(rect.right() - 6,
                                      rect.center().y()),
                     "down", tokens.BORDER_POPOVER, size=2.6)
        if self.hasFocus():
            paint_focus_ring(painter, rect.adjusted(1, 0, -1, 0),
                             tokens.RADIUS_SM)
        painter.end()

    def enterEvent(self, event) -> None:
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        self.picked.emit(self._box.id)
        self._drag_y = event.globalPosition().y()
        self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event) -> None:
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return
        if not self._dragging and abs(
                event.globalPosition().y() - self._drag_y) > 6:
            self._dragging = True
            self.drag_started.emit(self._box.id)
        if self._dragging:
            self.dragged.emit(self._box.id, event.globalPosition().y())
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._dragging:
            self._dragging = False
            self.drag_finished.emit(self._box.id)
        elif self._dot_rect().adjusted(-3, -3, 3, 3).contains(
                event.position()):
            visible = not self._box.visible
            self._box.visible = visible
            self.update()
            self.visibility_toggled.emit(self._box.id, visible)
        event.accept()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.picked.emit(self._box.id)
        elif key == Qt.Key.Key_Space:
            visible = not self._box.visible
            self._box.visible = visible
            self.update()
            self.visibility_toggled.emit(self._box.id, visible)
        elif key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.stepped.emit(self._box.id,
                              -1 if key == Qt.Key.Key_Up else 1)
        else:
            super().keyPressEvent(event)
            return
        event.accept()


class _StripBody(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: list[_StripRow] = []
        self.drop_index = -1
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(1)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.drop_index < 0 or not self.rows:
            return
        painter = QPainter(self)
        if self.drop_index == 0:
            y = self.rows[0].geometry().top()
        elif self.drop_index >= len(self.rows):
            y = self.rows[-1].geometry().bottom()
        else:
            y = self.rows[self.drop_index].geometry().top()
        painter.fillRect(0, max(0, y - 1), self.width(), 2,
                         QColor(tokens.ACCENT))
        painter.end()


class ContainerStrip(QWidget):
    """Slim layer list: select, add, duplicate, delete, reorder, visibility.

    Signals
        selected(str)
        add_requested()
        duplicate_requested(str)
        delete_requested(str)
        visibility_toggled(str, bool)
        reordered(list) — the new id order, top (front) first.
    """

    selected = pyqtSignal(str)
    add_requested = pyqtSignal()
    duplicate_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)
    visibility_toggled = pyqtSignal(str, bool)
    reordered = pyqtSignal(object)

    def __init__(self, boxes: Iterable[Any] = (), selected: str = "",
                 *, max_visible_rows: int = 6, parent=None):
        super().__init__(parent)
        self._boxes: list[ContainerBox] = []
        self._selected = str(selected)
        self._dragging_id = ""
        self._drop_index = -1
        self._max_rows = max(2, int(max_visible_rows))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(tokens.SPACE_4)

        head = QWidget(self)
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(0, 0, 0, 0)
        head_row.setSpacing(tokens.SPACE_4)
        head_row.addWidget(SectionLabel("Containers"), 0)
        self.count = Badge("0")
        head_row.addWidget(self.count, 0)
        head_row.addStretch(1)
        self.add_button = IconButton(
            glyph="plus", tooltip="Add container",
            accessible_name="Add container", variant="ghost", compact=True,
            parent=head)
        self.add_button.clicked.connect(self.add_requested)
        head_row.addWidget(self.add_button, 0)
        self.duplicate_button = IconButton(
            glyph="copy", tooltip="Duplicate container",
            accessible_name="Duplicate container", variant="ghost",
            compact=True, parent=head)
        self.duplicate_button.clicked.connect(
            lambda: self._emit_duplicate())
        head_row.addWidget(self.duplicate_button, 0)
        self.delete_button = IconButton(
            glyph="trash", tooltip="Delete container",
            accessible_name="Delete container", variant="ghost",
            compact=True, parent=head)
        self.delete_button.clicked.connect(lambda: self._emit_delete())
        head_row.addWidget(self.delete_button, 0)
        layout.addWidget(head)

        self.empty = EmptyState("No containers yet",
                                "Add one to start laying out the canvas.")
        layout.addWidget(self.empty)

        self.scroll = QScrollArea(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = _StripBody(self)
        self.scroll.setWidget(self.body)
        self.scroll.setVisible(False)
        layout.addWidget(self.scroll, 1)
        self.set_boxes(boxes, selected)

    # ── public ──────────────────────────────────────────────────────────────
    def set_boxes(self, boxes: Iterable[Any], selected: Optional[str] = None) -> None:
        self._boxes = [ContainerBox.from_any(box) for box in boxes]
        if selected is not None:
            self._selected = str(selected)
        if self._selected and not any(box.id == self._selected
                                      for box in self._boxes):
            self._selected = ""
        self._rebuild()

    def set_selected(self, box_id: str, *, emit: bool = False) -> None:
        if box_id == self._selected:
            return
        self._selected = str(box_id or "")
        for row in self.body.rows:
            row._selected = row.box().id == self._selected
            row.update()
        self._sync_buttons()
        if emit:
            self.selected.emit(self._selected)

    def selected_id(self) -> str:
        return self._selected

    # ── building ────────────────────────────────────────────────────────────
    def _rebuild(self) -> None:
        for row in self.body.rows:
            self.body._layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self.body.rows = []
        self.count.set_text(str(len(self._boxes)))
        has_boxes = bool(self._boxes)
        self.empty.setVisible(not has_boxes)
        self.scroll.setVisible(has_boxes)
        for box in self._boxes:
            row = _StripRow(box, box.id == self._selected, self.body)
            row.picked.connect(self._on_picked)
            row.visibility_toggled.connect(self.visibility_toggled)
            row.drag_started.connect(self._on_drag_started)
            row.dragged.connect(self._on_dragged)
            row.drag_finished.connect(self._on_drag_finished)
            row.stepped.connect(self._on_stepped)
            self.body._layout.addWidget(row)
            self.body.rows.append(row)
        rows = max(1, min(len(self._boxes), self._max_rows))
        self.scroll.setFixedHeight(
            rows * (tokens.CONTROL_HEIGHT_SM + 1) + 2)
        self._sync_buttons()

    def _sync_buttons(self) -> None:
        has_selection = any(box.id == self._selected for box in self._boxes)
        self.duplicate_button.setEnabled(has_selection)
        self.delete_button.setEnabled(has_selection and len(self._boxes) > 1)
        self.add_button.setEnabled(len(self._boxes) < 16)

    # ── interaction ─────────────────────────────────────────────────────────
    def _on_picked(self, box_id: str) -> None:
        if box_id != self._selected:
            self.set_selected(box_id, emit=True)

    def _emit_duplicate(self) -> None:
        if any(box.id == self._selected for box in self._boxes):
            self.duplicate_requested.emit(self._selected)

    def _emit_delete(self) -> None:
        if any(box.id == self._selected for box in self._boxes):
            self.delete_requested.emit(self._selected)

    def _on_stepped(self, box_id: str, direction: int) -> None:
        ids = [box.id for box in self._boxes]
        if box_id not in ids:
            return
        index = (ids.index(box_id) + direction) % len(ids)
        for row in self.body.rows:
            if row.box().id == ids[index]:
                row.setFocus(Qt.FocusReason.TabFocusReason)
                return

    def _on_drag_started(self, box_id: str) -> None:
        self._dragging_id = box_id

    def _on_dragged(self, box_id: str, global_y: float) -> None:
        if not self.body.rows:
            return
        position = self.body.mapFromGlobal(QPoint(0, int(global_y)))
        index = len(self.body.rows)
        for row in self.body.rows:
            if position.y() < row.geometry().center().y():
                index = self.body.rows.index(row)
                break
        self._drop_index = index
        self.body.drop_index = index
        self.body.update()

    def _on_drag_finished(self, box_id: str) -> None:
        drop = self._drop_index
        self._drop_index = -1
        self.body.drop_index = -1
        self.body.update()
        if drop < 0:
            return
        ids = [box.id for box in self._boxes]
        if box_id not in ids:
            return
        ids.remove(box_id)
        if drop > len(ids):
            drop = len(ids)
        ids.insert(drop, box_id)
        if ids != [box.id for box in self._boxes]:
            self.reordered.emit(ids)
        self._dragging_id = ""


__all__ = ["ContainerBox", "ContainerCanvas", "ContainerStrip"]
