"""
ui/panels/live_preview_panel.py

Center panel: Preview (left) + Live (right) + macro controls under Live.
Each viewport is a QWebEngineView rendering the same HTML/CSS/JS as OBS.
"""

import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSplitter
)
from PyQt6.QtGui import QIcon, QMouseEvent
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QEvent

from ui.widgets.display_view import DisplayView
from ui.widgets.aspect_ratio import AspectRatioWidget
from ui.styles import (
    MACRO_BTN_AMBER, MACRO_BTN_CLEAR,
    PANEL_HEADER_STYLE, PANEL_HEADER_LABEL_STYLE, PANEL_BODY_STYLE,
    RED_500
)


class PreviewOverlay(QWidget):
    """Transparent overlay that captures double-clicks on the preview viewport."""
    double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAutoFillBackground(False)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.double_clicked.emit()

    def mousePressEvent(self, event: QMouseEvent):
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        event.accept()

    def wheelEvent(self, event):
        event.accept()


class LivePreviewPanel(QWidget):
    """Center panel: Preview (left) + Live (right) + macro controls."""

    clear_recall = pyqtSignal()
    prev_verse = pyqtSignal()
    next_verse = pyqtSignal()
    preview_double_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # ── Splitter: Preview (left) | Live (right) ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # ── Preview Panel (left) ──
        preview_panel = QWidget()
        preview_panel.setStyleSheet(PANEL_BODY_STYLE)
        preview_panel_layout = QVBoxLayout(preview_panel)
        preview_panel_layout.setContentsMargins(8, 8, 8, 8)
        preview_panel_layout.setSpacing(8)

        preview_header = QWidget()
        preview_header.setStyleSheet(PANEL_HEADER_STYLE)
        preview_header_layout = QHBoxLayout(preview_header)
        preview_header_layout.setContentsMargins(12, 6, 12, 6)
        preview_title = QLabel("OPERATOR PREVIEW")
        preview_title.setStyleSheet(PANEL_HEADER_LABEL_STYLE)
        preview_header_layout.addWidget(preview_title)
        preview_header_layout.addStretch()
        preview_panel_layout.addWidget(preview_header)

        self.preview_frame = QFrame()
        self.preview_frame.setObjectName("OperatorPreviewViewport")
        self.preview_frame.setStyleSheet("""
            QFrame#OperatorPreviewViewport {
                background: black;
                border: 1px solid rgba(59, 130, 246, 0.2);
                border-radius: 6px;
            }
        """)

        self.preview_view = DisplayView(live_mode=False)
        self.preview_view.setMinimumHeight(1)

        preview_inner = QVBoxLayout(self.preview_frame)
        preview_inner.setContentsMargins(0, 0, 0, 0)
        preview_inner.addWidget(self.preview_view)

        self._preview_overlay = PreviewOverlay(self.preview_frame)
        self._preview_overlay.double_clicked.connect(self.preview_double_clicked.emit)
        self._preview_overlay.raise_()
        self.preview_frame.installEventFilter(self)

        self.preview_ar_widget = AspectRatioWidget(
            self.preview_frame, aspect_ratio=16.0 / 9.0,
            min_width=320, max_width=840
        )
        preview_panel_layout.addWidget(self.preview_ar_widget, 1)
        splitter.addWidget(preview_panel)

        # ── Live Panel (right) ──
        live_panel = QWidget()
        live_panel.setStyleSheet(PANEL_BODY_STYLE)
        live_panel_layout = QVBoxLayout(live_panel)
        live_panel_layout.setContentsMargins(8, 8, 8, 8)
        live_panel_layout.setSpacing(8)

        live_header = QWidget()
        live_header.setStyleSheet(PANEL_HEADER_STYLE)
        live_header_layout = QHBoxLayout(live_header)
        live_header_layout.setContentsMargins(12, 6, 12, 6)

        live_row = QHBoxLayout()
        live_row.setSpacing(4)
        live_dot = QLabel("●")
        live_dot.setStyleSheet(f"color: {RED_500}; font-size: 10px;")
        live_label = QLabel("LIVE")
        live_label.setStyleSheet(f"""
            color: {RED_500}; font-size: 12px; font-weight: 900;
            letter-spacing: 3px;
        """)
        live_row.addWidget(live_dot)
        live_row.addWidget(live_label)
        live_header_layout.addLayout(live_row)
        live_header_layout.addStretch()
        live_panel_layout.addWidget(live_header)

        self.viewport = QFrame()
        self.viewport.setObjectName("LiveOutputViewport")
        self.viewport.setStyleSheet("""
            QFrame#LiveOutputViewport {
                background: black;
                border: 1px solid rgba(239, 68, 68, 0.4);
                border-radius: 8px;
            }
        """)

        vp_layout = QVBoxLayout(self.viewport)
        vp_layout.setContentsMargins(0, 0, 0, 0)

        self.live_view = DisplayView(live_mode=False)
        self.live_view.setMinimumHeight(1)
        vp_layout.addWidget(self.live_view)

        self.ar_widget = AspectRatioWidget(
            self.viewport, aspect_ratio=16.0 / 9.0,
            min_width=320, max_width=840
        )
        live_panel_layout.addWidget(self.ar_widget, 1)
        splitter.addWidget(live_panel)

        # Default splitter ratio: 50% | 50%
        splitter.setSizes([500, 500])
        layout.addWidget(splitter, 1)

        # ── Macro Controls (under Live, right-aligned) ──
        controls_container = QWidget()
        controls = QHBoxLayout(controls_container)
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        btn_prev = QPushButton("<")
        btn_prev.setStyleSheet(MACRO_BTN_AMBER)
        btn_prev.setFixedSize(56, 30)
        btn_prev.setToolTip("Previous Verse")
        btn_prev.clicked.connect(self.prev_verse.emit)
        controls.addWidget(btn_prev)

        _icon_path = os.path.join(os.path.dirname(__file__), "..", "assets", "eye-off.svg")
        self.btn_clear = QPushButton()
        self.btn_clear.setIcon(QIcon(_icon_path))
        self.btn_clear.setIconSize(QSize(14, 14))
        self.btn_clear.setStyleSheet(MACRO_BTN_CLEAR)
        self.btn_clear.setFixedSize(56, 30)
        self.btn_clear.setToolTip("Clear screen / Recall last cleared verse")
        self.btn_clear.clicked.connect(self.clear_recall.emit)
        controls.addWidget(self.btn_clear)

        btn_next = QPushButton(">")
        btn_next.setStyleSheet(MACRO_BTN_AMBER)
        btn_next.setFixedSize(56, 30)
        btn_next.setToolTip("Next Verse")
        btn_next.clicked.connect(self.next_verse.emit)
        controls.addWidget(btn_next)

        # Right-align buttons under the Live viewport (right half of the panel)
        controls_wrapper = QHBoxLayout()
        controls_wrapper.addStretch()
        controls_wrapper.addWidget(controls_container)
        layout.addLayout(controls_wrapper)

    def eventFilter(self, obj, event):
        """Resize the preview overlay to match the preview frame."""
        if obj is self.preview_frame and event.type() == QEvent.Type.Resize:
            r = self.preview_frame.contentsRect()
            self._preview_overlay.setGeometry(r)
        return super().eventFilter(obj, event)

    def set_live_payload(self, payload: dict):
        """Send a verse payload to the live viewport."""
        self.live_view.display_verse(payload)

    def clear_live(self):
        """Clear the live viewport."""
        self.live_view.clear()

    def set_preview_payload(self, payload: dict):
        """Send a verse payload to the preview viewport."""
        self.preview_view.display_verse(payload)

    def clear_preview(self):
        """Clear the preview viewport."""
        self.preview_view.clear()

    def apply_theme(self, theme_data: dict):
        """Apply a theme to both viewports."""
        self.live_view.apply_theme(theme_data)
        self.preview_view.apply_theme(theme_data)

    def apply_theme_to_preview(self, theme_data: dict):
        """Apply a theme to the preview viewport only."""
        self.preview_view.apply_theme(theme_data)
