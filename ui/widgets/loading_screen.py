"""
loading_screen.py — Loading screen displayed during app initialization.

Static RhemaCast logo with wordmark and status message.
"""

import os
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap, QColor, QPainter


BG_COLOR = "#070b16"
CAST_COLOR = "#e0b93d"
TAGLINE_COLOR = "#7f8ba3"
STATUS_COLOR = "#5f6b82"


class LoadingScreen(QWidget):
    """Full-screen loading overlay shown during app initialization."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(520, 340)

        self._status_index = 0
        self._init_ui()
        self._start_timer()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(0)

        # ── Static logo SVG ──
        logo_label = QLabel()
        logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        assets_dir = os.path.join(os.path.dirname(__file__), "..", "assets")
        icon_path = os.path.join(assets_dir, "icon.svg")
        if os.path.exists(icon_path):
            pixmap = QPixmap(icon_path).scaled(
                130, 130, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            logo_label.setPixmap(pixmap)
        else:
            logo_label.setText("♫")
            logo_label.setStyleSheet("font-size: 60px; color: #38bdf8;")
        layout.addWidget(logo_label, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(16)

        # ── Wordmark ──
        wordmark = QLabel()
        wordmark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wordmark.setText(
            '<span style="color: #e7ecf5; font-size: 32px; font-weight: 700; '
            'letter-spacing: 0.5px;">Rhema</span>'
            f'<span style="color: {CAST_COLOR}; font-size: 32px; font-weight: 700;">Cast</span>'
        )
        wordmark.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(wordmark, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(4)

        # ── Tagline ──
        tagline = QLabel("WORD IN REAL TIME")
        tagline.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tagline.setStyleSheet(f"""
            color: {TAGLINE_COLOR};
            font-size: 10px;
            font-weight: 600;
            letter-spacing: 5px;
        """)
        layout.addWidget(tagline, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(28)

        # ── Static dots ──
        dots = QLabel()
        dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dots.setTextFormat(Qt.TextFormat.RichText)
        dots.setText(
            '<span style="display:inline-block;width:7px;height:7px;border-radius:4px;'
            f'background-color:#38bdf8;margin:0 5px;"></span>'
            '<span style="display:inline-block;width:7px;height:7px;border-radius:4px;'
            f'background-color:#8fd0f2;margin:0 5px;"></span>'
            '<span style="display:inline-block;width:7px;height:7px;border-radius:4px;'
            f'background-color:#e0b93d;margin:0 5px;"></span>'
        )
        layout.addWidget(dots, 0, Qt.AlignmentFlag.AlignCenter)

        layout.addSpacing(10)

        # ── Status text ──
        self._status_label = QLabel("Initializing...")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._status_label.setStyleSheet(f"""
            color: {STATUS_COLOR};
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
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._rotate_status)
        self._timer.start(2200)

    def _rotate_status(self):
        self._status_index = (self._status_index + 1) % len(self._statuses)
        self._status_label.setText(self._statuses[self._status_index])

    def set_status(self, text: str):
        self._status_label.setText(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(BG_COLOR))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), 12, 12)
        painter.end()
