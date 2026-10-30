"""
ui/widgets/lite_designer/format_ribbon.py

Word-processor ribbon for the Lite Designer freeform page.

Row 1 (always visible): font · size −/+ · B I S U · outline + color ·
    text color · clear · undo redo
Color section (below row 1, inline child only): quick swatches + HSV wheel +
    value slider + hex + Apply/Close; swatches/hex apply at once, wheel and
    value stage a pending color until Apply.
Row 2 (collapsible "¶"): alignment · spacing · bullets · numbers ·
    super/sub · UPPER/lower · RTL/LTR · HR

Operates on the active QTextEdit (set_editor). All character formatting goes
through _merge() so explicit txt props (UL_PROP/SO_PROP/OUTLINE_PROP) stay
consistent — see rich_txt module docstring for the contract.
"""

from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
                             QComboBox, QFontComboBox, QMenu, QLineEdit,
                             QGridLayout, QLabel, QSlider,
                             QTextEdit, QSizePolicy, QSpinBox)
from PyQt6.QtGui import (QTextCharFormat, QTextCursor, QTextBlockFormat,
                         QFont, QColor, QBrush, QTextFormat, QAction,
                         QImage, QPainter, QPen)
from PyQt6.QtCore import Qt, pyqtSignal
from ui import dialogs
from ui.popups import install_combo, menu_qss
import math
from contextlib import contextmanager

from ui.widgets.lite_designer.rich_txt import (
    OUTLINE_PROP, OUTLINE_OFF, SHADOW_PROP, SHADOW_OFF,
    UL_PROP, SO_PROP, SIZE_PROP, COLOR_PROP,
    CASE_PROP,
    FONT_PROP, ALIGN_PROP, DIR_PROP, insert_hr_at)
from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, SLATE_300, SLATE_600,
    BG_RAISED, ACCENT, SELECTION_BG, SELECTION_BORDER, CHROME_SOFT,
    TEXT_SELECTION,
    TEXT_FAINT, ACCENT_TEXT,
)

_PT_PER_PX = 0.75
_SIZES_PX = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 44, 54, 62, 72]
_SPACINGS = [("Single", 1.0), ("1.15", 1.15), ("1.5", 1.5), ("Double", 2.0)]

_RIBBON_STYLE = (
    "QWidget { background: " + CHROME_SOFT + "; color: " + TEXT_PRIMARY + "; }"
    "QToolButton { background: transparent; border: 1px solid transparent;"
    "  border-radius: 4px; padding: 3px 7px; font-size: 13px; font-weight: 700;"
    "  color: " + SLATE_300 + "; }"
    "QToolButton:hover { background: rgba(255,255,255,0.08); color: " + TEXT_PRIMARY + "; }"
    "QToolButton:checked { background: " + SELECTION_BG + ";"
    "  border-color: " + SELECTION_BORDER + "; color: " + ACCENT_TEXT + "; }"
    "QToolButton:disabled { color: " + TEXT_FAINT + "; }"
    "QComboBox { background: rgba(0,0,0,0.3); color: " + TEXT_PRIMARY + ";"
    "  border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;"
    "  padding: 2px 6px; font-size: 12px; }"
    "QComboBox QAbstractItemView { background: " + BG_RAISED + "; color: " + TEXT_PRIMARY + ";"
    "  selection-background-color: " + TEXT_SELECTION + "; }"
)


def _parse_outline_value(value) -> tuple[str, int]:
    """Parse OUTLINE_PROP's stored value into (hex color, width px).

    Newer runs store "Npx #rrggbb"; legacy runs are bare "#rrggbb"
    (width assumed 1).
    """
    raw = str(value or "").strip()
    if not raw:
        return "#000000", 1
    if "px" in raw.lower():
        first, _, rest = raw.partition("px")
        try:
            from core.constants import OUTLINE_MIN_PX, OUTLINE_MAX_PX
            width = max(OUTLINE_MIN_PX, min(OUTLINE_MAX_PX, int(float(first.strip()))))
        except ValueError:
            width = 1
        color = rest.strip()
        if color.startswith("#"):
            return color, width
        return "#000000", width
    return raw, 1


def _parse_shadow_value(value) -> tuple[int, int, int, str, int] | None:
    """A stored shadow value -> (size, opacity, distance, color, angle).

    Mirrors core.slide_parser._parse_shadow (which already normalized what the
    document holds); kept local so the ribbon can read a char format without
    re-importing the parser on every keystroke.
    """
    from core.slide_parser import _parse_shadow
    parsed = _parse_shadow(str(value or ""))
    if not parsed or parsed == "none":
        return None
    size, rest = parsed.split(" ", 1)
    opacity, rest = rest.split(" ", 1)
    distance, rest = rest.split(" ", 1)
    color, _, angle = rest.rpartition(" ")
    return (int(size[:-2]), int(opacity[:-1]), int(distance[:-2]), color,
            int(angle))


def set_outline_off(doc, start: int = 0, end: int | None = None):
    """Write the explicit outline-off marker over [start, end).

    mergeCharFormat (not setCharFormat) is deliberate: it *sets* the sentinel
    value instead of unsetting the property, so the run overrides a theme
    baseline instead of falling back to it.
    """
    fmt = QTextCharFormat()
    fmt.setProperty(OUTLINE_PROP, OUTLINE_OFF)
    cursor = QTextCursor(doc)
    if start == 0 and (end is None or end >= max(0, doc.characterCount() - 1)):
        cursor.select(QTextCursor.SelectionType.Document)
    else:
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    cursor.mergeCharFormat(fmt)


_COLOR_SWATCHES = ('#000000', '#ffffff', '#ff0000', '#ff6600', '#ffcc00', '#00cc66', '#00aaff', '#0066ff', '#9933ff', '#ff33cc', '#808080', '#c0c0c0')
_RECENT_KEY = "designer.recent_colors"
_RECENT_MAX = 10


def _load_recent_colors() -> list:
    """Recent text/outline/shadow picks, most-recent-first. Never raises:
    a missing DB or junk value just means no recents yet."""
    try:
        import json as _json
        from core.database import get_setting
        from core.slide_parser import _parse_hex_color
        raw = get_setting(_RECENT_KEY, "")
        if not raw:
            return []
        out = []
        for item in _json.loads(raw):
            parsed = _parse_hex_color(str(item or "")) if isinstance(
                item, str) else None
            if parsed and parsed not in out:
                out.append(parsed)
        return out[:_RECENT_MAX]
    except Exception:
        return []


def _save_recent_colors(colors: list):
    """Persist recents (settings table, same as splitter layouts). Never
    raises — a failed save just means this session's picks don't carry."""
    try:
        import json as _json
        from core.database import set_setting
        set_setting(_RECENT_KEY, _json.dumps(list(colors)[:_RECENT_MAX]))
    except Exception:
        pass
_WHEEL_DIAMETER = 144
_WHEEL_MARKER_PAD = 8
_WHEEL_HUE_KEY_STEP = 6
_WHEEL_SAT_KEY_STEP = 16


def _wheel_hue_sat_for_point(x: float, y: float, cx: float, cy: float,
                             radius: float) -> tuple[int, int] | None:
    """Wheel position -> (hue 0-359, saturation 0-255), or None outside."""
    if radius <= 0:
        return None
    dx, dy = x - cx, y - cy
    distance = math.hypot(dx, dy)
    if distance > radius + 0.5:
        return None
    saturation = int(round(255 * min(1.0, distance / radius)))
    hue = int(math.degrees(math.atan2(dx, -dy)) % 360)
    return hue, saturation


def _wheel_point_for_hue_sat(hue: int, saturation: int, cx: float, cy: float,
                             radius: float) -> tuple[float, float]:
    """Inverse of the picker above: where the marker belongs for HSV."""
    r = radius * max(0, min(255, int(saturation))) / 255
    angle = math.radians(int(hue) % 360)
    return cx + r * math.sin(angle), cy - r * math.cos(angle)


