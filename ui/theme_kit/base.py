"""ui/theme_kit/base.py

Shared vocabulary and painting helpers for the Theme Designer widget kit.

Nothing here knows a theme property name. The kit is deliberately
property-agnostic: rows, fields and compound editors receive their values,
ranges, options and defaults from the caller (ultimately
``core/theme_schema``) and only render or emit what they are given.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor, QFont, QFontMetricsF, QIcon, QPainter, QPainterPath, QPen,
)

from ui import tokens


# ─── Shared option shapes ───────────────────────────────────────────────────

@dataclass(frozen=True)
class ChoiceOption:
    """One choice in a dropdown, chip row or segmented toggle.

    ``value`` is whatever the caller stores (string, int, dict...). ``label``
    is display text. ``muted`` renders an "inherit/none/auto"-style option as
    secondary rather than as a normal value. ``font_family`` asks a list to
    preview the row in that typeface (font pickers). ``group`` lets a long
    list draw a section header; it is ignored by compact controls.
    """

    value: Any
    label: str = ""
    icon: Any = None
    muted: bool = False
    tooltip: str = ""
    disabled_reason: str = ""
    font_family: str = ""
    group: str = ""

    @property
    def text(self) -> str:
        return self.label if self.label else str(self.value)


@dataclass(frozen=True)
class SampleState:
    """One state for :class:`SampleInjector`; content stays caller-owned."""

    id: str
    label: str
    icon: Any = None
    group: str = ""
    #: "content" (ordinary), "custom" (opens text + reference), "shuffle"
    #: (emits reroll), or "blank" (empty sample).
    kind: str = "content"


def coerce_option(item: Any) -> ChoiceOption:
    """Accept a plain value or a :class:`ChoiceOption`."""
    if isinstance(item, ChoiceOption):
        return item
    if isinstance(item, SampleState):
        return ChoiceOption(item.id, item.label, item.icon, group=item.group)
    if isinstance(item, dict):
        return ChoiceOption(**item)
    return ChoiceOption(item, str(item))


def coerce_options(items: Iterable[Any]) -> list[ChoiceOption]:
    return [coerce_option(item) for item in items]


# ─── Small painting/text helpers ────────────────────────────────────────────

def font(size: int = tokens.TYPE_CAPTION,
         weight: int = tokens.WEIGHT_MEDIUM,
         family: str = "") -> QFont:
    result = QFont()
    if family:
        result.setFamily(family)
    result.setPixelSize(size)
    result.setWeight(QFont.Weight(weight))
    return result


def elide(text: str, width: float, size: int = tokens.TYPE_CAPTION,
          weight: int = tokens.WEIGHT_MEDIUM, family: str = "") -> str:
    metrics = QFontMetricsF(font(size, weight, family))
    return metrics.elidedText(str(text), Qt.TextElideMode.ElideRight,
                              max(0.0, width))


def format_number(value: float, *, integer: bool = False,
                  decimals: Optional[int] = None) -> str:
    """Stable display text: never ``24.0`` when the caller wants integers."""
    if integer:
        return str(int(round(float(value))))
    places = 2 if decimals is None else decimals
    text = f"{float(value):.{max(0, places)}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_number_text(text: str) -> Optional[float]:
    try:
        cleaned = str(text).strip().replace(",", ".")
        if not cleaned:
            return None
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def qcolor(value: Any, fallback: str = "#000000") -> QColor:
    """A QColor for painting only; schema validation stays with the caller."""
    color = QColor(value if value is not None else fallback)
    if not color.isValid():
        color = QColor(fallback)
    return color


def checkerboard(painter: QPainter, rect: QRectF, cell: int = 5) -> None:
    """Paint the alpha checkerboard inside ``rect`` (clipped)."""
    painter.save()
    path = QPainterPath()
    path.addRect(rect)
    painter.setClipPath(path)
    painter.fillRect(rect, QColor(tokens.CHECKER_DARK))
    light = QColor(tokens.CHECKER_LIGHT)
    y = rect.top()
    row = 0
    while y < rect.bottom():
        x = rect.left() + (cell if row % 2 else 0)
        while x < rect.right():
            painter.fillRect(QRectF(x, y, cell, cell), light)
            x += cell * 2
        y += cell
        row += 1
    painter.restore()


def rounded_rect(rect: QRectF, radius: float) -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    return path


def paint_focus_ring(painter: QPainter, rect: QRectF,
                     radius: float = tokens.RADIUS_SM) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(tokens.ACCENT), tokens.FOCUS_RING_WIDTH * 2)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    inset = tokens.FOCUS_RING_WIDTH
    painter.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset),
                            radius, radius)
    painter.restore()


def draw_chevron(painter: QPainter, centre: QPointF, direction: str,
                 color: str = tokens.TEXT_SECONDARY, size: float = 5.0,
                 width: float = 1.4) -> None:
    """A vector chevron identical on every platform (no QSS triangles)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    half = size / 2.0
    if direction in ("down", "up"):
        sign = 1 if direction == "down" else -1
        points = (
            QPointF(centre.x() - half, centre.y() - sign * half * 0.6),
            QPointF(centre.x(), centre.y() + sign * half * 0.6),
            QPointF(centre.x() + half, centre.y() - sign * half * 0.6),
        )
    else:
        sign = 1 if direction == "right" else -1
        points = (
            QPointF(centre.x() - sign * half * 0.6, centre.y() - half),
            QPointF(centre.x() + sign * half * 0.6, centre.y()),
            QPointF(centre.x() - sign * half * 0.6, centre.y() + half),
        )
    painter.drawPolyline(points)
    painter.restore()


def draw_check(painter: QPainter, rect: QRectF,
               color: str = tokens.ACCENT_TEXT) -> None:
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    left = rect.left() + rect.width() * 0.12
    mid = rect.left() + rect.width() * 0.42
    right = rect.left() + rect.width() * 0.9
    top = rect.top() + rect.height() * 0.52
    bottom = rect.bottom() - rect.height() * 0.12
    painter.drawPolyline(
        QPointF(left, top),
        QPointF(mid, bottom),
        QPointF(right, rect.top() + rect.height() * 0.18),
    )
    painter.restore()


def icon_pixmap(icon: Any, size: int) -> QIcon:
    """Normalise a path/QIcon so paints can ask for a pixmap."""
    if isinstance(icon, QIcon):
        return icon
    if isinstance(icon, str) and icon:
        return QIcon(icon)
    return QIcon()


def paints_icon(icon: Any) -> bool:
    return isinstance(icon, QIcon) or (isinstance(icon, str) and bool(icon))


#: A callable the kit calls after a state change to repaint a custom widget.
Repaint = Callable[[], None]

__all__ = [
    "ChoiceOption", "SampleState", "coerce_option", "coerce_options",
    "font", "elide", "format_number", "parse_number_text", "qcolor",
    "checkerboard", "rounded_rect", "paint_focus_ring", "draw_chevron",
    "draw_check", "icon_pixmap", "paints_icon",
]
