"""
ui/widgets/theme_animations_panel.py

Animations editor panel for the theme designer.
Provides three animation cards (Display Enter, Between Slides, Display Exit)
with timeline visualizations and property controls, plus an easing reference table.
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QComboBox, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QLinearGradient

from ui.styles import SLATE_500, SLATE_400, WHITE, BLUE_500


# ─── Shared Styles ──────────────────────────────────────────────────────────

_COMBO_STYLE = (
    "QComboBox {"
    "  background: rgba(0,0,0,0.3);"
    "  border: 1px solid rgba(255,255,255,0.08);"
    "  border-radius: 4px;"
    "  padding: 2px 6px;"
    "  color: #f8fafc;"
    "  font-size: 10px;"
    "  min-height: 20px;"
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

_SECTION_STYLE = (
    "background: transparent;"
    "border: none;"
    "color: #475569;"
    "font-size: 9px;"
    "font-weight: 700;"
    "text-transform: uppercase;"
    "letter-spacing: 1px;"
)


# ─── Animation Types ────────────────────────────────────────────────────────

ANIMATION_TYPES = {
    "display_enter": ["fade_up", "fade_in", "scale_up", "slide_up", "typewriter"],
    "between_slides_out": ["fade_down", "fade_out", "scale_down", "slide_down"],
    "between_slides_in": ["fade_up", "fade_in", "scale_up", "slide_up"],
    "display_exit": ["fade_down", "fade_out", "scale_down", "slide_down"],
}


# ─── Timeline Widget ────────────────────────────────────────────────────────

class TimelineWidget(QWidget):
    """Decorative 28px timeline bar with track and keyframe dots."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setMinimumWidth(100)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # Background
        painter.setBrush(QColor(0, 0, 0, 76))  # rgba(0,0,0,0.3)
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))  # 1px border
        painter.drawRoundedRect(0, 0, w, h, 6, 6)

        # Track line (4px height, centered)
        track_y = h // 2 - 2
        gradient = QLinearGradient(12, 0, w - 12, 0)
        gradient.setColorAt(0, QColor(59, 130, 246, 0))  # start transparent
        gradient.setColorAt(0.15, QColor(59, 130, 246, 76))  # 30% opacity
        gradient.setColorAt(0.85, QColor(59, 130, 246, 76))
        gradient.setColorAt(1, QColor(59, 130, 246, 0))  # end transparent
        painter.setBrush(gradient)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(12, track_y, w - 24, 4, 2, 2)

        # Keyframe dots at 20%, 50%, 80%
        dot_positions = [0.20, 0.50, 0.80]
        for pct in dot_positions:
            cx = int(12 + (w - 24) * pct)
            cy = h // 2

            # Outer ring
            painter.setBrush(QColor(59, 130, 246, 255))  # blue
            painter.setPen(QPen(QColor(255, 255, 255, 51), 2))  # 2px border
            painter.drawEllipse(cx - 5, cy - 5, 10, 10)

        painter.end()


# ─── Toggle Switch ──────────────────────────────────────────────────────────