class ColorWheel(QWidget):
    """Inline HSV disk: hue by angle, saturation by radius.

    A plain child widget (never a window/dialog), so it is safe inside the
    designer's Popup on Windows and Linux: no native color dialog opens,
    focus never leaves the designer, and the popup cannot close itself
    mid-pick. Brightness/value rides on the ribbon's slider; the disk keeps
    hue/saturation only, which keeps one drag gesture unambiguous.
    """

    colorChanged = pyqtSignal(str)

    def __init__(self, parent=None, diameter: int = _WHEEL_DIAMETER):
        super().__init__(parent)
        self.setFixedSize(max(96, int(diameter)), max(96, int(diameter)))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("Color wheel: click or drag for hue/saturation. "
                        "Arrow keys fine-tune; brightness slider sets value.")
        self._h = 0
        self._s = 0
        self._v = 255
        self._cache = None
        self._cache_key = None
        self._last_emitted = None

    def colorHex(self) -> str:
        return QColor.fromHsv(self._h, self._s, self._v).name()

    def setColor(self, hex_value: str) -> bool:
        """Adopt an external #rrggbb without emitting (picker sync)."""
        from core.slide_parser import _parse_hex_color
        parsed = _parse_hex_color(str(hex_value or ""))
        if parsed is None:
            return False
        h, s, v, _a = QColor(parsed).getHsv()
        if h < 0:
            h = 0
        changed = (h, s, v) != (self._h, self._s, self._v)
        self._h, self._s, self._v = int(h), int(s), int(v)
        self._last_emitted = self.colorHex()
        self._cache = None
        self.update()
        return changed

    def setValue(self, value: int):
        self._set_hsv(self._h, self._s, int(value), emit=True)

    def _set_hsv(self, h: int, s: int, v: int, emit: bool) -> bool:
        h = int(h) % 360
        s = max(0, min(255, int(s)))
        v = max(0, min(255, int(v)))
        if (h, s, v) == (self._h, self._s, self._v):
            return False
        value_changed = v != self._v
        self._h, self._s, self._v = h, s, v
        if value_changed:
            self._cache = None
        self.update()
        if emit:
            hx = self.colorHex()
            if hx != self._last_emitted:
                self._last_emitted = hx
                self.colorChanged.emit(hx)
        return True

    def _geometry(self) -> tuple[float, float, float]:
        side = min(self.width(), self.height())
        radius = max(1.0, side / 2 - _WHEEL_MARKER_PAD)
        return self.width() / 2, self.height() / 2, radius

    def _pick_point(self, point) -> bool:
        try:
            x, y = float(point.x()), float(point.y())
        except (TypeError, ValueError):
            return False
        cx, cy, radius = self._geometry()
        hsv = _wheel_hue_sat_for_point(x, y, cx, cy, radius)
        if hsv is None:
            return False
        return self._set_hsv(hsv[0], hsv[1], self._v, emit=True)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._pick_point(event.position())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._pick_point(event.position())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Left:
            self._set_hsv(self._h - _WHEEL_HUE_KEY_STEP, self._s, self._v, True)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self._set_hsv(self._h + _WHEEL_HUE_KEY_STEP, self._s, self._v, True)
            event.accept()
        elif key == Qt.Key.Key_Up:
            self._set_hsv(self._h, self._s + _WHEEL_SAT_KEY_STEP, self._v, True)
            event.accept()
        elif key == Qt.Key.Key_Down:
            self._set_hsv(self._h, self._s - _WHEEL_SAT_KEY_STEP, self._v, True)
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        w, h = max(1, self.width()), max(1, self.height())
        key = (w, h, self._v)
        if self._cache is None or self._cache_key != key:
            image = QImage(w, h, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.transparent)
            cx, cy, radius = self.width() / 2, self.height() / 2, (
                min(w, h) / 2 - _WHEEL_MARKER_PAD)
            for yy in range(h):
                for xx in range(w):
                    hsv = _wheel_hue_sat_for_point(xx + 0.5, yy + 0.5,
                                                   cx, cy, radius)
                    if hsv is not None:
                        image.setPixelColor(
                            xx, yy, QColor.fromHsv(hsv[0], hsv[1], self._v))
            self._cache = image
            self._cache_key = key
        painter = QPainter(self)
        painter.drawImage(self.rect(), self._cache)
        cx, cy, radius = self._geometry()
        mx, my = _wheel_point_for_hue_sat(self._h, self._s, cx, cy, radius)
        painter.setPen(QPen(QColor(0, 0, 0), 3))
        painter.drawEllipse(int(mx - 6), int(my - 6), 12, 12)
        painter.setPen(QPen(QColor(255, 255, 255), 1))
        painter.drawEllipse(int(mx - 5), int(my - 5), 10, 10)
        painter.end()



