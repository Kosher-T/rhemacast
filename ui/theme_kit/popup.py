"""ui/theme_kit/popup.py

The kit's own floating surfaces: dropdowns, colour pickers, easing cards,
sample lists, and tooltips. No ``QComboBox``/``QMenu``/``QToolTip`` native
popup is used, so Linux and Windows show the same surface, row metrics and
placement rules.

A popup is a top-level ``Qt.Popup`` window painted by us. Placement is
clamped to the active screen's available geometry, opening above the anchor
when there is no room below, so a list can never open off-screen.
"""

from __future__ import annotations

from typing import Callable, Optional

from PyQt6.QtCore import (
    QEvent, QObject, QPoint, QRect, QRectF, QSize, Qt, QTimer, pyqtSignal,
)
from PyQt6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PyQt6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget

from ui import tokens

_TEXT_ROLE = Qt.ItemDataRole.UserRole + 90


class PopupSurface(QWidget):
    """Opaque rounded surface with a translucent gutter and 1 px edge."""

    #: Emitted after the surface closes. Popups are not deleted on close
    #: (``WA_DeleteOnClose`` is off), so an owning field that waits for
    #: ``destroyed`` never hears about a close and keeps a stale reference —
    #: the second click then only "closes" an already hidden popup.
    closed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None, *,
                 popup: bool = True, radius: int = tokens.RADIUS_MD):
        # Flags must be passed at construction: setting them afterwards
        # recreates the window without a transient parent, and Wayland then
        # refuses to make the popup grabbing ("Failed to create grabbing
        # popup ... has a transientParent set"), so it never stays visible.
        flags = Qt.WindowType.FramelessWindowHint
        flags |= (Qt.WindowType.Popup if popup else Qt.WindowType.ToolTip)
        flags |= Qt.WindowType.NoDropShadowWindowHint
        super().__init__(parent, flags)
        self._radius = radius
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        if not popup:
            self.setAttribute(
                Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        outer = QVBoxLayout(self)
        gutter = tokens.POPUP_GUTTER
        outer.setContentsMargins(gutter, gutter, gutter, gutter)
        outer.setSpacing(0)
        self.body = QWidget(self)
        self.body.setObjectName("rcKitPopupBody")
        self.body.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body.setStyleSheet(
            "QWidget#rcKitPopupBody { background: transparent; }")
        outer.addWidget(self.body)
        self.content = QVBoxLayout(self.body)
        self.content.setContentsMargins(
            tokens.SPACE_8, tokens.SPACE_8, tokens.SPACE_8, tokens.SPACE_8)
        self.content.setSpacing(tokens.SPACE_4)

    # ── painting ────────────────────────────────────────────────────────────
    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        gutter = tokens.POPUP_GUTTER
        surface = QRectF(self.rect()).adjusted(
            gutter, gutter, -gutter, -gutter)
        # A cheap, platform-independent halo: six translucent rings instead
        # of QGraphicsDropShadowEffect (which Windows renders differently).
        for step in range(gutter, 0, -1):
            alpha = max(2, 14 - step * 2)
            halo = surface.adjusted(-step, -step, step, step)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawRoundedRect(halo, self._radius + step,
                                    self._radius + step)
        painter.setBrush(QColor(tokens.BG_POPOVER))
        painter.setPen(QPen(QColor(tokens.BORDER_POPOVER), 1))
        painter.drawRoundedRect(surface, self._radius, self._radius)
        painter.end()

    # ── placement ───────────────────────────────────────────────────────────
    def follow(self, widget: Optional[QWidget]) -> None:
        """Adopt a transient parent before the surface is shown.

        Wayland refuses to map a tooltip or popup without a transient parent
        ("Failed to create popup. Ensure popup ... has a transientParent
        set"). The kit tooltip is a long-lived singleton created before any
        window exists, so the parent is adopted on every show. This sets the
        platform window's transient parent; it does not reparent the widget,
        so a settings dialog closing can never destroy the shared surface.
        """
        window = widget.window() if widget is not None else None
        if window is None:
            window = QApplication.activeWindow()
        if window is None:
            return
        if window.windowHandle() is None:
            window.winId()
        parent = window.windowHandle()
        if parent is None:
            return
        if self.windowHandle() is None:
            self.winId()
        handle = self.windowHandle()
        if handle is not None and handle.transientParent() is not parent:
            handle.setTransientParent(parent)

    @staticmethod
    def _screen_for(global_point: QPoint):
        screen = QGuiApplication.screenAt(global_point)
        return screen or QGuiApplication.primaryScreen()

    def _place(self, anchor_rect: QRect, width: Optional[int], *,
               max_height: Optional[int], gap: int, prefer_above: bool,
               align: str) -> None:
        screen = self._screen_for(anchor_rect.center())
        available = screen.availableGeometry() if screen else QRect(
            0, 0, 1920, 1080)

        wanted = width if width is not None else anchor_rect.width()
        wanted = max(120, min(wanted, available.width() - 2 * tokens.SPACE_8))
        self.setFixedWidth(wanted)
        self.adjustSize()
        height = self.sizeHint().height()
        if max_height is not None:
            height = min(height, max_height)
        height = min(height, available.height() - 2 * tokens.SPACE_8)
        self.resize(wanted, height)

        if align == "right":
            x = anchor_rect.right() - wanted + 1
        elif align == "center":
            x = anchor_rect.center().x() - wanted // 2
        else:
            x = anchor_rect.left()
        x = max(available.left() + tokens.SPACE_4,
                min(x, available.right() - wanted - tokens.SPACE_4 + 1))

        below = anchor_rect.bottom() + gap
        above = anchor_rect.top() - gap - height
        room_below = available.bottom() - below
        room_above = anchor_rect.top() - gap - available.top()
        if prefer_above and room_above >= height:
            y = above
        elif room_below >= height:
            y = below
        elif room_above >= height or room_above > room_below:
            y = max(available.top() + tokens.SPACE_4, above)
        else:
            y = max(available.top() + tokens.SPACE_4,
                    min(below, available.bottom() - height -
                        tokens.SPACE_4 + 1))
        self.move(x, y)

    def show_below(self, anchor: QWidget, *, width: Optional[int] = None,
                   max_height: Optional[int] = tokens.POPUP_MAX_HEIGHT,
                   gap: int = 2, align: str = "left",
                   prefer_above: bool = False) -> None:
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        rect = QRect(top_left, anchor.size())
        self._place(rect, width, max_height=max_height, gap=gap,
                    prefer_above=prefer_above, align=align)
        self.show()
        self.raise_()

    def show_for(self, anchor: QWidget, *, width: Optional[int] = None,
                 max_height: Optional[int] = tokens.POPUP_MAX_HEIGHT,
                 gap: int = 6) -> None:
        """Show next to a widget without covering it (tooltips)."""
        top_left = anchor.mapToGlobal(QPoint(0, 0))
        rect = QRect(top_left, anchor.size())
        screen = self._screen_for(rect.center())
        available = screen.availableGeometry() if screen else QRect(
            0, 0, 1920, 1080)
        wanted = width if width is not None else 270
        wanted = max(120, min(wanted, available.width() - 2 * tokens.SPACE_8))
        self.setFixedWidth(wanted)
        self.adjustSize()
        height = self.sizeHint().height()
        if max_height is not None:
            height = min(height, max_height)
        height = min(height, available.height() - 2 * tokens.SPACE_8)
        self.resize(wanted, height)
        self.move(tooltip_position(rect, QSize(wanted, height), available,
                                   gap=gap))
        self.show()
        self.raise_()

    def show_at(self, global_pos: QPoint, *, width: Optional[int] = None,
                max_height: Optional[int] = tokens.POPUP_MAX_HEIGHT,
                gap: int = 2) -> None:
        # Anchor is a zero-size rect at the pointer; content grows down/right
        # and flips above when the screen bottom is close.
        rect = QRect(global_pos, QSize(1, 1))
        self._place(rect, width, max_height=max_height, gap=gap,
                    prefer_above=False, align="left")
        self.show()
        self.raise_()

    # ── keys ────────────────────────────────────────────────────────────────
    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self.closed.emit()
        super().closeEvent(event)


# ─── Tooltips ───────────────────────────────────────────────────────────────

def tooltip_position(anchor, tip, available, *, gap: int = 6) -> QPoint:
    """Top-left for a tooltip that does not cover the control it describes.

    Below the anchor first, then above it, then beside it. The old placement
    put the surface at the cursor plus an offset, which on a 240 px panel laid
    a 270 px tooltip straight over its own control. A position that would
    intersect the anchor is skipped even when it is otherwise on screen.
    """
    if not isinstance(anchor, QRect):
        anchor = QRect(*anchor)
    if not isinstance(available, QRect):
        available = QRect(*available)
    tip = tip if isinstance(tip, QSize) else QSize(*tip)

    def place(x: int, y: int) -> tuple[bool, QPoint]:
        x = max(available.left(),
                min(int(x), available.right() - tip.width() + 1))
        y = max(available.top(),
                min(int(y), available.bottom() - tip.height() + 1))
        rect = QRect(x, y, tip.width(), tip.height())
        return (available.contains(rect) and not rect.intersects(anchor),
                QPoint(x, y))

    candidates = (
        (anchor.left(), anchor.bottom() + gap),
        (anchor.left(), anchor.top() - gap - tip.height()),
        (anchor.right() + gap, anchor.top()),
        (anchor.left() - gap - tip.width(), anchor.top()),
    )
    for x, y in candidates:
        fits, point = place(x, y)
        if fits:
            return point
    return place(*candidates[0])[1]


class _TooltipPopup(PopupSurface):
    def __init__(self):
        super().__init__(popup=False, radius=tokens.RADIUS_SM)
        self.content.setContentsMargins(
            tokens.SPACE_8, tokens.SPACE_4, tokens.SPACE_8, tokens.SPACE_4)
        self.content.setSpacing(2)
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.PlainText)
        self._label.setStyleSheet(
            f"color: {tokens.TEXT_PRIMARY};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            f"background: transparent;")
        self.content.addWidget(self._label)
        self._more = QLabel()
        self._more.setWordWrap(True)
        self._more.setTextFormat(Qt.TextFormat.PlainText)
        self._more.setStyleSheet(
            f"color: {tokens.ACCENT_TEXT};"
            f"font-size: {tokens.TYPE_CAPTION}px;"
            f"background: transparent;")
        self._more.hide()
        self.content.addWidget(self._more)
        self.setMaximumWidth(320)

    def set_text(self, text: str, learn_more: str = "") -> None:
        self._label.setText(text)
        self._more.setVisible(bool(learn_more))
        self._more.setText(learn_more)


class TooltipManager(QObject):
    """One hover tooltip for the whole kit, with 500 ms hover delay.

    Tooltips are our own widget so Windows and Linux cannot disagree about
    padding, radius, wrapping or maximum width. ``attach_tooltip`` accepts a
    callable so a stateful control can update its text without re-attaching.
    """

    _instance: Optional["TooltipManager"] = None

    @classmethod
    def instance(cls) -> "TooltipManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._popup = _TooltipPopup()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._show_pending)
        self._widget: Optional[QWidget] = None
        self._text: Callable[[], str] | str = ""
        self._more: str = ""

    def attach(self, widget: QWidget,
               text: Callable[[], str] | str, learn_more: str = "") -> None:
        widget.setProperty("_rc_kit_tooltip", text)
        widget.setProperty("_rc_kit_tooltip_more", learn_more)
        widget.installEventFilter(self)

    @staticmethod
    def _resolve(value: Callable[[], str] | str) -> str:
        try:
            return value() if callable(value) else str(value)
        except Exception:
            return ""

    def _show_pending(self) -> None:
        widget = self._widget
        if widget is None or not widget.isVisible():
            return
        text = self._resolve(self._text).strip()
        if not text:
            return
        self._popup.set_text(text, self._more)
        self._popup.follow(widget)
        # Beside the control, never over it: on a narrow panel a cursor-anchored
        # tooltip covers the very field it describes.
        self._popup.show_for(widget, width=270, max_height=180)
        self._popup.raise_()

    def hide(self) -> None:
        self._timer.stop()
        try:
            self._popup.hide()
        except RuntimeError:
            # Qt may have destroyed the tooltip during app teardown while the
            # singleton still receives Leave/Hide events.
            pass

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if not isinstance(obj, QWidget):
            return False
        kind = event.type()
        if kind in (QEvent.Type.Enter, QEvent.Type.HoverEnter):
            text = obj.property("_rc_kit_tooltip")
            if text is None:
                return False
            self._widget = obj
            self._text = text
            self._more = str(obj.property("_rc_kit_tooltip_more") or "")
            if str(self._resolve(text)).strip():
                self._timer.start()
            return False
        if kind in (QEvent.Type.Leave, QEvent.Type.HoverLeave,
                    QEvent.Type.MouseButtonPress,
                    QEvent.Type.Wheel):
            if obj is self._widget or event.type() == QEvent.Type.Wheel:
                self.hide()
            return False
        if kind == QEvent.Type.ToolTip:
            text = obj.property("_rc_kit_tooltip")
            if text is None:
                return False
            value = self._resolve(text).strip()
            if not value:
                return True
            self._popup.set_text(
                value, str(obj.property("_rc_kit_tooltip_more") or ""))
            self._popup.follow(obj)
            self._popup.show_for(obj, width=270, max_height=180)
            return True
        if kind in (QEvent.Type.Hide, QEvent.Type.WindowDeactivate,
                    QEvent.Type.FocusOut):
            if obj is self._widget:
                self.hide()
        return False


def attach_tooltip(widget: QWidget, text: Callable[[], str] | str,
                   learn_more: str = "") -> None:
    """Attach the kit tooltip to ``widget`` (idempotent)."""
    if widget.property("_rc_kit_tooltip_installed"):
        return
    widget.setProperty("_rc_kit_tooltip_installed", True)
    TooltipManager.instance().attach(widget, text, learn_more)


__all__ = [
    "PopupSurface", "TooltipManager", "attach_tooltip", "tooltip_position",
]