class ToggleSwitch(QPushButton):
    """30x16 toggle switch button. Cyan when on, slate when off."""

    toggled_state = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(30, 16)
        self.setCheckable(True)
        self.setChecked(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(self._style(True))
        self.clicked.connect(self._on_click)

    def _style(self, on: bool) -> str:
        if on:
            return (
                "QPushButton {"
                "  background: #22d3ee;"
                "  border: none;"
                "  border-radius: 8px;"
                "}"
                "QPushButton::indicator {"
                "  width: 12px; height: 12px;"
                "  border-radius: 6px;"
                "  background: white;"
                "  margin: 2px;"
                "}"
                "QPushButton:checked::indicator {"
                "  margin-left: 16px;"
                "}"
            )
        else:
            return (
                "QPushButton {"
                "  background: #475569;"
                "  border: none;"
                "  border-radius: 8px;"
                "}"
                "QPushButton::indicator {"
                "  width: 12px; height: 12px;"
                "  border-radius: 6px;"
                "  background: #94a3b8;"
                "  margin: 2px;"
                "}"
                "QPushButton:checked::indicator {"
                "  margin-left: 16px;"
                "}"
            )

    def _on_click(self, checked):
        self.setStyleSheet(self._style(checked))
        self.toggled_state.emit(checked)

    def is_on(self) -> bool:
        return self.isChecked()


# ─── Badge Label ────────────────────────────────────────────────────────────

class BadgeLabel(QLabel):
    """Small colored badge: cyan for "In", amber for "Cycle", red for "Out"."""

    _COLORS = {
        "In": ("#22d3ee", "rgba(34,211,238,0.15)"),
        "Cycle": ("#f59e0b", "rgba(245,158,11,0.15)"),
        "Out": ("#ef4444", "rgba(239,68,68,0.15)"),
    }

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        color, bg = self._COLORS.get(text, ("#94a3b8", "rgba(148,163,184,0.15)"))
        self.setStyleSheet(
            f"background: {bg};"
            f"color: {color};"
            "border: none;"
            "border-radius: 4px;"
            "padding: 1px 6px;"
            "font-size: 9px;"
            "font-weight: 700;"
            "text-transform: uppercase;"
            "letter-spacing: 0.5px;"
        )


# ─── Animation Card ────────────────────────────────────────────────────────

class AnimationCard(QFrame):
    """Single animation card with header, timeline, and property rows."""

    card_changed = pyqtSignal()

    def __init__(
        self,
        title: str,
        badge_text: str,
        type_key: str,
        anim_options: list[str],
        parent=None,
    ):
        super().__init__(parent)
        self._type_key = type_key
        self._anim_options = anim_options

        self.setStyleSheet(
            "QFrame {"
            "  background: transparent;"
            "  padding: 10px 16px;"
            "  border-bottom: 1px solid rgba(255,255,255,0.04);"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Header row ──
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "background: transparent;"
            "border: none;"
            "color: #f8fafc;"
            "font-size: 11px;"
            "font-weight: 700;"
        )
        header.addWidget(title_lbl)

        header.addWidget(BadgeLabel(badge_text))
        header.addStretch()

        self._toggle = ToggleSwitch()
        self._toggle.toggled_state.connect(self._on_toggle)
        header.addWidget(self._toggle)

        layout.addLayout(header)

        # ── Timeline ──
        self._timeline = TimelineWidget()
        layout.addWidget(self._timeline)

        # ── Property rows ──
        props_layout = QHBoxLayout()
        props_layout.setContentsMargins(0, 0, 0, 0)
        props_layout.setSpacing(8)

        # Type row
        type_col = QVBoxLayout()
        type_col.setSpacing(2)
        type_lbl = QLabel("TYPE")
        type_lbl.setStyleSheet(_LABEL_STYLE)
        type_col.addWidget(type_lbl)

        self._type_combo = QComboBox()
        self._type_combo.setFixedHeight(24)
        self._type_combo.addItems(self._anim_options)
        self._type_combo.setStyleSheet(_COMBO_STYLE)
        self._type_combo.currentTextChanged.connect(self._on_change)
        type_col.addWidget(self._type_combo)
        props_layout.addLayout(type_col, 1)

        # Duration row
        dur_col = QVBoxLayout()
        dur_col.setSpacing(2)
        dur_lbl = QLabel("DURATION")
        dur_lbl.setStyleSheet(_LABEL_STYLE)
        dur_col.addWidget(dur_lbl)

        self._duration_input = QLineEdit("600")
        self._duration_input.setFixedHeight(24)
        self._duration_input.setPlaceholderText("ms")
        self._duration_input.setStyleSheet(_INPUT_STYLE)
        self._duration_input.textChanged.connect(self._on_change)
        dur_col.addWidget(self._duration_input)
        props_layout.addLayout(dur_col, 1)

        layout.addLayout(props_layout)

    def _on_toggle(self, on: bool):
        self._type_combo.setEnabled(on)
        self._duration_input.setEnabled(on)
        self.card_changed.emit()

    def _on_change(self, *_args):
        self.card_changed.emit()

    def set_enabled(self, on: bool):
        self._toggle.blockSignals(True)
        self._toggle.setChecked(on)
        self._toggle.setStyleSheet(self._toggle._style(on))
        self._type_combo.setEnabled(on)
        self._duration_input.setEnabled(on)
        self._toggle.blockSignals(False)

    def set_type(self, value: str):
        self._type_combo.blockSignals(True)
        idx = self._type_combo.findText(value)
        if idx >= 0:
            self._type_combo.setCurrentIndex(idx)
        else:
            self._type_combo.setCurrentText(value)
        self._type_combo.blockSignals(False)

    def get_type(self) -> str:
        return self._type_combo.currentText()

    def set_duration(self, ms: int):
        self._duration_input.blockSignals(True)
        self._duration_input.setText(str(ms))
        self._duration_input.blockSignals(False)

    def get_duration(self) -> int:
        try:
            return int(self._duration_input.text())
        except ValueError:
            return 600

    def is_enabled(self) -> bool:
        return self._toggle.is_on()


# ─── Between Slides Card (special: has out + in type rows) ─────────────────

class BetweenSlidesCard(QFrame):
    """Between Slides animation card with out_type and in_type combo boxes."""

    card_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setStyleSheet(
            "QFrame {"
            "  background: transparent;"
            "  padding: 10px 16px;"
            "  border-bottom: 1px solid rgba(255,255,255,0.04);"
            "}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # ── Header ──
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(6)

        title_lbl = QLabel("Between Slides")
        title_lbl.setStyleSheet(
            "background: transparent;"
            "border: none;"
            "color: #f8fafc;"
            "font-size: 11px;"
            "font-weight: 700;"
        )
        header.addWidget(title_lbl)

        header.addWidget(BadgeLabel("Cycle"))
        header.addStretch()

        self._toggle = ToggleSwitch()
        self._toggle.toggled_state.connect(self._on_toggle)
        header.addWidget(self._toggle)

        layout.addLayout(header)

        # ── Timeline ──
        self._timeline = TimelineWidget()
        layout.addWidget(self._timeline)

        # ── Out type row ──
        out_row = QHBoxLayout()
        out_row.setContentsMargins(0, 0, 0, 0)
        out_row.setSpacing(8)

        out_col = QVBoxLayout()
        out_col.setSpacing(2)
        out_lbl = QLabel("OUT TYPE")
        out_lbl.setStyleSheet(_LABEL_STYLE)
        out_col.addWidget(out_lbl)

        self._out_combo = QComboBox()
        self._out_combo.setFixedHeight(24)
        self._out_combo.addItems(ANIMATION_TYPES["between_slides_out"])
        self._out_combo.setStyleSheet(_COMBO_STYLE)
        self._out_combo.currentTextChanged.connect(self._on_change)
        out_col.addWidget(self._out_combo)
        out_row.addLayout(out_col, 1)

        in_col = QVBoxLayout()
        in_col.setSpacing(2)
        in_lbl = QLabel("IN TYPE")
        in_lbl.setStyleSheet(_LABEL_STYLE)
        in_col.addWidget(in_lbl)

        self._in_combo = QComboBox()
        self._in_combo.setFixedHeight(24)
        self._in_combo.addItems(ANIMATION_TYPES["between_slides_in"])
        self._in_combo.setStyleSheet(_COMBO_STYLE)
        self._in_combo.currentTextChanged.connect(self._on_change)
        in_col.addWidget(self._in_combo)
        out_row.addLayout(in_col, 1)

        layout.addLayout(out_row)

        # ── Duration row ──
        dur_row = QHBoxLayout()
        dur_row.setContentsMargins(0, 0, 0, 0)
        dur_row.setSpacing(8)

        dur_col = QVBoxLayout()
        dur_col.setSpacing(2)
        dur_lbl = QLabel("DURATION")
        dur_lbl.setStyleSheet(_LABEL_STYLE)
        dur_col.addWidget(dur_lbl)

        self._duration_input = QLineEdit("400")
        self._duration_input.setFixedHeight(24)
        self._duration_input.setPlaceholderText("ms")
        self._duration_input.setStyleSheet(_INPUT_STYLE)
        self._duration_input.textChanged.connect(self._on_change)
        dur_col.addWidget(self._duration_input)
        dur_row.addLayout(dur_col, 1)

        # Easing row (placeholder to balance layout)
        eas_col = QVBoxLayout()
        eas_col.setSpacing(2)
        eas_lbl = QLabel("EASING")
        eas_lbl.setStyleSheet(_LABEL_STYLE)
        eas_col.addWidget(eas_lbl)

        self._easing_combo = QComboBox()
        self._easing_combo.setFixedHeight(24)
        self._easing_combo.addItems([
            "ease-in-out", "ease-in", "ease-out", "linear",
            "cubic-bezier", "snap",
        ])
        self._easing_combo.setStyleSheet(_COMBO_STYLE)
        self._easing_combo.currentTextChanged.connect(self._on_change)
        eas_col.addWidget(self._easing_combo)
        dur_row.addLayout(eas_col, 1)

        layout.addLayout(dur_row)

    def _on_toggle(self, on: bool):
        self._out_combo.setEnabled(on)
        self._in_combo.setEnabled(on)
        self._duration_input.setEnabled(on)
        self._easing_combo.setEnabled(on)
        self.card_changed.emit()

    def _on_change(self, *_args):
        self.card_changed.emit()

    def set_enabled(self, on: bool):
        self._toggle.blockSignals(True)
        self._toggle.setChecked(on)
        self._toggle.setStyleSheet(self._toggle._style(on))
        self._out_combo.setEnabled(on)
        self._in_combo.setEnabled(on)
        self._duration_input.setEnabled(on)
        self._easing_combo.setEnabled(on)
        self._toggle.blockSignals(False)

    def set_out_type(self, value: str):
        self._out_combo.blockSignals(True)
        idx = self._out_combo.findText(value)
        if idx >= 0:
            self._out_combo.setCurrentIndex(idx)
        self._out_combo.blockSignals(False)

    def get_out_type(self) -> str:
        return self._out_combo.currentText()

    def set_in_type(self, value: str):
        self._in_combo.blockSignals(True)
        idx = self._in_combo.findText(value)
        if idx >= 0:
            self._in_combo.setCurrentIndex(idx)
        self._in_combo.blockSignals(False)

    def get_in_type(self) -> str:
        return self._in_combo.currentText()

    def set_duration(self, ms: int):
        self._duration_input.blockSignals(True)
        self._duration_input.setText(str(ms))
        self._duration_input.blockSignals(False)

    def get_duration(self) -> int:
        try:
            return int(self._duration_input.text())
        except ValueError:
            return 400

    def set_easing(self, value: str):
        self._easing_combo.blockSignals(True)
        idx = self._easing_combo.findText(value)
        if idx >= 0:
            self._easing_combo.setCurrentIndex(idx)
        self._easing_combo.blockSignals(False)

    def get_easing(self) -> str:
        return self._easing_combo.currentText()

    def is_enabled(self) -> bool:
        return self._toggle.is_on()


# ─── Easing Reference Section ───────────────────────────────────────────────

class EasingReference(QWidget):
    """Reference table showing 4 common easing curves."""

    EASINGS = [
        ("ease-out", "Fast start → slow end", "Decelerate into position"),
        ("ease-in", "Slow start → fast end", "Accelerate away from start"),
        ("ease-in-out", "Slow → fast → slow", "Smooth both edges"),
        ("linear", "Constant speed", "No acceleration curve"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        section_lbl = QLabel("EASING REFERENCE")
        section_lbl.setStyleSheet(_SECTION_STYLE)
        layout.addWidget(section_lbl)

        table = QFrame()
        table.setStyleSheet(
            "QFrame {"
            "  background: transparent;"
            "  border-bottom: 1px solid rgba(255,255,255,0.04);"
            "  padding: 6px 16px;"
            "}"
        )
        table_layout = QVBoxLayout(table)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.setSpacing(2)

        for name, curve, description in self.EASINGS:
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)

            # Easing name
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(90)
            name_lbl.setStyleSheet(
                "background: transparent;"
                "border: none;"
                "color: #60a5fa;"
                "font-size: 10px;"
                "font-weight: 600;"
                "font-family: 'Courier New', monospace;"
            )
            row.addWidget(name_lbl)

            # Mini curve indicator (just a colored dot)
            dot = QLabel()
            dot.setFixedSize(8, 8)
            dot.setStyleSheet(
                "background: rgba(59,130,246,0.3);"
                "border: 1px solid rgba(59,130,246,0.5);"
                "border-radius: 4px;"
            )
            row.addWidget(dot)

            # Description
            desc_lbl = QLabel(f"{curve} — {description}")
            desc_lbl.setStyleSheet(
                "background: transparent;"
                "border: none;"
                "color: #64748b;"
                "font-size: 10px;"
            )
            row.addWidget(desc_lbl, 1)

            row.addStretch()

            table_layout.addLayout(row)

        layout.addWidget(table)


# ─── Main Panel ─────────────────────────────────────────────────────────────

class ThemeAnimationsPanel(QWidget):
    """Animations editor panel for the theme designer."""

    animations_changed = pyqtSignal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._loading = False

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ── Display Enter card ──
        self._display_enter = AnimationCard(
            title="Display Enter",
            badge_text="In",
            type_key="display_enter",
            anim_options=ANIMATION_TYPES["display_enter"],
        )
        self._display_enter.card_changed.connect(self._on_edit)
        main_layout.addWidget(self._display_enter)

        # ── Between Slides card ──
        self._between_slides = BetweenSlidesCard()
        self._between_slides.card_changed.connect(self._on_edit)
        main_layout.addWidget(self._between_slides)

        # ── Display Exit card ──
        self._display_exit = AnimationCard(
            title="Display Exit",
            badge_text="Out",
            type_key="display_exit",
            anim_options=ANIMATION_TYPES["display_exit"],
        )
        self._display_exit.card_changed.connect(self._on_edit)
        main_layout.addWidget(self._display_exit)

        # ── Easing Reference ──
        self._easing_ref = EasingReference()
        main_layout.addWidget(self._easing_ref)

        main_layout.addStretch()

    def _on_edit(self):
        if self._loading:
            return
        self.animations_changed.emit(self.get_animations())

    def load_animations(self, anim_dict: dict):
        """Load animation state from dict structure."""
        self._loading = True

        # Display Enter
        de = anim_dict.get("display_enter", {})
        self._display_enter.set_type(de.get("type", "fade_up"))
        self._display_enter.set_duration(de.get("duration_ms", 600))
        self._display_enter.set_enabled(de.get("type") is not None)

        # Between Slides
        bs = anim_dict.get("between_slides", {})
        out_type = bs.get("out_type", "fade_down")
        in_type = bs.get("in_type", "fade_up")
        self._between_slides.set_out_type(out_type)
        self._between_slides.set_in_type(in_type)
        self._between_slides.set_duration(bs.get("duration_ms", 400))
        self._between_slides.set_easing(bs.get("easing", "ease-in-out"))
        has_between = bool(bs.get("out_type") or bs.get("in_type"))
        self._between_slides.set_enabled(has_between)

        # Display Exit
        dx = anim_dict.get("display_exit", {})
        self._display_exit.set_type(dx.get("type", "fade_down"))
        self._display_exit.set_duration(dx.get("duration_ms", 400))
        self._display_exit.set_enabled(dx.get("type") is not None)

        self._loading = False

    def get_animations(self) -> dict:
        """Return current animation state as a dict."""
        result = {}

        if self._display_enter.is_enabled():
            result["display_enter"] = {
                "type": self._display_enter.get_type(),
                "duration_ms": self._display_enter.get_duration(),
                "easing": "ease-out",
            }
        else:
            result["display_enter"] = {
                "type": None,
                "duration_ms": self._display_enter.get_duration(),
                "easing": "ease-out",
            }

        if self._between_slides.is_enabled():
            result["between_slides"] = {
                "out_type": self._between_slides.get_out_type(),
                "in_type": self._between_slides.get_in_type(),
                "duration_ms": self._between_slides.get_duration(),
                "easing": self._between_slides.get_easing(),
            }
        else:
            result["between_slides"] = {
                "out_type": None,
                "in_type": None,
                "duration_ms": self._between_slides.get_duration(),
                "easing": self._between_slides.get_easing(),
            }

        if self._display_exit.is_enabled():
            result["display_exit"] = {
                "type": self._display_exit.get_type(),
                "duration_ms": self._display_exit.get_duration(),
                "easing": "ease-out",
            }
        else:
            result["display_exit"] = {
                "type": None,
                "duration_ms": self._display_exit.get_duration(),
                "easing": "ease-out",
            }

        return result