class FormatRibbon(QWidget):
    """Two-row formatting ribbon bound to one active editor at a time."""

    format_applied = pyqtSignal()       # any text/block formatting change
    deck_format_changed = pyqtSignal(dict)  # e.g. {"spacing": 1.5}

    def __init__(self, parent=None, recent_store=None):
        super().__init__(parent)
        self._edit: QTextEdit | None = None
        # (edit, doc, revision, pos, fmt) for a format applied at a bare
        # caret. Qt's typing format is one per WIDGET and survives card
        # switches, so at a block start it is NOT evidence of the run
        # under the caret — only this marker is (see _run_char_format).
        self._typing_fmt = None
        # Deck-wide fan-out (set by the designer while the whole deck is
        # selected): _merge routes char formats here instead of the editor.
        self.fan_out = None
        self.fan_out_remove_outline = None
        self.fan_out_clear_all = None
        self.fan_out_block = None
        # Recent-colors persistence: (load, save) pair; tests inject a
        # memory pair so suites never touch the developer's real DB.
        if recent_store is None:
            recent_store = (_load_recent_colors, _save_recent_colors)
        self._recent_load, self._recent_save = recent_store
        self._recents: list = []
        # True while a ribbon slot is mutating a document. The designer reads
        # this to tell ribbon formats apart from typing: Qt fires
        # contentsChange/textChanged for BOTH, and only typing may collapse
        # tier selections (repeated spin clicks must keep working).
        self._in_ribbon_merge = False
        self._outline_color = "#000000"
        self._outline_width = 1
        self._shadow_color = "#000000"
        self._shadow_size_px = 8
        self._shadow_opacity_pct = 100
        self._shadow_distance_px = 0
        self._shadow_angle_deg = 45
        self._deck_spacing: float | None = None
        # Inline color picking (never a second window: the picker belongs
        # in the ribbon and the choice must not disturb editor focus).
        self._color_target: str | None = None
        self._pending_color: str | None = None
        self._text_chip_color: str | None = None
        # Theme baseline (core.theme_loader.display_format_defaults):
        # what the DISPLAY already applies. A run's own props win; these
        # only fill the gaps, so the ribbon shows effective formatting
        # instead of reading empty until the operator clicks something.
        self._theme_defaults: dict = {}
        # Deck top-script format (theme < deck < run). The designer pushes
        # it on load and on every deck-format patch.
        self._deck_format: dict = {}
        self.setStyleSheet(_RIBBON_STYLE)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 4, 8, 4)
        root.setSpacing(2)

        row1 = QHBoxLayout()
        row1.setSpacing(2)
        self._build_row1(row1)
        root.addLayout(row1)
        self._build_color_bar()
        root.addWidget(self._color_bar)

        self._more_toggle = QToolButton()
        self._more_toggle.setToolTip("More formatting")
        from ui.icons import apply_button as _apply_button
        _apply_button(self._more_toggle, "pilcrow")
        self._more_toggle.setText("More")
        self._more_toggle.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._more_toggle.setCheckable(True)
        self._more_toggle.setChecked(False)
        self._more_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._more_toggle.toggled.connect(self._on_more_toggled)
        row1.addWidget(self._more_toggle)

        self._row2 = QWidget()
        row2 = QHBoxLayout(self._row2)
        row2.setContentsMargins(0, 2, 0, 0)
        row2.setSpacing(2)
        self._build_row2(row2)
        row2.addStretch()
        root.addWidget(self._row2)
        self._row2.setVisible(False)

    # ─── construction ───────────────────────────────────────────────────

    def _btn(self, text: str, tip: str, checkable=False, icon=None) -> QToolButton:
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        if icon is not None:
            from ui.icons import apply_button
            apply_button(b, icon)
        return b

    def _spin(self, lo: int, hi: int, value: int, suffix: str, tip: str) -> QSpinBox:
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(value)
        s.setSuffix(suffix)
        s.setToolTip(tip)
        s.setMaximumWidth(72)
        return s

    def _build_row1(self, row: QHBoxLayout):
        self._font_combo = QFontComboBox()
        install_combo(self._font_combo)
        self._font_combo.setToolTip("Font family")
        self._font_combo.setMaximumWidth(150)
        self._font_combo.currentFontChanged.connect(self._on_font_family)
        row.addWidget(self._font_combo)

        self._size_minus = self._btn("−", "Decrease size", icon="minus")
        self._size_minus.clicked.connect(lambda: self._step_size(-1))
        row.addWidget(self._size_minus)
        self._size_combo = QComboBox()
        install_combo(self._size_combo)
        self._size_combo.setEditable(True)
        self._size_combo.setToolTip("Font size (px)")
        self._size_combo.setMaximumWidth(58)
        for s in _SIZES_PX:
            self._size_combo.addItem(str(s))
        self._size_combo.setCurrentText("20")
        self._size_combo.activated.connect(self._on_size_combo)
        self._size_combo.lineEdit().returnPressed.connect(self._on_size_typed)
        row.addWidget(self._size_combo)
        self._size_plus = self._btn("+", "Increase size", icon="plus")
        self._size_plus.clicked.connect(lambda: self._step_size(1))
        row.addWidget(self._size_plus)

        self._btn_bold = self._btn("B", "Bold (Ctrl+B)", True)
        self._btn_bold.clicked.connect(lambda: self._toggle_bold())
        row.addWidget(self._btn_bold)
        self._btn_italic = self._btn("I", "Italic (Ctrl+I)", True)
        self._btn_italic.clicked.connect(lambda: self._toggle_italic())
        row.addWidget(self._btn_italic)
        self._btn_strike = self._btn("S", "Strikethrough", True)
        self._btn_strike.clicked.connect(lambda: self._toggle_strike())
        row.addWidget(self._btn_strike)
        self._btn_underline = self._btn("U", "Underline (Ctrl+U)", True)
        self._btn_underline.clicked.connect(lambda: self._toggle_underline())
        row.addWidget(self._btn_underline)

        self._btn_outline = self._btn("O", "Outline (uses outline color)", True)
        self._btn_outline.clicked.connect(self._on_outline_toggled)
        row.addWidget(self._btn_outline)
        self._btn_outline_color = self._btn("■", "Outline color")
        self._btn_outline_color.clicked.connect(self._on_outline_color)
        self._btn_outline_color.setVisible(False)
        row.addWidget(self._btn_outline_color)
        from core.constants import OUTLINE_MIN_PX, OUTLINE_MAX_PX
        self._outline_size = QSpinBox()
        self._outline_size.setRange(OUTLINE_MIN_PX, OUTLINE_MAX_PX)
        self._outline_size.setValue(self._outline_width)
        self._outline_size.setSuffix(" px")
        self._outline_size.setToolTip(
            f"Outline thickness ({OUTLINE_MIN_PX}\u2013{OUTLINE_MAX_PX} px)")
        self._outline_size.setMaximumWidth(76)
        self._outline_size.valueChanged.connect(self._on_outline_size_changed)
        self._outline_size.setVisible(False)
        row.addWidget(self._outline_size)

        # Shadow: a hard ring drawn in shadow rather than stroke, so it can be
        # pulled away from the letters (distance) and faded (opacity).
        self._btn_shadow = self._btn("Sh", "Shadow (size / opacity / distance / angle)", True)
        self._btn_shadow.clicked.connect(self._on_shadow_toggled)
        row.addWidget(self._btn_shadow)
        self._btn_shadow_color = self._btn("\u25a0", "Shadow color")
        self._btn_shadow_color.clicked.connect(self._on_shadow_color)
        self._btn_shadow_color.setVisible(False)
        row.addWidget(self._btn_shadow_color)
        from core.constants import (SHADOW_SIZE_MIN_PX, SHADOW_SIZE_MAX_PX,
                                      SHADOW_DISTANCE_MIN_PX,
                                      SHADOW_DISTANCE_MAX_PX)
        self._shadow_size = self._spin(SHADOW_SIZE_MIN_PX, SHADOW_SIZE_MAX_PX,
                                      self._shadow_size_px, " px",
                                      f"Shadow size ({SHADOW_SIZE_MIN_PX}\u2013{SHADOW_SIZE_MAX_PX} px)")
        self._shadow_opacity = self._spin(0, 100, self._shadow_opacity_pct, " %",
                                          "Shadow opacity (0\u2013100 %)")
        self._shadow_distance = self._spin(SHADOW_DISTANCE_MIN_PX,
                                           SHADOW_DISTANCE_MAX_PX,
                                           self._shadow_distance_px, " px",
                                           f"Shadow distance from the letters ({SHADOW_DISTANCE_MIN_PX}\u2013{SHADOW_DISTANCE_MAX_PX} px)")
        self._shadow_angle = self._spin(0, 359, self._shadow_angle_deg, "\u00b0",
                                        "Shadow direction (degrees, 0 = east, 90 = down)")
        for s in (self._shadow_size, self._shadow_opacity, self._shadow_distance,
                  self._shadow_angle):
            s.setVisible(False)
            row.addWidget(s)
        self._shadow_size.valueChanged.connect(self._on_shadow_size_changed)
        self._shadow_opacity.valueChanged.connect(self._on_shadow_opacity_changed)
        self._shadow_distance.valueChanged.connect(self._on_shadow_distance_changed)
        self._shadow_angle.valueChanged.connect(self._on_shadow_angle_changed)

        self._btn_color = self._btn("A", "Text color")
        self._btn_color.clicked.connect(self._on_text_color)
        row.addWidget(self._btn_color)
        self._color_chip = QLabel()
        self._color_chip.setFixedSize(16, 16)
        self._color_chip.setToolTip("Current effective text color")
        row.addWidget(self._color_chip)

        self._btn_clear = self._btn("⌫", "Clear formatting", icon="eraser")
        self._btn_clear.clicked.connect(self._on_clear)
        row.addWidget(self._btn_clear)

        self._btn_undo = self._btn("↩", "Undo (Ctrl+Z)", icon="undo")
        self._btn_undo.clicked.connect(self._do_undo)
        row.addWidget(self._btn_undo)
        self._btn_redo = self._btn("↪", "Redo (Ctrl+Shift+Z)", icon="redo")
        self._btn_redo.clicked.connect(self._do_redo)
        row.addWidget(self._btn_redo)
        row.addStretch()

    def _build_color_bar(self):
        """Inline color section below row 1: swatches + wheel + value + hex.

        Still a plain child widget (no window/dialog), so the Popup-safe
        constraint holds. Swatches keep the old one-click apply/close;
        wheel/slider edits stage a pending color until Apply, so dragging
        never spams the document/undo stack with intermediate merges.
        """
        self._color_bar = QWidget()
        bar = QHBoxLayout(self._color_bar)
        bar.setContentsMargins(8, 6, 8, 6)
        bar.setSpacing(10)
        self._wheel = ColorWheel()
        self._wheel.colorChanged.connect(self._on_wheel_preview)
        bar.addWidget(self._wheel)

        side = QVBoxLayout()
        side.setSpacing(6)
        swatch_grid = QGridLayout()
        swatch_grid.setContentsMargins(0, 0, 0, 0)
        swatch_grid.setSpacing(2)
        self._swatches = []
        for i, hex_color in enumerate(_COLOR_SWATCHES):
            sw = QToolButton()
            sw.setFixedSize(20, 20)
            sw.setCursor(Qt.CursorShape.PointingHandCursor)
            sw.setToolTip(hex_color)
            sw.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;")
            sw.clicked.connect(
                lambda _=False, h=hex_color: self._pick_color(h))
            swatch_grid.addWidget(sw, i // 6, i % 6)
            self._swatches.append(sw)
        side.addLayout(swatch_grid)

        recent_row = QHBoxLayout()
        recent_row.setSpacing(6)
        recent_label = QLabel("Recent")
        recent_label.setToolTip(
            "Colors used before (kept across sessions) — click to reuse")
        recent_row.addWidget(recent_label)
        self._recent_chips = QHBoxLayout()
        self._recent_chips.setSpacing(2)
        recent_row.addLayout(self._recent_chips)
        recent_row.addStretch(1)
        side.addLayout(recent_row)
        try:
            self._recents = list(self._recent_load() or [])
        except Exception:
            self._recents = []
        self._refresh_recent_row()

        value_row = QHBoxLayout()
        value_row.setSpacing(6)
        value_label = QLabel("Value")
        value_label.setToolTip("Brightness for the wheel color")
        value_row.addWidget(value_label)
        self._value_slider = QSlider(Qt.Orientation.Horizontal)
        self._value_slider.setRange(0, 255)
        self._value_slider.setValue(255)
        self._value_slider.setToolTip("Brightness/value for the wheel color")
        self._value_slider.valueChanged.connect(self._on_value_changed)
        value_row.addWidget(self._value_slider, 1)
        side.addLayout(value_row)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(6)
        self._hex_edit = QLineEdit()
        self._hex_edit.setPlaceholderText("#rrggbb")
        self._hex_edit.setMaximumWidth(84)
        self._hex_edit.setToolTip("Type a hex color and press Enter")
        self._hex_edit.returnPressed.connect(self._on_hex_entered)
        hex_row.addWidget(self._hex_edit)
        self._color_preview = QLabel()
        self._color_preview.setFixedSize(40, 22)
        self._color_preview.setToolTip("Pending color (Apply to use it)")
        hex_row.addWidget(self._color_preview)
        self._btn_apply = self._btn("Apply", "Apply the pending color")
        self._btn_apply.clicked.connect(self._on_color_apply)
        hex_row.addWidget(self._btn_apply)
        self._btn_close = self._btn("Close", "Close without applying")
        self._btn_close.clicked.connect(self._hide_color_bar)
        hex_row.addWidget(self._btn_close)
        hex_row.addStretch(1)
        side.addLayout(hex_row)
        side.addStretch(1)
        bar.addLayout(side, 1)
        self._color_bar.setVisible(False)

    def _build_row2(self, row: QHBoxLayout):
        self._align_btns = {}
        _ALIGN_ICONS = {"left": "align-left", "center": "align-center",
                        "right": "align-right", "justify": "align-justify"}
        for key, label, tip in (("left", "≡", "Align left"),
                                ("center", "≣", "Align center"),
                                ("right", "≡", "Align right"),
                                ("justify", "☰", "Justify")):
            b = self._btn(label, tip, True, icon=_ALIGN_ICONS[key])
            b.clicked.connect(lambda _=False, k=key: self._on_align(k))
            row.addWidget(b)
            self._align_btns[key] = b

        self._spacing_btn = self._btn("↕", "Paragraph spacing", icon="spacing")
        self._spacing_menu = QMenu(self)
        self._spacing_menu.setStyleSheet(menu_qss())
        self._spacing_actions = {}
        for label, value in _SPACINGS:
            act = QAction(label, self, checkable=True)
            act.triggered.connect(lambda _=False, v=value: self._on_spacing(v))
            self._spacing_menu.addAction(act)
            self._spacing_actions[value] = act
        self._spacing_menu.addSeparator()
        custom = QAction("Custom…", self)
        custom.triggered.connect(self._on_spacing_custom)
        self._spacing_menu.addAction(custom)
        self._spacing_btn.setMenu(self._spacing_menu)
        self._spacing_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(self._spacing_btn)

        self._btn_bullets = self._btn("•", "Bullet list", True, icon="list-bullet")
        self._btn_bullets.clicked.connect(self._on_bullets)
        row.addWidget(self._btn_bullets)
        self._btn_numbers = self._btn("1.", "Numbered list", True, icon="list-ordered")
        self._btn_numbers.clicked.connect(self._on_numbers)
        row.addWidget(self._btn_numbers)

        self._btn_super = self._btn("x²", "Superscript", True)
        self._btn_super.clicked.connect(lambda: self._toggle_script(True))
        row.addWidget(self._btn_super)
        self._btn_sub = self._btn("x₂", "Subscript", True)
        self._btn_sub.clicked.connect(lambda: self._toggle_script(False))
        row.addWidget(self._btn_sub)

        self._btn_upper = self._btn("AA", "UPPERCASE", True)
        self._btn_upper.clicked.connect(lambda: self._on_case(True))
        row.addWidget(self._btn_upper)
        self._btn_lower = self._btn("aa", "lowercase", True)
        self._btn_lower.clicked.connect(lambda: self._on_case(False))
        row.addWidget(self._btn_lower)

        self._btn_rtl = self._btn("RTL", "Right-to-left block", True)
        self._btn_rtl.clicked.connect(lambda: self._on_direction(True))
        row.addWidget(self._btn_rtl)
        self._btn_ltr = self._btn("LTR", "Left-to-right block", True)
        self._btn_ltr.clicked.connect(lambda: self._on_direction(False))
        row.addWidget(self._btn_ltr)

        self._btn_hr = self._btn("―", "Horizontal line", icon="hr-line")
        self._btn_hr.clicked.connect(self._on_hr)
        row.addWidget(self._btn_hr)

    # ─── editor binding ─────────────────────────────────────────────────

    def clear_typing_format(self):
        """Forget the pending typing format (call when the card changes)."""
        self._typing_fmt = None

    def set_editor(self, edit: QTextEdit | None):
        self._typing_fmt = None
        if self._edit is not None:
            try:
                self._edit.cursorPositionChanged.disconnect(self.refresh_state)
                self._edit.undoAvailable.disconnect(self._btn_undo.setEnabled)
                self._edit.redoAvailable.disconnect(self._btn_redo.setEnabled)
            except (RuntimeError, TypeError):
                pass
        self._edit = edit
        if edit is not None:
            edit.cursorPositionChanged.connect(self.refresh_state)
            edit.undoAvailable.connect(self._btn_undo.setEnabled)
            edit.redoAvailable.connect(self._btn_redo.setEnabled)
            self._btn_undo.setEnabled(edit.document().isUndoAvailable())
            self._btn_redo.setEnabled(edit.document().isRedoAvailable())
        self.refresh_state()

    @contextmanager
    def _ribbon_merge(self):
        """Mark document mutations as ribbon-origin (see _in_ribbon_merge)."""
        prev = self._in_ribbon_merge
        self._in_ribbon_merge = True
        try:
            yield
        finally:
            self._in_ribbon_merge = prev

    def _merge(self, fmt: QTextCharFormat):
        """Apply char format to selection (or typing format when none)."""
        if self._edit is None:
            return
        with self._ribbon_merge():
            if self.fan_out is not None:
                self.fan_out(fmt)  # designer fans out; keeps deck selection
                self.refresh_state()
                return
            cursor = self._edit.textCursor()
            if cursor.hasSelection():
                cursor.mergeCharFormat(fmt)
            else:
                self._edit.mergeCurrentCharFormat(fmt)
                self._typing_fmt = (
                    self._edit, self._edit.document(),
                    self._edit.document().revision(),
                    self._edit.textCursor().position(),
                    self._edit.currentCharFormat())
            self.format_applied.emit()
            self.refresh_state()

    # ─── row 1 slots ────────────────────────────────────────────────────

    def _toggle_bold(self):
        # Flip the EFFECTIVE state, not the run's private one: on
        # theme-bold text the first click writes an explicit bold=false
        # (the text visibly un-bolds) instead of a redundant bold=true.
        # NB: `clicked` fires AFTER Qt flips the button, so the button
        # state is the POST-click value — reading it would apply the
        # format the operator just turned off. Use the pre-click
        # effective state instead (same basis the buttons display).
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Weight.Normal
                          if self._eff_bold()
                          else QFont.Weight.Bold)
        self._merge(fmt)

    def _toggle_italic(self):
        if self._edit is None:
            return
        fmt = QTextCharFormat()
        fmt.setFontItalic(not self._eff_italic())
        self._merge(fmt)

    def _toggle_strike(self):
        if self._edit is None:
            return
        new = not self._eff_strike()
        fmt = QTextCharFormat()
        fmt.setFontStrikeOut(new)
        # Record, don't clear: a loaded strike=false must flip to true in
        # the txt (a cleared prop would keep serializing false).
        fmt.setProperty(SO_PROP, new)
        self._merge(fmt)

    def _toggle_underline(self):
        if self._edit is None:
            return
        new = not self._eff_underline()
        fmt = QTextCharFormat()
        fmt.setFontUnderline(new)
        # Same as strike: Qt6 never marks the bool, so the prop IS the txt.
        fmt.setProperty(UL_PROP, new)
        self._merge(fmt)

    def _on_font_family(self, font: QFont):
        fmt = QTextCharFormat()
        # Metadata only: families render on preview, never in the pane.
        fmt.setProperty(FONT_PROP, font.family())
        self._merge(fmt)

    def _current_font_family(self) -> str:
        """Effective family: run prop, then deck, then theme ("" = none)."""
        if self._edit is not None:
            cf = self._run_char_format()
            if cf.hasProperty(FONT_PROP):
                family = str(cf.property(FONT_PROP) or "").strip()
                if family:
                    return family
        for source in (self._deck_format, self._theme_defaults):
            try:
                family = str(source.get("font") or "").strip()
            except AttributeError:
                family = ""
            if family:
                return family
        return ""

    def _sync_font_combo(self, family: str):
        """Mirror the effective family without re-applying it.

        QFontComboBox emits currentFontChanged on programmatic changes, so
        the sync is signal-blocked; otherwise simply selecting a run would
        stamp a font onto it.
        """
        if not family or self._font_combo.currentFont().family() == family:
            return
        self._font_combo.blockSignals(True)
        try:
            self._font_combo.setCurrentFont(QFont(family))
        finally:
            self._font_combo.blockSignals(False)

    def _current_size_px(self) -> int:
        """Effective nominal size: run, deck, theme, 20px fallback."""
        if self._edit is not None:
            cf = self._run_char_format()
            if cf.hasProperty(SIZE_PROP):
                try:
                    return max(1, int(cf.property(SIZE_PROP)))
                except (TypeError, ValueError):
                    pass
            pt = cf.fontPointSize()
            if pt:
                return max(1, round(pt / _PT_PER_PX))
        for key, source in (("size_nominal", self._deck_format),
                            ("size", self._theme_defaults)):
            try:
                if source.get(key) is not None:
                    raw = str(source.get(key)).strip()
                    if raw.lower().endswith("px"):
                        raw = raw[:-2].strip()
                    return max(1, int(float(raw)))
            except (TypeError, ValueError):
                pass
        return 20

    def _apply_size_px(self, px: int):
        fmt = QTextCharFormat()
        # Metadata only: the edit pane renders one fixed size; the
        # nominal px rides along for serialization + preview.
        fmt.setProperty(SIZE_PROP, max(1, px))
        self._merge(fmt)

    def _step_size(self, delta: int):
        # One unit per click — the preset ladder belongs to the dropdown,
        # not to the steppers (a stepper that jumped preset-to-preset
        # made fine adjustment impossible).
        self._apply_size_px(max(1, self._current_size_px() + delta))

    def _on_size_combo(self):
        try:
            self._apply_size_px(int(self._size_combo.currentText()))
        except ValueError:
            pass

    def _on_size_typed(self):
        self._on_size_combo()
        if self._edit is not None:
            self._edit.setFocus()

    def _outline_fmt(self, on: bool) -> QTextCharFormat:
        fmt = QTextCharFormat()
        if on:
            # Prop only (no tint cue): outlines render on preview, never
            # in the pane.
            fmt.setProperty(OUTLINE_PROP, f"{self._outline_width}px {self._outline_color}")
        else:
            fmt.clearProperty(OUTLINE_PROP)
            fmt.clearBackground()
        return fmt

    def _on_outline_toggled(self):
        on = self._btn_outline.isChecked()
        self._btn_outline_color.setVisible(on)
        self._outline_size.setVisible(on)
        if on:
            self._merge(self._outline_fmt(True))
        else:
            self._remove_outline_property()

    def set_outline_color(self, hex_color: str):
        self._outline_color = hex_color
        self._btn_outline_color.setStyleSheet(f"color: {hex_color};")
        if self._btn_outline.isChecked():
            self._merge(self._outline_fmt(True))

    # ── shadow ──────────────────────────────────────────────────────────
    def _shadow_value(self, on: bool = True) -> str:
        if not on:
            return SHADOW_OFF
        return (f"{self._shadow_size_px}px {self._shadow_opacity_pct}% "
                f"{self._shadow_distance_px}px {self._shadow_color} "
                f"{self._shadow_angle_deg}")

    def _shadow_fmt(self, on: bool = True) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setProperty(SHADOW_PROP, self._shadow_value(on))
        return fmt

    def _current_shadow(self) -> str | None:
        """The shadow actually in effect at the caret, else None."""
        if self._edit is None:
            return None
        cf = self._run_char_format()
        if cf.hasProperty(SHADOW_PROP):
            raw = cf.property(SHADOW_PROP)
            if raw and raw != SHADOW_OFF:
                return raw
        return None

    def _apply_shadow_keeper(self):
        """Size/opacity/distance/angle changes must not drop the run's own
        color (or angle, when only another knob moved). With no run shadow,
        seed from the effective deck value so the first knob touch keeps
        what display renders instead of reverting to a stale pick."""
        current = self._current_shadow()
        if current:
            parsed = _parse_shadow_value(current)
            if parsed:
                self._shadow_color = parsed[3]
                self._shadow_angle_deg = parsed[4]
                return
        deck = self._deck_format.get("shadow")
        if isinstance(deck, str) and not self._offish(deck):
            parsed = _parse_shadow_value(deck)
            if parsed:
                self._shadow_color = parsed[3]
                self._shadow_angle_deg = parsed[4]

    def _on_shadow_toggled(self):
        on = self._btn_shadow.isChecked()
        for w in (self._btn_shadow_color, self._shadow_size,
                  self._shadow_opacity, self._shadow_distance,
                  self._shadow_angle):
            w.setVisible(on)
        self._merge(self._shadow_fmt(on))

    def set_shadow_color(self, hex_color: str):
        self._shadow_color = hex_color
        self._btn_shadow_color.setStyleSheet(f"color: {hex_color};")
        if self._btn_shadow.isChecked():
            self._merge(self._shadow_fmt(True))

    def _on_shadow_color(self):
        self._toggle_color_bar("shadow")

    def _on_shadow_size_changed(self, px: int):
        from core.constants import SHADOW_SIZE_MIN_PX, SHADOW_SIZE_MAX_PX
        self._shadow_size_px = max(SHADOW_SIZE_MIN_PX,
                                   min(SHADOW_SIZE_MAX_PX, int(px)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper()
            self._merge(self._shadow_fmt(True))

    def _on_shadow_opacity_changed(self, pct: int):
        self._shadow_opacity_pct = max(0, min(100, int(pct)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper()
            self._merge(self._shadow_fmt(True))

    def _on_shadow_distance_changed(self, px: int):
        from core.constants import SHADOW_DISTANCE_MIN_PX, SHADOW_DISTANCE_MAX_PX
        self._shadow_distance_px = max(SHADOW_DISTANCE_MIN_PX,
                                       min(SHADOW_DISTANCE_MAX_PX, int(px)))
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper()
            self._merge(self._shadow_fmt(True))

    def _on_shadow_angle_changed(self, deg: int):
        # Keeper first: it syncs the run's color, and would otherwise restore
        # the run's old angle over the one just picked.
        if self._btn_shadow.isChecked():
            self._apply_shadow_keeper()
        self._shadow_angle_deg = int(deg) % 360
        if self._btn_shadow.isChecked():
            self._merge(self._shadow_fmt(True))

    def _outline_value_parts(self, value) -> tuple | None:
        """(color, width) from a deck/theme outline value ("Npx #hex" or
        bare "#hex"), or None when absent/off/unparseable."""
        if not isinstance(value, str) or self._offish(value):
            return None
        try:
            from core.slide_parser import _parse_hex_color
            color, width = _parse_outline_value(value)
            if _parse_hex_color(color):
                return color, width
        except Exception:
            pass
        return None

    def _current_outline_color(self) -> str:
        """Effective outline color: run, deck, theme, last pick."""
        if self._edit is None:
            return self._outline_color
        cf = self._run_char_format()
        try:
            if cf.hasProperty(OUTLINE_PROP):
                raw = cf.property(OUTLINE_PROP)
                if raw and raw != OUTLINE_OFF:
                    return _parse_outline_value(raw)[0]
        except Exception:
            pass
        for source in (self._deck_format, self._theme_defaults):
            parts = self._outline_value_parts(source.get("outline"))
            if parts:
                return parts[0]
        return self._outline_color

    def _on_outline_size_changed(self, px: int):
        from core.constants import OUTLINE_MIN_PX, OUTLINE_MAX_PX
        self._outline_width = max(OUTLINE_MIN_PX, min(OUTLINE_MAX_PX, int(px)))
        if self._btn_outline.isChecked():
            # Keep the effective color (run, deck, theme); only the width changed.
            self._outline_color = self._current_outline_color()
            self._merge(self._outline_fmt(True))

    def _remove_outline_property(self):
        """Turn outline off for the selection (or the caret's run).

        Writes the OUTLINE_OFF sentinel rather than clearing the property:
        a theme whose `text_shadow` outlines text would otherwise re-assert
        the outline on the very next refresh, and the toggle would look
        broken. mergeCharFormat *sets* the sentinel, so the operator's
        selection survives.
        """
        if self.fan_out_remove_outline is not None:
            with self._ribbon_merge():
                self.fan_out_remove_outline()
            self.format_applied.emit()
            self.refresh_state()
            return
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        with self._ribbon_merge():
            if cursor.hasSelection():
                set_outline_off(cursor.document(),
                                cursor.selectionStart(), cursor.selectionEnd())
            else:
                fmt = QTextCharFormat(cursor.charFormat())
                fmt.setProperty(OUTLINE_PROP, OUTLINE_OFF)
                self._edit.setCurrentCharFormat(fmt)
        self.format_applied.emit()
        self.refresh_state()

    def _current_shadow_color(self) -> str:
        """Effective shadow color: run, deck, last pick. (A theme shadow
        is raw CSS, not knob-shaped, so the theme can't seed the swatch.)"""
        raw = self._current_shadow()
        if raw:
            parsed = _parse_shadow_value(raw)
            if parsed:
                return parsed[3]
        deck = self._deck_format.get("shadow")
        if isinstance(deck, str) and not self._offish(deck):
            parsed = _parse_shadow_value(deck)
            if parsed:
                return parsed[3]
        return self._shadow_color

    def _current_text_color(self) -> str:
        """Effective text color: run override, deck, theme default, white."""
        from core.slide_parser import _parse_hex_color
        if self._edit is not None:
            cf = self._run_char_format()
            if cf.hasProperty(COLOR_PROP):
                parsed = _parse_hex_color(str(cf.property(COLOR_PROP) or ""))
                if parsed:
                    return parsed
        for source in (self._deck_format, self._theme_defaults):
            theme_color = source.get("color")
            if isinstance(theme_color, str):
                parsed = _parse_hex_color(theme_color)
                if parsed:
                    return parsed
        return "#ffffff"

    def _current_color_for_target(self, target: str) -> str:
        if target == "outline":
            return self._current_outline_color()
        if target == "shadow":
            return self._current_shadow_color()
        return self._current_text_color()

    def _record_recent(self, hex_color: str):
        """A committed pick joins the recents (front, deduped, capped) and
        persists for the next session. Previews never record — only picks
        that actually landed on text."""
        self._recents = [hex_color] + [c for c in self._recents
                                       if c != hex_color]
        self._recents = self._recents[:_RECENT_MAX]
        self._refresh_recent_row()
        try:
            self._recent_save(self._recents)
        except Exception:
            pass

    def _refresh_recent_row(self):
        """Rebuild recent chips from self._recents (takeAt detaches
        synchronously, so this is exact even without pumping events)."""
        while self._recent_chips.count():
            old = self._recent_chips.takeAt(0)
            if old is not None and old.widget() is not None:
                old.widget().deleteLater()
        for hex_color in self._recents:
            chip = QToolButton()
            chip.setFixedSize(20, 20)
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setToolTip(f"Reuse {hex_color}")
            chip.setStyleSheet(
                f"background-color: {hex_color}; border: 1px solid #555;")
            chip.clicked.connect(
                lambda _=False, h=hex_color: self._pick_color(h))
            self._recent_chips.addWidget(chip)

    def _update_color_preview(self, hex_color: str):
        self._color_preview.setStyleSheet(
            "QLabel { background-color: " + hex_color +
            "; border: 1px solid " + SELECTION_BORDER + "; border-radius: 4px; }")

    def _sync_color_picker(self, hex_color: str):
        """Stage a valid color across wheel/slider/hex/preview (no apply)."""
        self._pending_color = hex_color
        self._wheel.blockSignals(True)
        self._value_slider.blockSignals(True)
        try:
            self._wheel.setColor(hex_color)
            self._value_slider.setValue(QColor(hex_color).value())
        finally:
            self._wheel.blockSignals(False)
            self._value_slider.blockSignals(False)
        if self._hex_edit.text() != hex_color:
            self._hex_edit.setText(hex_color)
        self._update_color_preview(hex_color)

    def _apply_target_color(self, hex_color: str, target: str | None = None):
        target = self._color_target if target is None else target
        if target == "outline":
            self.set_outline_color(hex_color)
        elif target == "shadow":
            self.set_shadow_color(hex_color)
        elif target == "text":
            self._apply_text_color(hex_color)
        else:
            return False
        self._record_recent(hex_color)
        return True

    def _hide_color_bar(self):
        self._color_bar.setVisible(False)
        self._color_target = None
        self._pending_color = None

    def _toggle_color_bar(self, target: str):
        """Show the inline picker for outline/shadow/text color.

        A plain child widget: no window opens, so the designer Popup keeps
        focus and can never close itself picking a color (the modal-dialog
        bug). Clicking the active target's button hides the bar again.
        """
        if self._color_target == target and not self._color_bar.isHidden():
            self._hide_color_bar()
            return
        self._color_target = target
        self._sync_color_picker(self._current_color_for_target(target))
        self._hex_edit.selectAll()
        self._color_bar.setVisible(True)

    def _pick_color(self, hex_color: str):
        """Apply a swatch/hex pick to the active target, then hide the bar."""
        from core.slide_parser import _parse_hex_color
        color = _parse_hex_color(hex_color)
        if color is None:
            return
        self._sync_color_picker(color)
        self._apply_target_color(color)
        self._hide_color_bar()

    def _on_hex_entered(self):
        self._pick_color(self._hex_edit.text().strip())

    def _on_wheel_preview(self, hex_color: str):
        """Stage wheel drags without merging: Apply commits once."""
        from core.slide_parser import _parse_hex_color
        color = _parse_hex_color(hex_color)
        if color is None or self._color_target is None:
            return
        self._pending_color = color
        if self._hex_edit.text() != color:
            self._hex_edit.setText(color)
        self._update_color_preview(color)

    def _on_value_changed(self, value: int):
        self._wheel.setValue(value)

    def _on_color_apply(self):
        if self._pending_color is None or self._color_target is None:
            return
        self._apply_target_color(self._pending_color)
        self._hide_color_bar()

    def _apply_text_color(self, hex_color: str):
        fmt = QTextCharFormat()
        # Metadata only: colors render on preview, never in the pane.
        fmt.setProperty(COLOR_PROP, hex_color)
        self._merge(fmt)

    def _on_outline_color(self):
        self._toggle_color_bar("outline")

    def _on_text_color(self):
        if self._edit is None:
            return
        self._toggle_color_bar("text")

    def _on_clear(self):
        # Tier scope first: tiers 3-4 paint a REAL selection in the
        # focused box (visualization), so the selection branch below would
        # wrongly clear only the active slide. A raised tier means the
        # operator selected the scope — clear all of it.
        if self.fan_out_clear_all is not None:
            with self._ribbon_merge():
                self.fan_out_clear_all()
            self.format_applied.emit()
            self.refresh_state()
            return
        if self._edit is None:
            return
        fmt = QTextCharFormat()  # empty = all defaults
        fmt.clearProperty(UL_PROP)
        fmt.clearProperty(SO_PROP)
        fmt.clearProperty(OUTLINE_PROP)
        fmt.clearProperty(SHADOW_PROP)
        cursor = self._edit.textCursor()
        with self._ribbon_merge():
            if cursor.hasSelection():
                # mergeCharFormat with defaults won't unset; select+reset instead.
                cursor.setCharFormat(QTextCharFormat())
                self._edit.setTextCursor(cursor)
            else:
                self._edit.setCurrentCharFormat(QTextCharFormat())
        self.format_applied.emit()
        self.refresh_state()

    def _do_undo(self):
        if self._edit is not None:
            self._edit.undo()

    def _do_redo(self):
        if self._edit is not None:
            self._edit.redo()

    def _on_more_toggled(self, on: bool):
        self._row2.setVisible(on)

    # ─── row 2 slots ────────────────────────────────────────────────────

    def _on_align(self, key: str):
        if self._edit is None:
            return
        # Metadata only: alignment renders on preview, never in the pane.
        self._merge_block_prop(ALIGN_PROP, key)
        self.format_applied.emit()
        self.refresh_state()

    def _on_spacing(self, value: float):
        self.set_deck_spacing(value)
        self.deck_format_changed.emit({"spacing": value})

    def set_theme_defaults(self, defaults: dict | None):
        """Adopt the active theme's baseline formatting (see _theme_defaults)."""
        self._theme_defaults = dict(defaults or {})
        self.refresh_state()

    def set_deck_format(self, fmt: dict | None):
        """Adopt the deck's top-script format (theme < deck < run)."""
        self._deck_format = dict(fmt or {})
        self.refresh_state()

    # ─── effective state: theme < deck < run ──────────────────────────
    # The buttons show what the DISPLAY will render for the caret: the
    # run's own props first, then the deck top-script, then the theme.
    # Toggles flip the EFFECTIVE value by writing an explicit run
    # override — clicking B on theme-bold text writes bold=false (the
    # text visibly un-bolds) instead of a redundant bold=true.

    def _run_char_format(self):
        """charFormat of the run under the caret (None without an editor).

        Selections read the editor cursor (the selection's format). A
        collapsed caret at a BLOCK start reads through a fresh cursor:
        the editor cursor there reports the typing format, not the run —
        so right after a card switch (caret reset to 0) the buttons
        would show the theme instead of the run under the caret.
        """
        if self._edit is None:
            return None
        if (self._typing_fmt is not None
                and self._typing_fmt[1] is not self._edit.document()):
            self._typing_fmt = None
        cur = self._edit.textCursor()
        if cur.hasSelection():
            return cur.charFormat()
        block = cur.block()
        if cur.position() == block.position():
            mark = self._typing_fmt
            if (mark is not None and mark[0] is self._edit
                    and mark[1] is self._edit.document()
                    and mark[2] == self._edit.document().revision()
                    and mark[3] == cur.position()):
                return mark[4]
            probe = QTextCursor(self._edit.document())
            probe.setPosition(cur.position())
            return probe.charFormat()
        return cur.charFormat()

    def _eff_bold(self) -> bool:
        cf = self._run_char_format()
        if cf is not None and cf.hasProperty(QTextFormat.Property.FontWeight):
            return cf.fontWeight() >= 600
        deck = self._deck_format.get("bold")
        if deck is not None:
            return bool(deck)
        return bool(self._theme_defaults.get("bold"))

    def _eff_italic(self) -> bool:
        cf = self._run_char_format()
        if cf is not None and cf.hasProperty(QTextFormat.Property.FontItalic):
            return bool(cf.fontItalic())
        deck = self._deck_format.get("italics")
        if deck is not None:
            return bool(deck)
        return False

    def _eff_underline(self) -> bool:
        cf = self._run_char_format()
        if cf is not None:
            if cf.hasProperty(UL_PROP):
                return bool(cf.property(UL_PROP))
            if cf.underlineStyle() != QTextCharFormat.UnderlineStyle.NoUnderline:
                return True  # legacy native (rich paste), no prop yet
        deck = self._deck_format.get("underline")
        if deck is not None:
            return bool(deck)
        return False

    def _eff_strike(self) -> bool:
        cf = self._run_char_format()
        if cf is not None:
            if cf.hasProperty(SO_PROP):
                return bool(cf.property(SO_PROP))
            if cf.hasProperty(QTextFormat.Property.FontStrikeOut):
                return bool(cf.fontStrikeOut())
        deck = self._deck_format.get("strike")
        if deck is not None:
            return bool(deck)
        return False

    @staticmethod
    def _offish(value) -> bool:
        return str(value).strip().lower() in ("none", "off", "")

    def _eff_outline(self) -> bool:
        cf = self._run_char_format()
        if cf is not None and cf.hasProperty(OUTLINE_PROP):
            raw = cf.property(OUTLINE_PROP)
            return bool(raw) and raw != OUTLINE_OFF
        deck = self._deck_format.get("outline")
        if deck is not None:
            return bool(deck) and not self._offish(deck)
        theme = self._theme_defaults.get("outline")
        if theme is None:
            return False
        if theme is True:
            return True
        return bool(theme) and not self._offish(theme)

    def _eff_shadow(self) -> bool:
        cf = self._run_char_format()
        if cf is not None and cf.hasProperty(SHADOW_PROP):
            raw = cf.property(SHADOW_PROP)
            return bool(raw) and raw != SHADOW_OFF
        deck = self._deck_format.get("shadow")
        if deck is not None:
            return bool(deck) and not self._offish(deck)
        theme = self._theme_defaults.get("shadow")
        if theme is None:
            return False
        return bool(theme) and not self._offish(theme)

    def _eff_case(self):
        """Effective case: run, deck, theme (None = no opinion)."""
        if self._edit is not None:
            cf = self._run_char_format()
            if cf.hasProperty(CASE_PROP):
                case_prop = cf.property(CASE_PROP)
                if case_prop in ("upper", "lower", "origin"):
                    return case_prop
            cap = cf.fontCapitalization()
            if cap in (QFont.Capitalization.AllUppercase,
                       QFont.Capitalization.SmallCaps):
                return "upper"
            if cap == QFont.Capitalization.AllLowercase:
                return "lower"
        deck = self._deck_format.get("case")
        if deck in ("upper", "lower", "origin"):
            return deck
        theme = self._theme_defaults.get("case")
        if theme in ("upper", "lower"):
            return theme
        return None

    def _eff_align(self) -> str:
        """Effective block alignment: block, deck, theme, left."""
        if self._edit is not None:
            bfmt = self._edit.textCursor().blockFormat()
            if bfmt.hasProperty(ALIGN_PROP):
                align_key = bfmt.property(ALIGN_PROP)
                if align_key in ("left", "center", "right", "justify"):
                    return align_key
            else:
                align = bfmt.alignment()
                if align and align != Qt.AlignmentFlag.AlignLeft:
                    if align & Qt.AlignmentFlag.AlignCenter:
                        return "center"
                    if align & Qt.AlignmentFlag.AlignRight:
                        return "right"
                    if align & Qt.AlignmentFlag.AlignJustify:
                        return "justify"
        deck = self._deck_format.get("align")
        if deck in ("left", "center", "right", "justify"):
            return deck
        theme = self._theme_defaults.get("align")
        if theme in ("left", "center", "right", "justify"):
            return theme
        return "left"

    def _baseline_outline_raw(self):
        """Deck outline wins over theme; explicit off -> None."""
        deck = self._deck_format.get("outline")
        if deck is not None:
            return None if self._offish(deck) else deck
        return self._theme_defaults.get("outline")

    def set_deck_spacing(self, value: float | None):
        """Reflect the deck's spacing in the menu (no signal)."""
        self._deck_spacing = value
        for v, act in self._spacing_actions.items():
            act.setChecked(v == value)

    def _on_spacing_custom(self):
        value, ok = dialogs.get_double(self, "Custom spacing",
                                           "Line spacing (0.5 – 3.0):",
                                           self._deck_spacing or 1.0,
                                           0.5, 3.0, 2)
        if ok:
            self._on_spacing(round(value, 2))

    def _toggle_list_prefix(self, ordered: bool):
        """Toggle a literal • / N. prefix on each selected block."""
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        doc = self._edit.document()
        start = doc.findBlock(cursor.selectionStart())
        end = doc.findBlock(cursor.selectionEnd())
        cursor.beginEditBlock()
        n = 0
        b = start
        # Flag wraps endEditBlock too: Qt defers the signals until the block
        # closes, which is when the designer reads the flag.
        with self._ribbon_merge():
            try:
                while True:
                    n += 1
                    text = b.text()
                    bcursor = QTextCursor(b)
                    if ordered:
                        import re as _re
                        m = _re.match(r"^\d+\.\s+", text)
                        if m:
                            bcursor.setPosition(b.position() + len(m.group(0)),
                                                QTextCursor.MoveMode.KeepAnchor)
                            bcursor.removeSelectedText()
                        else:
                            bcursor.setPosition(b.position())
                            bcursor.insertText(f"{n}. ")
                    else:
                        if text.startswith("• "):
                            bcursor.setPosition(b.position())
                            bcursor.setPosition(b.position() + 2,
                                                QTextCursor.MoveMode.KeepAnchor)
                            bcursor.removeSelectedText()
                        else:
                            bcursor.setPosition(b.position())
                            bcursor.insertText("• ")
                    if b == end:
                        break
                    b = b.next()
                    if not b.isValid():
                        break
            finally:
                cursor.endEditBlock()
        self.format_applied.emit()
        self.refresh_state()

    def _on_bullets(self):
        self._toggle_list_prefix(ordered=False)

    def _on_numbers(self):
        self._toggle_list_prefix(ordered=True)

    def _toggle_script(self, super_: bool):
        if self._edit is None:
            return
        from PyQt6.QtGui import QTextCharFormat as _CF
        want = (_CF.VerticalAlignment.AlignSuperScript if super_
                else _CF.VerticalAlignment.AlignSubScript)
        cur = self._edit.textCursor().charFormat().verticalAlignment()
        fmt = QTextCharFormat()
        fmt.setVerticalAlignment(
            _CF.VerticalAlignment.AlignNormal if cur == want else want)
        self._merge(fmt)

    def _on_case(self, upper: bool):
        fmt = QTextCharFormat()
        # Metadata only: case renders on preview, never in the pane.
        fmt.setProperty(CASE_PROP, "upper" if upper else "lower")
        self._merge(fmt)

    def _on_direction(self, rtl: bool):
        if self._edit is None:
            return
        self._merge_block_prop(
            DIR_PROP, "rtl" if rtl else "ltr")
        self.format_applied.emit()
        self.refresh_state()

    def _merge_block_prop(self, prop_id, value):
        """Merge one block metadata prop across the selection (or the
        cursor block when there is none). Native block metrics stay
        untouched, so the edit pane stays inviolable. Tier-4 deck scope
        routes through fan_out_block instead (deck-level align/dir)."""
        if self.fan_out_block is not None:
            with self._ribbon_merge():
                self.fan_out_block(prop_id, value)
            self.format_applied.emit()
            self.refresh_state()
            return
        if self._edit is None:
            return
        cursor = self._edit.textCursor()
        doc = self._edit.document()
        if cursor.hasSelection():
            start = doc.findBlock(cursor.selectionStart())
            end = doc.findBlock(cursor.selectionEnd())
        else:
            start = end = cursor.block()
        # Flag wraps endEditBlock too: Qt defers contentsChange until the
        # block closes, which is when the designer reads the flag.
        with self._ribbon_merge():
            cursor.beginEditBlock()
            try:
                block = start
                while True:
                    fmt = QTextBlockFormat()
                    fmt.setProperty(prop_id, value)
                    bcursor = QTextCursor(block)
                    bcursor.mergeBlockFormat(fmt)
                    if block == end or not block.next().isValid():
                        break
                    block = block.next()
            finally:
                cursor.endEditBlock()

    def _on_hr(self):
        if self._edit is None:
            return
        with self._ribbon_merge():
            insert_hr_at(self._edit.textCursor())
        self._edit.setFocus()
        self.format_applied.emit()

    def _set_text_chip_color(self, hex_color: str):
        if hex_color == self._text_chip_color:
            return
        self._text_chip_color = hex_color
        self._color_chip.setStyleSheet(
            "QLabel { background-color: " + hex_color +
            "; border: 1px solid " + SELECTION_BORDER + "; border-radius: 3px; }")

    # ─── cursor probing ─────────────────────────────────────────────────

    def refresh_state(self):
        """Mirror the effective formats onto the toggle buttons (cheap).

        Precedence: the run's own props (what the deck stores) first,
        then the theme baseline (what display already applies), so the
        ribbon shows what the operator will actually see on output.
        """
        theme = self._theme_defaults
        if self._edit is None:
            for b in (self._btn_italic, self._btn_strike,
                      self._btn_underline, self._btn_shadow,
                      self._btn_super,
                      self._btn_sub, self._btn_bullets, self._btn_numbers,
                      self._btn_rtl, self._btn_ltr,
                      *self._align_btns.values()):
                b.setChecked(False)
            self._btn_upper.setChecked(theme.get("case") == "upper")
            self._btn_lower.setChecked(theme.get("case") == "lower")
            # No caret: deck wins over theme (both beat nothing).
            self._btn_bold.setChecked(self._eff_bold())
            self._btn_italic.setChecked(self._eff_italic())
            self._btn_strike.setChecked(self._eff_strike())
            self._btn_underline.setChecked(self._eff_underline())
            self._set_text_chip_color(self._current_text_color())
            baseline_outline = self._baseline_outline_raw()
            self._btn_outline.setChecked(self._eff_outline())
            self._btn_outline_color.setVisible(False)
            self._outline_size.setVisible(False)
            self._btn_shadow.setChecked(self._eff_shadow())
            self._btn_shadow_color.setVisible(False)
            for s in (self._shadow_size, self._shadow_opacity,
                      self._shadow_distance, self._shadow_angle):
                s.setVisible(False)
            if baseline_outline and baseline_outline is not True:
                color, width = _parse_outline_value(baseline_outline)
                self._outline_color = color
                self._outline_width = width
                self._btn_outline_color.setStyleSheet(
                    f"color: {self._outline_color};")
                self._outline_size.blockSignals(True)
                self._outline_size.setValue(width)
                self._outline_size.blockSignals(False)
            for key, btn in self._align_btns.items():
                btn.setChecked(key == self._eff_align())
            self._sync_font_combo(self._current_font_family())
            return
        cursor = self._edit.textCursor()
        cf = self._run_char_format()
        # Buttons mirror the EFFECTIVE value (run, deck, theme — see the
        # _eff_* helpers): on theme-bold text B reads on, and clicking it
        # writes an explicit off, so the first click always does something
        # visible. The color/size knobs further down stay run-scoped: they
        # edit what the run itself carries.
        self._btn_bold.setChecked(self._eff_bold())
        self._btn_italic.setChecked(self._eff_italic())
        self._btn_strike.setChecked(self._eff_strike())
        self._btn_underline.setChecked(self._eff_underline())
        self._set_text_chip_color(self._current_text_color())
        # Outline/shadow buttons follow the effective state, and so do the
        # knobs: with no run prop they show the effective deck/theme
        # params, and the first knob touch seeds an explicit run override
        # from those (never a stale pick).
        outline_on = self._eff_outline()
        self._btn_outline.setChecked(outline_on)
        self._btn_outline_color.setVisible(outline_on)
        self._outline_size.setVisible(outline_on)
        # The swatch/size follow the run's own prop first, then the
        # effective deck/theme value.
        outline_raw = (cf.property(OUTLINE_PROP)
                       if cf.hasProperty(OUTLINE_PROP) else None)
        if outline_raw and outline_raw != OUTLINE_OFF:
            color, width = _parse_outline_value(outline_raw)
            self._outline_color = color
            self._outline_width = width
            self._btn_outline_color.setStyleSheet(f"color: {self._outline_color};")
            self._outline_size.blockSignals(True)
            self._outline_size.setValue(width)
            self._outline_size.blockSignals(False)
        elif outline_on:
            parts = self._outline_value_parts(
                self._deck_format.get("outline")) or \
                self._outline_value_parts(
                    self._theme_defaults.get("outline"))
            if parts:
                self._outline_color, self._outline_width = parts
                self._btn_outline_color.setStyleSheet(
                    f"color: {self._outline_color};")
                self._outline_size.blockSignals(True)
                self._outline_size.setValue(self._outline_width)
                self._outline_size.blockSignals(False)
        # Shadow: same split — effective state on the button and knobs,
        # run values first, then the effective deck value. (A theme shadow
        # is raw CSS, not knob-shaped, so its knobs keep last picks.)
        shadow_on = self._eff_shadow()
        self._btn_shadow.setChecked(shadow_on)
        self._btn_shadow_color.setVisible(shadow_on)
        for s in (self._shadow_size, self._shadow_opacity,
                  self._shadow_distance, self._shadow_angle):
            s.setVisible(shadow_on)
        shadow_raw = (cf.property(SHADOW_PROP)
                      if cf.hasProperty(SHADOW_PROP) else None)
        if shadow_raw and shadow_raw != SHADOW_OFF:
            parsed = _parse_shadow_value(shadow_raw)
            if parsed:
                (self._shadow_size_px, self._shadow_opacity_pct,
                 self._shadow_distance_px, self._shadow_color,
                 self._shadow_angle_deg) = parsed
                self._btn_shadow_color.setStyleSheet(
                    f"color: {self._shadow_color};")
                for s, v in ((self._shadow_size, self._shadow_size_px),
                             (self._shadow_opacity, self._shadow_opacity_pct),
                             (self._shadow_distance,
                              self._shadow_distance_px),
                             (self._shadow_angle, self._shadow_angle_deg)):
                    s.blockSignals(True)
                    s.setValue(v)
                    s.blockSignals(False)
        elif shadow_on:
            deck = self._deck_format.get("shadow")
            parsed = _parse_shadow_value(deck) \
                if isinstance(deck, str) and not self._offish(deck) else None
            if parsed:
                (self._shadow_size_px, self._shadow_opacity_pct,
                 self._shadow_distance_px, self._shadow_color,
                 self._shadow_angle_deg) = parsed
                self._btn_shadow_color.setStyleSheet(
                    f"color: {self._shadow_color};")
                for s, v in ((self._shadow_size, self._shadow_size_px),
                             (self._shadow_opacity, self._shadow_opacity_pct),
                             (self._shadow_distance,
                              self._shadow_distance_px),
                             (self._shadow_angle, self._shadow_angle_deg)):
                    s.blockSignals(True)
                    s.setValue(v)
                    s.blockSignals(False)
        va = cf.verticalAlignment()
        self._btn_super.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSuperScript)
        self._btn_sub.setChecked(
            va == QTextCharFormat.VerticalAlignment.AlignSubScript)
        cap = self._eff_case()
        self._btn_upper.setChecked(cap == "upper")
        self._btn_lower.setChecked(cap == "lower")
        for key, btn in self._align_btns.items():
            btn.setChecked(key == self._eff_align())
        bfmt = cursor.blockFormat()
        if bfmt.hasProperty(DIR_PROP):
            rtl = bfmt.property(DIR_PROP) == "rtl"
        else:
            rtl = (bfmt.layoutDirection() == Qt.LayoutDirection.RightToLeft)
        self._btn_rtl.setChecked(rtl)
        self._btn_ltr.setChecked(not rtl)
        text = cursor.block().text()
        self._btn_bullets.setChecked(text.startswith("• "))
        import re as _re
        self._btn_numbers.setChecked(bool(_re.match(r"^\d+\.\s+", text)))
        self._size_combo.setCurrentText(str(self._current_size_px()))
        self._sync_font_combo(self._current_font_family())
