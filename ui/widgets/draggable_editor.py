"""
ui/widgets/draggable_editor.py

Drag-and-drop overlay for the theme designer.
Overlays transparent, draggable/resizable rectangles on top of a 16:9 viewport.
Coordinates are virtual 1920x1080, scaled to/from screen space.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QPushButton,
    QLineEdit, QComboBox, QScrollArea, QSizePolicy, QColorDialog,
    QCheckBox,
)
from PyQt6.QtCore import Qt, pyqtSignal, QRect, QPoint
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QFont

from ui.styles import (
    SLATE_950, SLATE_900, SLATE_800, SLATE_700, SLATE_600,
    SLATE_500, SLATE_400, WHITE, BLUE_500,
)
from ui.widgets.aspect_ratio import AspectRatioWidget

# ─── Constants ────────────────────────────────────────────────────────────────

VIRTUAL_W = 1920
VIRTUAL_H = 1080
MIN_HANDLE_W = 100
MIN_HANDLE_H = 40
CORNER_SIZE = 10
DEFAULT_CONTAINERS = {
    "text": {
        "x": 960, "y": 440, "w": 1200, "h": 400,
        "font_family": "'Nunito', sans-serif",
        "font_size": "44px",
        "font_weight": 700,
        "color": "#ffffff",
        "visible": True,
    },
    "reference": {
        "x": 960, "y": 760, "w": 800, "h": 120,
        "font_family": "'Nunito', sans-serif",
        "font_size": "34px",
        "font_weight": 500,
        "color": "#cccccc",
        "visible": True,
    },
    "translation": {
        "x": 960, "y": 840, "w": 800, "h": 80,
        "font_family": "'Nunito', sans-serif",
        "font_size": "28px",
        "font_weight": 400,
        "color": "#999999",
        "visible": True,
    },
}

# ─── Panel Styles ─────────────────────────────────────────────────────────────

_INPUT_STYLE = (
    "background: rgba(0,0,0,0.3);"
    "border: 1px solid rgba(255,255,255,0.08);"
    "border-radius: 4px;"
    "padding: 2px 6px;"
    "color: #f8fafc;"
    "font-size: 10px;"
)

_LABEL_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #64748b;"
    "font-size: 10px;"
    "font-weight: 600;"
    "text-transform: uppercase;"
)

_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0,0,0,0.3);"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 4px;"
    "  padding: 2px 6px;"
    "  color: #f8fafc;"
    "  font-size: 10px;"
    "}"
    "QComboBox::drop-down {"
    "  border: none;"
    "  width: 14px;"
    "}"
    "QComboBox QAbstractItemView {"
    "  background: #1e293b;"
    "  color: #f8fafc;"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  selection-background-color: rgba(59,130,246,0.3);"
    "}"
)

_PANEL_STYLE = (
    "QFrame {"
    "  background: rgba(15, 23, 42, 0.6);"
    "  border-left: 1px solid rgba(255, 255, 255, 0.06);"
    "}"
)

_SECTION_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #475569;"
    "font-size: 9px;"
    "font-weight: 700;"
    "text-transform: uppercase;"
    "letter-spacing: 1px;"
)


# ─── DragHandle ───────────────────────────────────────────────────────────────


class DragHandle(QWidget):
    """A single draggable element rectangle on the overlay."""

    position_changed = pyqtSignal(str, float, float)
    size_changed = pyqtSignal(str, float, float)
    selected = pyqtSignal(str)

    CORNERS = {"tl", "tr", "bl", "br"}

    def __init__(self, key: str, label: str, parent=None):
        super().__init__(parent)
        self._key = key
        self._label = label
        self._vx = 960.0
        self._vy = 540.0
        self._vw = 400.0
        self._vh = 200.0
        self._selected = False
        self._dragging = False
        self._resizing = False
        self._resize_corner: str = ""
        self._drag_start: QPoint = QPoint()
        self._drag_start_vx = 0.0
        self._drag_start_vy = 0.0
        self._drag_start_vw = 0.0
        self._drag_start_vh = 0.0

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    @property
    def key(self) -> str:
        return self._key

    @property
    def virtual_x(self) -> float:
        return self._vx

    @property
    def virtual_y(self) -> float:
        return self._vy

    @property
    def virtual_w(self) -> float:
        return self._vw

    @property
    def virtual_h(self) -> float:
        return self._vh

    @property
    def is_selected(self) -> bool:
        return self._selected

    def set_virtual_pos(self, vx: float, vy: float):
        self._vx = max(0, min(VIRTUAL_W, vx))
        self._vy = max(0, min(VIRTUAL_H, vy))

    def set_virtual_size(self, vw: float, vh: float):
        self._vw = max(MIN_HANDLE_W, vw)
        self._vh = max(MIN_HANDLE_H, vh)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def _corner_hit_test(self, pos: QPoint) -> str:
        w, h = self.width(), self.height()
        m = 4
        cx = [0, w]
        cy = [0, h]
        corners = [
            ("tl", 0, 0),
            ("tr", w, 0),
            ("bl", 0, h),
            ("br", w, h),
        ]
        for name, cxx, cyy in corners:
            if abs(pos.x() - cxx) <= CORNER_SIZE + m and abs(pos.y() - cyy) <= CORNER_SIZE + m:
                return name
        return ""

    def _resize_cursor_for_corner(self, corner: str):
        cursors = {
            "tl": Qt.CursorShape.SizeFDiagCursor,
            "tr": Qt.CursorShape.SizeBDiagCursor,
            "bl": Qt.CursorShape.SizeBDiagCursor,
            "br": Qt.CursorShape.SizeFDiagCursor,
        }
        self.setCursor(cursors.get(corner, Qt.CursorShape.SizeAllCursor))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        corner = self._corner_hit_test(event.pos())
        if corner:
            self._resizing = True
            self._resize_corner = corner
            self._drag_start = event.globalPosition().toPoint()
            self._drag_start_vx = self._vx
            self._drag_start_vy = self._vy
            self._drag_start_vw = self._vw
            self._drag_start_vh = self._vh
        else:
            self._dragging = True
            self._drag_start = event.globalPosition().toPoint()
            self._drag_start_vx = self._vx
            self._drag_start_vy = self._vy

        self.selected.emit(self._key)

    def mouseMoveEvent(self, event):
        if self._dragging:
            overlay = self.parentWidget()
            if not overlay:
                return
            scale = _get_scale(overlay)
            if scale <= 0:
                return
            dx_screen = event.globalPosition().toPoint().x() - self._drag_start.x()
            dy_screen = event.globalPosition().toPoint().y() - self._drag_start.y()
            new_vx = self._drag_start_vx + dx_screen / scale
            new_vy = self._drag_start_vy + dy_screen / scale
            hw = self._vw / 2
            hh = self._vh / 2
            new_vx = max(hw, min(VIRTUAL_W - hw, new_vx))
            new_vy = max(hh, min(VIRTUAL_H - hh, new_vy))
            if new_vx != self._vx or new_vy != self._vy:
                self._vx = new_vx
                self._vy = new_vy
                self.position_changed.emit(self._key, self._vx, self._vy)
                self.update()
                if overlay.parentWidget():
                    _position_from_virtual(self, overlay)

        elif self._resizing:
            overlay = self.parentWidget()
            if not overlay:
                return
            scale = _get_scale(overlay)
            if scale <= 0:
                return
            dx_screen = event.globalPosition().toPoint().x() - self._drag_start.x()
            dy_screen = event.globalPosition().toPoint().y() - self._drag_start.y()
            dx_v = dx_screen / scale
            dy_v = dy_screen / scale

            new_vx = self._drag_start_vx
            new_vy = self._drag_start_vy
            new_vw = self._drag_start_vw
            new_vh = self._drag_start_vh

            corner = self._resize_corner
            if "r" in corner:
                new_vw = self._drag_start_vw + dx_v
            elif "l" in corner:
                new_vw = self._drag_start_vw - dx_v
                new_vx = self._drag_start_vx + dx_v / 2
            if "b" in corner:
                new_vh = self._drag_start_vh + dy_v
            elif "t" in corner:
                new_vh = self._drag_start_vh - dy_v
                new_vy = self._drag_start_vy + dy_v / 2

            new_vw = max(MIN_HANDLE_W, min(VIRTUAL_W, new_vw))
            new_vh = max(MIN_HANDLE_H, min(VIRTUAL_H, new_vh))

            hw = new_vw / 2
            hh = new_vh / 2
            new_vx = max(hw, min(VIRTUAL_W - hw, new_vx))
            new_vy = max(hh, min(VIRTUAL_H - hh, new_vy))

            if new_vw != self._vw or new_vh != self._vh:
                self._vw = new_vw
                self._vh = new_vh
                self.size_changed.emit(self._key, self._vw, self._vh)
            if new_vx != self._vx or new_vy != self._vy:
                self._vx = new_vx
                self._vy = new_vy
                self.position_changed.emit(self._key, self._vx, self._vy)
            self.update()
            if overlay.parentWidget():
                _position_from_virtual(self, overlay)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._dragging:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            self._dragging = False
            self._resizing = False
            self._resize_corner = ""
            if self._dragging or self._resizing:
                self.selected.emit(self._key)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        if self._selected:
            pen = QPen(QColor(BLUE_500), 2)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(59, 130, 246, 20)))
            painter.drawRect(0, 0, w - 1, h - 1)

            for cx, cy in [(0, 0), (w - CORNER_SIZE, 0),
                           (0, h - CORNER_SIZE), (w - CORNER_SIZE, h - CORNER_SIZE)]:
                painter.setBrush(QBrush(QColor(BLUE_500)))
                painter.setPen(QPen(QColor(255, 255, 255, 180), 1))
                painter.drawRect(cx, cy, CORNER_SIZE - 1, CORNER_SIZE - 1)

            painter.setPen(QPen(QColor(255, 255, 255, 200), 1))
            painter.setFont(QFont("Nunito", 9, QFont.Weight.Bold))
            text_rect = QRect(6, 4, w - 12, 18)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._label)
        else:
            pen = QPen(QColor(255, 255, 255, 50), 1, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QBrush(QColor(255, 255, 255, 8)))
            painter.drawRect(0, 0, w - 1, h - 1)

            painter.setPen(QPen(QColor(255, 255, 255, 80), 1))
            painter.setFont(QFont("Nunito", 9))
            text_rect = QRect(6, 4, w - 12, 18)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self._label)

        painter.end()


# ─── Overlay Helpers ──────────────────────────────────────────────────────────


def _get_scale(overlay: QWidget) -> float:
    pw = overlay.width()
    ph = overlay.height()
    if pw <= 0 or ph <= 0:
        return 1.0
    return min(pw / VIRTUAL_W, ph / VIRTUAL_H)


def _position_from_virtual(handle: DragHandle, overlay: QWidget):
    scale = _get_scale(overlay)
    hw = handle.virtual_w / 2
    hh = handle.virtual_h / 2
    sx = int((handle.virtual_x - hw) * scale)
    sy = int((handle.virtual_y - hh) * scale)
    sw = max(1, int(handle.virtual_w * scale))
    sh = max(1, int(handle.virtual_h * scale))
    handle.setGeometry(sx, sy, sw, sh)


# ─── Properties Panel Rows ────────────────────────────────────────────────────


class _PropRow(QWidget):
    """Label + QLineEdit combo row."""

    value_changed = pyqtSignal(str)

    def __init__(self, label_text: str, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._input = QLineEdit()
        self._input.setFixedHeight(22)
        self._input.setPlaceholderText(placeholder)
        self._input.setStyleSheet(_INPUT_STYLE)
        self._input.textChanged.connect(lambda t: self.value_changed.emit(t))
        layout.addWidget(self._input, 1)

    def set_value(self, value: str):
        self._input.blockSignals(True)
        self._input.setText(str(value) if value is not None else "")
        self._input.blockSignals(False)

    def get_value(self) -> str:
        return self._input.text()


class _PropFontRow(QWidget):
    """Label + QComboBox with font family options."""

    value_changed = pyqtSignal(str)

    FONTS = [
        "'Nunito', sans-serif",
        "'DM Sans', sans-serif",
        "Georgia, serif",
        "'Times New Roman', serif",
    ]

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedHeight(22)
        self._combo.addItems(self.FONTS)
        self._combo.setStyleSheet(_COMBO_STYLE)
        self._combo.currentTextChanged.connect(lambda t: self.value_changed.emit(t))
        layout.addWidget(self._combo, 1)

    def set_value(self, value: str):
        self._combo.blockSignals(True)
        idx = self._combo.findText(value)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        else:
            self._combo.setCurrentText(value)
        self._combo.blockSignals(False)

    def get_value(self) -> str:
        return self._combo.currentText()


class _PropWeightRow(QWidget):
    """Label + QComboBox with font weight options."""

    value_changed = pyqtSignal(int)

    WEIGHTS = [
        ("Regular (400)", 400),
        ("Medium (500)", 500),
        ("Semi Bold (600)", 600),
        ("Bold (700)", 700),
        ("Extra Bold (800)", 800),
    ]

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._combo = QComboBox()
        self._combo.setFixedHeight(22)
        for label, _ in self.WEIGHTS:
            self._combo.addItem(label)
        self._combo.setStyleSheet(_COMBO_STYLE)
        self._combo.currentIndexChanged.connect(self._on_changed)
        layout.addWidget(self._combo, 1)

    def _on_changed(self, index: int):
        if 0 <= index < len(self.WEIGHTS):
            self.value_changed.emit(self.WEIGHTS[index][1])

    def set_value(self, value: int):
        self._combo.blockSignals(True)
        for i, (_, w) in enumerate(self.WEIGHTS):
            if w == value:
                self._combo.setCurrentIndex(i)
                break
        self._combo.blockSignals(False)

    def get_value(self) -> int:
        idx = self._combo.currentIndex()
        if 0 <= idx < len(self.WEIGHTS):
            return self.WEIGHTS[idx][1]
        return 400


class _PropColorRow(QWidget):
    """Label + color swatch + hex text input."""

    value_changed = pyqtSignal(str)

    def __init__(self, label_text: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(24)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(6)

        lbl = QLabel(label_text.upper())
        lbl.setFixedWidth(56)
        lbl.setStyleSheet(_LABEL_STYLE)
        layout.addWidget(lbl)

        self._swatch = QFrame()
        self._swatch.setFixedSize(22, 22)
        self._swatch.setCursor(Qt.CursorShape.PointingHandCursor)
        self._swatch.setStyleSheet(
            "background: #ffffff;"
            "border: 1px solid rgba(255,255,255,0.15);"
            "border-radius: 3px;"
        )
        self._swatch.mousePressEvent = lambda _: self._open_picker()
        layout.addWidget(self._swatch)

        self._hex = QLineEdit()
        self._hex.setFixedHeight(22)
        self._hex.setPlaceholderText("#000000")
        self._hex.setStyleSheet(_INPUT_STYLE)
        self._hex.textChanged.connect(self._on_hex_changed)
        self._hex.editingFinished.connect(self._on_hex_finished)
        layout.addWidget(self._hex, 1)

    def _open_picker(self):
        current = QColor(self._hex.text() if self._hex.text() else "#ffffff")
        dialog = QColorDialog(current, self)
        dialog.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, True)
        dialog.setWindowTitle("Select Color")
        if dialog.exec():
            c = dialog.currentColor()
            if c.alpha() < 255:
                hex_str = f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha()})"
            else:
                hex_str = c.name()
            self._hex.setText(hex_str)
            self._update_swatch(hex_str)

    def _update_swatch(self, color_str: str):
        if color_str.startswith("rgba"):
            parts = color_str.replace("rgba(", "").replace(")", "").split(",")
            r, g, b = int(parts[0]), int(parts[1]), int(parts[2])
            alpha = int(parts[3]) if len(parts) > 3 else 255
            if alpha < 255:
                self._swatch.setStyleSheet(
                    f"background: rgba({r},{g},{b},{alpha / 255:.2f});"
                    "border: 1px solid rgba(255,255,255,0.15);"
                    "border-radius: 3px;"
                )
            else:
                self._swatch.setStyleSheet(
                    f"background: #{r:02x}{g:02x}{b:02x};"
                    "border: 1px solid rgba(255,255,255,0.15);"
                    "border-radius: 3px;"
                )
        else:
            self._swatch.setStyleSheet(
                f"background: {color_str};"
                "border: 1px solid rgba(255,255,255,0.15);"
                "border-radius: 3px;"
            )

    def _on_hex_changed(self, text: str):
        self._update_swatch(text)

    def _on_hex_finished(self):
        self.value_changed.emit(self._hex.text())

    def set_value(self, value: str):
        self._hex.blockSignals(True)
        self._hex.setText(value)
        self._update_swatch(value)
        self._hex.blockSignals(False)

    def get_value(self) -> str:
        return self._hex.text()


# ─── DraggableEditor ──────────────────────────────────────────────────────────


class DraggableEditor(QWidget):
    """Main editor widget containing the overlay and properties panel."""

    containers_changed = pyqtSignal(dict)

    ELEMENTS = [
        ("text", "Text"),
        ("reference", "Reference"),
        ("translation", "Translation"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._containers: dict = {}
        self._loading = False
        self._active_key = "text"

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Left: viewport frame + overlay ──
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        self._viewport = QFrame()
        self._viewport.setStyleSheet(
            "QFrame { background: #000000; border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; }"
        )

        self._overlay = QWidget(self._viewport)
        self._overlay.setStyleSheet("background: transparent;")
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._overlay.setMouseTracking(True)

        # Wrap viewport in AspectRatioWidget so it stays 16:9
        self._ar = AspectRatioWidget(
            self._viewport, aspect_ratio=16.0 / 9.0,
            min_width=200, max_width=1920
        )
        left_layout.addWidget(self._ar, 1)
        main_layout.addWidget(left, 1)

        # ── Right: properties panel (280px) ──
        self._props_panel = QFrame()
        self._props_panel.setFixedWidth(280)
        self._props_panel.setStyleSheet(_PANEL_STYLE)

        props_scroll = QScrollArea()
        props_scroll.setWidgetResizable(True)
        props_scroll.setFrameShape(QFrame.Shape.NoFrame)
        props_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        props_scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical { background: transparent; width: 5px; }"
            "QScrollBar::handle:vertical {"
            "  background: rgba(255,255,255,0.1);"
            "  border-radius: 2px;"
            "}"
        )

        props_content = QWidget()
        props_content.setStyleSheet("background: transparent;")
        self._props_layout = QVBoxLayout(props_content)
        self._props_layout.setContentsMargins(12, 12, 12, 12)
        self._props_layout.setSpacing(2)
        self._props_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        props_scroll.setWidget(props_content)
        props_layout = QVBoxLayout(self._props_panel)
        props_layout.setContentsMargins(0, 0, 0, 0)
        props_layout.setSpacing(0)
        props_layout.addWidget(props_scroll)

        main_layout.addWidget(self._props_panel)

        # ── Build element handles ──
        self._handles: dict[str, DragHandle] = {}
        for key, display in self.ELEMENTS:
            handle = DragHandle(key, display, self._overlay)
            handle.position_changed.connect(self._on_position_changed)
            handle.size_changed.connect(self._on_size_changed)
            handle.selected.connect(self._on_element_selected)
            self._handles[key] = handle

        # ── Build properties panel ──
        self._build_props_panel()

        # ── Load defaults ──
        self._containers = {}
        self.load_from_theme(DEFAULT_CONTAINERS)

        # ── Connect resize ──
        self._viewport.installEventFilter(self)

    # ── Properties panel ────────────────────────────────────────────────────

    def _build_props_panel(self):
        self._prop_x = _PropRow("X", "960")
        self._prop_y = _PropRow("Y", "540")
        self._prop_w = _PropRow("W", "400")
        self._prop_h = _PropRow("H", "200")
        self._prop_font = _PropFontRow("Font")
        self._prop_size = _PropRow("Size", "44px")
        self._prop_weight = _PropWeightRow("Weight")
        self._prop_color = _PropColorRow("Color")
        self._prop_visible = QCheckBox("Visible")
        self._prop_visible.setStyleSheet(
            "QCheckBox {"
            "  color: #94a3b8;"
            "  font-size: 10px;"
            "  font-weight: 600;"
            "  spacing: 6px;"
            "}"
            "QCheckBox::indicator {"
            "  width: 14px; height: 14px;"
            "  border: 1px solid rgba(255,255,255,0.15);"
            "  border-radius: 3px;"
            "  background: rgba(0,0,0,0.3);"
            "}"
            "QCheckBox::indicator:checked {"
            "  background: #3b82f6;"
            "  border: 1px solid #3b82f6;"
            "}"
        )

        def _connect_row(row, signal_attr, slot):
            sig = getattr(row, signal_attr, None)
            if sig:
                sig.connect(slot)

        _connect_row(self._prop_x, "value_changed", self._on_prop_x_changed)
        _connect_row(self._prop_y, "value_changed", self._on_prop_y_changed)
        _connect_row(self._prop_w, "value_changed", self._on_prop_w_changed)
        _connect_row(self._prop_h, "value_changed", self._on_prop_h_changed)
        _connect_row(self._prop_font, "value_changed", self._on_prop_font_changed)
        _connect_row(self._prop_size, "value_changed", self._on_prop_size_changed)
        _connect_row(self._prop_weight, "value_changed", self._on_prop_weight_changed)
        _connect_row(self._prop_color, "value_changed", self._on_prop_color_changed)
        self._prop_visible.toggled.connect(self._on_prop_visible_toggled)

        self._props_layout.addWidget(self._section_label("POSITION"))
        self._props_layout.addWidget(self._prop_x)
        self._props_layout.addWidget(self._prop_y)
        self._props_layout.addSpacing(4)

        self._props_layout.addWidget(self._section_label("SIZE"))
        self._props_layout.addWidget(self._prop_w)
        self._props_layout.addWidget(self._prop_h)
        self._props_layout.addSpacing(4)

        self._props_layout.addWidget(self._section_label("FONT"))
        self._props_layout.addWidget(self._prop_font)
        self._props_layout.addWidget(self._prop_size)
        self._props_layout.addWidget(self._prop_weight)
        self._props_layout.addSpacing(4)

        self._props_layout.addWidget(self._section_label("COLOR"))
        self._props_layout.addWidget(self._prop_color)
        self._props_layout.addSpacing(4)

        self._props_layout.addWidget(self._section_label("OPTIONS"))
        self._props_layout.addWidget(self._prop_visible)

        self._props_layout.addStretch()

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(_SECTION_STYLE)
        return lbl

    # ── Event filter ────────────────────────────────────────────────────────

    def eventFilter(self, obj, event):
        if obj is self._viewport and event.type() in (
            event.Type.Resize, event.Type.Show, event.Type.LayoutRequest
        ):
            self._update_screen_positions()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_screen_positions()

    # ── Coordinate mapping ──────────────────────────────────────────────────

    def _update_screen_positions(self):
        for handle in self._handles.values():
            _position_from_virtual(handle, self._overlay)
        self._overlay.setGeometry(self._viewport.rect())

    # ── Load / get ──────────────────────────────────────────────────────────

    def load_from_theme(self, containers: dict):
        self._loading = True
        self._containers = {}
        for key in ("text", "reference", "translation"):
            src = containers.get(key, DEFAULT_CONTAINERS.get(key, {}))
            entry = {
                "x": src.get("x", 960.0),
                "y": src.get("y", 540.0),
                "w": src.get("w", 400.0),
                "h": src.get("h", 200.0),
                "font_family": src.get("font_family", "'Nunito', sans-serif"),
                "font_size": src.get("font_size", "44px"),
                "font_weight": src.get("font_weight", 700),
                "color": src.get("color", "#ffffff"),
                "visible": src.get("visible", True),
            }
            self._containers[key] = entry

            handle = self._handles[key]
            handle.set_virtual_pos(entry["x"], entry["y"])
            handle.set_virtual_size(entry["w"], entry["h"])

        self._update_screen_positions()
        self._select_element("text")
        self._loading = False

    def get_containers(self) -> dict:
        out = {}
        for key in ("text", "reference", "translation"):
            entry = self._containers.get(key, {})
            handle = self._handles.get(key)
            if handle:
                out[key] = {
                    "x": handle.virtual_x,
                    "y": handle.virtual_y,
                    "w": handle.virtual_w,
                    "h": handle.virtual_h,
                    "font_family": entry.get("font_family", "'Nunito', sans-serif"),
                    "font_size": entry.get("font_size", "44px"),
                    "font_weight": entry.get("font_weight", 700),
                    "color": entry.get("color", "#ffffff"),
                    "visible": entry.get("visible", True),
                }
            else:
                out[key] = dict(entry)
        return out

    # ── Selection ───────────────────────────────────────────────────────────

    def _on_element_selected(self, key: str):
        self._select_element(key)

    def _select_element(self, key: str):
        self._active_key = key
        for k, handle in self._handles.items():
            handle.set_selected(k == key)
        self._populate_props(key)

    def _populate_props(self, key: str):
        self._loading = True
        entry = self._containers.get(key, {})
        self._prop_x.set_value(str(int(entry.get("x", 960))))
        self._prop_y.set_value(str(int(entry.get("y", 540))))
        self._prop_w.set_value(str(int(entry.get("w", 400))))
        self._prop_h.set_value(str(int(entry.get("h", 200))))
        self._prop_font.set_value(entry.get("font_family", "'Nunito', sans-serif"))
        self._prop_size.set_value(entry.get("font_size", "44px"))
        self._prop_weight.set_value(entry.get("font_weight", 700))
        self._prop_color.set_value(entry.get("color", "#ffffff"))
        self._prop_visible.setChecked(entry.get("visible", True))
        self._loading = False

    # ── Position / size signals from handles ────────────────────────────────

    def _on_position_changed(self, key: str, vx: float, vy: float):
        if self._loading:
            return
        if key in self._containers:
            self._containers[key]["x"] = vx
            self._containers[key]["y"] = vy
        if key == self._active_key:
            self._prop_x.blockSignals(True)
            self._prop_y.blockSignals(True)
            self._prop_x.set_value(str(int(vx)))
            self._prop_y.set_value(str(int(vy)))
            self._prop_x.blockSignals(False)
            self._prop_y.blockSignals(False)
        self._emit_containers()

    def _on_size_changed(self, key: str, vw: float, vh: float):
        if self._loading:
            return
        if key in self._containers:
            self._containers[key]["w"] = vw
            self._containers[key]["h"] = vh
        if key == self._active_key:
            self._prop_w.blockSignals(True)
            self._prop_h.blockSignals(True)
            self._prop_w.set_value(str(int(vw)))
            self._prop_h.set_value(str(int(vh)))
            self._prop_w.blockSignals(False)
            self._prop_h.blockSignals(False)
        self._emit_containers()

    # ── Properties panel input handlers ─────────────────────────────────────

    def _on_prop_x_changed(self, text: str):
        if self._loading or self._active_key not in self._containers:
            return
        try:
            val = float(text)
        except ValueError:
            return
        handle = self._handles[self._active_key]
        handle.set_virtual_pos(val, handle.virtual_y)
        self._containers[self._active_key]["x"] = handle.virtual_x
        _position_from_virtual(handle, self._overlay)
        self._emit_containers()

    def _on_prop_y_changed(self, text: str):
        if self._loading or self._active_key not in self._containers:
            return
        try:
            val = float(text)
        except ValueError:
            return
        handle = self._handles[self._active_key]
        handle.set_virtual_pos(handle.virtual_x, val)
        self._containers[self._active_key]["y"] = handle.virtual_y
        _position_from_virtual(handle, self._overlay)
        self._emit_containers()

    def _on_prop_w_changed(self, text: str):
        if self._loading or self._active_key not in self._containers:
            return
        try:
            val = float(text)
        except ValueError:
            return
        handle = self._handles[self._active_key]
        handle.set_virtual_size(val, handle.virtual_h)
        self._containers[self._active_key]["w"] = handle.virtual_w
        _position_from_virtual(handle, self._overlay)
        self._emit_containers()

    def _on_prop_h_changed(self, text: str):
        if self._loading or self._active_key not in self._containers:
            return
        try:
            val = float(text)
        except ValueError:
            return
        handle = self._handles[self._active_key]
        handle.set_virtual_size(handle.virtual_w, val)
        self._containers[self._active_key]["h"] = handle.virtual_h
        _position_from_virtual(handle, self._overlay)
        self._emit_containers()

    def _on_prop_font_changed(self, value: str):
        if self._loading or self._active_key not in self._containers:
            return
        self._containers[self._active_key]["font_family"] = value
        self._emit_containers()

    def _on_prop_size_changed(self, value: str):
        if self._loading or self._active_key not in self._containers:
            return
        self._containers[self._active_key]["font_size"] = value
        self._emit_containers()

    def _on_prop_weight_changed(self, value: int):
        if self._loading or self._active_key not in self._containers:
            return
        self._containers[self._active_key]["font_weight"] = value
        self._emit_containers()

    def _on_prop_color_changed(self, value: str):
        if self._loading or self._active_key not in self._containers:
            return
        self._containers[self._active_key]["color"] = value
        self._emit_containers()

    def _on_prop_visible_toggled(self, checked: bool):
        if self._loading or self._active_key not in self._containers:
            return
        self._containers[self._active_key]["visible"] = checked
        handle = self._handles.get(self._active_key)
        if handle:
            handle.setVisible(checked)
        self._emit_containers()

    # ── Emit ────────────────────────────────────────────────────────────────

    def _emit_containers(self):
        if not self._loading:
            self.containers_changed.emit(self.get_containers())
