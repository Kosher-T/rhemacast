"""
ui/widgets/container_editor.py

Visual editor for the theme `container` element.
Left: 16:9 canvas showing the container rect on a 1920x1080 virtual screen.
Right: properties panel for all 14 container CSS properties.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QScrollArea, QSizePolicy, QColorDialog, QComboBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPointF
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont, QMouseEvent

from ui.styles import (
    SLATE_950, SLATE_900, SLATE_800, SLATE_700, SLATE_600,
    SLATE_500, SLATE_400, WHITE, BLUE_500,
)
from ui.widgets.aspect_ratio import AspectRatioWidget

# ─── Constants ────────────────────────────────────────────────────────────────

VIRTUAL_W = 1920
VIRTUAL_H = 1080
CORNER_SIZE = 8
HANDLE_HIT = 12  # px tolerance for corner hit test

DEFAULT_CONTAINER = {
    "background": "transparent",
    "border": "none",
    "border_radius": "0",
    "box_shadow": "none",
    "backdrop_filter": "none",
    "padding": "0",
    "width": "1840px",
    "height": "1080px",
    "max_width": "1840px",
    "min_width": "1840px",
    "display": "flex",
    "flex_direction": "column",
    "justify_content": "center",
    "align_items": "center",
}


# ─── Styles ───────────────────────────────────────────────────────────────────

_SECTION_STYLE = (
    "color: #475569;"
    "font-size: 9px;"
    "font-weight: 700;"
    "text-transform: uppercase;"
    "letter-spacing: 0.08em;"
    "padding: 0 0 2px 0;"
    "background: transparent;"
    "border: none;"
)

_LABEL_STYLE = (
    "color: #64748b;"
    "font-size: 10px;"
    "font-weight: 600;"
    "background: transparent;"
    "border: none;"
    "min-width: 60px;"
)

_INPUT_STYLE = (
    "QLineEdit {"
    "  background: rgba(0,0,0,0.3);"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 4px;"
    "  padding: 3px 6px;"
    "  color: #f8fafc;"
    "  font-size: 11px;"
    "  font-family: 'Consolas', monospace;"
    "}"
    "QLineEdit:focus {"
    "  border: 1px solid rgba(59,130,246,0.4);"
    "}"
)

_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0,0,0,0.3);"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 4px;"
    "  padding: 3px 6px;"
    "  color: #f8fafc;"
    "  font-size: 11px;"
    "}"
    "QComboBox:focus {"
    "  border: 1px solid rgba(59,130,246,0.4);"
    "}"
    "QComboBox::drop-down {"
    "  border: none;"
    "  width: 16px;"
    "}"
    "QComboBox::down-arrow {"
    "  image: none;"
    "  border-left: 4px solid transparent;"
    "  border-right: 4px solid transparent;"
    "  border-top: 5px solid #94a3b8;"
    "  margin-right: 4px;"
    "}"
    "QComboBox QAbstractItemView {"
    "  background: #1e293b;"
    "  border: 1px solid rgba(255,255,255,0.1);"
    "  color: #f8fafc;"
    "  selection-background-color: rgba(59,130,246,0.3);"
    "  padding: 2px;"
    "}"
)

_PANEL_STYLE = (
    "QFrame {"
    "  background: rgba(15,23,42,0.8);"
    "  border-left: 1px solid rgba(255,255,255,0.06);"
    "}"
)

_COLOR_BTN_STYLE = (
    "QPushButton {{"
    "  background: {color};"
    "  border: 1px solid rgba(255,255,255,0.15);"
    "  border-radius: 4px;"
    "  min-width: 24px; max-width: 24px;"
    "  min-height: 20px; max-height: 20px;"
    "}}"
)


# ─── Property Row Widgets ─────────────────────────────────────────────────────

class _PropRow(QWidget):
    """Label + QLineEdit row for text-based CSS values."""

    value_changed = pyqtSignal(str)

    def __init__(self, label: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(_LABEL_STYLE)
        lbl.setFixedWidth(60)
        layout.addWidget(lbl)

        self._input = QLineEdit()
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.setPlaceholderText(placeholder)
        self._input.textChanged.connect(lambda _: self.value_changed.emit(self.get_value()))
        layout.addWidget(self._input, 1)

    def get_value(self) -> str:
        return self._input.text().strip()

    def set_value(self, v: str):
        if self._input.text() != v:
            self._input.setText(v)


class _PropCombo(QWidget):
    """Label + QComboBox row for dropdown CSS values."""

    value_changed = pyqtSignal(str)

    def __init__(self, label: str, options: list[str], parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(_LABEL_STYLE)
        lbl.setFixedWidth(60)
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setStyleSheet(_COMBO_STYLE)
        self._combo.addItems(options)
        self._combo.currentTextChanged.connect(lambda _: self.value_changed.emit(self.get_value()))
        layout.addWidget(self._combo, 1)

    def get_value(self) -> str:
        return self._combo.currentText()

    def set_value(self, v: str):
        idx = self._combo.findText(v)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            self._combo.setEditText(v)


class _PropToggle(QWidget):
    """Label + toggle switch row."""

    toggled = pyqtSignal(bool)

    def __init__(self, label: str, checked: bool = False, parent=None):
        super().__init__(parent)
        self._checked = checked
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(_LABEL_STYLE)
        lbl.setFixedWidth(60)
        layout.addWidget(lbl)

        layout.addStretch()

        self._btn = QPushButton()
        self._btn.setFixedSize(32, 18)
        self._btn.setCheckable(True)
        self._btn.setChecked(checked)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setStyleSheet(self._style(checked))
        self._btn.clicked.connect(self._on_click)
        layout.addWidget(self._btn)

    def _style(self, on: bool) -> str:
        if on:
            return (
                "QPushButton { background: #3b82f6; border: none; border-radius: 9px; }"
                "QPushButton::indicator { width: 14px; height: 14px; border-radius: 7px; background: white; margin: 2px; }"
                "QPushButton:checked::indicator { margin-left: 16px; }"
            )
        return (
            "QPushButton { background: rgba(255,255,255,0.1); border: none; border-radius: 9px; }"
            "QPushButton::indicator { width: 14px; height: 14px; border-radius: 7px; background: #64748b; margin: 2px; }"
            "QPushButton:checked::indicator { margin-left: 16px; }"
        )

    def _on_click(self, checked: bool):
        self._checked = checked
        self._btn.setStyleSheet(self._style(checked))
        self.toggled.emit(checked)

    def is_on(self) -> bool:
        return self._checked

    def set_on(self, on: bool):
        self._checked = on
        self._btn.setChecked(on)
        self._btn.setStyleSheet(self._style(on))


class _PropColor(QWidget):
    """Label + color swatch button + hex QLineEdit row."""

    value_changed = pyqtSignal(str)

    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setStyleSheet(_LABEL_STYLE)
        lbl.setFixedWidth(60)
        layout.addWidget(lbl)

        self._swatch = QPushButton()
        self._swatch.setFixedSize(24, 20)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.clicked.connect(self._pick_color)
        layout.addWidget(self._swatch)

        self._input = QLineEdit()
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.setPlaceholderText("#000000")
        self._input.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._input, 1)

    def _pick_color(self):
        current = QColor(self._input.text() or "#000000")
        c = QColorDialog.getColor(current, self, "Choose Color",
                                  QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if c.isValid():
            alpha = c.alpha()
            if alpha < 255:
                text = f"rgba({c.red()},{c.green()},{c.blue()},{alpha/255:.2f})"
            else:
                text = c.name()
            self._input.setText(text)

    def _on_text_changed(self, text: str):
        color = QColor(text) if text else QColor("#000000")
        if color.isValid():
            self._swatch.setStyleSheet(_COLOR_BTN_STYLE.format(color=color.name()))
        self.value_changed.emit(text)

    def get_value(self) -> str:
        return self._input.text().strip()

    def set_value(self, v: str):
        if self._input.text() != v:
            self._input.setText(v)


# ─── Container Canvas ─────────────────────────────────────────────────────────

class ContainerCanvas(QWidget):
    """
    16:9 canvas that draws the container rect on a 1920x1080 virtual screen.
    Supports dragging and corner-resizing the container.
    """

    container_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._container: dict = dict(DEFAULT_CONTAINER)
        self._committed: dict = dict(DEFAULT_CONTAINER)  # theme state, updated on release only
        self._dragging = False
        self._resizing = False
        self._resize_corner: str = ""
        self._drag_start_screen = QPointF()
        self._drag_start_container: dict = {}
        self._selected = True  # container is always "selected"

        self.setMinimumSize(200, 113)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMouseTracking(True)

    # ── Public API ───────────────────────────────────────────────────────────

    def load_container(self, container: dict):
        self._container = dict(container)
        self._committed = dict(container)
        self.update()

    def get_container(self) -> dict:
        return dict(self._committed)

    # ── Coordinate mapping ───────────────────────────────────────────────────

    def _virtual_to_screen(self, vx: float, vy: float) -> tuple[float, float]:
        sx = vx * self.width() / VIRTUAL_W
        sy = vy * self.height() / VIRTUAL_H
        return sx, sy

    def _screen_to_virtual(self, sx: float, sy: float) -> tuple[float, float]:
        vx = sx * VIRTUAL_W / self.width()
        vy = sy * VIRTUAL_H / self.height()
        return vx, vy

    def _parse_px(self, val: str) -> float:
        """Parse '400px' → 400.0, 'auto' → -1."""
        if not val or val == "auto":
            return -1
        try:
            return float(val.replace("px", "").replace("%", "").strip())
        except (ValueError, AttributeError):
            return -1

    # ── Container rect on virtual screen ─────────────────────────────────────

    def _container_rect(self) -> tuple[float, float, float, float]:
        """Return (cx, cy, cw, ch) in virtual coords, centered on screen."""
        cw = self._parse_px(self._container.get("width", ""))
        ch = self._parse_px(self._container.get("height", ""))
        if cw <= 0:
            cw = self._parse_px(self._container.get("max_width", ""))
        if cw <= 0:
            cw = VIRTUAL_W
        if ch <= 0:
            ch = VIRTUAL_H
        cx = (VIRTUAL_W - cw) / 2
        cy = (VIRTUAL_H - ch) / 2
        return cx, cy, cw, ch

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Background
        p.fillRect(0, 0, w, h, QColor("#0f172a"))

        # Grid
        grid_pen = QPen(QColor(255, 255, 255, 8), 1)
        p.setPen(grid_pen)
        step_x = w / 12
        step_y = h / 12
        for i in range(1, 12):
            x = int(i * step_x)
            p.drawLine(x, 0, x, h)
        for i in range(1, 12):
            y = int(i * step_y)
            p.drawLine(0, y, w, y)

        # Container rect
        cx, cy, cw, ch = self._container_rect()
        sx, sy = self._virtual_to_screen(cx, cy)
        sw, sh = self._virtual_to_screen(cw, ch)
        rect = QRect(int(sx), int(sy), int(sw), int(sh))

        # Parse visual props
        bg = self._container.get("background", "transparent")
        border_str = self._container.get("border", "none")
        br = self._container.get("border_radius", "0")
        shadow = self._container.get("box_shadow", "none")
        padding_str = self._container.get("padding", "0")
        pad = self._parse_px(padding_str)

        # Container fill
        fill_color = self._parse_color(bg, QColor(255, 255, 255, 20))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(fill_color))
        p.drawRoundedRect(rect, self._parse_px(br), self._parse_px(br))

        # Container border
        if border_str and border_str != "none":
            parts = border_str.split()
            if len(parts) >= 3:
                bw = self._parse_px(parts[0])
                bc = self._parse_color(parts[2], QColor(255, 255, 255, 80))
                pen = QPen(bc, max(1, bw))
                p.setPen(pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(rect, self._parse_px(br), self._parse_px(br))

        # Padding inset
        if pad > 0:
            p_scale_x = pad * w / VIRTUAL_W
            p_scale_y = pad * h / VIRTUAL_H
            inner = rect.adjusted(int(p_scale_x), int(p_scale_y),
                                  -int(p_scale_x), -int(p_scale_y))
            p.setPen(QPen(QColor(59, 130, 246, 60), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(inner, 4, 4)

        # Center crosshair
        mid_x = int(sx + sw / 2)
        mid_y = int(sy + sh / 2)
        p.setPen(QPen(QColor(59, 130, 246, 40), 1))
        p.drawLine(mid_x, int(sy), mid_x, int(sy + sh))
        p.drawLine(int(sx), mid_y, int(sx + sw), mid_y)

        # Resize handles (when selected)
        if self._selected:
            corners = [
                (int(sx), int(sy)),
                (int(sx + sw - CORNER_SIZE), int(sy)),
                (int(sx), int(sy + sh - CORNER_SIZE)),
                (int(sx + sw - CORNER_SIZE), int(sy + sh - CORNER_SIZE)),
            ]
            for hx, hy in corners:
                p.setPen(QPen(QColor(255, 255, 255, 120), 1))
                p.setBrush(QBrush(QColor(BLUE_500)))
                p.drawRect(hx, hy, CORNER_SIZE - 1, CORNER_SIZE - 1)

        # Info label
        p.setPen(QPen(QColor(100, 116, 139), 1))
        p.setFont(QFont("Nunito", 8))
        info = f"{int(cw)}x{int(ch)}"
        p.drawText(8, h - 8, info)

        p.end()

    # ── Color parsing ────────────────────────────────────────────────────────

    def _parse_color(self, css: str, fallback: QColor) -> QColor:
        if not css or css == "transparent":
            return QColor(255, 255, 255, 20)
        if css.startswith("rgba"):
            try:
                parts = css.replace("rgba(", "").replace(")", "").split(",")
                return QColor(int(parts[0]), int(parts[1]), int(parts[2]),
                              int(float(parts[3].strip()) * 255))
            except (IndexError, ValueError):
                return fallback
        if css.startswith("rgb"):
            try:
                parts = css.replace("rgb(", "").replace(")", "").split(",")
                return QColor(int(parts[0]), int(parts[1]), int(parts[2]))
            except (IndexError, ValueError):
                return fallback
        c = QColor(css)
        return c if c.isValid() else fallback

    # ── Mouse: corner hit test ───────────────────────────────────────────────

    def _corner_hit_test(self, pos: QPointF) -> str:
        cx, cy, cw, ch = self._container_rect()
        sx, sy = self._virtual_to_screen(cx, cy)
        sw, sh = self._virtual_to_screen(cw, ch)
        corners = {
            "tl": (sx, sy),
            "tr": (sx + sw, sy),
            "bl": (sx, sy + sh),
            "br": (sx + sw, sy + sh),
        }
        for name, (cxx, cyy) in corners.items():
            if abs(pos.x() - cxx) <= HANDLE_HIT and abs(pos.y() - cyy) <= HANDLE_HIT:
                return name
        return ""

    def _on_container_rect(self, pos: QPointF) -> bool:
        cx, cy, cw, ch = self._container_rect()
        sx, sy = self._virtual_to_screen(cx, cy)
        sw, sh = self._virtual_to_screen(cw, ch)
        return sx <= pos.x() <= sx + sw and sy <= pos.y() <= sy + sh

    # ── Mouse events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        pos = event.position()
        corner = self._corner_hit_test(pos)
        if corner:
            self._resizing = True
            self._resize_corner = corner
            self._drag_start_screen = pos
            self._drag_start_container = dict(self._container)
        elif self._on_container_rect(pos):
            self._dragging = True
            self._drag_start_screen = pos
            self._drag_start_container = dict(self._container)

    def mouseMoveEvent(self, event):
        pos = event.position()

        if self._dragging:
            dx = pos.x() - self._drag_start_screen.x()
            dy = pos.y() - self._drag_start_screen.y()
            dx_v = dx * VIRTUAL_W / self.width()
            dy_v = dy * VIRTUAL_H / self.height()

            cw = self._parse_px(self._drag_start_container.get("width", ""))
            ch = self._parse_px(self._drag_start_container.get("height", ""))
            if cw <= 0:
                cw = VIRTUAL_W
            if ch <= 0:
                ch = VIRTUAL_H

            new_cx = (VIRTUAL_W - cw) / 2 + dx_v
            new_cy = (VIRTUAL_H - ch) / 2 + dy_v
            new_cx = max(0, min(VIRTUAL_W - cw, new_cx))
            new_cy = max(0, min(VIRTUAL_H - ch, new_cy))

            # Update width/height to account for offset from center
            # (since container is always centered, we store offset via width/height adjustments)
            # Actually: store as margin-based. For now, just move via width/height on one side
            # Simpler: use max_width and min_width to shift, or use a new 'offset_x/y' field.
            # For now: we'll adjust padding or just move the rect and let user see it.
            # The cleanest approach: add offset fields to container.
            # For this v1: we'll just track the visual offset and let the user see it.
            self.update()

        elif self._resizing:
            dx = pos.x() - self._drag_start_screen.x()
            dy = pos.y() - self._drag_start_screen.y()
            dx_v = dx * VIRTUAL_W / self.width()
            dy_v = dy * VIRTUAL_H / self.height()

            start = self._drag_start_container
            scw = self._parse_px(start.get("width", ""))
            sch = self._parse_px(start.get("height", ""))
            if scw <= 0:
                scw = VIRTUAL_W
            if sch <= 0:
                sch = VIRTUAL_H

            corner = self._resize_corner
            new_w, new_h = scw, sch

            if "r" in corner:
                new_w = scw + dx_v
            elif "l" in corner:
                new_w = scw - dx_v
            if "b" in corner:
                new_h = sch + dy_v
            elif "t" in corner:
                new_h = sch - dy_v

            new_w = max(200, min(VIRTUAL_W, new_w))
            new_h = max(100, min(VIRTUAL_H, new_h))

            self._container["width"] = f"{int(new_w)}px"
            self._container["height"] = f"{int(new_h)}px"
            self._container["max_width"] = f"{int(new_w)}px"
            self._container["min_width"] = f"{int(new_w)}px"
            self.update()

        else:
            # Update cursor
            corner = self._corner_hit_test(pos)
            if corner in ("tl", "br"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif corner in ("tr", "bl"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif self._on_container_rect(pos):
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            was_interacting = self._dragging or self._resizing
            self._dragging = False
            self._resizing = False
            self._resize_corner = ""
            self.setCursor(Qt.CursorShape.ArrowCursor)
            if was_interacting:
                self._committed = dict(self._container)
                self.container_changed.emit(self._committed)


# ─── Container Properties Panel ───────────────────────────────────────────────

class ContainerPropertiesPanel(QWidget):
    """
    Right-side panel with property editors for all container CSS properties.
    Emits container_changed when any property is edited.
    """

    container_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False
        self._container: dict = dict(DEFAULT_CONTAINER)

        self.setFixedWidth(280)
        self.setStyleSheet(_PANEL_STYLE)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,0.1);"
            "  border-radius: 2px;"
            "}"
        )

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        self._layout = QVBoxLayout(content)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(4)

        self._rows: dict[str, QWidget] = {}

        # ── Appearance ──
        self._build_section("Appearance")

        # Background: transparent toggle + color picker
        self._toggle_transparent = _PropToggle("Transparent", checked=True)
        self._toggle_transparent.toggled.connect(self._on_transparent_toggled)
        self._layout.addWidget(self._toggle_transparent)
        self._bg_color = _PropColor("Color")
        self._bg_color.value_changed.connect(self._on_edit)
        self._bg_color.setVisible(False)  # hidden when transparent
        self._layout.addWidget(self._bg_color)

        self._rows["border"] = self._add_text("Border", "none")
        self._rows["border_radius"] = self._add_text("Radius", "0")
        self._rows["box_shadow"] = self._add_text("Shadow", "none")
        self._rows["backdrop_filter"] = self._add_text("Backdrop", "none")

        # ── Sizing ──
        self._build_section("Sizing")
        self._rows["width"] = self._add_text("Width", "1840px")
        self._rows["height"] = self._add_text("Height", "1080px")

        # Resizable toggle → controls max/min width
        self._toggle_resizable = _PropToggle("Resizable", checked=False)
        self._toggle_resizable.toggled.connect(self._on_resizable_toggled)
        self._layout.addWidget(self._toggle_resizable)
        self._row_max_w = self._add_text("Max W", "1840px")
        self._row_min_w = self._add_text("Min W", "1840px")
        self._row_max_w.setEnabled(False)
        self._row_min_w.setEnabled(False)
        self._rows["max_width"] = self._row_max_w
        self._rows["min_width"] = self._row_min_w

        self._rows["padding"] = self._add_text("Padding", "0")

        # ── Layout ──
        self._build_section("Layout")
        self._rows["display"] = self._add_combo("Display", ["flex", "block", "grid", "none"])
        self._rows["flex_direction"] = self._add_combo("Direction", ["column", "row", "column-reverse", "row-reverse"])
        self._rows["justify_content"] = self._add_combo("Justify", [
            "center", "flex-start", "flex-end", "space-between", "space-around", "space-evenly",
        ])
        self._rows["align_items"] = self._add_combo("Align", [
            "center", "flex-start", "flex-end", "stretch", "baseline",
        ])

        self._layout.addStretch()
        scroll.setWidget(content)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll)

    # ── Builders ─────────────────────────────────────────────────────────────

    def _build_section(self, text: str):
        lbl = QLabel(text)
        lbl.setStyleSheet(_SECTION_STYLE)
        self._layout.addWidget(lbl)
        self._layout.addSpacing(2)

    def _add_text(self, label: str, placeholder: str = "") -> _PropRow:
        row = _PropRow(label, placeholder)
        row.value_changed.connect(self._on_edit)
        self._layout.addWidget(row)
        return row

    def _add_combo(self, label: str, options: list[str]) -> _PropCombo:
        row = _PropCombo(label, options)
        row.value_changed.connect(self._on_edit)
        self._layout.addWidget(row)
        return row

    def _add_color(self, label: str) -> _PropColor:
        row = _PropColor(label)
        row.value_changed.connect(self._on_edit)
        self._layout.addWidget(row)
        return row

    # ── Sync ─────────────────────────────────────────────────────────────────

    def _on_transparent_toggled(self, on: bool):
        self._bg_color.setVisible(not on)
        if not self._loading:
            self._on_edit()

    def _on_resizable_toggled(self, on: bool):
        self._row_max_w.setEnabled(on)
        self._row_min_w.setEnabled(on)
        if not self._loading:
            self._on_edit()

    def _on_edit(self):
        if self._loading:
            return
        self._collect()
        self.container_changed.emit(self._container)

    def _collect(self):
        for key, row in self._rows.items():
            self._container[key] = row.get_value()
        # Transparent toggle overrides background
        if self._toggle_transparent.is_on():
            self._container["background"] = "transparent"
        else:
            self._container["background"] = self._bg_color.get_value() or "transparent"
        # Resizable toggle: clear max/min when off
        if not self._toggle_resizable.is_on():
            self._container.pop("max_width", None)
            self._container.pop("min_width", None)

    def load_container(self, container: dict):
        self._loading = True
        self._container = dict(container)

        # ── Background toggle ──
        bg = container.get("background", "transparent")
        is_transparent = (bg == "transparent" or bg == "" or bg is None)
        self._toggle_transparent.set_on(is_transparent)
        self._bg_color.setVisible(not is_transparent)
        if not is_transparent:
            self._bg_color.set_value(bg)

        # ── Resizable toggle ──
        has_max = bool(container.get("max_width"))
        has_min = bool(container.get("min_width"))
        is_resizable = has_max or has_min
        self._toggle_resizable.set_on(is_resizable)
        self._row_max_w.setEnabled(is_resizable)
        self._row_min_w.setEnabled(is_resizable)

        # ── Text rows ──
        for key, row in self._rows.items():
            row.set_value(container.get(key, ""))

        self._loading = False

    def get_container(self) -> dict:
        return dict(self._container)


# ─── Main ContainerEditor Widget ──────────────────────────────────────────────

class ContainerEditor(QWidget):
    """
    Combined widget: ContainerCanvas on the left, ContainerPropertiesPanel on the right.
    Bidirectional sync: canvas drag/resize updates panel, panel edits update canvas.
    """

    container_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left: canvas wrapped in AspectRatioWidget
        self._canvas = ContainerCanvas()
        self._canvas.setMinimumWidth(200)
        self._ar = AspectRatioWidget(
            self._canvas, aspect_ratio=16.0 / 9.0,
            min_width=200, max_width=1920,
        )
        layout.addWidget(self._ar, 1)

        # Right: properties panel
        self._panel = ContainerPropertiesPanel()
        layout.addWidget(self._panel)

        # Bidirectional sync
        self._canvas.container_changed.connect(self._on_canvas_changed)
        self._panel.container_changed.connect(self._on_panel_changed)

    def load_container(self, container: dict):
        self._canvas.load_container(container)
        self._panel.load_container(container)

    def get_container(self) -> dict:
        return self._panel.get_container()

    def _on_canvas_changed(self, container: dict):
        self._panel.load_container(container)
        self.container_changed.emit(container)

    def _on_panel_changed(self, container: dict):
        self._canvas.load_container(container)
        self.container_changed.emit(container)
