"""
loading_screen.py — Loading screen displayed during app initialization.

Static RhemaCast mark: the brand SVG artwork (asymmetric waveform bars),
recolored from the app theme at load time — tile from bg_app, bars lerped
along the accent ramp by bar height. No timers, no motion. The same
renderer backs the header logo and window icon via mark_pixmap(), so
every logo in the app follows ui/app_theme.py.
"""

import os

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer, QRectF, QByteArray
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QRadialGradient
from PyQt6.QtSvg import QSvgRenderer

from ui.styles import (
    TEXT_PRIMARY, TEXT_MUTED, TEXT_FAINT,
    ACCENT, ACCENT_LIGHT, SELECTION_TEXT, BG_APP,
)

# Bar lengths in the 64-unit brand artwork (center line y=32).
_BAR_LENGTHS = (0, 14, 14, 18, 8)

_BG_CENTER = "#180b28"
_BG_EDGE = "#060005"

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")


def _lerp(lo: QColor, hi: QColor, t: float) -> QColor:
    t = min(1.0, max(0.0, t))
    return QColor(
        round(lo.red() + (hi.red() - lo.red()) * t),
        round(lo.green() + (hi.green() - lo.green()) * t),
        round(lo.blue() + (hi.blue() - lo.blue()) * t),
    )


def brand_svg_bytes() -> bytes:
    """Brand artwork with theme colors substituted (tile + bar ramp)."""
    with open(os.path.join(_ASSETS_DIR, "brand-mark.svg"),
              encoding="utf-8") as f:
        template = f.read()
    tallest = max(_BAR_LENGTHS)
    ramp = [_lerp(QColor(ACCENT), QColor(ACCENT_LIGHT),
                  length / tallest).name()
            for length in _BAR_LENGTHS]
    out = template.replace("__TILE__", QColor(BG_APP).name())
    for i, color in enumerate(ramp):
        out = out.replace(f"__BAR{i}__", color)
    return out.encode("utf-8")


def _renderer() -> QSvgRenderer:
    return QSvgRenderer(QByteArray(brand_svg_bytes()))


class BrandMark(QWidget):
    """Static brand tile; size in pixels (square). Rendered from the
    theme-recolored brand SVG, so the artwork is exact at any size."""

    def __init__(self, size: int = 150, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        # Transparent corners outside the tile's rounded rect.
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAutoFillBackground(False)
        self._renderer = _renderer()

    def paintEvent(self, event):
        p = QPainter(self)
        self._renderer.render(p, QRectF(self.rect()))
        p.end()


def mark_pixmap(size: int) -> QPixmap:
    """Render the theme-bound mark to a transparent pixmap (icons, headers)."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    p = QPainter(pixmap)
    _renderer().render(p, QRectF(0, 0, size, size))
    p.end()
    return pixmap


class LoadingDots(QWidget):
    """Three static loader dots in accent tones."""

    _COLORS = (ACCENT, ACCENT_LIGHT, SELECTION_TEXT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(3 * 16, 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, color in enumerate(self._COLORS):
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(5 + i * 16, 2, 6, 6))
        p.end()


class LoadingScreen(QWidget):
    """Full-screen loading overlay shown during app initialization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 380)

        self._status_index = 0
        self._init_ui()
        self._start_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 26, 40, 26)
        layout.setSpacing(0)

        # ── Brand mark (static artwork, theme colors) ──
        self._mark = BrandMark(150)
        mark_row = QHBoxLayout()
        mark_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_row.addWidget(self._mark)
        layout.addLayout(mark_row)

        layout.addSpacing(22)

        # ── Wordmark: Rhema bright, Cast light purple ──
        wordmark = QLabel()
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark.setText(
            '<span style="color: ' + TEXT_PRIMARY + '; font-size: 32px; '
            'font-weight: 700; letter-spacing: 0.5px;">Rhema</span>'
            '<span style="color: ' + ACCENT_LIGHT + '; font-size: 32px; '
            'font-weight: 700;">Cast</span>'
        )
        wordmark.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(wordmark, 0, Qt.AlignmentFlag.AlignCenter)

        # ── Tagline ──
        tagline = QLabel("WORD IN REAL TIME")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 5px;
        """)
        layout.addWidget(tagline, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(20)

        # ── Loader dots ──
        self._dots = LoadingDots()
        dots_row = QHBoxLayout()
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots_row.addWidget(self._dots)
        layout.addLayout(dots_row)

        layout.addSpacing(10)

        # ── Status text ──
        self._status_label = QLabel("Initializing...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"""
            color: {TEXT_FAINT};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.5px;
            text-transform: uppercase;
        """)
        layout.addWidget(self._status_label, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    def _start_timer(self):
        self._statuses = [
            "Initializing...",
            "Loading transcription engine...",
            "Preparing search indexes...",
            "Starting services...",
        ]
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._rotate_status)
        self._status_timer.start(2200)

    def _rotate_status(self):
        self._status_index = (self._status_index + 1) % len(self._statuses)
        self._status_label.setText(self._statuses[self._status_index])

    def set_status(self, text: str):
        self._status_label.setText(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QRadialGradient(
            self.width() / 2.0, self.height() * 0.38,
            max(self.width(), self.height()) * 0.75)
        grad.setColorAt(0.0, QColor(_BG_CENTER))
        grad.setColorAt(0.65, QColor(_BG_EDGE))
        grad.setColorAt(1.0, QColor(_BG_EDGE))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        painter.end()


class LoadingDots(QWidget):
    """Three static loader dots in accent tones."""

    _COLORS = (ACCENT, ACCENT_LIGHT, SELECTION_TEXT)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(3 * 16, 10)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, color in enumerate(self._COLORS):
            p.setBrush(QColor(color))
            p.drawEllipse(QRectF(5 + i * 16, 2, 6, 6))
        p.end()


class LoadingScreen(QWidget):
    """Full-screen loading overlay shown during app initialization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 380)

        self._status_index = 0
        self._init_ui()
        self._start_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 26, 40, 26)
        layout.setSpacing(0)

        # ── Brand mark (static, theme-bound) ──
        self._mark = BrandMark(150)
        mark_row = QHBoxLayout()
        mark_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark_row.addWidget(self._mark)
        layout.addLayout(mark_row)

        layout.addSpacing(22)

        # ── Wordmark: Rhema bright, Cast light purple ──
        wordmark = QLabel()
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark.setText(
            '<span style="color: ' + TEXT_PRIMARY + '; font-size: 32px; '
            'font-weight: 700; letter-spacing: 0.5px;">Rhema</span>'
            '<span style="color: ' + ACCENT_LIGHT + '; font-size: 32px; '
            'font-weight: 700;">Cast</span>'
        )
        wordmark.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(wordmark, 0, Qt.AlignmentFlag.AlignCenter)

        # ── Tagline ──
        tagline = QLabel("WORD IN REAL TIME")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"""
            color: {TEXT_MUTED};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 5px;
        """)
        layout.addWidget(tagline, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(20)

        # ── Loader dots ──
        self._dots = LoadingDots()
        dots_row = QHBoxLayout()
        dots_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots_row.addWidget(self._dots)
        layout.addLayout(dots_row)

        layout.addSpacing(10)

        # ── Status text ──
        self._status_label = QLabel("Initializing...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"""
            color: {TEXT_FAINT};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 1.5px;
            text-transform: uppercase;
        """)
        layout.addWidget(self._status_label, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addStretch()

    def _start_timer(self):
        self._statuses = [
            "Initializing...",
            "Loading transcription engine...",
            "Preparing search indexes...",
            "Starting services...",
        ]
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._rotate_status)
        self._status_timer.start(2200)

    def _rotate_status(self):
        self._status_index = (self._status_index + 1) % len(self._statuses)
        self._status_label.setText(self._statuses[self._status_index])

    def set_status(self, text: str):
        self._status_label.setText(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        grad = QRadialGradient(
            self.width() / 2.0, self.height() * 0.38,
            max(self.width(), self.height()) * 0.75)
        grad.setColorAt(0.0, QColor(_BG_CENTER))
        grad.setColorAt(0.65, QColor(_BG_EDGE))
        grad.setColorAt(1.0, QColor(_BG_EDGE))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        painter.end()
